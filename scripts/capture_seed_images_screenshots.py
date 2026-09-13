"""Capture screenshots of /wishlist/ and /cart/ after seeding product images.

Reuses the same pattern as the Phase 1 + Phase 2 screenshot scripts.
The test fixtures already exist (admin user, 4 WishlistItem rows, 1 CartItem).
We just need to re-add a CartItem (since the previous order placement removed
the cart's items via create_order_from_cart) so the /cart/ page shows
something. Then screenshot both pages.
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

PORT = 8783
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


def ensure_cart_item() -> None:
    """Make sure the admin user has at least one item in the cart so /cart/
    shows real content (not the empty state)."""
    import sys as _sys
    project_dir = str(PROJECT_DIR)
    if project_dir not in _sys.path:
        _sys.path.insert(0, project_dir)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    import django
    django.setup()

    from django.contrib.auth import get_user_model
    from apps.cart.models import Cart, CartItem
    from apps.catalog.models import ProductVariant

    User = get_user_model()
    user = User.objects.get(username="admin")
    cart, _ = Cart.objects.get_or_create(user=user)
    if not cart.items.exists():
        variant = ProductVariant.objects.filter(is_active=True).first()
        if variant is not None:
            CartItem.objects.create(cart=cart, variant=variant, quantity=1)
            print(f"    Added 1 item ({variant.sku}) to admin's cart")


def main() -> int:
    # 1. Ensure cart item exists
    print("[+] Ensuring admin cart has an item...")
    ensure_cart_item()

    # 2. Start Django
    print(f"[+] Starting Django on 127.0.0.1:{PORT} ...")
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
    pages_to_capture = [
        ("seed_images_01_wishlist",   f"{BASE_URL}/wishlist/", "admin", False),
        ("seed_images_02_cart",       f"{BASE_URL}/cart/",      "admin", False),
        ("seed_images_03_product_list", f"{BASE_URL}/products/", None, False),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        auth_context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        auth_page = auth_context.new_page()
        anon_context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        anon_page = anon_context.new_page()

        # Auth via /admin/login/
        print("[+] Authenticating admin session...")
        auth_page.goto(f"{BASE_URL}/admin/login/", wait_until="networkidle", timeout=15000)
        auth_page.fill("#id_username", "admin")
        auth_page.fill("#id_password", "admin12345")
        auth_page.click("input[type=submit]", timeout=10000)
        auth_page.wait_for_load_state("networkidle", timeout=15000)

        for name, url, auth_user, full_page in pages_to_capture:
            page = auth_page if auth_user else anon_page
            print(f"[+] {name:38s}  {url}")
            try:
                page.goto(url, wait_until="networkidle", timeout=20000)
            except Exception as exc:
                print(f"  ! Navigation failed: {exc}")
                rc = 1
                continue
            # Wait an extra 800ms for product images to load (the
            # networkidle event may fire before <img> tags finish
            # decoding). This is a real-world quirk — Django serves
            # /media/ in dev but the browser still needs to fetch each
            # image, and Playwright's networkidle is a hard threshold.
            page.wait_for_timeout(800)
            out_path = OUT_DIR / f"{name}.png"
            page.screenshot(path=str(out_path), full_page=full_page)
            print(f"    → {out_path.name}  ({out_path.stat().st_size} bytes)")

        # Also grab a full-page wishlist shot so all 4 product cards show
        print("[+] seed_images_04_wishlist_full (full-page)")
        try:
            auth_page.goto(f"{BASE_URL}/wishlist/", wait_until="networkidle", timeout=20000)
            auth_page.wait_for_timeout(800)
            out_path = OUT_DIR / "seed_images_04_wishlist_full.png"
            auth_page.screenshot(path=str(out_path), full_page=True)
            print(f"    → {out_path.name}  ({out_path.stat().st_size} bytes)")
        except Exception as exc:
            print(f"  ! Failed: {exc}")

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
    print("Screenshots saved to:", OUT_DIR)
    for f in sorted(OUT_DIR.glob("seed_images_*.png")):
        print(f"  {f.name:44s} {f.stat().st_size:>8d} bytes")
    return rc


if __name__ == "__main__":
    sys.exit(main())
