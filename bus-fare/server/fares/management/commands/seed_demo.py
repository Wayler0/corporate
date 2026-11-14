"""python manage.py seed_demo
Loads the same routes and test cards that are built into the Uno firmware
(bus-fare/terminal_mvp/terminal_mvp.ino), so both sides start out agreeing.
Safe to run again: existing rows are left as they are."""
from django.core.management.base import BaseCommand

from fares.models import Passenger, Route

ROUTES = [('Campus shuttle', 50), ('Marimanti-Chuka', 100), ('Marimanti-Meru', 250)]
PASSENGERS = [
    ('A1B2C3D4', 'Test: Kim', 200),
    ('11223344', 'Test: low funds', 30),
    ('E5734107', 'White card', 500),
    ('008DEC53', 'Blue fob', 500),
]


class Command(BaseCommand):
    help = 'Load the demo routes and test cards.'

    def handle(self, *args, **options):
        for name, fare in ROUTES:
            Route.objects.get_or_create(name=name, defaults={'fare': fare})
        for card_uid, name, balance in PASSENGERS:
            Passenger.objects.get_or_create(card_uid=card_uid, defaults={'name': name, 'balance': balance})
        if options['verbosity'] == 0:
            return
        self.stdout.write(self.style.SUCCESS(
            f'{Route.objects.count()} routes, {Passenger.objects.count()} passengers in the database.'))
