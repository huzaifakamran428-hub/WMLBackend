from rest_framework.routers import DefaultRouter
from apps.shopkeepers.views import ShopkeeperPaymentViewSet

router = DefaultRouter()
router.register("", ShopkeeperPaymentViewSet, basename="shopkeeper-payment")
urlpatterns = router.urls
