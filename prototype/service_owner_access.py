"""Compose Web authentication with the content store's owner boundary.

Service HTTP/WSS routes must call this gate for each protected operation.
The current Pilot controller_id is not an input or substitute for a cookie.
"""

from __future__ import annotations

from .postgres_service_store import PostgresServiceStore
from .service_identity_store import ServiceIdentityStore


class ServiceOwnerAccess:
    def __init__(
        self, identity: ServiceIdentityStore, content: PostgresServiceStore,
    ) -> None:
        self.identity = identity
        self.content = content

    def read(self, *, session_id: str, cookie_token: str | None) -> str:
        user_id = self.identity.authenticate(cookie_token)
        self.content.authorize_owner_session(session_id, user_id)
        return user_id

    def mutate(
        self, *, session_id: str, cookie_token: str | None,
        origin: str | None, csrf_token: str | None,
    ) -> str:
        user_id = self.identity.authenticate_mutation(
            token=cookie_token, origin=origin, csrf_token=csrf_token,
        )
        self.content.authorize_owner_session(session_id, user_id)
        return user_id

    def audio_websocket(
        self, *, session_id: str, cookie_token: str | None,
        origin: str | None,
    ) -> str:
        user_id = self.identity.authenticate_websocket(token=cookie_token, origin=origin)
        self.content.authorize_owner_session(session_id, user_id)
        return user_id
