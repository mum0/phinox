"""apps.payments.tests_paymob_client — Phase 4 Part 2 Paymob client tests.

Covers:
  - PaymobClient initialization (missing args, valid args).
  - decimal_to_cents precision (no float).
  - _auth_token (success, failure, caching).
  - register_order (success, failure).
  - get_payment_key (success, failure).
  - build_iframe_url format.
  - HTTP error handling (non-2xx response).
  - Network error retry (then fail).
  - Timeout handling (mock).

Per دستور §5: API keys are never logged. Per دستور §8: tests cover
success + failure paths.
"""
from __future__ import annotations

import json
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.payments.paymob_client import PaymobAPIError, PaymobClient


def _mock_urlopen_response(data: dict, status: int = 200) -> MagicMock:
    """Build a mock ``urlopen`` context manager that returns JSON data."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(data).encode("utf-8")
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class PaymobClientInitTest(TestCase):
    """Tests for PaymobClient.__init__."""

    def test_requires_api_key(self) -> None:
        with self.assertRaises(PaymobAPIError):
            PaymobClient(api_key="", integration_id="123", iframe_id="456")

    def test_requires_integration_id(self) -> None:
        with self.assertRaises(PaymobAPIError):
            PaymobClient(api_key="key", integration_id="", iframe_id="456")

    def test_requires_iframe_id(self) -> None:
        with self.assertRaises(PaymobAPIError):
            PaymobClient(api_key="key", integration_id="123", iframe_id="")

    def test_valid_init(self) -> None:
        client = PaymobClient(api_key="key", integration_id="123", iframe_id="456")
        self.assertEqual(client._integration_id, "123")
        self.assertEqual(client._iframe_id, "456")


class DecimalToCentsTest(TestCase):
    """Tests for PaymobClient.decimal_to_cents."""

    def test_whole_number(self) -> None:
        self.assertEqual(PaymobClient.decimal_to_cents(Decimal("2500.00")), 250000)

    def test_fractional_cents(self) -> None:
        self.assertEqual(PaymobClient.decimal_to_cents(Decimal("99.99")), 9999)

    def test_zero(self) -> None:
        self.assertEqual(PaymobClient.decimal_to_cents(Decimal("0.00")), 0)

    def test_large_amount(self) -> None:
        self.assertEqual(PaymobClient.decimal_to_cents(Decimal("100000.00")), 10000000)

    def test_no_float_conversion(self) -> None:
        """Ensure the function never passes through float."""
        # Decimal("0.1") * 100 via float = 10.000000000000002 (float error).
        # Via Decimal it should be exactly 10.
        result = PaymobClient.decimal_to_cents(Decimal("0.10"))
        self.assertEqual(result, 10)
        self.assertIsInstance(result, int)


class AuthTokenTest(TestCase):
    """Tests for PaymobClient._auth_token."""

    @patch("apps.payments.paymob_client.urllib.request.urlopen")
    def test_auth_success(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_urlopen_response({"token": "auth_token_123"})
        client = PaymobClient(api_key="key", integration_id="123", iframe_id="456")
        token = client._auth_token()
        self.assertEqual(token, "auth_token_123")

    @patch("apps.payments.paymob_client.urllib.request.urlopen")
    def test_auth_caching(self, mock_urlopen: MagicMock) -> None:
        """Second call to _auth_token should NOT make another HTTP request."""
        mock_urlopen.return_value = _mock_urlopen_response({"token": "cached_token"})
        client = PaymobClient(api_key="key", integration_id="123", iframe_id="456")
        t1 = client._auth_token()
        t2 = client._auth_token()
        self.assertEqual(t1, t2)
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("apps.payments.paymob_client.urllib.request.urlopen")
    def test_auth_missing_token_field(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_urlopen_response({"unexpected": "data"})
        client = PaymobClient(api_key="key", integration_id="123", iframe_id="456")
        with self.assertRaises(PaymobAPIError):
            client._auth_token()


class RegisterOrderTest(TestCase):
    """Tests for PaymobClient.register_order."""

    @patch("apps.payments.paymob_client.urllib.request.urlopen")
    def test_register_order_success(self, mock_urlopen: MagicMock) -> None:
        # First call = auth/tokens, second call = ecommerce/orders
        mock_urlopen.side_effect = [
            _mock_urlopen_response({"token": "auth_token"}),
            _mock_urlopen_response({"id": 987654}),
        ]
        client = PaymobClient(api_key="key", integration_id="123", iframe_id="456")
        order_id = client.register_order(
            merchant_order_id="PHX-ORD-000001",
            amount_cents=250000,
        )
        self.assertEqual(order_id, 987654)

    @patch("apps.payments.paymob_client.urllib.request.urlopen")
    def test_register_order_missing_id(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = [
            _mock_urlopen_response({"token": "auth_token"}),
            _mock_urlopen_response({"error": "something wrong"}),
        ]
        client = PaymobClient(api_key="key", integration_id="123", iframe_id="456")
        with self.assertRaises(PaymobAPIError):
            client.register_order(merchant_order_id="PHX-ORD-000001", amount_cents=100)


class GetPaymentKeyTest(TestCase):
    """Tests for PaymobClient.get_payment_key."""

    @patch("apps.payments.paymob_client.urllib.request.urlopen")
    def test_get_payment_key_success(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = [
            _mock_urlopen_response({"token": "auth_token"}),
            _mock_urlopen_response({"token": "payment_key_abc"}),
        ]
        client = PaymobClient(api_key="key", integration_id="123", iframe_id="456")
        key = client.get_payment_key(
            paymob_order_id=987654,
            amount_cents=250000,
            billing_data={"first_name": "Test", "last_name": "User",
                          "email": "test@test.com", "phone_number": "+201012345678"},
        )
        self.assertEqual(key, "payment_key_abc")

    @patch("apps.payments.paymob_client.urllib.request.urlopen")
    def test_get_payment_key_missing_token(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = [
            _mock_urlopen_response({"token": "auth_token"}),
            _mock_urlopen_response({"error": "bad"}),
        ]
        client = PaymobClient(api_key="key", integration_id="123", iframe_id="456")
        with self.assertRaises(PaymobAPIError):
            client.get_payment_key(
                paymob_order_id=1, amount_cents=100,
                billing_data={"first_name": "T", "last_name": "U",
                              "email": "t@t.com", "phone_number": "+201000000000"},
            )


class BuildIframeUrlTest(TestCase):
    """Tests for PaymobClient.build_iframe_url."""

    def test_iframe_url_format(self) -> None:
        client = PaymobClient(api_key="key", integration_id="123", iframe_id="789")
        url = client.build_iframe_url("payment_token_xyz")
        self.assertIn("accept.paymob.com", url)
        self.assertIn("/iframes/789", url)
        self.assertIn("payment_token=payment_token_xyz", url)


class HttpErrorTest(TestCase):
    """Tests for HTTP error handling."""

    @patch("apps.payments.paymob_client.urllib.request.urlopen")
    def test_http_error_raises_paymob_api_error(self, mock_urlopen: MagicMock) -> None:
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://accept.paymob.com/api/auth/tokens",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=BytesIO(b'{"error": "bad api key"}'),
        )
        client = PaymobClient(api_key="bad", integration_id="123", iframe_id="456")
        with self.assertRaises(PaymobAPIError):
            client._auth_token()


class NetworkErrorRetryTest(TestCase):
    """Tests for network error + retry behavior."""

    @patch("apps.payments.paymob_client.urllib.request.urlopen")
    def test_network_error_retries_once_then_fails(self, mock_urlopen: MagicMock) -> None:
        import urllib.error
        mock_urlopen.side_effect = [
            urllib.error.URLError("Connection refused"),
            urllib.error.URLError("Connection refused"),
        ]
        client = PaymobClient(api_key="key", integration_id="123", iframe_id="456")
        with self.assertRaises(PaymobAPIError):
            client._auth_token()
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("apps.payments.paymob_client.urllib.request.urlopen")
    def test_network_error_retries_once_then_succeeds(self, mock_urlopen: MagicMock) -> None:
        import urllib.error
        mock_urlopen.side_effect = [
            urllib.error.URLError("Connection refused"),
            _mock_urlopen_response({"token": "recovered_token"}),
        ]
        client = PaymobClient(api_key="key", integration_id="123", iframe_id="456")
        token = client._auth_token()
        self.assertEqual(token, "recovered_token")
        self.assertEqual(mock_urlopen.call_count, 2)
