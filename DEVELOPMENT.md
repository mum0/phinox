# PHINOX Development Guide

How to add a new feature to the PHINOX codebase. **Read `AGENTS.md` first** —
it's the canonical constitution, and many of the rules below derive from it.

## Prerequisites

- Python 3.12
- Node.js 20+ (for Tailwind CLI build)
- PostgreSQL 16 (or use SQLite in dev — see `config/settings/dev.py`)
- Redis 7 (or skip — dev gracefully degrades if Redis is down)

## Local setup

```bash
git clone <repo-url> phinox && cd phinox
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
npm install  # Tailwind CLI (dev only — prod uses built dist.css)

cp .env.example .env
# Edit .env: set DJANGO_SECRET_KEY + DATABASE_URL (or use the SQLite default)

python manage.py migrate
python manage.py seed_products          # 20 demo products + variants + inventory
python manage.py seed_product_images      # 20 brand-aligned placeholder PNGs
python manage.py collectstatic --noinput  # required for ManifestStaticFilesStorage
python manage.py createsuperuser
```

## Tailwind dev workflow

In dev, templates load Tailwind from the CDN (`<script src="https://cdn.tailwindcss.com">`).
The CDN reads the inline `tailwind.config = {...}` block in `templates/base.html`
and hot-compiles Tailwind classes in the browser — no build step needed for
fast iteration.

For production (or to test production locally):

```bash
# Build the production CSS:
npm run build:css        # writes static/css/dist.css (minified, ~30KB gzipped)
# Watch mode (auto-rebuild on template change):
npm run watch:css        # keeps running; Ctrl-C to stop
```

Templates use a hybrid approach (per Phase 6):
- `DEBUG=True` (dev): CDN script (hot-reload, no build step needed)
- `DEBUG=False` (prod): compiled `dist.css` (`{% static 'css/dist.css' %}`)

The compiled `dist.css` is checked into git so production deploys don't
need a Node.js build step in the Docker image.

To verify a production build locally:

```bash
npm run build:css
python manage.py collectstatic --noinput
# Start Django with DEBUG=False to use the built CSS:
DJANGO_SETTINGS_MODULE=config.settings.no_debug python manage.py runserver
# Visit http://127.0.0.1:8000/ — should render with the compiled dist.css.
```

## Adding a new feature

### 1. Pick the right app

PHINOX has 14 apps under `apps/`. Each app owns one domain — per دستور §3
"one app per domain":

| App | Domain | Add here when... |
|---|---|---|
| `catalog` | Products, Categories, Variants | adding a product-related model/view |
| `cart` | Cart, CartItem | adding cart mutations |
| `orders` | Order, OrderItem | adding order flow steps |
| `payments` | Payment | wiring a new payment provider |
| `accounts` | CustomUser, Addresses, Auth | adding user-facing features |
| `shipping` | ShippingMethod, ShippingAddress | adding a shipping tier |
| `inventory` | Warehouse, Inventory | adding stock location logic |
| `promotions` | Campaign, PromoCode | adding coupon logic |
| `reviews` | Review | adding review moderation |
| `wishlist` | WishlistItem | adding wishlist features |
| `analytics` | Attribution, Event | adding GA4 / tracking |
| `pages` | Static-ish pages | adding FAQ / about / contact |
| `core` | Abstract bases + Stable ID system | adding a shared abstract model |
| `api` | DRF router root | adding DRF endpoints |

### 2. Branch + commit

Per دستور §7:
- Branch naming: `phase/<N>-<feature-slug>` (e.g. `phase/7-paymob-webhook`).
- One branch per task. A task = one file in `.agents/tasks/`.
- Conventional Commits format: `feat(catalog): add ProductViewSet with variant prefetch`.
- Squash-merge to `main`. Linear history.

### 3. Write the model (if needed)

Per دستور §6:
- `models.py` is the source of truth — migrations are derived.
- Explicit `db_table = "app_model"` in every model's `Meta`.
- Explicit `name="..."` on every `Index` and `UniqueConstraint`.
- `CheckConstraint` on every money field + every invariant.
- UUIDs on externally-referenced entities; BigAutoField on internal ones.
- Snapshot denormalization on `Order`/`OrderItem`/`CartItem` is deliberate — don't normalize away.

### 4. Generate the migration

```bash
python manage.py makemigrations <app_name>
# Verify the migration applies cleanly:
python manage.py migrate
# Verify models + migrations are in sync (CI gate):
python manage.py makemigrations --check --dry-run
# Should print: "No changes detected"
```

### 5. Write the view + URL

Per دستور §3 + §4:
- Fat models, thin views, serializers for API output.
- `select_related` / `prefetch_related` on every list view that iterates FKs (N+1 = bug).
- `atomic()` for any multi-write operation (order placement, cart merge, payment capture).
- `@login_required` (or `LoginRequiredMixin`) for user-scoped views.
- URL names: snake_case, namespaced under the app (`catalog:product_detail`).

### 6. Write the template

Per دستور §9:
- `{% extends "base.html" %}` (or `base_standard.html` / `base_checkout.html`).
- `{% load static %}` at the top.
- `{% url %}` for every internal link — no hardcoded paths.
- `{% static %}` for every asset.
- `{% csrf_token %}` on every POST form.
- No business logic in templates — pass computed values via context.
- Zero border-radius (per دستور §9 brand law). Tailwind's `rounded-*` is
  overridden to `0px` in `tailwind.config.js`.

### 7. Write tests

Per دستور §8:
- pytest + pytest-django + factory-boy.
- `apps/<app>/tests.py` for unit tests.
- `apps/<app>/tests_views.py` for view tests.
- Every model constraint has a test proving it fires.
- Every service function has success + failure path tests.
- Every API endpoint has happy + auth-fail + validation-fail + not-found tests.
- Coverage 80% for active-phase apps, 95% for `payments`/`orders`/`accounts`.

### 8. Run CI locally before pushing

```bash
# Lint
ruff check .
ruff format --check .
# Tests
pytest --cov=apps --cov-report=term-missing
# Migrations drift
python manage.py makemigrations --check --dry-run
# Production readiness (warnings only)
python manage.py check --deploy || true
```

### 9. Push + open a PR

```bash
git push origin phase/7-paymob-webhook
# Open PR on GitHub. CI runs automatically. Squash-merge after review.
```

## Common gotchas

### Multi-line `{# #}` comments render as text

Django's `{# #}` comment tag is **single-line only**. A multi-line comment
containing a `{% url %}` tag will render the tag as raw visible text. Use
`{% comment %}...{% endcomment %}` for multi-line comments. This bit us in
Phase 1 + Phase 5 — see `worklog.md` for the pattern.

### ManifestStaticFilesStorage requires collectstatic

If you see `ValueError: Missing staticfiles manifest entry for 'css/tokens.css'`
in tests, run `python manage.py collectstatic --noinput` first. CI does
this in the test job's service setup.

### Tailwind CDN in dev vs built CSS in prod

If a Tailwind class isn't rendering in production (DEBUG=False), it's
likely because:
1. The class was added to a template but `npm run build:css` wasn't re-run
   (so `dist.css` is stale).
2. The class is in a template not scanned by Tailwind (`tailwind.config.js`
   `content` array — currently `templates/**/*.html` + `apps/**/templates/**/*.html`).

### `app_name = "orders"` namespace conflict

When two URL files share the same `app_name` and are include()'d separately,
Django's URL resolver only keeps the first one. Phase 2 used
`app_name = "orders_mgmt"` for the order management URL file (history /
detail / tracking) to avoid conflicting with `apps/orders/urls.py` (checkout /
confirmation). See `apps/orders/urls_orders.py` for the rationale.

### Tailwind `peer-checked` requires sibling input

The PDP variant selectors use `<input type="radio" class="sr-only peer">` +
a sibling `<div class="... peer-checked:border-primary">`. The `peer-checked:`
modifier only works if the `<input>` and the styled element are siblings
(both children of the same parent). Don't wrap them in different containers.
