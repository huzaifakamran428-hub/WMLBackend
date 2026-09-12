from rest_framework.routers import DefaultRouter
from apps.credit.views import CreditPlanViewSet

router = DefaultRouter()
router.register("", CreditPlanViewSet, basename="credit-plan")
urlpatterns = router.urls
