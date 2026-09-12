"""SRS 4.7-4.11 (Shopkeeper/Customer Credit Records, Payment Tracking,
Installment Completion, Notifications), 7 (Credit/Installment Plan,
Payment entities), 11 (business rules)."""
from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedModel


class CreditPlan(TimeStampedModel):
    ACTIVE, CLEARED = "ACTIVE", "CLEARED"
    STATUS_CHOICES = [(ACTIVE, "Active"), (CLEARED, "Cleared / Paid in Full")]

    # SRS 4.8: "Person Name" can be either a shopkeeper or a customer;
    # exactly one of the two FKs must be set.
    # SET_NULL (not PROTECT): current shopkeeper accounts no longer go
    # through CreditPlan at all (they use ShopkeeperLaptopItem/
    # ShopkeeperPayment instead -- see apps.shopkeepers.models), so this
    # link only exists on legacy rows. It must not block deleting a
    # shopkeeper account.
    shopkeeper = models.ForeignKey("shopkeepers.Shopkeeper", on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name="credit_plans")
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT,
                                  null=True, blank=True, related_name="credit_plans")

    laptop = models.ForeignKey("inventory.Laptop", on_delete=models.PROTECT, related_name="credit_plans")
    sale = models.ForeignKey("sales.Sale", on_delete=models.SET_NULL, null=True, blank=True, related_name="credit_plans")

    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    down_payment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    installment_amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=ACTIVE)
    cleared_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "due_date"])]

    def __str__(self):
        person = self.shopkeeper or self.customer
        return f"Credit plan for {person} - {self.laptop}"

    @property
    def person(self):
        return self.shopkeeper or self.customer

    @property
    def total_received(self):
        from apps.core.business_rules import total_received
        return total_received(self.payments.values_list("amount", flat=True)) + self.down_payment

    @property
    def remaining_amount(self):
        from apps.core.business_rules import calculate_remaining
        all_amounts = list(self.payments.values_list("amount", flat=True)) + [self.down_payment]
        return calculate_remaining(self.total_amount, all_amounts)

    @property
    def is_overdue(self):
        from apps.core.business_rules import is_overdue
        return is_overdue(self.due_date, self.status)


class Payment(TimeStampedModel):
    """SRS 7: 'Payment: id, credit_plan_id, amount, payment_date, method,
    note' — SRS 4.9: 'Each payment is stored separately.'"""
    CASH, BANK, OTHER = "CASH", "BANK", "OTHER"
    METHOD_CHOICES = [(CASH, "Cash"), (BANK, "Bank"), (OTHER, "Other")]

    credit_plan = models.ForeignKey(CreditPlan, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField(auto_now_add=True)
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default=CASH)
    note = models.CharField(max_length=250, blank=True, default="")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ["-payment_date", "-created_at"]

    def __str__(self):
        return f"Rs. {self.amount} on {self.payment_date} for plan #{self.credit_plan_id}"
