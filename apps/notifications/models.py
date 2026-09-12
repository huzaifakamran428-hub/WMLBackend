"""SRS 4.11 (Installment Notifications), 4.2 (Dashboard alerts), 7
(Notification entity), 10 (Notification Requirements)."""
from django.conf import settings
from django.db import models


class Notification(models.Model):
    LOW_STOCK = "LOW_STOCK"
    UPCOMING_PAYMENT = "UPCOMING_PAYMENT"
    PAYMENT_DUE = "PAYMENT_DUE"
    OVERDUE = "OVERDUE"
    SALE = "SALE"
    TYPE_CHOICES = [
        (LOW_STOCK, "Low Stock"), (UPCOMING_PAYMENT, "Upcoming Payment"),
        (PAYMENT_DUE, "Payment Due"), (OVERDUE, "Overdue"), (SALE, "Sale"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title = models.CharField(max_length=150)
    message = models.CharField(max_length=300)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.type}] {self.title}"


class DeviceToken(models.Model):
    """SRS 4.11: 'Swift registers for APNs permission and device token;
    backend stores device tokens.'"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="device_tokens")
    token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=20, default="ios")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.token[:12]}..."
