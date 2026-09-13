"""apps.accounts — tests for Google OAuth 2.0 (PHINOX-GOOGLE-OAUTH-MANUAL).

Covers:
  - GoogleOAuthClient.build_auth_url — correct URL + params.
  - GoogleOAuthClient.exchange_code — mocked urllib call.
  - GoogleOAuthClient.get_user_info — mocked urllib call.
  - GoogleOAuthClient.verify_id_token — JWT payload decode + claim checks.
  - generate_state + verify_state — CSRF protection.
  - GoogleLoginView — 404 when GOOGLE_CLIENT_ID is empty; 302 redirect when set.
  - GoogleCallbackView — state mismatch redirect; missing code redirect.
  - GoogleCallbackView._find_or_create_user — finds existing user by email;
    creates new user with unusable password + is_active=True.

Per دستور §5: never make real network calls in tests. All urllib calls
are mocked via unittest.mock.patch.
"""
from __future__ import annotations

import base64
import json
import time
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.google_oauth import (
    GoogleOAuthClient,
    GoogleOAuthError,
    generate_state,
    verify_state,
)
from apps.accounts.models import CustomUser


# ── Helpers ────────────────────────────────────────────────────────────────
TEST_CLIENT_ID = "test-google-client-id.apps.googleusercontent.com"
TEST_CLIENT_SECRET = "test-google-client-secret-GOCSPX"
TEST_REDIRECT_URI = "http://localhost:8000/accounts/google/callback/"


def _make_id_token(*, sub="12345", email="user@test.local", iss="https://accounts.google.com",
                  aud=TEST_CLIENT_ID, exp_delta=3600, name="Test User") -> str:
    """Build a fake Google id_token JWT for testing.

    The signature is fake (we're not verifying it locally — we cross-check
    via the mocked tokeninfo endpoint). The payload is real JSON.
    """
    header = {"alg": "RS256", "kid": "test-key-id", "typ": "JWT"}
    payload = {
        "sub": sub,
        "email": email,
        "email_verified": True,
        "name": name,
        "iss": iss,
        "aud": aud,
        "exp": int(time.time()) + exp_delta,
        "iat": int(time.time()),
    }

    def _b64(d: dict) -> str:
        b = json.dumps(d).encode("utf-8")
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")

    return f"{_b64(header)}.{_b64(payload)}.fake-signature"


def _mock_urlopen(resp_body: dict, status: int = 200):
    """Build a MagicMock that mimics urllib.request.urlopen."""
    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read = MagicMock(return_value=json.dumps(resp_body).encode("utf-8"))
    mock_resp.getcode = MagicMock(return_value=status)
    return mock_resp


# ===========================================================================
# GoogleOAuthClient unit tests
# ===========================================================================
class GoogleOAuthClientTests(TestCase):
    def setUp(self) -> None:
        self.client = GoogleOAuthClient(
            client_id=TEST_CLIENT_ID,
            client_secret=TEST_CLIENT_SECRET,
            redirect_uri=TEST_REDIRECT_URI,
        )

    def test_build_auth_url_contains_required_params(self) -> None:
        """build_auth_url returns a URL with client_id, redirect_uri, scope, state."""
        url = self.client.build_auth_url(state="test-state-123")
        self.assertIn("https://accounts.google.com/o/oauth2/v2/auth", url)
        self.assertIn(f"client_id={TEST_CLIENT_ID}", url)
        self.assertIn("redirect_uri=", url)
        self.assertIn("response_type=code", url)
        # urllib.parse.urlencode encodes spaces as '+'; the scope is
        # "openid email profile" → "openid+email+profile".
        self.assertIn("scope=openid+email+profile", url)
        self.assertIn("state=test-state-123", url)
        self.assertIn("prompt=select_account", url)

    @patch("apps.accounts.google_oauth.urllib.request.urlopen")
    def test_exchange_code_returns_token_response(self, mock_urlopen: MagicMock) -> None:
        """exchange_code parses the JSON response from Google's token endpoint."""
        mock_urlopen.return_value = _mock_urlopen({
            "access_token": "test-access-token",
            "id_token": _make_id_token(),
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "openid email profile",
        })
        response = self.client.exchange_code("test-auth-code")
        self.assertEqual(response["access_token"], "test-access-token")
        self.assertIn("id_token", response)

    @patch("apps.accounts.google_oauth.urllib.request.urlopen")
    def test_exchange_code_raises_on_missing_access_token(self, mock_urlopen: MagicMock) -> None:
        """exchange_code raises GoogleOAuthError if access_token is missing."""
        mock_urlopen.return_value = _mock_urlopen({"error": "invalid_grant"})
        with self.assertRaises(GoogleOAuthError):
            self.client.exchange_code("bad-code")

    @patch("apps.accounts.google_oauth.urllib.request.urlopen")
    def test_get_user_info_returns_parsed_json(self, mock_urlopen: MagicMock) -> None:
        """get_user_info parses the JSON userinfo response."""
        mock_urlopen.return_value = _mock_urlopen({
            "id": "12345",
            "email": "user@test.local",
            "verified_email": True,
            "name": "Test User",
            "picture": "https://lh3.googleusercontent.com/photo.jpg",
        })
        user_info = self.client.get_user_info("test-access-token")
        self.assertEqual(user_info["email"], "user@test.local")
        self.assertEqual(user_info["id"], "12345")

    @patch("apps.accounts.google_oauth.urllib.request.urlopen")
    def test_verify_id_token_decodes_payload_and_checks_claims(self, mock_urlopen: MagicMock) -> None:
        """verify_id_token decodes the JWT + checks iss/aud/exp + cross-checks tokeninfo."""
        id_token = _make_id_token(aud=TEST_CLIENT_ID)
        # Mock both _fetch_json calls (tokeninfo cross-check).
        mock_urlopen.return_value = _mock_urlopen({
            "sub": "12345",
            "email": "user@test.local",
            "iss": "https://accounts.google.com",
            "aud": TEST_CLIENT_ID,
        })
        claims = self.client.verify_id_token(id_token)
        self.assertEqual(claims["sub"], "12345")
        self.assertEqual(claims["email"], "user@test.local")
        self.assertEqual(claims["aud"], TEST_CLIENT_ID)

    def test_verify_id_token_rejects_wrong_audience(self) -> None:
        """verify_id_token raises if aud != our client_id."""
        id_token = _make_id_token(aud="some-other-client-id")
        # No need to mock urlopen — the aud check happens before the tokeninfo call.
        with self.assertRaises(GoogleOAuthError) as ctx:
            self.client.verify_id_token(id_token)
        self.assertIn("audience", str(ctx.exception))

    def test_verify_id_token_rejects_expired_token(self) -> None:
        """verify_id_token raises if exp is in the past."""
        id_token = _make_id_token(exp_delta=-3600)  # expired 1h ago
        with self.assertRaises(GoogleOAuthError) as ctx:
            self.client.verify_id_token(id_token)
        self.assertIn("expired", str(ctx.exception).lower())

    def test_verify_id_token_rejects_wrong_issuer(self) -> None:
        """verify_id_token raises if iss is not accounts.google.com."""
        id_token = _make_id_token(iss="https://evil.com")
        with self.assertRaises(GoogleOAuthError) as ctx:
            self.client.verify_id_token(id_token)
        self.assertIn("issuer", str(ctx.exception).lower())

    def test_verify_id_token_rejects_malformed_jwt(self) -> None:
        """verify_id_token raises if the JWT has fewer than 3 parts."""
        with self.assertRaises(GoogleOAuthError):
            self.client.verify_id_token("not-a-jwt")


# ===========================================================================
# State generation + verification (CSRF protection)
# ===========================================================================
class StateTests(TestCase):
    def test_generate_state_is_64_chars_hex(self) -> None:
        """generate_state returns a 64-char hex string (32 bytes)."""
        state = generate_state()
        self.assertEqual(len(state), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in state))

    def test_generate_state_is_unique(self) -> None:
        """Two calls to generate_state return different values."""
        self.assertNotEqual(generate_state(), generate_state())

    def test_verify_state_matches(self) -> None:
        """verify_state returns True when the states match."""
        state = generate_state()
        self.assertTrue(verify_state(state, state))

    def test_verify_state_mismatch(self) -> None:
        """verify_state returns False when the states don't match."""
        self.assertFalse(verify_state("state-a", "state-b"))

    def test_verify_state_empty(self) -> None:
        """verify_state returns False if either state is empty."""
        self.assertFalse(verify_state("", "abc"))
        self.assertFalse(verify_state("abc", ""))
        self.assertFalse(verify_state("", ""))


# ===========================================================================
# GoogleLoginView tests
# ===========================================================================
class GoogleLoginViewTest(TestCase):
    def test_google_login_404_when_not_configured(self) -> None:
        """GoogleLoginView returns 404 when GOOGLE_CLIENT_ID is empty."""
        # Default settings: GOOGLE_CLIENT_ID is empty.
        response = self.client.get(reverse("accounts:google_login"))
        self.assertEqual(response.status_code, 404)

    @override_settings(
        GOOGLE_CLIENT_ID=TEST_CLIENT_ID,
        GOOGLE_CLIENT_SECRET=TEST_CLIENT_SECRET,
        GOOGLE_REDIRECT_URI=TEST_REDIRECT_URI,
    )
    def test_google_login_redirects_to_google_when_configured(self) -> None:
        """GoogleLoginView redirects to Google's consent screen + stores state in session."""
        response = self.client.get(reverse("accounts:google_login"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("accounts.google.com/o/oauth2/v2/auth", response.url)
        self.assertIn(f"client_id={TEST_CLIENT_ID}", response.url)
        # State should be stored in the session.
        self.assertIn("google_oauth_state", self.client.session)
        self.assertEqual(len(self.client.session["google_oauth_state"]), 64)


# ===========================================================================
# GoogleCallbackView tests
# ===========================================================================
@override_settings(
    GOOGLE_CLIENT_ID=TEST_CLIENT_ID,
    GOOGLE_CLIENT_SECRET=TEST_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI=TEST_REDIRECT_URI,
)
class GoogleCallbackViewTest(TestCase):
    def test_callback_missing_code_redirects_to_login(self) -> None:
        """If the callback has no 'code' param, redirect to login with an error."""
        response = self.client.get(reverse("accounts:google_callback"), {"state": "abc"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response.url)

    def test_callback_state_mismatch_redirects_to_login(self) -> None:
        """If state doesn't match the session value, redirect to login with an error."""
        # Set a state in the session that won't match.
        session = self.client.session
        session["google_oauth_state"] = "session-state-xyz"
        session.save()

        response = self.client.get(reverse("accounts:google_callback"), {
            "code": "test-code",
            "state": "wrong-state",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response.url)

    @patch("apps.accounts.google_oauth.urllib.request.urlopen")
    def test_callback_creates_new_user_and_logs_them_in(self, mock_urlopen: MagicMock) -> None:
        """A new Google user is created with is_active=True + logged in."""
        # Set the state in the session first.
        session = self.client.session
        session["google_oauth_state"] = "test-state-abc"
        session.save()

        id_token = _make_id_token(email="newuser@test.local")

        # URL-based mock dispatch — each endpoint returns its matching
        # response based on the request URL. This is more robust than
        # side_effect lists (which are order-dependent).
        def _urlopen_side_effect(req, *args, **kwargs):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "oauth2.googleapis.com/token" in url and req.method == "POST":
                return _mock_urlopen({
                    "access_token": "test-access-token",
                    "id_token": id_token,
                })
            elif "oauth2.googleapis.com/tokeninfo" in url:
                return _mock_urlopen({
                    "sub": "12345",
                    "email": "newuser@test.local",
                    "iss": "https://accounts.google.com",
                    "aud": TEST_CLIENT_ID,
                })
            elif "googleapis.com/oauth2/v2/userinfo" in url:
                return _mock_urlopen({
                    "id": "12345",
                    "email": "newuser@test.local",
                    "verified_email": True,
                    "name": "New User",
                    "picture": "https://lh3.googleusercontent.com/photo.jpg",
                })
            return _mock_urlopen({})

        mock_urlopen.side_effect = _urlopen_side_effect

        response = self.client.get(reverse("accounts:google_callback"), {
            "code": "test-auth-code",
            "state": "test-state-abc",
        })
        self.assertEqual(response.status_code, 302)

        # User was created.
        user = CustomUser.objects.filter(email="newuser@test.local").first()
        self.assertIsNotNone(user)
        self.assertTrue(user.is_active)  # Google pre-verified the email.
        self.assertFalse(user.has_usable_password())  # Can only log in via Google.

        # User is logged in (session has _auth_user_id).
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    @patch("apps.accounts.google_oauth.urllib.request.urlopen")
    def test_callback_logs_in_existing_user(self, mock_urlopen: MagicMock) -> None:
        """An existing user with the same email is logged in (linked)."""
        existing_user = CustomUser.objects.create_user(
            username="existing", password="pw123456", email="existing@test.local"
        )
        # Set the state.
        session = self.client.session
        session["google_oauth_state"] = "test-state-def"
        session.save()

        id_token = _make_id_token(email="existing@test.local", sub="67890")

        # URL-based mock dispatch.
        def _urlopen_side_effect(req, *args, **kwargs):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "oauth2.googleapis.com/token" in url and req.method == "POST":
                return _mock_urlopen({"access_token": "test-access-token", "id_token": id_token})
            elif "oauth2.googleapis.com/tokeninfo" in url:
                return _mock_urlopen({
                    "sub": "67890", "email": "existing@test.local",
                    "iss": "https://accounts.google.com", "aud": TEST_CLIENT_ID,
                })
            elif "googleapis.com/oauth2/v2/userinfo" in url:
                return _mock_urlopen({
                    "id": "67890", "email": "existing@test.local",
                    "verified_email": True, "name": "Existing User",
                })
            return _mock_urlopen({})

        mock_urlopen.side_effect = _urlopen_side_effect

        response = self.client.get(reverse("accounts:google_callback"), {
            "code": "test-auth-code",
            "state": "test-state-def",
        })
        self.assertEqual(response.status_code, 302)

        # No new user was created (still just the one).
        self.assertEqual(CustomUser.objects.filter(email__iexact="existing@test.local").count(), 1)

        # The existing user is logged in.
        self.assertEqual(int(self.client.session["_auth_user_id"]), existing_user.pk)
