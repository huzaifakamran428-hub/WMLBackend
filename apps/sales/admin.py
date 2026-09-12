from django.contrib import admin
from apps.sales.models import Sale, SaleItem, ReceiptSequence

class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ["receipt_no", "customer", "final_total", "payment_status", "sale_date"]
    search_fields = ["receipt_no", "customer__name", "customer__phone"]
    inlines = [SaleItemInline]

admin.site.register(ReceiptSequence)
