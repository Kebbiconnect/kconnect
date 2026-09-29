"""
KPN Custom Middleware
=====================
"""
from django.http import HttpResponsePermanentRedirect


class RemoveWWWMiddleware:
    """
    Permanently redirects any request with a 'www.' prefix to the
    non-www version. This ensures the Telegram Login Widget always
    loads correctly since BotFather only allows one domain per bot.

    e.g. https://www.kpn.com.ng/join/telegram/
      → https://kpn.com.ng/join/telegram/   (301 Permanent Redirect)
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host()

        if host.startswith('www.'):
            # Build the canonical URL without 'www.'
            non_www_host = host[4:]
            scheme = 'https' if request.is_secure() else 'http'
            canonical = f"{scheme}://{non_www_host}{request.get_full_path()}"
            return HttpResponsePermanentRedirect(canonical)

        return self.get_response(request)
