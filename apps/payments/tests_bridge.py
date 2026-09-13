"""apps.payments.tests_bridge — Phase 4 Part 2 bridge tests.

Tests the ``initialize_paymob_payment`` bridge that connects
``PaymobClient`` to the ``Payment`` model, and the view's ability to
switch between simulation and real Paymob mode.

Covers:
  - Simulation mode raises PaymobDisabledError.
  - Sandbox mode creates a Payment + calls PaymobClient methods.
  - View redirects to iframe URL in sandbox mode.
  - PaymobAPIError is handled gracefully (no 500 crash).
  - Simulation mode in view falls back to simulate_card_payment.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.payments.paymob_client import PaymobAPIError
from apps.payments.services import PaymobDisabledError, initialize_paymob_payment


def _make_order(user: CustomUser) -> Order:
    return Order.objects.create(
        user=user,
        subtotal=Decimal("2500"),
        discount_total=Decimal("0"),
        shipping_cost=Decimal("0"),
        grand_total=Decimal("2500"),
    )


class InitializePaymobPaymentTest(TestCase):
    """Tests for apps.payments.services.initialize_paymob_payment."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = CustomUser.objects.create_user(
            username="buyer", password="pw123456", email="buyer@test.local"
        )
        cls.order = _make_order(cls.user)

    @override_settings(PAYMOB_MODE="simulation")
    def test_simulation_mode_raises_error(self) -> None:
        """When PAYMOB_MODE=simulation, PaymobDisabledError is raised."""
        with self.assertRaises(PaymobDisabledError):
            initialize_paymob_payment(self.order)

    @override_settings(
        PAYMOB_MODE="sandbox",
        PAYMOB_API_KEY="test_key",
        PAYMOB_INTEGRATION_ID="123",
        PAYMOB_IFRAME_ID="456",
        PAYMOB_SANDBOX=True,
    )
    @patch("apps.payments.paymob_client.PaymobClient")
    def test_paymob_mode_creates_payment(self, mock_client_cls: MagicMock) -> None:
        """In sandbox mode, a Payment row is created with status=PENDING."""
        mock_client = mock_client_cls.return_value
        mock_client.register_order.return_value = 987654
        mock_client.get_payment_key.return_value = "payment_token_xyz"
        mock_client.build_iframe_url.return_value = "https://accept.paymob.com/api/accept/iframes/456?payment_token=payment_token_xyz"

        payment, iframe_url = initialize_paymob_payment(self.order)

        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.payment_provider, Payment.PaymentProvider.PAYMOB)
        self.assertEqual(payment.method_type, Payment.MethodType.CARD)
        self.assertTrue(payment.is_test_transaction)  # sandbox = test
        # PHASE-A §A4: initialize_paymob_payment stores the Paymob order ID
        # in ``paymob_order_id`` (NOT ``provider_transaction_id``). The
        # webhook later populates ``provider_transaction_id`` with the
        # actual transaction ID after capture.
        self.assertEqual(payment.paymob_order_id, "987654")
        self.assertIsNone(payment.provider_transaction_id)
        self.assertIn("payment_token_xyz", iframe_url)

    @override_settings(
        PAYMOB_MODE="sandbox",
        PAYMOB_API_KEY="test_key",
        PAYMOB_INTEGRATION_ID="123",
        PAYMOB_IFRAME_ID="456",
        PAYMOB_SANDBOX=True,
    )
    @patch("apps.payments.paymob_client.PaymobClient")
    def test_register_order_called(self, mock_client_cls: MagicMock) -> None:
        """register_order is called with the correct merchant_order_id."""
        mock_client = mock_client_cls.return_value
        mock_client.register_order.return_value = 111
        mock_client.get_payment_key.return_value = "token"
        mock_client.build_iframe_url.return_value = "https://example.com"

        initialize_paymob_payment(self.order)

        mock_client.register_order.assert_called_once()
        call_kwargs = mock_client.register_order.call_args
        self.assertEqual(call_kwargs.kwargs["merchant_order_id"], self.order.business_id)

    @override_settings(
        PAYMOB_MODE="sandbox",
        PAYMOB_API_KEY="test_key",
        PAYMOB_INTEGRATION_ID="123",
        PAYMOB_IFRAME_ID="456",
        PAYMOB_SANDBOX=True,
    )
    @patch("apps.payments.paymob_client.PaymobClient")
    def test_paymob_api_failure_handled(self, mock_client_cls: MagicMock) -> None:
        """When PaymobClient raises PaymobAPIError, it propagates to the caller."""
        mock_client = mock_client_cls.return_value
        mock_client.register_order.side_effect = PaymobAPIError("API down")
        with self.assertRaises(PaymobAPIError):
            initialize_paymob_payment(self.order)


class PaymentViewBridgeTest(TestCase):
    """Tests for the view's ability to switch between sim and real Paymob."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = CustomUser.objects.create_user(
            username="buyer", password="pw123456"
        )
        cls.order = _make_order(cls.user)

    @override_settings(PAYMOB_MODE="simulation")
    def test_simulation_mode_uses_simulate_flow(self) -> None:
        """In simulation mode, POST creates a test Payment (not real Paymob)."""
        self.client.login(username="buyer", password="pw123456")
        url = reverse("payments:test_payment", args=[self.order.business_id])
        response = self.client.post(url, data={"simulate_success": "true"})
        self.assertIn(response.status_code, {200, 302})
        payment = Payment.objects.filter(order=self.order).first()
        self.assertIsNotNone(payment)
        self.assertTrue(payment.is_test_transaction)

    @override_settings(
        PAYMOB_MODE="sandbox",
        PAYMOB_API_KEY="test_key",
        PAYMOB_INTEGRATION_ID="123",
        PAYMOB_IFRAME_ID="456",
        PAYMOB_SANDBOX=True,
    )
    @patch("apps.payments.views.initialize_paymob_payment")
    def test_redirect_to_iframe(self, mock_init: MagicMock) -> None:
        """In sandbox mode, POST redirects to the Paymob iframe URL."""
        mock_payment = MagicMock()
        mock_payment.business_id = "PHX-PAY-000001"
        mock_init.return_value = (mock_payment, "https://accept.paymob.com/api/accept/iframes/456?payment_token=abc")

        self.client.login(username="buyer", password="pw123456")
        url = reverse("payments:test_payment", args=[self.order.business_id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("accept.paymob.com", response.url)

    @override_settings(
        PAYMOB_MODE="sandbox",
        PAYMOB_API_KEY="test_key",
        PAYMOB_INTEGRATION_ID="123",
        PAYMOB_IFRAME_ID="456",
        PAYMOB_SANDBOX=True,
    )
    @patch("apps.payments.views.initialize_paymob_payment")
    def test_paymob_api_failure_handled_in_view(self, mock_init: MagicMock) -> None:
        """When initialize_paymob_payment raises, view shows error message + redirects."""
        mock_init.side_effect = PaymobAPIError("Paymob is down")

        self.client.login(username="buyer", password="pw123456")
        url = reverse("payments:test_payment", args=[self.order.business_id])
        response = self.client.post(url)

        # View catches the exception and redirects to order confirmation.
        self.assertEqual(response.status_code, 302)
        self.assertIn("confirmation", response.url)
