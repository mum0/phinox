# AGENTS.md — PHINOX Project Constitution

> **This is the canonical source of truth for the PHINOX project.**
> Every AI agent — Kimi, Z.AI, Claude, Codex, Cursor, Continue, or any other —
> **MUST read this file in full before touching the codebase.**
>
> Agent-specific overlays live in `.kimi/`, `.claude/`, etc. They may add
> tooling preferences or workflow tweaks, but **MUST NOT contradict this file.**
> If an overlay and this file conflict, **this file wins.**
>
> Humans may amend this file via PR. Agents must never rewrite it without
> explicit human sign-off in the task spec.

---

## 0. Golden Rules (read these first, always)

1. **AGENTS.md is the constitution.** `.kimi/`, `.claude/` are overlays, not replacements.
2. **Never silently resolve an open question.** Open questions live in `ARCHITECTURE_MAP.md §8` and `IMPLEMENTATION_PLAN.md §5`. If you hit one, document it in the worklog and **stop** — escalate to the human.
3. **Phase discipline is sacred:** schema → logic → API → UI. Do not start Phase N+1 work to "unblock" yourself; escalate instead.
4. **Append to worklogs, never overwrite.** The shared worklog is the project's memory across agents and sessions.
5. **Egyptian context is the default:** EGP currency, 27 governorates, Paymob/valU/Fawry/COD payment rails, Arabic + English copy.
6. **Zero border-radius. Fire orange `#E85D04`. Dark surface `#121414`.** These are brand law, not preferences.
7. **No business logic in a scaffolded app** until that app's phase is greenlit in the task spec.
8. **UUIDs on externally-referenced entities, BigAutoField on internal ones.** See `ARCHITECTURE_MAP.md §3` for the exact list.
9. **Snapshot denormalization on `Order`/`OrderItem`/`CartItem` is deliberate.** Do not "normalize" it away. See `ARCHITECTURE_MAP.md §3`.
10. **When unsure, write a short design note in the worklog and ask.** Guessing is worse than blocking.

---

## 1. Architecture

PHINOX is a **monolithic Django 5.0 application** with a server-rendered template layer (customer-facing pages) and a Django REST Framework API layer (for future SPA/mobile clients and AJAX interactions).

- **Single deployable**: one Django project (`config/`), 14 domain apps under `apps/`.
- **Async**: Celery workers + Celery beat, backed by Redis, for payments, email, inventory reservation, and scheduled tasks.
- **Cache**: Redis via `django-redis`.
- **DB**: PostgreSQL in staging/prod, SQLite in local dev (config-driven).
- **Static/media**: Whitenoise in dev/staging; `django-storages` with Hetzner Object Storage (S3-compatible) in prod.
- **Frontend**: Tailwind CSS. Currently via CDN (pixel-fidelity with the Stitch source); production CLI build is wired in `package.json` but not yet consumed by templates.
- **No SPA.** No React, no Vue, no Next.js server. If a task seems to need one, raise it as an open question — do not introduce a framework silently.

### Phase Roadmap
| Phase | Scope | Status |
|---|---|---|
| 1 | Foundation: project scaffold, settings split, Docker, template shells, 14 apps stubbed | ✅ Done |
| 2 | Database schema: 15 models across 9 apps, hand-authored migrations, admin registrations | ✅ Done |
| 3 | Read APIs + auth: catalog/category/product DRF endpoints, phone-OTP auth, address book | ⬜ Next |
| 4 | Cart + checkout + payments: cart service, checkout flow, Paymob integration, webhooks | ⬜ |
| 5 | Admin polish + search + reviews: admin customizations, full-text search, review moderation | ⬜ |
| 6 | Production hardening: CI/CD, Tailwind prod build, observability, load test, deploy | ⬜ |

---

## 2. Technology Stack

### Backend (locked)
- **Python 3.12**
- **Django 5.0.\***
- **Django REST Framework 3.15.\***
- **django-environ 0.11.\*** (env-var config)
- **django-filter 24.\***
- **django-cors-headers 4.\***
- **django-redis 5.\*** + **redis 5.\***
- **psycopg[binary] 3.1.\*** (Postgres driver)
- **celery 5.4.\***
- **Pillow 10.\*** (image handling)
- **gunicorn 22.\*** (WSGI server)
- **whitenoise 6.\*** (static files)

### Frontend (locked)
- **Tailwind CSS 3.4** with `@tailwindcss/forms` + `@tailwindcss/container-queries`
- **Fonts**: Archivo Narrow (display), JetBrains Mono (technical/labels), Hanken Grotesk (body — Family B only)
- **No JS framework.** Vanilla JS + WebGL shaders for the hero background (`static/js/shaders/`).

### Dev tools (locked)
- **pytest 8.\*** + **pytest-django 4.\*** + **factory-boy 3.\***
- **ruff 0.5.\*** (linter + formatter)
- **django-extensions 3.2.\***
- **django-debug-toolbar 4.\***

### Prod extras (locked)
- **django-storages[s3] 1.14.\*** (Hetzner Object Storage)
- **sentry-sdk 2.\*** (error tracking)

### Policy on adding dependencies
- **Do not add a new dependency without human approval.** If a task seems to need one, raise it in the worklog with: the name, the version, the license, the reason, and the alternative considered.
- No dependency that duplicates a Django built-in (e.g. no `django-model-utils` for `TimeStampedModel` — we have our own in `apps.core`).
- No JS build tooling beyond Tailwind CLI. No bundler. No transpiler.

---

## 3. Folder Structure

```
phinox/
├── AGENTS.md                      ← THIS FILE — the constitution
├── ARCHITECTURE_MAP.md            ← as-is system map (read alongside this file)
├── IMPLEMENTATION_PLAN.md         ← full multi-phase plan (referenced, not in this delivery)
├── README.md                      ← human-facing project intro
│
├── .agents/                       ← agent workflow artifacts
│   ├── CONTRIBUTING.md            ← how agents pick up + log work
│   ├── worklog.md                 ← shared, append-only work log
│   └── tasks/                     ← one file per task: TASK-NNN-slug.md
│       └── TASK-001-catalog-read-api.md
│
├── .claude/                       ← Claude overlay (anti-lock-in — points back here)
│   └── CLAUDE.md
├── .kimi/                         ← Kimi overlay
│   └── KIMI.md
│
├── manage.py
├── package.json                   ← Tailwind CLI build scripts (not yet wired)
├── tailwind.config.js             ← Family A tokens as theme.extend
├── requirements/
│   ├── base.txt
│   ├── dev.txt                    ← adds pytest, ruff, debug-toolbar, django-extensions
│   └── prod.txt                   ← adds django-storages, sentry-sdk
│
├── config/                        ← Django project package
│   ├── __init__.py
│   ├── settings/
│   │   ├── base.py                ← shared settings
│   │   ├── dev.py
│   │   ├── staging.py
│   │   └── prod.py
│   ├── urls.py                    ← root URLconf
│   ├── wsgi.py
│   ├── asgi.py
│   └── celery.py
│
├── apps/                          ← 14 domain apps
│   ├── core/                      ← abstract bases (UUIDModel, TimeStampedModel), 404 view
│   ├── pages/                     ← home, contact (static-ish)
│   ├── accounts/                  ← User, Address, Governorate enum
│   ├── catalog/                   ← Category, Collection, Size, Color, Product, ProductImage, ProductVariant
│   ├── inventory/                 ← Warehouse, Inventory
│   ├── cart/                      ← Cart, CartItem
│   ├── checkout/                  ← (scaffold — Phase 4)
│   ├── orders/                    ← Order, OrderItem
│   ├── payments/                  ← Payment
│   ├── shipping/                  ← (scaffold — Phase 4)
│   ├── promotions/                ← Coupon
│   ├── reviews/                   ← Review
│   ├── wishlist/                  ← WishlistItem
│   └── api/                       ← DRF router root (Phase 3)
│
├── templates/
│   ├── base.html                  ← root shell
│   ├── base_standard.html         ← Standard TopAppBar + Bottom Nav Dock
│   ├── base_checkout.html         ← Checkout shell (Phase 4)
│   ├── pages/
│   │   ├── home.html              ← placeholder
│   │   └── contact.html           ← ported from Stitch
│   └── core/
│       ├── 404.html               ← ported from Stitch
│       └── components/            ← reusable partials
│
├── static/
│   ├── css/tokens.css             ← both token families as CSS vars
│   └── js/shaders/                ← WebGL hero animations
│
└── docker/
    ├── Dockerfile
    ├── docker-compose.yml
    ├── entrypoint.sh
    └── nginx.conf
```

### Rules
- One app per domain. Do not split a domain across apps. Do not merge domains.
- Templates live in the project-level `templates/` dir, not per-app `templates/` dirs. Exception: if an app's templates are only ever used by that app and would never be overridden, they may live in `apps/<app>/templates/`.
- Static assets live in `static/`, not per-app `static/` dirs.
- No business logic in `config/` — only project wiring.
- No models in `apps/core/` — only abstract bases shared across apps.

---

## 4. Coding Rules

### Python
- **Style**: PEP 8, enforced by `ruff`. Line length 100.
- **Type hints** on all public functions and methods. Internal/private helpers may omit them.
- **Imports**: stdlib → third-party → Django/DRF → local apps. One blank line between groups.
- **No `print()`** in committed code. Use `logging` with structured fields: `logger.info("order.placed", extra={"order_id": order.id, "user_id": user.id})`.
- **No bare `except:`**. Catch specific exceptions. If you must catch broadly, re-raise after logging.
- **No mutable default arguments.**
- **f-strings** for string formatting, not `.format()` or `%`.

### Django
- **Fat models, thin views, serializers for API output.** Business logic lives on the model (or a service module) — not in the view, not in the serializer, not in the template.
- **No business logic in templates.** Templates do presentation only. If you need a computed value, compute it in the view or a context processor.
- **No raw SQL** without a review comment explaining why the ORM can't do it.
- **`select_related` / `prefetch_related`** on every list view that iterates FKs. N+1 queries are a bug.
- **`atomic()`** for any multi-write operation (order placement, cart merge, payment capture).
- **Signals** are a last resort. Prefer explicit method calls. If you must use a signal, document why.
- **Template `{% if debug %}` (lowercase).** Django's `django.template.context_processors.debug` exposes `debug` (lowercase) in the template context — NOT `DEBUG` (uppercase). `{% if DEBUG %}` silently evaluates to falsy and is a classic bug that prevents Tailwind CDN from loading in dev mode. Always use `{% if debug %}`.
- **Template `{# #}` comments are single-line ONLY.** This is a hard rule — Django closes `{# #}` at the first `#}` it encounters, which means multi-line `{#` blocks render as visible text (a `TemplateSyntaxError` or raw text leak). The rules are:
  - `{# single-line only #}` — for one-line notes. Must open AND close on the same line.
  - `{% comment %}...{% endcomment %}` — for multi-line comments. Must be balanced (every `{% comment %}` has a matching `{% endcomment %}` in the same file).
  - **Never mix** the two in the same block. If a comment spans multiple lines, use `{% comment %}`.
  - **Never put `{% url %}` tags inside `{# #}`** — they render as visible text.
  - **CI lint**: `python scripts/lint_django_comment_syntax.py` is run in CI to detect violations. The linter checks: (a) `{#` not closed on the same line, (b) `{% comment %}` / `{% endcomment %}` count mismatch, (c) `{#` / `#}` count mismatch. Run it locally before committing.

### Naming
- **Python**: `snake_case` for functions/variables/modules, `PascalCase` for classes.
- **Templates**: `kebab-case` filenames. `{% block %}` names in `snake_case`.
- **CSS/Tailwind**: `kebab-case` class names. Custom utility names prefixed with the domain (`phinox-`).
- **DB tables**: explicit `db_table = "app_model"` in every model's `Meta`. Never rely on Django's auto-generated name.
- **DB indexes**: explicit `name="..."` on every `Index` and `UniqueConstraint`. Never rely on auto-generated names — they break under refactor.

### Docstrings
- Every module starts with a docstring stating: which app it belongs to, which phase introduced it, what scope it covers, and what's explicitly **not** in it yet.
- Every model class has a docstring explaining: what real-world entity it represents, why the pk type was chosen, and any non-obvious design decisions (denormalization, constraint choices).

---

## 5. Security Rules

### Secrets
- **Never commit** `.env`, API keys, passwords, or tokens. `.gitignore` must cover them.
- **Paymob keys**, **Sentry DSN**, **S3 credentials**, **Django `SECRET_KEY`** — all via env vars, never hardcoded.
- **Never log secrets.** Paymob request bodies, webhook payloads with card data, and user passwords must never appear in logs or Sentry breadcrumbs.
- **`raw_webhook_payload`** on `Payment` is for audit only — render it in admin with card numbers masked.

### Web security
- `DEBUG=False` in staging/prod. No exceptions.
- `SECURE_SSL_REDIRECT=True`, `SECURE_HSTS_SECONDS=31536000`, `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True` in prod.
- `X_FRAME_OPTIONS="DENY"`. No clickjacking.
- **CSRF** on every POST/PUT/DELETE form. DRF uses `SessionAuthentication` → CSRF applies to API too.
- **CORS**: `CORS_ALLOWED_ORIGINS` locked per-origin in prod. `CORS_ALLOW_ALL_ORIGINS=True` only in `dev.py`.
- **SQL injection**: ORM only. Raw SQL requires a review comment and parameterized inputs.

### Auth & PII
- **Phone OTP rate-limit**: max 3 OTP requests per 15 minutes per phone number. Max 5 verification attempts per OTP. Lockout for 30 min after.
- **Phone numbers** stored in E.164 (`+201012345678`). Validate with the `RegexValidator` on `User.phone_regex`.
- **Addresses** are PII. Never log full address in Sentry. Mask to governorate + city in non-admin logs.
- **Session fixation**: rotate session key on login (`django.contrib.auth.login` does this by default — do not disable).
- **Guest cart** is identified by `session_key`. Do not expose the session key in any API response or URL.

### Payments
- **Webhook signature verification is mandatory** before any `Payment.status` change. No verification → no state change, full stop.
- **Idempotency**: every webhook handler must be idempotent. Receiving the same webhook twice must not double-capture.
- **COD** has no webhook — its "capture" is manual (driver marks delivered). Audit log every manual state change with user + timestamp.
- **Test transactions**: `is_test_transaction=True` must never affect real inventory `quantity_reserved`. Test orders must not show in customer-facing order history.

---

## 6. Database Rules

### Primary keys
- **UUID** on externally-referenced entities (URLs, cookies, API payloads, payment provider references): `User`, `Address`, `Product`, `ProductVariant`, `Cart`, `WishlistItem`, `Order`, `Payment`, `Coupon`, `Review`.
- **BigAutoField** on internal/operational tables (never referenced outside their parent): `Category`, `Collection`, `Size`, `Color`, `ProductImage`, `Warehouse`, `Inventory`, `CartItem`, `OrderItem`.

### Constraints
- **Every money field** has a `MinValueValidator(0)` **and** a DB-level `CheckConstraint(check=Q(field__gte=0))`. Validation at the app layer is not enough — bad data from a shell script or a migration must still fail.
- **Every invariant** (`total = subtotal + shipping − discount`, `line_total = unit_price × quantity`, `reserved ≤ on_hand`, `rating ∈ [1,5]`, `valid_until > valid_from`) is a DB `CheckConstraint`, not just Python logic.
- **Every uniqueness rule** (SKU per variant, one primary image per product, one review per user per product, one wishlist entry per user/product/variant) is a `UniqueConstraint`, possibly conditional (e.g. `condition=Q(is_primary=True)`).

### Indexes
- **Every FK** gets an index (Django does this automatically — do not disable).
- **Every filtered queryset's WHERE columns** gets a composite index. Look at the viewset's `get_queryset()` and add indexes to match.
- **Every index and constraint has an explicit `name=`**. Auto-generated names are fragile under refactor.

### Migrations
- **`models.py` is the source of truth.** Migrations are derived. If they drift, regenerate from models.
- **`python manage.py makemigrations --check --dry-run`** must pass in CI. Drift = build failure.
- **Never edit a squashed or applied migration.** Create a new one.
- **Squash** only at phase boundaries, only after all environments have applied the unsquashed set.

### Soft delete
- Catalog/order entities are **never hard-deleted**. Use `is_active=False` (catalog) or `status=CANCELLED` (orders).
- Hard-delete is allowed only on `CartItem`, `WishlistItem` (user-owned ephemeral data) and on `Address` (user-owned, but only if no order references it — otherwise soft-delete by renaming to `<original> (deleted)`).

### Denormalization policy
- Snapshot fields on `Order`, `OrderItem`, `CartItem.unit_price_snapshot` are **deliberate** (see `ARCHITECTURE_MAP.md §3`). Do not remove them.
- Any **new** denormalization must be: (a) documented in the model's docstring, (b) accompanied by a test proving the snapshot is written atomically with the parent write.

---

## 7. Git Rules

### Branching
- **Branch naming**: `phase/<N>-<feature-slug>` (e.g. `phase/3-catalog-read-api`, `phase/4-paymob-webhook`).
- **One branch per task.** A task = one file in `.agents/tasks/`.
- **Branch off `main`**, rebase before merge.

### Commits
- **Conventional Commits** format:
  - `feat(catalog): add ProductViewSet with variant prefetch`
  - `fix(orders): enforce line_total check on save, not just migration`
  - `chore(deps): bump ruff to 0.5.7`
  - `docs(agents): add TASK-002 spec for cart service`
- **Scope** = app name (`catalog`, `orders`, `accounts`, ...) or `core` / `deps` / `agents` / `docs`.
- **Body** explains **why**, not **what**. The diff shows what.
- **No `--no-verify`**. Hooks exist for a reason.

### Pull requests
- **≤ 400 lines** preferred. Larger PRs need a "why this can't be split" note.
- **Must reference the task**: `Task: .agents/tasks/TASK-NNN-...md` in the PR description.
- **Squash-merge** to `main`. Linear history, no merge commits.
- **Every PR must include**:
  - The change itself.
  - Tests for the change (see §8).
  - A migration if models changed (and `makemigrations --check` passes).
  - A worklog entry (see §11).

### What never gets committed
- `.env`, `.env.*` (except `.env.example`)
- `db.sqlite3`
- `media/` (user uploads)
- `staticfiles/` (collectstatic output)
- `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.ruff_cache/`
- `node_modules/`
- `.venv/`

---

## 8. Testing Rules

### Framework
- **pytest + pytest-django**. No Django `TestCase` (slower, less ergonomic).
- **factory-boy** for fixtures. No `unittest.mock` for model instances — use factories.
- **`conftest.py`** at the repo root for shared fixtures (db, client, auth user).

### What must be tested
- **Every model constraint** has a test proving it fires (try to save bad data, assert `IntegrityError` or `ValidationError`).
- **Every API endpoint** has:
  - Happy path (200/201 with correct body).
  - Auth failure (401/403).
  - Validation failure (400 with useful error message).
  - Not-found (404).
- **Every service function** (cart merge, coupon redemption, payment capture) has unit tests with both success and failure paths.
- **Webhooks** have tests with: valid signature, invalid signature, replayed idempotency key, missing fields.

### Coverage
- **80%** for apps in their active phase.
- **95%** for `payments`, `orders`, `accounts` (money + PII = highest risk).
- Coverage is tracked, not enforced in CI yet (Phase 6).

### Performance
- **Every test under 2 seconds.** Slow tests get a `@pytest.mark.slow` marker and run in a separate CI job.
- **No `time.sleep()`** in tests. Use `freezegun` or Celery `eager` mode for async.

### What is NOT tested
- Django's own internals (we trust the framework).
- Third-party libraries' behavior (we trust their tests).
- Visual/UI regression (no Playwright/Selenium yet — Phase 6).

---

## 9. UI/UX Rules

### Design tokens (brand law)
- **Zero border-radius.** `borderRadius: { DEFAULT: "0px", lg: "0px", xl: "0px", full: "9999px" }`. Do not add `rounded-*` classes. Form inputs, buttons, cards, images — all sharp corners.
- **Fire orange** `#E85D04` is the only accent color. Use sparingly: CTAs, active states, brand stitching.
- **Dark surface** `#121414` is the default background. Light mode is **not** supported and not planned.
- **Touch target minimum**: 48px. No clickable element smaller than this on mobile.
- **Two token families** ship side-by-side (Family A = Checkout, Family B = Editorial). Do not merge them until open question #1 is resolved.

### Typography
- **Archivo Narrow** — display/headlines (700 weight for display, 600 for headlines).
- **JetBrains Mono** — technical labels, data rows, all-caps metadata. Letter-spacing 0.20-0.25em.
- **Hanken Grotesk** — body text (Family B only; Family A has no body font yet).
- **No system fonts.** No `font-sans` fallback as the primary. Fonts load via Google Fonts `<link>` in the base templates.

### Layout
- **Mobile-first.** Breakpoints: `sm: 640px`, `md: 768px`, `lg: 1024px`, `xl: 1280px`.
- **Margins**: `margin-mobile` (16px Family A / 20px Family B) on mobile, `margin-desktop` (40px Family A / 64px Family B) on ≥ `lg`.
- **Grid**: 12 columns on desktop, 4 on mobile.
- **Sticky footer** is mandatory if a footer exists. `min-h-screen flex flex-col` on the wrapper, `mt-auto` on the footer.

### Accessibility
- **Semantic HTML**: `<main>`, `<header>`, `<nav>`, `<section>`, `<article>`. No `<div>` soup.
- **ARIA** on interactive non-native elements (custom dropdowns, shader controls).
- **`alt` text** on every product image. `aria-hidden="true"` on purely decorative images (textures, shader canvas).
- **Keyboard navigation**: every interactive element reachable via Tab, no keyboard traps.
- **Color contrast**: WCAG AA minimum. The dark surface + on-surface `#e3e2e2` pair passes AAA.

### Interaction
- **Loading states**: every async action shows a spinner or skeleton within 200ms.
- **Error states**: every form shows inline errors next to the field, not a generic toast.
- **Feedback**: toast notifications for non-critical actions (wishlist add, coupon applied). Modal dialogs for destructive actions (order cancel, address delete).

### Arabic/RTL
- **Planned for Phase 5+.** Templates must use logical properties (`ms-`, `me-`, `ps-`, `pe-`) not physical (`ml-`, `mr-`, `pl-`, `pr-`) so the RTL flip is mechanical.
- **Copy strings** that are order-sensitive (e.g. "3 items in cart") must use Django's `blocktrans` or `ngettext`, not string concatenation.

---

## 10. Business Rules

### Money
- **Currency**: EGP, everywhere. `currency` field defaults to `"EGP"`.
- **Decimal, never float.** `DecimalField(max_digits=10, decimal_places=2)` on every money field. No `FloatField`, no `float()` casts in business logic.
- **Rounding**: half-up to 2 decimal places, only at the presentation layer (`floatformat` template filter). Internal math keeps full precision.

### Geography
- **27 governorates** as a `TextChoices` enum on `accounts.Governorate`. Not a table. Not user-editable. If a 28th governorate is created (unlikely), it's a migration + enum update, not a DB row insert.
- **Shipping methods**: `STANDARD_GROUND` (nationwide) and `SAME_DAY_ALEXANDRIA` (Alexandria only). No other options. The Stitch UI's "Same Day (Alexandria)" tile maps to the latter.

### Payments
- **Four providers**, all in the `Payment.Provider` enum: `CARD` (Visa/Mastercard via Paymob), `VALU` (BNPL), `COD` (Cash on Delivery), `FAWRY` (FawryPay).
- **Paymob is the card processor.** valU is a Paymob-hosted BNPL method. FawryPay is a separate aggregator. COD is manual.
- **Order of operations for card payment**:
  1. Create `Payment(status=PENDING, provider=CARD)`.
  2. Call Paymob `order/registration` → store `paymob_order_id`.
  3. Call Paymob `payment_keys` → get iframe URL → redirect user.
  4. User pays → Paymob sends webhook → verify signature → set `status=CAPTURED` (or `FAILED`).
  5. On `CAPTURED`: mark `Order.status=CONFIRMED`, decrement inventory `quantity_reserved`.
- **COD order placement**: `Payment(status=PENDING, provider=COD)`, `Order.status=CONFIRMED` immediately (no payment to wait for), inventory reserved. On delivery, staff manually marks `Payment.status=CAPTURED`.

### Coupons
- **Percentage or fixed**, never both on one coupon. `percentage` capped at 100 (DB check).
- **`minimum_order_amount`**: if set, cart subtotal must meet or exceed it.
- **`max_uses`**: blank = unlimited. `times_used` increments on successful redemption, rolls back on order cancel.
- **`valid_from` / `valid_until`**: DB check enforces `valid_until > valid_from`.
- **One coupon per order.** Stacking is not supported.

### Inventory
- **`quantity_on_hand`**: actual stock on the shelf.
- **`quantity_reserved`**: held for in-progress carts/checkouts. `quantity_available = on_hand − reserved`.
- **Reservation happens at checkout start**, release happens at checkout abandon (15-min TTL) or order cancel.
- **`low_stock_threshold`**: default 5. Admin alerts when `quantity_available ≤ threshold`.

### Reviews
- **One review per user per product** (DB unique constraint).
- **Rating 1-5** (DB check). No half-stars, no text-only reviews.
- **`is_verified_purchase`**: set True only if the user has a `DELIVERED` order containing this product.
- **`is_approved`**: defaults False. Staff approves before it shows on the PDP. Spam/abuse handling is manual for now.

### Wishlist
- **Optional variant pin**: user can save a product (any variant) or a specific variant. Both are valid.
- **Unique per user/product/variant** (DB constraint). Re-saving the same combo is a no-op, not an error.

### Orders
- **`order_number`** is human-readable (e.g. `PHX-2025-000123`), generated at placement, unique. The UUID `id` is the internal/external-API identifier.
- **`total = subtotal + shipping_cost − discount_amount`** is a DB check. If these three don't reconcile, the insert fails — this catches cart/pricing bugs at the worst possible moment, which is exactly when you want to catch them.
- **Status transitions**: `PENDING → CONFIRMED → PROCESSING → SHIPPED → DELIVERED`. `CANCELLED` and `REFUNDED` are terminal side-states. No backward transitions except `CONFIRMED → PENDING` (admin only, with audit log).

---

## 11. AI Agent Rules

### Hierarchy of authority
1. **`AGENTS.md`** (this file) — the constitution. Highest authority.
2. **`ARCHITECTURE_MAP.md`** — the as-is system map. Read alongside this file.
3. **`.agents/tasks/TASK-NNN-*.md`** — the specific task you've been assigned.
4. **`.kimi/KIMI.md` / `.claude/CLAUDE.md` / etc.** — agent-specific overlays. May refine workflow, may not contradict the above.

### Before starting any task, an agent MUST:
1. Read `AGENTS.md` in full (this file).
2. Read `ARCHITECTURE_MAP.md` in full.
3. Read `.agents/CONTRIBUTING.md` (worklog convention + how to pick up tasks).
4. Read `.agents/worklog.md` (what previous agents have done — append-only, read all of it).
5. Read the specific task file in `.agents/tasks/` that was assigned.
6. Read the relevant app's `models.py` and, if it exists, `views.py` / `serializers.py` / `urls.py`.

### While working, an agent MUST:
- **Append to `.agents/worklog.md`** at minimum: when you started, what you did, what you decided, what you're blocked on, when you stopped. Never overwrite — append a new `---` section.
- **Never silently resolve an open question** from `ARCHITECTURE_MAP.md §8`. If you hit one, document it in the worklog and stop. Do not guess.
- **Never skip phases.** If the task is Phase 3 and you find yourself needing Phase 4 work, escalate — do not "unblock" yourself by doing Phase 4 work informally.
- **Never install a new dependency** without human approval (see §2 policy).
- **Never rewrite this file (`AGENTS.md`)** without explicit human sign-off in the task spec.
- **Never edit a migration that's been applied.** Create a new one.
- **Never hard-delete catalog or order entities.** Soft-delete only (see §6).
- **Never commit `.env`, secrets, or credentials.**
- **Never disable a test to make CI pass.** Fix the test or fix the code. If the test is wrong, document why in the PR.

### When finished, an agent MUST:
1. Run `ruff check . && ruff format --check .` — must pass.
2. Run `pytest` — must pass (or, if no tests exist for the touched app yet, document that in the worklog).
3. Run `python manage.py makemigrations --check --dry-run` — must report "no changes" (proves models and migrations are in sync).
4. Append a completion entry to `.agents/worklog.md` with: files added/changed, decisions made, open questions surfaced, next-task recommendation.
5. If the task introduced a new open question, add it to `ARCHITECTURE_MAP.md §8` (append a row, do not edit existing rows).

### Agent-specific overlays
- **`.kimi/KIMI.md`** — Kimi's overlay. May specify: preferred file-reading order, max context budget, response language preferences, tool-call patterns.
- **`.claude/CLAUDE.md`** — Claude's overlay. By policy, this is **anti-lock-in**: it points back to `AGENTS.md` and adds nothing that contradicts it. Claude-specific ergonomic notes only.
- **New agents** (Codex, Cursor, Continue, etc.): create a `<agent-name>/<AGENT_NAME>.md` overlay following the same pattern. Do not edit `AGENTS.md` to "add support for" the new agent — the constitution is agent-agnostic by design.

### Anti-lock-in rule
PHINOX must never become dependent on a single AI agent. Concretely:
- **No agent-specific syntax in committed code.** No `// Claude: ...` comments, no `# kimi-ignore` pragmas. Comments are for humans.
- **No agent-specific build steps.** If a task can only be done by one agent, it's not done — escalate.
- **The constitution is portable.** If every agent disappeared tomorrow, a new one should be able to read `AGENTS.md` + `ARCHITECTURE_MAP.md` + `.agents/worklog.md` and continue the project.

---

*End of constitution. Read it, internalize it, build with it.*
