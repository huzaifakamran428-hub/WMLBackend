from apps.audit.models import AuditLog


def write_audit_log(user, action, entity, entity_id, detail=None):
    """Central helper used by every app that mutates financial or
    security-sensitive data (SRS 4.9 / 4.13 / 11 / 18)."""
    AuditLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        detail=detail or {},
    )
