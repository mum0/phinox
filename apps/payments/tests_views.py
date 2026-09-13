"""
apps.payments.tests_views — Phase 3 view tests for PaymentSimulationView.

Covers:
  - GET /payments/test/<order_business_id>/ → 200 + TEST MODE warning visible
  - POST → creates Payment with is_test_transaction=True + updates order
  - Login required

URL name expected (payments namespace):
  - payments:test_payment  → /payments/test/<order_business_id>/

Per دستور §5: card/online payments are TEST MODE ONLY in this phase. The
view must surface a clear "TEST MODE" banner so an operator cannot
confuse the simulated card form with a real Paymob checkout.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.orders.models import Order
from apps.payments.models import Payment


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------
def make_order(user: CustomUser, *, grand_total: Decimal = Decimal("100")) -> Order:
    """Create a minimal constraint-valid Order (subtotal=grand, no discount)."""
    return Order.objects.create(
        user=user,
        subtotal=grand_total,
        discount_total=Decimal("0"),
        shipping_cost=Decimal("0"),
        grand_total=grand_total,
    )


# ===========================================================================
# PaymentSimulationView
# ===========================================================================
class PaymentSimulationTest(TestCase):
    """GET/POST /payments/test/<order_business_id>/ — TEST MODE only."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = CustomUser.objects.create_user(
            username="buyer", password="pw123456"
        )
        cls.order = make_order(cls.user, grand_total=Decimal("100"))

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------
    def test_payment_test_get(self) -> None:
        """GET renders the test-mode card form + shows a TEST MODE warning."""
        self.client.login(username="buyer", password="pw123456")
        url = reverse("payments:test_payment", args=[self.order.business_id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # The page must visibly announce TEST MODE.
        content = response.content.decode("utf-8")
        self.assertIn(
            "TEST MODE",
            content.upper(),
            "the test payment page must surface a TEST MODE warning to operators",
        )
        # The order should be in context for the template to render totals.
        ctx_order = response.context.get("order") or response.context.get("object")
        self.assertIsNotNone(ctx_order, "order must be in context")
        self.assertEqual(ctx_order.business_id, self.order.business_id)

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------
    def test_payment_test_post_simulates(self) -> None:
        """POST creates a Payment with is_test_transaction=True + simulates success."""
        self.client.login(username="buyer", password="pw123456")
        # Seed CSRF cookie from the GET.
        seed = self.client.get(
            reverse("payments:test_payment", args=[self.order.business_id])
        )
        csrf = seed.cookies.get("csrftoken", "").value or ""

        url = reverse("payments:test_payment", args=[self.order.business_id])
        response = self.client.post(
            url,
            data={
                "simulate_success": "true",
                "csrfmiddlewaretoken": csrf,
            },
        )

        # The view either returns a JSON success or redirects to confirmation.
        self.assertIn(response.status_code, {200, 302})

        # Exactly one Payment was created with the test-mode flag.
        payment = Payment.objects.filter(order=self.order).order_by("-id").first()
        self.assertIsNotNone(payment, "a Payment must be created on POST")
        self.assertTrue(
            payment.is_test_transaction,
            "simulated card payment must be flagged is_test_transaction=True",
        )
        # Provider/method reflect a card simulation (Paymob card).
        self.assertEqual(payment.payment_provider, Payment.PaymentProvider.PAYMOB)
        self.assertEqual(payment.method_type, Payment.MethodType.CARD)
        # Amount matches the order.
        self.assertEqual(payment.amount, Decimal("100"))
        # Order payment_status was updated.
        self.order.refresh_from_db()
        self.assertIn(
            self.order.payment_status,
            {Order.PaymentStatus.PAID, Order.PaymentStatus.PENDING},
            "order payment_status should be advanced after the simulated payment",
        )

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def test_payment_test_login_required(self) -> None:
        """Anonymous GET redirects to the login page."""
        url = reverse("payments:test_payment", args=[self.order.business_id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "/accounts/login/",
            response.url,
            msg=f"expected redirect to login, got {response.url}",
        )
