from django.contrib import admin
from apps.shopkeepers.models import Shopkeeper, ShopkeeperLaptopItem, ShopkeeperExtraMoney, ShopkeeperPayment


class ShopkeeperLaptopItemInline(admin.TabularInline):
    model = ShopkeeperLaptopItem
    extra = 0
    readonly_fields = ["item_reference", "added_at"]


class ShopkeeperExtraMoneyInline(admin.TabularInline):
    model = ShopkeeperExtraMoney
    extra = 0
    readonly_fields = ["item_reference", "added_at"]


class ShopkeeperPaymentInline(admin.TabularInline):
    model = ShopkeeperPayment
    extra = 0
    readonly_fields = ["payment_date"]


@admin.register(Shopkeeper)
class ShopkeeperAdmin(admin.ModelAdmin):
    list_display = ["reference_number", "name", "phone", "total_amount", "remaining_amount", "status", "created_at"]
    search_fields = ["name", "phone", "reference_number"]
    readonly_fields = ["reference_number"]
    inlines = [ShopkeeperLaptopItemInline, ShopkeeperExtraMoneyInline, ShopkeeperPaymentInline]
