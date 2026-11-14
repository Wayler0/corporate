from django.urls import path

from . import views

urlpatterns = [
    path('tap/', views.TapView.as_view(), name='tap'),
    path('topup/', views.TopUpView.as_view(), name='topup'),
    path('trip/', views.NewTripView.as_view(), name='trip'),
    path('fare/', views.FareView.as_view(), name='fare'),
    path('routes/', views.RouteListView.as_view(), name='routes'),
    path('status/', views.StatusView.as_view(), name='status'),
    path('terminal/poll/', views.TerminalPollView.as_view(), name='terminal-poll'),
    path('live/', views.LiveView.as_view(), name='live'),
    path('passengers/', views.PassengerListView.as_view(), name='passengers'),
    path('passengers/<str:card_uid>/', views.PassengerDetailView.as_view(), name='passenger'),
]
