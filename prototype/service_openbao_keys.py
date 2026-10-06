"""Fail-closed OpenBao KV v2 candidate for RONRO session keys.

This adapter only proves the RONRO-side connection contract. A dedicated
mount, workload authentication, HA, snapshot retention, and irreversible
deletion still need infrastructure acceptance before live service use.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .service_crypto import ServiceCryptoError


class OpenBaoKvSessionKeyRegistry:
    """Create-only session DEKs in a dedicated KV v2 mount, then read them.

    The caller supplies a short-lived workload token. This class never logs
    request/response bodies or retains a token or DEK on the instance.
    """

    MOUNT = "ronro-session-keys"
    MAX_RESPONSE_BYTES = 16384

    def __init__(
        self, base_url: str, ca_bundle: str, token_provider: Callable[[], str],
        *, http: requests.Session | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.path or parsed.query or parsed.fragment
                or base_url != f"https://{parsed.netloc}"):
            raise ValueError("Canonical HTTPS OpenBao origin required")
        if not Path(ca_bundle).is_absolute() or not Path(ca_bundle).is_file():
            raise ValueError("An existing absolute CA bundle is required")
        if not callable(token_provider):
            raise ValueError("Workload token provider is required")
        self.base_url = base_url
        self.ca_bundle = ca_bundle
        self._token_provider = token_provider
        self._http = http if http is not None else requests.Session()
        self._http.trust_env = False

    @staticmethod
    def _key_path(session_id: str) -> str:
        try:
            parsed = uuid.UUID(session_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ServiceCryptoError("session_id_invalid") from exc
        if str(parsed) != session_id:
            raise ServiceCryptoError("session_id_invalid")
        return f"/v1/{OpenBaoKvSessionKeyRegistry.MOUNT}/data/sessions/{session_id}"

    def _request(self, method: str, path: str, *, payload: dict | None = None):
        token = self._token_provider()
        if (not isinstance(token, str) or not token or len(token) > 8192
                or not token.isascii() or not token.isprintable()):
            raise ServiceCryptoError("key_registry_token_unavailable")
        try:
            return self._http.request(
                method, self.base_url + path,
                headers={"X-Vault-Token": token, "Content-Type": "application/json"},
                json=payload, verify=self.ca_bundle, timeout=(3, 5),
                allow_redirects=False, stream=True,
            )
        except requests.RequestException as exc:
            raise ServiceCryptoError("key_registry_unavailable") from exc

    def create_key(self, session_id: str) -> None:
        path = self._key_path(session_id)
        key = AESGCM.generate_key(bit_length=256)
        payload = {
            "options": {"cas": 0},
            "data": {"key_b64": base64.b64encode(key).decode("ascii")},
        }
        with self._request("POST", path, payload=payload) as response:
            if response.status_code != 200:
                # A transport error or ambiguous write must not trigger a
                # speculative delete. Reconcile any orphan after DB outcome.
                raise ServiceCryptoError("key_creation_unverified")

    def get_key(self, session_id: str) -> bytes:
        path = self._key_path(session_id)
        with self._request("GET", path) as response:
            if response.status_code == 404:
                raise ServiceCryptoError("key_unavailable")
            if response.status_code != 200:
                raise ServiceCryptoError("key_registry_unavailable")
            data = bytearray()
            for chunk in response.iter_content(chunk_size=4096):
                data.extend(chunk)
                if len(data) > self.MAX_RESPONSE_BYTES:
                    raise ServiceCryptoError("key_response_invalid")
        try:
            value = json.loads(data)
            section = value["data"]
            metadata = section["metadata"]
            if (not isinstance(metadata, dict) or metadata.get("destroyed") is not False
                    or metadata.get("deletion_time") not in ("", None)):
                raise ValueError("Key version is unavailable")
            encoded = section["data"]["key_b64"]
            if not isinstance(encoded, str):
                raise ValueError("Key is invalid")
            key = base64.b64decode(encoded, validate=True)
            if len(key) != 32:
                raise ValueError("Key length is invalid")
            return key
        except (KeyError, TypeError, ValueError, binascii.Error) as exc:
            raise ServiceCryptoError("key_response_invalid") from exc

    def delete_key(self, session_id: str) -> None:
        self._key_path(session_id)
        # KV v2 soft-delete is reversible and even metadata delete can be
        # undone from an older Raft snapshot. Never report deletion success
        # before snapshot/backup policy and lifecycle fencing are verified.
        raise ServiceCryptoError("key_deletion_unverified")
