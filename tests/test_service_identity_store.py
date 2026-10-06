"""Synthetic PostgreSQL identity/session tests; never use real accounts."""

from __future__ import annotations

import os
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
from joserfc import jwt
from joserfc.jwk import RSAKey

from prototype.postgres_service_store import PostgresServiceStore
from prototype.schema import SchemaValidator
from prototype.service_browser_security import ServiceBrowserSecurity
from prototype.service_crypto import InMemoryTestKeyRegistry
from prototype.service_errors import ServiceStoreError
from prototype.service_identity_store import ServiceIdentityStore
from prototype.service_oidc import AuthorizationAttempt, OidcConfiguration, ServiceOidcClient
from prototype.service_owner_access import ServiceOwnerAccess


TEST_DSN = os.getenv("RONRO_TEST_POSTGRES_DSN")
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(TEST_DSN, "Synthetic PostgreSQL test DSN is not configured")
class ServiceIdentityStoreTests(unittest.TestCase):
    def setUp(self):
        self.oidc = ServiceOidcClient(OidcConfiguration(
            issuer="https://idp.example.test", client_id="synthetic-ronro-client",
            public_origin="https://ronro.example.test",
            redirect_uri="https://ronro.example.test/api/service/auth/callback",
            authorization_endpoint="https://idp.example.test/oauth/v2/authorize",
            token_endpoint="https://idp.example.test/oauth/v2/token",
            jwks_uri="https://idp.example.test/oauth/v2/keys",
            token_endpoint_auth_method="none",
        ))
        self.content = PostgresServiceStore(
            TEST_DSN, SchemaValidator(ROOT / "schemas"), InMemoryTestKeyRegistry(),
            allow_test_key_registry=True,
        )
        self.content.migrate()
        self.browser = ServiceBrowserSecurity("https://ronro.example.test")
        self.store = ServiceIdentityStore(
            TEST_DSN, bytes(range(32)), self.browser,
            expected_issuer=self.oidc.config.issuer,
        )
        self.created_users = []
        self.created_sessions = []
        self.browser_binding = "B" * 43

    def tearDown(self):
        with psycopg.connect(TEST_DSN) as connection:
            for session_id in self.created_sessions:
                connection.execute("DELETE FROM service_session WHERE session_id = %s", (session_id,))
            for user_id in self.created_users:
                connection.execute("DELETE FROM service_user WHERE user_id = %s", (user_id,))

    def _verified(self, subject: str):
        _, attempt = self.oidc.begin_authorization()
        key = RSAKey.generate_key(auto_kid=True)
        now = int(time.time())
        token = jwt.encode(
            {"alg": "RS256", "kid": key.kid},
            {"iss": self.oidc.config.issuer, "sub": subject,
             "aud": self.oidc.config.client_id, "exp": now + 600,
             "iat": now, "nonce": attempt.nonce},
            key,
        )
        return self.oidc.verify_id_token(
            id_token=token, jwks={"keys": [key.as_dict()]}, attempt=attempt,
        )

    def _user(self, subject: str):
        user_id = self.store.get_or_create_user(self._verified(subject))
        self.created_users.append(user_id)
        return user_id

    def test_attempt_is_encrypted_one_use_and_rejects_expired_state(self):
        _, attempt = self.oidc.begin_authorization()
        self.store.save_attempt(attempt, browser_binding_token=self.browser_binding)
        first_digest = self.store._digest("oidc-state", attempt.state.encode())
        with psycopg.connect(TEST_DSN) as connection:
            row = connection.execute(
                "SELECT state_digest, secret_cipher FROM service_auth_attempt "
                "WHERE state_digest = %s", (first_digest,),
            ).fetchone()
        self.assertNotIn(attempt.state.encode(), bytes(row[0]) + bytes(row[1]))
        self.assertNotIn(attempt.nonce.encode(), bytes(row[1]))
        self.assertNotIn(attempt.code_verifier.encode(), bytes(row[1]))
        self.assertEqual(self.store.consume_attempt(
            attempt.state, browser_binding_token=self.browser_binding,
        ), attempt)
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.consume_attempt(attempt.state, browser_binding_token=self.browser_binding)
        self.assertEqual(caught.exception.code, "oidc_state_invalid")

        _, expired = self.oidc.begin_authorization()
        self.store.save_attempt(expired, browser_binding_token=self.browser_binding)
        digest = self.store._digest("oidc-state", expired.state.encode())
        with psycopg.connect(TEST_DSN) as connection:
            connection.execute(
                "UPDATE service_auth_attempt SET created_at = now() - interval '2 minutes', "
                "expires_at = now() - interval '1 minute' "
                "WHERE state_digest = %s", (digest,),
            )
        with self.assertRaises(ServiceStoreError):
            self.store.consume_attempt(expired.state, browser_binding_token=self.browser_binding)
        self.assertEqual(self.store.purge_expired_auth_records()[0], 1)

    def test_concurrent_callback_can_consume_state_only_once(self):
        _, attempt = self.oidc.begin_authorization()
        self.store.save_attempt(attempt, browser_binding_token=self.browser_binding)

        def consume():
            try:
                return self.store.consume_attempt(
                    attempt.state, browser_binding_token=self.browser_binding,
                )
            except ServiceStoreError as exc:
                return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: consume(), range(2)))
        self.assertEqual(sum(isinstance(r, AuthorizationAttempt) for r in results), 1)
        self.assertEqual(results.count("oidc_state_invalid"), 1)

    def test_callback_requires_same_browser_without_breaking_parallel_tabs(self):
        _, first = self.oidc.begin_authorization()
        _, second = self.oidc.begin_authorization()
        self.store.save_attempt(first, browser_binding_token=self.browser_binding)
        self.store.save_attempt(second, browser_binding_token=self.browser_binding)
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.consume_attempt(first.state, browser_binding_token="C" * 43)
        self.assertEqual(caught.exception.code, "oidc_state_invalid")
        self.assertEqual(self.store.consume_attempt(
            second.state, browser_binding_token=self.browser_binding,
        ), second)
        self.assertEqual(self.store.consume_attempt(
            first.state, browser_binding_token=self.browser_binding,
        ), first)

    def test_user_mapping_and_session_revocation_are_scoped(self):
        first_subject = f"subject-{uuid.uuid4()}"
        first = self._user(first_subject)
        self.assertEqual(self.store.get_or_create_user(self._verified(first_subject)), first)
        second = self._user(f"subject-{uuid.uuid4()}")
        token, csrf = self.store.issue_web_session(first)
        other_token, _ = self.store.issue_web_session(second)
        self.assertEqual(self.store.authenticate(token), first)
        self.assertEqual(self.store.csrf_token_for_web_session(token), csrf)
        self.assertEqual(
            self.store.authenticate_mutation(
                token=token, origin=self.browser.public_origin, csrf_token=csrf,
            ), first,
        )
        self.assertEqual(
            self.store.authenticate_websocket(token=token, origin=self.browser.public_origin), first,
        )
        for wrong_origin, wrong_csrf in (
            ("https://attacker.example.test", csrf),
            (self.browser.public_origin, "wrong-token"),
        ):
            with self.assertRaises(ServiceStoreError):
                self.store.authenticate_mutation(
                    token=token, origin=wrong_origin, csrf_token=wrong_csrf,
                )
        with psycopg.connect(TEST_DSN) as connection:
            row = connection.execute(
                "SELECT token_digest, csrf_digest FROM service_web_session "
                "WHERE user_id = %s", (first,),
            ).fetchone()
        self.assertNotIn(token.encode(), bytes(row[0]) + bytes(row[1]))
        self.assertNotIn(csrf.encode(), bytes(row[0]) + bytes(row[1]))

        self.store.revoke_user_sessions(first)
        with self.assertRaises(ServiceStoreError):
            self.store.authenticate(token)
        self.assertEqual(self.store.authenticate(other_token), second)
        self.store.revoke_web_session(other_token)
        with self.assertRaises(ServiceStoreError):
            self.store.authenticate(other_token)

    def test_unverified_identity_and_disabled_user_fail_closed(self):
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.get_or_create_user(("https://idp.example.test", "synthetic"))
        self.assertEqual(caught.exception.code, "identity_unverified")
        user_id = self._user(f"subject-{uuid.uuid4()}")
        token, _ = self.store.issue_web_session(user_id)
        with psycopg.connect(TEST_DSN) as connection:
            connection.execute(
                "UPDATE service_user SET disabled_at = now() WHERE user_id = %s", (user_id,),
            )
        with self.assertRaises(ServiceStoreError):
            self.store.authenticate(token)
        with self.assertRaises(ServiceStoreError):
            self.store.issue_web_session(user_id)

    def test_expired_web_session_is_rejected_and_purged(self):
        user_id = self._user(f"subject-{uuid.uuid4()}")
        token, _ = self.store.issue_web_session(user_id)
        digest = self.store._digest("web-session", token.encode())
        with psycopg.connect(TEST_DSN) as connection:
            connection.execute(
                "UPDATE service_web_session SET created_at = now() - interval '2 days', "
                "expires_at = now() - interval '1 day' WHERE token_digest = %s",
                (digest,),
            )
        with self.assertRaises(ServiceStoreError) as caught:
            self.store.authenticate(token)
        self.assertEqual(caught.exception.code, "auth_required")
        self.assertEqual(self.store.purge_expired_auth_records()[1], 1)

    def test_owner_gate_rejects_other_account_for_read_mutation_and_audio(self):
        owner = self._user(f"owner-{uuid.uuid4()}")
        other = self._user(f"other-{uuid.uuid4()}")
        session_id = f"test-owner-{uuid.uuid4()}"
        self.created_sessions.append(session_id)
        self.content.create_session(session_id, owner)
        owner_token, owner_csrf = self.store.issue_web_session(owner)
        other_token, other_csrf = self.store.issue_web_session(other)
        gate = ServiceOwnerAccess(self.store, self.content)
        self.assertEqual(gate.read(session_id=session_id, cookie_token=owner_token), owner)
        self.assertEqual(gate.mutate(
            session_id=session_id, cookie_token=owner_token,
            origin=self.browser.public_origin, csrf_token=owner_csrf,
        ), owner)
        self.assertEqual(gate.audio_websocket(
            session_id=session_id, cookie_token=owner_token,
            origin=self.browser.public_origin,
        ), owner)
        for unauthorized_session in (session_id, f"missing-{uuid.uuid4()}"):
            with self.subTest(session=unauthorized_session), self.assertRaises(ServiceStoreError) as caught:
                gate.mutate(
                    session_id=unauthorized_session, cookie_token=other_token,
                    origin=self.browser.public_origin, csrf_token=other_csrf,
                )
            self.assertEqual(caught.exception.code, "session_not_found")
        with self.assertRaises(ServiceStoreError) as caught:
            gate.read(session_id=session_id, cookie_token=other_token)
        self.assertEqual(caught.exception.code, "session_not_found")
        with self.assertRaises(ServiceStoreError) as caught:
            gate.audio_websocket(
                session_id=session_id, cookie_token=other_token,
                origin=self.browser.public_origin,
            )
        self.assertEqual(caught.exception.code, "session_not_found")
        self.store.revoke_web_session(owner_token)
        with self.assertRaises(ServiceStoreError) as caught:
            gate.read(session_id=session_id, cookie_token=owner_token)
        self.assertEqual(caught.exception.code, "auth_required")
