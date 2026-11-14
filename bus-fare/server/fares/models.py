"""Database tables for the bus fare server.

Money is whole Kenya shillings. The Uno stores a balance in 16 bits and
refuses anything above 50,000, so the server keeps the same ceiling.
"""
from django.core.validators import MaxValueValidator, RegexValidator
from django.db import models

MAX_BALANCE = 50000

card_uid_validator = RegexValidator(
    r'^[0-9A-F]{8,20}$',
    'Card ID must be 8 to 20 uppercase hex characters with no spaces, e.g. E5734107.',
)


class Passenger(models.Model):
    card_uid = models.CharField(max_length=20, unique=True, validators=[card_uid_validator])
    name = models.CharField(max_length=80)
    balance = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(MAX_BALANCE)])

    def __str__(self):
        return f'{self.name} ({self.card_uid})'


class Route(models.Model):
    name = models.CharField(max_length=40, unique=True)
    fare = models.PositiveIntegerField(validators=[MaxValueValidator(MAX_BALANCE)])

    def __str__(self):
        return f'{self.name} (KSh {self.fare})'


class Trip(models.Model):
    """One run of the bus. Each card pays once per trip."""
    route = models.ForeignKey(Route, on_delete=models.PROTECT, related_name='trips')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'Trip {self.pk} on {self.route.name}'


class Transaction(models.Model):
    """Every tap (paid or refused) and every top-up. Never edited or deleted."""

    class Kind(models.TextChoices):
        TAP = 'TAP', 'Tap'
        TOPUP = 'TOPUP', 'Top-up'

    class Result(models.TextChoices):
        PAID = 'PAID', 'Paid'
        REPEAT = 'REPEAT', 'Already paid this trip'
        LOW = 'LOW', 'Low balance'
        UNKNOWN = 'UNKNOWN', 'Unknown card'
        TOPUP = 'TOPUP', 'Top-up'

    kind = models.CharField(max_length=5, choices=Kind.choices)
    result = models.CharField(max_length=7, choices=Result.choices)
    card_uid = models.CharField(max_length=20)  # kept even when the card is unknown
    passenger = models.ForeignKey(
        Passenger, null=True, blank=True, on_delete=models.PROTECT, related_name='transactions')
    trip = models.ForeignKey(
        Trip, null=True, blank=True, on_delete=models.PROTECT, related_name='transactions')
    amount = models.PositiveIntegerField(default=0)         # money that moved (0 for a refusal)
    balance_after = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            # The database itself refuses a second PAID for the same card on the same trip
            models.UniqueConstraint(
                fields=['trip', 'passenger'],
                condition=models.Q(result='PAID'),
                name='one_payment_per_card_per_trip',
            ),
        ]

    def __str__(self):
        return f'{self.created_at:%Y-%m-%d %H:%M} {self.card_uid} {self.result} {self.amount}'


class TerminalMessage(models.Model):
    """A line waiting to be sent down the USB cable to the Uno
    (MSG ..., FARE ..., trip). The bridge collects these when it polls."""
    line = models.CharField(max_length=47)  # the Uno reads at most 47 characters per line
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.line
