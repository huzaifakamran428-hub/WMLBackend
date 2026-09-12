"""
SRS 4.1 Authentication:
- Login using email and password.
- Login with Google.
- Login with Apple.
- Secure logout.
- Handle token expiry/refresh and session expiration without crashing.
- Display clear authentication errors.

Google/Apple flows verify the provider ID token server-side (never trust
a client-asserted identity) then issue our own JWT pair, matching SRS 13
('Use secure Apple/Google authentication flows').
"""
from django.contrib.auth import authenticate, get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.serializers import LoginSerializer, UserSerializer
from apps.audit.utils import write_audit_log

User = get_user_model()


def _issue_tokens(user):
    # Stamp last_activity at the moment of login too, not just on
    # authenticated requests. Without this, InactivityAwareJWTAuthentication
    # can deadlock: it only refreshes last_activity *after* a request passes
    # its own staleness check, so once last_activity goes stale (which it
    # always eventually will) every future request -- including ones right
    # after a brand-new login -- gets rejected, with no path back to a
    # fresh timestamp. A successful login is exactly the right place to
    # reset the clock, since it doesn't (and shouldn't) go through that
    # check itself.
    type(user).objects.filter(pk=user.pk).update(last_activity=timezone.now())
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class LoginView(APIView):
    """POST /api/auth/login/"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            # SRS 17: clear, non-technical authentication error
            return Response({"detail": "Invalid username or password."}, status=status.HTTP_401_UNAUTHORIZED)
        if not user.is_active:
            return Response({"detail": "This account has been deactivated. Contact the admin."}, status=status.HTTP_403_FORBIDDEN)

        tokens = _issue_tokens(user)
        write_audit_log(user, "LOGIN", "User", user.id)
        return Response({**tokens, "user": UserSerializer(user).data})


class GoogleLoginView(APIView):
    """POST /api/auth/google/ — body: {"id_token": "..."}"""
    permission_classes = [AllowAny]

    def post(self, request):
        id_token_str = request.data.get("id_token")
        if not id_token_str:
            return Response({"detail": "id_token is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            claims = self._verify_google_token(id_token_str)
        except Exception:
            return Response({"detail": "Google sign-in could not be verified."}, status=status.HTTP_401_UNAUTHORIZED)

        user, _ = User.objects.get_or_create(
            google_sub=claims["sub"],
            defaults={"username": claims["email"], "email": claims["email"], "role": User.READ_ONLY},
        )
        if not user.is_active:
            return Response({"detail": "This account has been deactivated. Contact the admin."}, status=status.HTTP_403_FORBIDDEN)
        tokens = _issue_tokens(user)
        write_audit_log(user, "LOGIN_GOOGLE", "User", user.id)
        return Response({**tokens, "user": UserSerializer(user).data})

    def _verify_google_token(self, id_token_str):
        """Verify against Google's public keys. Wire up
        google-auth's `google.oauth2.id_token.verify_oauth2_token` with
        settings.GOOGLE_OAUTH_CLIENT_ID here in production."""
        from google.oauth2 import id_token as google_id_token  # noqa
        from google.auth.transport import requests as google_requests  # noqa
        import os
        return google_id_token.verify_oauth2_token(
            id_token_str, google_requests.Request(), os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
        )


class AppleLoginView(APIView):
    """POST /api/auth/apple/ — body: {"identity_token": "..."}"""
    permission_classes = [AllowAny]

    def post(self, request):
        identity_token = request.data.get("identity_token")
        if not identity_token:
            return Response({"detail": "identity_token is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            claims = self._verify_apple_token(identity_token)
        except Exception:
            return Response({"detail": "Apple sign-in could not be verified."}, status=status.HTTP_401_UNAUTHORIZED)

        email = claims.get("email", f"{claims['sub']}@privaterelay.appleid.com")
        user, _ = User.objects.get_or_create(
            apple_sub=claims["sub"], defaults={"username": email, "email": email, "role": User.READ_ONLY},
        )
        if not user.is_active:
            return Response({"detail": "This account has been deactivated. Contact the admin."}, status=status.HTTP_403_FORBIDDEN)
        tokens = _issue_tokens(user)
        write_audit_log(user, "LOGIN_APPLE", "User", user.id)
        return Response({**tokens, "user": UserSerializer(user).data})

    def _verify_apple_token(self, identity_token):
        """Verify the Apple identity token signature/audience/issuer against
        Apple's public keys (see 'sign in with apple' JWKS) before trusting
        any claims. Implement with a library such as `python-jose` +
        Apple's JWKS endpoint, using settings.APPLE_SIGNIN_CLIENT_ID."""
        raise NotImplementedError("Wire up Apple JWKS verification for production.")


class LogoutView(APIView):
    """POST /api/auth/logout/ — blacklists the refresh token (SRS 4.1:
    'Secure logout')."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except Exception:
                pass
        write_audit_log(request.user, "LOGOUT", "User", request.user.id)
        return Response({"detail": "Logged out."})
