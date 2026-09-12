from rest_framework.routers import DefaultRouter
from apps.notifications.views import DeviceTokenViewSet

router = DefaultRouter()
router.register("", DeviceTokenViewSet, basename="device-token")
urlpatterns = router.urls
