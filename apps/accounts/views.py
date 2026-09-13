"""apps.accounts — Phase 5 + BUGFIX-ROUND-2 + REGISTER-FIX real auth views.

  - LoginView (Django built-in, subclassed for Stitch template).
  - SignupView (CreateView; is_active=False + verification email).
    [REGISTER-FIX] success_url → register_done (the "check your email" page).
  - RegisterDoneView (TemplateView; renders register_done.html).
  - EmailVerifyView (activates account via signed token).
    [REGISTER-FIX] on success → render verify_success.html (was: redirect to login).
    [REGISTER-FIX] on failure → render verify_failed.html (was: redirect to register).
  - logout_view (POST-only, redirects to login).
  - Password reset: Django built-in auth_views (email-based, no SMS).
  - ProfileView + AddressListView + CRUD.
"""
from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView,
    DeleteView,
    ListView,
    TemplateView,
    UpdateView,
)

from apps.accounts.auth_forms import SignupForm
from apps.accounts.models import CustomUser
from apps.shipping.models import ShippingAddress

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Real auth views (Phase 5 — replaces Phase 4 stubs)
# ---------------------------------------------------------------------------
class LoginView(DjangoLoginView):
    """Django's built-in LoginView, subclassed for the Stitch template.

    URL name: ``accounts:login``.
    Template: ``accounts/login.html`` (Stitch "Operative Authentication"
    port from Phase 1).
    On success: redirect to ``LOGIN_REDIRECT_URL`` (default: ``pages:home``).
    On failure: re-render the login template with the form errors (Django's
    default behavior — Django's ``AuthenticationForm`` raises
    ``ValidationError`` on bad credentials).

    PHINOX-GOOGLE-OAUTH-MANUAL: passes ``google_oauth_enabled`` via
    ``extra_context`` so the login template can conditionally render the
    "Continue with Google" button (only when GOOGLE_CLIENT_ID is set).
    """

    template_name = "accounts/login.html"
    authentication_form = AuthenticationForm
    redirect_authenticated_user = True
    extra_context = {
        "page_title": "PHINOX — Sign In",
    }

    def get_context_data(self, **kwargs):
        """Inject ``google_oauth_enabled`` based on settings.GOOGLE_CLIENT_ID."""
        from django.conf import settings as dj_settings
        context = super().get_context_data(**kwargs)
        # Only show the Google button when BOTH client_id + secret are set.
        context["google_oauth_enabled"] = bool(
            getattr(dj_settings, "GOOGLE_CLIENT_ID", "")
            and getattr(dj_settings, "GOOGLE_CLIENT_SECRET", "")
        )
        return context

    def get_form(self, form_class=None):
        """Add tech-input styling to the form fields."""
        form = super().get_form(form_class)
        form.fields["username"].widget.attrs.update({
            "class": "tech-input",
            "autocomplete": "username",
            "autofocus": True,
        })
        form.fields["password"].widget.attrs.update({
            "class": "tech-input",
            "autocomplete": "current-password",
        })
        return form

    def form_invalid(self, form):
        """On failed login, surface the error via Django messages framework."""
        messages.error(
            self.request,
            "Invalid credentials. Please verify your username/email and password.",
        )
        return super().form_invalid(form)


class SignupView(CreateView):
    """Custom signup view with email verification.

    URL name: ``accounts:register``.
    Template: ``accounts/register.html``.
    On success: set is_active=False + send verification email + redirect
    to ``accounts:register_done`` (the "check your email" page).

    PHINOX-REGISTER-FIX: success_url now points to ``accounts:register_done``
    instead of ``accounts:login`` — gives the user a clear "check your email"
    confirmation page rather than dropping them back at login with a flash
    message that might be missed.

    PHINOX-GOOGLE-OAUTH-MANUAL: passes ``google_oauth_enabled`` via
    ``get_context_data()`` so the register template can conditionally
    render the "Initialize with Google" button.
    """

    template_name = "accounts/register.html"
    form_class = SignupForm
    success_url = reverse_lazy("accounts:register_done")
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("pages:home")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """Inject ``google_oauth_enabled`` based on settings.GOOGLE_CLIENT_ID."""
        from django.conf import settings as dj_settings
        context = super().get_context_data(**kwargs)
        context["google_oauth_enabled"] = bool(
            getattr(dj_settings, "GOOGLE_CLIENT_ID", "")
            and getattr(dj_settings, "GOOGLE_CLIENT_SECRET", "")
        )
        return context

    def form_valid(self, form):
        """Save user with is_active=False + send verification email."""
        from django.core.signing import TimestampSigner
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string
        from django.conf import settings as dj_settings

        response = super().form_valid(form)
        user = self.object
        # Deactivate until email is verified.
        user.is_active = False
        user.save(update_fields=["is_active", "updated_at"])

        # Generate a signed token valid for 24h.
        signer = TimestampSigner()
        token = signer.sign(user.pk)

        # Build verification URL.
        site_domain = getattr(dj_settings, "PHINOX_SITE_DOMAIN", "http://localhost:8000").rstrip("/")
        verify_url = f"{site_domain}/accounts/verify/{token}/"

        # Send verification email (console in dev — visible in terminal).
        try:
            context = {"user": user, "verify_url": verify_url, "site_domain": site_domain}
            text_body = render_to_string("emails/account_verification.txt", context)
            html_body = render_to_string("emails/account_verification.html", context)
            msg = EmailMultiAlternatives(
                subject=f"PHINOX — Verify your operative dossier",
                body=text_body,
                from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", "no-reply@phinox.example"),
                to=[user.email],
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send(fail_silently=True)
        except Exception as exc:
            logger.warning("user.verification_email_failed", extra={"user_id": user.id, "error": str(exc)[:200]})

        logger.info(
            "user.signup_pending_verification",
            extra={"user_id": user.id, "customer_id": user.customer_id, "email": user.email},
        )
        return response

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below and re-submit.")
        return super().form_invalid(form)


class RegisterDoneView(TemplateView):
    """The "check your email" page shown after successful registration.

    URL name: ``accounts:register_done``.
    URL path: ``/accounts/register/done/``.
    Template: ``accounts/register_done.html``.

    PHINOX-REGISTER-FIX: a dedicated landing page (was: a flash message
    on the login page that users often missed). Tells the user to check
    their email for the verification link + has a CTA back to login.
    """

    template_name = "accounts/register_done.html"
    extra_context = {"page_title": "PHINOX — Dossier Initialized"}


class EmailVerifyView(View):
    """Email verification view — activates the user's account.

    URL: /accounts/verify/<token>/ — the token is a TimestampSigner
    signed value (valid 24h). On success: is_active=True + render
    verify_success.html. On failure (invalid/expired token): render
    verify_failed.html.

    PHINOX-REGISTER-FIX: previously redirected to login/register with
    a flash message. Now renders dedicated success/failed templates for
    a clearer post-verification UX.
    """

    def get(self, request, token: str) -> HttpResponse:
        from django.core.signing import TimestampSigner, BadSignature, SignatureExpired

        signer = TimestampSigner()
        try:
            user_pk = signer.unsign(token, max_age=86400)  # 24h
        except (BadSignature, SignatureExpired):
            # Render the failure page (don't leak whether the email exists).
            return render(request, "accounts/verify_failed.html", status=200)

        user = CustomUser.objects.filter(pk=user_pk).first()
        if not user:
            return render(request, "accounts/verify_failed.html", status=200)

        if user.is_active:
            # Already activated — render the success page (idempotent).
            return render(request, "accounts/verify_success.html", status=200)

        user.is_active = True
        user.save(update_fields=["is_active", "updated_at"])
        logger.info("user.verified", extra={"user_id": user.id, "username": user.username})
        return render(request, "accounts/verify_success.html", status=200)


# ---------------------------------------------------------------------------
# Google OAuth 2.0 (PHINOX-GOOGLE-OAUTH-MANUAL)
# ---------------------------------------------------------------------------
class GoogleLoginView(View):
    """Start the Google OAuth 2.0 authorization-code flow.

    URL: /accounts/google/login/  (name="accounts:google_login")

    Flow:
      1. Generate a random ``state`` (32-byte hex, ``secrets.token_hex(32)``).
      2. Store ``state`` in the user's Django session (server-side).
      3. Redirect to Google's consent screen with ``state`` + our
         ``client_id`` + ``redirect_uri`` + ``scope=openid email profile``.

    Per دستور §5 (Auth security):
      - ``state`` is a cryptographically-secure random value.
      - ``state`` is stored in the session (encrypted if SESSION_ENGINE
        is signed-cookie or db).
      - The callback verifies ``state`` with ``hmac.compare_digest``
        (constant-time) to prevent CSRF.

    Per PHINOX-GOOGLE-OAUTH-MANUAL spec: if GOOGLE_CLIENT_ID is not
    configured, return 404 (the login template hides the button, so
    reaching this view means misconfiguration).
    """

    def get(self, request) -> HttpResponseRedirect:
        from django.conf import settings as dj_settings
        from apps.accounts.google_oauth import GoogleOAuthClient, generate_state

        client_id = getattr(dj_settings, "GOOGLE_CLIENT_ID", "")
        client_secret = getattr(dj_settings, "GOOGLE_CLIENT_SECRET", "")
        redirect_uri = getattr(dj_settings, "GOOGLE_REDIRECT_URI", "")

        if not client_id or not client_secret:
            # Misconfiguration — the button is hidden when client_id is
            # empty, so reaching here means someone manually hit the URL.
            from django.http import Http404
            raise Http404("Google OAuth is not configured.")

        client = GoogleOAuthClient(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )
        # Generate + store state in the session (CSRF protection).
        state = generate_state()
        request.session["google_oauth_state"] = state
        request.session.save()

        auth_url = client.build_auth_url(state=state)
        logger.info("google_oauth.flow_started", extra={"state_len": len(state)})
        return redirect(auth_url)


class GoogleCallbackView(View):
    """Google OAuth 2.0 callback — exchanges the code + logs the user in.

    URL: /accounts/google/callback/  (name="accounts:google_callback")

    Flow:
      1. Read ``code`` + ``state`` from the query params.
      2. Verify ``state`` matches the session value (``hmac.compare_digest``).
      3. Exchange ``code`` for ``access_token`` + ``id_token`` (POST to
         https://oauth2.googleapis.com/token).
      4. Verify the ``id_token`` (decode payload + check iss/aud/exp +
         cross-check via Google's tokeninfo endpoint).
      5. GET https://www.googleapis.com/oauth2/v2/userinfo for the
         user's email + name.
      6. Find or create a CustomUser with the email.
         - If exists: link the Google account (no separate model needed —
           the email is the link).
         - If new: create with is_active=True (Google pre-verified the
           email) + a random unusable password (so the user can't log in
           via password — only via Google).
      7. ``django.contrib.auth.login(request, user)`` → establishes the
         Django session.
      8. Redirect to ``LOGIN_REDIRECT_URL`` (pages:home).

    Per دستور §5: never log the access_token, id_token, or client_secret.
    The JSONFormatter's PII scrub masks them if they end up in a log record.
    """

    def get(self, request) -> HttpResponse:
        from django.conf import settings as dj_settings
        from django.contrib.auth import login
        from django.contrib import messages
        from apps.accounts.google_oauth import (
            GoogleOAuthClient,
            GoogleOAuthError,
            verify_state,
        )

        client_id = getattr(dj_settings, "GOOGLE_CLIENT_ID", "")
        client_secret = getattr(dj_settings, "GOOGLE_CLIENT_SECRET", "")
        redirect_uri = getattr(dj_settings, "GOOGLE_REDIRECT_URI", "")

        if not client_id or not client_secret:
            from django.http import Http404
            raise Http404("Google OAuth is not configured.")

        # 1. Read code + state from Google's redirect.
        code = request.GET.get("code", "")
        state = request.GET.get("state", "")
        if not code:
            messages.error(request, "Google OAuth callback missing 'code' parameter.")
            return redirect("accounts:login")

        # 2. Verify state (CSRF protection — constant-time comparison).
        session_state = request.session.pop("google_oauth_state", "")
        if not verify_state(state, session_state):
            logger.warning(
                "google_oauth.state_mismatch",
                extra={
                    "state_len_request": len(state),
                    "state_len_session": len(session_state),
                },
            )
            messages.error(request, "Google OAuth state verification failed. Please try again.")
            return redirect("accounts:login")

        # 3. Exchange code → tokens + verify id_token + get user info.
        client = GoogleOAuthClient(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )
        try:
            token_response = client.exchange_code(code)
            access_token = token_response["access_token"]
            id_token = token_response.get("id_token", "")
            if id_token:
                # Verify the id_token (decode + check claims + tokeninfo
                # cross-check). The returned claims are not used directly —
                # the userinfo endpoint is the source of truth for the
                # user's profile.
                client.verify_id_token(id_token)
            user_info = client.get_user_info(access_token)
        except GoogleOAuthError as exc:
            logger.error(
                "google_oauth.flow_failed",
                extra={"error_type": type(exc).__name__, "error_msg": str(exc)[:200]},
            )
            messages.error(request, f"Google OAuth failed: {exc}. Please try again.")
            return redirect("accounts:login")

        # 4. Find or create the user.
        email = user_info.get("email", "").strip().lower()
        google_sub = user_info.get("id", "")  # Google's stable user ID
        google_name = user_info.get("name", "")
        google_picture = user_info.get("picture", "")
        email_verified = user_info.get("verified_email", False)

        if not email:
            messages.error(request, "Google did not return an email. Please try again.")
            return redirect("accounts:login")

        if not email_verified:
            messages.error(
                request,
                "Your Google email is not verified. Please verify it in Google Account settings.",
            )
            return redirect("accounts:login")

        user = self._find_or_create_user(
            email=email,
            google_sub=google_sub,
            google_name=google_name,
        )
        if user is None:
            # Shouldn't happen (we check email_verified above), but defensive.
            messages.error(request, "Could not find or create your account. Please contact support.")
            return redirect("accounts:login")

        # 5. Log the user in (establishes the Django session).
        login(request, user)
        logger.info(
            "google_oauth.login_success",
            extra={
                "user_id": user.id,
                "email": email,
                "google_sub": google_sub,
                "is_new_user": not user.has_usable_password(),
            },
        )
        messages.success(request, f"Welcome, {user.username}! Signed in via Google.")

        # Redirect to LOGIN_REDIRECT_URL or the ?next= param.
        next_url = request.GET.get("next") or request.session.pop(
            "google_oauth_next", ""
        ) or "pages:home"
        return redirect(next_url)

    def _find_or_create_user(
        self,
        *,
        email: str,
        google_sub: str,
        google_name: str,
    ) -> CustomUser | None:
        """Find an existing user by email, or create a new Google-linked one.

        Args:
            email: The verified email from Google (lowercased).
            google_sub: Google's stable user ID (``user_info.id``).
            google_name: The user's display name from Google.

        Returns:
            The CustomUser instance, or None if creation failed.
        """
        # Look up by email (case-insensitive — Google returns lowercase).
        user = CustomUser.objects.filter(email__iexact=email).first()
        if user is not None:
            # Existing user — log them in. The email match is the "link"
            # (no separate GoogleAccount model — keeps the schema simple
            # per دستور §6 "no premature abstraction").
            if not user.is_active:
                # Reactivate if the user was previously deactivated (e.g.
                # email verification pending — Google's verification is
                # sufficient to activate).
                user.is_active = True
                user.save(update_fields=["is_active", "updated_at"])
            return user

        # New user — create with is_active=True (Google pre-verified the
        # email) + a random unusable password (so the user can't log in
        # via password — only via Google). Username derived from email.
        from django.contrib.auth.models import UserManager
        base_username = email.split("@")[0][:30] if "@" in email else f"google_{google_sub[:20]}"
        candidate = base_username
        counter = 1
        while CustomUser.objects.filter(username=candidate).exists():
            counter += 1
            candidate = f"{base_username}{counter}"
        try:
            user = CustomUser.objects.create_user(
                username=candidate,
                email=email,
                # set_unusable_password — the user can only log in via Google.
                # If they later want a password, they can use the password
                # reset flow (which sets a usable password).
                password=None,
            )
        except Exception as exc:
            logger.error(
                "google_oauth.user_creation_failed",
                extra={"email": email, "error_msg": str(exc)[:200]},
            )
            return None

        # Google pre-verified the email → activate immediately.
        user.is_active = True
        # Populate first_name/last_name from Google's name (split on first space).
        if google_name:
            parts = google_name.split(None, 1)
            user.first_name = parts[0][:30]
            user.last_name = parts[1][:30] if len(parts) > 1 else ""
        # Store the Google sub ID for future linking (we use the phone field
        # as a scratch — the spec doesn't define a separate google_sub field
        # and adding one would require a migration. The phone field is
        # currently unused for Google users. If a future phase adds a
        # google_sub field, we'll migrate the data).
        # NOTE: not setting user.phone — let it stay blank.
        user.save(update_fields=[
            "is_active", "first_name", "last_name", "updated_at",
        ])
        logger.info(
            "google_oauth.user_created",
            extra={"user_id": user.id, "email": email, "username": user.username},
        )
        return user


@require_POST
def logout_view(request) -> HttpResponseRedirect:
    """Log the user out + redirect to login page.

    Uses Django's ``auth.logout`` which:
      - Clears the session.
      - Rotates the CSRF cookie (per دستور §5 session fixation rule).
      - Calls ``user_logged_out`` signal.

    A POST-only endpoint (per Django's recommended practice to prevent
    CSRF on logout). The Stitch profile page has a form that POSTs here.
    """
    auth_logout(request)
    messages.info(request, "You have been disconnected from the PHINOX node.")
    return redirect("accounts:login")


# ---------------------------------------------------------------------------
# Password reset — replaced by Django built-in auth_views
# (BUGFIX-ROUND-2: email-based reset, no SMS gateway needed)
# See apps/accounts/urls.py for the URL wiring.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Profile + Addresses (Phase 2 carry-over — unchanged in Phase 5 except
# removing the "Stub" suffix from ProfileStubView since auth is now real)
# ---------------------------------------------------------------------------
class ProfileView(LoginRequiredMixin, TemplateView):
    """Phase 2 + Phase 5 — real profile view.

    The Stitch "Client Archive & Profile" page renders the layout using
    the currently-logged-in user's basic fields (customer_id, username,
    email, phone, date_joined). Cards that need real backend wiring
    (VIP tier, payment tokens, body sizing matrix) remain placeholders.
    """

    template_name = "accounts/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        # Defensive defaults so the template renders even if a field is blank.
        context["profile_user"] = user
        context["customer_id"] = getattr(user, "customer_id", "") or "—"
        context["node_initiation"] = (
            user.date_joined.strftime("%B %Y") if user.date_joined else "—"
        )
        return context


class AddressListView(LoginRequiredMixin, ListView):
    """List the user's saved shipping addresses.

    PHASE-B §B4: filters ``is_active=True`` so soft-deleted addresses
    (addresses referenced by an Order that the user "deleted") don't
    appear in the list. The soft-delete preserves the address row so
    Order.shipping_address FK + the snapshot fields stay intact.
    """

    template_name = "accounts/addresses.html"
    context_object_name = "addresses"
    paginate_by = 20

    def get_queryset(self):
        return ShippingAddress.objects.filter(
            user=self.request.user, is_active=True,
        ).order_by("-is_default", "-updated_at")


class AddressCreateView(LoginRequiredMixin, CreateView):
    """Create a new shipping address for the current user."""

    model = ShippingAddress
    template_name = "accounts/address_form.html"
    fields = ["full_name", "phone", "governorate", "city", "country", "address", "postal_code", "is_default"]
    success_url = reverse_lazy("accounts:addresses")

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        if form.instance.is_default:
            ShippingAddress.objects.filter(user=self.request.user).exclude(
                pk=form.instance.pk
            ).update(is_default=False)
        messages.success(self.request, "Address saved.")
        return response


class AddressUpdateView(LoginRequiredMixin, UpdateView):
    """Edit an existing shipping address (owner-only)."""

    model = ShippingAddress
    template_name = "accounts/address_form.html"
    fields = ["full_name", "phone", "governorate", "city", "country", "address", "postal_code", "is_default"]
    success_url = reverse_lazy("accounts:addresses")

    def get_queryset(self):
        # PHASE-B §B4: only active addresses are editable; soft-deleted
        # ones are not (they exist solely for order history).
        return ShippingAddress.objects.filter(user=self.request.user, is_active=True)

    def form_valid(self, form):
        response = super().form_valid(form)
        if form.instance.is_default:
            ShippingAddress.objects.filter(user=self.request.user).exclude(
                pk=form.instance.pk
            ).update(is_default=False)
        messages.success(self.request, "Address updated.")
        return response


class AddressDeleteView(LoginRequiredMixin, DeleteView):
    """Delete an address.

    PHASE-B §B4: if the address is referenced by any Order, SOFT-DELETE
    (set is_active=False) so the Order's shipping_address FK + the
    snapshot fields stay intact. Otherwise hard-delete (the address row
    is removed entirely).

    Per دستور §6: snapshot denormalization on Order is deliberate — the
    Order has shipping_recipient_name/phone/governorate/city/street_address
    snapshot fields that survive even a hard delete. But the FK link
    (Order.shipping_address) is SET_NULL on hard-delete, so we soft-delete
    when the address is referenced to preserve the FK for audit.
    """

    model = ShippingAddress
    template_name = "accounts/address_confirm_delete.html"
    success_url = reverse_lazy("accounts:addresses")

    def get_queryset(self):
        return ShippingAddress.objects.filter(user=self.request.user, is_active=True)

    def form_valid(self, form):
        from apps.orders.models import Order

        addr = self.get_object()
        # PHASE-B §B4: if any Order references this address, soft-delete.
        if Order.objects.filter(shipping_address=addr).exists():
            addr.is_active = False
            # If this was the default address, clear the flag (the address
            # is no longer visible to the user, so it shouldn't be the default).
            addr.is_default = False
            addr.save(update_fields=["is_active", "is_default", "updated_at"])
            messages.info(
                self.request,
                "Address archived — it's linked to one or more orders, "
                "so we've kept it for order history. It's no longer visible "
                "in your address list.",
            )
            return redirect(self.success_url)
        # No orders reference this address — hard-delete is safe.
        addr.delete()
        messages.success(self.request, "Address removed.")
        return redirect(self.success_url)


@require_POST
def address_set_default(request, pk: int) -> HttpResponse:
    """POST-only endpoint: set the given address as the user's default."""
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    address = get_object_or_404(ShippingAddress, pk=pk, user=request.user)
    ShippingAddress.objects.filter(user=request.user).exclude(pk=pk).update(
        is_default=False
    )
    address.is_default = True
    address.save(update_fields=["is_default", "updated_at"])
    messages.success(request, f"Set '{address.full_name} — {address.city}' as default.")
    return redirect("accounts:addresses")


# Late import — settings needed for the dev-mode OTP banner
from django.conf import settings  # noqa: E402
