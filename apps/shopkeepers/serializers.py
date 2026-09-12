from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.shopkeepers.models import (
    Shopkeeper, ShopkeeperLaptopItem, ShopkeeperExtraMoney, ShopkeeperPayment,
)
from apps.inventory.models import Laptop, InventoryMovement
from apps.core.business_rules import (
    calculate_remaining, validate_new_payment, apply_sale_to_stock, BusinessRuleError,
)
from apps.audit.utils import write_audit_log


class ShopkeeperLaptopItemSerializer(serializers.ModelSerializer):
    """'Add another laptop' -- picked from Inventory. On create, only
    `inventory_laptop` (the Inventory item's id) and `price` (the rate
    given to this shopkeeper) are accepted; every spec field is copied
    from the Inventory item and returned read-only. On update, only
    `price` may change -- specs stay fixed once added."""

    item_reference = serializers.CharField(read_only=True)
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    remaining_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_cleared = serializers.BooleanField(read_only=True)
    inventory_laptop = serializers.PrimaryKeyRelatedField(
        queryset=Laptop.objects.all(), write_only=True, required=False
    )

    class Meta:
        model = ShopkeeperLaptopItem
        fields = [
            "id", "shopkeeper", "item_reference", "inventory_laptop", "brand", "model_name",
            "core_generation", "ram", "storage", "condition", "notes",
            "price", "added_at", "paid_amount", "remaining_amount", "is_cleared",
        ]
        read_only_fields = [
            "id", "item_reference", "added_at", "brand", "model_name",
            "core_generation", "ram", "storage", "condition", "notes",
        ]

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        inventory_laptop = validated_data.pop("inventory_laptop", None)
        if inventory_laptop is None:
            raise serializers.ValidationError({"inventory_laptop": "Select a laptop from Inventory."})

        # Lock the row so two admins can't both hand out the last unit at
        # the same time (same pattern as apps.sales.serializers).
        inventory_laptop = Laptop.objects.select_for_update().get(pk=inventory_laptop.pk)
        try:
            new_quantity = apply_sale_to_stock(inventory_laptop.quantity, 1)
        except BusinessRuleError as exc:
            raise serializers.ValidationError({"inventory_laptop": str(exc)})

        # Copy specs from Inventory at this moment -- fixed afterward even
        # if the Inventory item is later edited, archived, or deleted.
        item = ShopkeeperLaptopItem.objects.create(
            created_by=request.user,
            inventory_laptop=inventory_laptop,
            brand=inventory_laptop.brand,
            model_name=inventory_laptop.model_name,
            core_generation=inventory_laptop.generation,
            ram=inventory_laptop.ram,
            storage=inventory_laptop.storage,
            condition=inventory_laptop.get_condition_display(),
            **validated_data,
        )

        inventory_laptop.quantity = new_quantity
        inventory_laptop.save(update_fields=["quantity"])
        InventoryMovement.objects.create(
            product=inventory_laptop, type=InventoryMovement.SHOPKEEPER, quantity=-1,
            reference_id=item.item_reference, created_by=request.user,
        )

        write_audit_log(
            request.user, "ADD_SHOPKEEPER_LAPTOP", "Shopkeeper", item.shopkeeper_id,
            {"item_reference": item.item_reference, "price": str(item.price), "inventory_laptop_id": inventory_laptop.id},
        )
        return item

    @transaction.atomic
    def update(self, instance, validated_data):
        # Specs are read_only above, so validated_data can only ever
        # contain "price" (and maybe "shopkeeper", which we ignore --
        # a laptop never moves to a different shopkeeper account).
        request = self.context["request"]
        validated_data.pop("shopkeeper", None)
        validated_data.pop("inventory_laptop", None)
        before_price = instance.price
        new_price = validated_data.get("price", before_price)

        if new_price != before_price:
            # Lowering the price below what's already been paid against
            # THIS laptop specifically would leave it with a negative
            # remaining balance -- block that, same rule as everywhere else.
            already_paid = instance.paid_amount
            try:
                calculate_remaining(new_price, [already_paid])
            except BusinessRuleError as exc:
                raise serializers.ValidationError(str(exc))

        item = super().update(instance, validated_data)
        write_audit_log(
            request.user, "UPDATE_SHOPKEEPER_LAPTOP", "Shopkeeper", item.shopkeeper_id,
            {"item_reference": item.item_reference, "price_before": str(before_price), "price_after": str(item.price)},
        )
        return item


class ShopkeeperExtraMoneySerializer(serializers.ModelSerializer):
    """Extra cash a shopkeeper takes on top of laptops -- its own
    separate entry/receipt, rolled into the shopkeeper's one combined
    bill total."""

    item_reference = serializers.CharField(read_only=True)
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    remaining_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_cleared = serializers.BooleanField(read_only=True)

    class Meta:
        model = ShopkeeperExtraMoney
        fields = [
            "id", "shopkeeper", "item_reference", "amount", "note",
            "added_at", "paid_amount", "remaining_amount", "is_cleared",
        ]
        read_only_fields = ["id", "item_reference", "added_at"]

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        entry = ShopkeeperExtraMoney.objects.create(created_by=request.user, **validated_data)
        write_audit_log(
            request.user, "ADD_SHOPKEEPER_EXTRA_MONEY", "Shopkeeper", entry.shopkeeper_id,
            {"item_reference": entry.item_reference, "amount": str(entry.amount)},
        )
        return entry

    @transaction.atomic
    def update(self, instance, validated_data):
        request = self.context["request"]
        validated_data.pop("shopkeeper", None)
        before_amount = instance.amount
        new_amount = validated_data.get("amount", before_amount)

        if new_amount != before_amount:
            already_paid = instance.paid_amount
            try:
                calculate_remaining(new_amount, [already_paid])
            except BusinessRuleError as exc:
                raise serializers.ValidationError(str(exc))

        entry = super().update(instance, validated_data)
        write_audit_log(
            request.user, "UPDATE_SHOPKEEPER_EXTRA_MONEY", "Shopkeeper", entry.shopkeeper_id,
            {"item_reference": entry.item_reference, "amount_before": str(before_amount), "amount_after": str(entry.amount)},
        )
        return entry


class ShopkeeperPaymentSerializer(serializers.ModelSerializer):
    """A payment always targets exactly one thing: a specific laptop
    (`laptop_item`) or a specific extra-money entry (`extra_money`) --
    the "Extra Money / Laptop Payment" dropdown. `notes` travels with the
    payment and is always shown alongside it."""

    class Meta:
        model = ShopkeeperPayment
        fields = [
            "id", "shopkeeper", "laptop_item", "extra_money", "amount",
            "payment_date", "method", "note", "recorded_by",
        ]
        read_only_fields = ["id", "payment_date", "recorded_by"]

    def validate(self, attrs):
        laptop_item = attrs.get("laptop_item", getattr(self.instance, "laptop_item", None))
        extra_money = attrs.get("extra_money", getattr(self.instance, "extra_money", None))
        if bool(laptop_item) == bool(extra_money):
            raise serializers.ValidationError(
                "Select exactly one target for this payment: a laptop or extra money -- not both, not neither."
            )
        shopkeeper = attrs.get("shopkeeper", getattr(self.instance, "shopkeeper", None))
        target = laptop_item or extra_money
        if shopkeeper and target.shopkeeper_id != shopkeeper.id:
            raise serializers.ValidationError("The selected laptop/extra money does not belong to this shopkeeper.")
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        shopkeeper = Shopkeeper.objects.select_for_update().get(pk=validated_data["shopkeeper"].pk)
        target = validated_data.get("laptop_item") or validated_data.get("extra_money")

        # Lock and re-check the target row so two payments against the
        # same laptop can't race past its remaining balance.
        target_model = type(target)
        target = target_model.objects.select_for_update().get(pk=target.pk)
        already_paid = target.paid_amount
        target_price = target.price if isinstance(target, ShopkeeperLaptopItem) else target.amount
        try:
            validate_new_payment(target_price, [already_paid], validated_data["amount"])
        except BusinessRuleError as exc:
            raise serializers.ValidationError(str(exc))

        payment = ShopkeeperPayment.objects.create(recorded_by=request.user, **validated_data)
        write_audit_log(
            request.user, "ADD_SHOPKEEPER_PAYMENT", "Shopkeeper", shopkeeper.id,
            {
                "amount": str(validated_data["amount"]),
                "target": "laptop" if isinstance(target, ShopkeeperLaptopItem) else "extra_money",
                "target_reference": target.item_reference,
            },
        )
        return payment

    @transaction.atomic
    def update(self, instance, validated_data):
        """Edit an already-recorded payment's amount/method/note (the
        target itself is not changed here -- delete and re-add if the
        payment was recorded against the wrong laptop)."""
        request = self.context["request"]
        validated_data.pop("laptop_item", None)
        validated_data.pop("extra_money", None)
        validated_data.pop("shopkeeper", None)
        new_amount = validated_data.get("amount", instance.amount)

        target = instance.laptop_item or instance.extra_money
        target_model = type(target)
        target = target_model.objects.select_for_update().get(pk=target.pk)

        if "amount" in validated_data:
            other_paid = total_received_excluding(target, instance.pk)
            target_price = target.price if isinstance(target, ShopkeeperLaptopItem) else target.amount
            try:
                validate_new_payment(target_price, [other_paid], new_amount)
            except BusinessRuleError as exc:
                raise serializers.ValidationError(str(exc))

        before_amount = instance.amount
        payment = super().update(instance, validated_data)
        write_audit_log(
            request.user, "UPDATE_SHOPKEEPER_PAYMENT", "Shopkeeper", instance.shopkeeper_id,
            {"amount_before": str(before_amount), "amount_after": str(payment.amount)},
        )
        return payment


def total_received_excluding(target, payment_id) -> Decimal:
    """Sum of a laptop/extra-money target's other payments, excluding one
    (used when editing that payment's own amount so it doesn't double-count
    against itself)."""
    from apps.core.business_rules import total_received
    amounts = target.targeted_payments.exclude(pk=payment_id).values_list("amount", flat=True)
    return total_received(amounts)


class ShopkeeperSerializer(serializers.ModelSerializer):
    """One record per shopkeeper, reused for every laptop/extra-money they
    take -- creating a shopkeeper who already exists should never happen
    from the app; instead the UI offers 'Add another laptop' / 'Add Extra
    Money' on the existing record. Nested read-only here so a single GET
    renders the whole combined bill."""

    reference_number = serializers.CharField(read_only=True)
    laptops = ShopkeeperLaptopItemSerializer(many=True, read_only=True)
    extra_money = ShopkeeperExtraMoneySerializer(many=True, read_only=True)
    payments = ShopkeeperPaymentSerializer(many=True, read_only=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_received = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    remaining_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = Shopkeeper
        fields = [
            "id", "reference_number", "name", "phone", "cnic", "address", "notes",
            "laptops", "extra_money", "payments", "total_amount", "total_received",
            "remaining_amount", "status", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "reference_number", "created_at", "updated_at"]
