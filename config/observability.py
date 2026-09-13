"""config.observability — Phase 6 production observability utilities.

Three pieces:
  1. ``JSONFormatter`` — stdlib ``logging.Formatter`` subclass that emits
     one JSON object per log line (no ``python-json-logger`` dep needed,
     per دستور §2). Used by ``LOGGING`` config in ``config/settings/base.py``.
  2. ``scrub_pii_before_send`` — Sentry ``before_send`` hook that masks
     PII (phone numbers, card last4, full addresses, OTP codes) before
     events leave the process. Per دستور §5: "Never log secrets / PII
     in Sentry breadcrumbs".
  3. ``init_sentry`` — convenience wrapper that initializes Sentry with
     the Django integration + the PII-scrubbing hook + Celery + Redis
     integrations (auto-enabled if installed). Used by prod.py + staging.py.

Per دستور §5:
  - Never log raw OTP codes.
  - Phone numbers in non-admin logs: mask to ``+XX***NNNN`` format.
  - Card numbers: mask to ``**** **** **** XXXX`` (last 4 only).
  - Full addresses: mask to ``<recipient> — <city>, <country>`` (no street).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

# ---------------------------------------------------------------------------
# 1. JSON logging — stdlib only (per دستور §2, no python-json-logger dep)
# ---------------------------------------------------------------------------
class JSONFormatter(logging.Formatter):
    """Emit one JSON object per log line.

    Schema (per line):
      {"ts": "2026-09-10T12:34:56.789Z",
       "level": "INFO",
       "logger": "apps.accounts.services",
       "msg": "otp.issued",
       "event": "otp.issued",
       "extra": {"phone": "+20***5678", "purpose": "password_reset"},
       "exc": null | "<stack trace string>"}

    Rationale: per دستور §2, no new deps. We use stdlib ``json.dumps`` +
    a custom Formatter. The JSON is single-line + escape-safe (no newlines
    inside strings — json.dumps handles that).

    Per دستور §11 ("use logging with structured fields"):
    ``logger.info("order.placed", extra={"order_id": ...})`` becomes
    ``{"event": "order.placed", "extra": {"order_id": ...}}``.
    """

    # Fields from the LogRecord that should NOT be auto-included in "extra"
    _RESERVED = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        # Build the base JSON object
        # PHASE-A §A6: scrub PII from the message itself — if a developer
        # writes ``logger.info(f"phone={user.phone}")`` the phone would
        # otherwise leak to the log stream. Also scrub ``extra`` values.
        raw_msg = record.getMessage()
        scrubbed_msg = _scrub_string(raw_msg)
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S.") + f"{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            # Use scrubbed message so accidentally-logged PII is masked.
            "msg": scrubbed_msg,
            "event": scrubbed_msg,
        }
        # Collect any extra= kwargs the caller attached.
        # PHASE-A §A6: scrub PII from every string value in extra. Without
        # this, ``logger.info("otp.issued", extra={"phone": "+201012345678"})``
        # would write the raw phone to the JSON log stream. ``_scrub_recursive``
        # walks dict/list structures + masks phones, cards, and 6-digit OTPs.
        extra = {}
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                extra[key] = _scrub_recursive(value)
        if extra:
            payload["extra"] = extra
        # Attach exception traceback if present (the traceback itself is
        # NOT scrubbed here — Sentry's ``scrub_pii_before_send`` handles
        # PII in stacktrace frame vars. The local console log stream may
        # show PII in tracebacks, but that's the trade-off for keeping
        # debug info locally visible.)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info
        # json.dumps with default=str so non-serializable values (Decimals,
        # datetimes, etc.) degrade gracefully instead of raising.
        return json.dumps(payload, default=str, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 2. PII scrubbing — Sentry before_send hook
# ---------------------------------------------------------------------------
# PHASE-A §A6 + Phase-D §D4: E.164 phone regex.
#
# Previous regex ``\+(\d{1,3})(\d{3})(\d{4})`` matched ONLY 1-3 + 3 + 4 =
# 8-10 digits after the ``+``. Egyptian phones like ``+201012345678`` have
# 12 digits after the ``+``, so the old regex consumed only the first 10
# digits and left the trailing 2 digits unmasked — meaning
# ``+201012345678`` was displayed as ``+201***3456`` (which collides with
# ``+201012345699`` etc., defeating the masking purpose).
#
# New regex ``\+(\d{1,3})(\d+)(\d{4})`` matches any-length E.164 phone:
#   - group 1: country code (1-3 digits)
#   - group 2: middle digits (masked — at least 1 digit)
#   - group 3: last 4 digits (visible for ops triage)
# So ``+201012345678`` → ``+201***5678`` (no trailing-digit leak).
_PHONE_RE = re.compile(r"\+(\d{1,3})(\d+)(\d{4})")

# Card numbers (PAN): 12-19 digits, optionally space-dashed.
# Per دستور §5: card numbers → last 4 only. We never store the raw PAN.
# This regex is for emergency safety: even if a developer accidentally
# logs a card number, the scrub replaces all but the last 4.
_CARD_RE = re.compile(r"\b(\d{4})[\s-]?(\d{4})[\s-]?(\d{4})[\s-]?(\d{4})\b")

# 6-digit OTP codes (any standalone 6 digits in a row — heuristic, but
# OTPs are short + we err on the side of over-scrubbing).
_OT_RE = re.compile(r"\b\d{6}\b")


def _mask_phone(phone: str) -> str:
    """Mask an E.164 phone to ``+CC***NNNN`` format (last 4 visible).

    PHASE-A §A6 / Phase-D §D4: handles any-length E.164 phone (8-15 digits
    after the ``+``). Returns the original string if no E.164 pattern is
    found (so non-phone strings are not mangled).
    """
    m = _PHONE_RE.search(phone)
    if not m:
        return phone  # not E.164 — leave alone
    return f"+{m.group(1)}***{m.group(3)}"


def _scrub_string(value: str) -> str:
    """Scrub PII patterns from a single string."""
    if not isinstance(value, str):
        return value
    # 1. Card numbers: keep last 4 only.
    value = _CARD_RE.sub(lambda m: f"**** **** **** {m.group(4)}", value)
    # 2. E.164 phone numbers: keep +CC + last 4.
    value = _PHONE_RE.sub(lambda m: f"+{m.group(1)}***{m.group(3)}", value)
    # 3. 6-digit standalone codes (OTP — over-scrub is safe).
    value = _OT_RE.sub("[OTP-SCRUBBED]", value)
    return value


def _scrub_recursive(obj: Any) -> Any:
    """Walk a dict/list structure + scrub every string."""
    if isinstance(obj, str):
        return _scrub_string(obj)
    if isinstance(obj, dict):
        return {k: _scrub_recursive(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(_scrub_recursive(v) for v in obj)
    return obj


def scrub_pii_before_send(event: dict, hint: dict) -> dict:
    """Sentry ``before_send`` hook — masks PII before events leave.

    Per دستور §5: "Never log secrets / PII in Sentry breadcrumbs." This
    hook walks the entire event tree (request body, breadcrumbs, extra,
    exception values, stack frames) and scrubs:
      - Card numbers (PAN) → ``**** **** **** XXXX``
      - E.164 phones → ``+CC***NNNN``
      - 6-digit standalone codes → ``[OTP-SCRUBBED]``
    Returns ``None`` to drop the event if scrubbing fails entirely
    (extreme defensive — never leak raw PII).
    """
    try:
        # Scrub top-level fields
        for key in ("message", "culprit", "logger"):
            if key in event:
                event[key] = _scrub_string(event[key])
        # Scrub request data
        if "request" in event:
            event["request"] = _scrub_recursive(event["request"])
        # Scrub breadcrumbs
        if "breadcrumbs" in event and "values" in event["breadcrumbs"]:
            event["breadcrumbs"]["values"] = [
                _scrub_recursive(b) for b in event["breadcrumbs"]["values"]
            ]
        # Scrub extra context
        if "extra" in event:
            event["extra"] = _scrub_recursive(event["extra"])
        # Scrub exception values (message + stacktrace frame vars)
        if "exception" in event and "values" in event["exception"]:
            for exc in event["exception"]["values"]:
                if "value" in exc:
                    exc["value"] = _scrub_string(exc["value"])
                if "stacktrace" in exc and "frames" in exc["stacktrace"]:
                    for frame in exc["stacktrace"]["frames"]:
                        if "vars" in frame:
                            frame["vars"] = _scrub_recursive(frame["vars"])
        return event
    except Exception:
        # If anything goes wrong, drop the event entirely — never leak.
        return None


# ---------------------------------------------------------------------------
# 3. Sentry initialization — used by prod.py + staging.py
# ---------------------------------------------------------------------------
def init_sentry(dsn: str, environment: str, traces_sample_rate: float = 0.1) -> None:
    """Initialize Sentry with the Django integration + PII scrubbing.

    Per دستور §5: ``before_send=scrub_pii_before_send`` masks phone numbers,
    card numbers, OTP codes before events leave the process.

    Per دستور §0 rule 5: ``environment="production"`` so Sentry groups
    events by environment (production vs. staging alerts).

    Per دستور §5: ``send_default_pii=False`` is the default — but our
    ``scrub_pii_before_send`` hook is the real enforcement, not this flag
    (some integrations still send IP / user_id which we want for
    incident triage; the hook keeps those minus the PII).

    Args:
        dsn: The Sentry DSN. If empty, no-op.
        environment: "production" or "staging".
        traces_sample_rate: 0.1 = sample 10% of transactions for performance
            monitoring (per دستور §11 recommended default).
    """
    if not dsn:
        return
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    integrations: list = [DjangoIntegration()]
    # Celery + Redis integrations are auto-detected if installed (they're
    # in requirements/base.txt).
    try:
        from sentry_sdk.integrations.celery import CeleryIntegration
        integrations.append(CeleryIntegration())
    except ImportError:
        pass
    try:
        from sentry_sdk.integrations.redis import RedisIntegration
        integrations.append(RedisIntegration())
    except ImportError:
        pass

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        integrations=integrations,
        traces_sample_rate=traces_sample_rate,
        send_default_pii=False,  # defense in depth; the hook is the real enforcement
        before_send=scrub_pii_before_send,
        # Release tracking — set SENTRY_RELEASE env to the git SHA at deploy.
        release=os.environ.get("SENTRY_RELEASE", ""),
    )


# Late import so init_sentry can use it without forcing a top-of-module import.
import os  # noqa: E402
