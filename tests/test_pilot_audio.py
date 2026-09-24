from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prototype.errors import PrototypeError
from prototype.live_audio import AudioChunk
from prototype.live_session import LiveSessionManager
from prototype.pilot_audio import PilotAudioRecorder, purge_expired


ROOT = Path(__file__).resolve().parents[1]


class NoopAnalyzer:
    def analyze(self, utterance, current_graph, recent_events):
        return []


class PilotAudioTests(unittest.TestCase):
    def test_pcm_private_file_and_seven_day_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "recordings"
            recorder = PilotAudioRecorder(root, "live-123456abcdef")
            pcm = b"\x01\x02" * 2400
            recorder.append(AudioChunk(0, 0.0, pcm))
            recorder.append(AudioChunk(1, 0.1, pcm))
            recorder.close()
            path = root / "live-123456abcdef"
            self.assertEqual((path / "audio.pcm").read_bytes(), pcm + pcm)
            self.assertEqual((path / "audio.pcm").stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
            metadata = json.loads((path / "metadata.json").read_text())
            self.assertEqual(metadata["format"], "pcm_s16le")
            self.assertEqual(metadata["retention_days"], 7)
            expires = dt.datetime.fromisoformat(metadata["expires_at"])
            self.assertEqual(purge_expired(root, now=expires - dt.timedelta(seconds=1)), 0)
            self.assertEqual(purge_expired(root, now=expires), 1)
            self.assertFalse(path.exists())

    def test_pilot_requires_consent_and_records_without_graph_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            audio_root = Path(temporary) / "recordings"
            with patch.dict(os.environ, {"PILOT_RAW_AUDIO_ENABLED": "true", "PILOT_AUDIO_ROOT": str(audio_root)}):
                manager = LiveSessionManager(schema_dir=ROOT / "schemas", analyzer_factory=NoopAnalyzer)
                with self.assertRaises(PrototypeError) as error:
                    manager.start_mode("continuous", all_participants_consented=False)
                self.assertEqual(error.exception.code, "pilot_audio_consent_required")
                start = manager.start_mode("continuous", all_participants_consented=True)
                session_id = start["live_state"]["session_id"]
                self.assertEqual(start["live_state"]["pilot_audio"]["state"], "recording")
                self.assertEqual(manager.start_mode("continuous")["live_state"]["session_id"], session_id)
                manager.mark_connected()
                manager.activate()
                pcm = b"\x11\x00" * 2400
                first_chunk = manager.accept_chunk(AudioChunk(0, 0.0, pcm))
                self.assertEqual(first_chunk["live_state"]["pilot_audio"]["state"], "recording")
                manager.record_capture_interruption("test_disconnect")
                manager.mark_connected()
                manager.activate()
                manager.accept_chunk(AudioChunk(1, 0.1, pcm))
                self.assertEqual((audio_root / session_id / "audio.pcm").read_bytes(), pcm + pcm)
                snapshot = manager.snapshot()
                self.assertEqual(snapshot["state"]["graph"]["revision"], start["state"]["graph"]["revision"])
                self.assertNotIn("audio.pcm", str(snapshot))
                manager.close()
                metadata = json.loads((audio_root / session_id / "metadata.json").read_text())
                self.assertEqual(metadata["state"], "incomplete")
                self.assertEqual(metadata["capture_interruptions"][0]["code"], "test_disconnect")
                self.assertEqual(metadata["capture_interruptions"][0]["gap_duration"], "unknown")

    def test_crash_without_metadata_is_purged_after_seven_days(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "recordings"
            root.mkdir()
            path = root / "live-123456abcdef"
            path.mkdir()
            (path / "audio.pcm").write_bytes(b"\x00\x00")
            old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=8)).timestamp()
            os.utime(path, (old, old))
            self.assertEqual(purge_expired(root), 1)
            self.assertFalse(path.exists())

    def test_recording_write_failure_keeps_meeting_active_and_visible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"PILOT_RAW_AUDIO_ENABLED": "true", "PILOT_AUDIO_ROOT": str(Path(temporary) / "recordings")}):
                manager = LiveSessionManager(schema_dir=ROOT / "schemas", analyzer_factory=NoopAnalyzer)
                manager.start_mode("continuous", all_participants_consented=True)
                manager.mark_connected()
                manager.activate()
                with patch.object(manager._pilot_recorder, "append", side_effect=OSError("private storage error")):
                    failed_chunk = manager.accept_chunk(AudioChunk(0, 0.0, b"\x01\x00" * 2400))
                self.assertEqual(failed_chunk["live_state"]["pilot_audio"]["error"], "recording_write_failed")
                state = manager.snapshot()["live_state"]
                self.assertEqual(state["runtime_state"], "active")
                self.assertEqual(state["pilot_audio"]["state"], "incomplete")
                self.assertEqual(state["pilot_audio"]["error"], "recording_write_failed")
                manager.close()


if __name__ == "__main__":
    unittest.main()
