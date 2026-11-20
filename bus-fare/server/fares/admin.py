"""The platform's own back office (http://127.0.0.1:8000/admin/).

Here the platform creates: SACCOs it has agreements with, their routes and the
agreed fares, their vehicles (and the crew's logins), companies (and their admin's
login), and records company settlements.
Companies then register their own employees from the dashboard.
"""
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.utils import timezone

from .models import (
    Company, Passenger, Profile, Route, Sacco, Settlement, TerminalMessage, Transaction, Trip, Vehicle,
)
from .services import (
    change_fare, company_outstanding, deactivate_terminal, reactivate_terminal, vehicle_moved_sacco,
)


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


class TerminalStateFilter(admin.SimpleListFilter):
    title = 'terminal'
    parameter_name = 'terminal'

    def lookups(self, request, model_admin):
        return [('active', 'Active'), ('deactivated', 'Deactivated (lost or stolen)')]

    def queryset(self, request, queryset):
        if self.value() == 'active':
            return queryset.filter(terminal_deactivated_at__isnull=True)
        if self.value() == 'deactivated':
            return queryset.filter(terminal_deactivated_at__isnull=False)
        return queryset


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    """A lost or stolen terminal: tick the vehicle, then pick an action:
      * Deactivate terminal: its token is refused at once; the terminal locks itself.
      * Reactivate terminal: it was found; it works again and sends its offline payments.
      * Issue a new token: for a replacement terminal; the lost one never works again.
    A SACCO admin can also deactivate their own vehicles' terminals on the Fleet screen."""
    list_display = ('registration', 'name', 'sacco', 'terminal_state', 'last_seen_at')
    list_filter = ('sacco', TerminalStateFilter)
    readonly_fields = ('last_seen_at', 'terminal_deactivated_at')
    fields = ('registration', 'name', 'sacco', 'terminal_token', 'last_seen_at', 'terminal_deactivated_at')
    actions = ['deactivate_terminals', 'reactivate_terminals', 'issue_new_tokens']

    @admin.display(description='Terminal')
    def terminal_state(self, vehicle):
        if vehicle.terminal_active:
            return 'Active'
        return f'DEACTIVATED {timezone.localtime(vehicle.terminal_deactivated_at):%Y-%m-%d %H:%M}'

    @admin.action(description='Deactivate terminal (lost or stolen)')
    def deactivate_terminals(self, request, queryset):
        done = [v.registration for v in queryset if deactivate_terminal(v)]
        self.message_user(request, f'Deactivated: {", ".join(done)}.' if done else 'Already deactivated.',
                          messages.WARNING if done else messages.INFO)

    @admin.action(description='Reactivate terminal (it was found)')
    def reactivate_terminals(self, request, queryset):
        for vehicle in queryset:
            reactivate_terminal(vehicle)
        self.message_user(request, f'Reactivated: {", ".join(v.registration for v in queryset)}.')

    @admin.action(description='Issue a new token (replacement terminal) and reactivate')
    def issue_new_tokens(self, request, queryset):
        for vehicle in queryset:
            reactivate_terminal(vehicle, new_token=True)
            self.message_user(
                request, f'{vehicle.registration}: new token {vehicle.terminal_token} '
                         '(set it on the new terminal: "token <token>", or bridge.py --token). '
                         'The old token no longer works.', messages.WARNING)

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
