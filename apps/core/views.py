from rest_framework import generics
from apps.core.models import StoreSettings
from apps.core.serializers import StoreSettingsSerializer
from apps.core.permissions import IsAdminOrReadOnly


class StoreSettingsView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/store-settings/  (SRS Section 9)."""
    serializer_class = StoreSettingsSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_object(self):
        return StoreSettings.load()
