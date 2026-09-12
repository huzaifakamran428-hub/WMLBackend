from django.urls import path
from apps.notifications.views import NotificationListView, MarkNotificationReadView

urlpatterns = [
    path("", NotificationListView.as_view(), name="notification-list"),
    path("<int:pk>/read/", MarkNotificationReadView.as_view(), name="notification-read"),
]
