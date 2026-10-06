"""Browser request checks for the future authenticated Service routes.

This module does not authenticate a user or create an HTTP/WSS route. The
caller must obtain a verified OIDC-backed Web Session separately and store
the CSRF digest with that Session. No token belongs in a URL or log.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from urllib.parse import urlsplit

from .service_errors import ServiceStoreError


COOKIE_NAME = "__Host-ronro_session"
_OPAQUE_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,128}\Z", re.ASCII)


class ServiceBrowserSecurity:
    def __init__(self, public_origin: str) -> None:
        if not isinstance(public_origin, str):
            raise ValueError("A canonical HTTPS public origin is required")
        try:
            parsed = urlsplit(public_origin)
            normalized = self._normalized_origin(parsed)
        except ValueError as exc:
            raise ValueError("A canonical HTTPS public origin is required") from exc
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.path or parsed.query or parsed.fragment
                or public_origin != normalized):
            raise ValueError("A canonical HTTPS public origin is required")
        self.public_origin = public_origin

    @staticmethod
    def _normalized_origin(parsed) -> str:
        host = parsed.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port is not None else ""
        return f"{parsed.scheme}://{host}{port}"

    def require_same_origin(self, supplied_origin: str | None) -> None:
        """For cookie-authenticated mutations and WebSocket handshakes."""

        if not isinstance(supplied_origin, str) or supplied_origin != self.public_origin:
            raise ServiceStoreError("origin_rejected", "Request origin is not allowed")

    @staticmethod
    def new_csrf_secret() -> tuple[str, bytes]:
        token = secrets.token_urlsafe(32)
        return token, hashlib.sha256(token.encode("ascii")).digest()

    @staticmethod
    def require_csrf(supplied_token: str | None, stored_digest: bytes | None) -> None:
        if (not isinstance(supplied_token, str) or not 32 <= len(supplied_token) <= 128
                or not supplied_token.isascii() or not isinstance(stored_digest, bytes)
                or len(stored_digest) != hashlib.sha256().digest_size):
            raise ServiceStoreError("csrf_rejected", "CSRF verification failed")
        candidate = hashlib.sha256(supplied_token.encode("ascii")).digest()
        if not hmac.compare_digest(candidate, stored_digest):
            raise ServiceStoreError("csrf_rejected", "CSRF verification failed")

    def require_mutation(
        self, *, origin: str | None, csrf_token: str | None,
        session_csrf_digest: bytes | None,
    ) -> None:
        self.require_same_origin(origin)
        self.require_csrf(csrf_token, session_csrf_digest)

    @staticmethod
    def session_cookie(value: str, *, max_age_seconds: int) -> str:
        """Secure host-only browser cookie; value must be an opaque token."""

        if (not isinstance(value, str) or _OPAQUE_TOKEN.fullmatch(value) is None
                or type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 86400):
            raise ServiceStoreError("session_cookie_invalid", "Invalid Web Session cookie")
        return (f"{COOKIE_NAME}={value}; Path=/; Max-Age={max_age_seconds}; "
                "Secure; HttpOnly; SameSite=Lax")
