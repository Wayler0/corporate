from rest_framework import serializers

from .models import Passenger, Route, Transaction
from .services import normalize_card_uid


class CardUidField(serializers.CharField):
    """Accepts 'e5 73 41 07' and hands the views 'E5734107'."""

    def __init__(self, **kwargs):
        super().__init__(max_length=40, **kwargs)

    def to_internal_value(self, data):
        uid = normalize_card_uid(super().to_internal_value(data))
        if not 8 <= len(uid) <= 20:
            raise serializers.ValidationError('Card ID must be 8 to 20 hex characters.')
        return uid


class TapRequestSerializer(serializers.Serializer):
    card_uid = CardUidField()


class TapResponseSerializer(serializers.Serializer):
    result = serializers.CharField()
    fare = serializers.IntegerField()
    balance = serializers.IntegerField()


class TopUpRequestSerializer(serializers.Serializer):
    card_uid = CardUidField()
    amount = serializers.IntegerField(min_value=1)


class NewTripRequestSerializer(serializers.Serializer):
    route = serializers.PrimaryKeyRelatedField(queryset=Route.objects.all(), required=False)


class FareRequestSerializer(serializers.Serializer):
    fare = serializers.IntegerField(min_value=1)
    route = serializers.PrimaryKeyRelatedField(queryset=Route.objects.all(), required=False)


class RouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Route
        fields = ['id', 'name', 'fare']


class TransactionSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='passenger.name', default=None)

    class Meta:
        model = Transaction
        fields = ['id', 'kind', 'result', 'card_uid', 'name', 'amount', 'balance_after', 'trip', 'created_at']


class PassengerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Passenger
        fields = ['card_uid', 'name', 'balance']
