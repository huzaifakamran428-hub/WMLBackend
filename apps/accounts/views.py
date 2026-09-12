"""SRS 9: Users module (GET/POST/PATCH /api/users/), SRS 4.1 admin-only
create/activate/deactivate."""
from django.contrib.auth import get_user_model
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsAdmin
from apps.accounts.serializers import UserSerializer, CreateUserSerializer
from apps.audit.utils import write_audit_log

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("-date_joined")
    permission_classes = [IsAdmin]  # SRS 2: only Admin manages users

    def get_serializer_class(self):
        if self.action == "create":
            return CreateUserSerializer
        return UserSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        write_audit_log(self.request.user, "CREATE_USER", "User", user.id)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """SRS 4.1: 'Admin can activate/deactivate users.'"""
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=["is_active"])
        write_audit_log(request.user, "DEACTIVATE_USER", "User", user.id)
        return Response(UserSerializer(user).data)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=["is_active"])
        write_audit_log(request.user, "ACTIVATE_USER", "User", user.id)
        return Response(UserSerializer(user).data)
