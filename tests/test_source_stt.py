"""Public-safe source-scoped STT contract; no Provider or real audio calls."""

import unittest

from prototype.live_audio import AudioChunk
from prototype.source_stt import (
    AudioRange, SourceSTTLedger, STTCommitted, STTFailure, STTFinal, STTIntegrityError,
    STTSource,
)


SOURCE_A = STTSource("session-synthetic", "run-1", "player-a", "connection-1")
SOURCE_B = STTSource("session-synthetic", "run-1", "player-b", "connection-1")


def frame(sequence: int, start: int, *, signal: bool = True, samples: int = 2400) -> AudioChunk:
    pcm = (b"\x00\x10" if signal else b"\x00\x00") * samples
    return AudioChunk(sequence, start / 24_000, pcm)


def committed(source: STTSource, item: str, start: int, end: int) -> STTCommitted:
    return STTCommitted(source, item, AudioRange(start, end))


class SourceSTTLedgerTests(unittest.TestCase):
    def test_two_sources_may_reuse_provider_item_id_without_cross_correlation(self) -> None:
        first, second = SourceSTTLedger(SOURCE_A), SourceSTTLedger(SOURCE_B)
        first.append(frame(0, 0))
        second.append(frame(0, 0))
        first.commit(committed(SOURCE_A, "item-1", 0, 2400))
        second.commit(committed(SOURCE_B, "item-1", 0, 2400))
        with self.assertRaises(STTIntegrityError):
            first.complete(STTFinal(SOURCE_B, "item-1", "別の端末の発話"))
        self.assertTrue(first.complete(STTFinal(SOURCE_A, "item-1", "発話A")))
        self.assertTrue(second.complete(STTFinal(SOURCE_B, "item-1", "発話B")))
        self.assertEqual(first.next_ready_final().text, "発話A")
        self.assertEqual(second.next_ready_final().text, "発話B")
        first.acknowledge("item-1")
        self.assertTrue(first.drain().complete)
        self.assertFalse(second.drain().complete)

    def test_out_of_order_completion_waits_for_older_item_and_ack(self) -> None:
        ledger = SourceSTTLedger(SOURCE_A)
        ledger.append(frame(0, 0))
        ledger.append(frame(1, 2400))
        ledger.commit(committed(SOURCE_A, "old", 0, 2400))
        ledger.commit(committed(SOURCE_A, "new", 2400, 4800))
        ledger.complete(STTFinal(SOURCE_A, "new", "新しい発話"))
        self.assertIsNone(ledger.next_ready_final())
        ledger.complete(STTFinal(SOURCE_A, "old", "古い発話"))
        self.assertEqual(ledger.next_ready_final().item_id, "old")
        with self.assertRaises(STTIntegrityError):
            ledger.acknowledge("new")
        ledger.acknowledge("old")
        self.assertEqual(ledger.next_ready_final().item_id, "new")
        ledger.append(frame(2, 4800))
        ledger.acknowledge("new")
        self.assertEqual(ledger.drain().uncommitted_audio, AudioRange(4800, 7200))
        self.assertEqual(ledger.accepted_sample_end, 7200)

    def test_duplicate_final_is_idempotent_but_conflict_is_rejected(self) -> None:
        ledger = SourceSTTLedger(SOURCE_A)
        ledger.append(frame(0, 0))
        ledger.commit(committed(SOURCE_A, "item", 0, 2400))
        final = STTFinal(SOURCE_A, "item", "同じ発話")
        self.assertTrue(ledger.complete(final))
        self.assertFalse(ledger.complete(final))
        ledger.acknowledge("item")
        self.assertFalse(ledger.complete(final))
        with self.assertRaises(STTIntegrityError):
            ledger.complete(STTFinal(SOURCE_A, "item", "異なる発話"))
        self.assertTrue(ledger.drain().complete)

    def test_empty_completion_does_not_end_session_or_create_evidence(self) -> None:
        ledger = SourceSTTLedger(SOURCE_A)
        ledger.append(frame(0, 0, signal=False))
        ledger.commit(committed(SOURCE_A, "silent", 0, 2400))
        ledger.complete(STTFinal(SOURCE_A, "silent", "  "))
        self.assertIsNone(ledger.next_ready_final())
        self.assertTrue(ledger.drain().complete)
        ledger.append(frame(1, 2400, signal=True))
        ledger.commit(committed(SOURCE_A, "possible", 2400, 4800))
        ledger.complete(STTFinal(SOURCE_A, "possible", ""))
        self.assertEqual(ledger.drain().unresolved_item_ids, ("possible",))
        ledger.append(frame(2, 4800, signal=True))
        ledger.commit(committed(SOURCE_A, "later", 4800, 7200))
        ledger.complete(STTFinal(SOURCE_A, "later", "後続発話"))
        self.assertEqual(ledger.next_ready_final().item_id, "later")
        ledger.acknowledge("later")
        self.assertEqual(ledger.drain().unresolved_item_ids, ("possible",))

    def test_unknown_item_range_and_wrong_source_fail_closed(self) -> None:
        ledger = SourceSTTLedger(SOURCE_A)
        ledger.append(frame(0, 0))
        for value in (
            committed(SOURCE_B, "foreign", 0, 2400),
            committed(SOURCE_A, "unknown", 0, 4800),
        ):
            with self.assertRaises(STTIntegrityError):
                ledger.commit(value)
        with self.assertRaises(STTIntegrityError):
            ledger.complete(STTFinal(SOURCE_A, "no-commit", "架空の発話"))
        ledger.commit(committed(SOURCE_A, "known", 0, 2400))
        with self.assertRaises(STTIntegrityError):
            ledger.commit(committed(SOURCE_A, "overlap", 1200, 2400))
        with self.assertRaises(STTIntegrityError):
            ledger.commit(committed(SOURCE_A, "known", 0, 1200))
        self.assertEqual(ledger.drain().unresolved_item_ids, ("known",))

    def test_sequence_gap_sample_gap_and_metadata_bound_do_not_mutate_cursor(self) -> None:
        ledger = SourceSTTLedger(SOURCE_A, max_pending_frames=1)
        with self.assertRaises(STTIntegrityError):
            ledger.append(frame(1, 0))
        ledger.append(frame(0, 0))
        for invalid in (frame(1, 2500), frame(1, 2000), frame(2, 2400), frame(1, 2400)):
            with self.assertRaises(STTIntegrityError):
                ledger.append(invalid)
            self.assertEqual(ledger.accepted_sample_end, 2400)
        ledger.commit(committed(SOURCE_A, "item", 0, 2400))
        ledger.append(frame(1, 2400))
        ledger.close_capture(1)
        with self.assertRaises(STTIntegrityError):
            ledger.append(frame(2, 4800))
        self.assertEqual(ledger.drain().uncommitted_audio, AudioRange(2400, 4800))

    def test_skipped_signal_is_reported_but_skipped_silence_is_not(self) -> None:
        ledger = SourceSTTLedger(SOURCE_A)
        ledger.append(frame(0, 0, signal=True))
        ledger.append(frame(1, 2400, signal=False))
        ledger.append(frame(2, 4800, signal=True))
        ledger.commit(committed(SOURCE_A, "second", 2400, 4800))
        ledger.complete(STTFinal(SOURCE_A, "second", "二番目"))
        ledger.acknowledge("second")
        self.assertEqual(ledger.drain().unclaimed_audio, (AudioRange(0, 2400),))
        self.assertEqual(ledger.drain().uncommitted_audio, AudioRange(4800, 7200))

        silent = SourceSTTLedger(SOURCE_B)
        silent.append(frame(0, 0, signal=False))
        silent.append(frame(1, 2400, signal=True))
        silent.commit(committed(SOURCE_B, "second", 2400, 4800))
        silent.complete(STTFinal(SOURCE_B, "second", "発話"))
        silent.acknowledge("second")
        self.assertTrue(silent.drain().complete)

    def test_connection_generation_is_part_of_source_identity(self) -> None:
        old = SourceSTTLedger(SOURCE_A)
        old.append(frame(0, 0))
        old.commit(committed(SOURCE_A, "item", 0, 2400))
        newer = STTSource(SOURCE_A.session_id, SOURCE_A.run_id,
                          SOURCE_A.player_id, "connection-2")
        with self.assertRaises(STTIntegrityError):
            old.complete(STTFinal(newer, "item", "古い接続には属さない"))

    def test_failed_item_is_reported_and_does_not_block_later_final(self) -> None:
        ledger = SourceSTTLedger(SOURCE_A)
        ledger.append(frame(0, 0))
        ledger.append(frame(1, 2400))
        ledger.commit(committed(SOURCE_A, "failed", 0, 2400))
        ledger.commit(committed(SOURCE_A, "later", 2400, 4800))
        ledger.complete(STTFinal(SOURCE_A, "later", "後続発話"))
        self.assertIsNone(ledger.next_ready_final())
        ledger.fail(STTFailure(SOURCE_A, "provider_error", "failed"))
        ledger.fail(STTFailure(SOURCE_A, "provider_error", "failed"))
        with self.assertRaises(STTIntegrityError):
            ledger.fail(STTFailure(SOURCE_A, "different_error", "failed"))
        self.assertEqual(ledger.next_ready_final().item_id, "later")
        ledger.acknowledge("later")
        self.assertEqual(ledger.drain().unresolved_item_ids, ("failed",))
        with self.assertRaises(STTIntegrityError):
            ledger.complete(STTFinal(SOURCE_A, "failed", "遅れて来た不整合Final"))
        ledger.fail(STTFailure(SOURCE_A, "transport_unavailable"))
        self.assertEqual(ledger.drain().source_failure_codes, ("transport_unavailable",))
        with self.assertRaises(STTIntegrityError):
            STTFailure(SOURCE_A, "secret=provider-token")


if __name__ == "__main__":
    unittest.main()
