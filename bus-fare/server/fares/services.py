"""The fare rules. Views call these; nothing else changes a balance."""
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from .models import MAX_BALANCE, Passenger, Route, TerminalMessage, Transaction, Trip


class NoRouteError(Exception):
    """There is no route in the database, so there is no fare to charge."""


class UnknownCardError(Exception):
    """No passenger has this card."""


class AmountError(Exception):
    """The amount is not allowed (zero, negative, or over the balance ceiling)."""


@dataclass
class TapDecision:
    result: str   # PAID, REPEAT, LOW or UNKNOWN
    fare: int
    balance: int


def normalize_card_uid(text):
    """'e5 73 41 07' -> 'E5734107' (the same clean-up the Uno does)."""
    return ''.join(c for c in str(text).upper() if c in '0123456789ABCDEF')


def get_current_trip():
    """The trip that is running now. Starts one on the first route if none is."""
    trip = Trip.objects.filter(ended_at__isnull=True).select_related('route').order_by('-id').first()
    if trip:
        return trip
    route = Route.objects.order_by('id').first()
    if route is None:
        raise NoRouteError('Add a route first (python manage.py seed_demo).')
    return Trip.objects.create(route=route)


@transaction.atomic
def process_tap(card_uid):
    """Approve or refuse one tap, and record it. Checked in this order:
    UNKNOWN card -> REPEAT (already paid this trip) -> LOW balance -> PAID."""
    card_uid = normalize_card_uid(card_uid)
    trip = get_current_trip()
    fare = trip.route.fare

    def record(result, passenger=None, amount=0, balance=0):
        Transaction.objects.create(
            kind=Transaction.Kind.TAP, result=result, card_uid=card_uid,
            passenger=passenger, trip=trip, amount=amount, balance_after=balance)
        return TapDecision(result, fare, balance)

    # select_for_update locks the passenger's row so two taps at the same
    # moment cannot both take the fare (PostgreSQL/MySQL; SQLite locks the file).
    passenger = Passenger.objects.select_for_update().filter(card_uid=card_uid).first()
    if passenger is None:
        return record(Transaction.Result.UNKNOWN)

    already_paid = Transaction.objects.filter(
        trip=trip, passenger=passenger, result=Transaction.Result.PAID).exists()
    if already_paid:
        return record(Transaction.Result.REPEAT, passenger, balance=passenger.balance)

    if passenger.balance < fare:
        return record(Transaction.Result.LOW, passenger, balance=passenger.balance)

    passenger.balance -= fare
    passenger.save(update_fields=['balance'])
    return record(Transaction.Result.PAID, passenger, amount=fare, balance=passenger.balance)


# ---------- Messages for the terminal ----------
def queue_for_terminal(line):
    """Leave a line for the bridge to send to the Uno on its next poll."""
    TerminalMessage.objects.create(line=line[:47])


@transaction.atomic
def collect_terminal_lines():
    """Hand over every waiting line, oldest first, and mark them as sent."""
    waiting = list(TerminalMessage.objects.select_for_update().filter(delivered_at__isnull=True))
    TerminalMessage.objects.filter(pk__in=[m.pk for m in waiting]).update(delivered_at=timezone.now())
    return [m.line for m in waiting]


# ---------- Top-up ----------
@transaction.atomic
def top_up(card_uid, amount):
    """Add money to a card, record it, and tell the terminal. Returns the passenger."""
    card_uid = normalize_card_uid(card_uid)
    passenger = Passenger.objects.select_for_update().filter(card_uid=card_uid).first()
    if passenger is None:
        raise UnknownCardError(f'No passenger has card {card_uid}.')
    room = MAX_BALANCE - passenger.balance
    if amount < 1 or amount > room:
        raise AmountError(f'Amount must be 1 to {room} (a balance cannot pass KSh {MAX_BALANCE}).')
    passenger.balance += amount
    passenger.save(update_fields=['balance'])
    Transaction.objects.create(
        kind=Transaction.Kind.TOPUP, result=Transaction.Result.TOPUP, card_uid=card_uid,
        passenger=passenger, amount=amount, balance_after=passenger.balance)
    queue_for_terminal(f'MSG Top-up +{amount}|Bal: KSh {passenger.balance}')
    return passenger


# ---------- Trips and fares ----------
@transaction.atomic
def start_new_trip(route=None):
    """End the running trip and start a new one: every card can pay once again.
    With no route given, the new trip stays on the same route."""
    current = Trip.objects.filter(ended_at__isnull=True).select_related('route').order_by('-id').first()
    if route is None:
        route = current.route if current else Route.objects.order_by('id').first()
    if route is None:
        raise NoRouteError('Add a route first (python manage.py seed_demo).')
    Trip.objects.filter(ended_at__isnull=True).update(ended_at=timezone.now())
    trip = Trip.objects.create(route=route)
    queue_for_terminal(f'FARE {route.fare}')
    queue_for_terminal('trip')
    return trip


@transaction.atomic
def change_fare(fare, route=None):
    """Set a route's fare. With no route given, it is the running trip's route.
    The terminal is told only when the fare it is charging has changed."""
    if fare < 1 or fare > MAX_BALANCE:
        raise AmountError(f'Fare must be 1 to {MAX_BALANCE}.')
    trip = get_current_trip()
    if route is None:
        route = trip.route
    route.fare = fare
    route.save(update_fields=['fare'])
    if route.pk == trip.route_id:
        queue_for_terminal(f'FARE {fare}')
    return route
