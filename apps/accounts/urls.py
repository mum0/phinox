"""apps.accounts — URL config (Phase 5 + BUGFIX-ROUND-2 + REGISTER-FIX + GOOGLE-OAUTH-MANUAL).

URL names:
  Auth (real):
    - ``accounts:login``                → /accounts/login/
    - ``accounts:register``             → /accounts/register/
    - ``accounts:register_done``        → /accounts/register/done/      [REGISTER-FIX]
    - ``accounts:logout``               → /accounts/logout/  (POST-only)
    - ``accounts:verify``              → /accounts/verify/<token>/  (email verification)
    - ``accounts:google_login``        → /accounts/google/login/      [GOOGLE-OAUTH]
    - ``accounts:google_callback``    → /accounts/google/callback/   [GOOGLE-OAUTH]
    - ``accounts:password_reset``       → /accounts/password/reset/
    - ``accounts:password_reset_done``  → /accounts/password/reset/done/
    - ``accounts:password_reset_confirm`` → /accounts/password/reset/confirm/<uidb64>/<token>/
    - ``accounts:password_reset_complete`` → /accounts/password/reset/complete/

  Profile + Addresses:
    - ``accounts:profile``           → /accounts/profile/
    - ``accounts:addresses``         → /accounts/addresses/
    - ``accounts:address_create``    → /accounts/addresses/new/
    - ``accounts:address_update``    → /accounts/addresses/<pk>/edit/
    - ``accounts:address_delete``    → /accounts/addresses/<pk>/delete/
    - ``accounts:address_set_default`` → /accounts/addresses/<pk>/default/

BUGFIX-ROUND-2: Replaced PhoneReset views with Django built-in
PasswordResetView / PasswordResetDoneView / PasswordResetConfirmView /
PasswordResetCompleteView (email-based, no SMS gateway needed).
REGISTER-FIX: Added register_done + verify_success + verify_failed URLs +
templates for a clearer post-registration / post-verification flow.
GOOGLE-OAUTH-MANUAL: Added google_login + google_callback URLs for the
"Sign in with Google" button (stdlib-only — urllib + hashlib, no new deps).
"""
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from .views import (
    AddressCreateView,
    AddressDeleteView,
    AddressListView,
    AddressUpdateView,
    EmailVerifyView,
    GoogleCallbackView,
    GoogleLoginView,
    LoginView,
    ProfileView,
    RegisterDoneView,
    SignupView,
    address_set_default,
    logout_view,
)

app_name = "accounts"

urlpatterns = [
    # --- Real auth ---
    path("login/", LoginView.as_view(), name="login"),
    path("register/", SignupView.as_view(), name="register"),
    # PHINOX-REGISTER-FIX: dedicated "check your email" page.
    path("register/done/", RegisterDoneView.as_view(), name="register_done"),
    path("logout/", logout_view, name="logout"),
    # Email verification (Phase 5 BUGFIX-ROUND-2 + REGISTER-FIX)
    path("verify/<str:token>/", EmailVerifyView.as_view(), name="verify"),
    # Google OAuth 2.0 (PHINOX-GOOGLE-OAUTH-MANUAL)
    path("google/login/", GoogleLoginView.as_view(), name="google_login"),
    path("google/callback/", GoogleCallbackView.as_view(), name="google_callback"),

    # Password reset — Django built-in email-based (BUGFIX-ROUND-2)
    path(
        "password/reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset.html",
            success_url=reverse_lazy("accounts:password_reset_done"),
            email_template_name="emails/password_reset_email.txt",
            html_email_template_name="emails/password_reset_email.html",
            subject_template_name="emails/password_reset_subject.txt",
        ),
        name="password_reset",
    ),
    path(
        "password/reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "password/reset/confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "password/reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),

    # --- Profile + Addresses ---
    path("profile/", ProfileView.as_view(), name="profile"),
    path("addresses/", AddressListView.as_view(), name="addresses"),
    path("addresses/new/", AddressCreateView.as_view(), name="address_create"),
    path("addresses/<int:pk>/edit/", AddressUpdateView.as_view(), name="address_update"),
    path("addresses/<int:pk>/delete/", AddressDeleteView.as_view(), name="address_delete"),
    path(
        "addresses/<int:pk>/default/",
        address_set_default,
        name="address_set_default",
    ),
]
