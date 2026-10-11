"""Origin checks complement session-bound CSRF tokens, including pre-login forms."""

from fastapi.responses import JSONResponse

from backend.core.config import settings

PUBLIC_AUTH_WRITES = {
    f"/api/auth/{v}"
    for v in (
        "login",
        "register",
        "verify-registration",
        "resend-verification",
        "forgot-password",
        "reset-password",
    )
}


def register_auth_middleware(app):
    allowed = {
        settings.env.public_base_url.rstrip("/"),
        *(
            v.strip().rstrip("/")
            for v in settings.env.app_cors_origins.split(",")
            if v.strip()
        ),
    }

    @app.middleware("http")
    async def browser_security(request, call_next):
        if request.url.path.startswith("/api/") and request.method not in {
            "GET",
            "HEAD",
            "OPTIONS",
        }:
            origin = request.headers.get("Origin")
            invalid_origin = origin is not None and origin not in allowed
            invalid_form = (
                request.url.path in PUBLIC_AUTH_WRITES
                and request.headers.get("X-Requested-With") != "XMLHttpRequest"
            )
            if invalid_origin or invalid_form:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "status": 403,
                            "message": "安全校验失败，请从本站页面操作。",
                        }
                    },
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if settings.env.app_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response
