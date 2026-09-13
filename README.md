# PHINOX — Egyptian E-Commerce Platform

Production-grade Django 5.0 e-commerce platform built against the Stitch UI export.
**Egyptian context**: EGP currency, 27 governorates, Paymob/valU/Fawry/COD payment rails,
Alexandria node dispatch.

## Phase Status

| Phase | Scope | Status |
|---|---|---|
| 1 | Foundation: scaffold + 14 apps + Docker + tokens | ✅ Done |
| 2 | DB schema: 15 models, migrations, admin registrations | ✅ Done |
| 3 | Catalog + cart + checkout + payment views + Stitch templates | ✅ Done |
| 4 | (Pending) Paymob webhook + valU/Fawry integration | ⬜ Deferred to Phase 7 |
| 5 | Real auth (email+password + phone-OTP reset) | ✅ Done |
| 6 | Production hardening: CI/CD, observability, Docker, docs | ✅ Done |

## What's Done

- **29 Stitch-integrated pages** across catalog, cart, checkout, payments, orders,
  accounts, wishlist, search, collections, FAQ, Legal (privacy/terms/returns),
  About, 404 refresh, PDP refresh.
- **Real authentication**: Django LoginView + SignupView + LogoutView. Phone-OTP
  password reset with rate-limit + lockout (per دستور §5).
- **Brand-aligned product images**: `seed_product_images` management command
  generates 800×1000 PNG placeholders per product.
- **CI/CD**: GitHub Actions (lint + test + migrations check + check --deploy)
  + auto-deploy to Hetzner VPS via docker compose.
- **Observability**: Sentry with PII-scrubbing `before_send` hook + structured
  JSON logging (stdlib, no extra dep) + /health/ + /health/ready/ endpoints.
- **Production Docker**: multi-stage Dockerfile (builder + runtime), non-root
  user, HEALTHCHECK, gunicorn + nginx + Celery worker/beat.
- **Settings audit**: prod.py has all security headers, STORAGES dict (Django 5.0),
  S3-backed media via Hetzner Object Storage, ADMINS/CSRF_TRUSTED_ORIGINS
  from env (no open defaults).

## Quick Start (Local Dev)

```bash
# 1. Clone + install deps
git clone <repo-url> phinox && cd phinox
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
npm install  # for Tailwind CLI (dev only — prod uses built dist.css)

# 2. Configure env
cp .env.example .env
# Edit .env: set DJANGO_SECRET_KEY + DATABASE_URL

# 3. Database setup
python manage.py migrate
python manage.py seed_products          # 20 demo products + variants + inventory
python manage.py seed_product_images      # 20 brand-aligned placeholder PNGs
python manage.py collectstatic --noinput  # required for ManifestStaticFilesStorage

# 4. Create superuser
python manage.py createsuperuser

# 5. Run dev server
python manage.py runserver
# Open http://127.0.0.1:8000/
```

## Tech Stack

| Layer | Tech | Notes |
|---|---|---|
| Backend | Python 3.12, Django 5.0, DRF 3.15 | Per دستور §2 — locked |
| Frontend | Tailwind CSS 3.4 (CDN in dev / built in prod) | Per دستور §2 — no JS framework |
| DB | PostgreSQL 16 (prod) / SQLite (dev) | Config-driven via `DATABASE_URL` |
| Cache | Redis 7 (django-redis) | |
| Async | Celery 5.4 + beat (Redis broker) | |
| Storage | Hetzner Object Storage (S3) | django-storages 1.14 in prod |
| Static | WhiteNoise + CompressedManifestStaticFilesStorage | Per دستور §11 |
| Server | gunicorn 22 (sync worker, preload_app) | Per `gunicorn.conf.py` |
| Reverse proxy | nginx 1.27 (alpine) | TLS + gzip + security headers |
| Observability | sentry-sdk 2 (PII-scrubbed) + stdlib JSON logging | No extra dep |

## Documentation

| Doc | Purpose |
|---|---|
| `DEPLOYMENT.md` | How to deploy to Hetzner Cloud VPS via docker compose |
| `OPERATIONS.md` | How to run migrations / restart celery / read logs |
| `SECURITY.md` | How to report a vulnerability |
| `DEVELOPMENT.md` | How to add a new feature (Tailwind watch, dev workflow) |
| `AGENTS.md` | The constitution — every agent MUST read this before touching the codebase |
| `ARCHITECTURE_MAP.md` | The as-is system map (read alongside AGENTS.md) |

## Constitution

This project follows `AGENTS.md` as the canonical source of truth. Read it in
full before any contribution. Key rules:

- **Zero border-radius.** Fire orange `#E85D04`. Dark surface `#121414`.
- **UUIDs on externally-referenced entities**, BigAutoField on internal ones.
- **Snapshot denormalization on `Order`/`OrderItem`/`CartItem`** is deliberate — don't normalize away.
- **CheckConstraints on every money field + every invariant** at the DB level, not just Python.
- **No new deps without human approval** (per دستور §2).
- **No business logic in templates.** Fat models, thin views, services for non-trivial logic.

## Known Gaps (intentional)

1. **Phase 4 (Paymob webhook) is deferred** — the `Payment` model is Paymob-ready
   (paymob_order_id, paymob_transaction_id, raw_webhook_payload), but the webhook
   handler is not yet implemented. COD orders work end-to-end; card payments are
   test-mode only.
2. **Product images are brand-aligned placeholders** — `seed_product_images`
   generates 800×1000 PNGs per product (dark surface + orange lock-stitch + product
   name). To replace with real photos, upload `ProductImage` rows via Django admin.
3. **OTP delivery is console-only in dev** — production needs an SMS gateway
   (Twilio or Egyptian provider). Wiring requires دستور §2 sign-off (new dep).
4. **Phase 1 open question #1 (which Stitch token family is canonical)** —
   both Family A (Checkout) + Family B (Editorial) ship side-by-side. Phase 7
   resolves this.

## License

Proprietary. © 2024-2026 PHINOX. All rights reserved.
