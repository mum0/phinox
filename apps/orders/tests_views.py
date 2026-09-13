"""
apps.orders.tests_views — Phase 3 view tests for checkout + confirmation.

Covers:
  - CheckoutView (login required, GET form, POST creates order, empty-cart redirect)
  - OrderConfirmationView (shows own order, blocks other users' orders)

URL names expected (orders namespace):
  - orders:checkout            → /checkout/
  - orders:order_confirmation  → /orders/<business_id>/confirmation/

These tests assert the contract the parallel "views + templates" agent's
CheckoutView/OrderConfirmationView must satisfy.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, ProductVariant
from apps.orders.models import Order
from apps.shipping.models import ShippingAddress, ShippingMethod


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------
def make_category(name: str = "Winter", family_code: str = "WNT") -> Category:
    return Category.objects.create(name=name, family_code=family_code)


def make_product(category: Category, name: str = "Wool Coat") -> Product:
    return Product.objects.create(
        name=name,
        category=category,
        base_price=Decimal("1000"),
        status=Product.Status.ACTIVE,
    )


def make_variant(product: Product, price_extra: Decimal = Decimal("0")) -> ProductVariant:
    return ProductVariant.objects.create(product=product, price_extra=price_extra)


def make_shipping_method(
    *, code: str = "STD", price: Decimal = Decimal("50"), name: str = "Standard"
) -> ShippingMethod:
    return ShippingMethod.objects.create(
        name=name,
        code=code,
        price=price,
    )


def make_shipping_address(user: CustomUser) -> ShippingAddress:
    return ShippingAddress.objects.create(
        user=user,
        full_name="Buyer McBuyface",
        phone="+201012345678",
        city="Alexandria",
        country="Egypt",
        address="1 Tahrir Square",
        is_default=True,
    )


# ===========================================================================
# CheckoutView
# ===========================================================================
class CheckoutViewTest(TestCase):
    """GET/POST /checkout/ — login required, form rendering, order creation."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = CustomUser.objects.create_user(
            username="buyer", password="pw123456"
        )
        cls.category = make_category()
        cls.product = make_product(cls.category)
        cls.variant = make_variant(cls.product, price_extra=Decimal("0"))
        cls.cart = Cart.objects.create(user=cls.user)
        cls.cart_item = CartItem.objects.create(
            cart=cls.cart, variant=cls.variant, quantity=2
        )
        cls.shipping_method = make_shipping_method()
        cls.shipping_address = make_shipping_address(cls.user)

    def test_checkout_login_required(self) -> None:
        """Anonymous GET to /checkout/ redirects to the login page."""
        url = reverse("orders:checkout")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "/accounts/login/", response.url,
            msg=f"expected redirect to login, got {response.url}",
        )

    def test_checkout_get(self) -> None:
        """Authenticated GET renders the checkout form."""
        self.client.login(username="buyer", password="pw123456")
        url = reverse("orders:checkout")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Form + shipping addresses + shipping methods should be in context.
        # Tolerate either "form" or "shipping_addresses"/"shipping_methods".
        self.assertIsNotNone(
            response.context.get("form")
            or response.context.get("shipping_addresses"),
            "checkout view must expose a form or shipping data in context",
        )

    def test_checkout_post_creates_order(self) -> None:
        """POST with shipping_address + method + payment=cod creates an Order
        and redirects to the order confirmation page."""
        self.client.login(username="buyer", password="pw123456")
        # Seed CSRF cookie.
        seed = self.client.get(reverse("orders:checkout"))
        csrf = seed.cookies.get("csrftoken", "").value or ""

        url = reverse("orders:checkout")
        response = self.client.post(
            url,
            data={
                # PHASE-B §B6: field names must match CheckoutView.post's
                # request.POST reads (shipping_address_id, shipping_method_id,
                # payment_method). The old test used shipping_address / shipping_method
                # / payment which the view ignored → 302 redirect to checkout.
                "shipping_address_id": self.shipping_address.id,
                "shipping_method_id": self.shipping_method.id,
                "payment_method": "cod",
                "csrfmiddlewaretoken": csrf,
            },
        )

        self.assertEqual(response.status_code, 302, "POST must redirect")
        # An order was created for this user.
        order = Order.objects.filter(user=self.user).order_by("-id").first()
        self.assertIsNotNone(order, "an Order must be created on checkout POST")
        # The redirect target should reference the order's business_id.
        self.assertIn(
            order.business_id,
            response.url,
            msg=f"redirect should reference the new order, got {response.url}",
        )
        # Order has 2 OrderItems (snapshot of the cart).
        self.assertEqual(order.items.count(), 1, "one OrderItem per cart line")
        first_item = order.items.first()
        self.assertEqual(first_item.quantity, 2)
        self.assertEqual(first_item.sku, self.variant.sku)
        # Cart was cleared (the items, not the cart shell).
        self.assertEqual(self.cart.items.count(), 0, "cart must be cleared after checkout")
        # Shipping cost was applied.
        self.assertEqual(order.shipping_cost, Decimal("50"))
        # grand_total = subtotal - discount + shipping = 2000 - 0 + 50 = 2050.
        self.assertEqual(order.grand_total, Decimal("2050"))

    def test_checkout_empty_cart(self) -> None:
        """POSTing checkout with an empty cart redirects to /products/."""
        # Drain the cart.
        self.cart.items.all().delete()
        self.assertEqual(self.cart.items.count(), 0)

        self.client.login(username="buyer", password="pw123456")
        seed = self.client.get(reverse("orders:checkout"))
        csrf = seed.cookies.get("csrftoken", "").value or ""

        url = reverse("orders:checkout")
        response = self.client.post(
            url,
            data={
                # PHASE-B §B6: corrected field names (shipping_address_id, etc.)
                "shipping_address_id": self.shipping_address.id,
                "shipping_method_id": self.shipping_method.id,
                "payment_method": "cod",
                "csrfmiddlewaretoken": csrf,
            },
        )

        self.assertEqual(response.status_code, 302)
        # Should redirect to the products list (the catalog home) —
        # PHASE-B §B6: empty cart → catalog:product_list redirect.
        self.assertTrue(
            response.url.startswith("/products") or "products" in response.url,
            msg=f"empty cart should redirect to products, got {response.url}",
        )
        # No order was created.
        self.assertEqual(Order.objects.filter(user=self.user).count(), 0)


# ===========================================================================
# OrderConfirmationView
# ===========================================================================
class OrderConfirmationViewTest(TestCase):
    """GET /orders/<business_id>/confirmation/ — own order ✓, others ✗."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = CustomUser.objects.create_user(
            username="owner", password="pw123456"
        )
        cls.other = CustomUser.objects.create_user(
            username="other", password="pw123456"
        )
        # Build a minimal valid Order with one OrderItem (so the page can render).
        cls.order = Order.objects.create(
            user=cls.owner,
            subtotal=Decimal("2000"),
            discount_total=Decimal("0"),
            shipping_cost=Decimal("50"),
            grand_total=Decimal("2050"),
            placed_at=timezone.now(),
        )

    def test_confirmation_shows_order(self) -> None:
        """The order owner sees their order on the confirmation page."""
        self.client.login(username="owner", password="pw123456")
        # PHASE-B §B6: URL name is 'orders:confirmation' (not 'order_confirmation').
        url = reverse("orders:confirmation", args=[self.order.business_id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        ctx_order = (
            response.context.get("order")
            or response.context.get("object")
        )
        self.assertIsNotNone(ctx_order, "confirmation page must expose the order")
        self.assertEqual(ctx_order.business_id, self.order.business_id)

    def test_confirmation_wrong_user(self) -> None:
        """A different authenticated user cannot see another user's order."""
        self.client.login(username="other", password="pw123456")
        # PHASE-B §B6: URL name is 'orders:confirmation' (not 'order_confirmation').
        url = reverse("orders:confirmation", args=[self.order.business_id])
        response = self.client.get(url)

        self.assertIn(
            response.status_code,
            {403, 404},
            msg=(
                "wrong-user access to order confirmation must be 403/404, "
                f"got {response.status_code}"
            ),
        )
