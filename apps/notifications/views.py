"""SRS 9 (Notifications / device-tokens modules), 4.2, 4.11."""
from rest_framework import generics, viewsets
from django.utils import timezone

from apps.notifications.models import Notification, DeviceToken
from apps.notifications.serializers import NotificationSerializer, DeviceTokenSerializer
from apps.core.permissions import IsAdminOrReadOnly


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_fields = ["type"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class MarkNotificationReadView(generics.UpdateAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    def patch(self, request, *args, **kwargs):
        notif = self.get_object()
        notif.read_at = timezone.now()
        notif.save(update_fields=["read_at"])
        return self.retrieve(request, *args, **kwargs)


class DeviceTokenViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "delete", "head", "options"]
    serializer_class = DeviceTokenSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        return DeviceToken.objects.filter(user=self.request.user)
