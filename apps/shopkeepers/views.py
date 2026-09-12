"""SRS 9 (Shopkeepers module), 4.7 / 6 (shopkeeper search).

One Shopkeeper record is created once and reused for every laptop they
take afterward (ShopkeeperLaptopItem = "Add another laptop", picked from
Inventory) and every extra-money entry / payment they make. A
SHOPKEEPER-role login (created by the admin) can only ever read their own
account -- see apps.core.permissions.IsAdminOrOwnShopkeeper.
"""
from decimal import Decimal

from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from apps.shopkeepers.models import Shopkeeper, ShopkeeperLaptopItem, ShopkeeperExtraMoney, ShopkeeperPayment
from apps.shopkeepers.serializers import (
    ShopkeeperSerializer, ShopkeeperLaptopItemSerializer, ShopkeeperExtraMoneySerializer, ShopkeeperPaymentSerializer,
)
from apps.inventory.models import InventoryMovement
from apps.core.permissions import IsAdminOrOwnShopkeeper
from apps.core.business_rules import BusinessRuleError, calculate_remaining
from apps.audit.utils import write_audit_log


class ShopkeeperViewSet(viewsets.ModelViewSet):
    serializer_class = ShopkeeperSerializer
    permission_classes = [IsAdminOrOwnShopkeeper]
    search_fields = ["name", "phone", "reference_number"]
    ordering_fields = ["name", "created_at"]

    def get_queryset(self):
        qs = Shopkeeper.objects.all().prefetch_related("laptops", "extra_money", "payments")
        user = self.request.user
        if user.role == "SHOPKEEPER":
            return qs.filter(id=user.shopkeeper_id)
        return qs

    def perform_create(self, serializer):
        obj = serializer.save()
        write_audit_log(self.request.user, "CREATE_SHOPKEEPER", "Shopkeeper", obj.id)

    def perform_update(self, serializer):
        obj = serializer.save()
        write_audit_log(self.request.user, "UPDATE_SHOPKEEPER", "Shopkeeper", obj.id)

    def perform_destroy(self, instance):
        # Deleting a shopkeeper cascades to their laptops, extra money and
        # payments too (models.py: all FKs are CASCADE) -- log before it's
        # gone so the audit trail still shows what was removed and by whom.
        shopkeeper_id = instance.id
        write_audit_log(
            self.request.user, "DELETE_SHOPKEEPER", "Shopkeeper", shopkeeper_id,
            {
                "name": instance.name, "reference_number": instance.reference_number,
                "laptops_removed": instance.laptops.count(),
                "extra_money_removed": instance.extra_money.count(),
                "payments_removed": instance.payments.count(),
            },
        )
        instance.delete()


class ShopkeeperLaptopItemViewSet(viewsets.ModelViewSet):
    """'Add another laptop' -- picked from Inventory, which reduces
    Inventory stock exactly like a sale. Creating a new laptop item here
    never creates a new Shopkeeper; it's always attached to the existing
    one via the `shopkeeper` field, keeping everything on one combined
    bill.

    Full CRUD: admin can also correct the shopkeeper-specific price on an
    already-added item (edit) or remove it entirely (delete, which
    restores the Inventory stock it was taken from) -- see
    apps.core.permissions.IsAdminOrOwnShopkeeper for why only ADMIN can
    ever reach a non-safe method here.
    """
    serializer_class = ShopkeeperLaptopItemSerializer
    permission_classes = [IsAdminOrOwnShopkeeper]
    filterset_fields = ["shopkeeper"]
    ordering_fields = ["added_at"]

    def get_queryset(self):
        qs = ShopkeeperLaptopItem.objects.select_related("shopkeeper", "inventory_laptop").all()
        user = self.request.user
        if user.role == "SHOPKEEPER":
            return qs.filter(shopkeeper_id=user.shopkeeper_id)
        return qs

    def perform_destroy(self, instance):
        # Removing a laptop shrinks the shopkeeper's combined total. If
        # payments already targeted this specific laptop, removing it
        # would orphan/invalidate those payment records -- refuse instead.
        if instance.targeted_payments.exists():
            raise ValidationError(
                "Cannot remove this laptop: it already has payment(s) recorded against it. "
                "Remove those payments first."
            )

        # Give the unit back to Inventory, same as reversing a sale.
        if instance.inventory_laptop_id:
            laptop = instance.inventory_laptop
            laptop.quantity += 1
            laptop.save(update_fields=["quantity"])
            InventoryMovement.objects.create(
                product=laptop, type=InventoryMovement.ADJUSTMENT, quantity=1,
                reference_id=instance.item_reference, created_by=self.request.user,
            )

        write_audit_log(
            self.request.user, "DELETE_SHOPKEEPER_LAPTOP", "Shopkeeper", instance.shopkeeper_id,
            {"item_reference": instance.item_reference, "price": str(instance.price)},
        )
        instance.delete()


class ShopkeeperExtraMoneyViewSet(viewsets.ModelViewSet):
    """Extra cash a shopkeeper takes on top of laptops -- its own
    separate receipt line, rolled into the shopkeeper's one combined
    bill total."""
    serializer_class = ShopkeeperExtraMoneySerializer
    permission_classes = [IsAdminOrOwnShopkeeper]
    filterset_fields = ["shopkeeper"]
    ordering_fields = ["added_at"]

    def get_queryset(self):
        qs = ShopkeeperExtraMoney.objects.select_related("shopkeeper").all()
        user = self.request.user
        if user.role == "SHOPKEEPER":
            return qs.filter(shopkeeper_id=user.shopkeeper_id)
        return qs

    def perform_destroy(self, instance):
        if instance.targeted_payments.exists():
            raise ValidationError(
                "Cannot remove this extra money entry: it already has payment(s) recorded against it. "
                "Remove those payments first."
            )
        write_audit_log(
            self.request.user, "DELETE_SHOPKEEPER_EXTRA_MONEY", "Shopkeeper", instance.shopkeeper_id,
            {"item_reference": instance.item_reference, "amount": str(instance.amount)},
        )
        instance.delete()


class ShopkeeperPaymentViewSet(viewsets.ModelViewSet):
    """Full CRUD: admin can correct a mis-entered payment amount (edit) or
    remove one entirely (delete). See ShopkeeperPaymentSerializer.update
    for how an edited amount is re-validated against its target's own
    balance."""
    serializer_class = ShopkeeperPaymentSerializer
    permission_classes = [IsAdminOrOwnShopkeeper]
    filterset_fields = ["shopkeeper", "method"]
    ordering_fields = ["payment_date"]

    def get_queryset(self):
        qs = ShopkeeperPayment.objects.select_related("shopkeeper", "laptop_item", "extra_money").all()
        user = self.request.user
        if user.role == "SHOPKEEPER":
            return qs.filter(shopkeeper_id=user.shopkeeper_id)
        return qs

    def perform_destroy(self, instance):
        write_audit_log(
            self.request.user, "DELETE_SHOPKEEPER_PAYMENT", "Shopkeeper", instance.shopkeeper_id,
            {"amount": str(instance.amount)},
        )
        instance.delete()
