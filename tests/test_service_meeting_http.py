"""Synthetic owner/display HTTP reads; this server never binds publicly."""

from __future__ import annotations

import http.client
import json
import os
import threading
import time
import unittest
import uuid
from pathlib import Path

import psycopg
from joserfc import jwt
from joserfc.jwk import RSAKey

from prototype.postgres_service_store import PostgresServiceStore
from prototype.schema import SchemaValidator
from prototype.service_browser_security import COOKIE_NAME, ServiceBrowserSecurity
from prototype.service_crypto import InMemoryTestKeyRegistry
from prototype.service_identity_store import ServiceIdentityStore
from prototype.service_meeting_http import create_service_meeting_server
from prototype.service_oidc import OidcConfiguration, ServiceOidcClient
from tests.test_service_store import event, final


TEST_DSN = os.getenv("RONRO_TEST_POSTGRES_DSN")
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(TEST_DSN, "Synthetic PostgreSQL test DSN is not configured")
class ServiceMeetingHttpTests(unittest.TestCase):
    def setUp(self):
        self.validator = SchemaValidator(ROOT / "schemas")
        self.content = PostgresServiceStore(
            TEST_DSN, self.validator, InMemoryTestKeyRegistry(),
            allow_test_key_registry=True, require_provider_items=False,
        )
        self.content.migrate()
        self.oidc = ServiceOidcClient(OidcConfiguration(
            issuer="https://idp.example.test", client_id="synthetic-ronro-client",
            public_origin="https://ronro.example.test",
            redirect_uri="https://ronro.example.test/api/service/auth/callback",
            authorization_endpoint="https://idp.example.test/oauth/v2/authorize",
            token_endpoint="https://idp.example.test/oauth/v2/token",
            jwks_uri="https://idp.example.test/oauth/v2/keys",
            token_endpoint_auth_method="client_secret_basic",
            client_secret="synthetic-only-secret",
        ))
        self.identity = ServiceIdentityStore(
            TEST_DSN, bytes(range(32)), ServiceBrowserSecurity("https://ronro.example.test"),
            expected_issuer=self.oidc.config.issuer,
        )
        self.users = []
        self.sessions = []
        self.owner = self._user("owner")
        self.other = self._user("other")
        self.session_id = self._session(self.owner, "合成の会議")
        self.other_session_id = self._session(self.other, "別の合成会議")
        owner_token, _ = self.identity.issue_web_session(self.owner)
        other_token, _ = self.identity.issue_web_session(self.other)
        self.owner_cookie = f"{COOKIE_NAME}={owner_token}"
        self.other_cookie = f"{COOKIE_NAME}={other_token}"
        self.server = create_service_meeting_server(self.identity, self.oidc, self.content)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        with psycopg.connect(TEST_DSN) as connection:
            for session_id in self.sessions:
                connection.execute("DELETE FROM service_session WHERE session_id = %s", (session_id,))
            for user_id in self.users:
                connection.execute("DELETE FROM service_user WHERE user_id = %s", (user_id,))

    def _user(self, role):
        _, attempt = self.oidc.begin_authorization()
        key = RSAKey.generate_key(auto_kid=True)
        now = int(time.time())
        signed = jwt.encode(
            {"alg": "RS256", "kid": key.kid},
            {"iss": self.oidc.config.issuer, "sub": f"synthetic-{role}-{uuid.uuid4()}",
             "aud": self.oidc.config.client_id, "exp": now + 600,
             "iat": now, "nonce": attempt.nonce},
            key,
        )
        verified = self.oidc.verify_id_token(
            id_token=signed, jwks={"keys": [key.as_dict()]}, attempt=attempt,
        )
        user_id = self.identity.get_or_create_user(verified)
        self.users.append(user_id)
        return user_id

    def _session(self, owner, title):
        session_id = f"test-{uuid.uuid4()}"
        self.content.open_session(
            session_id, owner,
            event(session_id, 1, "session_created", {"title": title, "goal": "合成検討"}),
        )
        self.sessions.append(session_id)
        self.content.append_events(session_id, [event(session_id, 2, "session_started", {})])
        return session_id

    def _request(self, path, *, cookie=None, authorization=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {}
        if cookie is not None:
            headers["Cookie"] = cookie
        if authorization is not None:
            headers["Authorization"] = authorization
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def _analyzed_node(self):
        evidence, utterance = final(self.session_id, 1)
        self.content.accept_final(
            self.session_id, evidence, utterance, job_id="synthetic-job",
            contract_version="v1", provider_item_id="synthetic-item",
        )
        claim = self.content.claim_job(session_id=self.session_id, now=100)
        self.content.accept_job_result(
            self.session_id, "synthetic-job", attempt=claim["attempt"],
            start_revision=claim["start_revision"],
            accepted_output={"text": "内部だけの合成出力"},
            events=[event(
                self.session_id, 3, "node_detected",
                {"node_type": "idea", "label": "合成の案を検討する"},
                actor="analyzer", evidence_ids=[evidence["id"]],
            )],
        )
        return evidence["text"]

    def test_owner_read_is_authorized_and_canvas_contains_no_evidence(self):
        transcript = self._analyzed_node()
        base = f"/api/service/sessions/{self.session_id}"
        status, headers, body = self._request(base, cookie=self.owner_cookie)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(json.loads(body)["graph_revision"], 3)
        self.assertNotIn(transcript.encode(), body)
        status, _, body = self._request(base + "/canvas", cookie=self.owner_cookie)
        self.assertEqual(status, 200)
        canvas = json.loads(body)
        self.assertEqual(canvas["revision"], 3)
        self.assertEqual(len(canvas["nodes"]), 1)
        self.assertEqual(canvas["nodes"][0]["canonical"], "合成の案を検討する")
        self.assertNotIn(transcript.encode(), body)
        self.assertNotIn(b"evidence", body.lower())

    def test_foreign_and_nonexistent_sessions_are_indistinguishable(self):
        own = f"/api/service/sessions/{self.session_id}"
        missing = f"/api/service/sessions/test-{uuid.uuid4()}"
        for suffix in ("", "/canvas"):
            foreign = self._request(own + suffix, cookie=self.other_cookie)
            nonexistent = self._request(missing + suffix, cookie=self.other_cookie)
            self.assertEqual((foreign[0], foreign[2]), (404, nonexistent[2]))
        self.assertEqual(self._request(own)[0], 401)

    def test_live_display_bearer_can_read_only_canvas_and_is_revocable(self):
        base = f"/api/service/sessions/{self.session_id}"
        grant, token = self.content.issue_view_credential(self.session_id, self.owner)
        bearer = f"Bearer {token}"
        status, _, body = self._request(base + "/canvas", authorization=bearer)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["session_id"], self.session_id)
        self.assertEqual(self._request(base, authorization=bearer)[0], 404)
        self.assertEqual(self._request(base + "/canvas?token=" + token)[0], 404)
        self.assertEqual(self._request(base + "/canvas", authorization=bearer,
                                       cookie=self.owner_cookie)[0], 404)
        self.assertEqual(self._request(
            f"/api/service/sessions/{self.other_session_id}/canvas",
            authorization=bearer,
        )[0], 404)
        self.assertEqual(self._request("/api/service/auth/session", authorization=bearer)[0], 401)
        self.content.revoke_view_credential(self.session_id, self.owner, grant)
        self.assertEqual(self._request(base + "/canvas", authorization=bearer)[0], 404)

    def test_expired_display_bearer_cannot_read_canvas(self):
        grant, token = self.content.issue_view_credential(self.session_id, self.owner)
        with psycopg.connect(TEST_DSN) as connection:
            connection.execute(
                "UPDATE service_view_credential SET created_at = now() - interval '2 minutes', "
                "expires_at = now() - interval '1 minute' "
                "WHERE grant_id = %s", (grant,),
            )
        self.assertEqual(self._request(
            f"/api/service/sessions/{self.session_id}/canvas",
            authorization=f"Bearer {token}",
        )[0], 404)

    def test_server_does_not_bind_a_public_interface(self):
        with self.assertRaises(ValueError):
            create_service_meeting_server(
                self.identity, self.oidc, self.content, host="0.0.0.0",
            )
