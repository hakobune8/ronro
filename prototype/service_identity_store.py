"""PostgreSQL identity/session boundary for the opt-in Account Service.

This adapter is not mounted on Pilot HTTP routes. Its 32-byte identity key
must be durable, supplied by the deployment secret system, and kept separate
from meeting DEKs and database backups. No real users may be accepted until
the key's recovery, rotation, and deletion runbooks have been validated.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import uuid
from dataclasses import asdict
from typing import Any

import psycopg
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from psycopg.rows import dict_row

from .service_browser_security import ServiceBrowserSecurity
from .service_errors import ServiceStoreError
from .service_oidc import AuthorizationAttempt, VerifiedOidcIdentity


_OPAQUE = re.compile(r"[A-Za-z0-9_-]{32,128}\Z", re.ASCII)
_CIPHER_VERSION = 1


class ServiceIdentityStore:
    """Atomic one-use OIDC attempts and revocable, user-bound Web Sessions."""

    def __init__(
        self, dsn: str, identity_key: bytes, browser_security: ServiceBrowserSecurity,
        *, expected_issuer: str,
    ) -> None:
        if (not dsn or not isinstance(identity_key, bytes) or len(identity_key) != 32
                or not isinstance(expected_issuer, str) or not expected_issuer.startswith("https://")):
            raise ServiceStoreError("identity_store_unconfigured", "Identity store needs DB and key")
        derived = HKDF(
            algorithm=hashes.SHA256(), length=64, salt=None,
            info=b"ronro-service-v1-identity",
        ).derive(identity_key)
        self.dsn = dsn
        self._mac_key = derived[:32]
        self._cipher = AESGCM(derived[32:])
        self.browser_security = browser_security
        self.expected_issuer = expected_issuer

    def _digest(self, kind: str, value: bytes) -> bytes:
        return hmac.digest(self._mac_key, kind.encode("ascii") + b"\0" + value, "sha256")

    @staticmethod
    def _valid_opaque(value: Any) -> bool:
        return isinstance(value, str) and _OPAQUE.fullmatch(value) is not None

    def _encrypt_attempt(self, digest: bytes, attempt: AuthorizationAttempt) -> bytes:
        plaintext = json.dumps(asdict(attempt), separators=(",", ":")).encode("utf-8")
        nonce = os.urandom(12)
        aad = b"ronro-service-v1-auth-attempt\0" + digest
        return bytes([_CIPHER_VERSION]) + nonce + self._cipher.encrypt(nonce, plaintext, aad)

    def _decrypt_attempt(self, digest: bytes, blob: bytes) -> AuthorizationAttempt:
        value = bytes(blob)
        if len(value) < 30 or value[0] != _CIPHER_VERSION:
            raise ServiceStoreError("oidc_attempt_corrupt", "OIDC attempt is unavailable")
        nonce = value[1:13]
        try:
            plaintext = self._cipher.decrypt(
                nonce, value[13:], b"ronro-service-v1-auth-attempt\0" + digest,
            )
            values = json.loads(plaintext)
            attempt = AuthorizationAttempt(**values)
        except (InvalidTag, ValueError, TypeError, KeyError) as exc:
            raise ServiceStoreError("oidc_attempt_corrupt", "OIDC attempt is unavailable") from exc
        if not all(self._valid_opaque(v) for v in asdict(attempt).values()):
            raise ServiceStoreError("oidc_attempt_corrupt", "OIDC attempt is unavailable")
        return attempt

    def save_attempt(self, attempt: AuthorizationAttempt, *, ttl_seconds: int = 600) -> None:
        if (not isinstance(attempt, AuthorizationAttempt)
                or not all(self._valid_opaque(v) for v in asdict(attempt).values())
                or type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 600):
            raise ServiceStoreError("oidc_attempt_invalid", "OIDC attempt is invalid")
        digest = self._digest("oidc-state", attempt.state.encode("ascii"))
        cipher = self._encrypt_attempt(digest, attempt)
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                """INSERT INTO service_auth_attempt
                   (state_digest, secret_cipher, expires_at)
                   VALUES (%s, %s, now() + (%s * interval '1 second'))""",
                (digest, cipher, ttl_seconds),
            )

    def consume_attempt(self, received_state: str | None) -> AuthorizationAttempt:
        """Delete before token exchange; retries and concurrent callbacks fail."""

        if not self._valid_opaque(received_state):
            raise ServiceStoreError("oidc_state_invalid", "OIDC callback state is invalid")
        digest = self._digest("oidc-state", received_state.encode("ascii"))
        with psycopg.connect(self.dsn, row_factory=dict_row) as connection:
            row = connection.execute(
                """DELETE FROM service_auth_attempt
                   WHERE state_digest = %s AND expires_at > now()
                   RETURNING secret_cipher""",
                (digest,),
            ).fetchone()
            if row is None:
                raise ServiceStoreError("oidc_state_invalid", "OIDC callback state is invalid")
            attempt = self._decrypt_attempt(digest, row["secret_cipher"])
            if not hmac.compare_digest(attempt.state, received_state):
                raise ServiceStoreError("oidc_state_invalid", "OIDC callback state is invalid")
            return attempt

    def get_or_create_user(self, identity: VerifiedOidcIdentity) -> str:
        """Bind only a verified issuer/subject; never use email as identity."""

        if not isinstance(identity, VerifiedOidcIdentity):
            raise ServiceStoreError("identity_unverified", "Verified OIDC identity required")
        if (identity.issuer != self.expected_issuer
                or not 1 <= len(identity.subject) <= 1024):
            raise ServiceStoreError("identity_unverified", "Verified OIDC identity required")
        serialized = json.dumps([identity.issuer, identity.subject], separators=(",", ":"))
        digest = self._digest("oidc-subject", serialized.encode("utf-8"))
        proposed_id = str(uuid.uuid4())
        with psycopg.connect(self.dsn, row_factory=dict_row) as connection:
            row = connection.execute(
                """INSERT INTO service_user (user_id, subject_digest)
                   VALUES (%s, %s)
                   ON CONFLICT (subject_digest) DO UPDATE
                   SET subject_digest = EXCLUDED.subject_digest
                   RETURNING user_id, disabled_at""",
                (proposed_id, digest),
            ).fetchone()
            if row["disabled_at"] is not None:
                raise ServiceStoreError("account_disabled", "Account is unavailable")
            return row["user_id"]

    def issue_web_session(
        self, user_id: str, *, ttl_seconds: int = 12 * 3600,
    ) -> tuple[str, str]:
        """Return opaque cookie and CSRF material once; DB stores digests."""

        if (not isinstance(user_id, str) or not user_id
                or type(ttl_seconds) is not int or not 60 <= ttl_seconds <= 86400):
            raise ServiceStoreError("web_session_invalid", "Web Session request is invalid")
        token = secrets.token_urlsafe(32)
        csrf_token, csrf_digest = self.browser_security.new_csrf_secret()
        digest = self._digest("web-session", token.encode("ascii"))
        with psycopg.connect(self.dsn, row_factory=dict_row) as connection:
            row = connection.execute(
                "SELECT disabled_at FROM service_user WHERE user_id = %s FOR UPDATE",
                (user_id,),
            ).fetchone()
            if row is None or row["disabled_at"] is not None:
                raise ServiceStoreError("account_unavailable", "Account is unavailable")
            connection.execute(
                """INSERT INTO service_web_session
                   (token_digest, user_id, csrf_digest, expires_at)
                   VALUES (%s, %s, %s, now() + (%s * interval '1 second'))""",
                (digest, user_id, csrf_digest, ttl_seconds),
            )
        return token, csrf_token

    def _lookup_session(self, token: str | None) -> tuple[str, bytes]:
        if not self._valid_opaque(token):
            raise ServiceStoreError("auth_required", "Authentication required")
        digest = self._digest("web-session", token.encode("ascii"))
        with psycopg.connect(self.dsn, row_factory=dict_row) as connection:
            row = connection.execute(
                """SELECT w.user_id, w.csrf_digest FROM service_web_session AS w
                   JOIN service_user AS u ON u.user_id = w.user_id
                   WHERE w.token_digest = %s AND w.expires_at > now()
                     AND w.revoked_at IS NULL AND u.disabled_at IS NULL""",
                (digest,),
            ).fetchone()
        if row is None:
            raise ServiceStoreError("auth_required", "Authentication required")
        return row["user_id"], bytes(row["csrf_digest"])

    def authenticate(self, token: str | None) -> str:
        return self._lookup_session(token)[0]

    def authenticate_mutation(
        self, *, token: str | None, origin: str | None,
        csrf_token: str | None,
    ) -> str:
        self.browser_security.require_same_origin(origin)
        user_id, csrf_digest = self._lookup_session(token)
        self.browser_security.require_csrf(csrf_token, csrf_digest)
        return user_id

    def authenticate_websocket(self, *, token: str | None, origin: str | None) -> str:
        self.browser_security.require_same_origin(origin)
        return self.authenticate(token)

    def revoke_web_session(self, token: str | None) -> None:
        if not self._valid_opaque(token):
            raise ServiceStoreError("auth_required", "Authentication required")
        digest = self._digest("web-session", token.encode("ascii"))
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                """UPDATE service_web_session SET revoked_at = now()
                   WHERE token_digest = %s AND revoked_at IS NULL""",
                (digest,),
            )

    def revoke_user_sessions(self, user_id: str) -> None:
        """Internal revocation primitive for later account-withdrawal workflow."""

        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                """UPDATE service_web_session SET revoked_at = now()
                   WHERE user_id = %s AND revoked_at IS NULL""",
                (user_id,),
            )

    def purge_expired_auth_records(self) -> tuple[int, int]:
        """Remove expired login attempts and Web Sessions, not meeting data."""

        with psycopg.connect(self.dsn) as connection:
            attempts = connection.execute(
                "DELETE FROM service_auth_attempt WHERE expires_at <= now()"
            ).rowcount
            sessions = connection.execute(
                "DELETE FROM service_web_session WHERE expires_at <= now()"
            ).rowcount
        return attempts, sessions
