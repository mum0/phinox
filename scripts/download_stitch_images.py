"""Download all Stitch CDN images into static/images/stitch/<page_slug>/.

Walks every Stitch code.html under /home/z/my-project/stitch_extract/,
finds every Google CDN image URL (`lh3.googleusercontent.com/aida-public/...`
or `/aida/...`), downloads each unique URL once to
`/home/z/my-project/phinox/static/images/stitch/<page_slug>/<N>.<ext>`,
and prints a manifest of (page → list of local paths).

Idempotent: re-running skips URLs already on disk.
Detects extension from the Content-Type header (png/jpeg/webp/svg+xml).
30s per-request timeout. Uses stdlib only (no new deps).

Output: prints a JSON manifest to stdout AND writes
`/home/z/my-project/phinox/static/images/stitch/_manifest.json` for
later template-rendering reference.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
STITCH_ROOT = Path("/home/z/my-project/stitch_extract")
PROJECT_ROOT = Path("/home/z/my-project/phinox")
OUT_ROOT = PROJECT_ROOT / "static" / "images" / "stitch"
MANIFEST_PATH = OUT_ROOT / "_manifest.json"

# Per-request timeout for image downloads (seconds).
TIMEOUT = 30
# Concurrent-ish: just sequential to avoid hammering Google's CDN.
USER_AGENT = "phinox-stitch-integration/1.0 (image archiver)"

# ---------------------------------------------------------------------------
# URL extraction
# ---------------------------------------------------------------------------
# Match both `lh3.googleusercontent.com/aida-public/...` and
# `lh3.googleusercontent.com/aida/...` (the latter appears for brand logos).
# We accept any path starting with `aida` under googleusercontent.com.
URL_RE = re.compile(
    r"https://lh3\.googleusercontent\.com/aida[A-Za-z0-9_\-/]+",
    re.IGNORECASE,
)

CONTENT_TYPE_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "image/gif": "gif",
}


def find_html_files(root: Path) -> Iterable[Path]:
    """Yield every code.html under root."""
    for p in root.rglob("code.html"):
        if p.is_file():
            yield p


def page_slug_from_path(html_path: Path) -> str:
    """Return a stable slug for the page's folder.

    E.g. .../phinox_authentication_register_auth_desktop/code.html
    → 'phinox_authentication_register_auth_desktop'
    (We keep the full folder name so mobile/desktop variants get their own
    folders. Templates will pick the right one.)
    """
    return html_path.parent.name


def extract_urls(html: str) -> list[str]:
    """Return de-duplicated Google CDN image URLs in the order they appear."""
    seen: set[str] = set()
    out: list[str] = []
    for m in URL_RE.finditer(html):
        url = m.group(0)
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def download(url: str, dest: Path) -> str | None:
    """Download url to dest. Returns the file extension actually used, or None on failure."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as r:
            content_type = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            data = r.read()
    except urllib.error.HTTPError as e:
        print(f"  ! HTTP {e.code} for {url[:80]}...", file=sys.stderr)
        return None
    except Exception as e:  # noqa: BLE001
        print(f"  ! {type(e).__name__}: {e} for {url[:80]}...", file=sys.stderr)
        return None

    ext = CONTENT_TYPE_EXT.get(content_type, "png")
    dest.parent.mkdir(parents=True, exist_ok=True)
    # If the file already exists with the right ext, skip re-writing.
    target = dest.with_suffix(f".{ext}")
    if not target.exists():
        target.write_bytes(data)
    return ext


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, list[str]] = {}
    total_downloaded = 0
    total_skipped = 0
    total_failed = 0

    for html_path in find_html_files(STITCH_ROOT):
        slug = page_slug_from_path(html_path)
        html = html_path.read_text(encoding="utf-8", errors="replace")
        urls = extract_urls(html)
        if not urls:
            continue
        page_dir = OUT_ROOT / slug
        page_files: list[str] = []
        for idx, url in enumerate(urls):
            # Use a deterministic filename: <idx>.<ext> (extension determined
            # from the Content-Type header at download time).
            base_path = page_dir / f"{idx:02d}"
            if base_path.with_suffix(".png").exists() or \
               base_path.with_suffix(".jpg").exists() or \
               base_path.with_suffix(".webp").exists() or \
               base_path.with_suffix(".svg").exists() or \
               base_path.with_suffix(".gif").exists():
                # Already downloaded. Find which ext exists.
                for ext in ("png", "jpg", "webp", "svg", "gif"):
                    cand = base_path.with_suffix(f".{ext}")
                    if cand.exists():
                        page_files.append(cand.relative_to(PROJECT_ROOT).as_posix())
                        break
                total_skipped += 1
                continue
            ext = download(url, base_path)
            if ext is None:
                total_failed += 1
                continue
            page_files.append(base_path.with_suffix(f".{ext}").relative_to(PROJECT_ROOT).as_posix())
            total_downloaded += 1
        manifest[slug] = page_files

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"\n=== Manifest written to {MANIFEST_PATH} ===")
    print(f"  Pages with images: {len(manifest)}")
    print(f"  Downloaded this run: {total_downloaded}")
    print(f"  Already on disk (skipped): {total_skipped}")
    print(f"  Failed: {total_failed}")
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
