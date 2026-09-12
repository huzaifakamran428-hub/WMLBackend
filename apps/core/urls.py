from django.urls import path
from apps.core.views import StoreSettingsView

urlpatterns = [
    path("", StoreSettingsView.as_view(), name="store-settings"),
]
