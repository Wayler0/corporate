from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers

from .models import MAX_BALANCE, Passenger, Route, Transaction
from .services import normalize_card_uid, normalize_phone


class CardUidField(serializers.CharField):
    """Accepts 'e5 73 41 07' and hands the views 'E5734107'."""

    def __init__(self, **kwargs):
        super().__init__(max_length=40, **kwargs)

    def to_internal_value(self, data):
        uid = normalize_card_uid(super().to_internal_value(data))
        if not 8 <= len(uid) <= 20:
            raise serializers.ValidationError('Card ID must be 8 to 20 hex characters.')
        return uid


class PhoneField(serializers.CharField):
    """Accepts 0712 345 678 / 254712345678 / +254712345678; stores +254712345678."""

    def __init__(self, **kwargs):
        super().__init__(max_length=20, **kwargs)

    def to_internal_value(self, data):
        phone = normalize_phone(super().to_internal_value(data))
        if not phone:
            raise serializers.ValidationError('Enter a Kenyan mobile number, e.g. 0712 345 678.')
        return phone


# ---------- Terminal ----------
class TapRequestSerializer(serializers.Serializer):
    card_uid = CardUidField()


class TapResponseSerializer(serializers.Serializer):
    result = serializers.CharField()
    fare = serializers.IntegerField()
    balance = serializers.IntegerField()


class OfflineTapSerializer(serializers.Serializer):
    ref = serializers.IntegerField(min_value=0)            # the terminal's own tap number
    card_uid = CardUidField()
    fare = serializers.IntegerField(min_value=1, max_value=MAX_BALANCE)
    trip = serializers.IntegerField(min_value=0)           # server trip the terminal knew (0 = none)
    offset = serializers.IntegerField(min_value=0, max_value=10000)   # trips started offline since
    seconds_ago = serializers.IntegerField(min_value=0, required=False, allow_null=True, default=None)


class OfflineSyncSerializer(serializers.Serializer):
    terminal = serializers.RegexField(r'^[0-9A-Fa-f]{4,16}$')   # random ID the terminal made itself
    trip = serializers.IntegerField(min_value=0)
    trips_started = serializers.IntegerField(min_value=0, max_value=10000)
    taps = OfflineTapSerializer(many=True, max_length=100)


# ---------- Logins ----------
class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, help_text='Username, or an employee\'s phone number')
    password = serializers.CharField(max_length=128, trim_whitespace=False)

    def validate_username(self, value):
        # Employees log in with their phone number, typed however they like
        return normalize_phone(value) or value.strip()


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)

    def validate(self, data):
        user = self.context['user']
        if not user.check_password(data['old_password']):
            raise serializers.ValidationError({'old_password': 'That is not your current password.'})
        validate_password(data['new_password'], user)
        return data


# ---------- Operator ----------
class NewTripRequestSerializer(serializers.Serializer):
    route = serializers.PrimaryKeyRelatedField(queryset=Route.objects.all(), required=False)


class ReservedSeatsSerializer(serializers.Serializer):
    seats = serializers.IntegerField(min_value=0, max_value=999)


class RouteSerializer(serializers.ModelSerializer):
    sacco = serializers.CharField(source='sacco.name', default=None)

    class Meta:
        model = Route
        fields = ['id', 'name', 'fare', 'sacco']


class OperatorTapSerializer(serializers.ModelSerializer):
    """What the bus crew sees for one tap: who and how much. No card ID, no balance."""
    name = serializers.CharField(source='passenger.name', default=None)

    class Meta:
        model = Transaction
        fields = ['id', 'result', 'name', 'amount', 'created_at']


# ---------- Company admin and employee ----------
class AccountTransactionSerializer(serializers.ModelSerializer):
    """One line of an employee's statement."""
    route = serializers.CharField(source='trip.route.name', default=None)
    vehicle = serializers.CharField(source='vehicle.registration', default=None)
    sacco = serializers.CharField(source='vehicle.sacco.name', default=None)
    name = serializers.CharField(source='passenger.name', default=None)

    class Meta:
        model = Transaction
        fields = ['id', 'kind', 'result', 'amount', 'paid_by', 'method', 'balance_after',
                  'route', 'vehicle', 'sacco', 'name', 'created_at']


def validate_payment_account(method, account):
    """M-Pesa / Airtel need a phone number; a bank card keeps only its last 4 digits."""
    if not method:
        return ''
    if method in (Passenger.PaymentMethod.MPESA, Passenger.PaymentMethod.AIRTEL):
        phone = normalize_phone(account)
        if not phone:
            raise serializers.ValidationError({'payment_account': 'Enter the mobile money number, e.g. 0712 345 678.'})
        return phone
    digits = ''.join(c for c in account if c.isdigit())
    if len(digits) != 4:
        raise serializers.ValidationError({'payment_account': 'Enter the last 4 digits of the card.'})
    return digits


class EmployeeSerializer(serializers.ModelSerializer):
    """A company admin's view of one employee. The company comes from the admin."""
    card_uid = CardUidField()
    phone = PhoneField()
    staff_number = serializers.CharField(max_length=30)
    department = serializers.CharField(max_length=60, allow_blank=True, required=False, default='')
    payment_account = serializers.CharField(max_length=40, allow_blank=True, required=False, default='')
    # Admin: true blocks the card (lost or stolen), false unblocks it. Giving the
    # employee a new card_uid also unblocks, since the lost card is no longer theirs.
    card_blocked = serializers.BooleanField(required=False, write_only=True)

    class Meta:
        model = Passenger
        fields = ['id', 'name', 'staff_number', 'phone', 'department', 'card_uid',
                  'payment_method', 'payment_account', 'active', 'card_blocked', 'card_blocked_at',
                  'balance', 'created_at']
        read_only_fields = ['id', 'balance', 'card_blocked_at', 'created_at']

    def validate_card_uid(self, value):
        taken = Passenger.objects.filter(card_uid=value).exclude(pk=getattr(self.instance, 'pk', None))
        if taken.exists():
            raise serializers.ValidationError('This card is already given to someone.')
        return value

    def validate_staff_number(self, value):
        value = value.strip()
        taken = Passenger.objects.filter(company=self.context['company'], staff_number=value)
        if taken.exclude(pk=getattr(self.instance, 'pk', None)).exists():
            raise serializers.ValidationError('Another employee already has this staff number.')
        return value

    def validate_phone(self, value):
        own_user = getattr(self.instance, 'user_id', None)
        if get_user_model().objects.filter(username=value).exclude(pk=own_user).exists():
            raise serializers.ValidationError('An account with this phone number already exists.')
        return value

    def update(self, instance, validated_data):
        blocked = validated_data.pop('card_blocked', None)
        new_card = validated_data.get('card_uid', instance.card_uid) != instance.card_uid
        if blocked is True:
            instance.card_blocked_at = instance.card_blocked_at or timezone.now()
        elif blocked is False or new_card:
            instance.card_blocked_at = None
        return super().update(instance, validated_data)

    def validate(self, data):
        method = data.get('payment_method', getattr(self.instance, 'payment_method', ''))
        account = data.get('payment_account', getattr(self.instance, 'payment_account', ''))
        if 'payment_method' in data or 'payment_account' in data:
            data['payment_account'] = validate_payment_account(method, account)
        return data


class PaymentMethodSerializer(serializers.Serializer):
    payment_method = serializers.ChoiceField(choices=Passenger.PaymentMethod.choices)
    payment_account = serializers.CharField(max_length=40)

    def validate(self, data):
        data['payment_account'] = validate_payment_account(data['payment_method'], data['payment_account'])
        return data


class TopUpSerializer(serializers.Serializer):
    amount = serializers.IntegerField(min_value=1)
