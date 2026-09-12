from decimal import Decimal
from django.db import transaction
from rest_framework import serializers

from apps.sales.models import Sale, SaleItem, ReceiptSequence
from apps.inventory.models import Laptop, InventoryMovement
from apps.core.business_rules import (
    calculate_final_price, calculate_profit, apply_sale_to_stock, BusinessRuleError,
)
from apps.audit.utils import write_audit_log


class SaleItemSerializer(serializers.ModelSerializer):
    profit = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = SaleItem
        fields = ["id", "product", "purchase_cost_snapshot", "sale_price", "quantity", "profit"]
        read_only_fields = ["id", "purchase_cost_snapshot", "profit"]


class SaleSerializer(serializers.ModelSerializer):
    """SRS 4.5, 4.6, 8.2 (Normal Sale Workflow):
    - System calculates final price immediately.
    - Backend transaction creates the sale and inventory movement atomically.
    - Unique receipt/reference number is generated.
    - Historical purchase cost snapshot is stored.
    """
    remaining_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    laptop_id = serializers.PrimaryKeyRelatedField(queryset=Laptop.objects.all(), write_only=True)
    quantity = serializers.IntegerField(write_only=True, default=1, min_value=1)
    items = SaleItemSerializer(many=True, read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id", "receipt_no", "customer", "laptop_id", "quantity",
            "sale_price", "discount_amount", "discount_percent", "final_total",
            "payment_type", "payment_status", "amount_received", "remaining_amount",
            "sale_date", "notes", "items", "created_by",
        ]
        read_only_fields = ["id", "receipt_no", "final_total", "sale_date", "items", "created_by"]

    def validate(self, attrs):
        is_create = self.instance is None

        if is_create:
            laptop = attrs["laptop_id"]
            quantity = attrs.get("quantity", 1)
            if laptop.is_archived:
                raise serializers.ValidationError("This laptop record has been archived and cannot be sold.")
            if quantity > laptop.quantity:
                raise serializers.ValidationError(
                    f"Cannot sell {quantity} unit(s); only {laptop.quantity} in stock."
                )
            sale_price = attrs["sale_price"]
        else:
            # Editing an existing sale (SRS 11: admin can correct a
            # mis-entered bill). The laptop a sale was made against can't
            # be changed here -- only quantity/price/discount/payment
            # fields -- so silently ignore laptop_id if it was sent.
            attrs.pop("laptop_id", None)
            item = self.instance.items.first()
            quantity = attrs.get("quantity", item.quantity if item else 1)
            sale_price = attrs.get("sale_price", self.instance.sale_price)

            if item and "quantity" in attrs and quantity != item.quantity:
                extra_needed = quantity - item.quantity
                if extra_needed > 0 and extra_needed > item.product.quantity:
                    raise serializers.ValidationError(
                        f"Cannot raise quantity to {quantity}; only "
                        f"{item.product.quantity + item.quantity} unit(s) would be available "
                        f"(current stock plus what this sale already holds)."
                    )

        discount_amount = attrs.get("discount_amount", getattr(self.instance, "discount_amount", 0))
        discount_percent = attrs.get("discount_percent", getattr(self.instance, "discount_percent", 0))
        try:
            # Validate against the same total (unit price x quantity) that
            # create()/update() will actually charge, so this rejects an
            # out-of-range discount before the sale is written.
            calculate_final_price(sale_price * quantity, discount_amount, discount_percent)
        except BusinessRuleError as exc:
            raise serializers.ValidationError(str(exc))
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        laptop = validated_data.pop("laptop_id")
        quantity = validated_data.pop("quantity", 1)
        request = self.context["request"]

        # sale_price is the per-unit price; the discount is applied once to
        # the whole line (unit price x quantity), not per unit — otherwise
        # multi-unit sales were silently billed and profit-calculated as if
        # only one unit had been sold.
        final_total = calculate_final_price(
            validated_data["sale_price"] * quantity,
            validated_data.get("discount_amount", 0),
            validated_data.get("discount_percent", 0),
        )

        # Re-check stock under lock to stay correct under concurrent sales (SRS 4.4/11).
        laptop = Laptop.objects.select_for_update().get(pk=laptop.pk)
        laptop.quantity = apply_sale_to_stock(laptop.quantity, quantity)
        laptop.save(update_fields=["quantity"])

        amount_received = validated_data.get("amount_received", 0)
        if amount_received >= final_total:
            payment_status = Sale.PAID
        elif amount_received > 0:
            payment_status = Sale.PARTIAL
        else:
            payment_status = Sale.DUE
        validated_data["payment_status"] = payment_status

        sale = Sale.objects.create(
            receipt_no=ReceiptSequence.next_number(),
            final_total=final_total,
            created_by=request.user,
            **validated_data,
        )

        SaleItem.objects.create(
            sale=sale, product=laptop,
            purchase_cost_snapshot=laptop.purchase_price,  # SRS 4.12: immutable historical snapshot
            sale_price=final_total, quantity=quantity,
        )

        InventoryMovement.objects.create(
            product=laptop, type=InventoryMovement.SALE, quantity=-quantity,
            reference_id=sale.receipt_no, created_by=request.user,
        )

        write_audit_log(request.user, "CREATE_SALE", "Sale", sale.id, {"receipt_no": sale.receipt_no})
        return sale

@transaction.atomic
def update(self, instance, validated_data):
    """Update an existing sale and reconcile inventory when quantity changes."""
    request = self.context["request"]

    item = instance.items.select_related("product").first()

    new_quantity = validated_data.pop("quantity", None)

    sale_price = validated_data.get(
        "sale_price",
        instance.sale_price,
    )
    discount_amount = validated_data.get(
        "discount_amount",
        instance.discount_amount,
    )
    discount_percent = validated_data.get(
        "discount_percent",
        instance.discount_percent,
    )

    # ---------------------------------------------------------
    # 1. Update quantity and reconcile inventory
    # ---------------------------------------------------------
    if item and new_quantity is not None and new_quantity != item.quantity:

        if new_quantity < 1:
            raise serializers.ValidationError({
                "quantity": "Quantity must be at least 1."
            })

        laptop = Laptop.objects.select_for_update().get(
            pk=item.product_id
        )

        old_quantity = item.quantity
        delta = new_quantity - old_quantity

               # Increasing quantity means taking additional stock.
        if delta > 0:
            if delta > laptop.quantity:
                raise serializers.ValidationError({
                    "quantity": (
                        f"Cannot increase quantity to {new_quantity}. "
                        f"Only {laptop.quantity} additional unit(s) "
                        f"are currently available."
                    )
                })

            laptop.quantity -= delta

        # Decreasing quantity means returning stock.
        else:
            laptop.quantity += abs(delta)
            
        laptop.save(update_fields=["quantity"])

        InventoryMovement.objects.create(
            product=laptop,
            type=InventoryMovement.ADJUSTMENT,
            quantity=-delta,
            reference_id=f"{instance.receipt_no}-edit",
            created_by=request.user,
        )

        item.quantity = new_quantity

    # ---------------------------------------------------------
    # 2. Calculate new final total
    # ---------------------------------------------------------
    quantity = item.quantity if item else 1

    try:
        final_total = calculate_final_price(
            sale_price * quantity,
            discount_amount,
            discount_percent,
        )
    except BusinessRuleError as exc:
        raise serializers.ValidationError({
            "discount": str(exc)
        })

    # ---------------------------------------------------------
    # 3. Recalculate payment status
    # ---------------------------------------------------------
    amount_received = validated_data.get(
        "amount_received",
        instance.amount_received,
    )

    if amount_received < 0:
        raise serializers.ValidationError({
            "amount_received": "Amount received cannot be negative."
        })

    if amount_received >= final_total:
        payment_status = Sale.PAID
    elif amount_received > 0:
        payment_status = Sale.PARTIAL
    else:
        payment_status = Sale.DUE

    # ---------------------------------------------------------
    # 4. Save Sale
    # ---------------------------------------------------------
    instance.sale_price = sale_price
    instance.discount_amount = discount_amount
    instance.discount_percent = discount_percent
    instance.final_total = final_total

    instance.payment_type = validated_data.get(
        "payment_type",
        instance.payment_type,
    )

    instance.amount_received = amount_received
    instance.payment_status = payment_status

    instance.notes = validated_data.get(
        "notes",
        instance.notes,
    )

    instance.save()

    # ---------------------------------------------------------
    # 5. Keep SaleItem synchronized
    # ---------------------------------------------------------
    if item:
        item.sale_price = final_total
        item.save(
            update_fields=["sale_price", "quantity"]
        )

    # ---------------------------------------------------------
    # 6. Audit log
    # ---------------------------------------------------------
    write_audit_log(
        request.user,
        "UPDATE_SALE",
        "Sale",
        instance.id,
        {
            "receipt_no": instance.receipt_no,
        },
    )

    return instance