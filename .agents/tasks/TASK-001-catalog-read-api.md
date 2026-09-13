# TASK-001 — Catalog Read API (Phase 3a)

> **Phase**: 3a (first task of Phase 3 — read APIs + auth)
> **Status**: ready (awaiting agent pickup)
> **Assigned to**: first agent to pick this up
> **Blocks**: TASK-002 (cart service), TASK-003 (PDP page), TASK-005 (search)
> **Blocked by**: nothing (schema is complete from Phase 2)
> **Estimated size**: ~6 new files, ~250 LOC, 1 migration-free change (models unchanged)

---

## Goal

Expose `Category`, `Product`, and `ProductVariant` as **read-only** DRF
endpoints so that the future cart, PDP, PLP, and search features have a
catalog data source to call. This is the first real exercise of the DRF
stack on top of the Phase 2 schema — it validates that the models,
constraints, and indexes actually work end-to-end through a real API.

This task is deliberately **read-only**. No write endpoints, no auth, no
search, no filtering beyond `is_active` and category. Those land in later
tasks. See "Out of scope" below.

---

## Scope

### Files to create
- `apps/catalog/serializers.py` — `CategorySerializer`, `ProductImageSerializer`,
  `ProductVariantSerializer`, `ProductSerializer`, `CollectionSerializer`.
- `apps/catalog/viewsets.py` — `CategoryViewSet`, `ProductViewSet`,
  `CollectionViewSet` (all `ReadOnlyModelViewSet`).
- `apps/catalog/urls.py` — DRF router for the above, app-level.
- `apps/catalog/tests/test_api.py` — pytest test module covering happy path
  + 404 + `is_active` filter.
- `apps/catalog/factories.py` — factory-boy factories for `Category`,
  `Color`, `Size`, `Product`, `ProductVariant`, `ProductImage` (test data).
- `apps/api/urls.py` — wires the catalog router under `/api/v1/`.

### Files to modify
- `config/urls.py` — add `path("api/v1/", include("apps.api.urls"))`.

### Files NOT to touch
- `apps/catalog/models.py` — schema is frozen from Phase 2. If you think a
  model needs a change, stop and escalate (it would be a Phase 2 regression).
- `apps/catalog/migrations/` — no migration should be needed. If
  `makemigrations --check` reports drift, that's a Phase 2 bug — report it,
  do not silently regenerate the migration.
- `AGENTS.md`, `ARCHITECTURE_MAP.md` — governance files, off-limits without
  human sign-off.

---

## API contract

### `GET /api/v1/products/`
- **Query params**:
  - `category=<slug>` — filter by category slug (includes children, depth ≤ 3).
  - `collection=<slug>` — filter by collection slug.
  - `is_active=true` — default `true`. Pass `false` to include inactive
    (staff only — see Auth below; for now, return 403 for non-staff).
- **Pagination**: DRF `PageNumberPagination`, 24 per page (already set in
  `REST_FRAMEWORK` settings).
- **Response 200**:
  ```json
  {
    "count": 142,
    "next": "https://phinox.example/api/v1/products/?page=2",
    "previous": null,
    "results": [
      {
        "id": "uuid",
        "name": "Phinox Field Jacket",
        "slug": "phinox-field-jacket",
        "category": {"id": 1, "name": "Outerwear", "slug": "outerwear"},
        "base_price": "3200.00",
        "currency": "EGP",
        "is_active": true,
        "primary_image": {"url": "/media/products/2025/01/field.jpg", "alt_text": "Field Jacket front view"},
        "variants_count": 6
      }
    ]
  }
  ```
- **Performance**: must use `select_related("category")`, `prefetch_related("images")`,
  and annotate `variants_count` with `Count("variants")`. No N+1. Verify
  with `django.db.connection.queries` in a test (≤ 3 queries for a 24-item page).

### `GET /api/v1/products/{uuid}/`
- **Response 200**: full detail, including all variants and all images:
  ```json
  {
    "id": "uuid",
    "name": "Phinox Field Jacket",
    "slug": "phinox-field-jacket",
    "description": "...",
    "category": {"id": 1, "name": "Outerwear", "slug": "outerwear"},
    "collections": [{"id": 2, "name": "Winter 2025", "slug": "winter-2025"}],
    "base_price": "3200.00",
    "currency": "EGP",
    "is_active": true,
    "published_at": "2025-01-15T10:00:00+02:00",
    "images": [
      {"id": 1, "url": "/media/...", "alt_text": "...", "is_primary": true, "display_order": 0}
    ],
    "variants": [
      {
        "id": "uuid",
        "sku": "FJ-S-BLK",
        "size": {"id": 1, "label": "S", "size_type": "apparel"},
        "color": {"id": 2, "name": "Black", "hex_code": "#000000"},
        "price_override": null,
        "effective_price": "3200.00",
        "is_active": true
      }
    ]
  }
  ```
- **`effective_price`** = `price_override if price_override is not None else product.base_price`.
  Computed in the serializer, not stored.
- **Response 404**: `{"detail": "Not found."}` (DRF default).

### `GET /api/v1/categories/`
- **Response 200**: flat list, but each item includes `parent` and
  `children_count`. The client builds the tree (lighter server-side).
  ```json
  {
    "count": 18,
    "results": [
      {
        "id": 1,
        "name": "Men",
        "slug": "men",
        "parent": null,
        "children_count": 4,
        "is_active": true,
        "display_order": 0
      }
    ]
  }
  ```
- **Query params**: `is_active=true` (default), `parent=<id|null>` (filter
  by parent; `parent=null` returns roots).

### `GET /api/v1/collections/`
- **Response 200**: list of active collections.
- **Query params**: `is_active=true` (default).

### Auth
- **No auth required for read endpoints** (per `REST_FRAMEWORK` default
  `IsAuthenticatedOrReadOnly`).
- Staff-only filters (`is_active=false`) return 403 for non-staff. This
  can be relaxed once `is_staff` checking is wired (Phase 3b).

---

## Acceptance criteria

1. **`GET /api/v1/products/`** returns paginated list, 24/page, with
   `variants_count` annotation and no N+1 (verified by test).
2. **`GET /api/v1/products/{uuid}/`** returns full detail with variants
   and images, `effective_price` computed correctly.
3. **`GET /api/v1/categories/`** returns flat list with `children_count`.
4. **`GET /api/v1/collections/`** returns active collections.
5. **`is_active=false`** filter returns 403 for anonymous users.
6. **404** on non-existent UUID returns DRF default `{"detail": "Not found."}`.
7. **`ruff check . && ruff format --check .`** passes.
8. **`pytest apps/catalog/tests/`** passes with ≥ 90% coverage on the new
   serializers + viewsets.
9. **`python manage.py makemigrations --check --dry-run`** reports "no
   changes" (proves no model drift).
10. **Worklog entry appended** to `.agents/worklog.md` per `.agents/CONTRIBUTING.md §2`.

---

## Out of scope (do NOT do these — they are later tasks)

- Write endpoints (POST/PUT/DELETE) — Phase 5 (admin polish).
- Full-text search — TASK-005.
- Filtering by size/color/price — TASK-006 (PLP).
- Auth (login/register/OTP) — TASK-004.
- Cart integration — TASK-002.
- PDP template rendering — TASK-003.
- Caching (`@method_decorator(cache_page(...))`) — Phase 6 (perf).
- API versioning beyond `/api/v1/` — not needed yet.
- OpenAPI schema generation — Phase 6.

If you find yourself wanting to do any of these, **stop** — you're crossing
a phase boundary. Escalate.

---

## Implementation notes

### Serializer structure
- Use `HyperlinkedModelSerializer` for the list endpoints (lighter payload,
  follows REST conventions) **or** `ModelSerializer` with explicit `id`
  field (simpler for the future SPA to consume). **Decision: use
  `ModelSerializer` with explicit `id`** — the future frontend is
  server-rendered Django templates + vanilla JS, not a hyperlinks-following
  SPA. Log this decision in the worklog.
- Nested writes are not needed (read-only). Set `read_only=True` on FK/M2M
  fields where DRF would otherwise complain.
- `ProductVariantSerializer.effective_price` is a `SerializerMethodField`
  reading `obj.price_override or obj.product.base_price`.

### Viewset structure
- `queryset` on each viewset must apply the default `is_active=True` filter
  and use `select_related` / `prefetch_related` to avoid N+1.
- Override `get_queryset` to handle `?is_active=false` for staff.
- `lookup_field = "id"` (UUID) for `ProductViewSet`, `"slug"` is **not**
  used as lookup (slugs can change; UUIDs don't). The `?category=<slug>`
  query param is a filter, not a lookup.

### Factories
- `CategoryFactory` — creates a root category by default; pass `parent=`
  for a child.
- `ColorFactory` — `name` sequence ("Black", "White", ...), `hex_code`
  matching.
- `SizeFactory` — `label` sequence ("S", "M", "L", "XL"), `size_type`
  default `apparel`.
- `ProductFactory` — creates a `Category` via `SubFactory` if not passed,
  `base_price` random Decimal between 500 and 5000.
- `ProductVariantFactory` — creates `Product`, `Size`, `Color` via
  subfactories; `sku` unique sequence.
- `ProductImageFactory` — `is_primary=False` by default (the unique
  constraint on `is_primary=True` would otherwise fire on the second
  factory call).

### Test cases (minimum)
1. `test_list_products_returns_paginated_results` — create 25 products,
   GET list, assert `count=25`, `results` has 24 items, `next` is set.
2. `test_list_products_active_filter_default` — create 1 active + 1
   inactive, GET list, assert only active returned.
3. `test_list_products_is_active_false_requires_staff` — anonymous GET
   with `?is_active=false`, assert 403.
4. `test_retrieve_product_returns_variants_and_images` — create product
   with 2 variants + 2 images, GET detail, assert structure.
5. `test_retrieve_product_effective_price_uses_override` — variant with
   `price_override=100`, product `base_price=200`, assert `effective_price="100.00"`.
6. `test_retrieve_product_404_on_unknown_uuid` — GET
   `/api/v1/products/00000000-0000-0000-0000-000000000000/`, assert 404.
7. `test_list_categories_includes_children_count` — create root with 3
   children, GET list, assert `children_count=3` on root.
8. `test_list_products_no_nplus1` — use `assertNumQueries` (Django test
   helper) to verify ≤ 3 queries for a 24-item page.

### Performance check
- The `assertNumQueries` test is non-negotiable. N+1 is the #1 risk on
  list endpoints with nested serializers. If the test fails, fix the
  `prefetch_related` calls — do not relax the assertion.

---

## Definition of done

- All 8 acceptance criteria met.
- Worklog entry appended (both "Started" and "Finished" sections).
- PR opened (or handoff package prepared for the human to open the PR).
- Next-task recommendation in the worklog proposes TASK-002 (cart service).

---

## Open questions this task may surface

(Pre-seeded from `ARCHITECTURE_MAP.md §8` — the agent should watch for these
and add worklog notes if they come up.)

- **#1 (token family)**: should the API response include any
  presentation/token metadata? **Working assumption: no — the API is
  data-only; presentation is the template's job.** If this assumption
  breaks, log it.
- **#4 (no Home source)**: does the API need a "featured products"
  endpoint for the home page? **Working assumption: not in this task —
  home page is blocked on Stitch source.** Log if it comes up.

If the task surfaces a **new** open question, add it to
`ARCHITECTURE_MAP.md §8` as a new row (append, do not edit existing rows)
and reference it in the worklog entry.
