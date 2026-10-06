"""Loopback-only Account Service login routes with synthetic OIDC tokens."""

from __future__ import annotations

import http.client
import json
import os
import threading
import time
import unittest
import uuid
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit
from unittest.mock import patch

import psycopg
from joserfc import jwt
from joserfc.jwk import RSAKey

from prototype.postgres_service_store import PostgresServiceStore
from prototype.schema import SchemaValidator
from prototype.service_auth_http import create_service_auth_server
from prototype.service_browser_security import COOKIE_NAME, LOGIN_COOKIE_NAME, ServiceBrowserSecurity
from prototype.service_crypto import InMemoryTestKeyRegistry
from prototype.service_identity_store import ServiceIdentityStore
from prototype.service_oidc import OidcConfiguration, ServiceOidcClient


TEST_DSN = os.getenv("RONRO_TEST_POSTGRES_DSN")
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(TEST_DSN, "Synthetic PostgreSQL test DSN is not configured")
class ServiceAuthHttpTests(unittest.TestCase):
    def setUp(self):
        content = PostgresServiceStore(
            TEST_DSN, SchemaValidator(ROOT / "schemas"), InMemoryTestKeyRegistry(),
            allow_test_key_registry=True,
        )
        content.migrate()
        self.oidc = ServiceOidcClient(OidcConfiguration(
            issuer="https://idp.example.test", client_id="synthetic-ronro-client",
            public_origin="https://ronro.example.test",
            redirect_uri="https://ronro.example.test/api/service/auth/callback",
            authorization_endpoint="https://idp.example.test/oauth/v2/authorize",
            token_endpoint="https://idp.example.test/oauth/v2/token",
            jwks_uri="https://idp.example.test/oauth/v2/keys",
            token_endpoint_auth_method="none",
        ))
        self.identity = ServiceIdentityStore(
            TEST_DSN, bytes(range(32)), ServiceBrowserSecurity("https://ronro.example.test"),
            expected_issuer=self.oidc.config.issuer,
        )
        self.subject = f"synthetic-{uuid.uuid4()}"
        self.key = RSAKey.generate_key(auto_kid=True)
        self.states = []
        self.server = create_service_auth_server(self.identity, self.oidc)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        subject = json.dumps([self.oidc.config.issuer, self.subject], separators=(",", ":"))
        digest = self.identity._digest("oidc-subject", subject.encode())
        with psycopg.connect(TEST_DSN) as connection:
            connection.execute("DELETE FROM service_user WHERE subject_digest = %s", (digest,))
            for state in self.states:
                state_digest = self.identity._digest("oidc-state", state.encode())
                connection.execute(
                    "DELETE FROM service_auth_attempt WHERE state_digest = %s", (state_digest,),
                )

    def _request(self, method, path, *, cookie=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        sent = dict(headers or {})
        if cookie:
            sent["Cookie"] = cookie
        connection.request(method, path, headers=sent)
        response = connection.getresponse()
        body = response.read()
        result = response.status, dict(response.getheaders()), body
        connection.close()
        return result

    def _start(self, *, cookie=None):
        status, headers, body = self._request("GET", "/api/service/auth/login", cookie=cookie)
        self.assertEqual((status, body), (303, b""))
        state = parse_qs(urlsplit(headers["Location"]).query)["state"][0]
        self.states.append(state)
        binding = headers["Set-Cookie"].split(";", 1)[0]
        self.assertTrue(binding.startswith(f"{LOGIN_COOKIE_NAME}="))
        self.assertNotIn(binding.split("=", 1)[1], headers["Location"])
        return state, binding

    def _signed_token(self, nonce):
        now = int(time.time())
        return jwt.encode(
            {"alg": "RS256", "kid": self.key.kid},
            {"iss": self.oidc.config.issuer, "sub": self.subject,
             "aud": self.oidc.config.client_id, "exp": now + 600,
             "iat": now, "nonce": nonce},
            self.key,
        )

    def test_browser_bound_login_session_csrf_logout_and_replay(self):
        state, binding = self._start()
        callback = f"/api/service/auth/callback?code=synthetic-code&state={quote(state)}"
        wrong = f"{LOGIN_COOKIE_NAME}={'C' * 43}"
        status, _, body = self._request("GET", callback, cookie=wrong)
        self.assertEqual(status, 400)
        self.assertIn(b"oidc_state_invalid", body)

        def synthetic_exchange(*, code, attempt):
            self.assertEqual(code, "synthetic-code")
            return {"id_token": self._signed_token(attempt.nonce)}

        with patch.object(self.oidc, "exchange_code", side_effect=synthetic_exchange), \
                patch.object(self.oidc, "fetch_jwks", return_value={"keys": [self.key.as_dict()]}):
            status, headers, body = self._request("GET", callback, cookie=binding)
        self.assertEqual((status, body), (303, b""))
        self.assertEqual(headers["Location"], "/api/service/auth/session")
        self.assertEqual(headers["Cache-Control"], "no-store")
        web_cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertTrue(web_cookie.startswith(f"{COOKIE_NAME}="))
        self.assertIn("Secure; HttpOnly; SameSite=Lax", headers["Set-Cookie"])
        status, _, body = self._request("GET", callback, cookie=binding)
        self.assertEqual(status, 400)
        self.assertIn(b"oidc_state_invalid", body)

        status, _, body = self._request("GET", "/api/service/auth/session")
        self.assertEqual(status, 401)
        status, headers, body = self._request("GET", "/api/service/auth/session", cookie=web_cookie)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        snapshot = json.loads(body)
        csrf = snapshot["csrf_token"]
        status, _, body = self._request("GET", "/api/service/auth/session", cookie=web_cookie)
        self.assertEqual(json.loads(body)["csrf_token"], csrf)
        self.assertEqual(status, 200)

        status, _, body = self._request("POST", "/api/service/auth/logout", cookie=web_cookie,
                                        headers={"Origin": self.identity.browser_security.public_origin})
        self.assertEqual(status, 403)
        self.assertIn(b"csrf_rejected", body)
        status, _, body = self._request("POST", "/api/service/auth/logout", cookie=web_cookie,
                                        headers={"Origin": "https://attacker.example.test", "X-Ronro-CSRF": csrf})
        self.assertEqual(status, 403)
        self.assertIn(b"origin_rejected", body)
        status, _, body = self._request("POST", "/api/service/auth/logout", cookie=web_cookie,
                                        headers={"Origin": self.identity.browser_security.public_origin,
                                                 "X-Ronro-CSRF": csrf})
        self.assertEqual((status, body), (204, b""))
        status, _, _ = self._request("GET", "/api/service/auth/session", cookie=web_cookie)
        self.assertEqual(status, 401)

    def test_duplicate_callback_parameters_are_rejected_without_consuming_state(self):
        state, binding = self._start()
        callback = f"/api/service/auth/callback?code=first&code=second&state={quote(state)}"
        status, _, body = self._request("GET", callback, cookie=binding)
        self.assertEqual(status, 400)
        self.assertIn(b"oidc_callback_invalid", body)
        self.assertEqual(
            self.identity.consume_attempt(state, browser_binding_token=binding.split("=", 1)[1]).state,
            state,
        )

    def test_parallel_tabs_share_browser_binding_but_keep_distinct_states(self):
        first, binding = self._start()
        second, second_binding = self._start(cookie=binding)
        self.assertNotEqual(first, second)
        self.assertEqual(binding, second_binding)
        for state in (second, first):
            callback = f"/api/service/auth/callback?code=synthetic-code&state={quote(state)}"
            with patch.object(
                self.oidc, "exchange_code",
                side_effect=lambda *, code, attempt: {"id_token": self._signed_token(attempt.nonce)},
            ), patch.object(self.oidc, "fetch_jwks", return_value={"keys": [self.key.as_dict()]}):
                status, _, body = self._request("GET", callback, cookie=binding)
            self.assertEqual((status, body), (303, b""))

    def test_wrong_issuer_and_duplicate_cookie_do_not_consume_state(self):
        state, binding = self._start()
        callback = f"/api/service/auth/callback?code=synthetic-code&state={quote(state)}"
        status, _, body = self._request("GET", callback + "&iss=https://other.example.test",
                                        cookie=binding)
        self.assertEqual(status, 400)
        self.assertIn(b"oidc_callback_invalid", body)
        status, _, body = self._request("GET", callback, cookie=binding + "; " + binding)
        self.assertEqual(status, 400)
        self.assertIn(b"oidc_state_invalid", body)
        self.assertEqual(
            self.identity.consume_attempt(state, browser_binding_token=binding.split("=", 1)[1]).state,
            state,
        )
