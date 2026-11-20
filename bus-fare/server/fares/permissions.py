"""Who may call what.

* A vehicle's bridge sends   Authorization: Terminal <token>   (the vehicle's
  terminal_token). That identifies the vehicle; no person is logged in.
  A deactivated terminal (lost or stolen) is refused with 403 and
  {"code": "terminal_deactivated"}, so the terminal knows to lock itself.
* People log in through /api/auth/login/ and are known by their Profile role.
"""
from django.contrib.auth.models import AnonymousUser
from rest_framework import authentication, exceptions, permissions, status

from .models import Profile, Vehicle


class TerminalDeactivated(exceptions.APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = 'terminal_deactivated'

    def __init__(self):
        # A dict, so the code reaches the terminal in the body, not only the message
        super().__init__({'detail': 'This terminal has been deactivated. Contact the transport office.',
                          'code': self.default_code})


class TerminalAuthentication(authentication.BaseAuthentication):
    keyword = 'Terminal'

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode('latin-1').split()
        if not header or header[0] != self.keyword:
            return None
        if len(header) != 2:
            raise exceptions.AuthenticationFailed('Send: Authorization: Terminal <token>')
        vehicle = Vehicle.objects.filter(terminal_token=header[1]).first()
        if vehicle is None:
            raise exceptions.AuthenticationFailed('Unknown terminal token.')
        if not vehicle.terminal_active:
            raise TerminalDeactivated()
        return AnonymousUser(), vehicle

    def authenticate_header(self, request):
        return self.keyword


class IsTerminal(permissions.BasePermission):
    message = 'Only a vehicle terminal (bridge) may call this.'

    def has_permission(self, request, view):
        return isinstance(request.auth, Vehicle)


def profile_of(user):
    return getattr(user, 'profile', None) if user and user.is_authenticated else None


class HasRole(permissions.BasePermission):
    role = None
    message = 'Your account cannot open this page.'

    def has_permission(self, request, view):
        profile = profile_of(request.user)
        if profile is None or profile.role != self.role:
            return False
        if profile.must_change_password:
            self.message = 'Change your temporary password first.'
            return False
        return True


class IsOperator(HasRole):
    role = Profile.Role.OPERATOR

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.profile.vehicle_id is not None


class IsCompanyAdmin(HasRole):
    role = Profile.Role.COMPANY_ADMIN

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.profile.company_id is not None


class IsSaccoAdmin(HasRole):
    role = Profile.Role.SACCO_ADMIN

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.profile.sacco_id is not None


class IsEmployee(HasRole):
    role = Profile.Role.EMPLOYEE

    def has_permission(self, request, view):
        return super().has_permission(request, view) and hasattr(request.user, 'passenger')
