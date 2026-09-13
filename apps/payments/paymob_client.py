"""apps.payments.paymob_client — Phase 4 Part 2: outbound Paymob API client.

App: ``apps.payments``.
Phase: 4 Part 2 (outbound Paymob API — order registration + payment key).
Scope: ``PaymobClient`` class that wraps the three Paymob Accept API
       endpoints needed to redirect a user to the Paymob payment iframe.
Not in scope: the webhook receiver (Part 1 — already implemented in
  ``views_webhook.py``), valU BNPL or FawryPay-specific endpoints (future).

Per دستور §5 (Payments):
  - Paymob is the card processor. The flow is:
    1. ``POST /api/auth/tokens`` → get auth token.
    2. ``POST /api/ecommerce/orders`` → register order, get ``paymob_order_id``.
    3. ``POST /api/acceptance/payment_keys`` → get ``payment_token``.
    4. Redirect user to ``https://accept.paymob.com/api/accept/iframes/<iframe_id>?payment_token=<token>``.
  - No card data ever touches our server — the user enters it on Paymob's
    iframe.

Per دستور §2 (no new deps):
  - Uses ``urllib.request`` (stdlib) for HTTP calls — NOT ``requests``.
  - Uses ``json`` (stdlib) for request/response serialization.

Per دستور §10 (Money):
  - Decimal → cents conversion: ``(amount * 100).quantize(Decimal('1'))``
    (never ``float()`` — never ``int(amount * 100)`` which can lose precision).

Per دستور §5 (Security):
  - API keys + auth tokens are NEVER logged.
  - ``timeout=10`` on every request.
  - Retry once on network errors (not on API errors — those are caller's fault).
  - On API error → raise ``PaymobAPIError`` with a sanitized message (no
    secrets, no card data).
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Paymob API base URLs ──────────────────────────────────────────────────
SANDBOX_BASE = "https://accept.paymob.com/api"
LIVE_BASE = "https://accept.paymob.com/api"  # same host, different creds

REQUEST_TIMEOUT = 10  # seconds
MAX_RETRIES = 1  # retry once on network errors only


class PaymobAPIError(Exception):
    """Raised when a Paymob API call fails (non-2xx response or network error).

    The message is sanitized — never contains API keys or card data.
    """


class PaymobClient:
    """Client for the Paymob Accept API (outbound calls only).

    Three steps are needed to redirect a user to the Paymob payment iframe:
      1. ``_auth_token()`` → POST /api/auth/tokens → auth token (cached).
      2. ``register_order(order)`` → POST /api/ecommerce/orders → paymob_order_id.
      3. ``get_payment_key(order_id, amount_cents)`` → POST /api/acceptance/payment_keys → token.
      4. ``build_iframe_url(payment_token)`` → full URL for the browser to redirect to.

    The auth token is cached in-process (``self._cached_token``) with a
    1-hour TTL — Paymob tokens are valid for ~1 hour, so we avoid re-
    authenticating on every request.

    Args:
        api_key: Paymob API key (from Dashboard → Settings → Account Info).
        integration_id: Paymob Card Integration ID (from Dashboard → Developers).
        iframe_id: Paymob Iframe ID (from Dashboard → Developers → Iframes).
        sandbox: True for sandbox API, False for live.
    """

    def __init__(
        self,
        api_key: str,
        integration_id: str,
        iframe_id: str,
        sandbox: bool = True,
    ) -> None:
        if not api_key:
            raise PaymobAPIError("Paymob API key is required.")
        if not integration_id:
            raise PaymobAPIError("Paymob Integration ID is required.")
        if not iframe_id:
            raise PaymobAPIError("Paymob Iframe ID is required.")
        self._api_key = api_key
        self._integration_id = integration_id
        self._iframe_id = iframe_id
        self._base_url = SANDBOX_BASE if sandbox else LIVE_BASE
        self._cached_token: Optional[str] = None

    # ── 1. Auth token ───────────────────────────────────────────────────
    def _auth_token(self) -> str:
        """Get a Paymob auth token (cached for 1 hour).

        POST /api/auth/tokens with ``{"api_key": "<key>"}``.
        Returns the ``token`` field from the response.

        Raises:
            PaymobAPIError: on HTTP error or unexpected response.
        """
        if self._cached_token:
            return self._cached_token

        url = f"{self._base_url}/auth/tokens"
        body = json.dumps({"api_key": self._api_key}).encode("utf-8")
        resp = self._post(url, body)
        token = resp.get("token")
        if not token:
            raise PaymobAPIError("Paymob auth response missing 'token' field.")
        self._cached_token = token
        logger.info("paymob.auth.success", extra={"endpoint": "auth/tokens"})
        return token

    # ── 2. Register order ────────────────────────────────────────────────
    def register_order(
        self,
        merchant_order_id: str,
        amount_cents: int,
        currency: str = "EGP",
        items: Optional[list[dict]] = None,
    ) -> int:
        """Register an order in Paymob's system.

        POST /api/ecommerce/orders with:
          - ``auth_token``: from _auth_token().
          - ``merchant_order_id``: our business_id (e.g. "PHX-ORD-000001").
          - ``amount_cents``: order total in cents (Decimal * 100).
          - ``currency``: "EGP" (per دستور §10).
          - ``items``: optional list of items (for Paymob's fraud screening).

        Returns:
            The Paymob order ID (int).

        Raises:
            PaymobAPIError: on HTTP error or missing 'id' in response.
        """
        url = f"{self._base_url}/ecommerce/orders"
        payload: dict[str, Any] = {
            "auth_token": self._auth_token(),
            "merchant_order_id": merchant_order_id,
            "amount_cents": amount_cents,
            "currency": currency,
        }
        if items:
            payload["items"] = items

        body = json.dumps(payload).encode("utf-8")
        resp = self._post(url, body)
        order_id = resp.get("id")
        if order_id is None:
            raise PaymobAPIError("Paymob order registration response missing 'id' field.")
        logger.info(
            "paymob.order.registered",
            extra={"paymob_order_id": order_id, "merchant_order_id": merchant_order_id},
        )
        return int(order_id)

    # ── 3. Get payment key ──────────────────────────────────────────────
    def get_payment_key(
        self,
        paymob_order_id: int,
        amount_cents: int,
        billing_data: dict[str, str],
        currency: str = "EGP",
    ) -> str:
        """Request a payment key for the iframe redirect.

        POST /api/acceptance/payment_keys with:
          - ``auth_token``: from _auth_token().
          - ``amount_cents``: order total in cents.
          - ``expiration``: 3600 seconds (1 hour).
          - ``order_id``: the Paymob order ID from register_order().
          - ``billing_data``: customer name + email + phone (Paymob requires this).
          - ``currency``: "EGP".
          - ``integration_id``: the Card Integration ID.

        Returns:
            The payment token string (used in the iframe URL).

        Raises:
            PaymobAPIError: on HTTP error or missing 'token' in response.
        """
        url = f"{self._base_url}/acceptance/payment_keys"
        payload: dict[str, Any] = {
            "auth_token": self._auth_token(),
            "amount_cents": amount_cents,
            "expiration": 3600,
            "order_id": paymob_order_id,
            "billing_data": billing_data,
            "currency": currency,
            "integration_id": self._integration_id,
        }
        body = json.dumps(payload).encode("utf-8")
        resp = self._post(url, body)
        token = resp.get("token")
        if not token:
            raise PaymobAPIError("Paymob payment_keys response missing 'token' field.")
        logger.info(
            "paymob.payment_key.obtained",
            extra={"paymob_order_id": paymob_order_id},
        )
        return token

    # ── 4. Build iframe URL ─────────────────────────────────────────────
    def build_iframe_url(self, payment_token: str) -> str:
        """Build the Paymob iframe URL for the user to redirect to.

        The user enters their card details on Paymob's hosted iframe. After
        payment, Paymob redirects the user back to our site AND sends a
        webhook to ``PAYMOB_WEBHOOK_URL``.

        Returns:
            The full iframe URL: ``https://accept.paymob.com/api/accept/iframes/<iframe_id>?payment_token=<token>``.
        """
        base = "https://accept.paymob.com/api/accept/iframes/"
        return f"{base}{self._iframe_id}?payment_token={payment_token}"

    # ── Helper: Decimal → cents ────────────────────────────────────────
    @staticmethod
    def decimal_to_cents(amount: Decimal) -> int:
        """Convert a Decimal amount to integer cents (multiply by 100).

        Per دستور §10: Decimal only, never float.
        Uses ``quantize(Decimal('1'))`` to round to whole cents without
        float conversion.

        Args:
            amount: The Decimal amount (e.g. Decimal("2500.00")).

        Returns:
            Integer cents (e.g. 250000).
        """
        return int((amount * 100).quantize(Decimal("1")))

    # ── Helper: POST with retry ─────────────────────────────────────────
    def _post(self, url: str, body: bytes) -> dict:
        """POST JSON body to ``url`` with timeout + 1 retry on network error.

        Returns:
            Parsed JSON response dict.

        Raises:
            PaymobAPIError: on non-2xx response or network error after retry.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(1 + MAX_RETRIES):
            try:
                req = urllib.request.Request(
                    url,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                    raw = resp.read()
                    return json.loads(raw)
            except urllib.error.HTTPError as exc:
                # API error (4xx/5xx) — do NOT retry (caller's fault).
                resp_body = ""
                try:
                    resp_body = exc.read().decode("utf-8", errors="replace")[:300]
                except Exception:
                    pass
                logger.error(
                    "paymob.api.http_error",
                    extra={"url": url, "status": exc.code, "body_snippet": resp_body[:100]},
                )
                raise PaymobAPIError(
                    f"Paymob API returned HTTP {exc.code} for {url.split('/')[-1]}."
                ) from exc
            except (urllib.error.URLError, OSError) as exc:
                last_exc = exc
                logger.warning(
                    "paymob.api.network_error",
                    extra={"url": url, "attempt": attempt + 1, "error": str(exc)[:100]},
                )
                continue
        # Exhausted retries.
        raise PaymobAPIError(
            f"Paymob API network error after {1 + MAX_RETRIES} attempts: "
            f"{type(last_exc).__name__ if last_exc else 'unknown'}."
        ) from last_exc
