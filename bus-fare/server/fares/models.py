"""Database tables for the bus fare server.

Who is who:
  * Company: an employer that joins the scheme. Its own admin registers its
    employees. Either each employee pays fares from their own card balance,
    or the company pays for all of them and settles the bill later.
  * Passenger: an employee with a card (kept as "Passenger" so the fare code
    and the firmware's wording stay the same).
  * Sacco: a matatu SACCO the platform has an agreement with. It owns its
    vehicles and its routes, and each of its routes has the fare agreed with it,
    so the same road can cost different amounts with different SACCOs.
  * Vehicle: one bus or matatu with its own terminal. Its bridge proves who it
    is with the vehicle's terminal token. Each vehicle runs its own trips, only
    on its own SACCO's routes, and a card is charged that route's fare.
  * Profile: what a login is allowed to see: an operator (one vehicle), a
    company admin (one company), a SACCO admin (one SACCO's vehicles and routes)
    or an employee (their own account).

Money is whole Kenya shillings. The Uno stores a balance in 16 bits and
refuses anything above 50,000, so the server keeps the same ceiling.
"""
import secrets

from django.conf import settings
from django.core.validators import MaxValueValidator, RegexValidator
from django.db import models

MAX_BALANCE = 50000

card_uid_validator = RegexValidator(
    r'^[0-9A-F]{8,20}$',
    'Card ID must be 8 to 20 uppercase hex characters with no spaces, e.g. E5734107.',
)


def new_terminal_token():
    return secrets.token_urlsafe(24)


class Company(models.Model):
    class Billing(models.TextChoices):
        EMPLOYEE = 'EMPLOYEE', 'Employees pay from their own cards'
        COMPANY = 'COMPANY', 'Company pays for its employees and settles later'

    name = models.CharField(max_length=120, unique=True)
    billing = models.CharField(max_length=8, choices=Billing.choices, default=Billing.EMPLOYEE)
    credit_limit = models.PositiveIntegerField(
        default=0, help_text='Company pays only: most the unpaid bill may reach. 0 = no limit.')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'companies'

    def __str__(self):
        return self.name

    @property
    def company_pays(self):
        return self.billing == self.Billing.COMPANY


class Sacco(models.Model):
    """A matatu SACCO with an agreement with the platform. Its fares are fixed by
    that agreement: one fare per route, the same at every hour."""
    name = models.CharField(max_length=120, unique=True)
    licence_number = models.CharField(max_length=40, blank=True, help_text='NTSA licence, if known')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'SACCO'
        verbose_name_plural = 'SACCOs'

    def __str__(self):
        return self.name


class Vehicle(models.Model):
    registration = models.CharField(max_length=20, unique=True, help_text='Number plate, e.g. KDA 123A')
    name = models.CharField(max_length=60, blank=True, help_text='Optional nickname shown to the crew')
    sacco = models.ForeignKey(
        Sacco, null=True, blank=True, on_delete=models.PROTECT, related_name='vehicles',
        help_text="The vehicle runs only this SACCO's routes, at this SACCO's fares")
    terminal_token = models.CharField(
        max_length=64, unique=True, default=new_terminal_token,
        help_text="Secret the vehicle's bridge sends with every call: bridge.py --token ...")
    last_seen_at = models.DateTimeField(null=True, blank=True)   # last bridge poll

    def __str__(self):
        return f'{self.registration} ({self.name})' if self.name else self.registration


class Passenger(models.Model):
    """An employee with a card."""

    class PaymentMethod(models.TextChoices):
        MPESA = 'MPESA', 'M-Pesa'
        AIRTEL = 'AIRTEL', 'Airtel Money'
        CARD = 'CARD', 'Bank card'

    card_uid = models.CharField(max_length=20, unique=True, validators=[card_uid_validator])
    name = models.CharField(max_length=80)
    balance = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(MAX_BALANCE)])
    company = models.ForeignKey(
        Company, null=True, blank=True, on_delete=models.PROTECT, related_name='employees')
    staff_number = models.CharField(max_length=30, blank=True)
    phone = models.CharField(max_length=13, blank=True)          # +2547XXXXXXXX
    department = models.CharField(max_length=60, blank=True)
    payment_method = models.CharField(max_length=6, choices=PaymentMethod.choices, blank=True)
    payment_account = models.CharField(
        max_length=40, blank=True, help_text='M-Pesa / Airtel number, or the last 4 digits of a bank card')
    active = models.BooleanField(default=True, help_text='A deactivated card is declined at the terminal')
    card_blocked_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When the card was reported lost or stolen. A blocked card is declined at the terminal; '
                  'the login keeps working. Cleared when the company admin unblocks it or gives a new card.')
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='passenger')
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'staff_number'], condition=~models.Q(staff_number=''),
                name='unique_staff_number_per_company'),
        ]

    def __str__(self):
        return f'{self.name} ({self.card_uid})'


class Profile(models.Model):
    """What one login may see and do."""

    class Role(models.TextChoices):
        OPERATOR = 'OPERATOR', 'Operator (bus crew)'
        COMPANY_ADMIN = 'COMPANY_ADMIN', 'Company admin'
        SACCO_ADMIN = 'SACCO_ADMIN', 'SACCO admin'
        EMPLOYEE = 'EMPLOYEE', 'Employee'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=13, choices=Role.choices)
    vehicle = models.ForeignKey(
        Vehicle, null=True, blank=True, on_delete=models.PROTECT, related_name='operators',
        help_text='Operators only')
    company = models.ForeignKey(
        Company, null=True, blank=True, on_delete=models.PROTECT, related_name='admins',
        help_text='Company admins and employees')
    sacco = models.ForeignKey(
        Sacco, null=True, blank=True, on_delete=models.PROTECT, related_name='admins',
        help_text='SACCO admins only')
    must_change_password = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.user.username}: {self.get_role_display()}'


class Route(models.Model):
    """One of a SACCO's routes, with the fare agreed with that SACCO."""
    sacco = models.ForeignKey(
        Sacco, null=True, blank=True, on_delete=models.PROTECT, related_name='routes',
        help_text='The SACCO that runs this route. Its vehicles charge this fare')
    name = models.CharField(max_length=40)
    fare = models.PositiveIntegerField(validators=[MaxValueValidator(MAX_BALANCE)])

    class Meta:
        constraints = [
            # Two SACCOs may both run "CBD-Thika", each at its own fare
            models.UniqueConstraint(fields=['sacco', 'name'], name='unique_route_name_per_sacco'),
            models.UniqueConstraint(fields=['name'], condition=models.Q(sacco__isnull=True),
                                    name='unique_route_name_without_sacco'),
        ]

    def __str__(self):
        where = f'{self.sacco.name}: ' if self.sacco_id else ''
        return f'{where}{self.name} (KSh {self.fare})'


class Trip(models.Model):
    """One run of one vehicle. Each card pays once per trip."""
    vehicle = models.ForeignKey(Vehicle, null=True, on_delete=models.PROTECT, related_name='trips')
    route = models.ForeignKey(Route, on_delete=models.PROTECT, related_name='trips')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    # A trip the terminal started while offline: "<terminal id>:<server trip>+<n>"
    terminal_ref = models.CharField(max_length=40, blank=True, default='')
    # Seats held for corporate card holders this trip (reserved-seat boarding;
    # see bus-fare/BOARDING_DESIGN.md). 0 = none reserved.
    reserved_seats = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['vehicle', 'terminal_ref'], condition=~models.Q(terminal_ref=''),
                                    name='one_trip_per_terminal_ref'),
        ]

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
        LOW = 'LOW', 'Low balance / over credit limit'
        UNKNOWN = 'UNKNOWN', 'Unknown or deactivated card'
        BLOCKED = 'BLOCKED', 'Card reported lost or stolen'
        TOPUP = 'TOPUP', 'Top-up'

    class PaidBy(models.TextChoices):
        CARD = 'CARD', 'Card balance'
        COMPANY = 'COMPANY', 'Company account'

    kind = models.CharField(max_length=5, choices=Kind.choices)
    result = models.CharField(max_length=7, choices=Result.choices)
    card_uid = models.CharField(max_length=20)  # kept even when the card is unknown
    passenger = models.ForeignKey(
        Passenger, null=True, blank=True, on_delete=models.PROTECT, related_name='transactions')
    trip = models.ForeignKey(
        Trip, null=True, blank=True, on_delete=models.PROTECT, related_name='transactions')
    vehicle = models.ForeignKey(
        Vehicle, null=True, blank=True, on_delete=models.PROTECT, related_name='transactions')
    paid_by = models.CharField(max_length=7, choices=PaidBy.choices, blank=True)
    company = models.ForeignKey(   # the company billed, when it pays for the fare
        Company, null=True, blank=True, on_delete=models.PROTECT, related_name='billed_transactions')
    method = models.CharField(max_length=6, blank=True)     # top-ups: payment method used
    amount = models.PositiveIntegerField(default=0)         # money that moved (0 for a refusal)
    balance_after = models.PositiveIntegerField(default=0)  # the card's own balance
    created_at = models.DateTimeField(auto_now_add=True)    # offline taps: when the card was tapped
    # Taken by the terminal while offline and sent later. terminal_ref ("<terminal id>:<n>")
    # makes a resend harmless: the same tap is never recorded twice.
    offline = models.BooleanField(default=False)
    terminal_ref = models.CharField(max_length=40, blank=True, default='')

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            # The database itself refuses a second PAID for the same card on the same trip
            models.UniqueConstraint(
                fields=['trip', 'passenger'],
                condition=models.Q(result='PAID'),
                name='one_payment_per_card_per_trip',
            ),
            models.UniqueConstraint(
                fields=['vehicle', 'terminal_ref'], condition=~models.Q(terminal_ref=''),
                name='one_record_per_offline_tap',
            ),
        ]

    def __str__(self):
        return f'{self.created_at:%Y-%m-%d %H:%M} {self.card_uid} {self.result} {self.amount}'


class Settlement(models.Model):
    """Money a company paid towards its bill (company-pays billing).
    Recorded by the platform in the Django admin."""
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='settlements')
    amount = models.PositiveIntegerField()
    reference = models.CharField(max_length=60, blank=True, help_text='e.g. bank or M-Pesa reference')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.company} paid KSh {self.amount}'


class TerminalMessage(models.Model):
    """A line waiting to be sent down the USB cable to one vehicle's Uno
    (FARE ..., trip). That vehicle's bridge collects these when it polls."""
    vehicle = models.ForeignKey(Vehicle, null=True, on_delete=models.CASCADE, related_name='messages')
    line = models.CharField(max_length=47)  # the Uno reads at most 47 characters per line
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.line
