"""
SRS Section 13 (Security): "the session should expire after a period of
inactivity."

A plain Django *middleware* can't implement this by itself: JWT auth
(rest_framework_simplejwt) only populates `request.user` inside DRF's own
request cycle (APIView.initial(), which runs authentication classes), which
happens *after* Django's middleware stack has already finished. A
middleware sitting in MIDDLEWARE would see an anonymous request.user and
could never check or update an activity timestamp.

So this lives at the same layer as authentication itself: it wraps the
normal JWTAuthentication, and on every authenticated request it (a) checks
how long it's been since the user's last request and rejects with 401 if
that exceeds the configured idle timeout, then (b) stamps "now" as the new
last_activity. A *valid, unexpired* access token is no longer enough on
its own -- the user also has to have been actually using the app recently.
"""
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class InactivityAwareJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None  # no token on this request at all (e.g. login) -- nothing to check

        user, validated_token = result

        timeout_minutes = getattr(settings, "SESSION_INACTIVITY_TIMEOUT_MINUTES", 30)
        now = timezone.now()

        if user.last_activity is not None:
            idle_for = now - user.last_activity
            if idle_for.total_seconds() > timeout_minutes * 60:
                # Don't silently let this slide -- force a real re-login,
                # same as an expired/invalid token, so the client's
                # existing 401 handling (refresh-then-retry, and failing
                # that, sign the user out) takes over unchanged.
                raise AuthenticationFailed(
                    "Your session has expired due to inactivity. Please log in again.",
                    code="session_inactive",
                )

        # Cheap, best-effort stamp -- update_fields keeps this to a single
        # narrow UPDATE rather than a full row save on every request.
        type(user).objects.filter(pk=user.pk).update(last_activity=now)
        user.last_activity = now

        return user, validated_token
