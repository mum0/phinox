"""apps.checkout — placeholder app (logic currently lives in apps.orders).

The checkout flow (Cart → Order → Payment dispatch) is implemented in
``apps/orders/views.py:CheckoutView`` and ``apps/orders/services.py``.
This app is scaffolded but empty because:

  - دستور §0 rule 7: no business logic in a scaffolded app until that
    app's phase is greenlit.
  - The Phase 6 plan was to eventually extract checkout logic into its
    own app (multi-step checkout with address/payment/shipping/review
    stages), but the single-page CheckoutView in apps.orders.views is
    sufficient for the current scope.

When the multi-step checkout phase lands, this app will gain:
  - views.py: CheckoutStepGuardMiddleware + multi-step Class-Based Views.
  - services.py: checkout session state machine.
  - models.py: CheckoutSession (one per cart, holds the in-progress
    address/payment/shipping selections until the order is placed).

Until then, the ``checkout`` namespace has no URLs. Templates that link
to the checkout page use ``{% url 'orders:checkout' %}`` (not
``{% url 'checkout:...' %}``).

The app is registered in ``config/settings/base.py INSTALLED_APPS`` so
the future URL include + admin registration don't need a settings change.
"""
