from rest_framework import serializers
from apps.notifications.models import Notification, DeviceToken


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "type", "title", "message", "scheduled_at", "sent_at", "read_at", "created_at"]
        read_only_fields = fields


class DeviceTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceToken
        fields = ["id", "token", "platform", "created_at"]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):
        # Idempotent register: a device re-registering the same APNs token
        # simply updates ownership rather than erroring (SRS 4.11: 'must
        # not crash the app').
        token, _ = DeviceToken.objects.update_or_create(
            token=validated_data["token"],
            defaults={"user": self.context["request"].user, "platform": validated_data.get("platform", "ios")},
        )
        return token
