"""Baseline security response headers -- defense-in-depth for an API that
only ever returns JSON, so a browser rendering an error body (or a
future HTML-serving endpoint added without thinking about this) doesn't
inherit unsafe defaults. The dashboard's own CSP (much stricter, since it
actually serves HTML/JS to render) lives in `frontend/nginx.conf.template`
instead -- this middleware's job is the backend's own responses, not the
SPA's.
"""

from __future__ import annotations

from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_HEADERS = {
    # This API returns JSON only -- nothing here should ever be
    # sniffed/executed as HTML/script by a browser that happens to load it.
    "X-Content-Type-Options": "nosniff",
    # No legitimate reason to frame any response from a JSON API.
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    # Never leak the full URL (which can carry a short-lived ws-ticket
    # query param, see nids.api.broadcast) to a cross-origin Referer.
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        for name, value in _HEADERS.items():
            response.headers.setdefault(name, value)
        return response
