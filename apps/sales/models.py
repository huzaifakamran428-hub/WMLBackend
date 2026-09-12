"""SRS 4.5 (Sales and Bill Generation), 4.6 (Bill Layout), 4.7 (Customer
section), 7 (Sale / Sale Item entities), 12 (Receipt numbers)."""
from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedModel


class ReceiptSequence(models.Model):
    """Single-row counter guaranteeing unique, ever-increasing receipt
    numbers (SRS 12). Incremented inside a DB transaction with
    select_for_update() to stay correct under concurrent sales."""
    last_used = models.PositiveIntegerField(default=0)

    @classmethod
    def next_number(cls):
        from django.db import transaction
        from apps.core.business_rules import next_receipt_sequence, format_receipt_number
        with transaction.atomic():
            row, _ = cls.objects.select_for_update().get_or_create(pk=1)
            row.last_used = next_receipt_sequence(row.last_used)
            row.save(update_fields=["last_used"])
            return format_receipt_number(row.last_used)


class Sale(TimeStampedModel):
    CASH, BANK, OTHER = "CASH", "BANK", "OTHER"
    PAYMENT_TYPE_CHOICES = [(CASH, "Cash"), (BANK, "Bank"), (OTHER, "Other")]

    PAID, PARTIAL, DUE = "PAID", "PARTIAL", "DUE"
    PAYMENT_STATUS_CHOICES = [(PAID, "Paid"), (PARTIAL, "Partial"), (DUE, "Due")]

    receipt_no = models.CharField(max_length=10, unique=True, editable=False)  # SRS 12
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="sales")

    sale_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    final_total = models.DecimalField(max_digits=12, decimal_places=2, editable=False)

    payment_type = models.CharField(max_length=10, choices=PAYMENT_TYPE_CHOICES, default=CASH)
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default=PAID)
    amount_received = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    sale_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ["-sale_date"]
        indexes = [models.Index(fields=["receipt_no"]), models.Index(fields=["sale_date"])]

    def __str__(self):
        return f"Receipt {self.receipt_no} - {self.customer}"

    @property
    def remaining_amount(self):
        return self.final_total - self.amount_received


class SaleItem(TimeStampedModel):
    """SRS 7: 'Sale Item: id, sale_id, product_id, purchase_cost_snapshot,
    sale_price, quantity' — SRS 4.12: purchase cost snapshot is a
    historical value, immutable after the sale."""
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("inventory.Laptop", on_delete=models.PROTECT, related_name="sale_items")
    purchase_cost_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    sale_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.product} x{self.quantity} (sale #{self.sale_id})"

    @property
    def profit(self):
        from apps.core.business_rules import calculate_profit
        return calculate_profit(self.sale_price, self.purchase_cost_snapshot, self.quantity)
