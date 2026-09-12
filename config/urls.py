"""SRS Section 9: REST API Modules — top level router."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path("admin/", admin.site.urls),

    path("api/auth/", include("apps.accounts.auth_urls")),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    path("api/users/", include("apps.accounts.urls")),
    path("api/laptops/", include("apps.inventory.urls")),
    path("api/customers/", include("apps.customers.urls")),
    path("api/shopkeepers/", include("apps.shopkeepers.urls")),
    path("api/shopkeeper-laptops/", include("apps.shopkeepers.laptop_urls")),
    path("api/shopkeeper-payments/", include("apps.shopkeepers.payment_urls")),
    path("api/shopkeeper-extra-money/", include("apps.shopkeepers.extra_money_urls")),
    path("api/sales/", include("apps.sales.urls")),
    path("api/credit-plans/", include("apps.credit.urls")),
    path("api/payments/", include("apps.credit.payment_urls")),
    path("api/notifications/", include("apps.notifications.urls")),
    path("api/device-tokens/", include("apps.notifications.device_urls")),
    path("api/reports/", include("apps.reports.urls")),
    path("api/store-settings/", include("apps.core.urls")),
    path("api/audit-logs/", include("apps.audit.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
