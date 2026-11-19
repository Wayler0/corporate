"""python manage.py seed_demo
Loads demo data: a demo SACCO with the same routes and fares that are built into
the Uno firmware (bus-fare/terminal_mvp/terminal_mvp.ino), the same test cards, two
demo companies, two vehicles of that SACCO and a login for each dashboard. Safe to run again: existing rows are
left as they are.

DEMO ONLY: by default the logins use a published password and the vehicles use
published terminal tokens. On a public server (Railway) set your own secrets first,
or anyone can log in and send taps:
  DEMO_PASSWORD                 password of every demo login
  DEMO_TERMINAL_TOKEN_BUS1/2    terminal tokens of KDA 001A / KDB 002B
They only apply when the rows are first created.
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from fares.models import Company, Passenger, Profile, Route, Sacco, Vehicle

DEMO_PASSWORD = os.environ.get('DEMO_PASSWORD') or 'demo-pass-2026'

SACCO = 'Demo Sacco'

# the demo SACCO's routes and agreed fares
ROUTES = [('Campus shuttle', 50), ('Marimanti-Chuka', 100), ('Marimanti-Meru', 250)]

COMPANIES = [
    ('Demo Staff Ltd', Company.Billing.EMPLOYEE, 0),
    ('Demo Postpaid Ltd', Company.Billing.COMPANY, 5000),
]

# card, name, balance, company, staff number, phone, department
PASSENGERS = [
    ('E5734107', 'White card', 500, 'Demo Staff Ltd', 'DS-001', '+254700000001', 'Operations'),
    ('008DEC53', 'Blue fob', 500, 'Demo Staff Ltd', 'DS-002', '+254700000002', 'Finance'),
    ('11223344', 'Test: low funds', 30, 'Demo Staff Ltd', 'DS-003', '+254700000003', 'Operations'),
    ('A1B2C3D4', 'Test: Kim', 200, 'Demo Postpaid Ltd', 'DP-001', '+254700000004', 'Admin'),
]

# registration, nickname, terminal token (the bridge's --token)
VEHICLES = [
    ('KDA 001A', 'Bus 1', os.environ.get('DEMO_TERMINAL_TOKEN_BUS1') or 'demo-terminal-bus-1'),
    ('KDB 002B', 'Bus 2', os.environ.get('DEMO_TERMINAL_TOKEN_BUS2') or 'demo-terminal-bus-2'),
]

# username, role, vehicle or company
LOGINS = [
    ('crew1', Profile.Role.OPERATOR, 'KDA 001A'),
    ('crew2', Profile.Role.OPERATOR, 'KDB 002B'),
    ('staffadmin', Profile.Role.COMPANY_ADMIN, 'Demo Staff Ltd'),
    ('postpaidadmin', Profile.Role.COMPANY_ADMIN, 'Demo Postpaid Ltd'),
    ('saccoadmin', Profile.Role.SACCO_ADMIN, SACCO),
]


class Command(BaseCommand):
    help = 'Load demo routes, companies, cards, vehicles and dashboard logins.'

    def handle(self, *args, **options):
        User = get_user_model()
        sacco, _ = Sacco.objects.get_or_create(name=SACCO)
        for name, fare in ROUTES:
            # Older databases have these routes without a SACCO: give them the demo one
            route = Route.objects.filter(name=name, sacco__isnull=True).first()
            if route:
                route.sacco = sacco
                route.save(update_fields=['sacco'])
            else:
                Route.objects.get_or_create(sacco=sacco, name=name, defaults={'fare': fare})
        companies = {}
        for name, billing, limit in COMPANIES:
            companies[name], _ = Company.objects.get_or_create(
                name=name, defaults={'billing': billing, 'credit_limit': limit})
        vehicles = {}
        for registration, nickname, token in VEHICLES:
            vehicles[registration], _ = Vehicle.objects.get_or_create(
                registration=registration, defaults={'name': nickname, 'terminal_token': token, 'sacco': sacco})
            if vehicles[registration].sacco is None:   # older databases
                vehicles[registration].sacco = sacco
                vehicles[registration].save(update_fields=['sacco'])

        def login(username, first_name, role, **where):
            user, created = User.objects.get_or_create(username=username, defaults={'first_name': first_name})
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            Profile.objects.get_or_create(user=user, defaults={'role': role, **where})
            return user

        for card, name, balance, company, staff, phone, department in PASSENGERS:
            passenger, _ = Passenger.objects.get_or_create(card_uid=card, defaults={'name': name, 'balance': balance})
            if passenger.company is None:   # older databases: fill in the new details
                passenger.company, passenger.staff_number = companies[company], staff
                passenger.phone, passenger.department = phone, department
                passenger.payment_method, passenger.payment_account = Passenger.PaymentMethod.MPESA, phone
            if passenger.user is None:
                passenger.user = login(phone, name, Profile.Role.EMPLOYEE, company=companies[company])
            passenger.save()

        for username, role, target in LOGINS:
            if role == Profile.Role.OPERATOR:
                login(username, username, role, vehicle=vehicles[target])
            elif role == Profile.Role.SACCO_ADMIN:
                login(username, username, role, sacco=sacco)
            else:
                login(username, username, role, company=companies[target])

        if options['verbosity'] == 0:
            return
        self.stdout.write(self.style.SUCCESS(
            f'{Sacco.objects.count()} SACCOs, {Route.objects.count()} routes, {Company.objects.count()} companies, '
            f'{Passenger.objects.count()} employees, {Vehicle.objects.count()} vehicles.'))
        secret = 'DEMO_PASSWORD' in os.environ
        self.stdout.write('Demo logins (password: ' + ('the DEMO_PASSWORD variable' if secret else f'"{DEMO_PASSWORD}"') + '):')
        self.stdout.write('  crew1 / crew2              operator of KDA 001A / KDB 002B')
        self.stdout.write('  staffadmin / postpaidadmin company admin (employees pay / company pays)')
        self.stdout.write(f'  saccoadmin                 SACCO admin of {SACCO}')
        self.stdout.write('  0700000001 ... 0700000004  employees (White card, Blue fob, low funds, Kim)')
        if 'DEMO_TERMINAL_TOKEN_BUS1' not in os.environ:
            self.stdout.write('Bridges: python3 bridge.py --token demo-terminal-bus-1   (or demo-terminal-bus-2)')
