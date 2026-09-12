from rest_framework import serializers
from apps.audit.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    user_display = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = ["id", "user", "user_display", "action", "entity", "entity_id", "detail", "timestamp"]

    def get_user_display(self, obj):
        return str(obj.user) if obj.user else "System"
