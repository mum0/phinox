"""
apps.cart — tests for Cart + CartItem.

Covers:
  - Cart.subtotal computed property (sum of variant.unit_price * quantity)
  - user XOR session_key exclusivity (CheckConstraint)
  - UniqueConstraint: one CartItem per (cart, variant)
  - CartItem.quantity >= 1 (CheckConstraint)
  - Cart business_id generation (PHX-CART-000001)
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import CustomUser
from apps.catalog.models import Category, Product, ProductVariant
from apps.cart.models import Cart, CartItem


class CartSubtotalTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = CustomUser.objects.create_user(username="buyer", password="pw123456")
        cls.category = Category.objects.create(name="Winter", family_code="WNT")
        cls.product = Product.objects.create(
            name="Wool Coat",
            category=cls.category,
            base_price=Decimal("1000"),
            status=Product.Status.ACTIVE,
        )
        cls.variant_1 = ProductVariant.objects.create(
            product=cls.product, price_extra=Decimal("0")
        )  # unit_price = 1000
        cls.variant_2 = ProductVariant.objects.create(
            product=cls.product, price_extra=Decimal("250")
        )  # unit_price = 1250

    def test_cart_subtotal(self) -> None:
        """subtotal = sum(variant.unit_price * quantity)."""
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, variant=self.variant_1, quantity=2)  # 2 * 1000 = 2000
        CartItem.objects.create(cart=cart, variant=self.variant_2, quantity=1)  # 1 * 1250 = 1250

        self.assertEqual(cart.subtotal, Decimal("3250"))

    def test_cart_subtotal_empty(self) -> None:
        """Empty cart has subtotal = 0."""
        cart = Cart.objects.create(user=self.user)
        self.assertEqual(cart.subtotal, Decimal("0"))

    def test_cart_subtotal_single_item(self) -> None:
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, variant=self.variant_1, quantity=3)
        self.assertEqual(cart.subtotal, Decimal("3000"))


class CartUserXORSessionTests(TestCase):
    def test_user_only_cart_allowed(self) -> None:
        user = CustomUser.objects.create_user(username="u1", password="pw123456")
        cart = Cart.objects.create(user=user)
        self.assertEqual(cart.user, user)
        self.assertIsNone(cart.session_key)

    def test_session_only_cart_allowed(self) -> None:
        cart = Cart.objects.create(session_key="abc123")
        self.assertIsNone(cart.user)
        self.assertEqual(cart.session_key, "abc123")

    def test_user_xor_session_exclusive(self) -> None:
        """CheckConstraint cart_user_xor_session_exclusive rejects both set."""
        user = CustomUser.objects.create_user(username="both", password="pw123456")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Cart.objects.create(user=user, session_key="should-not-be-set")

    def test_neither_user_nor_session_rejected(self) -> None:
        """CheckConstraint rejects a cart with neither user nor session_key."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Cart.objects.create()

    def test_user_cart_one_to_one(self) -> None:
        """OneToOneField: only one cart per user."""
        user = CustomUser.objects.create_user(username="only", password="pw123456")
        Cart.objects.create(user=user)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Cart.objects.create(user=user)


class CartItemUniquePerVariantTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = CustomUser.objects.create_user(username="buyer", password="pw123456")
        cls.category = Category.objects.create(name="Winter", family_code="WNT")
        cls.product = Product.objects.create(
            name="Coat",
            category=cls.category,
            base_price=Decimal("500"),
            status=Product.Status.ACTIVE,
        )
        cls.variant = ProductVariant.objects.create(product=cls.product)
        cls.cart = Cart.objects.create(user=cls.user)

    def test_unique_cartitem_per_variant(self) -> None:
        """UniqueConstraint uniq_cartitem_per_variant blocks duplicate (cart, variant)."""
        CartItem.objects.create(cart=self.cart, variant=self.variant, quantity=1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CartItem.objects.create(cart=self.cart, variant=self.variant, quantity=2)

    def test_same_variant_in_different_carts_allowed(self) -> None:
        """Same variant can appear in different carts."""
        CartItem.objects.create(cart=self.cart, variant=self.variant, quantity=1)
        user2 = CustomUser.objects.create_user(username="u2", password="pw123456")
        cart2 = Cart.objects.create(user=user2)
        item2 = CartItem.objects.create(cart=cart2, variant=self.variant, quantity=1)
        self.assertEqual(item2.quantity, 1)

    def test_cartitem_quantity_gte_1(self) -> None:
        """CheckConstraint cartitem_quantity_gte_1 rejects quantity < 1."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CartItem.objects.create(cart=self.cart, variant=self.variant, quantity=0)


class CartBusinessIDTests(TestCase):
    def test_cart_business_id(self) -> None:
        """Cart business_id is PHX-CART-000001, then 000002."""
        user1 = CustomUser.objects.create_user(username="u1", password="pw123456")
        user2 = CustomUser.objects.create_user(username="u2", password="pw123456")
        c1 = Cart.objects.create(user=user1)
        c2 = Cart.objects.create(user=user2)
        self.assertEqual(c1.business_id, "PHX-CART-000001")
        self.assertEqual(c2.business_id, "PHX-CART-000002")

    def test_cart_business_id_format(self) -> None:
        cart = Cart.objects.create(session_key="sess1")
        self.assertRegex(cart.business_id, r"^PHX-CART-\d{6}$")
