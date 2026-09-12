from rest_framework import serializers
from django.db import transaction
from django.utils import timezone

from apps.credit.models import CreditPlan, Payment
from apps.core.business_rules import calculate_remaining, validate_new_payment, BusinessRuleError
from apps.audit.utils import write_audit_log


class CreditPlanSerializer(serializers.ModelSerializer):
    total_received = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    remaining_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    person_name = serializers.SerializerMethodField()

    class Meta:
        model = CreditPlan
        fields = [
            "id", "shopkeeper", "customer", "person_name", "laptop", "sale",
            "total_amount", "down_payment", "installment_amount", "due_date",
            "status", "cleared_at", "notes", "total_received", "remaining_amount",
            "is_overdue", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "cleared_at", "created_at", "updated_at"]

    def get_person_name(self, obj):
        return str(obj.person) if obj.person else None

    def validate(self, attrs):
        shopkeeper = attrs.get("shopkeeper", getattr(self.instance, "shopkeeper", None))
        customer = attrs.get("customer", getattr(self.instance, "customer", None))
        if bool(shopkeeper) == bool(customer):
            raise serializers.ValidationError(
                "A credit plan must be linked to exactly one shopkeeper OR one customer."
            )
        total_amount = attrs.get("total_amount", getattr(self.instance, "total_amount", None))
        down_payment = attrs.get("down_payment", getattr(self.instance, "down_payment", 0))
        try:
            calculate_remaining(total_amount, [down_payment])
        except BusinessRuleError as exc:
            raise serializers.ValidationError({"down_payment": str(exc)})
        return attrs

    def create(self, validated_data):
        plan = CreditPlan.objects.create(created_by=self.context["request"].user, **validated_data)
        write_audit_log(self.context["request"].user, "CREATE_CREDIT_PLAN", "CreditPlan", plan.id)
        return plan


class PaymentSerializer(serializers.ModelSerializer):
    """SRS 4.9 (Add Payment (+) action), 4.10 (clearance), 11."""
    class Meta:
        model = Payment
        fields = ["id", "credit_plan", "amount", "payment_date", "method", "note", "recorded_by"]
        read_only_fields = ["id", "payment_date", "recorded_by"]

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        plan = CreditPlan.objects.select_for_update().get(pk=validated_data["credit_plan"].pk)

        existing_amounts = list(plan.payments.values_list("amount", flat=True)) + [plan.down_payment]
        try:
            new_remaining = validate_new_payment(plan.total_amount, existing_amounts, validated_data["amount"])
        except BusinessRuleError as exc:
            raise serializers.ValidationError(str(exc))

        payment = Payment.objects.create(recorded_by=request.user, **validated_data)

        if new_remaining == 0:
            # SRS 4.10: status automatically becomes CLEARED / PAID IN FULL;
            # Add Payment must disappear; reminders stop automatically.
            plan.status = CreditPlan.CLEARED
            plan.cleared_at = timezone.now()
            plan.save(update_fields=["status", "cleared_at"])

        write_audit_log(request.user, "ADD_PAYMENT", "CreditPlan", plan.id, {"amount": str(validated_data["amount"])})
        return payment
