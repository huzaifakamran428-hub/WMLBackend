"""
SRS Section 2 (User Types and Access Control), Section 4.1 (Authentication
and User Management), Section 7 ('User: id, name, email, role, active,
created_at').
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ADMIN = "ADMIN"
    READ_ONLY = "READ_ONLY"
    SHOPKEEPER = "SHOPKEEPER"
    ROLE_CHOICES = [
        (ADMIN, "Admin"),
        (READ_ONLY, "Read-Only User"),
        (SHOPKEEPER, "Shopkeeper (limited, own account only)"),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=READ_ONLY)
    phone_number = models.CharField(max_length=30, blank=True, default="")

    # Admin-created shopkeeper login: links this account to the one
    # Shopkeeper record it's allowed to view (own laptops/payments/balance
    # only). Null for ADMIN / READ_ONLY users.
    shopkeeper = models.OneToOneField(
        "shopkeepers.Shopkeeper", on_delete=models.CASCADE,
        null=True, blank=True, related_name="user_account",
    )

    # SRS 4.1: Google / Apple Sign-In identifiers
    google_sub = models.CharField(max_length=255, blank=True, null=True, unique=True)
    apple_sub = models.CharField(max_length=255, blank=True, null=True, unique=True)

    # SRS 4.11: push notification device tokens are stored per-user via
    # notifications.DeviceToken (kept in a separate app/table).

    # SRS 13 ("session should expire after a period of inactivity"): JWT
    # access tokens alone don't cover this -- a client can silently
    # refresh forever without the *user* ever touching the app. This is
    # stamped on every authenticated request by
    # apps.core.authentication.InactivityAwareJWTAuthentication and
    # checked against settings.SESSION_INACTIVITY_TIMEOUT_MINUTES.
    last_activity = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.role})"

    @property
    def is_admin(self):
        return self.role == self.ADMIN

    def save(self, *args, **kwargs):
        # A Django superuser (created via `createsuperuser` or the admin
        # site) must always carry the app-level ADMIN role too, otherwise
        # DRF's IsAdmin/IsAdminOrReadOnly permission checks (which look at
        # `role`, not `is_superuser`) would lock the first admin account
        # out of admin-only endpoints like /api/users/ and /api/audit-logs/.
        if self.is_superuser:
            self.role = self.ADMIN
        super().save(*args, **kwargs)
