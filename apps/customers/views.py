"""SRS 9 (Customers module), 4.7 / 6.1 (customer search)."""
from rest_framework import viewsets
from apps.customers.models import Customer
from apps.customers.serializers import CustomerSerializer
from apps.core.permissions import IsAdminOrReadOnly
from apps.audit.utils import write_audit_log


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ["name", "phone"]  # combined with sales search for laptop/receipt (see apps.sales)
    ordering_fields = ["name", "created_at"]

    def perform_create(self, serializer):
        obj = serializer.save()
        write_audit_log(self.request.user, "CREATE_CUSTOMER", "Customer", obj.id)

    def perform_update(self, serializer):
        obj = serializer.save()
        write_audit_log(self.request.user, "UPDATE_CUSTOMER", "Customer", obj.id)
