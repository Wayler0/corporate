from django.core.management import call_command
from django.db import IntegrityError, transaction
from rest_framework.test import APITestCase

from .models import Passenger, Route, Transaction, Trip
from .services import get_current_trip


class TapTests(APITestCase):
    """The same sequence as the 'Full test' table in bus-fare/WIRING.md."""

    def setUp(self):
        call_command('seed_demo', verbosity=0)

    def tap(self, card_uid):
        return self.client.post('/api/tap/', {'card_uid': card_uid}, format='json')

    def test_paid_takes_the_fare(self):
        response = self.tap('E5734107')
        self.assertEqual(response.json(), {'result': 'PAID', 'fare': 50, 'balance': 450})
        self.assertEqual(Passenger.objects.get(card_uid='E5734107').balance, 450)

    def test_second_tap_on_same_trip_is_repeat_and_free(self):
        self.tap('E5734107')
        response = self.tap('E5734107')
        self.assertEqual(response.json(), {'result': 'REPEAT', 'fare': 50, 'balance': 450})

    def test_low_balance_is_refused_and_untouched(self):
        response = self.tap('11223344')
        self.assertEqual(response.json(), {'result': 'LOW', 'fare': 50, 'balance': 30})
        self.assertEqual(Passenger.objects.get(card_uid='11223344').balance, 30)

    def test_unknown_card(self):
        response = self.tap('99999999')
        self.assertEqual(response.json(), {'result': 'UNKNOWN', 'fare': 50, 'balance': 0})

    def test_new_trip_lets_the_card_pay_again(self):
        self.tap('E5734107')
        Trip.objects.update(ended_at='2026-11-14T12:00:00+03:00')
        response = self.tap('E5734107')
        self.assertEqual(response.json(), {'result': 'PAID', 'fare': 50, 'balance': 400})

    def test_card_id_is_cleaned_up(self):
        self.assertEqual(self.tap('e5 73 41 07').json()['result'], 'PAID')

    def test_bad_card_id_is_rejected(self):
        self.assertEqual(self.tap('hello').status_code, 400)
        self.assertEqual(self.client.post('/api/tap/', {}, format='json').status_code, 400)

    def test_every_tap_is_recorded(self):
        for card in ('E5734107', 'E5734107', '11223344', '99999999'):
            self.tap(card)
        results = list(Transaction.objects.order_by('id').values_list('result', 'amount', 'balance_after'))
        self.assertEqual(results, [('PAID', 50, 450), ('REPEAT', 0, 450), ('LOW', 0, 30), ('UNKNOWN', 0, 0)])

    def test_database_refuses_a_second_payment_on_one_trip(self):
        self.tap('E5734107')
        passenger = Passenger.objects.get(card_uid='E5734107')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Transaction.objects.create(
                kind='TAP', result='PAID', card_uid=passenger.card_uid,
                passenger=passenger, trip=get_current_trip(), amount=50, balance_after=400)

    def test_no_routes_gives_503(self):
        Trip.objects.all().delete()
        Route.objects.all().delete()
        self.assertEqual(self.tap('E5734107').status_code, 503)


class Step2Tests(APITestCase):
    def setUp(self):
        call_command('seed_demo', verbosity=0)

    def post(self, path, data=None):
        return self.client.post(path, data or {}, format='json')

    def poll(self):
        return self.post('/api/terminal/poll/').json()['lines']

    # ----- top-up -----
    def test_topup_adds_money_records_it_and_tells_the_terminal(self):
        response = self.post('/api/topup/', {'card_uid': '11223344', 'amount': 100})
        self.assertEqual(response.json(), {'card_uid': '11223344', 'name': 'Test: low funds', 'balance': 130})
        last = Transaction.objects.order_by('-id').first()
        self.assertEqual((last.kind, last.result, last.amount, last.balance_after), ('TOPUP', 'TOPUP', 100, 130))
        self.assertEqual(self.poll(), ['MSG Top-up +100|Bal: KSh 130'])

    def test_topup_then_tap_pays(self):
        self.post('/api/topup/', {'card_uid': '11223344', 'amount': 100})
        response = self.post('/api/tap/', {'card_uid': '11223344'})
        self.assertEqual(response.json(), {'result': 'PAID', 'fare': 50, 'balance': 80})

    def test_topup_unknown_card_is_404(self):
        self.assertEqual(self.post('/api/topup/', {'card_uid': '99999999', 'amount': 100}).status_code, 404)

    def test_topup_bad_amounts_are_refused(self):
        for amount in (0, -5, 'abc', 49501):  # white card has 500: 49,501 would pass 50,000
            response = self.post('/api/topup/', {'card_uid': 'E5734107', 'amount': amount})
            self.assertEqual(response.status_code, 400, amount)
        self.assertEqual(Passenger.objects.get(card_uid='E5734107').balance, 500)
        self.assertEqual(self.poll(), [])

    def test_topup_up_to_the_ceiling_is_allowed(self):
        response = self.post('/api/topup/', {'card_uid': 'E5734107', 'amount': 49500})
        self.assertEqual(response.json()['balance'], 50000)

    # ----- trips -----
    def test_new_trip_lets_everyone_pay_again(self):
        self.post('/api/tap/', {'card_uid': 'E5734107'})
        response = self.post('/api/trip/')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['fare'], 50)
        self.assertEqual(Trip.objects.filter(ended_at__isnull=True).count(), 1)
        self.assertEqual(self.poll(), ['FARE 50', 'trip'])
        self.assertEqual(self.post('/api/tap/', {'card_uid': 'E5734107'}).json()['result'], 'PAID')

    def test_new_trip_on_another_route_uses_its_fare(self):
        chuka = Route.objects.get(name='Marimanti-Chuka')
        response = self.post('/api/trip/', {'route': chuka.pk})
        self.assertEqual(response.json()['route_name'], 'Marimanti-Chuka')
        self.assertEqual(self.poll(), ['FARE 100', 'trip'])
        self.assertEqual(
            self.post('/api/tap/', {'card_uid': 'E5734107'}).json(),
            {'result': 'PAID', 'fare': 100, 'balance': 400})

    def test_new_trip_unknown_route_is_400(self):
        self.assertEqual(self.post('/api/trip/', {'route': 999}).status_code, 400)

    # ----- fares -----
    def test_change_fare_of_the_running_route(self):
        response = self.post('/api/fare/', {'fare': 70})
        self.assertEqual(response.json()['fare'], 70)
        self.assertEqual(self.poll(), ['FARE 70'])
        self.assertEqual(
            self.post('/api/tap/', {'card_uid': 'E5734107'}).json(),
            {'result': 'PAID', 'fare': 70, 'balance': 430})

    def test_change_fare_of_another_route_does_not_disturb_the_terminal(self):
        meru = Route.objects.get(name='Marimanti-Meru')
        self.post('/api/fare/', {'fare': 300, 'route': meru.pk})
        self.assertEqual(Route.objects.get(pk=meru.pk).fare, 300)
        self.assertEqual(self.poll(), [])

    def test_bad_fares_are_refused(self):
        for fare in (0, -1, 50001, 'abc'):
            self.assertEqual(self.post('/api/fare/', {'fare': fare}).status_code, 400, fare)

    # ----- status, routes, poll -----
    def test_status_and_routes(self):
        status = self.client.get('/api/status/').json()
        self.assertEqual((status['route_name'], status['fare']), ('Campus shuttle', 50))
        self.assertEqual([r['fare'] for r in self.client.get('/api/routes/').json()], [50, 100, 250])

    def test_poll_hands_each_line_over_once_in_order(self):
        self.post('/api/topup/', {'card_uid': 'E5734107', 'amount': 10})
        self.post('/api/topup/', {'card_uid': 'E5734107', 'amount': 20})
        self.assertEqual(self.poll(), ['MSG Top-up +10|Bal: KSh 510', 'MSG Top-up +20|Bal: KSh 530'])
        self.assertEqual(self.poll(), [])

    def test_terminal_lines_fit_the_lcd_and_the_uno_buffer(self):
        self.post('/api/topup/', {'card_uid': 'E5734107', 'amount': 49500})
        line = self.poll()[0]
        self.assertLessEqual(len(line), 47)
        for half in line[4:].split('|'):
            self.assertLessEqual(len(half), 16)
