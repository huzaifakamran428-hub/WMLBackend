"""
SRS Section 2 (User Types and Access Control) + Section 13 (Security):
'Role-based access control must be enforced by the Django backend. Swift
UI restrictions are only a usability layer and must never be treated as
the security boundary.'
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdmin(BasePermission):
    """Full access role (SRS 2)."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == "ADMIN")


class IsAdminOrReadOnly(BasePermission):
    """SRS 2: Read-Only User can 'Login and view permitted records/reports
    only. Cannot add, edit, delete, sell, receive payments or change
    system data.' Admin has full access."""
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.role == "ADMIN":
            return True
        return request.method in SAFE_METHODS


class IsActiveUser(BasePermission):
    """SRS 4.1: 'Admin can activate/deactivate users.' Deactivated users
    must be denied even with a still-valid token."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_active)


class IsAdminOrOwnShopkeeper(BasePermission):
    """Admin has full access. A SHOPKEEPER-role user (a login the admin
    created for a specific shopkeeper) can only READ -- and only their own
    shopkeeper account: their own laptops, payments and running balance.
    They can never create/edit/delete, and can never see another
    shopkeeper's account."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.role == "ADMIN":
            return True
        if user.role == "SHOPKEEPER":
            return request.method in SAFE_METHODS and user.shopkeeper_id is not None
        return request.method in SAFE_METHODS

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.role == "ADMIN":
            return True
        if user.role != "SHOPKEEPER" or request.method not in SAFE_METHODS:
            return False
        shopkeeper_id = getattr(obj, "shopkeeper_id", getattr(obj, "id", None))
        return shopkeeper_id == user.shopkeeper_id
