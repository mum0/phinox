# PHINOX — Implementation Plan

> Status: living document. Update on each phase completion.
> Last updated: PHINOX-FINAL-PACKAGING-ENTRYPOINT (post-v2.1).

---

## 1. Phase Overview

| Phase | Scope | Status |
|-------|-------|--------|
| Phase 1 | Stitch pages (home/login/register/cart/checkout/payment/confirmation) | ✅ Complete |
| Phase 2 | Stitch pages (profile/addresses/order history/detail/tracking/about/wishlist) | ✅ Complete |
| Phase 3 | Stitch pages (FAQ/legal/404/PDP refresh/collections/search) | ✅ Complete |
| Phase 4.1 | Paymob webhook receiver + 19 tests | ✅ Complete |
| Phase 4.2 | PaymobClient (urllib) + bridge fix + `initialize_paymob_payment` | ✅ Complete |
| Phase 5 | Real auth (email+password login/register + email reset) | ✅ Complete |
| Phase 6 | Production hardening (CI/CD + Sentry + Docker multi-stage + health) | ✅ Complete |
| Google Free Tier | 8 cost-control flags + `DEPLOYMENT_MODES.md` | ✅ Complete |
| Unified Topbar | Unified topbar/footer + mobile drawer + cart badge | ✅ Complete |
| Bugfix Round 2 | Remove old footer + clean auth pages + email reset + email verify | ✅ Complete |
| PDP/Admin/Checkout Enhance | Alexandria rebrand + PDP variant picker + Admin matrix + inline address + Shipping/VAT | ✅ Complete |
| PHINOX-CRITICAL-REMEDIATION-A | 7 critical fixes (A1–A7) | ✅ Complete |
| PHINOX-CRITICAL-REMEDIATION-B | 7 promised features (B1–B7) | ✅ Complete |
| PHINOX-CRITICAL-REMEDIATION-C | 5 test-infra tasks (C1–C5) | ✅ Complete |
| PHINOX-CRITICAL-REMEDIATION-D | 7 prod hardening tasks (D1–D7) | ✅ Complete |
| PHINOX-FINAL-PACKAGING-ENTRYPOINT | ZIP packaging fix + entrypoint Celery role branching | ✅ Complete |
| PHINOX-V2.1-COMPLETE-ZIP | CELERY_BEAT_SCHEDULE + .env.example refresh + complete ZIP | ✅ Complete |

## 2. Stable ID System

| Entity    | Format           | Generator                    | Sequence Key        |
|-----------|------------------|------------------------------|---------------------|
| Order     | `PHX-ORD-000001` | `next_business_id("ORD")`    | `IDSequence.prefix="ORD"` |
| Customer  | `PHX-CUS-000001` | `next_business_id("CUS")`    | `IDSequence.prefix="CUS"` |
| Product   | `PHX-PROD-000001`| `BusinessIDModel` save hook  | `IDSequence.prefix="PROD"` |
| Payment   | `PHX-PAY-000001` | `BusinessIDModel` save hook  | `IDSequence.prefix="PAY"` |
| Cart      | `PHX-CART-000001`| `BusinessIDModel` save hook  | `IDSequence.prefix="CART"` |
| SKU       | `PHX-WNT-001`    | `next_sku(family_code)`     | `IDSequence.prefix="SKU_{FAMILY}"` |

## 3. Snapshot Denormalization (PHASE-B §B1)

- `CartItem.unit_price_snapshot` — frozen at add-to-cart time.
- `Order.shipping_recipient_name/phone_number/governorate/city/street_address` — frozen at order placement.
- `OrderItem.product_name/variant_sku/size_label/color_name` — frozen at order creation.
- Survives variant/address deletion (SET_NULL on FK, snapshots remain).

## 4. Inventory Reservation Lifecycle (PHASE-B §B2)

```
Cart add → checkout POST
   ↓
create_order_from_cart → Order (PENDING)
   ↓
reserve_inventory → quantity_reserved += N (F() atomic)
   ↓
+15 min → release_abandoned_reservations (Celery beat, every 5 min)
   ↓ (if abandoned)
   Order.status=CANCELLED + quantity_reserved -= N
   ↓ (if paid)
   decrement_reserved_inventory → quantity_on_hand -= N + quantity_reserved -= N
```

## 5. Paymob Webhook Flow (PHASE-A §A4 + §A5)

```
Paymob sends webhook → verify_paymob_signature (HMAC-SHA512)
   ↓ (valid)
   extract_paymob_transaction_data → paymob_order_id + transaction_id
   ↓
   lookup Payment by paymob_order_id (NOT provider_transaction_id)
   ↓
   if payment.is_test_transaction: return 200 {"status": "test_ignored"}
   ↓ (real payment)
   if payment.status == target_status: return 200 (idempotent skip)
   ↓
   with transaction.atomic() + select_for_update(payment):
     - update Payment.status + provider_transaction_id
     - update Order.payment_status
     - (outside atomic) decrement_reserved_inventory OR release_inventory_reservation
     - (outside atomic) send_payment_confirmation_email
```

## 6. Celery Beat Schedule (PHINOX-V2.1)

| Task | Cron | Source |
|------|------|--------|
| release_abandoned_reservations | every 5 min | `apps/orders/tasks.py` |

Wire-up: `config/settings/base.py` `CELERY_BEAT_SCHEDULE` dict + `docker-compose.yml`'s `celery_beat` service (`CELERY_ROLE=beat`).

## 7. Test Counts

- Django test runner (`python manage.py test apps`): 249 tests pass.
- pytest (`python -m pytest`): 252 passed, 1 skipped (SQLite-only concurrency test).
- Coverage: tracked via `pytest --cov=apps` (CI uploads to GitHub artifacts).

## 8. Open Items (Future Phases)

- SMS gateway for production OTP (currently email-based reset).
- BOS ERP sync (fields present, no API integration).
- Multi-step checkout (currently single-page CheckoutView).
- DRF router root (apps/api scaffolded, no viewsets yet).
- Low-stock alert email (Celery task stub in CELERY_BEAT_SCHEDULE comments).
- Cleanup-expired-OTPs task (Celery task stub in CELERY_BEAT_SCHEDULE comments).
