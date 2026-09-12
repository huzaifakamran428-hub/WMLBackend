from rest_framework.routers import DefaultRouter
from apps.accounts.views import UserViewSet

router = DefaultRouter()
router.register("", UserViewSet, basename="user")
urlpatterns = router.urls
