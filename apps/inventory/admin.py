from django.contrib import admin
from apps.inventory.models import Laptop, InventoryMovement

@admin.register(Laptop)
class LaptopAdmin(admin.ModelAdmin):
    list_display = ["brand", "model_name", "condition", "quantity", "sale_price", "is_archived"]
    list_filter = ["condition", "brand", "is_archived"]
    search_fields = ["brand", "model_name", "serial_number", "processor"]

@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = ["date", "product", "type", "quantity", "reference_id"]
    list_filter = ["type"]
