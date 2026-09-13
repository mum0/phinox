"""Start Django dev server + capture screenshots in one go.

The sandbox kills background processes when a Bash command ends, so we
must start the Django runserver, run Playwright, and kill Django all
inside the same Python process to keep the server alive for the whole
screenshot session.

Workflow:
  1. Start Django runserver on 127.0.0.1:8765 as a subprocess.
  2. Wait for it to be ready (poll /admin/login/).
  3. Use Playwright to capture:
     - Admin login form
     - Admin home (after login)
     - Admin home scrolled to PHINOX CATALOG module
     - Admin → PHINOX CATALOG → Products list
     - Public /products/ page (viewport + full-page)
  4. Kill the Django subprocess (best-effort).
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# Run Django with the same env we use for manage.py.
ENV = {
    **os.environ,
    "DJANGO_SETTINGS_MODULE": "config.settings.dev",
    "DJANGO_SECRET_KEY": "test-secret",
    "DJANGO_DEBUG": "True",
    "ALLOWED_HOSTS": "*",
}

PROJECT_DIR = Path("/home/z/my-project/phinox")
OUT_DIR = Path("/home/z/my-project/download")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PORT = 8766
ADMIN_URL = f"http://127.0.0.1:{PORT}/admin/login/"
ADMIN_HOME_URL = f"http://127.0.0.1:{PORT}/admin/"
ADMIN_CATALOG_URL = f"http://127.0.0.1:{PORT}/admin/catalog/product/"
PRODUCTS_URL = f"http://127.0.0.1:{PORT}/products/"

ADMIN_USER = "admin"
ADMIN_PASS = "admin12345"


def wait_for_server(url: str, timeout: float = 30.0) -> bool:
    """Poll the URL until it returns 200 or timeout expires."""
    deadline = time.time() + timeout
    last_err = ""
    while time.time() < deadline:
        try:
            r = urllib.request.urlopen(url, timeout=2)
            if r.status == 200:
                return True
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
        time.sleep(0.5)
    print(f"  ! Server did not become ready at {url} (last: {last_err})")
    return False


def main() -> int:
    # Make sure no stale Django is holding the port.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.bind(("127.0.0.1", PORT))
    except OSError:
        # Port is busy — assume a previous instance is still up.
        print(f"[!] Port {PORT} is busy; trying to use the existing server.")
        if not wait_for_server(ADMIN_URL, timeout=5):
            print("  ! Existing server not responding. Aborting.")
            return 2
        server_proc = None
    else:
        # Start Django runserver as a child process.
        print(f"[+] Starting Django runserver on 127.0.0.1:{PORT} ...")
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
            start_new_session=True,  # detach from this script's process group
        )
        # Wait for server readiness.
        if not wait_for_server(ADMIN_URL, timeout=30):
            print("  ! Django did not become ready in 30s.")
            if server_proc:
                server_proc.terminate()
            return 3
        print("  ✓ Django is ready.")

    # -------------------------------------------------------------------
    # Playwright screenshots
    # -------------------------------------------------------------------
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        print(f"  ! Playwright unavailable: {exc}")
        if server_proc:
            server_proc.terminate()
        return 4

    rc = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900}, locale="en-US",
        )
        page = context.new_page()

        # 1. Admin login form
        print(f"[1/5] {ADMIN_URL}")
        page.goto(ADMIN_URL, wait_until="networkidle", timeout=15000)
        page.fill("#id_username", ADMIN_USER)
        page.fill("#id_password", ADMIN_PASS)
        page.screenshot(path=str(OUT_DIR / "01_admin_login_page.png"), full_page=False)
        print("      ✓ 01_admin_login_page.png")

        # Submit login. Django admin uses <input type="submit" value="Log in">.
        page.click("input[type=submit]", timeout=10000)
        page.wait_for_load_state("networkidle", timeout=15000)
        print(f"      Landed on: {page.url}")

        # 2. Admin home (showing all app modules)
        print(f"[2/5] {ADMIN_HOME_URL}")
        page.screenshot(path=str(OUT_DIR / "02_admin_home.png"), full_page=False)
        print("      ✓ 02_admin_home.png")

        # 2b. Scroll the PHINOX CATALOG module into view, then capture.
        print(f"[2b/5] Scrolling to PHINOX CATALOG module ...")
        try:
            page.eval_on_selector(
                ".app-catalog.module",
                "el => el.scrollIntoView({block:'center'})",
            )
            page.wait_for_timeout(400)
        except Exception as exc:  # noqa: BLE001
            print(f"      (scroll-to-catalog skipped: {exc})")
        page.screenshot(path=str(OUT_DIR / "02b_admin_catalog_module.png"), full_page=False)
        print("      ✓ 02b_admin_catalog_module.png")

        # 3. Admin → PHINOX CATALOG → Products list
        print(f"[3/5] {ADMIN_CATALOG_URL}")
        page.goto(ADMIN_CATALOG_URL, wait_until="networkidle", timeout=15000)
        page.screenshot(path=str(OUT_DIR / "03_admin_products.png"), full_page=False)
        print("      ✓ 03_admin_products.png")

        # 4. Public /products/ page (viewport)
        print(f"[4/5] {PRODUCTS_URL}")
        page.goto(PRODUCTS_URL, wait_until="networkidle", timeout=15000)
        page.screenshot(path=str(OUT_DIR / "04_products_page.png"), full_page=False)
        print("      ✓ 04_products_page.png")

        # 5. Public /products/ full page (all 20 products)
        print(f"[5/5] {PRODUCTS_URL} (full page)")
        page.screenshot(path=str(OUT_DIR / "04b_products_page_full.png"), full_page=True)
        print("      ✓ 04b_products_page_full.png")

        browser.close()

    print()
    print("All screenshots saved to:", OUT_DIR)
    for f in sorted(OUT_DIR.glob("0*.png")):
        size = f.stat().st_size
        print(f"  {f.name:40s} {size:>8d} bytes")

    # -------------------------------------------------------------------
    # Cleanup: kill Django
    # -------------------------------------------------------------------
    if server_proc is not None:
        print("\n[+] Stopping Django ...")
        try:
            os.killpg(os.getpgid(server_proc.pid), signal.SIGTERM)
            server_proc.wait(timeout=5)
            print("  ✓ Django stopped.")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! Error stopping Django: {exc}")
            try:
                server_proc.kill()
            except Exception:
                pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
