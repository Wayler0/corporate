from django.contrib import admin

from .models import Passenger, Route, TerminalMessage, Transaction, Trip


@admin.register(Passenger)
class PassengerAdmin(admin.ModelAdmin):
    list_display = ('name', 'card_uid', 'balance')
    search_fields = ('name', 'card_uid')


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ('name', 'fare')


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ('id', 'route', 'started_at', 'ended_at')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'card_uid', 'kind', 'result', 'amount', 'balance_after', 'trip')
    list_filter = ('kind', 'result')
    search_fields = ('card_uid',)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TerminalMessage)
class TerminalMessageAdmin(admin.ModelAdmin):
    list_display = ('line', 'created_at', 'delivered_at')
