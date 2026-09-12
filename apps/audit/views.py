"""SRS 4.13 ('Audit record viewing for important changes'), 9 (GET
/api/audit-logs/). Admin-only, read-only per SRS 2/13."""
from rest_framework import generics
from apps.audit.models import AuditLog
from apps.audit.serializers import AuditLogSerializer
from apps.core.permissions import IsAdmin


class AuditLogListView(generics.ListAPIView):
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdmin]
    filterset_fields = ["entity", "action", "user"]
    search_fields = ["entity", "action"]
    ordering_fields = ["timestamp"]

    def get_queryset(self):
        return AuditLog.objects.all()
