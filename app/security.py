"""Production configuration and request protection shared by all routes."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.responses import PlainTextResponse

MAX_REQUEST_BYTES = 12 * 1024 * 1024
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class SecuritySettings:
    production: bool
    secret_key: str
    secure_cookie: bool
    allowed_host: str | None


def security_settings() -> SecuritySettings:
    environment = os.environ.get("APP_ENV", "development").strip().lower()
    if environment not in {"development", "test", "production"}:
        raise RuntimeError("APP_ENV skal være development, test eller production")
    production = environment == "production"
    key = os.environ.get("SECRET_KEY", "")
    secure = os.environ.get("SESSION_COOKIE_SECURE", "").lower() in {"1", "true", "yes"}
    host = None
    if production:
        if (
            len(key) < 32
            or len(set(key)) < 16
            or any(
                marker in key.lower()
                for marker in (
                    "dev-secret",
                    "skift-denne",
                    "indsæt",
                    "change-me",
                    "changeme",
                )
            )
        ):
            raise RuntimeError(
                "Produktion kræver en tilfældig SECRET_KEY på mindst 32 tegn"
            )
        if not secure:
            raise RuntimeError("Produktion kræver SESSION_COOKIE_SECURE=true")
        public_url = urlsplit(os.environ.get("PUBLIC_BASE_URL", ""))
        if (
            public_url.scheme != "https"
            or not public_url.hostname
            or public_url.username
            or public_url.password
            or public_url.path not in {"", "/"}
            or public_url.query
            or public_url.fragment
        ):
            raise RuntimeError(
                "Produktion kræver PUBLIC_BASE_URL med et HTTPS-domæne uden sti"
            )
        host = public_url.hostname
    return SecuritySettings(production, key or "dev-secret", secure, host)


def password_error(password: str) -> str | None:
    if security_settings().production and len(password) < 16:
        return "Adgangskoden skal være mindst 16 tegn i produktion"
    return None


class RateLimiter:
    """Atomic counters shared by workers using the same local SQLite file.

    Keys are HMACs: neither resident tokens nor usernames/IPs are stored verbatim.
    This operational database is independent of application transactions.
    """

    def __init__(self, path: Path, secret_key: str):
        self.path = path
        self.key = secret_key.encode()

    def check(
        self, limits: list[tuple[str, int, int]], now: float | None = None
    ) -> int:
        now = int(time.time() if now is None else now)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS limits (key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires INTEGER NOT NULL)"
            )
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM limits WHERE expires <= ?", (now,))
            entries = []
            retry_after = 0
            for identity, maximum, period in limits:
                key = hmac.new(self.key, identity.encode(), hashlib.sha256).hexdigest()
                row = db.execute(
                    "SELECT count, expires FROM limits WHERE key = ?", (key,)
                ).fetchone()
                count, expires = row if row else (0, now + period)
                if count >= maximum:
                    retry_after = max(retry_after, expires - now)
                entries.append((key, count + 1, expires))
            if not retry_after:
                db.executemany(
                    "INSERT OR REPLACE INTO limits VALUES (?, ?, ?)", entries
                )
            return retry_after


class SecurityMiddleware:
    """Bound request bodies before parsing and enforce session-bound CSRF tokens."""

    def __init__(self, app, limiter: RateLimiter, production: bool = False):
        self.app = app
        self.limiter = limiter
        self.production = production

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        session = scope["session"]  # SessionMiddleware must wrap this middleware.
        token = session.setdefault("csrf_token", secrets.token_urlsafe(32))

        async def protected_send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
                headers["X-Frame-Options"] = "DENY"
                if not scope["path"].startswith("/static/"):
                    headers["Cache-Control"] = "no-store"
                if self.production:
                    headers["Strict-Transport-Security"] = "max-age=31536000"
            await send(message)

        async def reject(status, message, headers=None):
            await PlainTextResponse(message, status_code=status, headers=headers)(
                scope, receive, protected_send
            )

        if scope["method"] in SAFE_METHODS:
            return await self.app(scope, receive, protected_send)
        headers = Headers(scope=scope)
        try:
            content_length = int(headers.get("content-length", "0"))
        except ValueError:
            return await reject(400, "Ugyldig requestlængde")
        if content_length < 0:
            return await reject(400, "Ugyldig requestlængde")
        if content_length > MAX_REQUEST_BYTES:
            return await reject(413, "Forespørgslen må højst fylde 12 MiB")
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > MAX_REQUEST_BYTES:
                return await reject(413, "Forespørgslen må højst fylde 12 MiB")
            if not message.get("more_body", False):
                break
        body = bytes(body)

        def replay():
            sent = False

            async def read():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            return read

        request = Request(scope, receive=replay())
        supplied = headers.get("x-csrf-token", "")
        username = ""
        if headers.get("content-type", "").split(";", 1)[0].strip() in {
            "application/x-www-form-urlencoded",
            "multipart/form-data",
        }:
            try:
                async with request.form(
                    max_files=4, max_fields=200, max_part_size=MAX_REQUEST_BYTES
                ) as form:
                    supplied = supplied or form.get("csrf_token", "")
                    value = form.get("username", "")
                    username = value.strip() if isinstance(value, str) else ""
            except Exception:
                return await reject(400, "Formularen kunne ikke læses")
        if not isinstance(supplied, str) or not secrets.compare_digest(
            supplied.encode(), token.encode()
        ):
            return await reject(
                403,
                "Formularen er udløbet eller ugyldig. Genindlæs siden og prøv igen.",
            )
        # ASGI client is populated by the server; do not trust raw forwarded headers here.
        client = scope.get("client")
        ip = client[0] if client else "unknown"
        limits = []
        if scope["path"] == "/login":
            limits = [(f"login-ip:{ip}", 30, 900), (f"login-user:{username}", 10, 900)]
        elif scope["path"].startswith("/r/"):
            limits = [
                (f"resident-ip:{ip}", 120, 3600),
                (f"resident-token:{scope['path']}", 60, 3600),
            ]
        if limits:
            try:
                retry = await run_in_threadpool(self.limiter.check, limits)
            except (sqlite3.Error, OSError):
                return await reject(503, "Prøv igen senere", {"Retry-After": "60"})
            if retry:
                return await reject(
                    429,
                    "For mange forsøg. Prøv igen senere.",
                    {"Retry-After": str(retry)},
                )
        await self.app(scope, replay(), protected_send)
