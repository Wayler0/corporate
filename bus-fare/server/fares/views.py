"""API endpoints, grouped by who calls them:

  terminal       a vehicle's bridge (Authorization: Terminal <token>)
  auth           anyone: log in, log out, who am I, change password
  operator       bus crew: their own vehicle only
  company        a company admin: their own company only
  me             an employee: their own account only
"""
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.http import HttpResponse
from django.db import transaction as db_transaction
from django.db.models import Min, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Passenger, Profile, Route, Transaction, Trip
from .permissions import IsCompanyAdmin, IsEmployee, IsOperator, IsTerminal, TerminalAuthentication
from .serializers import (
    AccountTransactionSerializer, EmployeeSerializer, LoginSerializer, NewTripRequestSerializer,
    OfflineSyncSerializer,
    OperatorTapSerializer, PasswordChangeSerializer, PaymentMethodSerializer, RouteSerializer,
    TapRequestSerializer, TapResponseSerializer, TopUpSerializer,
)
from .services import (
    AmountError, NoRouteError, NotAllowedError, collect_terminal_lines, company_outstanding,
    block_card, create_employee, get_current_trip, process_tap, reset_password, settlements_total,
    start_new_trip, sync_offline, tap_totals, terminal_cards, terminal_status, top_up, trip_stats,
)

LIVE_TAPS = 30       # taps on the operator's live screen
TRIP_HISTORY = 10    # trips on the operator's trips screen
HISTORY = 30         # lines on an employee's statement


def trip_summary(trip):
    return {'trip': trip.pk, 'route': trip.route_id, 'route_name': trip.route.name, 'fare': trip.route.fare}


def no_route(error):
    return Response({'detail': str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


def month_start():
    return timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def statement(passenger):
    return (passenger.transactions.select_related('trip__route', 'vehicle', 'passenger')[:HISTORY])


# =====================================================================
# Terminal (the vehicle's bridge)
# =====================================================================
class TerminalView(APIView):
    authentication_classes = [TerminalAuthentication]
    permission_classes = [IsTerminal]


class TapView(TerminalView):
    """POST /api/tap/  {"card_uid": "E5734107"}
    -> {"result": "PAID", "fare": 50, "balance": 450}
    The bridge turns that answer into the line  RES PAID 50 450  for the Uno.
    When the company pays, "balance" is the card's own (unchanged) balance."""

    def post(self, request):
        serializer = TapRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            decision = process_tap(request.auth, serializer.validated_data['card_uid'])
        except NoRouteError as error:
            return no_route(error)
        return Response(TapResponseSerializer(decision).data)


class StatusView(TerminalView):
    """GET /api/status/ -> this vehicle's running trip, its route and fare.
    The bridge calls this when the Uno starts, to send it the right fare."""

    def get(self, request):
        try:
            return Response(trip_summary(get_current_trip(request.auth)))
        except NoRouteError as error:
            return no_route(error)


class TerminalPollView(TerminalView):
    """POST /api/terminal/poll/ -> {"lines": ["FARE 70", "trip"]}
    The bridge calls this every 2 s and writes each line to the Uno. A line is
    handed over once only. Polling is also how the vehicle shows as online."""

    def post(self, request):
        return Response({'lines': collect_terminal_lines(request.auth)})


class TerminalCardsView(TerminalView):
    """GET /api/terminal/cards/ -> plain text: the running trip and every active
    card, so the terminal can decide taps by itself when offline. Format in
    services.terminal_cards."""

    def get(self, request):
        try:
            text = terminal_cards(request.auth)
        except NoRouteError as error:
            return no_route(error)
        return HttpResponse(text, content_type='text/plain; charset=utf-8')


class TerminalSyncView(TerminalView):
    """POST /api/terminal/sync/
    {"terminal": "3F2A9C01", "trip": 12, "trips_started": 1,
     "taps": [{"ref": 7, "card_uid": "E5734107", "fare": 50, "trip": 12, "offset": 1, "seconds_ago": 300}]}
    -> {"trip": 14, "fare": 50}   (the running trip after the sync)
    Payments the terminal took offline. Sending the same taps again is harmless."""

    def post(self, request):
        serializer = OfflineSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            trip = sync_offline(request.auth, data['terminal'].upper(), data['trip'], data['trips_started'],
                                data['taps'])
        except NoRouteError as error:
            return no_route(error)
        return Response({'trip': trip.pk, 'fare': trip.route.fare})


# =====================================================================
# Logins
# =====================================================================
def describe(user):
    """What the dashboard needs to know about the person logged in."""
    profile = getattr(user, 'profile', None)
    if profile is None:
        return None
    data = {
        'username': user.username,
        'name': user.get_full_name() or user.username,
        'role': profile.role,
        'must_change_password': profile.must_change_password,
    }
    if profile.vehicle:
        data['vehicle'] = {'id': profile.vehicle_id, 'registration': profile.vehicle.registration,
                           'name': profile.vehicle.name}
    if profile.company:
        data['company'] = {'id': profile.company_id, 'name': profile.company.name,
                           'billing': profile.company.billing}
    return data


@method_decorator(ensure_csrf_cookie, name='dispatch')
class MeView(APIView):
    """GET /api/auth/me/ -> {"user": {...}} or {"user": null}. Also hands the
    browser its CSRF cookie, which every later POST must echo back."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({'user': describe(request.user) if request.user.is_authenticated else None})


class LoginView(APIView):
    """POST /api/auth/login/ {"username": "0712345678", "password": "..."}"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request, **serializer.validated_data)
        if user is None or describe(user) is None:
            return Response({'detail': 'Wrong phone number / username or password.'},
                            status=status.HTTP_400_BAD_REQUEST)
        login(request, user)
        return Response({'user': describe(user)})


class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        logout(request)
        return Response({'user': None})


class PasswordView(APIView):
    """POST /api/auth/password/ {"old_password": "...", "new_password": "..."}"""

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={'user': request.user})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save(update_fields=['password'])
        update_session_auth_hash(request, request.user)   # stay logged in
        Profile.objects.filter(user=request.user).update(must_change_password=False)
        request.user.refresh_from_db()
        return Response({'user': describe(request.user)})


# =====================================================================
# Operator: their own vehicle only
# =====================================================================
class OperatorView(APIView):
    permission_classes = [IsOperator]

    @property
    def vehicle(self):
        return self.request.user.profile.vehicle


class OperatorLiveView(OperatorView):
    """GET /api/operator/live/ -> this vehicle's running trip, its totals, whether
    its terminal is linked, and the latest taps (name and amount only)."""

    def get(self, request):
        try:
            trip = get_current_trip(self.vehicle)
        except NoRouteError as error:
            return no_route(error)
        taps = (Transaction.objects.filter(trip=trip, kind=Transaction.Kind.TAP)
                .select_related('passenger')[:LIVE_TAPS])
        return Response({
            'trip': {**trip_summary(trip), 'started_at': trip.started_at},
            'stats': trip_stats(trip),
            'terminal': terminal_status(self.vehicle),
            'taps': OperatorTapSerializer(taps, many=True).data,
        })


class OperatorTripsView(OperatorView):
    """GET /api/operator/trips/ -> this vehicle's latest trips with their totals, and today's totals."""

    def get(self, request):
        vehicle = self.vehicle
        trips = Trip.objects.filter(vehicle=vehicle).select_related('route').order_by('-id')[:TRIP_HISTORY]
        today = timezone.localdate()
        totals = tap_totals(Transaction.objects.filter(
            vehicle=vehicle, kind=Transaction.Kind.TAP, created_at__date=today))
        return Response({
            'today': {'collected': totals['collected'], 'paid': totals['paid'],
                      'trips': Trip.objects.filter(vehicle=vehicle, started_at__date=today).count()},
            'trips': [{**trip_summary(t), 'started_at': t.started_at, 'ended_at': t.ended_at,
                       'stats': trip_stats(t)} for t in trips],
        })


class OperatorNewTripView(OperatorView):
    """POST /api/operator/trip/ {} or {"route": 2} -> the new trip."""

    def post(self, request):
        serializer = NewTripRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            trip = start_new_trip(self.vehicle, serializer.validated_data.get('route'))
        except NoRouteError as error:
            return no_route(error)
        return Response(trip_summary(trip), status=status.HTTP_201_CREATED)


class RouteListView(APIView):
    """GET /api/routes/ -> [{"id": 1, "name": "Campus shuttle", "fare": 50}, ...]
    Fares are set by the platform in the Django admin."""

    def get(self, request):
        return Response(RouteSerializer(Route.objects.order_by('id'), many=True).data)


# =====================================================================
# Company admin: their own company only
# =====================================================================
class CompanyView(APIView):
    permission_classes = [IsCompanyAdmin]

    @property
    def company(self):
        return self.request.user.profile.company

    def employee(self, pk):
        return get_object_or_404(Passenger.objects.select_related('user'), pk=pk, company=self.company)


class CompanyOverviewView(CompanyView):
    """GET /api/company/ -> the company, its billing, this month's travel and
    (company pays) what it owes."""

    def get(self, request):
        company = self.company
        month_taps = Transaction.objects.filter(
            passenger__company=company, kind=Transaction.Kind.TAP, created_at__gte=month_start())
        totals = tap_totals(month_taps)
        employees = company.employees
        data = {
            'name': company.name,
            'billing': company.billing,
            'billing_label': company.get_billing_display(),
            'employees': employees.count(),
            'active_employees': employees.filter(active=True).count(),
            'month': {'spent': totals['collected'], 'trips': totals['paid'], 'declined': totals['refused']},
            'recent': AccountTransactionSerializer(
                month_taps.select_related('trip__route', 'vehicle', 'passenger')[:10], many=True).data,
        }
        if company.company_pays:
            data['bill'] = {
                'outstanding': company_outstanding(company),
                'credit_limit': company.credit_limit,
                'settled_total': settlements_total(company),
                'settlements': [{'amount': s.amount, 'reference': s.reference, 'created_at': s.created_at}
                                for s in company.settlements.all()[:5]],
            }
        else:
            # Employees who cannot afford even the cheapest route
            cheapest = Route.objects.aggregate(fare=Min('fare'))['fare'] or 0
            data['low_balance'] = employees.filter(active=True, balance__lt=cheapest).count()
        return Response(data)


class EmployeeListView(CompanyView):
    """GET /api/company/employees/?q=...   list (search by name, staff number, phone, department)
    POST /api/company/employees/           register one; answers with a temporary password"""

    def get(self, request):
        employees = self.company.employees.order_by('name')
        q = request.query_params.get('q', '').strip()
        if q:
            employees = employees.filter(
                Q(name__icontains=q) | Q(staff_number__icontains=q) | Q(phone__icontains=q.lstrip('0'))
                | Q(department__icontains=q))
        return Response(EmployeeSerializer(employees, many=True, context={'company': self.company}).data)

    def post(self, request):
        serializer = EmployeeSerializer(data=request.data, context={'company': self.company})
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop('active', None)
        data.pop('card_blocked', None)
        try:
            passenger, password = create_employee(self.company, **data)
        except NotAllowedError as error:
            return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({**EmployeeSerializer(passenger, context={'company': self.company}).data,
                         'temporary_password': password}, status=status.HTTP_201_CREATED)


class EmployeeDetailView(CompanyView):
    """GET   /api/company/employees/<id>/  the employee and their statement
    PATCH /api/company/employees/<id>/  change details, card, payment method, or deactivate"""

    def get(self, request, pk):
        passenger = self.employee(pk)
        return Response({**EmployeeSerializer(passenger, context={'company': self.company}).data,
                         'transactions': AccountTransactionSerializer(statement(passenger), many=True).data})

    @db_transaction.atomic
    def patch(self, request, pk):
        passenger = self.employee(pk)
        serializer = EmployeeSerializer(passenger, data=request.data, partial=True, context={'company': self.company})
        serializer.is_valid(raise_exception=True)
        passenger = serializer.save()
        user = passenger.user
        if user is not None:
            # The login follows the employee's phone and name, and stops when deactivated
            user.username, user.first_name, user.is_active = passenger.phone, passenger.name[:150], passenger.active
            user.save(update_fields=['username', 'first_name', 'is_active'])
        return Response(EmployeeSerializer(passenger, context={'company': self.company}).data)


class EmployeeResetPasswordView(CompanyView):
    """POST /api/company/employees/<id>/reset-password/ -> {"temporary_password": "..."}"""

    def post(self, request, pk):
        passenger = self.employee(pk)
        if passenger.user is None:
            return Response({'detail': 'This employee has no login.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'temporary_password': reset_password(passenger.user)})


# =====================================================================
# Employee: their own account only
# =====================================================================
class EmployeeView(APIView):
    permission_classes = [IsEmployee]

    @property
    def passenger(self):
        return self.request.user.passenger


def account(passenger):
    company = passenger.company
    month = passenger.transactions.filter(
        kind=Transaction.Kind.TAP, result=Transaction.Result.PAID, created_at__gte=month_start())
    return {
        'name': passenger.name,
        'staff_number': passenger.staff_number,
        'phone': passenger.phone,
        'department': passenger.department,
        'card_uid': passenger.card_uid,
        'active': passenger.active,
        'card_blocked_at': passenger.card_blocked_at,
        'balance': passenger.balance,
        'company': company.name if company else None,
        'company_pays': bool(company and company.company_pays),
        'payment_method': passenger.payment_method,
        'payment_account': passenger.payment_account,
        'month': {'spent': sum(month.values_list('amount', flat=True)), 'trips': month.count()},
        'transactions': AccountTransactionSerializer(statement(passenger), many=True).data,
    }


class MyAccountView(EmployeeView):
    """GET /api/me/ -> balance, card, company billing, payment method and statement."""

    def get(self, request):
        return Response(account(self.passenger))


class MyTopUpView(EmployeeView):
    """POST /api/me/topup/ {"amount": 200} -> the account.
    DEMO: no payment provider is connected yet, so the payment always succeeds."""

    def post(self, request):
        serializer = TopUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        passenger = self.passenger
        try:
            passenger = top_up(passenger, serializer.validated_data['amount'], passenger.payment_method)
        except (AmountError, NotAllowedError) as error:
            return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(account(passenger))


class MyCardBlockView(EmployeeView):
    """POST /api/me/card/block/ -> the account. Lost or stolen card: it is declined
    on every vehicle from now on. The login keeps working. Only the company admin
    can unblock it or give a new card (the card may have been copied meanwhile)."""

    def post(self, request):
        passenger = self.passenger
        block_card(passenger)
        return Response(account(passenger))


class MyPaymentMethodView(EmployeeView):
    """PUT /api/me/payment-method/ {"payment_method": "MPESA", "payment_account": "0712345678"}"""

    def put(self, request):
        serializer = PaymentMethodSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        passenger = self.passenger
        passenger.payment_method = serializer.validated_data['payment_method']
        passenger.payment_account = serializer.validated_data['payment_account']
        passenger.save(update_fields=['payment_method', 'payment_account'])
        return Response(account(passenger))
