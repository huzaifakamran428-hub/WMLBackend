"""SRS 9 (Sales module), 6.1/6.3 (customer sale & receipt search), 8.2."""
from django.db import transaction
from rest_framework import viewsets, generics
from rest_framework.response import Response
from django_filters import rest_framework as django_filters

from apps.sales.models import Sale
from apps.sales.serializers import SaleSerializer
from apps.inventory.models import Laptop, InventoryMovement
from apps.core.permissions import IsAdminOrReadOnly
from apps.audit.utils import write_audit_log


class SaleFilter(django_filters.FilterSet):
    class Meta:
        model = Sale
        fields = ["payment_status", "payment_type", "customer"]


class SaleViewSet(viewsets.ModelViewSet):
    """Sales support full CRUD (SRS 11: admin can correct or remove a
    mis-entered bill after the fact) -- see SaleSerializer.update for how
    an edit reconciles quantity/stock, and perform_destroy below for how a
    delete reverses the sale's effect on inventory. Only ADMIN can reach
    any of the non-safe methods (IsAdminOrReadOnly); Read-Only stays
    view-only, unchanged."""
    queryset = Sale.objects.select_related("customer").prefetch_related("items")
    serializer_class = SaleSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_class = SaleFilter
    search_fields = [
        "customer__name", "customer__phone", "receipt_no",
        "items__product__brand", "items__product__model_name", "items__product__generation",
    ]
    ordering_fields = ["sale_date", "final_total"]

@transaction.atomic
def perform_destroy(self, instance):
    request = self.request

    # Restore inventory for every item belonging to this sale.
    for item in instance.items.select_related("product").all():
        laptop = Laptop.objects.select_for_update().get(pk=item.product_id)

        laptop.quantity += item.quantity
        laptop.save(update_fields=["quantity"])

        InventoryMovement.objects.create(
            product=laptop,
            type=InventoryMovement.ADJUSTMENT,
            quantity=item.quantity,
            reference_id=f"{instance.receipt_no}-deleted",
            created_by=request.user,
        )

    write_audit_log(
        request.user,
        "DELETE_SALE",
        "Sale",
        instance.id,
        {
            "receipt_no": instance.receipt_no,
            "final_total": str(instance.final_total),
        },
    )

    instance.delete()


class ReceiptSearchView(generics.RetrieveAPIView):
    """SRS 6.3: 'searching 00025 directly finds Receipt No. 00025' with the
    full result payload (person, phone, laptop specs, pricing, payment
    history, status)."""
    serializer_class = SaleSerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = "receipt_no"
    queryset = Sale.objects.select_related("customer").prefetch_related("items")
