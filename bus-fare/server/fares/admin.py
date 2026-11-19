"""The platform's own back office (http://127.0.0.1:8000/admin/).

Here the platform creates: SACCOs it has agreements with, their routes and the
agreed fares, their vehicles (and the crew's logins), companies (and their admin's
login), and records company settlements.
Companies then register their own employees from the dashboard.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import (
    Company, Passenger, Profile, Route, Sacco, Settlement, TerminalMessage, Transaction, Trip, Vehicle,
)
from .services import change_fare, company_outstanding, vehicle_moved_sacco


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 1
    max_num = 1
    fields = ('role', 'vehicle', 'company', 'sacco', 'must_change_password')


admin.site.unregister(User)


@admin.register(User)
class UserWithProfileAdmin(UserAdmin):
    """Add a person's dashboard role on the user page: Operator + vehicle,
    Company admin + company, or SACCO admin + SACCO."""
    inlines = [ProfileInline]
    list_display = ('username', 'first_name', 'role', 'is_staff', 'is_active')

    @admin.display(description='Dashboard role')
    def role(self, user):
        profile = getattr(user, 'profile', None)
        return profile.get_role_display() if profile else '—'


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'billing', 'credit_limit', 'outstanding')

    @admin.display(description='Unpaid bill (KSh)')
    def outstanding(self, company):
        return company_outstanding(company) if company.company_pays else '—'


@admin.register(Settlement)
class SettlementAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'company', 'amount', 'reference')
    list_filter = ('company',)


@admin.register(Sacco)
class SaccoAdmin(admin.ModelAdmin):
    list_display = ('name', 'licence_number', 'vehicle_count', 'route_count')
    search_fields = ('name', 'licence_number')

    @admin.display(description='Vehicles')
    def vehicle_count(self, sacco):
        return sacco.vehicles.count()

    @admin.display(description='Routes')
    def route_count(self, sacco):
        return sacco.routes.count()


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('registration', 'name', 'sacco', 'last_seen_at')
    list_filter = ('sacco',)
    readonly_fields = ('last_seen_at',)
    fields = ('registration', 'name', 'sacco', 'terminal_token', 'last_seen_at')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change and 'sacco' in form.changed_data:
            vehicle_moved_sacco(obj)   # its running trip was on the old SACCO's fare


@admin.register(Passenger)
class PassengerAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'staff_number', 'card_uid', 'balance', 'active')
    list_filter = ('company', 'active')
    search_fields = ('name', 'card_uid', 'staff_number', 'phone')
    readonly_fields = ('user', 'created_at')


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ('name', 'sacco', 'fare')
    list_filter = ('sacco',)
    search_fields = ('name',)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)   # every edited field, not only the fare
        if change and 'fare' in form.changed_data:
            change_fare(obj, obj.fare)   # tells every vehicle running this route


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ('id', 'vehicle', 'route', 'started_at', 'ended_at')
    list_filter = ('vehicle',)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'card_uid', 'kind', 'result', 'amount', 'paid_by', 'balance_after', 'vehicle')
    list_filter = ('kind', 'result', 'paid_by', 'vehicle', 'company')
    search_fields = ('card_uid',)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TerminalMessage)
class TerminalMessageAdmin(admin.ModelAdmin):
    list_display = ('line', 'vehicle', 'created_at', 'delivered_at')
