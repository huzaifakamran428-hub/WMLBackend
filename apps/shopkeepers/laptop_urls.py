from rest_framework.routers import DefaultRouter
from apps.shopkeepers.views import ShopkeeperLaptopItemViewSet

router = DefaultRouter()
router.register("", ShopkeeperLaptopItemViewSet, basename="shopkeeper-laptop")
urlpatterns = router.urls
