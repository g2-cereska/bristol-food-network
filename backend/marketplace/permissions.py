from rest_framework.permissions import BasePermission


class IsAuthenticatedAndProducer(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and hasattr(request.user, 'producer_profile')
        )


class IsAuthenticatedAndCustomer(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and hasattr(request.user, 'customer_profile')
        )


class IsAdminUserOrStaff(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)
        )
