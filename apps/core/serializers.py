from rest_framework import serializers
from apps.core.models import StoreSettings


class StoreSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreSettings
        fields = [
            "id", "store_name", "address", "phone_number", "logo",
            "ceo_name", "ceo_contact_number",
            "thank_you_message", "low_stock_alerts_enabled",
            "due_today_reminder_enabled", "two_day_reminder_enabled",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
