"""
SRS 4.12 (Profit and Sales Reports), 4.13 (Reports and Admin Panel),
16 (Reporting Requirements). Pure query/aggregation functions — kept out
of views.py so they're independently testable.
"""
from decimal import Decimal
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from django.utils import timezone

from apps.sales.models import Sale, SaleItem
from apps.inventory.models import Laptop
from apps.credit.models import CreditPlan
from apps.shopkeepers.models import Shopkeeper
from apps.core.business_rules import BusinessRuleError


def sales_report(date_from=None, date_to=None):
    qs = Sale.objects.all()
    if date_from:
        qs = qs.filter(sale_date__date__gte=date_from)
    if date_to:
        qs = qs.filter(sale_date__date__lte=date_to)
    totals = qs.aggregate(total_sales=Sum("final_total"))
    return {
        "count": qs.count(),
        "total_sales": totals["total_sales"] or Decimal("0"),
        "sales": qs.values("id", "receipt_no", "customer__name", "final_total", "sale_date"),
    }


def profit_report(date_from=None, date_to=None):
    qs = SaleItem.objects.select_related("sale", "product")
    if date_from:
        qs = qs.filter(sale__sale_date__date__gte=date_from)
    if date_to:
        qs = qs.filter(sale__sale_date__date__lte=date_to)

    line_profit = ExpressionWrapper(
        (F("sale_price") - F("purchase_cost_snapshot") * F("quantity")),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    qs = qs.annotate(profit=line_profit)
    total_profit = qs.aggregate(total=Sum("profit"))["total"] or Decimal("0")
    return {
        "total_profit": total_profit,
        "items": qs.values(
            "id", "sale__receipt_no", "product__brand", "product__model_name",
            "sale_price", "purchase_cost_snapshot", "quantity", "profit",
        ),
    }


def investment_report():
    """SRS 4.12/16: money spent purchasing laptops currently in inventory."""
    qs = Laptop.objects.filter(is_archived=False)
    total = qs.aggregate(total=Sum(F("purchase_price") * F("quantity"), output_field=DecimalField(max_digits=14, decimal_places=2)))
    return {"total_investment": total["total"] or Decimal("0"), "laptops": qs.count()}


def inventory_report():
    """SRS 16: current stock, stock value, low-stock items."""
    from django.conf import settings
    qs = Laptop.objects.filter(is_archived=False)
    value = qs.aggregate(total=Sum(F("purchase_price") * F("quantity"), output_field=DecimalField(max_digits=14, decimal_places=2)))
    low_stock = qs.filter(quantity__lt=settings.LOW_STOCK_THRESHOLD, quantity__gt=0)
    out_of_stock = qs.filter(quantity=0)
    return {
        "total_stock_value": value["total"] or Decimal("0"),
        "total_units": qs.aggregate(u=Sum("quantity"))["u"] or 0,
        "low_stock_count": low_stock.count(),
        "out_of_stock_count": out_of_stock.count(),
        "low_stock_items": low_stock.values("id", "brand", "model_name", "quantity"),
    }


def outstanding_report():
    """SRS 4.12/16: unpaid/remaining customer or shopkeeper balances.

    Customer installment sales still use CreditPlan (one plan per laptop
    sold from inventory). Shopkeepers now use their own running account
    (one Shopkeeper record, many manually-entered laptops, one combined
    balance) so they're reported separately below.
    """
    plans = CreditPlan.objects.filter(status=CreditPlan.ACTIVE).select_related("shopkeeper", "customer")
    rows = []
    total_outstanding = Decimal("0")
    for plan in plans:
        remaining = plan.remaining_amount
        total_outstanding += remaining
        rows.append({
            "id": plan.id, "person": str(plan.person), "remaining_amount": remaining,
            "due_date": plan.due_date, "is_overdue": plan.is_overdue,
        })

    shopkeeper_rows = []
    # `status` is a computed property, not a database field, so it can't be
    # filtered in the queryset -- pull every shopkeeper and check remaining
    # balance in Python instead. Also guards against any shopkeeper whose
    # payments currently exceed their laptop total (e.g. from a laptop item
    # being removed after a payment was made) so one bad account can't take
    # the whole report down.
    for sk in Shopkeeper.objects.all().prefetch_related("laptops", "payments"):
        try:
            remaining = sk.remaining_amount
        except BusinessRuleError:
            continue
        if remaining <= 0:
            continue
        total_outstanding += remaining
        shopkeeper_rows.append({
            "id": sk.id, "reference_number": sk.reference_number, "person": sk.name,
            "remaining_amount": remaining, "laptop_count": sk.laptops.count(),
        })

    return {"total_outstanding": total_outstanding, "plans": rows, "shopkeepers": shopkeeper_rows}


def payments_report(date_from=None, date_to=None):
    """SRS 16: payment history by person/date. Covers customer installment
    payments (against a CreditPlan) and shopkeeper payments (against their
    combined running account) side by side."""
    from apps.credit.models import Payment
    from apps.shopkeepers.models import ShopkeeperPayment

    qs = Payment.objects.select_related("credit_plan", "credit_plan__shopkeeper", "credit_plan__customer")
    sk_qs = ShopkeeperPayment.objects.select_related("shopkeeper")
    if date_from:
        qs = qs.filter(payment_date__gte=date_from)
        sk_qs = sk_qs.filter(payment_date__gte=date_from)
    if date_to:
        qs = qs.filter(payment_date__lte=date_to)
        sk_qs = sk_qs.filter(payment_date__lte=date_to)

    total = qs.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    sk_total = sk_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return {
        "total_received": total + sk_total,
        "payments": qs.values(
            "id", "credit_plan_id", "amount", "payment_date", "method",
        ),
        "shopkeeper_payments": sk_qs.values(
            "id", "shopkeeper_id", "shopkeeper__name", "amount", "payment_date", "method",
        ),
    }
