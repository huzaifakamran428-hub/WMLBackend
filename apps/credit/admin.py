from django.contrib import admin
from apps.credit.models import CreditPlan, Payment

class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0

@admin.register(CreditPlan)
class CreditPlanAdmin(admin.ModelAdmin):
    list_display = ["id", "person", "laptop", "total_amount", "status", "due_date"]
    list_filter = ["status"]
    inlines = [PaymentInline]

admin.site.register(Payment)
