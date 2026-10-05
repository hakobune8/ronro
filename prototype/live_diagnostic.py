"""Opt-in, in-memory diagnostics. Never used for finalization decisions.

No audio, transcript, prompt, credentials or device identifiers are retained.
The caller owns private persistence; normal runtime has no recorder installed.
"""
from __future__ import annotations

import contextvars
import time
from contextlib import contextmanager

_current = contextvars.ContextVar("live_diagnostic_recorder", default=None)


@contextmanager
def capture_diagnostics(recorder):
    token = _current.set(recorder)
    try:
        yield recorder
    finally:
        _current.reset(token)


def diagnostic(kind, *, session=None, provider=None, raw=None, **metadata):
    recorder = _current.get()
    if recorder is None:
        return
    try:
        recorder.record(kind, session=session, provider=provider, raw=raw, **metadata)
    except Exception:
        # Instrumentation cannot turn a Provider success into a product error.
        recorder.dropped += 1


class DiagnosticRecorder:
    def __init__(self):
        self.rows = []
        self.dropped = 0
        self.started = time.monotonic()
        self.generation = 0
        self.transport = {}
        self.items = {}
        self.completed = set()
        self.delta_counts = {}
        self.max_completed_rank = -1
        self.last_resolved_item = None

    def record(self, kind, *, session=None, provider=None, raw=None, **metadata):
        row = {"seq": len(self.rows), "elapsed": time.monotonic()-self.started,
               "wall_time": time.time(), "kind": kind, "generation": self.generation}
        if kind == "transport_state":
            self.transport = dict(metadata)
        row["transport"] = dict(self.transport)
        if session is not None:
            row["local"] = {
                "frame_start": session._current_audio_start_sequence,
                "frame_end": session._current_audio_end_sequence,
                "audio_start": session._current_audio_start_seconds,
                "audio_end": session.audio_end_seconds,
                "pending_seconds": session.audio_buffer_duration_seconds(),
                "meaningful": session.has_meaningful_audio_buffer(),
                "runtime_state": session.runtime_state,
            }
        if provider is not None:
            row["provider_local"] = provider.diagnostic_context()
        row.update(metadata)
        if raw is not None:
            event = {k: raw[k] for k in ("type", "event_id", "item_id", "previous_item_id", "audio_start_ms", "audio_end_ms", "content_index", "transcript_id", "commit_id") if k in raw}
            kind_raw = raw.get("type", "")
            item = raw.get("item_id")
            if kind_raw == "error" or kind_raw.endswith(".failed"):
                err = raw.get("error") or {}
                event["error"] = {k:err[k] for k in ("type", "code", "event_id", "item_id") if k in err}
            if item:
                info = self.items.setdefault(item, {})
                if kind_raw == "input_audio_buffer.speech_started":
                    info["audio_start_ms"] = raw.get("audio_start_ms")
                if kind_raw == "input_audio_buffer.speech_stopped":
                    info["audio_end_ms"] = raw.get("audio_end_ms")
                if kind_raw == "input_audio_buffer.committed":
                    info["committed_rank"] = sum("committed_rank" in i for i in self.items.values())
                    info["committed_event_id"] = raw.get("event_id")
                if kind_raw.endswith("transcription.delta"):
                    self.delta_counts[item] = self.delta_counts.get(item, 0)+1
                    event["delta_count"] = self.delta_counts[item]
                    event["delta_length"] = len(str(raw.get("delta", "")))
                if kind_raw.endswith("transcription.completed"):
                    text = raw.get("transcript")
                    event["transcript_empty"] = not isinstance(text, str) or not text.strip()
                    event["transcript_length"] = len(text) if isinstance(text, str) else None
                    event["duplicate_completion"] = item in self.completed
                    rank = info.get("committed_rank")
                    event["out_of_order_completion"] = rank < self.max_completed_rank if rank is not None else None
                    if rank is not None:
                        self.max_completed_rank = max(rank, self.max_completed_rank)
                    self.completed.add(item)
                    event["item_delta_count"] = self.delta_counts.get(item, 0)
            row["event"] = event
        if kind == "buffer_clear_before":
            item = metadata.get("item_id")
            end = self.items.get(item, {}).get("audio_end_ms")
            local_end = (row.get("local") or {}).get("audio_end")
            row["provider_item_end_ms"] = end
            row["older_item_clears_newer_audio"] = local_end*1000 > end+1 if end is not None and local_end is not None else None
            row["newer_audio_seconds"] = max(0, local_end-end/1000) if end is not None and local_end is not None else None
        if kind == "buffer_clear_after":
            self.generation += 1
            self.last_resolved_item = metadata.get("item_id")
        row["completed_item_count"] = len(self.completed)
        row["last_resolved_item"] = self.last_resolved_item
        self.rows.append(row)
