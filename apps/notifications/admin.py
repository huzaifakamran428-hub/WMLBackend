from django.contrib import admin
from apps.notifications.models import Notification, DeviceToken

admin.site.register(Notification)
admin.site.register(DeviceToken)
