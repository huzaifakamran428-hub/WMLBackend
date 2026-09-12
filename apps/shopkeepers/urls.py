from rest_framework.routers import DefaultRouter
from apps.shopkeepers.views import ShopkeeperViewSet

router = DefaultRouter()
router.register("", ShopkeeperViewSet, basename="shopkeeper")
urlpatterns = router.urls
