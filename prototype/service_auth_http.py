"""Opt-in local Account Service authentication HTTP boundary.

This server is deliberately separate from ``prototype.server`` and is not
started by the production/Pilot entrypoint. A durable identity key, dedicated
ZITADEL client, trusted HTTPS ingress, and route-level authorization still
need deployment integration before this may serve real users.
"""

from __future__ import annotations

import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .service_browser_security import COOKIE_NAME, LOGIN_COOKIE_NAME
from .service_errors import ServiceStoreError
from .service_identity_store import ServiceIdentityStore
from .service_oidc import ServiceOidcClient


def _cookie_value(header: str | None, name: str) -> str | None:
    if not header:
        return None
    values = []
    for part in header.split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key == name:
            values.append(value)
    return values[0] if len(values) == 1 else None


class ServiceAuthRequestHandler(BaseHTTPRequestHandler):
    identity: ServiceIdentityStore
    oidc: ServiceOidcClient

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        # Callback URLs contain OIDC codes. Do not emit an access log here.
        return

    def _send(
        self, status: int, body: bytes = b"", *, content_type: str = "application/json; charset=utf-8",
        location: str | None = None, cookies: tuple[str, ...] = (),
        attachment_filename: str | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        if location is not None:
            self.send_header("Location", location)
        if attachment_filename is not None:
            self.send_header("Content-Disposition", f'attachment; filename="{attachment_filename}"')
        for cookie in cookies:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _error(self, exc: ServiceStoreError) -> None:
        status = {
            "auth_required": 401,
            "origin_rejected": 403,
            "csrf_rejected": 403,
            "account_disabled": 403,
            "account_unavailable": 403,
            "owner_lookup_unavailable": 503,
            "session_not_found": 404,
            "session_deleted": 410,
            "session_closed": 409,
            "session_not_ended": 409,
            "capacity_unavailable": 429,
            "version_mismatch": 409,
            "capture_transition_invalid": 409,
            "operation_key_conflict": 409,
            "replay_mismatch": 503,
            "oidc_exchange_failed": 502,
            "oidc_jwks_unavailable": 502,
        }.get(exc.code, 400)
        self._send(status, json.dumps({"error": {"code": exc.code}}).encode("ascii"))

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlsplit(self.path)
            if parsed.path == "/api/service/auth/login" and not parsed.query:
                existing = _cookie_value(self.headers.get("Cookie"), LOGIN_COOKIE_NAME)
                binding = existing if self.identity._valid_opaque(existing) else secrets.token_urlsafe(32)
                url, attempt = self.oidc.begin_authorization()
                self.identity.save_attempt(attempt, browser_binding_token=binding)
                self._send(
                    303, location=url,
                    cookies=(self.identity.browser_security.login_cookie(binding),),
                )
                return
            if parsed.path == "/api/service/auth/callback":
                values = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=4)
                if (set(values) not in ({"code", "state"}, {"code", "state", "iss"})
                        or len(values["code"]) != 1 or len(values["state"]) != 1):
                    raise ServiceStoreError("oidc_callback_invalid", "OIDC callback is invalid")
                if ("iss" in values and
                        (len(values["iss"]) != 1 or values["iss"][0] != self.oidc.config.issuer)):
                    raise ServiceStoreError("oidc_callback_invalid", "OIDC callback is invalid")
                state = values["state"][0]
                code = values["code"][0]
                binding = _cookie_value(self.headers.get("Cookie"), LOGIN_COOKIE_NAME)
                attempt = self.identity.consume_attempt(state, browser_binding_token=binding)
                verified = self.oidc.complete_authorization(
                    code=code, received_state=state, attempt=attempt,
                )
                user_id = self.identity.get_or_create_user(verified)
                token, _ = self.identity.issue_web_session(user_id)
                self._send(
                    303, location="/api/service/auth/session",
                    cookies=(self.identity.browser_security.session_cookie(
                        token, max_age_seconds=12 * 3600,
                    ),),
                )
                return
            if parsed.path == "/api/service/auth/session" and not parsed.query:
                token = _cookie_value(self.headers.get("Cookie"), COOKIE_NAME)
                user_id = self.identity.authenticate(token)
                csrf = self.identity.csrf_token_for_web_session(token)
                self._send(200, json.dumps({
                    "authenticated": True, "user_id": user_id, "csrf_token": csrf,
                }).encode("ascii"))
                return
            self._send(404, b'{"error":{"code":"not_found"}}')
        except ServiceStoreError as exc:
            self._error(exc)
        except ValueError:
            self._send(400, b'{"error":{"code":"request_invalid"}}')
        except Exception:
            self._send(503, b'{"error":{"code":"service_unavailable"}}')

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/service/auth/logout":
            self._send(404, b'{"error":{"code":"not_found"}}')
            return
        try:
            token = _cookie_value(self.headers.get("Cookie"), COOKIE_NAME)
            self.identity.authenticate_mutation(
                token=token, origin=self.headers.get("Origin"),
                csrf_token=self.headers.get("X-Ronro-CSRF"),
            )
            self.identity.revoke_web_session(token)
            self._send(204, cookies=(
                f"{COOKIE_NAME}=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax",
                f"{LOGIN_COOKIE_NAME}=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax",
            ))
        except ServiceStoreError as exc:
            self._error(exc)
        except Exception:
            self._send(503, b'{"error":{"code":"service_unavailable"}}')


def create_service_auth_server(
    identity: ServiceIdentityStore, oidc: ServiceOidcClient,
    host: str = "127.0.0.1", port: int = 0,
) -> ThreadingHTTPServer:
    """Candidate test entrypoint; never mounted on the Pilot server."""

    if host not in {"127.0.0.1", "::1"}:
        raise ValueError("Service authentication candidate may bind only to loopback")
    handler = type(
        "BoundServiceAuthRequestHandler", (ServiceAuthRequestHandler,),
        {"identity": identity, "oidc": oidc},
    )
    return ThreadingHTTPServer((host, port), handler)
