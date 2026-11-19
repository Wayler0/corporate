"""The fare rules. Views call these; nothing else changes a balance."""
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.utils import timezone

from .models import (
    MAX_BALANCE, Company, Passenger, Profile, Route, Settlement, TerminalMessage, Transaction, Trip,
)


class NoRouteError(Exception):
    """There is no route in the database, so there is no fare to charge."""


class AmountError(Exception):
    """The amount is not allowed (zero, negative, or over the balance ceiling)."""


class NotAllowedError(Exception):
    """The request makes sense but this account may not do it."""


@dataclass
class TapDecision:
    result: str   # PAID, REPEAT, LOW, UNKNOWN or BLOCKED
    fare: int
    balance: int


def normalize_card_uid(text):
    """'e5 73 41 07' -> 'E5734107' (the same clean-up the Uno does)."""
    return ''.join(c for c in str(text).upper() if c in '0123456789ABCDEF')


def normalize_phone(text):
    """'0712 345 678', '254712345678', '+254712345678' -> '+254712345678'.
    Returns '' if it is not a Kenyan mobile number."""
    digits = re.sub(r'\D', '', str(text))
    if re.fullmatch(r'0[17]\d{8}', digits):
        digits = '254' + digits[1:]
    if re.fullmatch(r'254[17]\d{8}', digits):
        return '+' + digits
    return ''


# ---------- Trips (one running trip per vehicle) ----------
def running_trip(vehicle):
    return (Trip.objects.filter(vehicle=vehicle, ended_at__isnull=True)
            .select_related('route').order_by('-id').first())


def get_current_trip(vehicle):
    """The trip this vehicle is running now. Starts one on the first route if none is."""
    trip = running_trip(vehicle)
    if trip:
        return trip
    # Carry on with the route this vehicle ran last; only a vehicle that has never
    # run a trip starts on the first route (the crew changes it on the Trips screen)
    last = Trip.objects.filter(vehicle=vehicle).select_related('route').order_by('-id').first()
    route = last.route if last else Route.objects.order_by('id').first()
    if route is None:
        raise NoRouteError('Add a route first (python manage.py seed_demo).')
    return Trip.objects.create(vehicle=vehicle, route=route)


@transaction.atomic
def start_new_trip(vehicle, route=None):
    """End this vehicle's running trip and start a new one: every card can pay
    once again. With no route given, the new trip stays on the same route."""
    current = running_trip(vehicle)
    if route is None:
        route = current.route if current else Route.objects.order_by('id').first()
    if route is None:
        raise NoRouteError('Add a route first (python manage.py seed_demo).')
    Trip.objects.filter(vehicle=vehicle, ended_at__isnull=True).update(ended_at=timezone.now())
    trip = Trip.objects.create(vehicle=vehicle, route=route)
    queue_for_terminal(vehicle, f'FARE {route.fare}')
    queue_for_terminal(vehicle, 'trip')
    return trip


@transaction.atomic
def change_fare(route, fare):
    """Set a route's fare (platform staff, from the Django admin). Every vehicle
    running a trip on that route is told."""
    if fare < 1 or fare > MAX_BALANCE:
        raise AmountError(f'Fare must be 1 to {MAX_BALANCE}.')
    route.fare = fare
    route.save(update_fields=['fare'])
    for trip in Trip.objects.filter(route=route, ended_at__isnull=True, vehicle__isnull=False):
        queue_for_terminal(trip.vehicle, f'FARE {fare}')
    return route


# ---------- Taps ----------
def company_outstanding(company):
    """What a company-pays company still owes: fares charged minus settlements."""
    charged = Transaction.objects.filter(
        company=company, paid_by=Transaction.PaidBy.COMPANY).aggregate(
        total=models.Sum('amount', default=0))['total']
    paid = company.settlements.aggregate(total=models.Sum('amount', default=0))['total']
    return charged - paid


@transaction.atomic
def process_tap(vehicle, card_uid):
    """Approve or refuse one tap on one vehicle, and record it. Checked in this order:
    UNKNOWN (or deactivated) card -> BLOCKED (reported lost) -> REPEAT (already paid
    this trip) -> LOW -> PAID.
    LOW means: not enough on the card, or (company pays) over the company's credit limit."""
    card_uid = normalize_card_uid(card_uid)
    trip = get_current_trip(vehicle)
    fare = trip.route.fare

    def record(result, passenger=None, amount=0, balance=0, paid_by='', company=None):
        Transaction.objects.create(
            kind=Transaction.Kind.TAP, result=result, card_uid=card_uid, passenger=passenger,
            trip=trip, vehicle=vehicle, amount=amount, balance_after=balance,
            paid_by=paid_by, company=company)
        return TapDecision(result, fare, balance)

    # select_for_update locks the passenger's row so two taps at the same
    # moment cannot both take the fare (PostgreSQL/MySQL; SQLite locks the file).
    passenger = (Passenger.objects.select_for_update(of=('self',)).select_related('company')
                 .filter(card_uid=card_uid).first())
    if passenger is None or not passenger.active:
        return record(Transaction.Result.UNKNOWN, passenger)
    if passenger.card_blocked_at is not None:
        # Recorded, so the employee and their company see that someone tried the
        # lost card. The balance is not shown to whoever is holding it.
        return record(Transaction.Result.BLOCKED, passenger)

    already_paid = Transaction.objects.filter(
        trip=trip, passenger=passenger, result=Transaction.Result.PAID).exists()
    if already_paid:
        return record(Transaction.Result.REPEAT, passenger, balance=passenger.balance)

    company = passenger.company
    if company is not None and company.company_pays:
        # Lock the company too, so two taps cannot both squeeze under the limit
        company = Company.objects.select_for_update().get(pk=company.pk)
        if company.credit_limit and company_outstanding(company) + fare > company.credit_limit:
            return record(Transaction.Result.LOW, passenger, balance=passenger.balance)
        return record(Transaction.Result.PAID, passenger, amount=fare, balance=passenger.balance,
                      paid_by=Transaction.PaidBy.COMPANY, company=company)

    if passenger.balance < fare:
        return record(Transaction.Result.LOW, passenger, balance=passenger.balance)

    passenger.balance -= fare
    passenger.save(update_fields=['balance'])
    return record(Transaction.Result.PAID, passenger, amount=fare, balance=passenger.balance,
                  paid_by=Transaction.PaidBy.CARD)


# ---------- Offline mode ----------
OFFLINE_MAX_AGE = timedelta(days=7)   # an older "seconds ago" is treated as this old


def terminal_cards(vehicle):
    """Everything a terminal needs to decide taps by itself when the server is out
    of reach, as plain text (easy for the ESP32 to read line by line):

        TRIP 12 FARE 50 Campus shuttle
        E5734107 450 -
        008DEC53 450 P
        A1B2C3D4 200 C

    One line per active card: card ID, the card's own balance, and flags:
    P already paid this trip, C the company pays, X the company is over its
    credit limit, B blocked (lost or stolen), - none. Deactivated cards are left out."""
    trip = get_current_trip(vehicle)
    fare = trip.route.fare
    paid = set(Transaction.objects.filter(trip=trip, result=Transaction.Result.PAID)
               .values_list('passenger_id', flat=True))
    over_limit = {c.pk for c in Company.objects.filter(billing=Company.Billing.COMPANY, credit_limit__gt=0)
                  if company_outstanding(c) + fare > c.credit_limit}
    lines = [f'TRIP {trip.pk} FARE {fare} {trip.route.name}']
    for p in Passenger.objects.filter(active=True).select_related('company').order_by('pk'):
        flags = ''
        if p.pk in paid:
            flags += 'P'
        if p.company is not None and p.company.company_pays:
            flags += 'C'
            if p.company_id in over_limit:
                flags += 'X'
        if p.card_blocked_at is not None:
            flags += 'B'
        lines.append(f'{p.card_uid} {p.balance} {flags or "-"}')
    return '\n'.join(lines) + '\n'


def _offline_trip(vehicle, terminal_id, base_id, offset):
    """The trip an offline tap belongs to. offset 0: the server trip the terminal
    knew (base_id). offset n: the n-th trip the terminal started by itself after
    that one, created here (already ended) the first time it is mentioned."""
    base = Trip.objects.filter(pk=base_id, vehicle=vehicle).select_related('route').first() if base_id else None
    if offset == 0:
        return base or get_current_trip(vehicle)
    route = base.route if base else get_current_trip(vehicle).route
    trip, _ = Trip.objects.get_or_create(
        vehicle=vehicle, terminal_ref=f'{terminal_id}:{base_id}+{offset}',
        defaults={'route': route, 'ended_at': timezone.now()})
    return trip


@transaction.atomic
def sync_offline(vehicle, terminal_id, trip_id, trips_started, taps):
    """Record the payments a terminal took while offline, and the trips it started.

    The passenger has already ridden, so the terminal's decision stands; this only
    puts the money and the record right:
      * a card deactivated since, or blocked before the tap  -> UNKNOWN / BLOCKED, no fare
      * already paid on that trip (e.g. online, then offline) -> REPEAT, no fare
      * the company pays                                     -> billed to the company
      * otherwise the fare comes off the card; if the card was spent elsewhere in
        the meantime, what is left is taken (amount < fare shows the shortfall)
    A tap whose terminal_ref was recorded before is skipped, so resending is safe.

    If the terminal started trips offline and the crew has not started a newer one
    on the server, the terminal's latest trip becomes this vehicle's running trip.
    Returns the running trip."""
    now = timezone.now()
    R = Transaction.Result
    for tap in taps:
        ref = f'{terminal_id}:{tap["ref"]}'
        if Transaction.objects.filter(vehicle=vehicle, terminal_ref=ref).exists():
            continue
        trip = _offline_trip(vehicle, terminal_id, tap['trip'], tap['offset'])
        age = tap.get('seconds_ago')
        at = now - min(timedelta(seconds=age), OFFLINE_MAX_AGE) if age is not None else now
        uid = normalize_card_uid(tap['card_uid'])
        passenger = (Passenger.objects.select_for_update(of=('self',)).select_related('company')
                     .filter(card_uid=uid).first())

        def record(result, amount=0, balance=0, paid_by='', company=None):
            t = Transaction.objects.create(
                kind=Transaction.Kind.TAP, result=result, card_uid=uid, passenger=passenger, trip=trip,
                vehicle=vehicle, amount=amount, balance_after=balance, paid_by=paid_by, company=company,
                offline=True, terminal_ref=ref)
            Transaction.objects.filter(pk=t.pk).update(created_at=at)   # when it really happened

        # Never charge more than the trip's route fare, whatever the terminal says
        fare = min(tap['fare'], trip.route.fare)

        if passenger is None or not passenger.active:
            record(R.UNKNOWN)
        elif passenger.card_blocked_at is not None and passenger.card_blocked_at <= at:
            record(R.BLOCKED)
        elif Transaction.objects.filter(trip=trip, passenger=passenger, result=R.PAID).exists():
            record(R.REPEAT, balance=passenger.balance)
        elif passenger.company is not None and passenger.company.company_pays:
            record(R.PAID, amount=fare, balance=passenger.balance,
                   paid_by=Transaction.PaidBy.COMPANY, company=passenger.company)
        else:
            take = min(fare, passenger.balance)
            passenger.balance -= take
            passenger.save(update_fields=['balance'])
            record(R.PAID, amount=take, balance=passenger.balance, paid_by=Transaction.PaidBy.CARD)

    running = running_trip(vehicle)
    if trips_started and (running is None or running.pk == trip_id):
        latest = _offline_trip(vehicle, terminal_id, trip_id, trips_started)
        Trip.objects.filter(vehicle=vehicle, ended_at__isnull=True).exclude(pk=latest.pk).update(ended_at=now)
        Trip.objects.filter(pk=latest.pk).update(ended_at=None)
        running = latest
    return running or get_current_trip(vehicle)


# ---------- Messages for a terminal ----------
def queue_for_terminal(vehicle, line):
    """Leave a line for this vehicle's bridge to send to its Uno on the next poll."""
    TerminalMessage.objects.create(vehicle=vehicle, line=line[:47])


@transaction.atomic
def collect_terminal_lines(vehicle):
    """Hand over this vehicle's waiting lines, oldest first, mark them as sent,
    and note that its terminal is linked."""
    now = timezone.now()
    type(vehicle).objects.filter(pk=vehicle.pk).update(last_seen_at=now)
    waiting = list(TerminalMessage.objects.select_for_update().filter(vehicle=vehicle, delivered_at__isnull=True))
    TerminalMessage.objects.filter(pk__in=[m.pk for m in waiting]).update(delivered_at=now)
    return [m.line for m in waiting]


TERMINAL_ONLINE_SECONDS = 8   # the Uno itself gives up on the link after 8 s without LINK


def terminal_status(vehicle):
    last = vehicle.last_seen_at
    online = last is not None and (timezone.now() - last).total_seconds() <= TERMINAL_ONLINE_SECONDS
    return {'online': online, 'last_seen': last}


# ---------- Lost cards ----------
@transaction.atomic
def block_card(passenger):
    """Stop this card working on every vehicle, straight away. Only the card:
    the employee can still log in. Blocking twice keeps the first time."""
    updated = Passenger.objects.filter(pk=passenger.pk, card_blocked_at__isnull=True).update(
        card_blocked_at=timezone.now())
    passenger.refresh_from_db(fields=['card_blocked_at'])
    return updated == 1


# ---------- Top-up (employee pays billing) ----------
@transaction.atomic
def top_up(passenger, amount, method):
    """Add money to an employee's card. DEMO: no payment provider is connected
    yet, so the payment always succeeds. Real M-Pesa goes here later. Until then
    it only works where settings.DEMO_TOPUP is on (never by default in production)."""
    if not settings.DEMO_TOPUP:
        raise NotAllowedError('Top-up is not available yet: mobile money payments are coming.')
    passenger = Passenger.objects.select_for_update(of=('self',)).select_related('company').get(pk=passenger.pk)
    if passenger.company is not None and passenger.company.company_pays:
        raise NotAllowedError(f'{passenger.company.name} pays your fares, so there is nothing to top up.')
    if not method:
        raise NotAllowedError('Choose a payment method first.')
    room = MAX_BALANCE - passenger.balance
    if amount < 1 or amount > room:
        raise AmountError(f'Amount must be 1 to {room} (a balance cannot pass KSh {MAX_BALANCE}).')
    passenger.balance += amount
    passenger.save(update_fields=['balance'])
    Transaction.objects.create(
        kind=Transaction.Kind.TOPUP, result=Transaction.Result.TOPUP, card_uid=passenger.card_uid,
        passenger=passenger, amount=amount, balance_after=passenger.balance, method=method)
    return passenger


# ---------- Totals ----------
def tap_totals(taps):
    """Money and counts for a set of TAP transactions."""
    R = Transaction.Result
    return taps.aggregate(
        collected=models.Sum('amount', filter=models.Q(result=R.PAID), default=0),
        paid=models.Count('id', filter=models.Q(result=R.PAID)),
        repeat=models.Count('id', filter=models.Q(result=R.REPEAT)),
        refused=models.Count('id', filter=models.Q(result__in=[R.LOW, R.UNKNOWN, R.BLOCKED])),
    )


def trip_stats(trip):
    return tap_totals(Transaction.objects.filter(trip=trip, kind=Transaction.Kind.TAP))


# ---------- Accounts ----------
def temporary_password():
    """Easy to read out or SMS: no 0/O or 1/l."""
    alphabet = 'abcdefghjkmnpqrstuvwxyz23456789'
    return ''.join(secrets.choice(alphabet) for _ in range(10))


@transaction.atomic
def create_employee(company, *, name, staff_number, phone, department, card_uid,
                    payment_method='', payment_account=''):
    """Register an employee with a card and a login (phone number + temporary
    password, changed at first login). Returns (passenger, temporary_password)."""
    User = get_user_model()
    if User.objects.filter(username=phone).exists():
        raise NotAllowedError('An account with this phone number already exists.')
    password = temporary_password()
    user = User.objects.create_user(username=phone, password=password, first_name=name[:150])
    Profile.objects.create(user=user, role=Profile.Role.EMPLOYEE, company=company, must_change_password=True)
    passenger = Passenger.objects.create(
        company=company, user=user, name=name, staff_number=staff_number, phone=phone,
        department=department, card_uid=card_uid, payment_method=payment_method,
        payment_account=payment_account)
    return passenger, password


def reset_password(user):
    password = temporary_password()
    user.set_password(password)
    user.save(update_fields=['password'])
    Profile.objects.filter(user=user).update(must_change_password=True)
    return password


def settlements_total(company):
    return Settlement.objects.filter(company=company).aggregate(total=models.Sum('amount', default=0))['total']
