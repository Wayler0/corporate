"""The platform's own back office (http://127.0.0.1:8000/admin/).

Here the platform creates: companies (and their admin's login), vehicles (and
the crew's logins), routes and fares, and records company settlements.
Companies then register their own employees from the dashboard.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import Company, Passenger, Profile, Route, Settlement, TerminalMessage, Transaction, Trip, Vehicle
from .services import change_fare, company_outstanding


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 1
    max_num = 1
    fields = ('role', 'vehicle', 'company', 'must_change_password')


admin.site.unregister(User)


@admin.register(User)
class UserWithProfileAdmin(UserAdmin):
    """Add a person's dashboard role on the user page: Operator + vehicle,
    or Company admin + company."""
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


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('registration', 'name', 'last_seen_at')
    readonly_fields = ('last_seen_at',)
    fields = ('registration', 'name', 'terminal_token', 'last_seen_at')


@admin.register(Passenger)
class PassengerAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'staff_number', 'card_uid', 'balance', 'active')
    list_filter = ('company', 'active')
    search_fields = ('name', 'card_uid', 'staff_number', 'phone')
    readonly_fields = ('user', 'created_at')


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ('name', 'fare')

    def save_model(self, request, obj, form, change):
        if change and 'fare' in form.changed_data:
            change_fare(obj, obj.fare)   # also tells every vehicle running this route
        else:
            super().save_model(request, obj, form, change)


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
