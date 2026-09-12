"""
core/business_rules.py

Pure, framework-free implementation of every calculation / status rule
in Section 11 ("Business Rules and Validation") of the SRS. Kept free of
Django imports on purpose so it can be unit tested in any environment
and is reused unmodified by the Django serializers/models/signals in
apps/sales, apps/credit and apps/inventory.

All money values are handled as integers/Decimals in "paisa-free" Rupee
units (the store does not use sub-rupee currency), using Decimal to
avoid floating point drift.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
from typing import Iterable, Optional


LOW_STOCK_THRESHOLD = 2  # SRS 4.4 / 4.2 / 10: alert when quantity < 2
REMINDER_DAYS_BEFORE_DUE = 2  # SRS 4.11 / 10


class BusinessRuleError(ValueError):
    """Raised when an operation would violate an SRS business rule."""


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# 11: Final sale price / discount
# ---------------------------------------------------------------------------

def calculate_final_price(sale_price, discount_amount=0, discount_percent=0) -> Decimal:
    """Final sale price = sale price - discount (SRS 11).

    Accepts either a fixed discount_amount OR a discount_percent (SRS 4.3 /
    4.5 allow discount to be "fixed amount or percentage"). If both are
    supplied, the percentage is applied first and the fixed amount is then
    subtracted, matching how the SRS describes discount as a single field
    that can be either type — callers should normally supply only one.
    """
    sale_price = _money(sale_price)
    if sale_price < 0:
        raise BusinessRuleError("Sale price cannot be negative.")

    price = sale_price
    if discount_percent:
        discount_percent = Decimal(str(discount_percent))
        if not (0 <= discount_percent <= 100):
            raise BusinessRuleError("Discount percent must be between 0 and 100.")
        price -= (price * discount_percent / Decimal("100"))

    if discount_amount:
        discount_amount = _money(discount_amount)
        if discount_amount < 0:
            raise BusinessRuleError("Discount amount cannot be negative.")
        price -= discount_amount

    final_price = _money(price)
    if final_price < 0:
        raise BusinessRuleError("Discount cannot exceed the sale price.")
    return final_price


# ---------------------------------------------------------------------------
# 11: Profit
# ---------------------------------------------------------------------------

def calculate_profit(final_sale_price, purchase_cost_snapshot, quantity=1) -> Decimal:
    """Profit = final sale price - purchase cost for the sold quantity (SRS
    4.12 / 11). purchase_cost_snapshot is the price-per-unit captured at the
    moment of sale (SRS 4.12: "Purchase cost must remain unchanged as a
    historical snapshot after the sale")."""
    final_sale_price = _money(final_sale_price)
    total_cost = _money(purchase_cost_snapshot) * quantity
    return final_sale_price - total_cost


# ---------------------------------------------------------------------------
# 11 / 4.4: Inventory
# ---------------------------------------------------------------------------

def apply_sale_to_stock(current_quantity: int, quantity_sold: int) -> int:
    """Reduce stock after a sale. Never allows negative inventory (SRS 4.4
    / 11: "Inventory quantity cannot become negative", "System prevents
    selling more units than available stock.")."""
    if quantity_sold <= 0:
        raise BusinessRuleError("Quantity sold must be greater than zero.")
    if quantity_sold > current_quantity:
        raise BusinessRuleError(
            f"Cannot sell {quantity_sold} unit(s); only {current_quantity} in stock."
        )
    return current_quantity - quantity_sold


def is_low_stock(quantity: int) -> bool:
    """SRS 4.4 / 4.2 / 10: alert when quantity becomes less than 2."""
    return quantity < LOW_STOCK_THRESHOLD


def is_out_of_stock(quantity: int) -> bool:
    return quantity <= 0


# ---------------------------------------------------------------------------
# 4.9 / 4.10 / 11: Credit plan / installment balance & status
# ---------------------------------------------------------------------------

CLEARED = "CLEARED"
ACTIVE = "ACTIVE"
OVERDUE = "OVERDUE"


def total_received(payments: Iterable) -> Decimal:
    """Total Received is calculated from recorded payments (SRS 4.9 / 11).
    `payments` is an iterable of amounts (Decimal/int/str)."""
    total = Decimal("0")
    for amount in payments:
        amount = _money(amount)
        if amount < 0:
            raise BusinessRuleError("A payment amount cannot be negative.")
        total += amount
    return total


def calculate_remaining(total_amount, payments: Iterable) -> Decimal:
    """Remaining Amount = Total Amount - Total Received (SRS 4.8 / 4.9 /
    11). Never negative (SRS 4.9 / 11)."""
    total_amount = _money(total_amount)
    remaining = total_amount - total_received(payments)
    if remaining < 0:
        raise BusinessRuleError("Remaining amount must never be less than Rs. 0.")
    return remaining


def validate_new_payment(total_amount, existing_payments: Iterable, new_payment_amount) -> Decimal:
    """SRS 4.9: 'Payment greater than the remaining balance is rejected
    unless an explicit controlled adjustment/reversal process is
    implemented.' SRS 4.10: a CLEARED plan cannot receive another normal
    payment. Returns the new remaining balance if the payment is valid,
    else raises BusinessRuleError."""
    total_amount = _money(total_amount)
    new_payment_amount = _money(new_payment_amount)
    if new_payment_amount <= 0:
        raise BusinessRuleError("Payment amount must be greater than Rs. 0.")

    remaining_before = calculate_remaining(total_amount, existing_payments)
    if remaining_before == 0:
        raise BusinessRuleError(
            "This credit plan is already CLEARED; no further normal payment can be added."
        )
    if new_payment_amount > remaining_before:
        raise BusinessRuleError(
            "Payment amount cannot be greater than the remaining amount."
        )
    return remaining_before - new_payment_amount


def credit_plan_status(total_amount, payments: Iterable) -> str:
    """SRS 4.10: status becomes CLEARED / PAID IN FULL only when Total
    Received equals Total Amount."""
    remaining = calculate_remaining(total_amount, payments)
    return CLEARED if remaining == 0 else ACTIVE


def is_overdue(due_date: date, status: str, as_of: Optional[date] = None) -> bool:
    """SRS 4.11: after the due date and unpaid status, mark the plan
    overdue. SRS 4.10 / 11: reminders/overdue status stop automatically
    once a plan is CLEARED."""
    if status == CLEARED:
        return False
    as_of = as_of or date.today()
    return as_of > due_date


def reminder_due(due_date: date, status: str, as_of: Optional[date] = None) -> bool:
    """SRS 4.11 / 10: two days before each due date, create a reminder.
    Reminders stop automatically once CLEARED."""
    if status == CLEARED:
        return False
    as_of = as_of or date.today()
    return as_of == (due_date - timedelta(days=REMINDER_DAYS_BEFORE_DUE))


# ---------------------------------------------------------------------------
# Shopkeeper running account: one shopkeeper, many manually-entered laptops,
# one combined balance. Payments are recorded against the account as a
# whole (a single "how much he paid" figure, per the shop owner's own
# workflow) but are allocated oldest-laptop-first purely for *display*, so
# each laptop can still show its own paid/remaining figure under the one
# combined bill.
# ---------------------------------------------------------------------------

def allocate_payments_fifo(item_prices: Iterable, total_paid) -> list:
    """Given laptop prices in the order they were added, and the total
    amount paid so far against the shopkeeper's combined balance, return
    the remaining balance for each laptop (oldest first absorbs payment
    first). The sum of the returned list always equals
    calculate_remaining(sum(item_prices), [total_paid]).
    """
    remaining_pool = _money(total_paid)
    if remaining_pool < 0:
        raise BusinessRuleError("Total paid cannot be negative.")

    balances = []
    for price in item_prices:
        price = _money(price)
        if remaining_pool >= price:
            balances.append(Decimal("0"))
            remaining_pool -= price
        else:
            balances.append(price - remaining_pool)
            remaining_pool = Decimal("0")
    return balances


# ---------------------------------------------------------------------------
# 12: Receipt / reference numbers
# ---------------------------------------------------------------------------

MAX_RECEIPT_NUMBER = 99_999  # SRS 12: "Support up to 99,999 receipt numbers"


def format_receipt_number(sequence_number: int) -> str:
    """SRS 12: 'Receipt No. 00001, 00002, 00003' — zero-padded to 5 digits,
    unique, permanently attached to the sale, never changes."""
    if not (1 <= sequence_number <= MAX_RECEIPT_NUMBER):
        raise BusinessRuleError(
            f"Receipt sequence number must be between 1 and {MAX_RECEIPT_NUMBER}."
        )
    return str(sequence_number).zfill(5)


def next_receipt_sequence(last_used_sequence: int) -> int:
    """Receipt numbers continue increasing for new sales (SRS 12)."""
    next_seq = last_used_sequence + 1
    if next_seq > MAX_RECEIPT_NUMBER:
        raise BusinessRuleError("Maximum receipt number (99999) has been reached.")
    return next_seq


@dataclass
class SaleCalculation:
    """Convenience aggregate used by the Sales serializer/service to run
    every SRS 11 calculation for one sale line in a single call."""
    sale_price: Decimal
    discount_amount: Decimal = Decimal("0")
    discount_percent: Decimal = Decimal("0")
    purchase_cost_snapshot: Decimal = Decimal("0")
    quantity: int = 1
    final_price: Decimal = field(init=False)
    profit: Decimal = field(init=False)

    def __post_init__(self):
        self.final_price = calculate_final_price(
            self.sale_price, self.discount_amount, self.discount_percent
        )
        self.profit = calculate_profit(
            self.final_price, self.purchase_cost_snapshot, self.quantity
        )
