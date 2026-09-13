"""apps.accounts.google_oauth — Google OAuth 2.0 client (stdlib-only).

PHINOX-GOOGLE-OAUTH-MANUAL: implements the Google OAuth 2.0 Authorization
Code flow using ONLY stdlib (urllib.request + hashlib + hmac + secrets +
json + base64). No `requests`, no `PyJWT`, no `cryptography` — per
AGENTS.md §2 "no new dependencies".

Flow (Authorization Code with PKCE-lite — we use ``state`` for CSRF):
  1. User clicks "Sign in with Google" on /accounts/login/.
  2. GoogleLoginView generates a random ``state``, stores it in the
     session, + redirects to Google's consent screen.
  3. User consents → Google redirects to /accounts/google/callback/?code=...&state=...
  4. GoogleCallbackView verifies ``state`` matches the session value
     (hmac.compare_digest — constant-time to prevent timing attacks).
  5. Exchange the ``code`` for an ``access_token`` + ``id_token`` via
     POST to https://oauth2.googleapis.com/token.
  6. Decode the ``id_token`` (JWT) payload (base64 + json — stdlib) +
     verify claims (iss, aud, exp). Call Google's tokeninfo endpoint
     for server-side signature verification (avoids needing local RSA
     crypto — see ``verify_id_token`` docstring for the trade-off).
  7. GET https://www.googleapis.com/oauth2/v2/userinfo for the user's
     email + name + Google sub ID.
  8. If a CustomUser with the email exists → log them in.
     If not → create a new CustomUser with is_active=True (Google
     pre-verified the email) + log them in.

Per دستور §5 (Auth security):
  - ``state`` is a random 32-byte hex string (``secrets.token_hex(32)``).
  - ``state`` is stored in the Django session (server-side, encrypted
    if SESSION_ENGINE is signed-cookie or db).
  - ``state`` comparison uses ``hmac.compare_digest`` (constant-time).
  - ``client_secret`` is NEVER logged (the JSONFormatter's PII scrub
    also masks it if it accidentally ends up in a log record).
  - ``access_token`` is NEVER logged (same).
  - All HTTP calls use ``timeout=10`` (per spec) to prevent hanging.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Google OAuth 2.0 endpoints (per Google's official docs).
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_JWK_URL = "https://www.googleapis.com/oauth2/v3/certs"

# Per دستور §5: 10-second timeout for all outbound HTTP calls to Google.
# Long enough to absorb Google's occasional latency, short enough to fail
# fast in the view (the user is waiting on a redirect).
HTTP_TIMEOUT_SECONDS = 10

# Valid issuers for Google id_tokens (per Google's docs).
_VALID_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}


class GoogleOAuthError(Exception):
    """Raised when a Google OAuth API call fails (network, parse, or auth).

    The view catches this + shows a user-friendly error message. The
    underlying error is logged at WARNING level (never includes
    ``client_secret`` or ``access_token`` — those are scrubbed by the
    JSONFormatter before logging).
    """


class GoogleOAuthClient:
    """Google OAuth 2.0 client (stdlib-only — urllib + hashlib).

    Per PHINOX-GOOGLE-OAUTH-MANUAL spec: implements the authorization
    code flow with the following methods:

      * ``build_auth_url(state)`` → builds the Google consent URL.
      * ``exchange_code(code)`` → POST to Google's token endpoint to
        exchange the auth code for an ``access_token`` + ``id_token``.
      * ``get_user_info(access_token)`` → GET the user's profile.
      * ``verify_id_token(id_token)`` → decode the JWT payload + verify
        claims (iss, aud, exp) + cross-check via Google's tokeninfo
        endpoint (server-side signature verification).

    All HTTP calls use ``urllib.request`` (stdlib) with a 10s timeout.
    No ``requests`` dependency.

    Args:
        client_id: Google OAuth client ID (from Google Cloud Console).
        client_secret: Google OAuth client secret (NEVER logged).
        redirect_uri: The callback URL registered in Google Cloud Console.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> None:
        if not client_id or not client_secret:
            raise GoogleOAuthError(
                "Google OAuth requires GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET. "
                "Set them in .env or via the environment."
            )
        self.client_id = client_id
        # Per دستور §5: client_secret is sensitive — never log it.
        self._client_secret = client_secret
        self.redirect_uri = redirect_uri

    # ------------------------------------------------------------------
    # Step 1: build the consent URL
    # ------------------------------------------------------------------
    def build_auth_url(self, state: str) -> str:
        """Build the Google OAuth consent screen URL.

        The user's browser is redirected here to consent. After consent,
        Google redirects to ``redirect_uri`` with ``?code=...&state=...``.

        Args:
            state: A random string (32-byte hex) stored in the session
                for CSRF protection. Verified in the callback.

        Returns:
            The fully-built Google consent URL with query params.
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            # prompt=select_account lets the user pick which Google account
            # to sign in with (useful for users with multiple accounts).
            "prompt": "select_account",
        }
        return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"

    # ------------------------------------------------------------------
    # Step 2: exchange the auth code for tokens
    # ------------------------------------------------------------------
    def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange the authorization code for an access_token + id_token.

        POSTs to https://oauth2.googleapis.com/token with the auth code.
        Google responds with a JSON object containing ``access_token``,
        ``id_token``, ``expires_in``, ``token_type``, ``scope``.

        Args:
            code: The authorization code from Google's callback redirect.

        Returns:
            The parsed JSON response dict (contains access_token + id_token).

        Raises:
            GoogleOAuthError: If the HTTP call fails, the response is
                not JSON, or Google returns an error (e.g. invalid code).
        """
        data = urllib.parse.urlencode({
            "code": code,
            "client_id": self.client_id,
            "client_secret": self._client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }).encode("utf-8")

        req = urllib.request.Request(
            GOOGLE_TOKEN_URL,
            data=data,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response_data = self._fetch_json(req, "exchange_code")
        if "access_token" not in response_data:
            raise GoogleOAuthError(
                f"Google token endpoint did not return access_token. "
                f"Response keys: {list(response_data.keys())}"
            )
        return response_data

    # ------------------------------------------------------------------
    # Step 3: get the user's profile
    # ------------------------------------------------------------------
    def get_user_info(self, access_token: str) -> dict[str, Any]:
        """Fetch the user's profile from Google's userinfo endpoint.

        GET https://www.googleapis.com/oauth2/v2/userinfo with the
        ``access_token`` in the Authorization header. Returns the
        user's ``sub`` (Google's stable user ID), ``email``, ``name``,
        ``picture``, ``email_verified``.

        Args:
            access_token: The access_token from ``exchange_code``.

        Returns:
            The parsed JSON response dict.

        Raises:
            GoogleOAuthError: If the HTTP call fails or the response is
                not JSON.
        """
        req = urllib.request.Request(
            GOOGLE_USERINFO_URL,
            method="GET",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return self._fetch_json(req, "get_user_info")

    # ------------------------------------------------------------------
    # Step 4: verify the id_token
    # ------------------------------------------------------------------
    def verify_id_token(
        self,
        id_token: str,
        *,
        expected_audience: Optional[str] = None,
    ) -> dict[str, Any]:
        """Verify a Google id_token + return its claims.

        PHINOX-GOOGLE-OAUTH-MANUAL — stdlib-only verification:
          1. Split the JWT into 3 parts (header.payload.signature).
          2. Base64-decode the payload (stdlib ``base64``).
          3. Check the ``iss`` claim (must be accounts.google.com).
          4. Check the ``aud`` claim (must be our client_id).
          5. Check the ``exp`` claim (must be in the future).
          6. Cross-check the claims via Google's tokeninfo endpoint
             (``GET https://oauth2.googleapis.com/tokeninfo?id_token=...``).
             Google validates the RS256 signature server-side + returns
             the same claims. If Google's response matches our local
             decode, the token is authentic.

        TRADE-OFF: local RS256 signature verification would require the
        ``cryptography`` package (not in requirements/ — adding it
        violates AGENTS.md §2). The tokeninfo cross-check is the
        stdlib-compatible alternative: Google verifies the signature
        server-side, we verify the claims client-side, both must match.
        This is acceptable because:
          (a) The token was obtained directly from Google over HTTPS
              (TLS protects the exchange from MITM).
          (b) The ``state`` parameter (CSRF) + ``aud`` check (token
              audience) prevent cross-app token replay.
          (c) The tokeninfo call is fast (one HTTP GET) + only happens
              on the OAuth callback (not on every request).

        Args:
            id_token: The id_token from ``exchange_code``.
            expected_audience: The expected ``aud`` claim (our client_id).
                If None, defaults to ``self.client_id``.

        Returns:
            The id_token's claims dict (sub, email, name, etc.).

        Raises:
            GoogleOAuthError: If the JWT is malformed, claims don't
                match, the token is expired, or the tokeninfo cross-check
                fails.
        """
        if expected_audience is None:
            expected_audience = self.client_id

        # 1. Split the JWT into 3 parts.
        parts = id_token.split(".")
        if len(parts) != 3:
            raise GoogleOAuthError(
                f"Invalid id_token format: expected 3 parts, got {len(parts)}."
            )

        # 2. Base64-decode the payload (the middle part).
        payload_b64 = parts[1]
        # JWT uses base64url (without padding). Add padding back.
        padding = 4 - (len(payload_b64) % 4)
        if padding != 4:
            payload_b64 += "=" * padding
        try:
            payload_bytes = base64.urlsafe_b64decode(payload_b64)
            claims = json.loads(payload_bytes)
        except (ValueError, json.JSONDecodeError) as exc:
            raise GoogleOAuthError(
                f"Failed to decode id_token payload: {exc}"
            ) from exc

        # 3. Check the ``iss`` claim.
        iss = claims.get("iss", "")
        if iss not in _VALID_ISSUERS:
            raise GoogleOAuthError(
                f"Invalid id_token issuer: {iss!r}. "
                f"Expected one of {sorted(_VALID_ISSUERS)}."
            )

        # 4. Check the ``aud`` claim.
        aud = claims.get("aud", "")
        if aud != expected_audience:
            raise GoogleOAuthError(
                f"Invalid id_token audience: {aud!r}. "
                f"Expected {expected_audience!r}."
            )

        # 5. Check the ``exp`` claim.
        import time
        exp = claims.get("exp")
        if exp is None:
            raise GoogleOAuthError("id_token missing 'exp' claim.")
        if int(exp) < int(time.time()):
            raise GoogleOAuthError("id_token has expired.")

        # 6. Cross-check via Google's tokeninfo endpoint (server-side
        # signature verification — avoids needing local RSA crypto).
        tokeninfo = self._fetch_tokeninfo(id_token)
        # Verify the tokeninfo response's key claims match our local decode.
        # Per دستور §5: don't log the full tokeninfo (may contain the
        # user's email — PII). Only compare key fields.
        for key in ("sub", "email", "iss", "aud"):
            if tokeninfo.get(key) != claims.get(key):
                raise GoogleOAuthError(
                    f"id_token cross-check failed: tokeninfo {key!r} mismatch. "
                    f"Local={claims.get(key)!r} Google={tokeninfo.get(key)!r}."
                )

        logger.info(
            "google_oauth.id_token_verified",
            extra={
                "sub": claims.get("sub"),
                "email_verified": claims.get("email_verified"),
                "iss": claims.get("iss"),
            },
        )
        return claims

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _fetch_json(self, req: urllib.request.Request, context: str) -> dict[str, Any]:
        """Execute a urllib Request + parse the JSON response.

        Args:
            req: The configured urllib.request.Request.
            context: A short label for logging (e.g. "exchange_code").

        Returns:
            The parsed JSON response dict.

        Raises:
            GoogleOAuthError: On HTTP error, timeout, or JSON parse error.
        """
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            # HTTP error from Google — read the body for the error message.
            try:
                err_body = exc.read().decode("utf-8")[:500]
            except Exception:
                err_body = "(unreadable)"
            raise GoogleOAuthError(
                f"{context}: HTTP {exc.code} from Google. Body: {err_body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise GoogleOAuthError(
                f"{context}: network error — {exc.reason}"
            ) from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise GoogleOAuthError(
                f"{context}: Google returned non-JSON response. "
                f"First 200 chars: {body[:200]!r}"
            ) from exc

    def _fetch_tokeninfo(self, id_token: str) -> dict[str, Any]:
        """Call Google's tokeninfo endpoint to verify the id_token.

        GET https://oauth2.googleapis.com/tokeninfo?id_token=<id_token>
        Google validates the RS256 signature server-side + returns the
        claims if the token is authentic. Returns 400 if invalid.

        Args:
            id_token: The id_token to verify.

        Returns:
            The claims dict from Google's tokeninfo response.

        Raises:
            GoogleOAuthError: If Google rejects the token (400) or the
                call fails.
        """
        url = f"{GOOGLE_TOKENINFO_URL}?{urllib.parse.urlencode({'id_token': id_token})}"
        req = urllib.request.Request(url, method="GET")
        return self._fetch_json(req, "tokeninfo")


def generate_state() -> str:
    """Generate a cryptographically-secure random state string.

    Uses ``secrets.token_hex(32)`` — 32 bytes → 64 hex chars.
    Per دستور §5: state prevents CSRF in the OAuth flow.

    Returns:
        A 64-character hex string.
    """
    return secrets.token_hex(32)


def verify_state(state_from_request: str, state_from_session: str) -> bool:
    """Verify the OAuth state parameter (CSRF protection).

    Per دستور §5: uses ``hmac.compare_digest`` (constant-time comparison)
    to prevent timing attacks that could leak the expected state value.

    Args:
        state_from_request: The ``state`` query param from Google's callback.
        state_from_session: The ``state`` stored in the user's session.

    Returns:
        True if the states match (constant-time), False otherwise.
    """
    if not state_from_request or not state_from_session:
        return False
    return hmac.compare_digest(
        state_from_request.encode("utf-8"),
        state_from_session.encode("utf-8"),
    )
