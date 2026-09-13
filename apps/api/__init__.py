"""apps.api — Phase 6 DRF router root (scaffolded, no viewsets yet).

Per دستور §0 rule 7: "No business logic in a scaffolded app until that
app's phase is greenlit in the task spec." This app is scaffolded with
__init__.py + apps.py ONLY — no models, no views, no serializers, no
URLs. A future Phase 6+ task will populate it with:

  - DRF router root at /api/
  - Viewsets for Product / ProductVariant / Cart / Order / Payment
  - Schema endpoint (drf-spectacular — requires دستور §2 sign-off)

The app is registered in ``config/settings/base.py INSTALLED_APPS`` so
the ``api`` namespace + the future URL include don't need a settings
change when the viewsets land.
"""
