"""Atomic Account Service withdrawal boundary; never mounted on Pilot routes."""

from __future__ import annotations

import hmac

import psycopg
from psycopg.rows import dict_row

from .postgres_service_store import PostgresServiceStore
from .service_crypto import ServiceCryptoError
from .service_errors import ServiceStoreError
from .service_identity_store import ServiceIdentityStore


class ServiceAccountWithdrawal:
    """Revoke identity and fence every owned meeting in one DB transaction.

    Actual key destruction and row purge are handled by the deletion worker.
    If any live meeting's owner cannot be decrypted, withdrawal fails closed
    without disabling the account or partially fencing meetings.
    """

    def __init__(
        self, identity: ServiceIdentityStore, content: PostgresServiceStore,
    ) -> None:
        if identity.dsn != content.dsn:
            raise ServiceStoreError("database_mismatch", "Identity and content DB must match")
        self.identity = identity
        self.content = content

    def withdraw(
        self, *, token: str | None, origin: str | None,
        csrf_token: str | None,
    ) -> int:
        user_id = self.identity.authenticate_mutation(
            token=token, origin=origin, csrf_token=csrf_token,
        )
        with psycopg.connect(self.identity.dsn, row_factory=dict_row) as connection:
            user = connection.execute(
                "SELECT user_id FROM service_user WHERE user_id = %s FOR UPDATE",
                (user_id,),
            ).fetchone()
            if user is None:
                raise ServiceStoreError("auth_required", "Authentication required")
            # No plaintext owner index exists; inspect encrypted owner values.
            # Lock all rows so intake/credential changes cannot interleave.
            sessions = connection.execute(
                "SELECT * FROM service_session ORDER BY session_id FOR UPDATE"
            ).fetchall()
            fenced = 0
            for session in sessions:
                if session["service_state"] == "deleting":
                    continue
                session_id = str(session["session_id"])
                try:
                    owner = self.content.codec.decrypt_json(
                        session_id, "owner", session_id, session["owner_cipher"],
                    )
                except ServiceCryptoError as exc:
                    raise ServiceStoreError(
                        "owner_lookup_unavailable", "Account withdrawal cannot be verified",
                    ) from exc
                if not isinstance(owner, str) or not owner.isascii() or not owner:
                    raise ServiceStoreError(
                        "owner_lookup_unavailable", "Account withdrawal cannot be verified",
                    )
                if hmac.compare_digest(owner, user_id):
                    self.content._begin_deletion_locked(
                        connection, session_id, session, reason="account_withdrawal",
                    )
                    fenced += 1
            connection.execute(
                """INSERT INTO service_withdrawal_receipt
                   (token_digest, csrf_digest, fenced_sessions, expires_at)
                   SELECT token_digest, csrf_digest, %s, now() + interval '1 day'
                   FROM service_web_session
                   WHERE user_id = %s AND expires_at > now() AND revoked_at IS NULL""",
                (fenced, user_id),
            )
            # ON DELETE CASCADE revokes all Web Sessions in the same commit.
            connection.execute("DELETE FROM service_user WHERE user_id = %s", (user_id,))
        return fenced
