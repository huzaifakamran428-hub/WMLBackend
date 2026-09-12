"""SRS 9 (Reports module), 4.12, 4.13, 16."""
from rest_framework.views import APIView
from rest_framework.response import Response
from apps.core.permissions import IsAdmin  # export restricted to authorized users (SRS 13/16)
from apps.reports import services


class BaseReportView(APIView):
    permission_classes = [IsAdmin]
    service_fn = None

    def get(self, request):
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        try:
            data = self.service_fn(date_from, date_to)
        except TypeError:
            data = self.service_fn()
        return Response(data)


class SalesReportView(BaseReportView):
    service_fn = staticmethod(services.sales_report)


class ProfitReportView(BaseReportView):
    service_fn = staticmethod(services.profit_report)


class InventoryReportView(BaseReportView):
    service_fn = staticmethod(services.inventory_report)


class InvestmentReportView(BaseReportView):
    service_fn = staticmethod(services.investment_report)


class OutstandingReportView(BaseReportView):
    service_fn = staticmethod(services.outstanding_report)


class PaymentsReportView(BaseReportView):
    service_fn = staticmethod(services.payments_report)
