"""Capture Phase 3 screenshots for all 9 Stitch-integrated pages.

Phase 3 pages:
  1. FAQ (/faq/) — public
  2. Privacy Policy (/privacy/) — public
  3. Terms of Service (/terms/) — public
  4. Returns & Refunds (/returns/) — public
  5. 404 page (/some-nonexistent-page/) — public (uses the Stitch 404)
  6. PDP (refresh) (/products/<slug>/) — public
  7. Collections Matrix (/products/collections/) — public
  8. Collection Detail (/products/collections/<slug>/) — public
  9. Advanced Search (/products/search/) — public

All Phase 3 pages are public (no login required). The 404 page is
triggered by visiting a non-existent URL.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_DIR = Path("/home/z/my-project/phinox")
OUT_DIR = Path("/home/z/my-project/download")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PORT = 8791
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


def main() -> int:
    # 1. Start Django
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

    # 2. Playwright screenshots — all public pages, no auth needed
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        print(f"  ! Playwright unavailable: {exc}")
        try:
            os.killpg(os.getpgid(server_proc.pid), signal.SIGTERM)
        except Exception:
            pass
        return 3

    # Use a product slug we know exists (from seed_products)
    product_slug = "phinox-signature-jacket"
    collection_slug = "winter-drop-2025"

    pages_to_capture = [
        ("phase3_01_faq",                f"{BASE_URL}/faq/"),
        ("phase3_02_privacy",             f"{BASE_URL}/privacy/"),
        ("phase3_03_terms",               f"{BASE_URL}/terms/"),
        ("phase3_04_returns",             f"{BASE_URL}/returns/"),
        ("phase3_05_404",                  f"{BASE_URL}/this-page-does-not-exist-phase3-test/"),
        ("phase3_06_pdp",                  f"{BASE_URL}/products/{product_slug}/"),
        ("phase3_07_collections",         f"{BASE_URL}/products/collections/"),
        ("phase3_08_collection_detail",    f"{BASE_URL}/products/collections/{collection_slug}/"),
        ("phase3_09_advanced_search",     f"{BASE_URL}/products/search/"),
    ]

    rc = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        page = context.new_page()

        for name, url in pages_to_capture:
            print(f"[+] {name:36s}  {url}")
            try:
                page.goto(url, wait_until="networkidle", timeout=20000)
                page.wait_for_timeout(800)  # let images decode
            except Exception as exc:
                print(f"  ! Navigation failed: {exc}")
                rc = 1
                continue
            out_path = OUT_DIR / f"{name}.png"
            page.screenshot(path=str(out_path), full_page=False)
            print(f"    → {out_path.name}  ({out_path.stat().st_size} bytes)")

        # Also capture full-page shots for FAQ + PDP (the longer pages)
        for name, url in [
            ("phase3_10_faq_full",       f"{BASE_URL}/faq/"),
            ("phase3_11_pdp_full",        f"{BASE_URL}/products/{product_slug}/"),
            ("phase3_12_collections_full", f"{BASE_URL}/products/collections/"),
        ]:
            print(f"[+] {name:36s}  {url}")
            try:
                page.goto(url, wait_until="networkidle", timeout=20000)
                page.wait_for_timeout(800)
                out_path = OUT_DIR / f"{name}.png"
                page.screenshot(path=str(out_path), full_page=True)
                print(f"    → {out_path.name}  ({out_path.stat().st_size} bytes)")
            except Exception as exc:
                print(f"  ! Failed: {exc}")

        browser.close()

    # 3. Kill Django
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
    print("Phase 3 screenshots saved to:", OUT_DIR)
    for f in sorted(OUT_DIR.glob("phase3_*.png")):
        print(f"  {f.name:44s} {f.stat().st_size:>8d} bytes")
    return rc


if __name__ == "__main__":
    sys.exit(main())
