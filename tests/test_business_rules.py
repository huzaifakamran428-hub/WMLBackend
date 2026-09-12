"""
Unit tests for apps/core/business_rules.py.

These map directly to SRS Section 20 "Acceptance Criteria" and Section 11
"Business Rules and Validation". Run with:

    python3 -m unittest discover -s backend/tests -v

No Django / database / network required — this validates the pure
calculation and status logic that the Django layer (models/serializers/
signals) delegates to.
"""
import sys
import os
import unittest
from decimal import Decimal
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "core"))
import business_rules as br  # noqa: E402


class FinalPriceTests(unittest.TestCase):
    def test_fixed_discount(self):
        self.assertEqual(br.calculate_final_price(100000, discount_amount=5000), Decimal("95000"))

    def test_percent_discount(self):
        self.assertEqual(br.calculate_final_price(100000, discount_percent=10), Decimal("90000"))

    def test_no_discount(self):
        self.assertEqual(br.calculate_final_price(50000), Decimal("50000"))

    def test_discount_cannot_exceed_price(self):
        with self.assertRaises(br.BusinessRuleError):
            br.calculate_final_price(1000, discount_amount=5000)

    def test_negative_sale_price_rejected(self):
        with self.assertRaises(br.BusinessRuleError):
            br.calculate_final_price(-100)


class ProfitTests(unittest.TestCase):
    def test_profit_basic(self):
        # SRS: Profit = final sale price - purchase cost for sold quantity
        self.assertEqual(br.calculate_profit(90000, 70000, quantity=1), Decimal("20000"))

    def test_profit_multi_quantity(self):
        self.assertEqual(br.calculate_profit(200000, 70000, quantity=2), Decimal("60000"))

    def test_profit_can_be_negative(self):
        self.assertEqual(br.calculate_profit(50000, 70000), Decimal("-20000"))


class InventoryTests(unittest.TestCase):
    def test_stock_reduces_on_sale(self):
        self.assertEqual(br.apply_sale_to_stock(5, 1), 4)

    def test_cannot_oversell(self):
        with self.assertRaises(br.BusinessRuleError):
            br.apply_sale_to_stock(1, 2)

    def test_stock_never_negative(self):
        with self.assertRaises(br.BusinessRuleError):
            br.apply_sale_to_stock(0, 1)

    def test_low_stock_threshold(self):
        # SRS: alert when quantity < 2  -> 0 and 1 are low stock, 2 is not
        self.assertTrue(br.is_low_stock(0))
        self.assertTrue(br.is_low_stock(1))
        self.assertFalse(br.is_low_stock(2))

    def test_out_of_stock(self):
        self.assertTrue(br.is_out_of_stock(0))
        self.assertFalse(br.is_out_of_stock(1))


class CreditPlanTests(unittest.TestCase):
    def test_remaining_balance_basic(self):
        self.assertEqual(br.calculate_remaining(80000, [20000, 30000]), Decimal("30000"))

    def test_remaining_never_negative(self):
        with self.assertRaises(br.BusinessRuleError):
            br.calculate_remaining(80000, [50000, 50000])

    def test_payment_greater_than_remaining_rejected(self):
        # SRS 4.9 / 17: "Payment amount cannot be greater than the remaining amount."
        with self.assertRaises(br.BusinessRuleError):
            br.validate_new_payment(80000, [70000], 20000)

    def test_valid_payment_reduces_remaining(self):
        new_remaining = br.validate_new_payment(80000, [20000], 30000)
        self.assertEqual(new_remaining, Decimal("30000"))

    def test_cleared_plan_rejects_further_payment(self):
        # SRS acceptance criteria #53: 80,000 fully received -> CLEARED, remaining Rs 0
        with self.assertRaises(br.BusinessRuleError):
            br.validate_new_payment(80000, [80000], 1000)

    def test_status_becomes_cleared_when_fully_paid(self):
        # SRS acceptance criteria #53
        status = br.credit_plan_status(80000, [30000, 50000])
        self.assertEqual(status, br.CLEARED)
        self.assertEqual(br.calculate_remaining(80000, [30000, 50000]), Decimal("0"))

    def test_status_active_when_partially_paid(self):
        self.assertEqual(br.credit_plan_status(80000, [30000]), br.ACTIVE)

    def test_reminder_two_days_before_due(self):
        due = date.today() + timedelta(days=2)
        self.assertTrue(br.reminder_due(due, br.ACTIVE, as_of=date.today()))
        self.assertFalse(br.reminder_due(due, br.ACTIVE, as_of=date.today() + timedelta(days=1)))

    def test_reminder_stops_after_clearance(self):
        due = date.today() + timedelta(days=2)
        self.assertFalse(br.reminder_due(due, br.CLEARED, as_of=date.today()))

    def test_overdue_detection(self):
        due = date.today() - timedelta(days=1)
        self.assertTrue(br.is_overdue(due, br.ACTIVE))

    def test_overdue_false_once_cleared(self):
        due = date.today() - timedelta(days=5)
        self.assertFalse(br.is_overdue(due, br.CLEARED))

    def test_not_overdue_before_due_date(self):
        due = date.today() + timedelta(days=3)
        self.assertFalse(br.is_overdue(due, br.ACTIVE))


class ReceiptNumberTests(unittest.TestCase):
    def test_format_padding(self):
        self.assertEqual(br.format_receipt_number(1), "00001")
        self.assertEqual(br.format_receipt_number(25), "00025")
        self.assertEqual(br.format_receipt_number(99999), "99999")

    def test_sequence_increments(self):
        self.assertEqual(br.next_receipt_sequence(24), 25)

    def test_sequence_cap(self):
        with self.assertRaises(br.BusinessRuleError):
            br.next_receipt_sequence(99999)

    def test_sequence_lower_bound(self):
        with self.assertRaises(br.BusinessRuleError):
            br.format_receipt_number(0)


class SaleCalculationTests(unittest.TestCase):
    def test_end_to_end_sale_math(self):
        calc = br.SaleCalculation(
            sale_price=120000,
            discount_amount=5000,
            purchase_cost_snapshot=90000,
            quantity=1,
        )
        self.assertEqual(calc.final_price, Decimal("115000"))
        self.assertEqual(calc.profit, Decimal("25000"))


class ShopkeeperFifoAllocationTests(unittest.TestCase):
    """A shopkeeper's payment is recorded once against their combined
    total, but each laptop still needs to show its own remaining balance
    -- allocated oldest-laptop-first."""

    def test_first_laptop_fully_cleared_by_payment(self):
        balances = br.allocate_payments_fifo([50000, 40000], 60000)
        self.assertEqual(balances, [Decimal("0"), Decimal("30000")])

    def test_no_payment_yet_full_balances_owed(self):
        balances = br.allocate_payments_fifo([50000, 40000], 0)
        self.assertEqual(balances, [Decimal("50000"), Decimal("40000")])

    def test_payment_clears_everything(self):
        balances = br.allocate_payments_fifo([50000, 40000], 90000)
        self.assertEqual(balances, [Decimal("0"), Decimal("0")])

    def test_overpayment_pool_does_not_go_negative(self):
        balances = br.allocate_payments_fifo([50000, 40000], 999999)
        self.assertEqual(balances, [Decimal("0"), Decimal("0")])

    def test_single_laptop(self):
        balances = br.allocate_payments_fifo([25000], 10000)
        self.assertEqual(balances, [Decimal("15000")])

    def test_negative_total_paid_rejected(self):
        with self.assertRaises(br.BusinessRuleError):
            br.allocate_payments_fifo([50000], -1)


if __name__ == "__main__":
    unittest.main()
