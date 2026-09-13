"""Capture Phase 1 screenshots for all 7 Stitch-integrated pages.

Pages and their access requirements:
  1. Home (/) — public
  2. Login (/accounts/login/) — public (stub view)
  3. Register (/accounts/register/) — public (stub view)
  4. Cart (/cart/) — public (guest cart works)
  5. Checkout/Shipping (/checkout/) — auth required (uses request.user.cart)
  6. Payment test (/payments/test/<order_business_id>/) — auth required + needs an order
  7. Order Confirmation (/checkout/<business_id>/confirmation/) — auth required + needs an order

For pages 5-7 we:
  - Create (or reuse) a test superuser `admin / admin12345`
  - Make sure 1+ ShippingMethod exists (seed if missing)
  - Make sure 1+ ShippingAddress exists for the user (seed if missing)
  - Add 1 product variant to the user's cart
  - Place an order via the CheckoutView (POST) so we have a real order with business_id
  - Then we have a real order to drive the payment + confirmation pages

After that we visit each page in Playwright (headless Chromium), screenshot
it (1440x900 viewport + full-page variant), and save PNGs to
/home/z/my-project/download/.

The Django dev server is started in-process (subprocess) so the sandbox
networking issue is avoided — same approach as the prior screenshot script.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from decimal import Decimal
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths and config
# ---------------------------------------------------------------------------
PROJECT_DIR = Path("/home/z/my-project/phinox")
OUT_DIR = Path("/home/z/my-project/download")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PORT = 8773
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


def setup_test_order() -> str:
    """Create (idempotent) test fixtures: superuser, ShippingMethod, ShippingAddress,
    add a product to cart, place an order. Returns the order's business_id."""
    # Make sure the project is on sys.path so `import config` works.
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
    method, _ = ShippingMethod.objects.get_or_create(
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

    # --- ShippingAddress ---
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

    # --- Cart + item ---
    cart, _ = Cart.objects.get_or_create(user=user)
    if not cart.items.exists():
        variant = ProductVariant.objects.filter(is_active=True).first()
        if variant is None:
            raise RuntimeError("No active ProductVariant in DB. Run `manage.py seed_products` first.")
        CartItem.objects.create(cart=cart, variant=variant, quantity=1)

    # --- Order (look for an existing one for this user; create if missing) ---
    order = Order.objects.filter(user=user).order_by("-created_at").first()
    if order is None:
        order = create_order_from_cart(cart=cart, user=user, shipping_cost=Decimal("65.00"))
        order.shipping_address = addr
        order.save(update_fields=["shipping_address", "updated_at"])
        create_cod_payment(order)

    return user.username, order.business_id


def main() -> int:
    # 1. Set up fixtures
    print("[+] Setting up test fixtures (user, address, cart, order)...")
    try:
        username, order_business_id = setup_test_order()
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
    # NOTE: the actual reverse URLs:
    # - orders:checkout          → /checkout/checkout/   (prefix "checkout/" + path "checkout/")
    # - orders:confirmation      → /checkout/<business_id>/confirmation/
    # - payments:test_payment    → /payments/test/<business_id>/
    pages_to_capture = [
        ("phase1_01_home",                f"{BASE_URL}/",                                                                 None,            False),
        ("phase1_02_login",               f"{BASE_URL}/accounts/login/",                                                  None,            False),
        ("phase1_03_register",             f"{BASE_URL}/accounts/register/",                                               None,            False),
        ("phase1_04_cart",                 f"{BASE_URL}/cart/",                                                            None,            False),
        ("phase1_05_checkout_shipping",    f"{BASE_URL}/checkout/checkout/",                                              "admin",         False),
        ("phase1_06_payment",              f"{BASE_URL}/payments/test/{order_business_id}/", "admin", False),
        ("phase1_07_order_confirmation",   f"{BASE_URL}/checkout/{order_business_id}/confirmation/", "admin", False),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # Authenticated context (for pages 5-7)
        auth_context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        auth_page = auth_context.new_page()

        # Anonymous context (for pages 1-4)
        anon_context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        anon_page = anon_context.new_page()

        # Log in the authenticated context first by hitting the admin login (we'll
        # use Django's built-in /admin/login/ since the Stitch /accounts/login/ is
        # a visual-only stub and won't actually authenticate).
        print(f"[+] Authenticating test session via /admin/login/ (admin / admin12345)...")
        auth_page.goto(f"{BASE_URL}/admin/login/", wait_until="networkidle", timeout=15000)
        auth_page.fill("#id_username", "admin")
        auth_page.fill("#id_password", "admin12345")
        auth_page.click("input[type=submit]", timeout=10000)
        auth_page.wait_for_load_state("networkidle", timeout=15000)
        # Confirm we're authed — the admin index should show "Log out"
        if "Log out" in auth_page.content() or "WELCOME" in auth_page.content().upper():
            print("    Auth OK.")
        else:
            print("    ! Admin login may have failed — auth-required pages may show login redirect.")

        for name, url, auth_user, full_page in pages_to_capture:
            page = auth_page if auth_user else anon_page
            print(f"[+] {name:36s}  {url}")
            try:
                page.goto(url, wait_until="networkidle", timeout=15000)
            except Exception as exc:
                print(f"  ! Navigation failed: {exc}")
                rc = 1
                continue
            # Screenshot
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
    print("All Phase 1 screenshots saved to:", OUT_DIR)
    for f in sorted(OUT_DIR.glob("phase1_*.png")):
        print(f"  {f.name:42s} {f.stat().st_size:>8d} bytes")
    return rc


if __name__ == "__main__":
    sys.exit(main())
