"""SRS 9 (Credit Plans / Payments modules), 4.10 (cleared filter), 6."""
from rest_framework import viewsets
from django_filters import rest_framework as django_filters

from apps.credit.models import CreditPlan, Payment
from apps.credit.serializers import CreditPlanSerializer, PaymentSerializer
from apps.core.permissions import IsAdminOrReadOnly


class CreditPlanFilter(django_filters.FilterSet):
    class Meta:
        model = CreditPlan
        fields = ["status", "shopkeeper", "customer"]


class CreditPlanViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "head", "options"]  # never hard-delete a financial record
    queryset = CreditPlan.objects.select_related("shopkeeper", "customer", "laptop").prefetch_related("payments")
    serializer_class = CreditPlanSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_class = CreditPlanFilter
    search_fields = ["shopkeeper__name", "customer__name", "laptop__brand", "laptop__model_name"]
    ordering_fields = ["due_date", "created_at", "total_amount"]


class PaymentViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "head", "options"]  # payments are immutable once recorded (SRS 11)
    queryset = Payment.objects.select_related("credit_plan")
    serializer_class = PaymentSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_fields = ["credit_plan", "method"]
    ordering_fields = ["payment_date"]
