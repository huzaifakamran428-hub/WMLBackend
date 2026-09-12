"""SRS 4.7 (Separate Customer section), 7 (Customer entity)."""
from apps.core.models import TimeStampedModel
from django.db import models


class Customer(TimeStampedModel):
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    address = models.CharField(max_length=250, blank=True, default="")
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["name", "phone"])]

    def __str__(self):
        return f"{self.name} ({self.phone})"
