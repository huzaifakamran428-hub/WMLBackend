from django.urls import path
from apps.accounts.auth_views import LoginView, GoogleLoginView, AppleLoginView, LogoutView

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("google/", GoogleLoginView.as_view(), name="auth-google"),
    path("apple/", AppleLoginView.as_view(), name="auth-apple"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
]
