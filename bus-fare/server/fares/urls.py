from django.urls import path

from . import views

urlpatterns = [
    path('health/', views.HealthView.as_view(), name='health'),

    # A vehicle's bridge (Authorization: Terminal <token>)
    path('tap/', views.TapView.as_view(), name='tap'),
    path('status/', views.StatusView.as_view(), name='status'),
    path('terminal/poll/', views.TerminalPollView.as_view(), name='terminal-poll'),
    path('terminal/cards/', views.TerminalCardsView.as_view(), name='terminal-cards'),
    path('terminal/sync/', views.TerminalSyncView.as_view(), name='terminal-sync'),

    # Logins
    path('auth/me/', views.MeView.as_view(), name='me'),
    path('auth/login/', views.LoginView.as_view(), name='login'),
    path('auth/logout/', views.LogoutView.as_view(), name='logout'),
    path('auth/password/', views.PasswordView.as_view(), name='password'),

    # Bus crew: their own vehicle
    path('operator/live/', views.OperatorLiveView.as_view(), name='operator-live'),
    path('operator/trips/', views.OperatorTripsView.as_view(), name='operator-trips'),
    path('operator/trip/', views.OperatorNewTripView.as_view(), name='operator-new-trip'),
    path('operator/reserved/', views.OperatorReservedView.as_view(), name='operator-reserved'),
    path('routes/', views.RouteListView.as_view(), name='routes'),

    # SACCO admin: their own SACCO's vehicles and routes
    path('sacco/', views.SaccoOverviewView.as_view(), name='sacco'),
    path('sacco/vehicles/', views.SaccoFleetView.as_view(), name='sacco-vehicles'),
    path('sacco/vehicles/<int:pk>/reserved/', views.SaccoReservedView.as_view(), name='sacco-reserved'),
    path('sacco/vehicles/<int:pk>/deactivate-terminal/', views.SaccoTerminalDeactivateView.as_view(),
         name='sacco-deactivate-terminal'),
    path('sacco/vehicles/<int:pk>/reactivate-terminal/', views.SaccoTerminalReactivateView.as_view(),
         name='sacco-reactivate-terminal'),

    # Company admin: their own company
    path('company/', views.CompanyOverviewView.as_view(), name='company'),
    path('company/employees/', views.EmployeeListView.as_view(), name='employees'),
    path('company/employees/<int:pk>/', views.EmployeeDetailView.as_view(), name='employee'),
    path('company/employees/<int:pk>/reset-password/', views.EmployeeResetPasswordView.as_view(),
         name='employee-reset-password'),

    # Employee: their own account
    path('me/', views.MyAccountView.as_view(), name='my-account'),
    path('me/topup/', views.MyTopUpView.as_view(), name='my-topup'),
    path('me/card/block/', views.MyCardBlockView.as_view(), name='my-card-block'),
    path('me/payment-method/', views.MyPaymentMethodView.as_view(), name='my-payment-method'),
]
