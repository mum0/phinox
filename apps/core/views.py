"""
Custom error handlers for PHINOX — 403, 404, 500.

All render the PHINOX-branded error pages (dark surface, fire-orange,
zero radius, Archivo Narrow). Context is deliberately minimal — Django's
error handlers receive no guarantee that normal context processors (cart,
session, auth) have run cleanly, since an error can happen mid-failure.
"""
from django.http import HttpResponseForbidden, HttpResponseNotFound, HttpResponseServerError
from django.template import loader


def custom_403(request, exception=None):
    """Render the PHINOX 403 page (access denied)."""
    template = loader.get_template("core/403.html")
    return HttpResponseForbidden(template.render({}, request))


def custom_404(request, exception=None):
    """Render the PHINOX 404 page (not found).

    Phase 3 STITCH-INTEGRATION: the Stitch "Lost Coordinates" 404 page
    surfaces the requested path + a request_id + timestamp in a
    "telemetry log" panel for diagnostic clarity. Both come from the
    request itself (no DB access — safe to render even on a mid-failure
    request).
    """
    import uuid
    template = loader.get_template("core/404.html")
    context = {
        "request_path": request.path,
        "request_id": getattr(request, "request_id", None) or str(uuid.uuid4())[:8],
        "request": request,
    }
    return HttpResponseNotFound(template.render(context, request))


def custom_500(request):
    """Render the PHINOX 500 page (server error).

    Note: Django does NOT pass `exception` to handler500 — only `request`.
    The template degrades gracefully (request_id/error_id use |default:"—").
    """
    template = loader.get_template("core/500.html")
    return HttpResponseServerError(template.render({}, request))
