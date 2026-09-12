"""SRS 4.3 (Laptop Product / Inventory Record), 4.4 (Inventory Management),
7 (Product/Laptop, Inventory Movement entities)."""
from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedModel


class Laptop(TimeStampedModel):
    NEW, USED, REFURBISHED = "NEW", "USED", "REFURBISHED"
    CONDITION_CHOICES = [(NEW, "New"), (USED, "Used"), (REFURBISHED, "Refurbished")]

    brand = models.CharField(max_length=100)
    model_name = models.CharField(max_length=150)
    generation = models.CharField(max_length=50, blank=True, default="")
    processor = models.CharField(max_length=100)
    cpu_cores = models.PositiveIntegerField()
    ram = models.CharField(max_length=50)          # "8 GB" etc — kept as text per SRS example values
    storage = models.CharField(max_length=50)       # "256 GB SSD" etc
    gpu = models.CharField(max_length=100, blank=True, default="")
    screen_size = models.CharField(max_length=30, blank=True, default="")
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default=NEW)
    serial_number = models.CharField(max_length=100, blank=True, null=True, unique=True)

    purchase_price = models.DecimalField(max_digits=12, decimal_places=2)
    sale_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    quantity = models.PositiveIntegerField(default=0)
    supplier = models.CharField(max_length=150, blank=True, default="")
    purchase_date = models.DateField(blank=True, null=True)
    warranty = models.CharField(max_length=150, blank=True, default="")
    photo = models.ImageField(upload_to="laptops/", blank=True, null=True)  # SRS 4.3: never required to save
    notes = models.TextField(blank=True, default="")

    is_archived = models.BooleanField(default=False)  # SRS 4.4: archive, don't hard-delete financial history

    class Meta:
        ordering = ["brand", "model_name"]
        indexes = [
            models.Index(fields=["brand", "model_name", "generation", "condition"]),
            models.Index(fields=["serial_number"]),
        ]

    def __str__(self):
        return f"{self.brand} {self.model_name} ({self.serial_number or 'no S/N'})"

    @property
    def final_price(self):
        from apps.core.business_rules import calculate_final_price
        return calculate_final_price(self.sale_price, self.discount_amount, self.discount_percent)

    @property
    def is_low_stock(self):
        from apps.core.business_rules import is_low_stock
        return is_low_stock(self.quantity)

    @property
    def is_out_of_stock(self):
        from apps.core.business_rules import is_out_of_stock
        return is_out_of_stock(self.quantity)


class InventoryMovement(models.Model):
    """SRS 7: 'Inventory Movement: id, product_id, type, quantity,
    reference_id, date' — SRS 4.4: 'Inventory changes create inventory
    movement records.'"""
    STOCK_IN, SALE, ADJUSTMENT, ARCHIVE, SHOPKEEPER = "STOCK_IN", "SALE", "ADJUSTMENT", "ARCHIVE", "SHOPKEEPER"
    TYPE_CHOICES = [
        (STOCK_IN, "Stock In"), (SALE, "Sale"), (ADJUSTMENT, "Adjustment"),
        (ARCHIVE, "Archive"), (SHOPKEEPER, "Given to Shopkeeper"),
    ]

    product = models.ForeignKey(Laptop, on_delete=models.PROTECT, related_name="movements")
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    quantity = models.IntegerField()  # negative for outgoing, positive for incoming
    reference_id = models.CharField(max_length=50, blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.type} {self.quantity} - {self.product}"
