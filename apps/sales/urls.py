from rest_framework.routers import DefaultRouter
from django.urls import path, include
from apps.sales.views import SaleViewSet, ReceiptSearchView

router = DefaultRouter()
router.register("", SaleViewSet, basename="sale")

urlpatterns = [
    path("receipt/<str:receipt_no>/", ReceiptSearchView.as_view(), name="receipt-search"),
    path("", include(router.urls)),
]
