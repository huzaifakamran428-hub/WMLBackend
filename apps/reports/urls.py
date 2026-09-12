from django.urls import path
from apps.reports.views import (
    SalesReportView, ProfitReportView, InventoryReportView,
    InvestmentReportView, OutstandingReportView, PaymentsReportView,
)

urlpatterns = [
    path("sales/", SalesReportView.as_view(), name="report-sales"),
    path("profit/", ProfitReportView.as_view(), name="report-profit"),
    path("inventory/", InventoryReportView.as_view(), name="report-inventory"),
    path("investment/", InvestmentReportView.as_view(), name="report-investment"),
    path("outstanding/", OutstandingReportView.as_view(), name="report-outstanding"),
    path("payments/", PaymentsReportView.as_view(), name="report-payments"),
]
