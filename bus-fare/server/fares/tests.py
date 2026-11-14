from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from .models import Company, Passenger, Route, Settlement, Transaction, Trip, Vehicle
from .services import change_fare, get_current_trip, normalize_phone

PASSWORD = 'demo-pass-2026'
BUS1 = 'demo-terminal-bus-1'
BUS2 = 'demo-terminal-bus-2'


# Real password hashing is slow on purpose; tests create many logins
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class Base(APITestCase):
    def setUp(self):
        call_command('seed_demo', verbosity=0)
        self.bus1 = Vehicle.objects.get(registration='KDA 001A')
        self.bus2 = Vehicle.objects.get(registration='KDB 002B')

    # ----- a vehicle's bridge -----
    def terminal(self, token=BUS1):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Terminal {token}')
        return client

    def tap(self, card_uid, token=BUS1):
        return self.terminal(token).post('/api/tap/', {'card_uid': card_uid}, format='json')

    def poll(self, token=BUS1):
        return self.terminal(token).post('/api/terminal/poll/').json()['lines']

    # ----- a person -----
    def person(self, username, password=PASSWORD):
        client = APIClient()
        response = client.post('/api/auth/login/', {'username': username, 'password': password}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        return client


class TapTests(Base):
    """The same sequence as the 'Full test' table in bus-fare/WIRING.md, on one bus."""

    def test_paid_takes_the_fare(self):
        self.assertEqual(self.tap('E5734107').json(), {'result': 'PAID', 'fare': 50, 'balance': 450})
        self.assertEqual(Passenger.objects.get(card_uid='E5734107').balance, 450)

    def test_second_tap_on_same_trip_is_repeat_and_free(self):
        self.tap('E5734107')
        self.assertEqual(self.tap('E5734107').json(), {'result': 'REPEAT', 'fare': 50, 'balance': 450})

    def test_low_balance_is_refused_and_untouched(self):
        self.assertEqual(self.tap('11223344').json(), {'result': 'LOW', 'fare': 50, 'balance': 30})
        self.assertEqual(Passenger.objects.get(card_uid='11223344').balance, 30)

    def test_unknown_card(self):
        self.assertEqual(self.tap('99999999').json(), {'result': 'UNKNOWN', 'fare': 50, 'balance': 0})

    def test_deactivated_card_is_refused(self):
        Passenger.objects.filter(card_uid='E5734107').update(active=False)
        self.assertEqual(self.tap('E5734107').json()['result'], 'UNKNOWN')
        self.assertEqual(Passenger.objects.get(card_uid='E5734107').balance, 500)

    def test_card_id_is_cleaned_up(self):
        self.assertEqual(self.tap('e5 73 41 07').json()['result'], 'PAID')

    def test_bad_card_id_is_rejected(self):
        self.assertEqual(self.tap('hello').status_code, 400)

    def test_every_tap_is_recorded_with_its_vehicle(self):
        for card in ('E5734107', 'E5734107', '11223344', '99999999'):
            self.tap(card)
        rows = list(Transaction.objects.order_by('id').values_list('result', 'amount', 'balance_after', 'vehicle'))
        b = self.bus1.pk
        self.assertEqual(rows, [('PAID', 50, 450, b), ('REPEAT', 0, 450, b), ('LOW', 0, 30, b), ('UNKNOWN', 0, 0, b)])

    def test_database_refuses_a_second_payment_on_one_trip(self):
        self.tap('E5734107')
        passenger = Passenger.objects.get(card_uid='E5734107')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Transaction.objects.create(
                kind='TAP', result='PAID', card_uid=passenger.card_uid,
                passenger=passenger, trip=get_current_trip(self.bus1), amount=50, balance_after=400)

    def test_no_routes_gives_503(self):
        Trip.objects.all().delete()
        Route.objects.all().delete()
        self.assertEqual(self.tap('E5734107').status_code, 503)


class TerminalTokenTests(Base):
    def test_terminal_endpoints_need_a_valid_token(self):
        for client in (APIClient(), self.terminal('wrong-token')):
            self.assertIn(client.post('/api/tap/', {'card_uid': 'E5734107'}, format='json').status_code, (401, 403))
            self.assertIn(client.post('/api/terminal/poll/').status_code, (401, 403))
            self.assertIn(client.get('/api/status/').status_code, (401, 403))
        self.assertEqual(Transaction.objects.count(), 0)

    def test_a_logged_in_person_cannot_pretend_to_be_a_terminal(self):
        crew = self.person('crew1')
        self.assertIn(crew.post('/api/tap/', {'card_uid': 'E5734107'}, format='json').status_code, (401, 403))
        self.assertEqual(Transaction.objects.count(), 0)


class MultiVehicleTests(Base):
    def test_each_vehicle_has_its_own_trip(self):
        self.assertEqual(self.tap('E5734107', BUS1).json()['result'], 'PAID')
        # Same card on another bus is another trip: it pays again
        self.assertEqual(self.tap('E5734107', BUS2).json(), {'result': 'PAID', 'fare': 50, 'balance': 400})
        self.assertEqual(Trip.objects.filter(ended_at__isnull=True).count(), 2)

    def test_messages_go_to_the_right_vehicle_only(self):
        crew1 = self.person('crew1')
        crew1.post('/api/operator/trip/', {}, format='json')
        self.assertEqual(self.poll(BUS2), [])
        self.assertEqual(self.poll(BUS1), ['FARE 50', 'trip'])
        self.assertEqual(self.poll(BUS1), [])

    def test_status_is_per_vehicle(self):
        chuka = Route.objects.get(name='Marimanti-Chuka')
        self.person('crew2').post('/api/operator/trip/', {'route': chuka.pk}, format='json')
        self.assertEqual(self.terminal(BUS1).get('/api/status/').json()['fare'], 50)
        self.assertEqual(self.terminal(BUS2).get('/api/status/').json()['fare'], 100)

    def test_fare_change_reaches_every_vehicle_on_that_route(self):
        self.tap('E5734107', BUS1)
        self.tap('008DEC53', BUS2)
        change_fare(Route.objects.get(name='Campus shuttle'), 70)
        self.assertEqual(self.poll(BUS1), ['FARE 70'])
        self.assertEqual(self.poll(BUS2), ['FARE 70'])
        change_fare(Route.objects.get(name='Marimanti-Meru'), 300)
        self.assertEqual(self.poll(BUS1), [])


class CompanyPaysTests(Base):
    """Demo Postpaid Ltd pays for its employees (Kim's card A1B2C3D4), limit KSh 5,000."""

    def test_company_pays_and_card_balance_is_untouched(self):
        self.assertEqual(self.tap('A1B2C3D4').json(), {'result': 'PAID', 'fare': 50, 'balance': 200})
        tx = Transaction.objects.get(result='PAID')
        self.assertEqual((tx.paid_by, tx.company.name, tx.amount), ('COMPANY', 'Demo Postpaid Ltd', 50))
        self.assertEqual(Passenger.objects.get(card_uid='A1B2C3D4').balance, 200)

    def test_credit_limit_declines_and_settlement_frees_it(self):
        company = Company.objects.get(name='Demo Postpaid Ltd')
        company.credit_limit = 80
        company.save()
        self.assertEqual(self.tap('A1B2C3D4', BUS1).json()['result'], 'PAID')    # owes 50
        self.assertEqual(self.tap('A1B2C3D4', BUS2).json()['result'], 'LOW')     # 100 > 80
        Settlement.objects.create(company=company, amount=50)
        self.person('crew2').post('/api/operator/trip/', {}, format='json')
        self.assertEqual(self.tap('A1B2C3D4', BUS2).json()['result'], 'PAID')


class OperatorTests(Base):
    def test_crew_sees_only_their_vehicle_names_and_amounts(self):
        for card in ['E5734107', '008DEC53', 'E5734107', '11223344', '99999999']:
            self.tap(card, BUS1)
        self.tap('A1B2C3D4', BUS2)
        self.poll(BUS1)
        live = self.person('crew1').get('/api/operator/live/').json()
        self.assertEqual(live['stats'], {'collected': 100, 'paid': 2, 'repeat': 1, 'refused': 2})
        self.assertEqual([t['result'] for t in live['taps']], ['UNKNOWN', 'LOW', 'REPEAT', 'PAID', 'PAID'])
        self.assertNotIn('Test: Kim', [t['name'] for t in live['taps']])   # tapped on bus 2
        self.assertEqual(set(live['taps'][3]), {'id', 'result', 'name', 'amount', 'created_at'})
        self.assertTrue(live['terminal']['online'])
        self.assertFalse(self.person('crew2').get('/api/operator/live/').json()['terminal']['online'])

    def test_terminal_goes_offline_after_8_seconds(self):
        self.poll(BUS1)
        later = timezone.now() + timedelta(seconds=9)
        with mock.patch('fares.services.timezone.now', return_value=later):
            self.assertFalse(self.person('crew1').get('/api/operator/live/').json()['terminal']['online'])

    def test_trips_and_today(self):
        crew = self.person('crew1')
        self.tap('E5734107')
        self.tap('008DEC53')
        crew.post('/api/operator/trip/', {}, format='json')
        self.tap('E5734107')
        self.tap('A1B2C3D4', BUS2)          # another bus: not counted
        data = crew.get('/api/operator/trips/').json()
        self.assertEqual(data['today'], {'collected': 150, 'paid': 3, 'trips': 2})
        self.assertEqual([t['stats']['collected'] for t in data['trips']], [50, 100])

    def test_new_trip_lets_everyone_pay_again(self):
        self.tap('E5734107')
        response = self.person('crew1').post('/api/operator/trip/', {}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.tap('E5734107').json()['result'], 'PAID')

    def test_new_trip_unknown_route_is_400(self):
        self.assertEqual(self.person('crew1').post('/api/operator/trip/', {'route': 999}, format='json').status_code, 400)

    def test_others_cannot_use_operator_pages(self):
        self.assertEqual(APIClient().get('/api/operator/live/').status_code, 403)
        self.assertEqual(self.person('staffadmin').get('/api/operator/live/').status_code, 403)
        self.assertEqual(self.person('0700000001').get('/api/operator/live/').status_code, 403)


class LoginTests(Base):
    def test_me_login_logout(self):
        client = APIClient()
        self.assertEqual(client.get('/api/auth/me/').json(), {'user': None})
        response = client.post('/api/auth/login/', {'username': 'crew1', 'password': PASSWORD}, format='json')
        user = response.json()['user']
        self.assertEqual((user['role'], user['vehicle']['registration']), ('OPERATOR', 'KDA 001A'))
        self.assertEqual(client.get('/api/auth/me/').json()['user']['username'], 'crew1')
        client.post('/api/auth/logout/')
        self.assertEqual(client.get('/api/auth/me/').json(), {'user': None})

    def test_employee_logs_in_with_phone_typed_any_way(self):
        for typed in ('0700000001', '0700 000 001', '254700000001', '+254700000001'):
            response = APIClient().post('/api/auth/login/', {'username': typed, 'password': PASSWORD}, format='json')
            self.assertEqual(response.json()['user']['role'], 'EMPLOYEE', typed)

    def test_wrong_password(self):
        response = APIClient().post('/api/auth/login/', {'username': 'crew1', 'password': 'nope'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_user_without_profile_cannot_log_in(self):
        get_user_model().objects.create_user('nobody', password=PASSWORD)
        response = APIClient().post('/api/auth/login/', {'username': 'nobody', 'password': PASSWORD}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_phone_numbers(self):
        self.assertEqual(normalize_phone('0712 345 678'), '+254712345678')
        self.assertEqual(normalize_phone('0112345678'), '+254112345678')
        self.assertEqual(normalize_phone('12345'), '')


class CompanyAdminTests(Base):
    NEW = {'name': 'Achieng Otieno', 'staff_number': 'DS-010', 'phone': '0711 222 333',
           'department': 'Sales', 'card_uid': 'aa bb cc dd', 'payment_method': 'MPESA',
           'payment_account': '0711222333'}

    def test_register_employee_who_then_logs_in_and_must_change_password(self):
        admin = self.person('staffadmin')
        response = admin.post('/api/company/employees/', self.NEW, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual((data['card_uid'], data['phone'], data['payment_account']),
                         ('AABBCCDD', '+254711222333', '+254711222333'))
        temp = data['temporary_password']

        employee = self.person('0711222333', temp)
        self.assertTrue(employee.get('/api/auth/me/').json()['user']['must_change_password'])
        self.assertEqual(employee.get('/api/me/').status_code, 403)    # must change first
        changed = employee.post('/api/auth/password/', {'old_password': temp, 'new_password': 'kahawa-ya-asubuhi'},
                                format='json')
        self.assertFalse(changed.json()['user']['must_change_password'])
        self.assertEqual(employee.get('/api/me/').json()['company'], 'Demo Staff Ltd')
        # and the new card works on a bus
        self.assertEqual(self.tap('AABBCCDD').json()['result'], 'LOW')   # balance 0 until topped up

    def test_duplicates_are_refused(self):
        admin = self.person('staffadmin')
        for field, value in (('card_uid', 'E5734107'), ('staff_number', 'DS-001'), ('phone', '0700000001')):
            response = admin.post('/api/company/employees/', {**self.NEW, field: value}, format='json')
            self.assertEqual(response.status_code, 400, field)
            self.assertIn(field, response.json())

    def test_admin_sees_only_their_own_company(self):
        names = [e['name'] for e in self.person('staffadmin').get('/api/company/employees/').json()]
        self.assertEqual(names, ['Blue fob', 'Test: low funds', 'White card'])
        kim = Passenger.objects.get(card_uid='A1B2C3D4')
        self.assertEqual(self.person('staffadmin').get(f'/api/company/employees/{kim.pk}/').status_code, 404)

    def test_search(self):
        found = self.person('staffadmin').get('/api/company/employees/?q=finance').json()
        self.assertEqual([e['name'] for e in found], ['Blue fob'])

    def test_deactivate_blocks_card_and_login(self):
        white = Passenger.objects.get(card_uid='E5734107')
        self.person('staffadmin').patch(f'/api/company/employees/{white.pk}/', {'active': False}, format='json')
        self.assertEqual(self.tap('E5734107').json()['result'], 'UNKNOWN')
        response = APIClient().post('/api/auth/login/', {'username': '0700000001', 'password': PASSWORD}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_phone_change_moves_the_login(self):
        white = Passenger.objects.get(card_uid='E5734107')
        self.person('staffadmin').patch(f'/api/company/employees/{white.pk}/', {'phone': '0799888777'}, format='json')
        self.person('0799888777')

    def test_reset_password(self):
        white = Passenger.objects.get(card_uid='E5734107')
        temp = self.person('staffadmin').post(f'/api/company/employees/{white.pk}/reset-password/').json()[
            'temporary_password']
        self.assertTrue(self.person('0700000001', temp).get('/api/auth/me/').json()['user']['must_change_password'])

    def test_overview_employee_pays(self):
        self.tap('E5734107')
        self.tap('11223344')
        data = self.person('staffadmin').get('/api/company/').json()
        self.assertEqual(data['billing'], 'EMPLOYEE')
        self.assertEqual(data['month'], {'spent': 50, 'trips': 1, 'declined': 1})
        self.assertEqual(data['low_balance'], 1)
        self.assertNotIn('bill', data)

    def test_overview_company_pays_shows_the_bill(self):
        self.tap('A1B2C3D4')
        company = Company.objects.get(name='Demo Postpaid Ltd')
        Settlement.objects.create(company=company, amount=20, reference='MPESA-QX1')
        bill = self.person('postpaidadmin').get('/api/company/').json()['bill']
        self.assertEqual((bill['outstanding'], bill['settled_total'], bill['credit_limit']), (30, 20, 5000))

    def test_others_cannot_use_company_pages(self):
        self.assertEqual(self.person('crew1').get('/api/company/').status_code, 403)
        self.assertEqual(self.person('0700000001').get('/api/company/employees/').status_code, 403)


class EmployeeTests(Base):
    def test_account_shows_balance_and_statement_with_route_and_bus(self):
        self.tap('E5734107')
        data = self.person('0700000001').get('/api/me/').json()
        self.assertEqual((data['balance'], data['company'], data['company_pays']), (450, 'Demo Staff Ltd', False))
        self.assertEqual(data['month'], {'spent': 50, 'trips': 1})
        line = data['transactions'][0]
        self.assertEqual((line['result'], line['route'], line['vehicle']), ('PAID', 'Campus shuttle', 'KDA 001A'))

    def test_top_up_with_payment_method(self):
        me = self.person('0700000003')
        data = me.post('/api/me/topup/', {'amount': 100}, format='json').json()
        self.assertEqual(data['balance'], 130)
        self.assertEqual(data['transactions'][0]['method'], 'MPESA')
        self.assertEqual(self.tap('11223344').json()['result'], 'PAID')

    def test_top_up_limits(self):
        me = self.person('0700000001')
        for amount in (0, -5, 'abc', 49501):
            self.assertEqual(me.post('/api/me/topup/', {'amount': amount}, format='json').status_code, 400, amount)

    def test_no_top_up_when_company_pays(self):
        response = self.person('0700000004').post('/api/me/topup/', {'amount': 100}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('pays your fares', response.json()['detail'])

    def test_change_payment_method(self):
        me = self.person('0700000001')
        data = me.put('/api/me/payment-method/', {'payment_method': 'CARD', 'payment_account': '4111 1111 1111 1234'},
                      format='json')
        self.assertEqual(data.status_code, 400)   # only the last 4 digits are kept
        data = me.put('/api/me/payment-method/', {'payment_method': 'CARD', 'payment_account': '1234'}, format='json')
        self.assertEqual((data.json()['payment_method'], data.json()['payment_account']), ('CARD', '1234'))

    def test_employee_sees_only_their_own_account(self):
        self.tap('008DEC53')
        data = self.person('0700000001').get('/api/me/').json()
        self.assertEqual(data['transactions'], [])
