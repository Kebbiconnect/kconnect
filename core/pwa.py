"""Root-scoped worker serving; no user data or external calls."""
from pathlib import Path
from django.contrib.staticfiles import finders
from django.http import Http404, HttpResponse
from django.views.decorators.http import require_GET


@require_GET
def service_worker(request):
    path = finders.find("sw.js")
    if not path:
        raise Http404("Service worker asset unavailable.")
    response = HttpResponse(Path(path).read_bytes(),
                            content_type="application/javascript")
    response["Cache-Control"] = "no-cache"
    response["Service-Worker-Allowed"] = "/"
    return response