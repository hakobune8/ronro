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
_BEARER = re.compile(r"Bearer ([A-Za-z0-9_-]{32,128})\Z", re.ASCII)


class ServiceMeetingRequestHandler(ServiceAuthRequestHandler):
    content: PostgresServiceStore

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
