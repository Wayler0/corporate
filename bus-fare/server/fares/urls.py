from django.urls import path

from . import views

urlpatterns = [
    # A vehicle's bridge (Authorization: Terminal <token>)
    path('tap/', views.TapView.as_view(), name='tap'),
    path('status/', views.StatusView.as_view(), name='status'),
    path('terminal/poll/', views.TerminalPollView.as_view(), name='terminal-poll'),

    # Logins
    path('auth/me/', views.MeView.as_view(), name='me'),
    path('auth/login/', views.LoginView.as_view(), name='login'),
    path('auth/logout/', views.LogoutView.as_view(), name='logout'),
    path('auth/password/', views.PasswordView.as_view(), name='password'),

    # Bus crew: their own vehicle
    path('operator/live/', views.OperatorLiveView.as_view(), name='operator-live'),
    path('operator/trips/', views.OperatorTripsView.as_view(), name='operator-trips'),
    path('operator/trip/', views.OperatorNewTripView.as_view(), name='operator-new-trip'),
    path('routes/', views.RouteListView.as_view(), name='routes'),

    # Company admin: their own company
    path('company/', views.CompanyOverviewView.as_view(), name='company'),
    path('company/employees/', views.EmployeeListView.as_view(), name='employees'),
    path('company/employees/<int:pk>/', views.EmployeeDetailView.as_view(), name='employee'),
    path('company/employees/<int:pk>/reset-password/', views.EmployeeResetPasswordView.as_view(),
         name='employee-reset-password'),

    # Employee: their own account
    path('me/', views.MyAccountView.as_view(), name='my-account'),
    path('me/topup/', views.MyTopUpView.as_view(), name='my-topup'),
    path('me/payment-method/', views.MyPaymentMethodView.as_view(), name='my-payment-method'),
]
