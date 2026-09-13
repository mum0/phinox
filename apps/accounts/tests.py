"""
apps.accounts — tests for CustomUser stable customer_id generation.

Covers:
  - customer_id sequential generation (PHX-CUS-000001, PHX-CUS-000002)
  - customer_id immutability
  - phone field is optional
"""
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import CustomUser


class CustomUserIDTests(TestCase):
    def test_customer_id_sequential(self) -> None:
        """customer_id is sequential: PHX-CUS-000001, PHX-CUS-000002."""
        u1 = CustomUser.objects.create_user(username="alice", password="pw123456")
        u2 = CustomUser.objects.create_user(username="bob", password="pw123456")
        u3 = CustomUser.objects.create_user(username="carol", password="pw123456")

        self.assertEqual(u1.customer_id, "PHX-CUS-000001")
        self.assertEqual(u2.customer_id, "PHX-CUS-000002")
        self.assertEqual(u3.customer_id, "PHX-CUS-000003")

    def test_customer_id_format(self) -> None:
        """customer_id matches the PHX-CUS-000001 format."""
        u = CustomUser.objects.create_user(username="user1", password="pw123456")
        self.assertRegex(u.customer_id, r"^PHX-CUS-\d{6}$")

    def test_customer_id_immutable(self) -> None:
        """customer_id does not change on subsequent saves."""
        u = CustomUser.objects.create_user(username="alice", password="pw123456")
        original = u.customer_id
        u.email = "alice@example.com"
        u.save()
        u.refresh_from_db()
        self.assertEqual(u.customer_id, original)

    def test_customer_id_unique(self) -> None:
        """customer_id must be unique."""
        u1 = CustomUser.objects.create_user(username="alice", password="pw123456")
        u2 = CustomUser.objects.create_user(username="bob", password="pw123456")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                u2.customer_id = u1.customer_id
                u2.save(update_fields=["customer_id"])


class CustomUserFieldTests(TestCase):
    def test_phone_optional(self) -> None:
        """phone field is optional (blank=True)."""
        u = CustomUser.objects.create_user(username="nopw", password="pw123456")
        self.assertEqual(u.phone, "")

    def test_phone_set(self) -> None:
        u = CustomUser.objects.create_user(
            username="phoneuser",
            password="pw123456",
            phone="+201012345678",
        )
        self.assertEqual(u.phone, "+201012345678")

    def test_str_representation(self) -> None:
        u = CustomUser.objects.create_user(username="alice", password="pw123456")
        self.assertEqual(str(u), f"{u.customer_id} — alice")

    def test_timestamps_present(self) -> None:
        """AbstractUser lacks created_at/updated_at; CustomUser adds them."""
        u = CustomUser.objects.create_user(username="ts", password="pw123456")
        self.assertIsNotNone(u.created_at)
        self.assertIsNotNone(u.updated_at)
