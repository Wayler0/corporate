from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Passenger, Route, Transaction, Trip
from .serializers import (
    FareRequestSerializer, NewTripRequestSerializer, OperatorTapSerializer, PassengerSerializer, RouteSerializer,
    TapRequestSerializer, TapResponseSerializer, TopUpRequestSerializer, TransactionSerializer,
)
from .services import (
    AmountError, NoRouteError, UnknownCardError, change_fare, collect_terminal_lines,
    get_current_trip, normalize_card_uid, note_terminal_poll, process_tap, start_new_trip,
    terminal_status, top_up, trip_stats,
)

LIVE_TAPS = 30       # taps shown on the dashboard's live screen
TRIP_HISTORY = 10    # trips shown on the operator's trips screen
CARD_HISTORY = 20    # transactions shown on a card's page


def trip_summary(trip):
    return {'trip': trip.pk, 'route': trip.route_id, 'route_name': trip.route.name, 'fare': trip.route.fare}


class TapView(APIView):
    """POST /api/tap/  {"card_uid": "E5734107"}
    -> {"result": "PAID", "fare": 50, "balance": 450}
    The bridge turns that answer into the line  RES PAID 50 450  for the Uno."""

    def post(self, request):
        serializer = TapRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            decision = process_tap(serializer.validated_data['card_uid'])
        except NoRouteError as error:
            return Response({'detail': str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(TapResponseSerializer(decision).data)


class TopUpView(APIView):
    """POST /api/topup/  {"card_uid": "E5734107", "amount": 100}
    -> {"card_uid": "E5734107", "name": "White card", "balance": 600}"""

    def post(self, request):
        serializer = TopUpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            passenger = top_up(**serializer.validated_data)
        except UnknownCardError as error:
            return Response({'detail': str(error)}, status=status.HTTP_404_NOT_FOUND)
        except AmountError as error:
            return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'card_uid': passenger.card_uid, 'name': passenger.name, 'balance': passenger.balance})


class NewTripView(APIView):
    """POST /api/trip/  {}  or  {"route": 2}
    -> {"trip": 7, "route": 2, "route_name": "Marimanti-Chuka", "fare": 100}"""

    def post(self, request):
        serializer = NewTripRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            trip = start_new_trip(serializer.validated_data.get('route'))
        except NoRouteError as error:
            return Response({'detail': str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(trip_summary(trip), status=status.HTTP_201_CREATED)


class FareView(APIView):
    """POST /api/fare/  {"fare": 70}  or  {"fare": 70, "route": 2}
    -> {"id": 1, "name": "Campus shuttle", "fare": 70}"""

    def post(self, request):
        serializer = FareRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            route = change_fare(serializer.validated_data['fare'], serializer.validated_data.get('route'))
        except NoRouteError as error:
            return Response({'detail': str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except AmountError as error:
            return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(RouteSerializer(route).data)


class RouteListView(APIView):
    """GET /api/routes/ -> [{"id": 1, "name": "Campus shuttle", "fare": 50}, ...]"""

    def get(self, request):
        return Response(RouteSerializer(Route.objects.order_by('id'), many=True).data)


class StatusView(APIView):
    """GET /api/status/ -> the running trip, its route and fare.
    The bridge calls this when the Uno starts, to send it the right fare."""

    def get(self, request):
        try:
            return Response(trip_summary(get_current_trip()))
        except NoRouteError as error:
            return Response({'detail': str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class TerminalPollView(APIView):
    """POST /api/terminal/poll/ -> {"lines": ["MSG Top-up +100|Bal: KSh 600"]}
    The bridge calls this every 2 s and writes each line to the Uno.
    A line is handed over once only. A successful answer also tells the
    bridge the server is up, so it may keep sending LINK."""

    def post(self, request):
        note_terminal_poll()
        return Response({'lines': collect_terminal_lines()})


# ---------- Dashboard (read only) ----------
class LiveView(APIView):
    """GET /api/live/ -> everything the operator dashboard's Live screen shows, in
    one call (it polls every 2 s): the running trip, its totals, whether the
    terminal is linked, and the latest taps of this trip, newest first.
    Taps carry only the passenger's name and the amount: the crew does not see
    card IDs or balances."""

    def get(self, request):
        try:
            trip = get_current_trip()
        except NoRouteError as error:
            return Response({'detail': str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        taps = (Transaction.objects.filter(trip=trip, kind=Transaction.Kind.TAP)
                .select_related('passenger')[:LIVE_TAPS])
        return Response({
            'trip': {**trip_summary(trip), 'started_at': trip.started_at},
            'stats': trip_stats(trip),
            'terminal': terminal_status(),
            'taps': OperatorTapSerializer(taps, many=True).data,
        })


class TripListView(APIView):
    """GET /api/trips/ -> the latest trips (running one first) with their totals,
    and the totals for today across all trips."""

    def get(self, request):
        trips = Trip.objects.select_related('route').order_by('-id')[:TRIP_HISTORY]
        today = timezone.localdate()
        today_taps = Transaction.objects.filter(
            kind=Transaction.Kind.TAP, result=Transaction.Result.PAID, created_at__date=today)
        return Response({
            'today': {
                'collected': sum(today_taps.values_list('amount', flat=True)),
                'paid': today_taps.count(),
                'trips': Trip.objects.filter(started_at__date=today).count(),
            },
            'trips': [{
                **trip_summary(t),
                'started_at': t.started_at,
                'ended_at': t.ended_at,
                'stats': trip_stats(t),
            } for t in trips],
        })


class PassengerListView(APIView):
    """GET /api/passengers/ -> [{"card_uid": "E5734107", "name": "White card", "balance": 450}, ...]"""

    def get(self, request):
        return Response(PassengerSerializer(Passenger.objects.order_by('name'), many=True).data)


class PassengerDetailView(APIView):
    """GET /api/passengers/E5734107/ -> the card, whether it has paid on the
    running trip, and its latest transactions (taps and top-ups), newest first."""

    def get(self, request, card_uid):
        passenger = get_object_or_404(Passenger, card_uid=normalize_card_uid(card_uid))
        trip = Trip.objects.filter(ended_at__isnull=True).order_by('-id').first()
        paid = trip is not None and passenger.transactions.filter(
            trip=trip, result=Transaction.Result.PAID).exists()
        history = passenger.transactions.select_related('passenger')[:CARD_HISTORY]
        return Response({
            **PassengerSerializer(passenger).data,
            'paid_this_trip': paid,
            'transactions': TransactionSerializer(history, many=True).data,
        })
