"""Loopback-only, synthetic-owner and synthetic-Provider Service WSS checks."""

from __future__ import annotations

import asyncio
import json
import os
import time
import unittest
import uuid
from pathlib import Path

import psycopg
from joserfc import jwt
from joserfc.jwk import RSAKey
from websockets.asyncio.client import connect

from prototype.live_audio import AudioChunk, encode_audio_frame
from prototype.live_stt import RealtimeSTTConfig
from prototype.live_turns import TurnLedger
from prototype.postgres_service_store import PostgresServiceStore
from prototype.schema import SchemaValidator
from prototype.service_audio_transport import ServiceAudioGateway, serve_service_audio_candidate
from prototype.service_browser_security import COOKIE_NAME, ServiceBrowserSecurity
from prototype.service_crypto import InMemoryTestKeyRegistry
from prototype.service_identity_store import ServiceIdentityStore
from prototype.service_oidc import OidcConfiguration, ServiceOidcClient
from tests.test_service_store import event


TEST_DSN = os.getenv("RONRO_TEST_POSTGRES_DSN")
ROOT = Path(__file__).resolve().parents[1]


class SyntheticProvider:
    def __init__(self, config, *, fail_append=False):
        self.config = config
        self.turns = TurnLedger()
        self.events = asyncio.Queue()
        self.fail_append = fail_append
        self.closed = False

    async def connect(self):
        return None

    async def close(self):
        self.closed = True

    async def append_audio(self, pcm):
        if self.fail_append:
            raise RuntimeError("synthetic provider append failure")
        self.turns.append(pcm)
        self.turns.request(1, "synthetic_turn", "synthetic-client-commit")
        committed = {
            "type": "input_audio_buffer.committed", "event_id": "synthetic-commit",
            "item_id": "synthetic-item",
        }
        self.turns.observe(committed)
        await self.events.put({
            "type": "provider_item_committed", "event_id": "synthetic-commit",
            "item_id": "synthetic-item", "_turn": self.turns.context("synthetic-item"),
        })
        await self.events.put({
            "type": "final_transcript",
            "raw_type": "conversation.item.input_audio_transcription.completed",
            "event_id": "synthetic-completion", "item_id": "synthetic-item",
            "text": "合成会議の案を検討する", "_turn": self.turns.context("synthetic-item"),
        })

    async def receive_event(self):
        return await self.events.get()

    def has_pending_vad_completion(self):
        return False


@unittest.skipUnless(TEST_DSN, "Synthetic PostgreSQL test DSN is not configured")
class ServiceAudioTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session_id = str(uuid.uuid4())
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
        self.identity = ServiceIdentityStore(
            TEST_DSN, bytes(range(32)), ServiceBrowserSecurity("https://ronro.example.test"),
            expected_issuer=self.oidc.config.issuer,
        )
        _, attempt = self.oidc.begin_authorization()
        key = RSAKey.generate_key(auto_kid=True)
        now = int(time.time())
        signed = jwt.encode(
            {"alg": "RS256", "kid": key.kid},
            {"iss": self.oidc.config.issuer, "sub": f"synthetic-{uuid.uuid4()}",
             "aud": self.oidc.config.client_id, "exp": now + 600,
             "iat": now, "nonce": attempt.nonce},
            key,
        )
        verified = self.oidc.verify_id_token(
            id_token=signed, jwks={"keys": [key.as_dict()]}, attempt=attempt,
        )
        self.owner = self.identity.get_or_create_user(verified)
        self.token, _ = self.identity.issue_web_session(self.owner)
        self.content.open_session(
            self.session_id, self.owner,
            event(self.session_id, 1, "session_created", {"title": "合成会議", "goal": "検討"}),
        )
        self.content.request_capture_transition(
            self.session_id, self.owner, action="start",
            operation_key="synthetic-start", expected_version=0,
        )
        config = RealtimeSTTConfig(
            endpoint="wss://example.invalid/realtime", api_key=None,
            model="gpt-transcribe", language="ja", prompt=None,
            keywords=(), timeout_seconds=1.0, finalization_mode="none",
        )
        self.providers = []

        def factory(config):
            provider = SyntheticProvider(config, fail_append=getattr(self, "fail_append", False))
            self.providers.append(provider)
            return provider

        self.gateway = ServiceAudioGateway(
            self.identity, self.content, stt_config=config, provider_factory=factory,
        )
        self.server = await serve_service_audio_candidate(self.gateway)
        port = self.server.sockets[0].getsockname()[1]
        self.url = (f"ws://127.0.0.1:{port}/api/service/sessions/"
                    f"{self.session_id}/audio?generation=1")

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()
        with psycopg.connect(TEST_DSN) as connection:
            connection.execute("DELETE FROM service_session WHERE session_id = %s", (self.session_id,))
            connection.execute("DELETE FROM service_user WHERE user_id = %s", (self.owner,))

    def _headers(self):
        return {"Cookie": f"{COOKIE_NAME}={self.token}"}

    async def _connect(self, *, origin="https://ronro.example.test", headers=None, url=None):
        return await connect(
            url or self.url, origin=origin,
            additional_headers=self._headers() if headers is None else headers,
            proxy=None, close_timeout=1,
        )

    async def test_owner_audio_reaches_strict_item_store_then_pauses_cleanly(self):
        async with await self._connect() as socket:
            self.assertEqual(json.loads(await socket.recv()), {
                "type": "capture_ready", "generation": 1,
            })
            frame = encode_audio_frame(AudioChunk(0, 0.0, b"\x01\x00" * 2400))
            await socket.send(frame)
            self.assertEqual(json.loads(await socket.recv()), {
                "type": "frame_received", "sequence": 0, "created": True,
            })
            self.assertEqual(json.loads(await socket.recv()), {
                "type": "final_accepted", "sequence": 1,
            })
            self.assertEqual(len(self.content.replay(self.session_id).state["evidence"]), 1)
            snapshot = self.content.capture_snapshot(self.session_id, self.owner)
            self.content.request_capture_transition(
                self.session_id, self.owner, action="pause",
                operation_key="synthetic-pause", expected_version=snapshot["version"],
            )
            await socket.send(json.dumps({"type": "capture_stop", "last_sequence": 0}))
            self.assertEqual(json.loads(await socket.recv()), {
                "type": "capture_paused", "generation": 1,
            })
            await asyncio.wait_for(socket.wait_closed(), timeout=3)
        self.assertEqual(self.content.capture_snapshot(self.session_id, self.owner)["state"], "paused")

    async def test_pause_resume_keeps_graph_and_uses_new_audio_generation(self):
        frame = encode_audio_frame(AudioChunk(0, 0.0, b"\x01\x00" * 2400))
        async with await self._connect() as socket:
            await socket.recv()  # capture_ready
            await socket.send(frame)
            self.assertEqual(json.loads(await socket.recv())["type"], "frame_received")
            self.assertEqual(json.loads(await socket.recv())["sequence"], 1)
            first = self.content.capture_snapshot(self.session_id, self.owner)
            self.content.request_capture_transition(
                self.session_id, self.owner, action="pause",
                operation_key="pause-once", expected_version=first["version"],
            )
            await socket.send(json.dumps({"type": "capture_stop", "last_sequence": 0}))
            self.assertEqual(json.loads(await socket.recv())["type"], "capture_paused")
            await asyncio.wait_for(socket.wait_closed(), timeout=3)
        paused = self.content.capture_snapshot(self.session_id, self.owner)
        self.assertEqual(paused["state"], "paused")
        resumed = self.content.request_capture_transition(
            self.session_id, self.owner, action="resume",
            operation_key="resume-once", expected_version=paused["version"],
        )
        self.assertEqual(resumed["generation"], 2)
        async with await self._connect(url=self.url.replace("generation=1", "generation=2")) as socket:
            self.assertEqual(json.loads(await socket.recv())["generation"], 2)
            await socket.send(frame)
            self.assertTrue(json.loads(await socket.recv())["created"])
            self.assertEqual(json.loads(await socket.recv())["sequence"], 2)
        self.assertEqual(len(self.content.replay(self.session_id).state["evidence"]), 2)

    async def test_origin_cookie_and_generation_are_required_before_provider_connect(self):
        for options in (
            {"origin": "https://other.example.test"},
            {"headers": {}},
            {"url": self.url.replace("generation=1", "generation=2")},
            {"url": self.url + "&token=not-allowed"},
        ):
            with self.subTest(options=options):
                async with await self._connect(**options) as socket:
                    await asyncio.wait_for(socket.wait_closed(), timeout=2)
                    self.assertEqual(socket.close_code, 1008)
        self.assertEqual(self.providers, [])

    async def test_web_session_revocation_interrupts_silent_socket(self):
        async with await self._connect() as socket:
            self.assertEqual(json.loads(await socket.recv())["type"], "capture_ready")
            self.identity.revoke_web_session(self.token)
            await asyncio.wait_for(socket.wait_closed(), timeout=3)
        snapshot = self.content.capture_snapshot(self.session_id, self.owner)
        self.assertEqual(snapshot["state"], "reconnecting")
        self.assertEqual(snapshot["generation"], 2)

    async def test_retried_frame_is_not_appended_or_finalized_twice(self):
        async with await self._connect() as socket:
            self.assertEqual(json.loads(await socket.recv())["type"], "capture_ready")
            frame = encode_audio_frame(AudioChunk(0, 0.0, b"\x01\x00" * 2400))
            await socket.send(frame)
            self.assertTrue(json.loads(await socket.recv())["created"])
            self.assertEqual(json.loads(await socket.recv())["type"], "final_accepted")
            await socket.send(frame)
            self.assertEqual(json.loads(await socket.recv()), {
                "type": "frame_received", "sequence": 0, "created": False,
            })
            self.assertEqual(self.providers[0].turns.samples, 2400)
            self.assertEqual(len(self.content.replay(self.session_id).state["evidence"]), 1)

    async def test_other_owner_cannot_open_audio_for_this_session(self):
        _, attempt = self.oidc.begin_authorization()
        key = RSAKey.generate_key(auto_kid=True)
        now = int(time.time())
        signed = jwt.encode(
            {"alg": "RS256", "kid": key.kid},
            {"iss": self.oidc.config.issuer, "sub": f"synthetic-other-{uuid.uuid4()}",
             "aud": self.oidc.config.client_id, "exp": now + 600,
             "iat": now, "nonce": attempt.nonce}, key,
        )
        verified = self.oidc.verify_id_token(
            id_token=signed, jwks={"keys": [key.as_dict()]}, attempt=attempt,
        )
        other = self.identity.get_or_create_user(verified)
        try:
            other_token, _ = self.identity.issue_web_session(other)
            async with await self._connect(headers={
                "Cookie": f"{COOKIE_NAME}={other_token}",
            }) as socket:
                await asyncio.wait_for(socket.wait_closed(), timeout=2)
                self.assertEqual(socket.close_code, 1008)
            self.assertEqual(self.providers, [])
        finally:
            with psycopg.connect(TEST_DSN) as connection:
                connection.execute("DELETE FROM service_user WHERE user_id = %s", (other,))

    async def test_failed_provider_append_is_explicit_gap_and_fences_generation(self):
        self.fail_append = True
        async with await self._connect() as socket:
            self.assertEqual(json.loads(await socket.recv())["type"], "capture_ready")
            await socket.send(encode_audio_frame(AudioChunk(0, 0.0, b"\x01\x00" * 2400)))
            await asyncio.wait_for(socket.wait_closed(), timeout=3)
        snapshot = self.content.capture_snapshot(self.session_id, self.owner)
        self.assertEqual(snapshot["state"], "reconnecting")
        self.assertEqual(snapshot["generation"], 2)
        with psycopg.connect(TEST_DSN) as connection:
            row = connection.execute(
                """SELECT reason_code, missing_first_sequence, missing_last_sequence
                   FROM service_capture_interval WHERE session_id = %s""",
                (self.session_id,),
            ).fetchone()
        self.assertEqual(row, ("provider_append_unverified", 0, 0))

    async def test_provider_connection_failure_releases_starting_generation(self):
        class FailingConnect(SyntheticProvider):
            async def connect(self):
                raise RuntimeError("synthetic connection failure")

        self.gateway.provider_factory = lambda config: FailingConnect(config)
        async with await self._connect() as socket:
            await asyncio.wait_for(socket.wait_closed(), timeout=3)
        snapshot = self.content.capture_snapshot(self.session_id, self.owner)
        self.assertEqual(snapshot["state"], "reconnecting")
        self.assertEqual(snapshot["generation"], 2)

    async def test_pause_does_not_claim_clean_state_with_unresolved_provider_item(self):
        class StalledProvider(SyntheticProvider):
            async def append_audio(self, pcm):
                self.turns.append(pcm)
                self.turns.request(1, "synthetic_turn", "synthetic-client-commit")
                self.turns.observe({
                    "type": "input_audio_buffer.committed", "event_id": "synthetic-commit",
                    "item_id": "synthetic-item",
                })
                await self.events.put({
                    "type": "provider_item_committed", "event_id": "synthetic-commit",
                    "item_id": "synthetic-item", "_turn": self.turns.context("synthetic-item"),
                })

        self.gateway.provider_factory = lambda config: StalledProvider(config)
        async with await self._connect() as socket:
            self.assertEqual(json.loads(await socket.recv())["type"], "capture_ready")
            await socket.send(encode_audio_frame(AudioChunk(0, 0.0, b"\x01\x00" * 2400)))
            self.assertEqual(json.loads(await socket.recv())["type"], "frame_received")
            snapshot = self.content.capture_snapshot(self.session_id, self.owner)
            self.content.request_capture_transition(
                self.session_id, self.owner, action="pause",
                operation_key="pause-unresolved", expected_version=snapshot["version"],
            )
            await socket.send(json.dumps({"type": "capture_stop", "last_sequence": 0}))
            await asyncio.wait_for(socket.wait_closed(), timeout=3)
        snapshot = self.content.capture_snapshot(self.session_id, self.owner)
        self.assertEqual(snapshot["state"], "reconnecting")
        self.assertEqual(snapshot["generation"], 2)

    async def test_pause_without_verified_stop_cannot_become_paused(self):
        async with await self._connect() as socket:
            self.assertEqual(json.loads(await socket.recv())["type"], "capture_ready")
            snapshot = self.content.capture_snapshot(self.session_id, self.owner)
            self.content.request_capture_transition(
                self.session_id, self.owner, action="pause",
                operation_key="pause-without-stop", expected_version=snapshot["version"],
            )
            await asyncio.wait_for(socket.wait_closed(), timeout=3)
        snapshot = self.content.capture_snapshot(self.session_id, self.owner)
        self.assertEqual(snapshot["state"], "reconnecting")
        with psycopg.connect(TEST_DSN) as connection:
            count = connection.execute(
                """SELECT COUNT(*) FROM service_capture_interval
                   WHERE session_id = %s AND kind = 'capture_unavailable'""",
                (self.session_id,),
            ).fetchone()[0]
        self.assertGreaterEqual(count, 1)

    async def test_pause_rejects_mismatched_last_frame_and_does_not_end_cleanly(self):
        async with await self._connect() as socket:
            self.assertEqual(json.loads(await socket.recv())["type"], "capture_ready")
            await socket.send(encode_audio_frame(AudioChunk(0, 0.0, b"\x01\x00" * 2400)))
            self.assertEqual(json.loads(await socket.recv())["type"], "frame_received")
            self.assertEqual(json.loads(await socket.recv())["type"], "final_accepted")
            snapshot = self.content.capture_snapshot(self.session_id, self.owner)
            self.content.request_capture_transition(
                self.session_id, self.owner, action="pause",
                operation_key="pause-wrong-tail", expected_version=snapshot["version"],
            )
            await socket.send(json.dumps({"type": "capture_stop", "last_sequence": 1}))
            await asyncio.wait_for(socket.wait_closed(), timeout=3)
        self.assertEqual(self.content.capture_snapshot(self.session_id, self.owner)["state"],
                         "reconnecting")

    async def test_frames_queued_after_http_pause_are_accepted_before_stop_control(self):
        async with await self._connect() as socket:
            self.assertEqual(json.loads(await socket.recv())["type"], "capture_ready")
            snapshot = self.content.capture_snapshot(self.session_id, self.owner)
            self.content.request_capture_transition(
                self.session_id, self.owner, action="pause",
                operation_key="pause-before-last-frame", expected_version=snapshot["version"],
            )
            await socket.send(encode_audio_frame(AudioChunk(0, 0.0, b"\x01\x00" * 2400)))
            await socket.send(json.dumps({"type": "capture_stop", "last_sequence": 0}))
            received = [json.loads(await socket.recv()) for _ in range(3)]
            self.assertEqual([item["type"] for item in received], [
                "frame_received", "final_accepted", "capture_paused",
            ])
            await asyncio.wait_for(socket.wait_closed(), timeout=3)
        self.assertEqual(self.content.capture_snapshot(self.session_id, self.owner)["state"],
                         "paused")
        self.assertEqual(len(self.content.replay(self.session_id).state["evidence"]), 1)


if __name__ == "__main__":
    unittest.main()
