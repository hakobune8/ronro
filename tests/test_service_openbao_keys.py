"""Synthetic HTTP contract for the RONRO-side OpenBao key adapter."""

from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from prototype.service_crypto import ServiceCryptoError
from prototype.service_openbao_keys import OpenBaoKvSessionKeyRegistry


class FakeResponse:
    def __init__(self, status: int, value: dict | None = None) -> None:
        self.status_code = status
        self.body = json.dumps(value or {}).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def iter_content(self, chunk_size=4096):
        yield self.body


class FakeHttp:
    trust_env = True

    def __init__(self) -> None:
        self.calls = []
        self.write_status = 200
        self.read_status = 200
        self.metadata = {"destroyed": False, "deletion_time": ""}
        self.key_b64 = None

    def request(self, method, url, **options):
        self.calls.append((method, url, options))
        if method == "POST":
            self.key_b64 = options["json"]["data"]["key_b64"]
            return FakeResponse(self.write_status)
        return FakeResponse(self.read_status, {
            "data": {"data": {"key_b64": self.key_b64},
                     "metadata": self.metadata},
        })


class OpenBaoKeyRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ca = Path(self.temp.name) / "ca.pem"
        self.ca.write_text("synthetic CA fixture, never used for TLS")
        self.http = FakeHttp()
        self.registry = OpenBaoKvSessionKeyRegistry(
            "https://bao.example.test", str(self.ca),
            lambda: "synthetic-only-workload-token", http=self.http,
        )
        self.session_id = str(uuid.uuid4())

    def test_create_only_cas_read_and_no_delete_before_backup_proof(self):
        self.assertFalse(self.http.trust_env)
        self.registry.create_key(self.session_id)
        method, url, options = self.http.calls[-1]
        self.assertEqual(method, "POST")
        self.assertEqual(url, f"https://bao.example.test/v1/ronro-session-keys/data/sessions/{self.session_id}")
        self.assertEqual(options["json"]["options"], {"cas": 0})
        self.assertEqual(options["verify"], str(self.ca))
        self.assertIs(options["allow_redirects"], False)
        self.assertEqual(len(self.registry.get_key(self.session_id)), 32)
        self.assertNotIn("synthetic-only-workload-token", repr(self.registry))
        before = len(self.http.calls)
        with self.assertRaises(ServiceCryptoError) as caught:
            self.registry.delete_key(self.session_id)
        self.assertEqual(caught.exception.code, "key_deletion_unverified")
        self.assertEqual(len(self.http.calls), before)

    def test_invalid_id_and_non_dedicated_endpoint_fail_without_request(self):
        for session_id in ("../../certificates", "not-a-uuid", self.session_id.upper()):
            with self.subTest(session_id=session_id), self.assertRaises(ServiceCryptoError):
                self.registry.create_key(session_id)
        self.assertEqual(self.http.calls, [])
        for base in ("http://bao.example.test", "https://bao.example.test/kv",
                     "https://user:pass@bao.example.test"):
            with self.subTest(base=base), self.assertRaises(ValueError):
                OpenBaoKvSessionKeyRegistry(base, str(self.ca), lambda: "token")

    def test_ambiguous_write_and_unavailable_or_malformed_read_fail_closed(self):
        self.http.write_status = 400
        with self.assertRaises(ServiceCryptoError) as caught:
            self.registry.create_key(self.session_id)
        self.assertEqual(caught.exception.code, "key_creation_unverified")
        self.http.read_status = 404
        with self.assertRaises(ServiceCryptoError) as caught:
            self.registry.get_key(self.session_id)
        self.assertEqual(caught.exception.code, "key_unavailable")
        self.http.read_status = 200
        self.http.metadata = {"destroyed": True, "deletion_time": ""}
        with self.assertRaises(ServiceCryptoError) as caught:
            self.registry.get_key(self.session_id)
        self.assertEqual(caught.exception.code, "key_response_invalid")
        self.http.metadata = {"destroyed": False, "deletion_time": ""}
        self.http.key_b64 = "invalid!"
        with self.assertRaises(ServiceCryptoError) as caught:
            self.registry.get_key(self.session_id)
        self.assertEqual(caught.exception.code, "key_response_invalid")

    def test_invalid_workload_token_fails_without_http(self):
        registry = OpenBaoKvSessionKeyRegistry(
            "https://bao.example.test", str(self.ca), lambda: "bad\ntoken", http=self.http,
        )
        with self.assertRaises(ServiceCryptoError) as caught:
            registry.get_key(self.session_id)
        self.assertEqual(caught.exception.code, "key_registry_token_unavailable")
        self.assertEqual(self.http.calls, [])
