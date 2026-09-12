"""SRS 4.4, 6.2, 9 (Inventory module), 4.13 (low-stock report)."""
from rest_framework import viewsets, generics
from django_filters import rest_framework as django_filters

from apps.inventory.models import Laptop, InventoryMovement
from apps.inventory.serializers import LaptopSerializer, InventoryMovementSerializer
from apps.core.permissions import IsAdminOrReadOnly
from apps.audit.utils import write_audit_log


class LaptopFilter(django_filters.FilterSet):
    in_stock = django_filters.BooleanFilter(method="filter_in_stock")
    low_stock = django_filters.BooleanFilter(method="filter_low_stock")

    class Meta:
        model = Laptop
        fields = ["condition", "brand", "is_archived"]

    def filter_in_stock(self, qs, name, value):
        return qs.filter(quantity__gt=0) if value else qs.filter(quantity=0)

    def filter_low_stock(self, qs, name, value):
        from django.conf import settings
        return qs.filter(quantity__lt=settings.LOW_STOCK_THRESHOLD, quantity__gt=0) if value else qs


class LaptopViewSet(viewsets.ModelViewSet):
    """SRS 4.4: searchable inventory list; SRS 6.2: spec search fields."""
    queryset = Laptop.objects.all()
    serializer_class = LaptopSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_class = LaptopFilter
    search_fields = [
        "brand", "model_name", "generation", "processor", "serial_number",
        "condition", "gpu", "screen_size",
    ]
    ordering_fields = ["brand", "model_name", "quantity", "sale_price", "created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("include_archived") != "true":
            qs = qs.filter(is_archived=False)
        return qs

    def perform_create(self, serializer):
        laptop = serializer.save()
        from apps.inventory.models import InventoryMovement
        InventoryMovement.objects.create(
            product=laptop, type=InventoryMovement.STOCK_IN, quantity=laptop.quantity,
            created_by=self.request.user,
        )
        write_audit_log(self.request.user, "CREATE_LAPTOP", "Laptop", laptop.id)

    def perform_update(self, serializer):
        laptop = serializer.save()
        write_audit_log(self.request.user, "UPDATE_LAPTOP", "Laptop", laptop.id)

    def perform_destroy(self, instance):
        # SRS 4.4: archive rather than permanently delete financial history
        instance.is_archived = True
        instance.save(update_fields=["is_archived"])
        from apps.inventory.models import InventoryMovement
        InventoryMovement.objects.create(
            product=instance, type=InventoryMovement.ARCHIVE, quantity=0, created_by=self.request.user,
        )
        write_audit_log(self.request.user, "ARCHIVE_LAPTOP", "Laptop", instance.id)


class InventoryMovementListView(generics.ListAPIView):
    serializer_class = InventoryMovementSerializer
    permission_classes = [IsAdminOrReadOnly]
    queryset = InventoryMovement.objects.all()
    filterset_fields = ["product", "type"]
