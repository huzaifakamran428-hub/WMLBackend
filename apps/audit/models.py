"""SRS 4.9 ('Every correction to a financial record must create an audit
record'), 4.13, 7 ('Audit Log: id, user_id, action, entity, entity_id,
timestamp'), 11, 18."""
from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="audit_logs")
    action = models.CharField(max_length=100)
    entity = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=50, blank=True, default="")
    detail = models.JSONField(blank=True, default=dict)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["entity", "entity_id"])]

    def __str__(self):
        return f"{self.timestamp} {self.user} {self.action} {self.entity}#{self.entity_id}"
