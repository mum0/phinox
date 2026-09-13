# PHINOX Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in PHINOX, please report it
responsibly. **Do NOT open a public GitHub issue** for security bugs.

### Preferred reporting channel

1. **Email**: `security@phinox.example` (the `DJANGO_ADMIN_EMAIL` recipient
   in production).
2. **PGP-encrypted**: send the report to the same address encrypted to the
   PGP key published at `https://phinox.example/.well-known/security.txt`.
3. **GitHub Security Advisory**: for repo-level vulnerabilities, use the
   "Security → Advisories" tab on GitHub (private disclosure to maintainers).

### What to include in the report

To help us triage + fix the vulnerability quickly, include:

- A clear description of the issue (what's vulnerable + the impact).
- The exact version / commit SHA where the vulnerability was found.
- Steps to reproduce (or a proof-of-concept).
- Your assessment of severity (low / medium / high / critical).
- Any suggested mitigation or fix (optional but appreciated).

### Response timeline

| Step | SLA |
|---|---|
| Acknowledgement of receipt | within 48 hours |
| Initial triage + severity rating | within 7 days |
| Fix or mitigation | within 90 days (severity-dependent) |
| Public disclosure (after fix is shipped) | coordinated with the reporter |

## Security architecture (Phase 6)

Per `AGENTS.md` §5 (Security Rules), PHINOX enforces:

### Auth & PII
- **Phone OTP rate-limit** (per دستور §5): max 3 OTP requests per 15 minutes per
  phone, max 5 verification attempts per OTP, 30-minute lockout after.
- **Phone numbers in E.164** (`+201012345678`) validated via `RegexValidator`.
- **Addresses are PII** — masked to governorate + city in non-admin logs.
- **Session fixation** — Django rotates the session key on login (do not disable).
- **Guest cart** identified by `session_key` — never exposed in API responses or URLs.

### Payments
- **Webhook signature verification mandatory** before any `Payment.status` change
  (Phase 4 — not yet wired).
- **Idempotency**: every webhook handler is idempotent (re-receive = no double-capture).
- **COD**: no webhook; manual capture (driver marks delivered); audit log every manual state change.
- **Test transactions**: `is_test_transaction=True` never affects real inventory.

### Web security
- `DEBUG=False` in staging/prod (no exceptions).
- `SECURE_SSL_REDIRECT=True`, `SECURE_HSTS_SECONDS=31536000` (1 year),
  `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True` in prod.
- `X_FRAME_OPTIONS="DENY"`. `SECURE_CONTENT_TYPE_NOSNIFF=True`.
- `SECURE_REFERRER_POLICY="same-origin"`.
- **CSP** via nginx (`docker/nginx.conf`): script-src allows `self`,
  `cdn.tailwindcss.com` (dev only — prod uses built `dist.css`), `unpkg.com`
  (htmx); style-src allows `self` + Google Fonts; font-src allows `self` +
  Google Fonts; frame-ancestors `'none'`.
- **CSRF** on every POST/PUT/DELETE form (DRF uses SessionAuthentication → CSRF applies to API too).
- **CORS** locked per-origin in prod (`CORS_ALLOWED_ORIGINS` from env, no open default).
- **SQL injection**: ORM only — raw SQL requires a review comment + parameterized inputs.

### Sentry PII scrubbing

Sentry is initialized with a `before_send` hook (`config.observability.scrub_pii_before_send`)
that masks the following PII before any event leaves the process:

- **Card numbers (PAN)**: 12-19 digit numbers → `**** **** **** XXXX` (last 4 only).
- **E.164 phone numbers**: `+201012345678` → `+2012***5678` (last 4 only).
- **6-digit OTP codes**: any standalone 6-digit number → `[OTP-SCRUBBED]`.

The hook walks the entire event tree (request, breadcrumbs, extra, exception
values, stack frames) and scrubs recursively. If scrubbing fails entirely,
the event is dropped (never leak raw PII).

### Secrets management

- **`.env` is gitignored** — never committed (per دستور §5).
- **Production secrets** come from the deploy host's environment (Hetzner VPS
  `.env` file or Docker secrets).
- **CI/CD** never reads production secrets — only the deploy workflow uses
  SSH_PRIVATE_KEY + HETZNER_HOST (which are non-secret SSH credentials, not
  Django secrets).
- **Paymob keys**, **Sentry DSN**, **S3 credentials** — all via env, never
  hardcoded (per دستور §5).

### Audit trail

Phase 5+ includes structured JSON logging (per دستور §11). Auth events are
logged at INFO level with structured fields:
- `user.signup` — user_id, customer_id, username
- `user.login` — user_id
- `user.password_reset` — user_id, phone (masked in non-admin logs)
- `otp.issued`, `otp.verified`, `otp.rate_limited`, `otp.locked_out` — phone (masked)

## Known security gaps (intentional — Phase 7+)

1. **Phase 4 (Paymob webhook) is not yet implemented** — the `Payment` model
   is Paymob-ready but the webhook handler + signature verification are
   deferred to Phase 7.
2. **SMS gateway for OTP delivery is not yet wired** — dev mode prints the OTP
   to the console + shows it in a banner; production needs an SMS gateway
   (Twilio or Egyptian provider — requires دستور §2 sign-off for the new dep).
3. **DB-level email uniqueness** is enforced at the form level (`SignupForm.clean_email`)
   but not yet at the DB level (no `UniqueConstraint`). A race condition could
   theoretically allow duplicate emails. Phase 7 adds the constraint.

## Compliance

PHINOX targets compliance with:
- **Egyptian Data Protection Law** (privacy policy + data retention at `pages/privacy.html`).
- **PCI-DSS** — card data is tokenized via Paymob (we never store raw PANs).
- **Central Bank of Egypt** standards — payment rails (CARD/valU/FAWRY/COD) follow the
  regulated flow.
