import unittest
import asyncio
import json
from pathlib import Path

from prototype.live_turns import TurnLedger
from prototype.live_stt import OpenAIRealtimeTranscriptionClient, RealtimeSTTConfig
from prototype.live_continuous import LiveContinuousSession
from prototype.live_audio import AudioChunk
from prototype.schema import SchemaValidator
from prototype.replay import ReplayRunner


def pcm(seconds, speech=True):
    return (b'\x00\x10' if speech else b'\x00\x00') * round(seconds * 24000)


class TurnLedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = TurnLedger()

    def commit(self, key, end=None, previous=None):
        if end is not None:
            self.ledger.observe(dict(type='input_audio_buffer.speech_stopped',
                                     item_id=key, audio_end_ms=end * 1000))
        self.ledger.observe(dict(type='input_audio_buffer.committed', item_id=key,
                                 previous_item_id=previous))

    def test_normal_vad(self):
        self.ledger.append(pcm(1))
        self.commit('a', 1)
        self.assertTrue(self.ledger.pending())
        self.assertEqual(self.ledger.context('a')['boundary_reason'], 'server_vad')

    def test_silent_preroll_does_not_age_first_speech(self):
        self.ledger.append(pcm(53, False))
        self.assertEqual(self.ledger.meaningful_pending_seconds, 0)
        self.ledger.append(pcm(.1))
        self.assertAlmostEqual(self.ledger.pending_seconds, 53.1)
        self.assertAlmostEqual(self.ledger.meaningful_pending_seconds, .1)
        self.ledger.append(pcm(29.9))
        self.assertEqual(self.ledger.meaningful_pending_seconds, 30)
        self.ledger.request(1, 'bounded_fallback')
        self.assertEqual(self.ledger.intents[0]['start'], 0)
        self.assertEqual(self.ledger.meaningful_pending_seconds, 0)

    def test_internal_pauses_still_count_toward_bound(self):
        self.ledger.append(pcm(1))
        self.ledger.append(pcm(29, False))
        self.assertEqual(self.ledger.meaningful_pending_seconds, 30)

    def test_new_turn_after_vad_excludes_silent_gap(self):
        self.ledger.append(pcm(1))
        self.commit('a', 1)
        self.ledger.append(pcm(40, False))
        self.ledger.append(pcm(.1))
        self.ledger.complete('a', {'type': 'final_transcript'})
        self.ledger.acknowledge('a')
        self.assertAlmostEqual(self.ledger.meaningful_pending_seconds, .1)

    def test_bound_clamps_to_committed_cursor_inside_frame(self):
        self.ledger.append(pcm(1))
        self.commit('a', .75)
        self.assertEqual(self.ledger.meaningful_pending_seconds, .25)

    def test_out_of_order_completion_does_not_reset_new_clock(self):
        self.ledger.append(pcm(2))
        self.commit('a', 1)
        self.commit('b', 2, 'a')
        self.ledger.append(pcm(40, False))
        self.ledger.append(pcm(3))
        self.ledger.complete('b', {'type': 'final_transcript'})
        self.ledger.complete('a', {'type': 'final_transcript'})
        self.assertEqual(self.ledger.meaningful_pending_seconds, 3)

    def test_bounded_commit_keeps_completion_pending(self):
        self.ledger.append(pcm(30))
        self.ledger.request(1, 'bounded_fallback')
        self.assertEqual(self.ledger.pending_seconds, 0)
        self.commit('a')
        self.assertTrue(self.ledger.pending())
        self.assertEqual(self.ledger.context('a')['local_commit_sequence'], 1)

    def test_r3_belongs_to_different_items(self):
        self.ledger.append(pcm(30))
        self.ledger.request(1, 'bounded_fallback')
        self.commit('a')
        self.ledger.append(pcm(.4, False))
        self.commit('b', 30.368, 'a')
        self.assertTrue(self.ledger.context('a')['meaningful'])
        self.assertFalse(self.ledger.context('b')['meaningful'])
        self.assertEqual(self.ledger.context('b')['boundary_reason'], 'server_vad')
        self.assertIsNone(self.ledger.context('b')['local_commit_sequence'])

    def test_empty_item_diagnostic_keeps_vad_and_delta_identity(self):
        self.ledger.append(pcm(1))
        self.ledger.observe(dict(type='input_audio_buffer.speech_stopped', item_id='tail',
                                 audio_end_ms=1000))
        self.ledger.observe(dict(type='input_audio_buffer.committed', item_id='tail',
                                 previous_item_id='explicit'))
        context = self.ledger.context('tail')
        self.assertIsNone(context['vad_start_ms'])
        self.assertEqual(context['vad_end_ms'], 1000)
        self.assertEqual(context['provider_previous_item_id'], 'explicit')
        self.assertEqual(context['delta_count'], 0)
        self.ledger.observe(dict(type='conversation.item.input_audio_transcription.delta',
                                 item_id='tail'))
        self.assertEqual(self.ledger.context('tail')['delta_count'], 1)

    def test_two_items_pending(self):
        self.ledger.append(pcm(2))
        self.commit('a', 1)
        self.commit('b', 2, 'a')
        self.ledger.acknowledge('a')
        self.assertTrue(self.ledger.pending())

    def test_out_of_order_is_released_in_committed_order(self):
        self.ledger.append(pcm(2))
        self.commit('a', 1)
        self.commit('b', 2, 'a')
        self.assertEqual(self.ledger.complete('b', {'type': 'final_transcript', 'item_id': 'b'})['type'], 'ignored')
        first = self.ledger.complete('a', {'type': 'final_transcript', 'item_id': 'a'})
        self.assertEqual(first['item_id'], 'a')
        self.assertEqual(self.ledger.ready.popleft()['item_id'], 'b')

    def test_duplicate_completion_does_not_release_twice(self):
        self.ledger.append(pcm(1))
        self.commit('a', 1)
        self.ledger.complete('a', {'type': 'final_transcript'})
        self.assertEqual(self.ledger.complete('a', {})['type'], 'duplicate_final')
        self.assertEqual(len(self.ledger.ready), 0)

    def test_old_completion_does_not_clear_new_audio(self):
        self.ledger.append(pcm(30))
        self.ledger.request(1, 'bounded_fallback')
        self.commit('a')
        self.ledger.append(pcm(2))
        self.ledger.complete('a', {'type': 'final_transcript'})
        self.ledger.acknowledge('a')
        self.assertEqual(self.ledger.pending_seconds, 2)
        self.assertTrue(self.ledger.meaningful(self.ledger.cursor, self.ledger.samples))

    def test_explicit_empty_is_not_automatic_silence(self):
        self.ledger.append(pcm(1, False))
        self.ledger.request(1, 'session_end')
        self.commit('a')
        self.assertEqual(self.ledger.context('a')['boundary_reason'], 'session_end')

    def test_silent_vad_region_is_known(self):
        self.ledger.append(pcm(1, False))
        self.commit('a', 1)
        self.assertTrue(self.ledger.context('a')['range_known'])
        self.assertFalse(self.ledger.context('a')['meaningful'])

    def test_end_with_uncommitted_audio(self):
        self.ledger.append(pcm(1))
        self.assertEqual(self.ledger.pending_seconds, 1)
        self.ledger.request(1, 'session_end')
        self.assertTrue(self.ledger.pending())

    def test_end_waits_for_application_handling_not_just_receive(self):
        self.ledger.append(pcm(1))
        self.commit('a', 1)
        self.ledger.complete('a', {'type': 'final_transcript'})
        self.assertTrue(self.ledger.pending())
        self.ledger.acknowledge('a')
        self.assertFalse(self.ledger.pending())

    def test_none_mode_explicit_has_known_range_without_vad(self):
        self.ledger.append(pcm(1))
        self.ledger.request(1, 'explicit_commit')
        self.commit('a')
        self.assertEqual(self.ledger.context('a')['audio_end'], 1)

    def test_duplicate_committed_does_not_consume_another_intent(self):
        self.ledger.append(pcm(1))
        self.ledger.request(1, 'explicit_commit')
        self.commit('a')
        self.ledger.append(pcm(1))
        self.ledger.request(2, 'explicit_commit')
        self.commit('a')
        self.assertEqual(len(self.ledger.intents), 1)

    def test_unknown_ranges_are_not_silent(self):
        self.commit('unknown')
        self.assertFalse(self.ledger.context('unknown')['range_known'])
        self.assertIsNone(self.ledger.context('unknown')['meaningful'])

    def test_overlapping_vad_and_explicit_ack_fails_closed(self):
        self.ledger.append(pcm(30))
        self.ledger.request(1, 'bounded_fallback')
        self.commit('vad', 30)
        self.commit('explicit', previous='vad')
        self.assertFalse(self.ledger.context('explicit')['range_known'])

    def test_unresolved_item_deadline(self):
        self.ledger.append(pcm(1))
        self.commit('a', 1)
        self.ledger.items['a']['at'] -= 100
        self.assertTrue(self.ledger.expired(30))

    def test_empty_commit_after_vad_keeps_item_pending(self):
        self.ledger.append(pcm(1))
        self.ledger.append(pcm(.1, False))
        self.ledger.request(1, 'session_end', 'local-1')
        self.commit('vad', 1.05)
        self.assertTrue(self.ledger.reconcile_empty_commit('local-1'))
        self.assertTrue(self.ledger.pending())

    def test_empty_commit_with_uncovered_speech_is_unsafe(self):
        self.ledger.append(pcm(2))
        self.ledger.request(1, 'session_end', 'local-1')
        self.commit('vad', 1)
        self.assertFalse(self.ledger.reconcile_empty_commit('local-1'))

    def test_empty_commit_wrong_identity_is_unsafe(self):
        self.ledger.append(pcm(1))
        self.ledger.request(1, 'session_end', 'local-1')
        self.commit('vad', 1)
        self.assertFalse(self.ledger.reconcile_empty_commit('other'))

    def test_empty_commit_without_committed_vad_is_unsafe(self):
        self.ledger.append(pcm(1))
        self.ledger.request(1, 'session_end', 'local-1')
        self.assertFalse(self.ledger.reconcile_empty_commit('local-1'))


class ProviderItemTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = OpenAIRealtimeTranscriptionClient(RealtimeSTTConfig(
            endpoint='wss://example.invalid', api_key=None, model='gpt-transcribe',
            language='ja', prompt='', keywords=(), timeout_seconds=5,
            finalization_mode='server_vad_bounded'))
        class Connection:
            def __init__(self): self.events = asyncio.Queue()
            async def send(self, value): pass
            async def recv(self): return await self.events.get()
        self.client._connection = Connection()

    async def event(self, typ, **fields):
        await self.client._connection.events.put(json.dumps(dict(type=typ, **fields)))
        return await self.client.receive_event()

    async def test_opt_in_item_trace_records_identity_without_content(self):
        self.client._trace_item_lifecycle = True
        with self.assertLogs('prototype.live_stt', level='WARNING') as captured:
            await self.client.append_audio(pcm(1))
            self.client.mark_boundary_reason('bounded_fallback')
            await self.client.commit()
            await self.event('input_audio_buffer.committed', item_id='item-a',
                             event_id='commit-a')
            await self.event('conversation.item.input_audio_transcription.completed',
                             item_id='item-a', event_id='complete-a',
                             transcript='非公開の発話本文')
        log = '\n'.join(captured.output)
        self.assertIn('explicit_commit_requested', log)
        self.assertIn('item-a', log)
        self.assertIn('"transcript_length":8', log)
        self.assertNotIn('非公開の発話本文', log)
        self.assertNotIn('"transcript":', log)

    async def test_trace_does_not_break_malformed_provider_error(self):
        self.client._trace_item_lifecycle = True
        with self.assertLogs('prototype.live_stt', level='WARNING'):
            event = await self.event('error', error='unexpected shape')
        self.assertEqual(event['type'], 'stt_error')

    async def test_r3_empty_b_waits_for_a_and_remains_item_scoped(self):
        await self.client.append_audio(pcm(30))
        self.client.mark_boundary_reason('bounded_fallback')
        await self.client.commit()
        await self.event('input_audio_buffer.committed', item_id='a', previous_item_id=None, event_id='commit-a')
        await self.client.append_audio(pcm(.4, False))
        await self.event('input_audio_buffer.speech_stopped', item_id='b', audio_end_ms=30368, event_id='stop-b')
        await self.event('input_audio_buffer.committed', item_id='b', previous_item_id='a')
        empty = await self.event('conversation.item.input_audio_transcription.completed', item_id='b', transcript='')
        self.assertEqual(empty['type'], 'ignored')
        a = await self.event('conversation.item.input_audio_transcription.completed', item_id='a', transcript='検証用発話')
        self.assertEqual(a['item_id'], 'a')
        self.assertEqual(a['_transport']['boundary_reason'], 'bounded_fallback')
        self.assertEqual(a['_transport']['boundary_event_id'], 'commit-a')
        self.client.turns.acknowledge('a')
        self.assertTrue(self.client.has_pending_vad_completion())
        b = await self.client.receive_event()
        self.assertTrue(b['_benign_empty'])
        self.assertEqual(b['_transport']['boundary_reason'], 'server_vad')
        self.assertEqual(b['_transport']['boundary_event_id'], 'stop-b')
        self.client.turns.acknowledge('b')
        self.assertFalse(self.client.has_pending_vad_completion())

    async def test_meaningful_vad_empty_remains_unsafe(self):
        await self.client.append_audio(pcm(1))
        await self.event('input_audio_buffer.speech_stopped', item_id='a', audio_end_ms=1000)
        await self.event('input_audio_buffer.committed', item_id='a')
        result = await self.event('conversation.item.input_audio_transcription.completed', item_id='a', transcript='')
        self.assertEqual(result['code'], 'empty_final_transcript')
        self.assertFalse(result['_benign_empty'])

    async def test_unknown_nonempty_item_cannot_create_wrong_evidence_span(self):
        result = await self.event('conversation.item.input_audio_transcription.completed', item_id='unknown', transcript='検証')
        self.assertEqual(result['code'], 'turn_correlation_failed')

    async def test_explicit_empty_remains_unsafe(self):
        await self.client.append_audio(pcm(1, False))
        await self.client.commit()
        await self.event('input_audio_buffer.committed', item_id='a')
        result = await self.event('conversation.item.input_audio_transcription.completed', item_id='a', transcript='')
        self.assertFalse(result['_benign_empty'])

    async def test_pending_older_item_does_not_block_newer_fallback(self):
        await self.client.append_audio(pcm(30))
        await self.client.commit()
        await self.event('input_audio_buffer.committed', item_id='a')
        await self.client.append_audio(pcm(30))
        self.assertTrue(self.client.should_commit_bounded_fallback(has_audio_buffer=True, meaningful_audio=True))
        self.assertEqual(self.client.turns.pending_seconds, 30)

    async def test_none_mode_end_requires_explicit_commit(self):
        from dataclasses import replace
        self.client.config = replace(self.client.config, finalization_mode='none')
        await self.client.append_audio(pcm(1))
        self.assertTrue(self.client.should_commit_at_session_end(has_audio_buffer=True, meaningful_audio=True))
        await self.client.commit()
        self.assertFalse(self.client.should_commit_at_session_end(has_audio_buffer=True, meaningful_audio=True))

    async def test_gateway_preroll_short_speech_only_commits_at_end(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from prototype.live_session import LiveSessionManager
        from prototype.live_transport import LiveWebSocketGateway
        from prototype.live_audio import encode_audio_frame

        class Analyzer:
            provider_name = model = prompt_version = 'test'
            last_trace = None
            def analyze(self, *args): return []

        class Browser:
            request = SimpleNamespace(path='/live?controller_id=preroll-test')
            def __init__(self):
                self.incoming, self.sent = asyncio.Queue(), []
            async def recv(self): return await self.incoming.get()
            async def send(self, message): self.sent.append(json.loads(message))
            async def close(self): pass

        async def provider_send(message):
            value = json.loads(message)
            if value['type'] == 'input_audio_buffer.commit':
                for event in [
                    dict(type='input_audio_buffer.committed', item_id='end-item', previous_item_id=None),
                    dict(type='conversation.item.input_audio_transcription.completed',
                         item_id='end-item', transcript='資料を確認します'),
                ]:
                    await self.client._connection.events.put(json.dumps(event))

        self.client._connection.send = provider_send
        self.client.connect = AsyncMock()
        manager = LiveSessionManager(schema_dir=Path(__file__).resolve().parents[1] / 'schemas', analyzer_factory=Analyzer)
        manager.start_mode('continuous', controller_id='preroll-test')
        browser = Browser()
        for seq in range(540):
            await browser.incoming.put(encode_audio_frame(AudioChunk(seq, seq / 10, pcm(.1, seq >= 530))))
        await browser.incoming.put(json.dumps({'type': 'stop'}))
        try:
            with patch('prototype.live_transport.OpenAIRealtimeTranscriptionClient', lambda cfg: self.client):
                await asyncio.wait_for(LiveWebSocketGateway(manager, stt_config=self.client.config)(browser), 5)
            boundaries = [e['boundary_reason'] for e in browser.sent if e['type'] == 'stt_committing']
            self.assertEqual(boundaries, ['session_end'])
            self.assertEqual(manager.snapshot()['live_state']['runtime_state'], 'ended')
            self.assertEqual(len(self.client.turns.delivered), 1)
        finally:
            manager.current().close()

    async def test_unmatched_commit_error_drains_incomplete_without_hanging(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from prototype.live_session import LiveSessionManager
        from prototype.live_transport import LiveWebSocketGateway
        from prototype.live_audio import encode_audio_frame

        class Analyzer:
            provider_name = 'test'
            model = 'test'
            prompt_version = 'test'
            last_trace = None
            def analyze(self, *args): return []

        class Browser:
            request = SimpleNamespace(path='/live?controller_id=range-test')
            def __init__(self):
                self.incoming, self.sent = asyncio.Queue(), []
            async def recv(self): return await self.incoming.get()
            async def send(self, message): self.sent.append(json.loads(message))
            async def close(self): pass

        async def provider_send(message):
            value = json.loads(message)
            if value['type'] == 'input_audio_buffer.commit':
                await self.client._connection.events.put(json.dumps({
                    'type': 'error', 'error': {'code': 'input_audio_buffer_commit_empty',
                                             'event_id': value['event_id'], 'message': 'empty'}}))

        self.client._connection.send = provider_send
        self.client.connect = AsyncMock()
        manager = LiveSessionManager(schema_dir=Path(__file__).resolve().parents[1] / 'schemas', analyzer_factory=Analyzer)
        manager.start_mode('continuous', controller_id='range-test')
        browser = Browser()
        await browser.incoming.put(encode_audio_frame(AudioChunk(0, 0.0, pcm(.1))))
        await browser.incoming.put(json.dumps({'type': 'stop'}))
        try:
            with patch('prototype.live_transport.OpenAIRealtimeTranscriptionClient', lambda cfg: self.client):
                await asyncio.wait_for(LiveWebSocketGateway(manager, stt_config=self.client.config)(browser), 2)
            ended = next(x for x in browser.sent if x['type'] == 'session_ended')
            self.assertEqual(ended['snapshot']['live_state']['runtime_state'], 'ended_with_incomplete_processing')
        finally:
            manager.current().close()


class SessionRangeTests(unittest.TestCase):
    def test_final_preserves_newer_buffer_and_evidence_uses_item_range(self):
        class Analyzer:
            provider_name = 'test'
            model = 'test'
            prompt_version = 'test'
            last_trace = None
            def analyze(self, *args): return []
        validator = SchemaValidator(Path(__file__).resolve().parents[1] / 'schemas')
        session = LiveContinuousSession(session_id='item-range-test', schema_validator=validator,
                                        replay_runner=ReplayRunner(validator), analyzer=Analyzer())
        try:
            session.mark_connected()
            session.activate()
            for i in range(3):
                session.accept_audio_chunk(AudioChunk(i, float(i), pcm(1)))
            session.retire_committed_audio(1)
            turn = dict(range_known=True, audio_start=0, audio_end=1,
                        frame_start=0, frame_end=0)
            session.process_final_transcript(raw_text='図書館の資料を確認します', item_id='a',
                                             provider_event={'item_id': 'a', '_turn': turn})
            self.assertEqual(session.audio_buffer_duration_seconds(), 2)
            self.assertEqual(session._current_audio_start_sequence, 1)
            self.assertEqual(session._current_audio_end_sequence, 2)
            self.assertTrue(session.has_meaningful_audio_buffer())
            self.assertEqual(session._live_evidence['audio_end'], 1)
            self.assertEqual(session._live_evidence['audio_frame_sequence_end'], 0)
            self.assertEqual(len(session._evidence), 1)
        finally:
            session.close()


if __name__ == '__main__':
    unittest.main()
