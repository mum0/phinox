"""Capture Phase 2 screenshots for all 7 Stitch-integrated pages.

Pages and their access requirements (same as Phase 1's pattern):
  1. Profile (/accounts/profile/) — login required
  2. Addresses (/accounts/addresses/) — login required
  3. Order History (/orders/) — login required
  4. Order Detail (/orders/<business_id>/) — login required + needs an order
  5. Order Tracking (/orders/<business_id>/track/) — login required + needs an order
  6. About (/about/) — public
  7. Wishlist (/wishlist/) — login required

For the auth-required pages we:
  - Reuse the test superuser `admin / admin12345` (created in Phase 1's screenshot script)
  - Make sure 1+ ShippingAddress exists for the user (for the Addresses page)
  - Make sure 1+ Order exists for the user (for Order History/Detail/Tracking)
  - Make sure 1+ WishlistItem exists (for the Wishlist page)

After that we visit each page in Playwright (headless Chromium), screenshot
it (1440x900 viewport), and save PNGs to /home/z/my-project/download/.

The Django dev server is started in-process (subprocess) so the sandbox
networking issue is avoided.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.request
from decimal import Decimal
from pathlib import Path

PROJECT_DIR = Path("/home/z/my-project/phinox")
OUT_DIR = Path("/home/z/my-project/download")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PORT = 8781
BASE_URL = f"http://127.0.0.1:{PORT}"

ENV = {
    **os.environ,
    "DJANGO_SETTINGS_MODULE": "config.settings.dev",
    "DJANGO_SECRET_KEY": "test-secret",
    "DJANGO_DEBUG": "True",
    "ALLOWED_HOSTS": "*",
}


def wait_for_server(url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = urllib.request.urlopen(url, timeout=2)
            if r.status == 200:
                return True
        except Exception:
            time.sleep(0.5)
    return False


def setup_test_fixtures() -> str:
    """Create (idempotent) test fixtures for Phase 2 screenshots.

    Returns (username, order_business_id)."""
    import sys as _sys
    project_dir = str(PROJECT_DIR)
    if project_dir not in _sys.path:
        _sys.path.insert(0, project_dir)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    import django
    django.setup()

    from django.contrib.auth import get_user_model
    from apps.cart.models import Cart, CartItem
    from apps.catalog.models import Product, ProductVariant
    from apps.orders.models import Order
    from apps.orders.services import create_order_from_cart
    from apps.payments.services import create_cod_payment
    from apps.shipping.models import ShippingAddress, ShippingMethod
    from apps.wishlist.models import WishlistItem

    User = get_user_model()

    # --- User ---
    user, created = User.objects.get_or_create(
        username="admin",
        defaults={"email": "admin@phinox.local", "is_staff": True, "is_superuser": True},
    )
    if created or not user.has_usable_password() or not user.check_password("admin12345"):
        user.set_password("admin12345")
        user.is_staff = True
        user.is_superuser = True
        user.save()

    # --- ShippingMethod ---
    ShippingMethod.objects.get_or_create(
        code="STANDARD_GROUND",
        defaults={
            "name": "Standard Ground",
            "price": Decimal("65.00"),
            "currency": "EGP",
            "estimated_days_min": 2,
            "estimated_days_max": 4,
            "is_active": True,
        },
    )

    # --- ShippingAddress (use the existing or create one) ---
    addr, _ = ShippingAddress.objects.get_or_create(
        user=user,
        full_name="Youssef El-Gammal",
        defaults={
            "address": "12 Tahrir Square",
            "city": "Alexandria",
            "country": "Egypt",
            "phone": "+201012345678",
            "postal_code": "11511",
            "is_default": True,
        },
    )
    # Add a 2nd address for visual variety
    if user.shipping_addresses.count() < 2:
        ShippingAddress.objects.create(
            user=user,
            full_name="Layla Hassan",
            address="45 Road 9, Maadi",
            city="Alexandria",
            country="Egypt",
            phone="+201112345678",
            postal_code="11712",
            is_default=False,
        )

    # --- Cart + item ---
    cart, _ = Cart.objects.get_or_create(user=user)
    if not cart.items.exists():
        variant = ProductVariant.objects.filter(is_active=True).first()
        if variant is None:
            raise RuntimeError("No active ProductVariant. Run `manage.py seed_products` first.")
        CartItem.objects.create(cart=cart, variant=variant, quantity=1)

    # --- Order (existing or new) ---
    order = Order.objects.filter(user=user).order_by("-created_at").first()
    if order is None:
        order = create_order_from_cart(cart=cart, user=user, shipping_cost=Decimal("65.00"))
        order.shipping_address = addr
        order.save(update_fields=["shipping_address", "updated_at"])
        create_cod_payment(order)

    # --- Wishlist items ---
    if not WishlistItem.objects.filter(user=user).exists():
        # Save the first 4 active products to the wishlist for visual variety
        products = list(Product.objects.filter(status="active", is_active=True)[:4])
        for product in products:
            variant = product.variants.filter(is_active=True).first()
            WishlistItem.objects.get_or_create(
                user=user, product=product, variant=variant,
            )

    return user.username, order.business_id


def main() -> int:
    # 1. Set up fixtures
    print("[+] Setting up Phase 2 test fixtures (user, addresses, order, wishlist items)...")
    try:
        username, order_business_id = setup_test_fixtures()
        print(f"    User: {username}")
        print(f"    Order: {order_business_id}")
    except Exception as e:
        print(f"  ! Setup failed: {e}")
        return 1

    # 2. Start Django dev server in-process
    print(f"[+] Starting Django dev server on 127.0.0.1:{PORT} ...")
    server_proc = subprocess.Popen(
        [
            "/home/z/.venv/bin/python", "manage.py", "runserver",
            "--noreload", "--nothreading",
            f"127.0.0.1:{PORT}",
        ],
        cwd=str(PROJECT_DIR),
        env=ENV,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    if not wait_for_server(f"{BASE_URL}/", timeout=30):
        print("  ! Django did not become ready.")
        try:
            os.killpg(os.getpgid(server_proc.pid), signal.SIGTERM)
        except Exception:
            pass
        return 2
    print("    Django ready.")

    # 3. Playwright screenshots
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        print(f"  ! Playwright unavailable: {exc}")
        try:
            os.killpg(os.getpgid(server_proc.pid), signal.SIGTERM)
        except Exception:
            pass
        return 3

    rc = 0
    # Phase 2 page list:
    pages_to_capture = [
        ("phase2_01_profile",        f"{BASE_URL}/accounts/profile/",                              "admin",  False),
        ("phase2_02_addresses",       f"{BASE_URL}/accounts/addresses/",                            "admin",  False),
        ("phase2_03_order_history",   f"{BASE_URL}/orders/",                                        "admin",  False),
        ("phase2_04_order_detail",    f"{BASE_URL}/orders/{order_business_id}/", "admin", False),
        ("phase2_05_order_tracking",  f"{BASE_URL}/orders/{order_business_id}/track/", "admin", False),
        ("phase2_06_about",           f"{BASE_URL}/about/",                                          None,     False),
        ("phase2_07_wishlist",        f"{BASE_URL}/wishlist/",                                       "admin",  False),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # Authenticated context
        auth_context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        auth_page = auth_context.new_page()

        # Anonymous context
        anon_context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        anon_page = anon_context.new_page()

        # Authenticate via /admin/login/ (since /accounts/login/ is a visual stub)
        print(f"[+] Authenticating test session via /admin/login/ (admin / admin12345)...")
        auth_page.goto(f"{BASE_URL}/admin/login/", wait_until="networkidle", timeout=15000)
        auth_page.fill("#id_username", "admin")
        auth_page.fill("#id_password", "admin12345")
        auth_page.click("input[type=submit]", timeout=10000)
        auth_page.wait_for_load_state("networkidle", timeout=15000)
        if "Log out" in auth_page.content():
            print("    Auth OK.")
        else:
            print("    ! Admin login may have failed.")

        for name, url, auth_user, full_page in pages_to_capture:
            page = auth_page if auth_user else anon_page
            print(f"[+] {name:36s}  {url}")
            try:
                page.goto(url, wait_until="networkidle", timeout=20000)
            except Exception as exc:
                print(f"  ! Navigation failed: {exc}")
                rc = 1
                continue
            out_path = OUT_DIR / f"{name}.png"
            page.screenshot(path=str(out_path), full_page=full_page)
            print(f"    → {out_path.name}  ({out_path.stat().st_size} bytes)")

        browser.close()

    # 4. Kill Django
    print("\n[+] Stopping Django ...")
    try:
        os.killpg(os.getpgid(server_proc.pid), signal.SIGTERM)
        server_proc.wait(timeout=5)
        print("    ✓ Stopped.")
    except Exception as exc:
        print(f"  ! Error stopping Django: {exc}")
        try:
            server_proc.kill()
        except Exception:
            pass

    print()
    print("All Phase 2 screenshots saved to:", OUT_DIR)
    for f in sorted(OUT_DIR.glob("phase2_*.png")):
        print(f"  {f.name:42s} {f.stat().st_size:>8d} bytes")
    return rc


if __name__ == "__main__":
    sys.exit(main())
