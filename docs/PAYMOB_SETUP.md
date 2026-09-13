# Paymob Integration Setup Guide

## Overview

This file documents how to complete Paymob integration after you finish their
onboarding process. All placeholders marked with `TODO` in the codebase refer
to this file.

## Step 1 — Paymob Account Setup

1. Register at https://accept.paymob.com/portal/en/signin
2. Complete KYC (Egyptian business documents required).
3. Get your credentials from Dashboard → Settings → Account Info:
   - API Key → add to `.env` as `PAYMOB_API_KEY`
   - HMAC Secret → add to `.env` as `PAYMOB_HMAC_SECRET`
4. Get Integration ID:
   - Dashboard → Developers → Payment Integrations
   - Select the "Card" integration → copy Integration ID
   - Add to `.env` as `PAYMOB_INTEGRATION_ID`
5. Get Iframe ID:
   - Dashboard → Developers → Iframes
   - Copy the default iframe ID
   - Add to `.env` as `PAYMOB_IFRAME_ID`

## Step 2 — Webhook Registration

1. Expose your local dev server via ngrok:
   ```bash
   ngrok http 8000
   ```
2. Copy the HTTPS URL (e.g., https://abc123.ngrok.io)
3. In Paymob Dashboard → Settings → Webhooks:
   - Add webhook URL: https://abc123.ngrok.io/payments/webhooks/paymob/
   - Enable events: Transaction Processed, Transaction Failed
4. Update .env:
   ```bash
   PAYMOB_WEBHOOK_URL=https://abc123.ngrok.io/payments/webhooks/paymob/
   ```

## Step 3 — Test Mode

- Keep `PAYMOB_SANDBOX=True` for testing.
- Paymob provides test card numbers in their sandbox docs.
- No real charges during sandbox mode.

## Step 4 — Production

- Change `PAYMOB_SANDBOX=False`.
- Update `PAYMOB_WEBHOOK_URL` to production URL.
- Update `PAYMOB_HMAC_SECRET` to production secret.
- Restart Django service.

## Where to find placeholders in code

Search the codebase for `TODO` comments:
```bash
grep -rn "TODO.*PAYMOB" .
```

Files that need manual edit after onboarding:
- `.env` (not committed)
- `config/settings/base.py` (defaults are empty)
- `PAYMOB_SETUP.md` (this file)

## Security Notes

- NEVER commit `.env` to git.
- NEVER log `PAYMOB_HMAC_SECRET` or `PAYMOB_API_KEY`.
- Webhook signature verification is MANDATORY (section 5 in AGENTS.md).
- Test the webhook with an invalid signature — it MUST return 403.

## Webhook Flow (Phase 4 — implemented)

```
Paymob → POST /payments/webhooks/paymob/?SHA512=<hmac>
                    │
                    ▼
    ┌───────────────────────────────┐
    │ 1. Read raw body bytes          │
    │ 2. Extract SHA512 signature     │
    │ 3. Verify HMAC-SHA512           │──→ 403 if invalid (no state change)
    │ 4. Parse JSON payload           │──→ 400 if malformed
    │ 5. Find Payment by txn_id       │──→ 200 if not found (no retry)
    │ 6. Idempotency check            │──→ 200 if already processed
    │ 7. Update Payment + Order       │
    │ 8. Decrement/Release inventory   │
    │ 9. Send confirmation email       │
    │ 10. Return 200                  │
    └───────────────────────────────┘
```

## Phase 4 Part 2 — Outbound API (not yet implemented)

The webhook receiver (Phase 4 Part 1) is complete. Phase 4 Part 2
(the outbound Paymob API calls that create an order + redirect the user
to the Paymob iframe) is a future task. The API credentials
(`PAYMOB_API_KEY`, `PAYMOB_INTEGRATION_ID`, `PAYMOB_IFRAME_ID`) are
already wired in `config/settings/base.py` so Part 2 is a no-config
change — only code needs to be written.

Expected flow for Part 2:
1. CheckoutView creates a Payment with `status='pending'`, `provider='paymob'`.
2. Backend calls Paymob `order/registration` API → gets `paymob_order_id`.
3. Backend calls Paymob `payment_keys` API → gets `payment_token`.
4. Backend redirects user to `https://accept.paymob.com/api/accept/iframes/<IFRAME_ID>?payment_token=<token>`.
5. User pays on Paymob's iframe.
6. Paymob sends webhook → Phase 4 Part 1 handler (already implemented) updates Payment + Order + inventory.
