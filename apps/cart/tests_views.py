"""
apps.cart.tests_views — Phase 3 view tests for the cart views.

Covers:
  - CartView (read): authenticated + guest + empty states
  - add_to_cart (POST → JSON): auth, guest, GET rejection, CSRF,
    invalid variant
  - update_cart_item (POST): quantity change + invalid item 404
  - remove_cart_item (POST): item deletion + invalid item 404

PHASE-B §B6: tests now use form-encoded POST data (not JSON) because
the cart views read ``request.POST.get(...)`` directly (the views are
HTMX-friendly, not JSON-API). The previous JSON-body tests were sending
data the views never read → all assertions failed.

URL names expected (cart namespace):
  - cart:cart            → /cart/
  - cart:add_to_cart     → /cart/add/
  - cart:update_cart_item → /cart/update/
  - cart:remove_cart_item → /cart/remove/
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, ProductVariant


# ---------------------------------------------------------------------------
# Test factories
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


# ===========================================================================
# CartView (GET /cart/)
# ===========================================================================
class CartViewTest(TestCase):
    """GET /cart/ shows the current user's (or guest session's) cart."""

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

    def test_cart_view_authenticated(self) -> None:
        """Authenticated user sees their cart items."""
        self.client.login(username="buyer", password="pw123456")
        url = reverse("cart:cart")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # The view exposes either the cart or its items in context.
        items = (
            response.context.get("cart_items")
            or response.context.get("items")
            or (response.context.get("cart").items.all()
                if response.context.get("cart")
                else [])
        )
        self.assertGreaterEqual(len(list(items)), 1, "cart items must be in context")

    def test_cart_view_guest(self) -> None:
        """Anonymous user gets a session-key based cart."""
        # Hit the cart view once to seed the session_key. The view's
        # ``get_or_create_cart`` lazily creates a session-key cart for the
        # guest on the first GET — we don't need to manually create one
        # (the original test did that, creating a duplicate that crashed
        # the second GET with MultipleObjectsReturned).
        url = reverse("cart:cart")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        session_key = self.client.session.session_key
        self.assertIsNotNone(session_key, "a guest request must create a session")

        # Fetch the cart that the view just created + add an item to it
        # directly (simulating what add_to_cart would do).
        guest_cart = Cart.objects.get(session_key=session_key)
        CartItem.objects.create(cart=guest_cart, variant=self.variant, quantity=1)

        response2 = self.client.get(url)
        self.assertEqual(response2.status_code, 200)
        # No exception + 200 = guest path served correctly.
        items = (
            response2.context.get("cart_items")
            or response2.context.get("items")
            or (response2.context.get("cart").items.all()
                if response2.context.get("cart")
                else [])
        )
        self.assertGreaterEqual(len(list(items)), 1, "guest cart items must be in context")

    def test_cart_view_empty(self) -> None:
        """An authenticated user with no items still gets 200 + empty state."""
        # New user with an empty cart.
        CustomUser.objects.create_user(username="empty", password="pw123456")
        Cart.objects.create(
            user=CustomUser.objects.get(username="empty")
        )
        self.client.login(username="empty", password="pw123456")

        url = reverse("cart:cart")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        items = (
            response.context.get("cart_items")
            or response.context.get("items")
            or (response.context.get("cart").items.all()
                if response.context.get("cart")
                else [])
        )
        self.assertEqual(len(list(items)), 0, "empty cart must have 0 items")


# ===========================================================================
# add_to_cart (POST /cart/add/) — form-encoded (PHASE-B §B6)
# ===========================================================================
class AddToCartTest(TestCase):
    """POST /cart/add/ creates a CartItem and returns JSON {success: True}.

    PHASE-B §B6: tests now use form-encoded POST data (the view reads
    ``request.POST.get("variant_id")`` directly). Previous JSON-body tests
    were sending data the view never read → all assertions failed.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = CustomUser.objects.create_user(
            username="buyer", password="pw123456"
        )
        cls.category = make_category()
        cls.product = make_product(cls.category)
        cls.variant = make_variant(cls.product, price_extra=Decimal("250"))

    def test_add_to_cart_post(self) -> None:
        """Authenticated POST creates a CartItem + returns JSON success=True."""
        self.client.login(username="buyer", password="pw123456")
        # Get a CSRF token from a prior GET (catalog list — anything that
        # boots the session + CSRF cookie is fine; we use the cart page).
        seed = self.client.get(reverse("cart:cart"))
        csrf = seed.cookies.get("csrftoken", "").value or ""

        url = reverse("cart:add_to_cart")
        # PHASE-B §B6: form-encoded data (no content_type="application/json")
        # so request.POST.get() works. Set X-Requested-With so the view's
        # ``_is_ajax`` check returns True → returns JSON instead of redirect.
        response = self.client.post(
            url,
            data={
                "variant_id": self.variant.id,
                "quantity": 2,
                "csrfmiddlewaretoken": csrf,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_X_CSRFTOKEN=csrf,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("success"), f"unexpected payload: {payload}")
        # CartItem was created with the requested quantity.
        cart = Cart.objects.get(user=self.user)
        item = CartItem.objects.get(cart=cart, variant=self.variant)
        self.assertEqual(item.quantity, 2)

    def test_add_to_cart_get_rejected(self) -> None:
        """GET /cart/add/ is not allowed — must return 405 (or redirect)."""
        self.client.login(username="buyer", password="pw123456")
        url = reverse("cart:add_to_cart")
        response = self.client.get(url)
        self.assertIn(
            response.status_code,
            {405, 302, 403},
            msg=f"GET on add_to_cart must be rejected, got {response.status_code}",
        )

    def test_add_to_cart_csrf_required(self) -> None:
        """POST without a CSRF token is rejected (403) when CSRF is enforced."""
        client = self.client_class(enforce_csrf_checks=True)
        client.login(username="buyer", password="pw123456")

        url = reverse("cart:add_to_cart")
        response = client.post(
            url,
            data={"variant_id": self.variant.id, "quantity": 1},
        )
        self.assertEqual(
            response.status_code,
            403,
            "POST without CSRF token must be rejected",
        )

    def test_add_to_cart_invalid_variant(self) -> None:
        """POST with an unknown variant_id returns 404 (or an error JSON)."""
        self.client.login(username="buyer", password="pw123456")
        seed = self.client.get(reverse("cart:cart"))
        csrf = seed.cookies.get("csrftoken", "").value or ""

        url = reverse("cart:add_to_cart")
        response = self.client.post(
            url,
            data={
                "variant_id": 999_999,  # non-existent
                "quantity": 1,
                "csrfmiddlewaretoken": csrf,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_X_CSRFTOKEN=csrf,
        )
        # 404 or an error payload — either is acceptable per the task spec.
        self.assertIn(
            response.status_code,
            {404, 400},
            msg=f"invalid variant should 404/400, got {response.status_code}",
        )
        if response.status_code == 200:
            payload = response.json()
            self.assertFalse(
                payload.get("success", True),
                "invalid variant must surface as failure in JSON",
            )

    def test_add_to_cart_guest(self) -> None:
        """Anonymous POST creates a session-key cart and adds the item."""
        client = self.client_class(enforce_csrf_checks=False)
        # Seed a session + CSRF cookie.
        seed = client.get(reverse("cart:cart"))
        csrf = seed.cookies.get("csrftoken", "").value or ""
        session_key = client.session.session_key
        self.assertIsNotNone(session_key)

        url = reverse("cart:add_to_cart")
        response = client.post(
            url,
            data={
                "variant_id": self.variant.id,
                "quantity": 1,
                "csrfmiddlewaretoken": csrf,
            },
            # PHASE-B §B6: set X-Requested-With so the view returns JSON.
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_X_CSRFTOKEN=csrf,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("success"), f"unexpected payload: {payload}")

        # A session-key cart was created and holds the item.
        cart = Cart.objects.get(session_key=session_key)
        self.assertTrue(
            CartItem.objects.filter(cart=cart, variant=self.variant).exists(),
            "guest cart item must be created",
        )


# ===========================================================================
# update_cart_item (POST /cart/update/) — form-encoded (PHASE-B §B6)
# ===========================================================================
class UpdateCartItemTest(TestCase):
    """POST /cart/update/ changes quantity + updates subtotal."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = CustomUser.objects.create_user(
            username="buyer", password="pw123456"
        )
        cls.category = make_category()
        cls.product = make_product(cls.category)
        cls.variant = make_variant(cls.product, price_extra=Decimal("0"))
        cls.cart = Cart.objects.create(user=cls.user)
        cls.item = CartItem.objects.create(
            cart=cls.cart, variant=cls.variant, quantity=1
        )

    def test_update_quantity(self) -> None:
        """Updating the quantity persists + the cart subtotal reflects it."""
        self.client.login(username="buyer", password="pw123456")
        seed = self.client.get(reverse("cart:cart"))
        csrf = seed.cookies.get("csrftoken", "").value or ""

        url = reverse("cart:update_cart_item")
        # PHASE-B §B6: form-encoded data + AJAX header so the view returns JSON.
        response = self.client.post(
            url,
            data={
                "item_id": self.item.id,
                "quantity": 4,
                "csrfmiddlewaretoken": csrf,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_X_CSRFTOKEN=csrf,
        )

        self.assertIn(response.status_code, {200, 302})
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 4)
        # Subtotal: 4 * (base_price 1000 + price_extra 0) = 4000.
        self.assertEqual(self.cart.subtotal, Decimal("4000"))

    def test_update_invalid_item(self) -> None:
        """Updating a non-existent item returns 404 (or error)."""
        self.client.login(username="buyer", password="pw123456")
        seed = self.client.get(reverse("cart:cart"))
        csrf = seed.cookies.get("csrftoken", "").value or ""

        url = reverse("cart:update_cart_item")
        response = self.client.post(
            url,
            data={
                "item_id": 999_999,
                "quantity": 2,
                "csrfmiddlewaretoken": csrf,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertIn(
            response.status_code,
            {404, 400},
            msg=f"update of invalid item must 404/400, got {response.status_code}",
        )


# ===========================================================================
# remove_cart_item (POST /cart/remove/) — form-encoded (PHASE-B §B6)
# ===========================================================================
class RemoveCartItemTest(TestCase):
    """POST /cart/remove/ deletes the item + updates the cart subtotal."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = CustomUser.objects.create_user(
            username="buyer", password="pw123456"
        )
        cls.category = make_category()
        cls.product = make_product(cls.category)
        cls.variant = make_variant(cls.product, price_extra=Decimal("0"))
        cls.cart = Cart.objects.create(user=cls.user)

    def test_remove_item(self) -> None:
        """Removing an item deletes it and zeroes the subtotal."""
        item = CartItem.objects.create(
            cart=self.cart, variant=self.variant, quantity=3
        )
        self.client.login(username="buyer", password="pw123456")
        seed = self.client.get(reverse("cart:cart"))
        csrf = seed.cookies.get("csrftoken", "").value or ""

        url = reverse("cart:remove_cart_item")
        # PHASE-B §B6: form-encoded data + AJAX header so the view returns JSON.
        response = self.client.post(
            url,
            data={
                "item_id": item.id,
                "csrfmiddlewaretoken": csrf,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_X_CSRFTOKEN=csrf,
        )

        self.assertIn(response.status_code, {200, 302})
        self.assertFalse(
            CartItem.objects.filter(id=item.id).exists(),
            "item must be deleted",
        )
        # Cart is now empty → subtotal 0.
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.subtotal, Decimal("0"))

    def test_remove_invalid_item(self) -> None:
        """Removing a non-existent item returns 404."""
        self.client.login(username="buyer", password="pw123456")
        seed = self.client.get(reverse("cart:cart"))
        csrf = seed.cookies.get("csrftoken", "").value or ""

        url = reverse("cart:remove_cart_item")
        response = self.client.post(
            url,
            data={
                "item_id": 999_999,
                "csrfmiddlewaretoken": csrf,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertIn(
            response.status_code,
            {404, 400},
            msg=f"remove of invalid item must 404/400, got {response.status_code}",
        )
