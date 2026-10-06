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
from prototype.service_account_withdrawal import ServiceAccountWithdrawal
from prototype.service_crypto import InMemoryTestKeyRegistry
from prototype.service_crypto import ServiceCryptoError
from prototype.service_deletion_worker import ServiceDeletionWorker
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
        self.receipt_digests = []
        self.browser_binding = "B" * 43

    def tearDown(self):
        with psycopg.connect(TEST_DSN) as connection:
            for digest in self.receipt_digests:
                connection.execute(
                    "DELETE FROM service_withdrawal_receipt WHERE token_digest = %s", (digest,),
                )
            for session_id in self.created_sessions:
                connection.execute("DELETE FROM service_session WHERE session_id = %s", (session_id,))
                connection.execute("DELETE FROM service_deletion_job WHERE session_id = %s", (session_id,))
            for user_id in self.created_users:
                connection.execute("DELETE FROM service_user WHERE user_id = %s", (user_id,))

    def test_withdrawal_fences_owned_sessions_and_rejects_new_admission(self):
        owner = self._user(f"withdrawing-{uuid.uuid4()}")
        other = self._user(f"remaining-{uuid.uuid4()}")
        owned_ids = [f"test-withdraw-{uuid.uuid4()}" for _ in range(2)]
        other_id = f"test-other-{uuid.uuid4()}"
        for session_id in [*owned_ids, other_id]:
            self.created_sessions.append(session_id)
            self.content.create_session(
                session_id, owner if session_id in owned_ids else other,
            )
        token, csrf = self.store.issue_web_session(owner)
        self.receipt_digests.append(self.store._digest("web-session", token.encode()))
        other_token, _ = self.store.issue_web_session(other)
        grant_id, bearer = self.content.issue_view_credential(owned_ids[0], owner)
        self.assertIsNotNone(grant_id)
        withdrawal = ServiceAccountWithdrawal(self.store, self.content)
        self.assertEqual(withdrawal.withdraw(
            token=token, origin=self.browser.public_origin, csrf_token=csrf,
        ), 2)
        with self.assertRaises(ServiceStoreError) as auth:
            self.store.authenticate(token)
        self.assertEqual(auth.exception.code, "auth_required")
        self.assertEqual(self.store.authenticate(other_token), other)
        with self.assertRaises(ServiceStoreError):
            self.content.authorize_live_canvas(owned_ids[0], bearer)
        with psycopg.connect(TEST_DSN) as connection:
            rows = connection.execute(
                "SELECT session_id, reason FROM service_deletion_job WHERE session_id = ANY(%s)",
                (owned_ids,),
            ).fetchall()
        self.assertEqual({(sid, reason) for sid, reason in rows},
                         {(sid, "account_withdrawal") for sid in owned_ids})
        candidate = f"test-after-withdrawal-{uuid.uuid4()}"
        with self.assertRaises(ServiceStoreError) as admission:
            self.content.open_session(
                candidate, owner,
                {"session_id": candidate, "event_type": "session_created", "sequence": 1},
                require_active_user=True,
            )
        self.assertEqual(admission.exception.code, "account_unavailable")
        worker = ServiceDeletionWorker(self.content)
        self.assertEqual({worker.process_one()["session_id"] for _ in range(2)}, set(owned_ids))
        with psycopg.connect(TEST_DSN) as connection:
            remaining = connection.execute(
                "SELECT session_id FROM service_session WHERE session_id = %s", (other_id,),
            ).fetchone()
        self.assertEqual(remaining[0], other_id)

    def test_withdrawal_rolls_back_if_any_owner_cannot_be_checked(self):
        owner = self._user(f"withdrawing-{uuid.uuid4()}")
        other = self._user(f"unreadable-{uuid.uuid4()}")
        owned_id = f"test-owned-{uuid.uuid4()}"
        unreadable_id = f"test-unreadable-{uuid.uuid4()}"
        for session_id, user_id in ((owned_id, owner), (unreadable_id, other)):
            self.created_sessions.append(session_id)
            self.content.create_session(session_id, user_id)
        token, csrf = self.store.issue_web_session(owner)
        self.content.key_registry.delete_key(unreadable_id)
        with self.assertRaises(ServiceStoreError) as failure:
            ServiceAccountWithdrawal(self.store, self.content).withdraw(
                token=token, origin=self.browser.public_origin, csrf_token=csrf,
            )
        self.assertEqual(failure.exception.code, "owner_lookup_unavailable")
        self.assertEqual(self.store.authenticate(token), owner)
        self.assertEqual(self.content.authorize_owner_session(owned_id, owner), "open")
        with psycopg.connect(TEST_DSN) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM service_deletion_job WHERE session_id = %s", (owned_id,),
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_withdrawal_wins_over_stale_authenticated_create(self):
        owner = self._user(f"admission-race-{uuid.uuid4()}")
        candidate = f"test-after-revocation-{uuid.uuid4()}"
        with psycopg.connect(TEST_DSN) as blocker:
            blocker.execute(
                "SELECT user_id FROM service_user WHERE user_id = %s FOR UPDATE",
                (owner,),
            )
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    self.content.open_session, candidate, owner,
                    {"session_id": candidate, "event_type": "session_created", "sequence": 1},
                    require_active_user=True,
                )
                blocker.execute("DELETE FROM service_user WHERE user_id = %s", (owner,))
                blocker.commit()
                with self.assertRaises(ServiceStoreError) as rejected:
                    future.result(timeout=5)
        self.assertEqual(rejected.exception.code, "account_unavailable")
        with self.assertRaises(ServiceCryptoError) as key:
            self.content.key_registry.get_key(candidate)
        self.assertEqual(key.exception.code, "key_unavailable")
        with psycopg.connect(TEST_DSN) as connection:
            row = connection.execute(
                "SELECT session_id FROM service_session WHERE session_id = %s",
                (candidate,),
            ).fetchone()
        self.assertIsNone(row)

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
