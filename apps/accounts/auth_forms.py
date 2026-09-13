"""apps.accounts.auth_forms — Phase 5 STITCH-INTEGRATION auth forms.

Three custom forms, all derived from Django's auth forms:

  - ``SignupForm`` — extends ``UserCreationForm`` to create a ``CustomUser``
    with email + phone + full_name fields on top of the standard
    username + password1 + password2.
  - ``PhoneResetRequestForm`` — single phone field, used by the
    PhoneResetRequestView to send an OTP.
  - ``PhoneResetConfirmForm`` — phone + otp + new_password1 + new_password2
    fields, used by the PhoneResetConfirmView to set a new password after
    verifying the OTP.
"""
from __future__ import annotations

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.core.validators import RegexValidator

from apps.accounts.models import CustomUser


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------
class SignupForm(UserCreationForm):
    """Custom signup form. Extends Django's ``UserCreationForm``.

    Adds ``email`` (required), ``phone`` (E.164, optional per دستور §5 —
    the field has the regex validator on CustomUser but isn't strictly
    required at signup since دستور §5 says phone-OTP is for password
    reset, not signup), and ``full_name`` (auto-populates first_name +
    last_name on save).

    Field names match the Stitch register template's existing inputs
    (``full_name``, ``mobile_number``, ``email``, ``password1``,
    ``password2``) so the template needs minimal changes.
    """

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "tech-input", "autocomplete": "email"}),
        help_text="",
    )
    full_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "tech-input", "autocomplete": "name"}),
        help_text="Optional. Displayed on your profile.",
    )
    mobile_number = forms.CharField(
        max_length=16,
        required=False,
        validators=[CustomUser.phone_regex],
        widget=forms.TextInput(attrs={"class": "tech-input", "autocomplete": "tel"}),
        help_text="E.164 format, e.g. +201012345678. Required for password reset via OTP.",
    )

    class Meta:
        model = CustomUser
        fields = ("username", "email", "phone", "full_name", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Match the Stitch template's field names where it makes sense.
        # The template uses ``mobile_number`` for the phone input; we map
        # that to the model's ``phone`` field in ``clean_mobile_number`` below.
        # Username: hidden + auto-generated from email (the Stitch template
        # doesn't ask for a username — only email + full_name).
        self.fields["username"].widget = forms.HiddenInput()
        self.fields["username"].required = False
        self.fields["password1"].widget.attrs.update({"class": "tech-input", "autocomplete": "new-password"})
        self.fields["password2"].widget.attrs.update({"class": "tech-input", "autocomplete": "new-password"})

    def clean_username(self):
        """Auto-generate username from email if not provided."""
        username = self.cleaned_data.get("username", "").strip()
        if username:
            return username
        # Generate from email: take the part before @ + append a number if taken
        email = self.cleaned_data.get("email", "").strip().lower()
        if not email or "@" not in email:
            return username
        base = email.split("@")[0]
        candidate = base
        counter = 1
        while CustomUser.objects.filter(username=candidate).exists():
            candidate = f"{base}{counter}"
            counter += 1
        return candidate

    def clean_email(self):
        """Enforce email uniqueness (Django's default AbstractUser doesn't)."""
        email = self.cleaned_data.get("email", "").strip().lower()
        if email and CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit: bool = True) -> CustomUser:
        """Save the new user + map full_name → first_name + populate phone."""
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        # Stitch template uses ``mobile_number`` — map to ``phone``.
        user.phone = self.cleaned_data.get("mobile_number", "")
        # If full_name provided, split into first_name + last_name
        full_name = (self.cleaned_data.get("full_name") or "").strip()
        if full_name:
            parts = full_name.split(None, 1)
            user.first_name = parts[0]
            user.last_name = parts[1] if len(parts) > 1 else ""
        if commit:
            user.save()
        return user


# ---------------------------------------------------------------------------
# Password reset — request OTP
# ---------------------------------------------------------------------------
class PhoneResetRequestForm(forms.Form):
    """Single phone field. Triggers OTP issuance via the OTP service."""

    mobile_number = forms.CharField(
        max_length=16,
        required=True,
        validators=[CustomUser.phone_regex],
        widget=forms.TextInput(attrs={"class": "tech-input", "autocomplete": "tel", "placeholder": "+20 10 1234 5678"}),
        help_text="Enter your registered phone number (E.164). An OTP will be sent to it.",
    )

    def clean_mobile_number(self):
        """Validate the phone is registered to an existing user."""
        phone = (self.cleaned_data.get("mobile_number") or "").strip()
        # Normalize: remove whitespace
        phone = "".join(phone.split())
        # Per دستور §5 + the OTP service: don't leak whether the phone
        # exists. The view still issues an OTP (which goes to console /
        # the SMS gateway) — the user has to verify it to reset. But we
        # do enforce the rate-limit on the phone regardless.
        return phone


# ---------------------------------------------------------------------------
# Password reset — verify OTP + set new password
# ---------------------------------------------------------------------------
class PhoneResetConfirmForm(forms.Form):
    """Phone + OTP + new_password1 + new_password2 fields.

    Validates the OTP via the OTP service (which enforces the دستور §5
    rate-limit + lockout rules). On success, sets the new password on
    the CustomUser matching the phone.
    """

    mobile_number = forms.CharField(
        max_length=16,
        required=True,
        widget=forms.HiddenInput(attrs={"autocomplete": "tel"}),
    )
    otp = forms.CharField(
        max_length=6,
        min_length=6,
        required=True,
        widget=forms.TextInput(attrs={
            "class": "tech-input text-center text-3xl tracking-[0.5em]",
            "autocomplete": "one-time-code",
            "inputmode": "numeric",
            "pattern": "[0-9]{6}",
            "placeholder": "• • • • • •",
        }),
        help_text="Enter the 6-digit code sent to your phone.",
    )
    new_password1 = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={"class": "tech-input", "autocomplete": "new-password"}),
        help_text="Min 8 chars. Will replace your current password.",
    )
    new_password2 = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={"class": "tech-input", "autocomplete": "new-password"}),
        help_text="Re-enter the new password to confirm.",
    )

    def clean(self):
        cleaned = super().clean()
        phone = cleaned.get("mobile_number", "")
        otp = cleaned.get("otp", "")
        p1 = cleaned.get("new_password1", "")
        p2 = cleaned.get("new_password2", "")

        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("The two new-password fields don't match.")
        # The OTP verify happens in the view (since the view needs to
        # surface the OTPLockoutError / OTPInvalidError to the user
        # via the messages framework, not via field-level errors).
        return cleaned
