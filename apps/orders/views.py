"""
apps.orders.views — Checkout + OrderConfirmation views.

Per دستور §6: checkout converts a Cart into an Order (snapshotting items
via ``create_order_from_cart``), then either:
  - creates a COD Payment (live) and marks ``payment_status='pending'``, OR
  - redirects to the card-payment simulation flow (TEST MODE ONLY — see
    ``apps.payments.views.PaymentSimulationView``).

``OrderConfirmationView`` verifies ``order.user == request.user`` (staff
bypass) and exposes order items, latest payment, and shipping address in
the context.
"""
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import DetailView, ListView

from apps.cart.models import Cart
from apps.cart.services import calculate_cart_subtotal
from apps.inventory.services import reserve_inventory
from apps.orders.models import Order
from apps.orders.services import create_order_from_cart
from apps.payments.services import create_cod_payment
from apps.shipping.models import ShippingAddress, ShippingMethod


@method_decorator(login_required, name="dispatch")
class CheckoutView(View):
    """Display the checkout form (GET) or place an order (POST).

    GET: renders ``orders/checkout.html`` with the user's shipping
    addresses, available shipping methods, cart items, and subtotal.

    POST:
      1. Validate ``shipping_address_id`` and ``shipping_method_id``.
      2. Look up the shipping cost from the chosen ``ShippingMethod``.
      3. Call ``create_order_from_cart(cart, user, shipping_cost)``.
      4. Attach the chosen ``ShippingAddress`` to the order (defensively —
         see note on ``order.shipping_address`` below).
      5. If ``payment_method == 'cod'``: create a COD Payment and set
         ``order.payment_status='pending'``, then redirect to the order
         confirmation page.
      6. If ``payment_method == 'card'``: redirect to the test-mode card
         payment simulation flow (``payments:test_payment``).

    Login is required (``method_decorator(login_required, ...)`` on dispatch).
    """

    template_name = "orders/checkout.html"

    # ------------------------------------------------------------------ GET
    def get(self, request) -> HttpResponse:
        """Render the checkout form with cart + shipping context."""
        cart = get_object_or_404(Cart, user=request.user)
        cart_items = list(cart.items.select_related("variant__product"))
        subtotal = calculate_cart_subtotal(cart)

        shipping_addresses = request.user.shipping_addresses.all()
        shipping_methods = ShippingMethod.objects.filter(is_active=True)

        context = {
            "cart": cart,
            "cart_items": cart_items,
            "subtotal": subtotal,
            "shipping_addresses": shipping_addresses,
            "shipping_methods": shipping_methods,
        }
        return render(request, self.template_name, context)

    # ----------------------------------------------------------------- POST
    @method_decorator(transaction.atomic, name="post")
    def post(self, request) -> HttpResponse:
        """Validate inputs, create the order, reserve inventory, dispatch to payment.

        PHASE-B §B5: the entire POST body is wrapped in ``transaction.atomic``
        via ``@method_decorator(transaction.atomic, name="post")``. If any
        step raises — Order creation, inventory reservation, COD payment
        creation — the entire transaction rolls back. No partial state
        (orphan Order without a Payment, reserved inventory without an
        Order, etc.) persists.

        PHASE-B §B2: after create_order_from_cart, calls ``reserve_inventory``
        so the items are held for this order until payment is captured or
        the order is abandoned. The Celery ``release_abandoned_reservations``
        task releases the reservation if the user abandons checkout
        (status=PENDING + created_at < now - 15min).
        """
        cart = get_object_or_404(Cart, user=request.user)

        # PHASE-B §B6: empty cart → redirect to products list (friendlier UX
        # than re-rendering checkout with an error message).
        if not cart.items.exists():
            messages.error(request, "Your cart is empty. Add a product first.")
            return redirect("catalog:product_list")

        shipping_address_id = request.POST.get("shipping_address_id")
        shipping_method_id = request.POST.get("shipping_method_id")
        payment_method = (request.POST.get("payment_method") or "").strip().lower()

        # --- Validate inputs ------------------------------------------------
        if not shipping_address_id or not shipping_method_id:
            messages.error(request, "Please select a shipping address and method.")
            return redirect("orders:checkout")

        if payment_method not in {"cod", "card"}:
            messages.error(
                request, "Please choose a payment method (COD or Card)."
            )
            return redirect("orders:checkout")

        # PHASE-A §A7: refuse the card-payment path in production with
        # PAYMOB_MODE='simulation'. config/settings/prod.py raises at import
        # time if PAYMOB_MODE='simulation' in prod, but this view-level
        # check is defense in depth — if someone accidentally unsets the
        # setting or runs staging with simulation, the order is NOT created.
        if (
            payment_method == "card"
            and not getattr(settings, "DEBUG", False)
            and getattr(settings, "PAYMOB_MODE", "simulation") == "simulation"
        ):
            raise ImproperlyConfigured(
                "Card payment path is FORBIDDEN in production with "
                "PAYMOB_MODE='simulation'. Set PAYMOB_MODE='sandbox' or "
                "'live' to enable real card payments."
            )

        shipping_address = get_object_or_404(
            ShippingAddress, pk=shipping_address_id, user=request.user
        )
        shipping_method = get_object_or_404(
            ShippingMethod, pk=shipping_method_id, is_active=True
        )

        # --- Create the order ----------------------------------------------
        # PHASE-B §B5: inside the @transaction.atomic wrapper, so a failure
        # in any subsequent step rolls back the Order creation.
        try:
            order = create_order_from_cart(
                cart=cart,
                user=request.user,
                shipping_cost=shipping_method.price,
                # PHASE-B §B1: pass the shipping_address so the Order
                # snapshots recipient/phone/governorate/city/street at
                # creation time — survives later address deletion/edit.
                shipping_address=shipping_address,
            )
        except ValueError as exc:
            messages.error(request, f"Could not place order: {exc}.")
            return redirect("orders:checkout")

        # --- Reserve inventory (PHASE-B §B2) -------------------------------
        # Idempotent — if the variant has no Inventory row, this is a no-op.
        # If the variant has insufficient stock, we still proceed (the
        # decrement_reserved_inventory flow will surface the shortfall
        # at payment capture time, and the Celery task releases the
        # reservation if the user abandons checkout).
        try:
            reserve_inventory(order)
        except Exception as exc:
            # reserve_inventory is itself atomic — if it raises, the
            # Order creation has already been rolled back by the outer
            # @transaction.atomic. Re-raise so the @transaction.atomic
            # wrapper catches it (defensive — the outer wrapper would
            # catch it anyway, but explicit is better).
            raise

        # --- Shipping address FK is already set by create_order_from_cart
        # (passed via shipping_address kwarg above). The defensive block
        # below handles the case where a future refactor drops the kwarg.
        if hasattr(order, "shipping_address") and order.shipping_address_id is None:
            order.shipping_address = shipping_address
            order.save(update_fields=["shipping_address", "updated_at"])

        # --- Dispatch to the chosen payment flow ---------------------------
        if payment_method == "cod":
            create_cod_payment(order)
            order.payment_status = Order.PaymentStatus.PENDING
            order.save(update_fields=["payment_status", "updated_at"])
            messages.success(
                request,
                f"Order {order.business_id} placed. Pay cash on delivery.",
            )
            return redirect("orders:confirmation", business_id=order.business_id)

        # card → test-mode simulation flow (per دستور, card payments are
        # TEST MODE ONLY in this phase).
        return redirect(
            "payments:test_payment", order_business_id=order.business_id
        )


class OrderConfirmationView(DetailView):
    """Display the order confirmation page.

    Looks up the order by ``business_id`` (``slug_field`` / ``slug_url_kwarg``).
    Restricted to the order's owner (or any staff user) via ``get_queryset``.

    Context adds: ``order_items`` (all OrderItem rows), ``payment`` (the
    most recent Payment row, if any), and ``shipping_address`` (the order's
    attached ShippingAddress, if the FK is present on the model).
    """

    model = Order
    template_name = "orders/order_confirmation.html"
    context_object_name = "order"
    slug_field = "business_id"
    slug_url_kwarg = "business_id"

    def get_queryset(self):
        """Restrict to the requesting user's orders (staff sees all).

        ``select_related("user", "shipping_address")`` + ``prefetch_related``
        for ``items`` and ``payments`` keeps the confirmation page at a
        constant number of queries — the template loops over order items
        and renders the latest payment, so without these the page would
        issue N+1 queries per order line / payment lookup.
        """
        qs = super().get_queryset().select_related(
            "user", "shipping_address"
        ).prefetch_related("items", "payments")
        if self.request.user.is_staff:
            return qs
        return qs.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        """Add order items, latest payment, and shipping address to context."""
        context = super().get_context_data(**kwargs)
        order = self.object
        context["order_items"] = order.items.all()
        context["payment"] = order.payments.order_by("-created_at").first()
        # Defensive — see CheckoutView note about order.shipping_address.
        context["shipping_address"] = getattr(order, "shipping_address", None)
        return context


# ---------------------------------------------------------------------------
# Phase 2 STITCH-INTEGRATION — Order History / Detail / Tracking views
# ---------------------------------------------------------------------------


class OrderHistoryView(LoginRequiredMixin, ListView):
    """List the requesting user's orders (newest first).

    Per user Phase 2 spec: ``LoginRequiredMixin + ListView`` over
    ``Order.objects.filter(user=request.user)``. Staff sees all orders.

    Renders the Stitch-styled order archive list with each row showing
    the business_id (PHX-ORD-XXXXXX), placed_at date, status badge,
    grand_total, and a "View Details" CTA linking to ``orders:detail``.
    """

    model = Order
    template_name = "orders/order_history.html"
    context_object_name = "orders"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            Order.objects.select_related("user", "shipping_address")
            .prefetch_related("items", "payments")
            .order_by("-created_at")
        )
        if self.request.user.is_staff:
            return qs
        return qs.filter(user=self.request.user)


class OrderDetailView(LoginRequiredMixin, DetailView):
    """Single order detail page.

    Per user Phase 2 spec: ``LoginRequiredMixin + DetailView`` looked up
    by ``business_id``. Restricted to the order's owner (or any staff).

    Context adds the same fields as OrderConfirmationView (order_items,
    payment, shipping_address) so the template can render a full
    read-only view of the placed order — useful when the customer comes
    back later to review past purchases.
    """

    model = Order
    template_name = "orders/order_detail.html"
    context_object_name = "order"
    slug_field = "business_id"
    slug_url_kwarg = "business_id"

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "user", "shipping_address",
        ).prefetch_related("items", "payments")
        if self.request.user.is_staff:
            return qs
        return qs.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        context["order_items"] = order.items.all()
        context["payment"] = order.payments.order_by("-created_at").first()
        context["shipping_address"] = getattr(order, "shipping_address", None)
        return context


class OrderTrackingView(LoginRequiredMixin, DetailView):
    """Order tracking page — shows the status timeline + ETA + dispatch info.

    Per user Phase 2 spec: ``LoginRequiredMixin + DetailView`` for Order.
    URL: ``/orders/<business_id>/track/``.

    Renders the Stitch "LIVE DISPATCH // TRACKING" timeline showing the
    4-stage progress: CONFIRMED → PROCESSING → SHIPPED → DELIVERED. The
    "current stage" is derived from ``order.status``. Includes a
    "CONTACT SUPPORT" CTA linking to ``pages:contact``.
    """

    model = Order
    template_name = "orders/order_tracking.html"
    context_object_name = "order"
    slug_field = "business_id"
    slug_url_kwarg = "business_id"

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "user", "shipping_address",
        ).prefetch_related("items", "payments")
        if self.request.user.is_staff:
            return qs
        return qs.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        context["order_items"] = order.items.all()
        context["payment"] = order.payments.order_by("-created_at").first()
        context["shipping_address"] = getattr(order, "shipping_address", None)
        # Derive the "current stage index" so the template can highlight the
        # active step in the 4-stage timeline.
        status_order = {
            Order.Status.PENDING: 0,
            Order.Status.CONFIRMED: 1,
            Order.Status.PROCESSING: 2,
            Order.Status.SHIPPED: 3,
            Order.Status.DELIVERED: 4,
        }
        context["current_stage"] = status_order.get(order.status, 0)
        return context
