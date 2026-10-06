"""Dedicated-client OIDC code/PKCE and ID-token verification boundary.

The caller must persist each AuthorizationAttempt server-side, consume it once
before exchanging the code, and issue a Web Session only after verify_id_token
succeeds. This module neither authenticates a route nor stores an account.
"""

from __future__ import annotations

import hmac
import json
import secrets
from dataclasses import dataclass
from urllib.parse import urlsplit

import requests
from authlib.integrations.requests_client import OAuth2Session
from authlib.oidc.core import CodeIDToken
from joserfc import jwt
from joserfc.jwk import KeySet

from .service_errors import ServiceStoreError


def _https_origin(value: str) -> str:
    try:
        parts = urlsplit(value)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise ValueError("HTTPS URL required")
        port = parts.port
    except (TypeError, ValueError) as exc:
        raise ValueError("HTTPS URL required") from exc
    hostname = parts.hostname
    if ":" in hostname:
        hostname = f"[{hostname}]"
    return f"https://{hostname}" + (f":{port}" if port is not None else "")


@dataclass(frozen=True)
class OidcConfiguration:
    issuer: str
    client_id: str
    public_origin: str
    redirect_uri: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str

    def __post_init__(self) -> None:
        if (not self.client_id or not self.client_id.isascii()
                or not self.client_id.isprintable() or self.client_id.strip() != self.client_id
                or len(self.client_id) > 256):
            raise ValueError("OIDC client ID is invalid")
        origin = _https_origin(self.issuer)
        if self.issuer != origin:
            raise ValueError("OIDC issuer must be a canonical HTTPS origin")
        public_origin = _https_origin(self.public_origin)
        if self.public_origin != public_origin:
            raise ValueError("RONRO public origin must be canonical HTTPS")
        redirect = urlsplit(self.redirect_uri)
        if (_https_origin(self.redirect_uri) != public_origin
                or not redirect.path.startswith("/") or redirect.query or redirect.fragment
                or self.redirect_uri != public_origin + redirect.path):
            raise ValueError("OIDC redirect URI is invalid")
        for endpoint in (self.authorization_endpoint, self.token_endpoint, self.jwks_uri):
            parsed = urlsplit(endpoint)
            if (_https_origin(endpoint) != origin or not parsed.path.startswith("/")
                    or parsed.fragment or parsed.query):
                raise ValueError("OIDC endpoint is outside configured issuer origin")


@dataclass(frozen=True)
class AuthorizationAttempt:
    state: str
    nonce: str
    code_verifier: str


class ServiceOidcClient:
    def __init__(self, config: OidcConfiguration) -> None:
        self.config = config

    def _client(self) -> OAuth2Session:
        return OAuth2Session(
            self.config.client_id, scope="openid", redirect_uri=self.config.redirect_uri,
            token_endpoint_auth_method="none", code_challenge_method="S256",
        )

    def begin_authorization(self) -> tuple[str, AuthorizationAttempt]:
        """Return a redirect URL and server-side-only state/nonce/PKCE secrets."""

        attempt = AuthorizationAttempt(
            state=secrets.token_urlsafe(32), nonce=secrets.token_urlsafe(32),
            code_verifier=secrets.token_urlsafe(48),
        )
        client = self._client()
        url, returned_state = client.create_authorization_url(
            self.config.authorization_endpoint, state=attempt.state,
            nonce=attempt.nonce, code_verifier=attempt.code_verifier,
        )
        if returned_state != attempt.state:
            raise ServiceStoreError("oidc_state_invalid", "OIDC state generation failed")
        return url, attempt

    @staticmethod
    def require_callback_state(expected: AuthorizationAttempt, received: str | None) -> None:
        if (not isinstance(received, str) or not hmac.compare_digest(expected.state, received)):
            raise ServiceStoreError("oidc_state_invalid", "OIDC callback state is invalid")

    def exchange_code(self, *, code: str, attempt: AuthorizationAttempt) -> dict:
        """Call only after atomically consuming the persisted attempt."""

        if (not isinstance(code, str) or not 1 <= len(code) <= 4096
                or not code.isascii() or not code.isprintable()):
            raise ServiceStoreError("oidc_code_invalid", "OIDC authorization code is invalid")
        try:
            token = self._client().fetch_token(
                self.config.token_endpoint, code=code,
                code_verifier=attempt.code_verifier,
            )
        except Exception as exc:
            raise ServiceStoreError("oidc_exchange_failed", "OIDC code exchange failed") from exc
        if not isinstance(token, dict) or not isinstance(token.get("id_token"), str):
            raise ServiceStoreError("oidc_token_invalid", "OIDC ID token is missing")
        return token

    def complete_authorization(
        self, *, code: str, received_state: str | None,
        attempt: AuthorizationAttempt,
    ) -> tuple[str, str]:
        """Return verified identity; persisted state must be consumed once first.

        Browser-supplied signing keys are never accepted. The configured JWKS
        endpoint is fetched without following redirects.
        """

        self.require_callback_state(attempt, received_state)
        token = self.exchange_code(code=code, attempt=attempt)
        return self.verify_id_token(
            id_token=token["id_token"], jwks=self.fetch_jwks(), attempt=attempt,
            access_token=token.get("access_token"),
        )

    def fetch_jwks(self) -> dict:
        try:
            with requests.get(
                self.config.jwks_uri, timeout=5, stream=True, allow_redirects=False,
            ) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError("JWKS response must be 200 OK")
                size = 0
                chunks = []
                for chunk in response.iter_content(chunk_size=8192):
                    size += len(chunk)
                    if size > 65536:
                        raise ValueError("JWKS exceeds size limit")
                    chunks.append(chunk)
            jwks = json.loads(b"".join(chunks))
            if (not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list)
                    or not 1 <= len(jwks["keys"]) <= 32):
                raise ValueError("JWKS is malformed")
        except (requests.RequestException, ValueError) as exc:
            raise ServiceStoreError("oidc_jwks_unavailable", "OIDC signing keys unavailable") from exc
        return jwks

    def verify_id_token(
        self, *, id_token: str, jwks: dict, attempt: AuthorizationAttempt,
        access_token: str | None = None,
    ) -> tuple[str, str]:
        """Verify RS256 signature/claims; return only stable issuer + subject."""

        try:
            keys = KeySet.import_key_set(jwks)
            decoded = jwt.decode(id_token, keys, algorithms=["RS256"])
            claims = CodeIDToken(
                decoded.claims, decoded.header,
                {"iss": {"value": self.config.issuer},
                 "aud": {"value": self.config.client_id}},
                {"nonce": attempt.nonce, "client_id": self.config.client_id,
                 "access_token": access_token},
            )
            claims.validate(leeway=30)
            subject = claims.get("sub")
            if (claims.get("iss") != self.config.issuer
                    or not isinstance(subject, str) or not subject):
                raise ValueError("OIDC issuer/subject mismatch")
        except Exception as exc:
            raise ServiceStoreError("oidc_token_invalid", "OIDC ID token verification failed") from exc
        return self.config.issuer, subject
