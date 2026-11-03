import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from app.core.config import settings

CSRF_COOKIE_NAME = "jobpulse_csrf"
CSRF_HEADER_NAME = "x-csrf-token"

class SecurityHeadersAndCSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Host Header Validation
        host = request.headers.get("host", "")
        if host and not any(host.startswith(allowed) for allowed in settings.ALLOWED_HOSTS):
            return JSONResponse(status_code=400, content={"detail": f"Invalid Host header: {host}"})

        # 2. Origin & Referer Validation on State-Changing Methods
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("origin")
            referer = request.headers.get("referer")

            # Check origin if present
            if origin:
                valid_origin = any(
                    origin.startswith(f"http://{allowed}") or origin.startswith(f"https://{allowed}")
                    for allowed in ["127.0.0.1", "localhost", "testserver"]
                )
                if not valid_origin:
                    return JSONResponse(status_code=403, content={"detail": "Cross-Origin request blocked by security policy."})
            # If no origin, check referer
            elif referer:
                valid_referer = any(
                    referer.startswith(f"http://{allowed}") or referer.startswith(f"https://{allowed}")
                    for allowed in ["127.0.0.1", "localhost", "testserver"]
                )
                if not valid_referer:
                    return JSONResponse(status_code=403, content={"detail": "Cross-Site Referer request blocked by security policy."})

        # Ensure a CSRF token cookie is present
        csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
        new_csrf_cookie = False
        if not csrf_token:
            csrf_token = secrets.token_hex(32)
            new_csrf_cookie = True

        # Attach token to request state so templates can render it
        request.state.csrf_token = csrf_token

        response: Response = await call_next(request)

        # Set secure HttpOnly/SameSite cookie if newly generated
        if new_csrf_cookie:
            response.set_cookie(
                key=CSRF_COOKIE_NAME,
                value=csrf_token,
                httponly=False, # Accessible to JS/HTMX for X-CSRF-Token header
                samesite="lax",
                secure=False # Local development
            )

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"

        return response

