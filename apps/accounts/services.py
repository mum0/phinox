"""apps.accounts.services — Phase 5 auth services.

Phone-OTP password reset flow per دستور §5:
  - **Rate limit**: max 3 OTP requests per 15 minutes per phone number.
  - **Verify attempts**: max 5 verification attempts per OTP.
  - **Lockout**: 30 minutes after either limit is hit.

PHASE-A §A2 — Dev delivery hardening:
  - The original ``print(f"[OTP DELIVERY] ...")`` call was removed in
    BUGFIX-ROUND-2 (phone-OTP reset → email-based reset via Django's
    PasswordResetView, so no caller invokes ``issue_otp`` from the
    request path anymore).
  - To prevent regressions, a DEBUG-gated helper ``dev_deliver_otp`` is
    provided here. Future re-wirings of phone-OTP MUST call this helper
    rather than calling ``print()`` directly — the helper enforces the
    "never print PII in prod" rule from دستور §5.
  - In prod, the helper is a no-op + logs ``otp.dev_delivery_skipped``.

All functions here are pure (no HTTP concerns) and transactional where
they should be (multi-row writes: issuing an OTP + creating an
attempt row, verifying an OTP + updating rows + creating an attempt row).
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import OTPAttempt, OTPRequest

logger = logging.getLogger(__name__)

# Per دستور §5 — rate-limit + lockout constants (in seconds where noted)
OTP_TTL_SECONDS = 10 * 60  # 10-minute OTP lifetime
OTP_REQUEST_WINDOW = timedelta(minutes=15)  # rate-limit window for requests
OTP_MAX_REQUESTS_PER_WINDOW = 3  # دستور §5: "max 3 OTP requests per 15 minutes per phone number"
OTP_MAX_VERIFY_ATTEMPTS = 5  # دستور §5: "max 5 verification attempts per OTP"
OTP_LOCKOUT_DURATION = timedelta(minutes=30)  # دستور §5: "lockout for 30 min after"


def _hash_code(code: str) -> str:
    """SHA-256 hash the OTP code so the raw code is never stored in the DB."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_6_digit_code() -> str:
    """Generate a cryptographically-secure 6-digit OTP code.

    Uses ``secrets`` (not ``random``) for cryptographic security per
    دستور §5 (rate-limit only works if OTPs are unpredictable).
    """
    return f"{secrets.randbelow(1_000_000):06d}"


# ---------------------------------------------------------------------------
# OTP request: issue + rate-limit
# ---------------------------------------------------------------------------
class OTPLockoutError(Exception):
    """Raised when a phone is locked out (rate-limit hit)."""


@transaction.atomic
def issue_otp(phone: str, purpose: str = "password_reset") -> str:
    """Issue a new OTP for the given phone.

    Per دستور §5 rate-limit:
      - If the phone already has >= 3 OTP requests in the last 15 minutes,
        raise ``OTPLockoutError``.
      - If the phone's most-recent unverified OTP is still locked, raise
        ``OTPLockoutError``.

    Returns:
        The raw 6-digit OTP code (caller is responsible for delivery —
        in dev: log it + put it in context; in prod: send via SMS
        gateway). The hashed code is stored in ``OTPRequest.code_hash``.
    """
    phone = _normalize_phone(phone)

    # --- Rate-limit: max 3 OTPs per 15 min per phone ---
    window_start = timezone.now() - OTP_REQUEST_WINDOW
    recent_count = OTPRequest.objects.filter(
        phone=phone,
        created_at__gte=window_start,
    ).count()
    if recent_count >= OTP_MAX_REQUESTS_PER_WINDOW:
        logger.warning(
            "otp.rate_limited",
            extra={"phone": phone, "recent_count": recent_count},
        )
        raise OTPLockoutError(
            f"Rate limit: max {OTP_MAX_REQUESTS_PER_WINDOW} OTP requests "
            f"per {int(OTP_REQUEST_WINDOW.total_seconds() / 60)} minutes. "
            "Try again later."
        )

    # --- Most-recent OTP still locked? ---
    most_recent = (
        OTPRequest.objects.filter(phone=phone, is_verified=False)
        .order_by("-created_at")
        .first()
    )
    if most_recent and most_recent.locked_until and most_recent.locked_until > timezone.now():
        logger.warning(
            "otp.locked_out",
            extra={"phone": phone, "locked_until": most_recent.locked_until.isoformat()},
        )
        raise OTPLockoutError(
            "This phone is locked out due to too many failed verification "
            f"attempts. Try again after {most_recent.locked_until.strftime('%H:%M')} CLT."
        )

    # --- Issue a fresh OTP ---
    raw_code = _generate_6_digit_code()
    expires_at = timezone.now() + timedelta(seconds=OTP_TTL_SECONDS)
    OTPRequest.objects.create(
        phone=phone,
        code_hash=_hash_code(raw_code),
        purpose=purpose,
        expires_at=expires_at,
    )
    logger.info(
        "otp.issued",
        extra={"phone": phone, "purpose": purpose, "expires_at": expires_at.isoformat()},
    )
    return raw_code


# ---------------------------------------------------------------------------
# OTP verify: check code + enforce attempts + lockout
# ---------------------------------------------------------------------------
class OTPInvalidError(Exception):
    """Raised when the OTP code is invalid/expired/already-verified."""


@transaction.atomic
def verify_otp(phone: str, code: str) -> None:
    """Verify the user-submitted OTP code.

    Per دستور §5:
      - Find the most-recent unverified OTP for this phone.
      - If not found: raise ``OTPInvalidError`` ("No active OTP request").
      - If expired: raise ``OTPInvalidError`` ("OTP has expired").
      - If locked: raise ``OTPLockoutError`` ("Phone is locked out").
      - Count failed attempts on this OTP. If >= 5, set
        ``OTPRequest.locked_until`` to 30 min in the future + raise
        ``OTPLockoutError``.
      - If the code matches: mark OTP as verified (``is_verified=True``,
        ``verified_at`` set). Single-use per دستور §5.
      - If the code doesn't match: create an ``OTPAttempt`` row with
        ``was_successful=False``, increment failed count, possibly lock.

    Args:
        phone: The phone number (E.164 or as-normalized by us).
        code: The 6-digit OTP code the user submitted.

    Raises:
        OTPInvalidError: code mismatch / expired / no active OTP.
        OTPLockoutError: phone locked out (max attempts hit).
    """
    phone = _normalize_phone(phone)
    submitted_hash = _hash_code(code)

    otp = (
        OTPRequest.objects.filter(phone=phone, is_verified=False)
        .order_by("-created_at")
        .first()
    )
    if not otp:
        raise OTPInvalidError("No active OTP request for this phone.")

    if otp.expires_at < timezone.now():
        raise OTPInvalidError("OTP has expired. Request a new one.")

    if otp.locked_until and otp.locked_until > timezone.now():
        raise OTPLockoutError(
            "This phone is locked out due to too many failed verification "
            f"attempts. Try again after {otp.locked_until.strftime('%H:%M')} CLT."
        )

    # --- Successful match ---
    if otp.code_hash == submitted_hash:
        otp.is_verified = True
        otp.verified_at = timezone.now()
        otp.save(update_fields=["is_verified", "verified_at", "updated_at"])
        OTPAttempt.objects.create(
            otp_request=otp, phone=phone, was_successful=True, attempted_code_hash=submitted_hash,
        )
        logger.info("otp.verified", extra={"phone": phone, "purpose": otp.purpose})
        return

    # --- Failed match ---
    OTPAttempt.objects.create(
        otp_request=otp, phone=phone, was_successful=False, attempted_code_hash=submitted_hash,
    )

    # Count failed attempts on this specific OTP (not the phone globally)
    failed_count = otp.attempts.filter(was_successful=False).count()
    if failed_count >= OTP_MAX_VERIFY_ATTEMPTS:
        otp.locked_until = timezone.now() + OTP_LOCKOUT_DURATION
        otp.save(update_fields=["locked_until", "updated_at"])
        logger.warning(
            "otp.max_attempts_reached",
            extra={"phone": phone, "failed_count": failed_count},
        )
        raise OTPLockoutError(
            "Max verification attempts reached. This phone is locked out "
            f"for {int(OTP_LOCKOUT_DURATION.total_seconds() / 60)} minutes."
        )

    remaining = OTP_MAX_VERIFY_ATTEMPTS - failed_count
    raise OTPInvalidError(
        f"Invalid OTP code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
    )


def get_verified_otp(phone: str, purpose: str = "password_reset") -> Optional[OTPRequest]:
    """Return the most-recent verified OTP for the phone (or None).

    Used by the password reset confirm view to check that the user
    successfully verified an OTP before letting them set a new password.
    """
    phone = _normalize_phone(phone)
    return (
        OTPRequest.objects.filter(
            phone=phone, purpose=purpose, is_verified=True,
        )
        .order_by("-verified_at")
        .first()
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalize_phone(phone: str) -> str:
    """Strip whitespace + ensure E.164-ish (per دستور §5).

    Accepts "+20 10 1234 5678" → "+201012345678". Doesn't add a country
    code if missing (validation happens on CustomUser.phone via
    RegexValidator — but the OTP flow operates on its own phone arg
    so we just normalize whitespace here).
    """
    if not phone:
        return ""
    return "".join(phone.strip().split())


def _mask_phone(phone: str) -> str:
    """Mask an E.164 phone to ``+CC***NNNN`` (last 4 visible).

    Used for the ``otp.dev_delivery`` log event so a developer reading
    the dev-mode log can correlate the OTP to a phone without the phone
    being fully exposed in the log stream (per دستور §5 PII rule).
    """
    if not phone or len(phone) < 8:
        return "***"
    # Keep the leading + and up to 3 country-code digits, mask the middle,
    # expose the last 4.
    return f"{phone[:4]}***{phone[-4:]}"


def dev_deliver_otp(phone: str, raw_code: str, purpose: str = "password_reset") -> None:
    """DEBUG-gated dev delivery of an OTP code.

    PHASE-A §A2: this helper replaces the previous ``print(f"[OTP DELIVERY] ...")``
    call. It is a NO-OP in production (DEBUG=False) — only emits a structured
    ``otp.dev_delivery`` log event when DEBUG=True, so a developer running the
    server locally can read the OTP from the log stream.

    Production callers MUST wire a real SMS gateway instead of this helper.

    Args:
        phone: The E.164 phone the OTP was issued for.
        raw_code: The 6-digit OTP code (returned by ``issue_otp``).
        purpose: The OTP purpose (defaults to "password_reset").
    """
    if not getattr(settings, "DEBUG", False):
        # Production: never log the raw code. Emit a marker so ops can see
        # that a dev-delivery call was made (which indicates misconfigured
        # SMS gateway in prod) without leaking PII.
        logger.warning(
            "otp.dev_delivery_skipped",
            extra={"phone": _mask_phone(phone), "purpose": purpose,
                   "reason": "DEBUG=False — caller should wire an SMS gateway"},
        )
        return
    # Dev only — emit the raw code so the developer can read it from the
    # log stream. The phone is masked per دستور §5 PII rule.
    logger.info(
        "otp.dev_delivery",
        extra={"phone_masked": _mask_phone(phone), "code": raw_code, "purpose": purpose},
    )
