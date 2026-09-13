"""apps.accounts.tests_auth — Phase 5 + BUGFIX-ROUND-2 auth tests.

Covers:
  - Login: success, fail (wrong password), fail (inactive user).
  - Register: success (is_active=False + verification email), fail (duplicate email).
  - Logout: success (POST).
  - Password reset (email-based): request success, done page.
  - Profile: login required, shows user data.
"""
from __future__ import annotations

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser


class LoginViewTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = CustomUser.objects.create_user(
            username="testuser", password="TestPass123!", email="test@test.local"
        )

    def test_login_success(self) -> None:
        response = self.client.post(reverse("accounts:login"), {
            "username": "testuser", "password": "TestPass123!",
        })
        self.assertEqual(response.status_code, 302)

    def test_login_wrong_password(self) -> None:
        response = self.client.post(reverse("accounts:login"), {
            "username": "testuser", "password": "wrongpassword",
        })
        self.assertEqual(response.status_code, 200)

    def test_login_inactive_user(self) -> None:
        self.user.is_active = False
        self.user.save()
        response = self.client.post(reverse("accounts:login"), {
            "username": "testuser", "password": "TestPass123!",
        })
        self.assertEqual(response.status_code, 200)


class SignupViewTest(TestCase):
    def test_register_success(self) -> None:
        """Registration creates inactive user + redirects to register_done."""
        response = self.client.post(reverse("accounts:register"), {
            "email": "new@test.local",
            "full_name": "New User",
            "mobile_number": "+201012345678",
            "password1": "StrongPass456!",
            "password2": "StrongPass456!",
        })
        self.assertEqual(response.status_code, 302)
        # PHINOX-REGISTER-FIX: now redirects to register_done (the "check your email" page).
        self.assertIn("/accounts/register/done", response.url)
        user = CustomUser.objects.filter(email="new@test.local").first()
        self.assertIsNotNone(user)
        self.assertFalse(user.is_active)  # Must be inactive until verified

    def test_register_duplicate_email(self) -> None:
        CustomUser.objects.create_user(
            username="existing", password="pw123456", email="dup@test.local"
        )
        response = self.client.post(reverse("accounts:register"), {
            "email": "dup@test.local",
            "password1": "StrongPass456!",
            "password2": "StrongPass456!",
        })
        self.assertEqual(response.status_code, 200)


class LogoutViewTest(TestCase):
    def test_logout_success(self) -> None:
        CustomUser.objects.create_user(username="logoutuser", password="pw123456")
        self.client.login(username="logoutuser", password="pw123456")
        response = self.client.post(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response.url)


class ProfileViewTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = CustomUser.objects.create_user(
            username="profileuser", password="pw123456", email="profile@test.local"
        )

    def test_profile_login_required(self) -> None:
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response.url)

    def test_profile_shows_user_data(self) -> None:
        self.client.login(username="profileuser", password="pw123456")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("profile_user", response.context)
        self.assertEqual(response.context["profile_user"].username, "profileuser")


class PasswordResetTest(TestCase):
    """Tests for Django built-in email-based password reset."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = CustomUser.objects.create_user(
            username="resetuser", password="oldpw123",
            email="reset@test.local", phone="+201012345678"
        )

    def test_reset_request_success(self) -> None:
        """Valid email POST redirects to 'done' page."""
        response = self.client.post(reverse("accounts:password_reset"), {
            "email": "reset@test.local",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/password/reset/done/", response.url)

    def test_reset_done_page(self) -> None:
        """GET 'done' page renders."""
        response = self.client.get(reverse("accounts:password_reset_done"))
        self.assertEqual(response.status_code, 200)

    def test_reset_complete_page(self) -> None:
        """GET 'complete' page renders."""
        response = self.client.get(reverse("accounts:password_reset_complete"))
        self.assertEqual(response.status_code, 200)
