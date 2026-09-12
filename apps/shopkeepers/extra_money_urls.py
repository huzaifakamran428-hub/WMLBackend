from rest_framework.routers import DefaultRouter
from apps.shopkeepers.views import ShopkeeperExtraMoneyViewSet

router = DefaultRouter()
router.register("", ShopkeeperExtraMoneyViewSet, basename="shopkeeper-extra-money")
urlpatterns = router.urls
