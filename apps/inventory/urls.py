from rest_framework.routers import DefaultRouter
from django.urls import path, include
from apps.inventory.views import LaptopViewSet, InventoryMovementListView

router = DefaultRouter()
router.register("", LaptopViewSet, basename="laptop")

urlpatterns = [
    path("movements/", InventoryMovementListView.as_view(), name="inventory-movements"),
    path("", include(router.urls)),
]
