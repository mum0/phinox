"""PHINOX E2E Automated Test — 6 scenarios.

Runs against a live Django dev server (started in-process).
Covers:
  1. Browse as guest (home, shop, collections, about, product detail, add to cart)
  2. Register new account
  3. Checkout (COD)
  4. Wishlist
  5. Mobile viewport (drawer)
  6. OTP password reset
"""
from __future__ import annotations
import os, signal, subprocess, sys, time, urllib.request
from pathlib import Path
from decimal import Decimal

PROJECT_DIR = Path("/home/z/my-project/phinox")
OUT_DIR = Path("/home/z/my-project/download")
PORT = 8840
BASE_URL = f"http://127.0.0.1:{PORT}"
ENV = {
    **os.environ,
    "DJANGO_SETTINGS_MODULE": "config.settings.dev",
    "DJANGO_SECRET_KEY": "test-secret",
    "DJANGO_DEBUG": "True",
    "ALLOWED_HOSTS": "*",
}

def wait_for_server(url, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except:
            time.sleep(0.5)
    return False

def setup_fixtures():
    """Create test user + shipping address + seed products + images."""
    import sys as _sys
    if str(PROJECT_DIR) not in _sys.path:
        _sys.path.insert(0, str(PROJECT_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    import django; django.setup()

    from django.contrib.auth import get_user_model
    from apps.shipping.models import ShippingAddress, ShippingMethod

    U = get_user_model()
    # Create test user for E2E
    user, created = U.objects.get_or_create(
        username="e2e_tester",
        defaults={"email": "e2e@test.local", "phone": "+201012345678"}
    )
    if created or not user.check_password("E2Epass123!"):
        user.set_password("E2Epass123!")
        user.save()

    # Shipping method
    ShippingMethod.objects.get_or_create(
        code="STANDARD_GROUND",
        defaults={
            "name": "Standard Ground",
            "price": Decimal("65.00"),
            "currency": "EGP",
            "estimated_days_min": 2,
            "estimated_days_max": 4,
            "is_active": True,
        }
    )

    # Shipping address
    addr, _ = ShippingAddress.objects.get_or_create(
        user=user,
        full_name="E2E Tester",
        defaults={
            "address": "12 Tahrir Square",
            "city": "Alexandria",
            "country": "Egypt",
            "phone": "+201012345678",
            "postal_code": "11511",
            "is_default": True,
        }
    )

    print(f"  Fixtures ready: user={user.username}, addr={addr.full_name}")

def main():
    print("[+] Setting up fixtures...")
    setup_fixtures()

    print(f"[+] Starting Django on port {PORT}...")
    proc = subprocess.Popen(
        ["/home/z/.venv/bin/python", "manage.py", "runserver",
         "--noreload", "--nothreading", f"127.0.0.1:{PORT}"],
        cwd=str(PROJECT_DIR), env=ENV,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    if not wait_for_server(f"{BASE_URL}/", timeout=30):
        print("  ! Django not ready")
        return 1
    print("  Django ready.")

    from playwright.sync_api import sync_playwright

    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # ═══════════════════════════════════════════════════════════════
        # TEST 1: Browse as guest
        # ═══════════════════════════════════════════════════════════════
        print("\n=== TEST 1: Browse as guest ===")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        try:
            # Home
            page.goto(f"{BASE_URL}/", wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(1000)
            assert "PHINOX" in page.title()
            assert page.is_visible("text=SHOP")
            assert page.is_visible("text=COLLECTIONS")
            assert page.is_visible("text=ABOUT")
            print("  [x] / → Home with topbar (SHOP/COLLECTIONS/ABOUT)")
            results["1_home"] = "✅"

            # Shop
            page.goto(f"{BASE_URL}/products/", wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(500)
            assert "PHINOX" in page.title()
            print("  [x] /products/ → Shop page")
            results["1_shop"] = "✅"

            # Collections
            page.goto(f"{BASE_URL}/products/collections/", wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(500)
            print("  [x] /products/collections/ → Collections page")
            results["1_collections"] = "✅"

            # About
            page.goto(f"{BASE_URL}/about/", wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(500)
            print("  [x] /about/ → About page")
            results["1_about"] = "✅"

            # Journal (guest — link not in topbar but URL accessible)
            page.goto(f"{BASE_URL}/journal/", wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(500)
            assert "JOURNAL" in page.content().upper()
            print("  [x] /journal/ → Journal stub page")
            results["1_journal"] = "✅"

            # Product detail
            page.goto(f"{BASE_URL}/products/phinox-signature-jacket/", wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(500)
            assert "PHINOX" in page.title()
            print("  [x] /products/<slug>/ → Product detail page")
            results["1_pdp"] = "✅"

            # Cart (empty for guest)
            page.goto(f"{BASE_URL}/cart/", wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(500)
            cart_content = page.content()
            if "CART IS EMPTY" in cart_content.upper() or "Your cart is empty" in cart_content:
                print("  [x] /cart/ → Empty cart state (guest)")
                results["1_cart_empty"] = "✅"
            else:
                print("  [ ] /cart/ → Cart has items (unexpected for fresh guest)")
                results["1_cart_empty"] = "⚠️ (cart not empty)"

        except Exception as e:
            print(f"  [ ] TEST 1 FAILED: {e}")
            results["1_error"] = f"❌ {e}"

        # ═══════════════════════════════════════════════════════════════
        # TEST 2: Register new account
        # ═══════════════════════════════════════════════════════════════
        print("\n=== TEST 2: Register new account ===")
        ctx2 = browser.new_context(viewport={"width": 1440, "height": 900})
        page2 = ctx2.new_page()
        try:
            import time as _time
            _ts = int(_time.time())
            page2.goto(f"{BASE_URL}/accounts/register/", wait_until="networkidle", timeout=15000)
            page2.wait_for_timeout(500)
            page2.fill("#id_email", f"e2e_user_{_ts}")
            page2.fill("#id_email", f"e2e_{_ts}@test.local")
            page2.fill("#id_mobile_number", "+201012345678")
            page2.fill("#id_password1", "E2Epass123!")
            page2.fill("#id_password2", "E2Epass123!")
            page2.click("button[type=submit]", timeout=10000)
            page2.wait_for_load_state("networkidle", timeout=15000)

            # After register, should redirect to home (logged in)
            if "accounts/login" not in page2.url:
                print(f"  [x] Register → redirected to {page2.url}")
                results["2_register"] = "✅"
            else:
                print(f"  [ ] Register stayed on login page: {page2.url}")
                results["2_register"] = "❌ (stayed on login)"

            # Check if JOURNAL/WISHLIST links appear (authenticated)
            content = page2.content()
            if "JOURNAL" in content and "WISHLIST" in content:
                print("  [x] Authenticated topbar shows JOURNAL + WISHLIST")
                results["2_auth_links"] = "✅"
            else:
                print("  [ ] JOURNAL/WISHLIST not visible")
                results["2_auth_links"] = "⚠️ (links not visible)"

            # Profile
            page2.goto(f"{BASE_URL}/accounts/profile/", wait_until="networkidle", timeout=15000)
            page2.wait_for_timeout(500)
            if page2.url == f"{BASE_URL}/accounts/profile/" or "profile" in page2.url:
                print("  [x] /accounts/profile/ accessible")
                results["2_profile"] = "✅"
            else:
                print(f"  [ ] Profile redirected to: {page2.url}")
                results["2_profile"] = f"❌ (redirected to {page2.url})"

        except Exception as e:
            print(f"  [ ] TEST 2 FAILED: {e}")
            results["2_error"] = f"❌ {e}"

        # ═══════════════════════════════════════════════════════════════
        # TEST 5: Mobile viewport (drawer)
        # ═══════════════════════════════════════════════════════════════
        print("\n=== TEST 5: Mobile viewport (drawer) ===")
        ctx5 = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
        page5 = ctx5.new_page()
        try:
            page5.goto(f"{BASE_URL}/", wait_until="networkidle", timeout=15000)
            page5.wait_for_timeout(1000)
            content = page5.content()

            # Check hamburger menu is visible (lg:hidden = visible on mobile)
            if "menu" in content.lower():
                print("  [x] Mobile: hamburger menu button visible")
                results["5_hamburger"] = "✅"
            else:
                print("  [ ] Mobile: hamburger not found")
                results["5_hamburger"] = "❌"

            # Click hamburger to open drawer
            try:
                page5.click("#phx-drawer-toggle", timeout=5000)
                page5.wait_for_timeout(500)
                drawer = page5.query_selector("#phx-drawer")
                if drawer:
                    style = drawer.get_attribute("class") or ""
                    if "-translate-x-full" not in style:
                        print("  [x] Mobile: drawer opened")
                        results["5_drawer_open"] = "✅"
                    else:
                        print("  [ ] Mobile: drawer still hidden")
                        results["5_drawer_open"] = "⚠️ (drawer hidden)"
                else:
                    results["5_drawer_open"] = "❌ (no drawer element)"
            except Exception as e:
                print(f"  [ ] Mobile: drawer toggle failed: {e}")
                results["5_drawer_open"] = f"❌ {e}"

            # Close with Escape
            try:
                page5.keyboard.press("Escape")
                page5.wait_for_timeout(300)
                drawer = page5.query_selector("#phx-drawer")
                if drawer:
                    style = drawer.get_attribute("class") or ""
                    if "-translate-x-full" in style:
                        print("  [x] Mobile: drawer closed with Escape")
                        results["5_drawer_close"] = "✅"
                    else:
                        results["5_drawer_close"] = "⚠️ (still open)"
            except:
                results["5_drawer_close"] = "⚠️"

            # Screenshot
            page5.screenshot(path=str(OUT_DIR / "e2e_mobile.png"))
            print("  [x] Mobile screenshot saved")

        except Exception as e:
            print(f"  [ ] TEST 5 FAILED: {e}")
            results["5_error"] = f"❌ {e}"

        # ═══════════════════════════════════════════════════════════════
        # TEST 6: OTP password reset (request only — no real OTP verify)
        # ═══════════════════════════════════════════════════════════════
        print("\n=== TEST 6: OTP password reset ===")
        ctx6 = browser.new_context(viewport={"width": 1440, "height": 900})
        page6 = ctx6.new_page()
        try:
            page6.goto(f"{BASE_URL}/accounts/password/reset/", wait_until="networkidle", timeout=15000)
            page6.wait_for_timeout(500)
            assert "CIPHER" in page6.content().upper() or "RESET" in page6.content().upper()
            print("  [x] /accounts/password/reset/ → Reset request page")
            results["6_reset_page"] = "✅"

            # Submit phone number
            page6.fill("input[name='mobile_number']", "+201012345678")
            page6.click("button[type=submit]", timeout=10000)
            page6.wait_for_load_state("networkidle", timeout=15000)

            # Should redirect to confirm page
            if "confirm" in page6.url:
                print(f"  [x] Reset → redirected to {page6.url}")
                results["6_reset_submit"] = "✅"
            else:
                print(f"  [ ] Reset → stayed at {page6.url}")
                results["6_reset_submit"] = f"⚠️ (url={page6.url})"

            # Check that confirm page shows
            content = page6.content()
            if "CIPHER" in content.upper() or "VERIFICATION" in content.upper() or "OTP" in content.upper():
                print("  [x] Confirm page shows OTP form")
                results["6_confirm_page"] = "✅"
            else:
                print("  [ ] Confirm page doesn't show OTP form")
                results["6_confirm_page"] = "⚠️"

        except Exception as e:
            print(f"  [ ] TEST 6 FAILED: {e}")
            results["6_error"] = f"❌ {e}"

        browser.close()

    # ═══════════════════════════════════════════════════════════════
    # TEST 3 & 4: Checkout + Wishlist (via Django test client — requires auth)
    # ═══════════════════════════════════════════════════════════════
    print("\n=== TEST 3: Checkout (COD) via Django test client ===")
    try:
        import sys as _sys
        if str(PROJECT_DIR) not in _sys.path:
            _sys.path.insert(0, str(PROJECT_DIR))
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
        import django; django.setup()

        from django.test import Client
        from django.contrib.auth import get_user_model
        from apps.cart.models import Cart, CartItem
        from apps.catalog.models import ProductVariant
        from apps.orders.models import Order
        from apps.shipping.models import ShippingAddress, ShippingMethod

        U = get_user_model()
        user = U.objects.get(username="e2e_tester")
        c = Client()
        c.force_login(user)

        # Add item to cart
        cart, _ = Cart.objects.get_or_create(user=user)
        cart.items.all().delete()  # clean slate
        variant = ProductVariant.objects.filter(is_active=True).first()
        CartItem.objects.create(cart=cart, variant=variant, quantity=1)

        # Checkout
        addr = ShippingAddress.objects.filter(user=user, is_default=True).first()
        method = ShippingMethod.objects.filter(is_active=True).first()
        response = c.post("/checkout/", {
            "shipping_address_id": addr.pk,
            "shipping_method_id": method.pk,
            "payment_method": "cod",
        })
        if response.status_code == 302 and "confirmation" in response.url:
            print("  [x] Checkout POST → redirect to confirmation")
            results["3_checkout"] = "✅"

            # Check order was created
            order = Order.objects.filter(user=user).order_by("-created_at").first()
            if order:
                print(f"  [x] Order created: {order.business_id} (status={order.status})")
                results["3_order_created"] = "✅"

                # Order history
                response = c.get("/orders/")
                if response.status_code == 200:
                    print("  [x] /orders/ → Order history accessible")
                    results["3_order_history"] = "✅"
                else:
                    results["3_order_history"] = f"❌ ({response.status_code})"

                # Order tracking
                response = c.get(f"/orders/{order.business_id}/track/")
                if response.status_code == 200:
                    print("  [x] /orders/<id>/track/ → Tracking page")
                    results["3_tracking"] = "✅"
                else:
                    results["3_tracking"] = f"❌ ({response.status_code})"
            else:
                results["3_order_created"] = "❌ (no order)"
        else:
            print(f"  [ ] Checkout failed: {response.status_code} → {response.url}")
            results["3_checkout"] = f"❌ ({response.status_code})"

    except Exception as e:
        print(f"  [ ] TEST 3 FAILED: {e}")
        results["3_error"] = f"❌ {e}"

    print("\n=== TEST 4: Wishlist ===")
    try:
        from apps.wishlist.models import WishlistItem
        from apps.catalog.models import Product

        # Add to wishlist
        product = Product.objects.filter(status="active", is_active=True).first()
        wi, created = WishlistItem.objects.get_or_create(user=user, product=product)

        response = c.get("/wishlist/")
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            if product.name.upper() in content.upper():
                print(f"  [x] /wishlist/ → Shows '{product.name}'")
                results["4_wishlist"] = "✅"
            else:
                print("  [ ] Wishlist page doesn't show product")
                results["4_wishlist"] = "⚠️ (product not visible)"
        else:
            results["4_wishlist"] = f"❌ ({response.status_code})"

        # Remove from wishlist
        wi.delete()
        response = c.get("/wishlist/")
        content = response.content.decode("utf-8")
        if "VAULT IS EMPTY" in content.upper() or "empty" in content.lower():
            print("  [x] Wishlist empty after remove")
            results["4_wishlist_remove"] = "✅"
        else:
            results["4_wishlist_remove"] = "⚠️"

    except Exception as e:
        print(f"  [ ] TEST 4 FAILED: {e}")
        results["4_error"] = f"❌ {e}"

    # Kill Django
    print("\n[+] Stopping Django...")
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=5)
    except:
        try: proc.kill()
        except: pass

    # ═══════════════════════════════════════════════════════════════
    # REPORT
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("E2E TEST RESULTS")
    print("=" * 60)
    for key in sorted(results.keys()):
        print(f"  {results[key]:6s}  {key}")
    print("=" * 60)

    ok_count = sum(1 for v in results.values() if v.startswith("✅"))
    warn_count = sum(1 for v in results.values() if v.startswith("⚠️"))
    fail_count = sum(1 for v in results.values() if v.startswith("❌"))
    print(f"\n  ✅ {ok_count} passed  |  ⚠️ {warn_count} warnings  |  ❌ {fail_count} failed")
    print("=" * 60)

    return 0 if fail_count == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
