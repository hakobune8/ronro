"""Loopback-only owner and live-display read routes for Account Service v1.

This is not a deployed Service entrypoint. In particular it cannot create a
meeting, accept audio, or delete content. The content adapter rejects the
ephemeral test registry unless explicitly opted in for synthetic tests.
"""

from __future__ import annotations

import json
import re
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit

from .display_labels import display_projection
from .postgres_service_store import PostgresServiceStore
from .semantic_canvas import project_semantic_canvas
from .service_auth_http import ServiceAuthRequestHandler, _cookie_value
from .service_browser_security import COOKIE_NAME
from .service_errors import ServiceStoreError
from .service_identity_store import ServiceIdentityStore
from .service_oidc import ServiceOidcClient


_SESSION_PATH = re.compile(r"/api/service/sessions/([A-Za-z0-9_-]{1,128})(/canvas)?\Z")
_ISSUE_VIEW_PATH = re.compile(r"/api/service/sessions/([A-Za-z0-9_-]{1,128})/view-credentials\Z")
_REVOKE_VIEW_PATH = re.compile(
    r"/api/service/sessions/([A-Za-z0-9_-]{1,128})/view-credentials/([0-9a-fA-F-]{36})\Z"
)
_BEARER = re.compile(r"Bearer ([A-Za-z0-9_-]{32,128})\Z", re.ASCII)


class ServiceMeetingRequestHandler(ServiceAuthRequestHandler):
    content: PostgresServiceStore

    def _mutating_owner(self) -> str:
        if self.headers.get("Authorization") is not None:
            raise ServiceStoreError("session_not_found", "Session not found")
        if self.headers.get("Transfer-Encoding") is not None or self.headers.get("Content-Length") not in (None, "0"):
            raise ServiceStoreError("request_invalid", "Unexpected request body")
        return self.identity.authenticate_mutation(
            token=_cookie_value(self.headers.get("Cookie"), COOKIE_NAME),
            origin=self.headers.get("Origin"),
            csrf_token=self.headers.get("X-Ronro-CSRF"),
        )

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        matched = _ISSUE_VIEW_PATH.fullmatch(parsed.path) if not parsed.query else None
        if matched is None:
            super().do_POST()
            return
        try:
            owner = self._mutating_owner()
            grant_id, token = self.content.issue_view_credential(matched.group(1), owner)
            payload = {"grant_id": grant_id, "token": token, "expires_in": 300}
            self._send(201, json.dumps(payload, separators=(",", ":")).encode("ascii"))
        except ServiceStoreError as exc:
            self._error(exc)
        except Exception:
            self._send(503, b'{"error":{"code":"service_unavailable"}}')

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        matched = _REVOKE_VIEW_PATH.fullmatch(parsed.path) if not parsed.query else None
        if matched is None:
            self._send(404, b'{"error":{"code":"not_found"}}')
            return
        try:
            owner = self._mutating_owner()
            self.content.revoke_view_credential(matched.group(1), owner, matched.group(2))
            self._send(204)
        except ServiceStoreError as exc:
            self._error(exc)
        except Exception:
            self._send(503, b'{"error":{"code":"service_unavailable"}}')

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        matched = _SESSION_PATH.fullmatch(parsed.path) if not parsed.query else None
        if matched is None:
            super().do_GET()
            return
        session_id, canvas_path = matched.groups()
        try:
            authorization = self.headers.get("Authorization")
            cookie = _cookie_value(self.headers.get("Cookie"), COOKIE_NAME)
            if authorization is not None:
                # A display bearer cannot silently fall back to owner authority.
                if cookie is not None or not canvas_path:
                    raise ServiceStoreError("session_not_found", "Session not found")
                bearer = _BEARER.fullmatch(authorization)
                if bearer is None:
                    raise ServiceStoreError("session_not_found", "Session not found")
                replay = self.content.load_live_canvas_source(session_id, bearer.group(1))
                state = None
            else:
                owner = self.identity.authenticate(cookie)
                replay, state = self.content.load_owner_canvas_source(session_id, owner)
            if canvas_path:
                graph = replay.state["graph"]
                display = display_projection(graph, replay.presentation)
                labels = {node_id: value["text"] for node_id, value in display.items()}
                payload = project_semantic_canvas(graph, replay.events, labels)
            else:
                payload = {"session_id": session_id, **state}
            self._send(200, json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        except ServiceStoreError as exc:
            self._error(exc)
        except Exception:
            self._send(503, b'{"error":{"code":"service_unavailable"}}')


def create_service_meeting_server(
    identity: ServiceIdentityStore, oidc: ServiceOidcClient,
    content: PostgresServiceStore, *, host: str = "127.0.0.1", port: int = 0,
) -> ThreadingHTTPServer:
    """Compose auth and read-only routes; loopback is an enforced boundary."""

    if host not in {"127.0.0.1", "::1"}:
        raise ValueError("Service meeting candidate may bind only to loopback")
    handler = type(
        "BoundServiceMeetingRequestHandler", (ServiceMeetingRequestHandler,),
        {"identity": identity, "oidc": oidc, "content": content},
    )
    return ThreadingHTTPServer((host, port), handler)
