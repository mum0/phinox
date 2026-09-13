"""Capture Phase 5 screenshots — real auth wiring.

Phase 5 pages:
  1. Login (real Django LoginView) — /accounts/login/
  2. Register (real SignupView) — /accounts/register/
  3. Profile (with real logout button pointing to accounts:logout) — /accounts/profile/
  4. Password Reset Step 1 (request OTP) — /accounts/password/reset/
  5. Password Reset Step 2 (verify OTP + new password) — /accounts/password/reset/confirm/?phone=...
  6. Post-login home page (shows "logged in" state — the home topbar now knows about user)

The script:
  - Sets up: ensures admin user exists with password admin12345
  - Starts Django dev server in-process
  - Uses Playwright with TWO browser contexts:
    - Anonymous context (for login/register/reset pages)
    - Authenticated context (after logging in via the Stitch login form)
  - Screenshots each page (1440x900 viewport)
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

PORT = 8803
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


def ensure_user() -> None:
    """Ensure the admin user exists with password admin12345 + a phone number."""
    import sys as _sys
    project_dir = str(PROJECT_DIR)
    if project_dir not in _sys.path:
        _sys.path.insert(0, project_dir)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    import django
    django.setup()
    from django.contrib.auth import get_user_model
    U = get_user_model()
    user, _ = U.objects.get_or_create(username="admin", defaults={"email": "admin@phinox.local"})
    user.set_password("admin12345")
    user.is_staff = True
    user.is_superuser = True
    user.phone = "+201012345678"  # for OTP reset flow
    user.save()


def main() -> int:
    print("[+] Ensuring admin user (admin/admin12345, phone=+201012345678)...")
    ensure_user()

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
        try: os.killpg(os.getpgid(server_proc.pid), signal.SIGTERM)
        except: pass
        return 2
    print("    Django ready.")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        print(f"  ! Playwright unavailable: {exc}")
        server_proc.terminate()
        return 3

    rc = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        anon_context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        auth_context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        anon_page = anon_context.new_page()
        auth_page = auth_context.new_page()

        # Pages to capture (anonymous)
        public_pages = [
            ("phase5_01_login",         f"{BASE_URL}/accounts/login/"),
            ("phase5_02_register",      f"{BASE_URL}/accounts/register/"),
            ("phase5_03_password_reset_request", f"{BASE_URL}/accounts/password/reset/"),
            ("phase5_04_password_reset_confirm", f"{BASE_URL}/accounts/password/reset/confirm/?phone=+201012345678"),
        ]
        for name, url in public_pages:
            print(f"[+] {name:36s}  {url}")
            try:
                anon_page.goto(url, wait_until="networkidle", timeout=20000)
                anon_page.wait_for_timeout(600)
                out_path = OUT_DIR / f"{name}.png"
                anon_page.screenshot(path=str(out_path), full_page=False)
                print(f"    → {out_path.name}  ({out_path.stat().st_size} bytes)")
            except Exception as exc:
                print(f"  ! Failed: {exc}")
                rc = 1

        # Now log in via the Stitch login form (real auth)
        print(f"[+] Authenticating via Stitch login form (admin/admin12345)...")
        try:
            auth_page.goto(f"{BASE_URL}/accounts/login/", wait_until="networkidle", timeout=15000)
            auth_page.fill("#id_username", "admin")
            auth_page.fill("#id_password", "admin12345")
            auth_page.click("button[type=submit]", timeout=10000)
            auth_page.wait_for_load_state("networkidle", timeout=15000)
            print(f"    Landed on: {auth_page.url}")
        except Exception as exc:
            print(f"  ! Login failed: {exc}")

        # Captures in auth context
        auth_pages = [
            ("phase5_05_profile_with_logout", f"{BASE_URL}/accounts/profile/"),
            ("phase5_06_home_authed",          f"{BASE_URL}/"),
        ]
        for name, url in auth_pages:
            print(f"[+] {name:36s}  {url}")
            try:
                auth_page.goto(url, wait_until="networkidle", timeout=20000)
                auth_page.wait_for_timeout(600)
                out_path = OUT_DIR / f"{name}.png"
                auth_page.screenshot(path=str(out_path), full_page=False)
                print(f"    → {out_path.name}  ({out_path.stat().st_size} bytes)")
            except Exception as exc:
                print(f"  ! Failed: {exc}")
                rc = 1

        # Full-page login + register shots
        for name, url in [
            ("phase5_07_login_full",     f"{BASE_URL}/accounts/login/"),
            ("phase5_08_register_full",   f"{BASE_URL}/accounts/register/"),
            ("phase5_09_password_reset_full", f"{BASE_URL}/accounts/password/reset/"),
            ("phase5_10_password_reset_confirm_full", f"{BASE_URL}/accounts/password/reset/confirm/?phone=+201012345678"),
        ]:
            print(f"[+] {name:36s}  {url}")
            try:
                anon_page.goto(url, wait_until="networkidle", timeout=20000)
                anon_page.wait_for_timeout(600)
                out_path = OUT_DIR / f"{name}.png"
                anon_page.screenshot(path=str(out_path), full_page=True)
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

    print()
    print("Phase 5 screenshots saved to:", OUT_DIR)
    for f in sorted(OUT_DIR.glob("phase5_*.png")):
        print(f"  {f.name:44s} {f.stat().st_size:>8d} bytes")
    return rc


if __name__ == "__main__":
    sys.exit(main())
