from rest_framework import serializers
from apps.inventory.models import Laptop, InventoryMovement
from apps.core.business_rules import BusinessRuleError


class LaptopSerializer(serializers.ModelSerializer):
    final_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    is_out_of_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Laptop
        fields = [
            "id", "brand", "model_name", "generation", "processor", "cpu_cores",
            "ram", "storage", "gpu", "screen_size", "condition", "serial_number",
            "purchase_price", "sale_price", "discount_amount", "discount_percent",
            "quantity", "supplier", "purchase_date", "warranty", "photo", "notes",
            "is_archived", "final_price", "is_low_stock", "is_out_of_stock",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        # SRS 4.3: discount/pricing must always resolve to a valid final price
        sale_price = attrs.get("sale_price", getattr(self.instance, "sale_price", None))
        discount_amount = attrs.get("discount_amount", getattr(self.instance, "discount_amount", 0))
        discount_percent = attrs.get("discount_percent", getattr(self.instance, "discount_percent", 0))
        if sale_price is not None:
            from apps.core.business_rules import calculate_final_price
            try:
                calculate_final_price(sale_price, discount_amount, discount_percent)
            except BusinessRuleError as exc:
                raise serializers.ValidationError({"discount_amount": str(exc)})
        return attrs

    def validate_serial_number(self, value):
        # SRS 4.3: serial number is optional. The model allows NULL so
        # multiple laptops can be saved with no serial number, but an
        # empty string ("") is a distinct value from NULL at the database
        # level — two blank submissions would otherwise collide against
        # the unique constraint. Normalize blank input to None so
        # "no serial number" behaves consistently no matter how many
        # laptops are saved without one.
        return value or None


class InventoryMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryMovement
        fields = ["id", "product", "type", "quantity", "reference_id", "created_by", "date"]
        read_only_fields = fields
