"""Session-scoped authenticated encryption for service persistence.

Only the content database receives ciphertext. Key lifetime and the separate
Key Registry are specified by the service ADR; the in-memory registry below is
strictly for synthetic tests and must not back a live meeting.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import struct
import threading
from typing import Any, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class ServiceCryptoError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class SessionKeyRegistry(Protocol):
    def create_key(self, session_id: str) -> None: ...
    def get_key(self, session_id: str) -> bytes: ...
    def delete_key(self, session_id: str) -> None: ...


class InMemoryTestKeyRegistry:
    """Synthetic-test registry. It is not durable or suitable for production."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._keys: dict[str, bytes] = {}

    def create_key(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._keys:
                raise ServiceCryptoError("key_exists")
            self._keys[session_id] = AESGCM.generate_key(bit_length=256)

    def get_key(self, session_id: str) -> bytes:
        with self._lock:
            try:
                return self._keys[session_id]
            except KeyError as exc:
                raise ServiceCryptoError("key_unavailable") from exc

    def delete_key(self, session_id: str) -> None:
        with self._lock:
            self._keys.pop(session_id, None)


class SessionEnvelopeCodec:
    VERSION = 1
    NONCE_BYTES = 12

    def __init__(self, registry: SessionKeyRegistry) -> None:
        self.registry = registry

    @staticmethod
    def _aad(session_id: str, kind: str, record_id: str) -> bytes:
        if not session_id or not kind or not record_id:
            raise ServiceCryptoError("aad_invalid")
        return json.dumps(
            ["ronro-service-v1", session_id, kind, record_id],
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")

    def encrypt_json(self, session_id: str, kind: str, record_id: str, value: Any) -> bytes:
        plaintext = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        nonce = os.urandom(self.NONCE_BYTES)
        encrypted = AESGCM(self.registry.get_key(session_id)).encrypt(
            nonce, plaintext, self._aad(session_id, kind, record_id)
        )
        return bytes([self.VERSION]) + nonce + encrypted

    def decrypt_json(self, session_id: str, kind: str, record_id: str, blob: bytes) -> Any:
        value = bytes(blob)
        if len(value) <= 1 + self.NONCE_BYTES or value[0] != self.VERSION:
            raise ServiceCryptoError("ciphertext_invalid")
        nonce = value[1:1 + self.NONCE_BYTES]
        try:
            plaintext = AESGCM(self.registry.get_key(session_id)).decrypt(
                nonce, value[1 + self.NONCE_BYTES:], self._aad(session_id, kind, record_id)
            )
        except InvalidTag as exc:
            raise ServiceCryptoError("decrypt_failed") from exc
        try:
            return json.loads(plaintext)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ServiceCryptoError("plaintext_invalid") from exc

    def blind_provider_item_id(self, session_id: str, provider_item_id: str) -> bytes:
        if not provider_item_id:
            raise ServiceCryptoError("provider_item_invalid")
        return hmac.digest(
            self.registry.get_key(session_id),
            self._aad(session_id, "provider-item", provider_item_id),
            hashlib.sha256,
        )

    def blind_provider_transcript(self, session_id: str, transcript: str) -> bytes:
        """Bind a completed transcript without persisting its plaintext here."""
        return hmac.digest(
            self.registry.get_key(session_id),
            self._aad(session_id, "provider-transcript", "content")
            + transcript.strip().encode("utf-8"),
            hashlib.sha256,
        )

    def blind_capture_connection_id(self, session_id: str, connection_id: str) -> bytes:
        if not connection_id:
            raise ServiceCryptoError("capture_connection_invalid")
        return hmac.digest(
            self.registry.get_key(session_id),
            self._aad(session_id, "capture-connection", connection_id),
            hashlib.sha256,
        )

    def blind_capture_frame(
        self, session_id: str, generation: int, sequence: int,
        audio_start_seconds: float, pcm16le: bytes,
    ) -> bytes:
        return hmac.digest(
            self.registry.get_key(session_id),
            self._aad(session_id, "capture-frame", f"{generation}:{sequence}")
            + struct.pack(">d", audio_start_seconds) + pcm16le,
            hashlib.sha256,
        )
