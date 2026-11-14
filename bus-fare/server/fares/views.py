from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Route
from .serializers import (
    FareRequestSerializer, NewTripRequestSerializer, RouteSerializer,
    TapRequestSerializer, TapResponseSerializer, TopUpRequestSerializer,
)
from .services import (
    AmountError, NoRouteError, UnknownCardError, change_fare, collect_terminal_lines,
    get_current_trip, process_tap, start_new_trip, top_up,
)


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
        return Response({'lines': collect_terminal_lines()})
