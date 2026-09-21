"""Runtime-only Presentation render coalescing for Continuous Live sessions."""

from __future__ import annotations

import threading
import time
from typing import Any


class PresentationRenderCoalescer:
    """Coalesce ordinary Map/Status/Flow renders without delaying the Graph.

    Canonical processing calls :meth:`mark_dirty` immediately after a worker
    settles.  A browser render becomes eligible after ``interval_seconds``;
    critical state and Human Commands can call :meth:`render_now` directly.
    The class stores only presentation counters and revisions.
    """

    def __init__(self, *, initial_revision: int = 0, interval_seconds: float = 2.0) -> None:
        if interval_seconds < 0:
            raise ValueError("interval_seconds must be non-negative")
        self.interval_seconds = interval_seconds
        self._lock = threading.RLock()
        self._graph_revision = initial_revision
        self._rendered_revision = initial_revision
        self._dirty = False
        self._due_at: float | None = None
        self._render_count = 0
        self._last_render_at: float | None = None

    def mark_dirty(self, graph_revision: int, *, critical: bool = False) -> None:
        with self._lock:
            self._graph_revision = max(self._graph_revision, graph_revision)
            self._dirty = self._graph_revision > self._rendered_revision
            if not self._dirty:
                self._due_at = None
                return
            if critical or self.interval_seconds == 0:
                self._due_at = time.monotonic()
            elif self._due_at is None:
                self._due_at = time.monotonic() + self.interval_seconds

    def should_render(self) -> bool:
        with self._lock:
            return self._dirty and self._due_at is not None and time.monotonic() >= self._due_at

    def render_now(self, graph_revision: int | None = None) -> dict[str, Any]:
        with self._lock:
            if graph_revision is not None:
                self._graph_revision = max(self._graph_revision, graph_revision)
            self._rendered_revision = self._graph_revision
            self._dirty = False
            self._due_at = None
            self._render_count += 1
            self._last_render_at = time.monotonic()
            return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "graph_revision": self._graph_revision,
                "rendered_revision": self._rendered_revision,
                "render_pending": self._dirty,
                "render_count": self._render_count,
                "interval_seconds": self.interval_seconds,
            }

