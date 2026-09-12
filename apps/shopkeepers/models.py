"""SRS 4.7 (Separate Shopkeeper section), 7 (Shopkeeper entity).

A Shopkeeper is created once and reused. Every laptop they take on
installment is added under their existing record via ShopkeeperLaptopItem
-- picked from shop Inventory (brand/model/specs copied at add-time and
never editable afterward) with only the shopkeeper's own price editable,
since that price differs from the shop's own sale price. Giving a laptop
to a shopkeeper reduces the shop's Inventory stock, same as a sale, so
stock counts and low-stock alerts stay accurate.

A shopkeeper can also take ShopkeeperExtraMoney (cash on top of laptops)
-- its own separate record/receipt, but rolled into the shopkeeper's one
combined bill total.

Payments (ShopkeeperPayment) are recorded once per shopkeeper but are
explicitly targeted at ONE thing when made -- a specific laptop or a
specific extra-money entry -- rather than auto-allocated. That target is
what shows "Cleared" on the bill once its own price/amount is fully paid.
There is exactly one bill/reference number per shopkeeper either way.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction

from apps.core.models import TimeStampedModel


def _next_shopkeeper_reference():
    """SK-00001, SK-00002, ... one reference number per shopkeeper, issued
    once when the shopkeeper account is created and never changed."""
    with transaction.atomic():
        last = (
            Shopkeeper.objects.select_for_update()
            .exclude(reference_number="")
            .order_by("-id")
            .first()
        )
        last_seq = 0
        if last and last.reference_number.startswith("SK-"):
            try:
                last_seq = int(last.reference_number.split("-")[1])
            except (IndexError, ValueError):
                last_seq = 0
        return f"SK-{str(last_seq + 1).zfill(5)}"


class Shopkeeper(TimeStampedModel):
    ACTIVE, CLEARED = "ACTIVE", "CLEARED"

    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    cnic = models.CharField(max_length=30, blank=True, null=True)  # SRS 4.8: optional, avoid storing unless needed
    address = models.CharField(max_length=250, blank=True, default="")
    notes = models.TextField(blank=True, default="")

    # One reference number per shopkeeper (the "one receipt" the owner
    # asked for) -- every laptop item, extra-money entry, and payment
    # lives under this same account instead of generating a new one each
    # time.
    reference_number = models.CharField(max_length=20, unique=True, blank=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["name", "phone"])]

    def __str__(self):
        return f"{self.name} ({self.phone})"

    def save(self, *args, **kwargs):
        if not self.reference_number:
            self.reference_number = _next_shopkeeper_reference()
        super().save(*args, **kwargs)

    # -- running-account totals (SRS-style business rules, all shared with
    # the credit app's helpers so both use identical rounding/validation) --

    @property
    def total_amount(self) -> Decimal:
        """Combined total = every laptop's price + every extra-money
        amount, all under this one shopkeeper account/bill."""
        from apps.core.business_rules import _money
        total = Decimal("0")
        for price in self.laptops.values_list("price", flat=True):
            total += _money(price)
        for amount in self.extra_money.values_list("amount", flat=True):
            total += _money(amount)
        return total

    @property
    def total_received(self) -> Decimal:
        from apps.core.business_rules import total_received
        return total_received(self.payments.values_list("amount", flat=True))

    @property
    def remaining_amount(self) -> Decimal:
        from apps.core.business_rules import calculate_remaining, BusinessRuleError
        try:
            return calculate_remaining(
                self.total_amount, self.payments.values_list("amount", flat=True)
            )
        except BusinessRuleError:
            # Never let *reading* a shopkeeper's balance fail -- floor at 0
            # for display instead of throwing, so the account can still be
            # opened even from an already-broken historical record.
            return Decimal("0")

    @property
    def status(self) -> str:
        if (self.laptops.exists() or self.extra_money.exists()) and self.remaining_amount == 0:
            return self.CLEARED
        return self.ACTIVE


class ShopkeeperLaptopItem(TimeStampedModel):
    """A laptop taken by a shopkeeper on installment -- picked from shop
    Inventory. Brand/model/specs are copied from the Inventory item at the
    moment it's added and are fixed after that (so the record stays
    correct even if the Inventory item is later edited, archived, or
    deleted); only the price given to this shopkeeper stays editable,
    since it's set by the owner and differs from the shop's own sale
    price. Adding one reduces the linked Inventory item's stock, exactly
    like a sale, and removing one restores it."""

    # CASCADE: deleting a shopkeeper account is expected to remove every
    # laptop item entered under it too (owner request -- "delete the
    # shopkeeper account and laptop also be deleted").
    shopkeeper = models.ForeignKey(Shopkeeper, on_delete=models.CASCADE, related_name="laptops")

    # SET_NULL: the Inventory item itself may later be archived/deleted;
    # this record's own copied specs below are what the bill actually
    # shows, so losing the live link doesn't break anything.
    inventory_laptop = models.ForeignKey(
        "inventory.Laptop", on_delete=models.SET_NULL, null=True, blank=True, related_name="shopkeeper_items"
    )

    item_reference = models.CharField(max_length=25, unique=True, blank=True)

    # Copied from Inventory at add-time -- fixed afterward (not editable).
    brand = models.CharField(max_length=100)
    model_name = models.CharField(max_length=150)
    core_generation = models.CharField(max_length=50, blank=True, default="")
    ram = models.CharField(max_length=50, blank=True, default="")
    storage = models.CharField(max_length=50, blank=True, default="")
    condition = models.CharField(max_length=50, blank=True, default="")
    notes = models.CharField(max_length=250, blank=True, default="")

    # The only field the admin can set/edit here -- the rate given to this
    # particular shopkeeper, separate from the shop's own sale price.
    price = models.DecimalField(max_digits=12, decimal_places=2)

    added_at = models.DateField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ["added_at", "id"]

    def __str__(self):
        return f"{self.item_reference}: {self.brand} {self.model_name} for {self.shopkeeper}"

    def save(self, *args, **kwargs):
        if not self.item_reference:
            existing_count = self.shopkeeper.laptops.count() + self.shopkeeper.extra_money.count()
            self.item_reference = f"{self.shopkeeper.reference_number}-{existing_count + 1}"
        super().save(*args, **kwargs)

    @property
    def paid_amount(self) -> Decimal:
        from apps.core.business_rules import total_received
        return total_received(self.targeted_payments.values_list("amount", flat=True))

    @property
    def remaining_amount(self) -> Decimal:
        from apps.core.business_rules import calculate_remaining, BusinessRuleError
        try:
            return calculate_remaining(self.price, self.targeted_payments.values_list("amount", flat=True))
        except BusinessRuleError:
            return Decimal("0")

    @property
    def is_cleared(self) -> bool:
        return self.remaining_amount == 0


class ShopkeeperExtraMoney(TimeStampedModel):
    """Cash a shopkeeper takes on top of laptops (SRS-style extension per
    owner request: "some shopkeepers also take extra money"). Shown as its
    own separate entry/receipt line, but its amount is rolled into the
    shopkeeper's one combined bill total, same as a laptop."""

    shopkeeper = models.ForeignKey(Shopkeeper, on_delete=models.CASCADE, related_name="extra_money")
    item_reference = models.CharField(max_length=25, unique=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=250, blank=True, default="")
    added_at = models.DateField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ["added_at", "id"]
        verbose_name_plural = "Shopkeeper extra money"

    def __str__(self):
        return f"{self.item_reference}: Rs. {self.amount} extra money for {self.shopkeeper}"

    def save(self, *args, **kwargs):
        if not self.item_reference:
            existing_count = self.shopkeeper.laptops.count() + self.shopkeeper.extra_money.count()
            self.item_reference = f"{self.shopkeeper.reference_number}-{existing_count + 1}"
        super().save(*args, **kwargs)

    @property
    def paid_amount(self) -> Decimal:
        from apps.core.business_rules import total_received
        return total_received(self.targeted_payments.values_list("amount", flat=True))

    @property
    def remaining_amount(self) -> Decimal:
        from apps.core.business_rules import calculate_remaining, BusinessRuleError
        try:
            return calculate_remaining(self.amount, self.targeted_payments.values_list("amount", flat=True))
        except BusinessRuleError:
            return Decimal("0")

    @property
    def is_cleared(self) -> bool:
        return self.remaining_amount == 0


class ShopkeeperPayment(TimeStampedModel):
    """One payment against a shopkeeper's account, explicitly targeted at
    ONE laptop OR ONE extra-money entry (never both, never neither) -- the
    "which laptop is this payment clearing" dropdown the owner asked for.
    The shopkeeper's combined total/received/remaining still add up across
    every payment regardless of what each one targets."""

    CASH, BANK, OTHER = "CASH", "BANK", "OTHER"
    METHOD_CHOICES = [(CASH, "Cash"), (BANK, "Bank"), (OTHER, "Other")]

    # CASCADE: same reasoning as ShopkeeperLaptopItem.shopkeeper above --
    # deleting the account removes its payment history with it.
    shopkeeper = models.ForeignKey(Shopkeeper, on_delete=models.CASCADE, related_name="payments")

    # Exactly one of these two is set -- enforced in the serializer, where
    # a clear "Extra Money" vs "Laptop Payment" dropdown decides which.
    laptop_item = models.ForeignKey(
        ShopkeeperLaptopItem, on_delete=models.CASCADE, null=True, blank=True, related_name="targeted_payments"
    )
    extra_money = models.ForeignKey(
        ShopkeeperExtraMoney, on_delete=models.CASCADE, null=True, blank=True, related_name="targeted_payments"
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField(auto_now_add=True)
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default=CASH)
    note = models.CharField(max_length=250, blank=True, default="")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ["-payment_date", "-created_at"]

    def __str__(self):
        return f"Rs. {self.amount} on {self.payment_date} for {self.shopkeeper}"
