#!/usr/bin/env python3
"""PHINOX-FIX-DJANGO-COMMENT-SYNTAX — template comment syntax linter.

Scans templates/**/*.html for Django template comment syntax violations:
  1. {# ... #} spanning multiple lines (Django doesn't support multi-line {# #}).
  2. {% comment %} without a matching {% endcomment %}.
  3. {% endcomment %} without a matching {% comment %}.
  4. Mismatched {# / #} counts.

Usage:
    python scripts/lint_django_comment_syntax.py [--fix]

    --fix: attempt automatic fixes (convert multi-line {# #} to {% comment %}).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple


class Violation(NamedTuple):
    file: Path
    line: int
    rule: str
    message: str
    context: str


def scan_file(filepath: Path) -> list[Violation]:
    """Scan a single template file for comment syntax violations."""
    content = filepath.read_text(encoding="utf-8")
    lines = content.splitlines()
    violations: list[Violation] = []

    # ── Rule 1: {# ... #} spanning multiple lines ────────────────────────
    # Django's {# #} comment MUST be on a single line. If {# appears on
    # one line and #} appears on a later line, it's a syntax error.
    in_single_line_comment = False
    for i, line in enumerate(lines, start=1):
        if in_single_line_comment:
            # We're inside a multi-line {# ... #} — that's a violation.
            if "#}" in line:
                in_single_line_comment = False
                violations.append(Violation(
                    filepath, i, "MULTILINE_HASH_COMMENT",
                    "{# ... #} spans multiple lines — Django requires single-line {# #}.",
                    f"  L{i}: {line.strip()[:100]}",
                ))
            else:
                # Still inside the multi-line block.
                violations.append(Violation(
                    filepath, i, "MULTILINE_HASH_COMMENT",
                    "Continuation of multi-line {# ... #}.",
                    f"  L{i}: {line.strip()[:100]}",
                ))
        else:
            # Check if this line opens a {# that doesn't close on the same line.
            open_count = line.count("{#")
            close_count = line.count("#}")
            if open_count > close_count:
                in_single_line_comment = True
                violations.append(Violation(
                    filepath, i, "MULTILINE_HASH_COMMENT",
                    "{# opened but not closed on the same line.",
                    f"  L{i}: {line.strip()[:100]}",
                ))

    # ── Rule 2 + 3: {% comment %} / {% endcomment %} balance ──────────────
    comment_open = 0
    comment_close = 0
    for i, line in enumerate(lines, start=1):
        comment_open += len(re.findall(r"{%\s*comment\s*%}", line))
        comment_close += len(re.findall(r"{%\s*endcomment\s*%}", line))

    if comment_open != comment_close:
        violations.append(Violation(
            filepath, 0, "COMMENT_BLOCK_MISMATCH",
            f"{comment_open} {{% comment %}} vs {comment_close} {{% endcomment %}} — must be equal.",
            f"  comment_open={comment_open}, comment_close={comment_close}",
        ))

    # ── Rule 4: {# and #} count mismatch ─────────────────────────────────
    hash_open = content.count("{#")
    hash_close = content.count("#}")
    if hash_open != hash_close:
        violations.append(Violation(
            filepath, 0, "HASH_COUNT_MISMATCH",
            f"{hash_open} {{# vs {hash_close} #}} — must be equal.",
            f"  hash_open={hash_open}, hash_close={hash_close}",
        ))

    return violations


def scan_directory(root: Path) -> list[Violation]:
    """Scan all .html files under root/templates/."""
    templates_dir = root / "templates"
    if not templates_dir.exists():
        return []
    all_violations: list[Violation] = []
    for html_file in sorted(templates_dir.rglob("*.html")):
        all_violations.extend(scan_file(html_file))
    return all_violations


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    violations = scan_directory(root)

    if not violations:
        print("✓ No Django template comment syntax violations found.")
        return 0

    print(f"✗ Found {len(violations)} violation(s):\n")
    current_file: Path | None = None
    for v in violations:
        if v.file != current_file:
            current_file = v.file
            print(f"📁 {v.file.relative_to(root)}")
        print(f"  L{v.line}: [{v.rule}] {v.message}")
        print(f"  {v.context}")
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
