from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
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
        cache.clear()   # login throttle counts
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

    @override_settings(DEMO_TOPUP=False)
    def test_no_top_up_without_demo_flag(self):
        me = self.person('0700000003')
        self.assertFalse(me.get('/api/me/').json()['topup_enabled'])
        response = me.post('/api/me/topup/', {'amount': 100}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Passenger.objects.get(card_uid='11223344').balance, 30)

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


class LostCardTests(Base):
    """An employee blocks their own lost card; only the company admin brings it back."""

    def block(self, username='0700000001'):
        return self.person(username).post('/api/me/card/block/')

    def test_employee_blocks_own_card(self):
        response = self.block()
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json()['card_blocked_at'])
        # Declined on every vehicle, no fare taken, balance not shown to whoever holds it
        self.assertEqual(self.tap('E5734107').json(), {'result': 'BLOCKED', 'fare': 50, 'balance': 0})
        self.assertEqual(self.tap('E5734107', BUS2).json()['result'], 'BLOCKED')
        self.assertEqual(Passenger.objects.get(card_uid='E5734107').balance, 500)

    def test_login_keeps_working_and_attempts_are_visible(self):
        self.block()
        self.tap('E5734107')
        me = self.person('0700000001').get('/api/me/').json()
        self.assertEqual(me['transactions'][0]['result'], 'BLOCKED')
        self.assertEqual(self.person('staffadmin').get('/api/company/').json()['month']['declined'], 1)

    def test_blocking_twice_keeps_the_first_time(self):
        first = self.block().json()['card_blocked_at']
        self.assertEqual(self.block().json()['card_blocked_at'], first)

    def test_blocks_only_their_own_card(self):
        self.block('0700000001')
        self.assertEqual(self.tap('008DEC53').json()['result'], 'PAID')

    def test_others_cannot_use_the_endpoint(self):
        self.assertEqual(APIClient().post('/api/me/card/block/').status_code, 403)
        self.assertEqual(self.person('staffadmin').post('/api/me/card/block/').status_code, 403)
        self.assertEqual(self.person('crew1').post('/api/me/card/block/').status_code, 403)

    def test_employee_cannot_unblock_through_their_account(self):
        self.block()
        me = self.person('0700000001')
        self.assertEqual(me.patch('/api/me/', {'card_blocked_at': None}, format='json').status_code, 405)
        self.assertEqual(self.tap('E5734107').json()['result'], 'BLOCKED')

    def test_admin_unblocks(self):
        self.block()
        white = Passenger.objects.get(card_uid='E5734107')
        data = self.person('staffadmin').patch(
            f'/api/company/employees/{white.pk}/', {'card_blocked': False}, format='json').json()
        self.assertIsNone(data['card_blocked_at'])
        self.assertEqual(self.tap('E5734107').json()['result'], 'PAID')

    def test_new_card_replaces_the_lost_one(self):
        self.block()
        white = Passenger.objects.get(card_uid='E5734107')
        self.person('staffadmin').patch(
            f'/api/company/employees/{white.pk}/', {'card_uid': 'AABBCCDD'}, format='json')
        self.assertEqual(self.tap('AABBCCDD').json(), {'result': 'PAID', 'fare': 50, 'balance': 450})
        self.assertEqual(self.tap('E5734107').json()['result'], 'UNKNOWN')   # the lost card is nobody's now

    def test_admin_can_block_too(self):
        white = Passenger.objects.get(card_uid='E5734107')
        self.person('staffadmin').patch(f'/api/company/employees/{white.pk}/', {'card_blocked': True}, format='json')
        self.assertEqual(self.tap('E5734107').json()['result'], 'BLOCKED')

    def test_admin_of_another_company_cannot_touch_it(self):
        kim = Passenger.objects.get(card_uid='A1B2C3D4')
        response = self.person('staffadmin').patch(
            f'/api/company/employees/{kim.pk}/', {'card_blocked': True}, format='json')
        self.assertEqual(response.status_code, 404)


class OfflineModeTests(Base):
    """The terminal's card list, and payments it took offline sent later."""
    TERMINAL = 'A1B2C3D4'

    def cards(self, token=BUS1):
        response = self.terminal(token).get('/api/terminal/cards/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/plain'))
        lines = response.content.decode().splitlines()
        return lines[0], {uid: (int(bal), flags) for uid, bal, flags in (l.split(' ') for l in lines[1:])}

    def trip_id(self):
        return get_current_trip(self.bus1).pk

    def sync(self, taps, trips_started=0, trip=None, token=BUS1):
        trip = self.trip_id() if trip is None else trip
        return self.terminal(token).post('/api/terminal/sync/', {
            'terminal': self.TERMINAL, 'trip': trip, 'trips_started': trips_started, 'taps': taps}, format='json')

    def offline_tap(self, ref, uid, offset=0, fare=50, trip=None, seconds_ago=60):
        return {'ref': ref, 'card_uid': uid, 'fare': fare, 'trip': self.trip_id() if trip is None else trip,
                'offset': offset, 'seconds_ago': seconds_ago}

    # ----- card list -----
    def test_card_list(self):
        self.tap('E5734107')
        Passenger.objects.filter(card_uid='11223344').update(card_blocked_at=timezone.now())
        Passenger.objects.filter(card_uid='008DEC53').update(active=False)
        header, cards = self.cards()
        self.assertEqual(header, f'TRIP {self.trip_id()} FARE 50 Campus shuttle')
        self.assertEqual(cards['E5734107'], (450, 'P'))     # paid this trip
        self.assertEqual(cards['11223344'], (30, 'B'))      # blocked
        self.assertEqual(cards['A1B2C3D4'][1], 'C')         # company pays
        self.assertNotIn('008DEC53', cards)                 # deactivated: left out

    def test_card_list_marks_company_over_limit(self):
        Company.objects.filter(billing=Company.Billing.COMPANY).update(credit_limit=40)
        self.assertEqual(self.cards()[1]['A1B2C3D4'][1], 'CX')

    def test_card_list_needs_terminal_token(self):
        self.assertEqual(APIClient().get('/api/terminal/cards/').status_code, 401)
        self.assertEqual(self.person('crew1').get('/api/terminal/cards/').status_code, 401)   # a login is not a terminal

    # ----- sync -----
    def test_offline_payment_is_charged_and_dated(self):
        response = self.sync([self.offline_tap(1, 'E5734107', seconds_ago=600)])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Passenger.objects.get(card_uid='E5734107').balance, 450)
        t = Transaction.objects.get(card_uid='E5734107')
        self.assertEqual((t.result, t.amount, t.offline), ('PAID', 50, True))
        self.assertAlmostEqual((timezone.now() - t.created_at).total_seconds(), 600, delta=5)

    def test_resending_is_harmless(self):
        taps = [self.offline_tap(1, 'E5734107'), self.offline_tap(2, '008DEC53')]
        self.sync(taps)
        self.sync(taps)
        self.assertEqual(Transaction.objects.filter(offline=True).count(), 2)
        self.assertEqual(Passenger.objects.get(card_uid='E5734107').balance, 450)

    def test_same_ref_from_another_terminal_is_a_different_tap(self):
        self.sync([self.offline_tap(1, 'E5734107')])
        self.TERMINAL = 'FFFF0000'
        self.sync([self.offline_tap(1, '008DEC53')])
        self.assertEqual(Transaction.objects.filter(offline=True).count(), 2)

    def test_paid_online_then_offline_on_the_same_trip_is_not_charged_twice(self):
        self.tap('E5734107')
        self.sync([self.offline_tap(1, 'E5734107')])
        self.assertEqual(Passenger.objects.get(card_uid='E5734107').balance, 450)
        self.assertEqual(Transaction.objects.get(offline=True).result, 'REPEAT')

    def test_spent_elsewhere_meanwhile_takes_what_is_left(self):
        Passenger.objects.filter(card_uid='11223344').update(balance=20)
        self.sync([self.offline_tap(1, '11223344')])
        t = Transaction.objects.get(offline=True)
        self.assertEqual((t.result, t.amount, t.balance_after), ('PAID', 20, 0))

    def test_company_pays_offline_ignores_the_limit(self):
        Company.objects.filter(billing=Company.Billing.COMPANY).update(credit_limit=10)
        self.sync([self.offline_tap(1, 'A1B2C3D4')])
        t = Transaction.objects.get(offline=True)
        self.assertEqual((t.result, t.paid_by, t.amount), ('PAID', 'COMPANY', 50))

    def test_card_blocked_before_the_tap_is_not_charged(self):
        Passenger.objects.filter(card_uid='E5734107').update(card_blocked_at=timezone.now() - timedelta(hours=1))
        self.sync([self.offline_tap(1, 'E5734107', seconds_ago=60)])
        self.assertEqual(Transaction.objects.get(offline=True).result, 'BLOCKED')
        self.assertEqual(Passenger.objects.get(card_uid='E5734107').balance, 500)

    def test_card_blocked_after_the_tap_is_charged(self):
        Passenger.objects.filter(card_uid='E5734107').update(card_blocked_at=timezone.now() - timedelta(minutes=1))
        self.sync([self.offline_tap(1, 'E5734107', seconds_ago=3600)])
        self.assertEqual(Transaction.objects.get(offline=True).result, 'PAID')

    def test_unknown_card_is_recorded_without_a_fare(self):
        self.sync([self.offline_tap(1, '99999999')])
        self.assertEqual(Transaction.objects.get(offline=True).result, 'UNKNOWN')

    def test_trips_started_offline(self):
        base = self.trip_id()
        self.tap('E5734107')                                   # paid online on the base trip
        response = self.sync([
            self.offline_tap(1, 'E5734107', offset=1, trip=base),   # new trip 1: pays again
            self.offline_tap(2, 'E5734107', offset=2, trip=base),   # new trip 2: pays again
        ], trips_started=2, trip=base).json()
        self.assertEqual(Passenger.objects.get(card_uid='E5734107').balance, 350)
        running = get_current_trip(self.bus1)
        self.assertEqual(response['trip'], running.pk)
        self.assertNotEqual(running.pk, base)
        self.assertEqual(Trip.objects.filter(vehicle=self.bus1, ended_at__isnull=True).count(), 1)
        self.assertEqual(Trip.objects.filter(vehicle=self.bus1).count(), 3)
        # Online again on the trip the terminal is on: the same card is already paid
        self.assertEqual(self.tap('E5734107').json()['result'], 'REPEAT')

    def test_crew_started_a_trip_on_the_server_meanwhile(self):
        base = self.trip_id()
        newer = self.person('crew1').post('/api/operator/trip/', {}, format='json').json()['trip']
        response = self.sync([self.offline_tap(1, 'E5734107', offset=1, trip=base)], trips_started=1, trip=base)
        self.assertEqual(response.json()['trip'], newer)        # the server's trip wins
        self.assertEqual(Transaction.objects.get(offline=True).result, 'PAID')

    def test_sync_never_charges_more_than_the_route_fare(self):
        self.sync([self.offline_tap(1, 'E5734107', fare=5000)])
        self.assertEqual(Passenger.objects.get(card_uid='E5734107').balance, 450)

    def test_sync_is_per_vehicle(self):
        self.sync([self.offline_tap(1, 'E5734107')], token=BUS2, trip=0)
        t = Transaction.objects.get(offline=True)
        self.assertEqual(t.vehicle, self.bus2)
        self.assertEqual(t.trip.vehicle, self.bus2)

    def test_bad_requests(self):
        self.assertEqual(self.sync([{'ref': 1, 'card_uid': 'xyz', 'fare': 50, 'trip': 0, 'offset': 0}]).status_code, 400)
        self.assertEqual(self.sync([self.offline_tap(1, 'E5734107', fare=0)]).status_code, 400)
        self.assertEqual(self.sync([self.offline_tap(i, 'E5734107') for i in range(101)]).status_code, 400)
        self.assertEqual(APIClient().post('/api/terminal/sync/', {}, format='json').status_code, 401)


class SafetyTests(Base):
    def test_login_is_rate_limited(self):
        client = APIClient()
        codes = [client.post('/api/auth/login/', {'username': '0700000001', 'password': 'wrong'},
                             format='json').status_code for _ in range(11)]
        self.assertEqual(codes[:10], [400] * 10)
        self.assertEqual(codes[10], 429)

    def test_a_vehicle_without_a_running_trip_keeps_its_last_route(self):
        marimanti = Route.objects.get(name='Marimanti-Meru')
        self.person('crew1').post('/api/operator/trip/', {'route': marimanti.pk}, format='json')
        Trip.objects.filter(vehicle=self.bus1).update(ended_at=timezone.now())
        self.assertEqual(self.tap('E5734107').json()['fare'], marimanti.fare)


class ReservedSeatsTests(Base):
    """Reserved-seat boarding counter on the crew live screen (BOARDING_DESIGN.md)."""

    def crew(self):
        return self.person('crew1')   # operator of KDA 001A (bus1)

    def test_default_zero_and_counts_corporate_paid_taps(self):
        crew = self.crew()
        self.assertEqual(crew.get('/api/operator/live/').json()['seats'],
                         {'reserved': 0, 'boarded': 0, 'left': 0})
        self.assertEqual(crew.post('/api/operator/reserved/', {'seats': 15}, format='json').json(),
                         {'reserved': 15, 'boarded': 0, 'left': 15})
        self.tap('E5734107')   # a Demo Staff Ltd employee (corporate)
        self.assertEqual(crew.get('/api/operator/live/').json()['seats'],
                         {'reserved': 15, 'boarded': 1, 'left': 14})

    def test_non_corporate_card_is_not_counted(self):
        Passenger.objects.create(card_uid='DEADBEEF', name='Walk-in', balance=500)
        crew = self.crew()
        crew.post('/api/operator/reserved/', {'seats': 10}, format='json')
        self.tap('DEADBEEF')
        self.assertEqual(crew.get('/api/operator/live/').json()['seats']['boarded'], 0)

    def test_left_never_goes_negative(self):
        crew = self.crew()
        self.tap('E5734107')
        self.assertEqual(crew.get('/api/operator/live/').json()['seats'],
                         {'reserved': 0, 'boarded': 1, 'left': 0})

    def test_seats_must_be_in_range(self):
        crew = self.crew()
        self.assertEqual(crew.post('/api/operator/reserved/', {'seats': -1}, format='json').status_code, 400)
        self.assertEqual(crew.post('/api/operator/reserved/', {'seats': 1000}, format='json').status_code, 400)

    def test_only_the_operator_can_set_reserved_seats(self):
        self.assertEqual(APIClient().post('/api/operator/reserved/', {'seats': 5}, format='json').status_code,
                         403)
