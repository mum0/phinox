"""
apps.accounts — CustomUser with stable customer_id (PHX-CUS-000001).

AUTH_USER_MODEL = "accounts.CustomUser" is set in config/settings/base.py.
This must be in place before the first migrate.

Per دستور: phone-first auth is planned for a later phase — the phone field
is added now as schema only. No OTP / auth views are implemented here.
"""
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models

from apps.core.models import next_business_id


class CustomUser(AbstractUser):
    """Custom user model extending AbstractUser.

    - Internal PK: BigAutoField (inherited from AbstractUser)
    - Stable business ID: customer_id = PHX-CUS-000001 (auto-generated)
    - Phone field for the planned phone-first OTP auth flow

    The customer_id is generated atomically via next_business_id("CUS")
    on first save and is immutable thereafter.
    """

    # Stable business ID — externally visible
    customer_id = models.CharField(
        max_length=30,
        unique=True,
        editable=False,
        blank=True,
        db_index=True,
    )

    phone_regex = RegexValidator(
        regex=r"^\+?[1-9]\d{7,14}$",
        message="Phone number must be in international format, e.g. +201012345678.",
    )
    phone = models.CharField(
        max_length=16,
        blank=True,
        validators=[phone_regex],
        help_text="E.164 format, e.g. +201012345678.",
    )

    # Timestamps (AbstractUser doesn't have created_at/updated_at)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_user"
        indexes = [
            models.Index(fields=["customer_id"], name="user_customer_id_idx"),
            models.Index(fields=["phone"], name="user_phone_idx"),
            models.Index(fields=["email"], name="user_email_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self.customer_id:
            self.customer_id = next_business_id("CUS")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.customer_id} — {self.username}"
"""apps.accounts.models — OTP request + attempt tracking models.

Phase 5 STITCH-INTEGRATION: phone-OTP password reset flow per دستور §5.

Models:
  - ``OTPRequest`` — one row per OTP issued. Tracks the phone number,
    the hashed OTP code (never store raw), issue timestamp, expiry,
    whether it's been verified, and whether the user is locked out.
  - ``OTPAttempt`` — one row per verification attempt (success or fail).
    Used to enforce دستور §5's "max 5 verification attempts per OTP"
    rule.

Per دستور §5:
  - **Rate limit**: max 3 OTP requests per 15 minutes per phone number.
  - **Verify attempts**: max 5 verification attempts per OTP.
  - **Lockout**: 30 minutes after either limit is hit.

The models here are the data backing for these rules — the actual
enforcement lives in ``apps.accounts.services.otp_service`` (see
``apps/accounts/services.py``).
"""
from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


# ---------------------------------------------------------------------------
# Phase 5 STITCH-INTEGRATION — OTP request + attempt tracking
# Per دستور §5: phone-OTP rate-limit (3 OTP/15min, 5 verify attempts, 30min lockout)
# ---------------------------------------------------------------------------

class OTPRequest(BaseModel):
    """One row per OTP issued. Hashed code (never raw).

    The OTP code itself is stored as a SHA-256 hash so a database
    compromise doesn't reveal usable OTPs. The raw code is only sent
    to the user (via SMS in prod, via console + dev-mode banner in dev).

    Lifecycle:
      - ``is_verified = False`` initially.
      - On successful verify: ``is_verified = True``, ``verified_at`` set.
      - On failed verify: an ``OTPAttempt`` row is created with
        ``was_successful = False``. When 5 such rows exist, the OTP
        is locked (``locked_until`` set 30 min in the future).
      - After ``expires_at``, the OTP is no longer usable.
    """

    phone = models.CharField(
        max_length=16,
        db_index=True,
        help_text="E.164 format, e.g. +201012345678.",
    )
    code_hash = models.CharField(
        max_length=128,
        help_text="SHA-256 hash of the 6-digit OTP code (raw code never stored).",
    )
    purpose = models.CharField(
        max_length=20,
        default="password_reset",
        help_text="What this OTP authorizes (e.g. 'password_reset', 'phone_verify').",
    )
    expires_at = models.DateTimeField()
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    locked_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="If set, the OTP cannot be verified until this time passes.",
    )
    # Per دستور §5: an OTP is single-use. Once verified, the same code
    # can't be reused (the verify endpoint checks is_verified first).

    class Meta:
        db_table = "accounts_otp_request"
        indexes = [
            models.Index(fields=["phone", "-created_at"], name="otpreq_phone_created_idx"),
            models.Index(fields=["expires_at"], name="otpreq_expires_idx"),
            models.Index(fields=["purpose", "is_verified"], name="otpreq_purpose_verified_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP for {self.phone} ({self.purpose}) — verified={self.is_verified}"


class OTPAttempt(BaseModel):
    """One row per verification attempt (success or failure).

    Per دستور §5: max 5 verification attempts per OTP. After the 5th
    failure, the OTP is locked (``OTPRequest.locked_until`` set).

    We track success attempts too (for audit) but they don't count
    toward the lockout limit (a successful attempt immediately
    invalidates the OTP via ``OTPRequest.is_verified = True``).
    """

    otp_request = models.ForeignKey(
        OTPRequest,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    phone = models.CharField(max_length=16, db_index=True)
    was_successful = models.BooleanField(default=False)
    attempted_code_hash = models.CharField(
        max_length=128,
        blank=True,
        help_text="SHA-256 hash of the code the user submitted (for audit).",
    )

    class Meta:
        db_table = "accounts_otp_attempt"
        indexes = [
            models.Index(fields=["otp_request", "-created_at"], name="otpatt_req_created_idx"),
            models.Index(fields=["phone", "-created_at"], name="otpatt_phone_created_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTPAttempt({self.phone}) — success={self.was_successful}"
