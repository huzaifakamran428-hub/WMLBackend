from django.contrib import admin
from apps.audit.models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["timestamp", "user", "action", "entity", "entity_id"]
    list_filter = ["entity", "action"]
    search_fields = ["entity", "entity_id", "action"]
