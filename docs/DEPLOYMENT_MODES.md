# PHINOX Deployment Modes

This file documents the cost-control flags, their defaults, and the upgrade
path to Google Cloud free-tier alternatives. All flags default to **$0 cost**
(local/simulation backends).

## Flag Reference

| Flag | Default | Google Alternative | Cost |
|------|---------|-------------------|------|
| `PAYMOB_MODE` | `simulation` | `sandbox` then `live` (Paymob, not Google) | Paymob fees per transaction |
| `SMS_BACKEND` | `console` | `twilio` / `vonage` (not Google) | Per-SMS fee |
| `STORAGE_BACKEND` | `local` | `gcs` (Google Cloud Storage — 5GB free) | $0 up to 5GB, then ~$0.020/GB/month |
| `CACHE_BACKEND` | `locmem` | `redis` (not Google, requires Redis instance) | Hetzner Redis: ~EUR2/month |
| `ERROR_TRACKING` | `none` | `sentry` (free tier) or `gcp` (GCP Error Reporting) | Sentry: free tier; GCP: free tier |
| `EMAIL_BACKEND_MODE` | `console` | `gmail` (Gmail SMTP — free for low volume) | Free up to 500 emails/day |
| `USE_CELERY` | `False` | `True` (requires Redis) | Redis cost only |
| `USE_CLOUD_TASKS` | `False` | `True` (Google Cloud Tasks — 1M free/month) | Free up to 1M requests/month |

## Zero-Cost Default

With the default flags, PHINOX runs entirely on local/simulation backends:

- **Payments**: simulation mode (no real Paymob API calls; `PaymentSimulationView` handles test-mode).
- **SMS**: console (OTP printed to stdout — visible in runserver log).
- **Storage**: local filesystem (`media/` directory).
- **Cache**: Django LocMemCache (in-process, no Redis needed).
- **Error tracking**: none (no Sentry, no GCP — errors visible in Django logs only).
- **Email**: console (emails printed to stdout — visible in runserver log).
- **Async**: synchronous (no Celery, no Cloud Tasks — tasks run in-process).

This is suitable for:
- Local development.
- CI/CD testing.
- Initial staging on a single VPS (Hetzner CX21, ~EUR4/month).

## Upgrade Path

### Step 1: Enable Sentry error tracking (free tier)

```bash
# .env
ERROR_TRACKING=sentry
SENTRY_DSN=https://<your-dsn>@sentry.io/<project-id>
SENTRY_TRACES_SAMPLE_RATE=0.1
```

No new deps (sentry-sdk already in requirements/prod.txt).

### Step 2: Enable Redis cache (Hetzner VPS)

```bash
# .env
CACHE_BACKEND=redis
REDIS_URL=redis://redis:6379/0
USE_CELERY=True
```

Redis runs as a Docker container alongside Django (see docker-compose.yml).

### Step 3: Enable Gmail SMTP (free for low volume)

```bash
# .env
EMAIL_BACKEND_MODE=gmail
EMAIL_HOST=smtp.gmail.com
EMAIL_HOST_USER=your-app-password@gmail.com
EMAIL_HOST_PASSWORD=<app-specific-password>
```

Gmail allows 500 emails/day for free. Use an app-specific password (not your
account password). See Google's "App Passwords" docs.

### Step 4: Enable Google Cloud Storage (5GB free)

```bash
# .env
STORAGE_BACKEND=gcs
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
GCS_BUCKET_NAME=phinox-media
```

Uncomment in requirements/prod.txt:
```
django-storages[google]==1.14.*
google-cloud-storage==2.*
```

GCS gives 5GB free storage + 1GB free egress/month. PHINOX media is
small (product images < 1MB each, 20 products = ~20MB total).

### Step 5: Enable Paymob sandbox (real API, test cards)

```bash
# .env
PAYMOB_MODE=sandbox
PAYMOB_HMAC_SECRET=<from Paymob Dashboard>
PAYMOB_API_KEY=<from Paymob Dashboard>
PAYMOB_INTEGRATION_ID=<from Paymob Dashboard>
PAYMOB_IFRAME_ID=<from Paymob Dashboard>
PAYMOB_SANDBOX=True
PAYMOB_WEBHOOK_URL=https://<ngrok-or-domain>/payments/webhooks/paymob/
```

See `PAYMOB_SETUP.md` for step-by-step Paymob onboarding.

### Step 6: Go live (production Paymob + HTTPS + real SMS)

```bash
# .env
PAYMOB_MODE=live
PAYMOB_SANDBOX=False
SMS_BACKEND=twilio
# (or an Egyptian SMS provider like SMSMasr)
```

At this point, all backends are production-ready. The project is
commercial-launch ready.
