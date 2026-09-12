"""SRS 4.13 / 19: Store settings (Store name, address, phone and logo
management), shared TimeStamped base model."""
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class StoreSettings(TimeStampedModel):
    """Singleton-style settings row (SRS 4.13, 5 'StoreProfileViewController',
    15 'Professional Bill Specification')."""
    store_name = models.CharField(max_length=200, default="Waqare Medina Computers and Laptop")
    address = models.CharField(max_length=300, default="PF Road, Waqare Medina, Mianwali, Pakistan")
    phone_number = models.CharField(max_length=30, blank=True, default="")
    # Owner request: every generated bill should also show the CEO's name
    # and contact number, editable here like the rest of the store profile.
    ceo_name = models.CharField(max_length=150, blank=True, default="Yasir")
    ceo_contact_number = models.CharField(max_length=30, blank=True, default="03288621265")
    logo = models.ImageField(upload_to="store/", blank=True, null=True)
    thank_you_message = models.CharField(max_length=200, blank=True, default="Thank you for your business!")

    # SRS 4.11: notification preferences
    low_stock_alerts_enabled = models.BooleanField(default=True)
    due_today_reminder_enabled = models.BooleanField(default=True)
    two_day_reminder_enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.store_name

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
