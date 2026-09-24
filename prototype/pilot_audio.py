"""Private, pilot-only PCM capture. Never part of Canonical Evidence/Graph.

The file is raw mono PCM16LE, 24 kHz. Metadata contains no transcript or
device identifier. No HTTP route exposes this directory.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
from pathlib import Path

from .live_audio import AudioChunk, TARGET_SAMPLE_RATE


RETENTION = dt.timedelta(days=7)
MIN_FREE_BYTES = 128 * 1024 * 1024
SESSION_ID = re.compile(r"^live-[0-9a-f]{12}$")


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _private_dir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise OSError("Pilot recording path is not a private directory")
    path.chmod(0o700)


def purge_expired(root: Path, *, now: dt.datetime | None = None, exclude_session_id: str | None = None) -> int:
    """Remove only expired, application-named recording directories."""

    now = now or _utc_now()
    if not root.exists():
        return 0
    removed = 0
    for entry in root.iterdir():
        if entry.name == exclude_session_id or not SESSION_ID.fullmatch(entry.name) or entry.is_symlink() or not entry.is_dir():
            continue
        metadata = entry / "metadata.json"
        try:
            value = json.loads(metadata.read_text(encoding="utf-8"))
            expires = dt.datetime.fromisoformat(value["expires_at"])
            if expires.tzinfo is None:
                continue
        except (OSError, ValueError, KeyError, TypeError):
            # A crash before metadata creation must not leave raw audio forever.
            expires = dt.datetime.fromtimestamp(entry.stat().st_mtime, dt.timezone.utc) + RETENTION
        if expires <= now:
            for filename in ("audio.pcm", "metadata.json", "metadata.tmp"):
                target = entry / filename
                if target.is_file() or target.is_symlink():
                    target.unlink()
            try:
                entry.rmdir()
                removed += 1
            except OSError:
                pass
    return removed


class PilotAudioRecorder:
    def __init__(self, root: Path, session_id: str) -> None:
        if not SESSION_ID.fullmatch(session_id):
            raise ValueError("Invalid pilot recording session identifier")
        _private_dir(root)
        if shutil.disk_usage(root).free < MIN_FREE_BYTES:
            raise OSError("Pilot recording storage reserve reached")
        self.directory = root / session_id
        if self.directory.exists():
            raise OSError("Pilot recording session already exists")
        self.directory.mkdir(mode=0o700)
        self._started_at = _utc_now()
        self._last_sequence = -1
        self._bytes = 0
        self._interruption_markers: list[dict[str, object]] = []
        self._closed = False
        self._file = None
        try:
            descriptor = os.open(self.directory / "audio.pcm", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            self._file = os.fdopen(descriptor, "wb", buffering=0)
            self._write_metadata("recording")
        except BaseException:
            if self._file is not None:
                self._file.close()
            raise

    def _write_metadata(self, state: str) -> None:
        now = _utc_now()
        metadata = {
            "format": "pcm_s16le",
            "sample_rate_hz": TARGET_SAMPLE_RATE,
            "channels": 1,
            "retention_days": 7,
            "consent_attestation": "all_participants_confirmed_before_start",
            "started_at": self._started_at.isoformat(),
            "ended_at": now.isoformat() if state != "recording" else None,
            "expires_at": (now + RETENTION).isoformat() if state != "recording" else (self._started_at + RETENTION).isoformat(),
            "state": state,
            "frame_count": self._last_sequence + 1,
            "bytes": self._bytes,
            "capture_interruptions": self._interruption_markers,
        }
        target = self.directory / "metadata.json"
        temporary = self.directory / "metadata.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(metadata, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(target)

    def append(self, chunk: AudioChunk) -> None:
        if self._closed or self._file is None:
            raise OSError("Pilot recording is closed")
        if chunk.sequence != self._last_sequence + 1:
            raise OSError("Pilot recording frame sequence gap")
        if shutil.disk_usage(self.directory).free < MIN_FREE_BYTES + len(chunk.pcm16le):
            raise OSError("Pilot recording storage reserve reached")
        written = self._file.write(chunk.pcm16le)
        if written != len(chunk.pcm16le):
            raise OSError("Pilot recording write incomplete")
        self._bytes += written
        self._last_sequence = chunk.sequence

    def note_interruption(self, code: str) -> None:
        """Mark a possible gap without fabricating its audio or duration."""
        self._interruption_markers.append({
            "at": _utc_now().isoformat(),
            "after_frame_sequence": self._last_sequence,
            "code": code,
            "gap_duration": "unknown",
        })

    def close(self, *, state: str = "ended") -> None:
        if self._closed:
            return
        self._closed = True
        failure: OSError | None = None
        if self._file is not None:
            try:
                self._file.flush()
                os.fsync(self._file.fileno())
            except OSError as exc:
                failure = exc
            finally:
                self._file.close()
        self._write_metadata("incomplete" if failure is not None else state)
        if failure is not None:
            raise failure

    @property
    def bytes_written(self) -> int:
        return self._bytes
