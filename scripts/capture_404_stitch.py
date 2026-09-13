"""Capture the Stitch 404 page screenshot with DEBUG=False.

Django shows the technical debug 404 page (with URL patterns) when
DEBUG=True. To see the actual custom 404 template (the Stitch
"Lost Coordinates" design), we need DEBUG=False. We use a custom
``no_debug`` settings module that sets DEBUG=False + bypasses SSL
redirect / cookie security so plain HTTP localhost works for the
screenshot capture.
"""
from __future__ import annotations
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_DIR = Path("/home/z/my-project/phinox")
OUT_DIR = Path("/home/z/my-project/download")

PORT = 8794
BASE_URL = f"http://127.0.0.1:{PORT}"

ENV = {
    **os.environ,
    "DJANGO_SETTINGS_MODULE": "config.settings.no_debug",
    "DJANGO_SECRET_KEY": "test-secret-no-debug-for-404-screenshot",
    "ALLOWED_HOSTS": "*",
}


def main() -> int:
    print(f"[+] Starting Django on 127.0.0.1:{PORT} (no_debug settings, DEBUG=False) ...")
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
    time.sleep(5)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        print(f"  ! Playwright unavailable: {exc}")
        server_proc.terminate()
        return 1

    rc = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        page = context.new_page()

        print("[+] phase3_05_404_stitch")
        try:
            response = page.goto(f"{BASE_URL}/this-page-does-not-exist-phase3-test/", wait_until="networkidle", timeout=20000)
            print(f"    HTTP {response.status if response else 'unknown'}")
            page.wait_for_timeout(500)
            out_path = OUT_DIR / "phase3_05_404_stitch.png"
            page.screenshot(path=str(out_path), full_page=False)
            print(f"    → {out_path.name}  ({out_path.stat().st_size} bytes)")
        except Exception as exc:
            print(f"  ! Failed: {exc}")
            rc = 1

        browser.close()

    print("\n[+] Stopping Django ...")
    try:
        os.killpg(os.getpgid(server_proc.pid), signal.SIGTERM)
        server_proc.wait(timeout=5)
    except Exception:
        try: server_proc.kill()
        except: pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
