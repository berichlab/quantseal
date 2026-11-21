"""Built-in admin authentication using HMAC-SHA256 signed HttpOnly cookies."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any

from fastapi import Depends, HTTPException, Request, Response, status

from quantseal.config import Settings, get_settings

COOKIE_NAME = "quantseal_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days


def _sign_token(issued_at: int, secret_key: str) -> str:
    payload = f"admin:{issued_at}".encode()
    sig = hmac.new(secret_key.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"{issued_at}.{sig}"


def verify_session_token(token: str | None, secret_key: str) -> bool:
    if not token or "." not in token:
        return False
    parts = token.split(".", 1)
    try:
        issued_at = int(parts[0])
    except ValueError:
        return False
    if (time.time() - issued_at) > SESSION_TTL_SECONDS or issued_at > time.time() + 60:
        return False
    expected = _sign_token(issued_at, secret_key)
    return hmac.compare_digest(token, expected)


def verify_password(candidate: str, configured: str) -> bool:
    if not configured:
        return True
    return secrets.compare_digest(candidate.encode("utf-8"), configured.encode("utf-8"))


def is_authenticated(request: Request, settings: Settings) -> bool:
    if not settings.admin_password.strip():
        return True
    secret = settings.resolved_secret_key()
    cookie_token = request.cookies.get(COOKIE_NAME)
    if verify_session_token(cookie_token, secret):
        return True
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        bearer = auth_header[7:].strip()
        if verify_password(bearer, settings.admin_password) or verify_session_token(bearer, secret):
            return True
    return False


def set_session_cookie(response: Response, settings: Settings) -> None:
    token = _sign_token(int(time.time()), settings.resolved_secret_key())
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


def require_auth(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if not is_authenticated(request, settings):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return {"authenticated": True, "auth_enabled": bool(settings.admin_password.strip())}
