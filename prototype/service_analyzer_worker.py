"""One durable Analyzer Job execution for the isolated Account Service path.

The provider call runs outside the database transaction. Only an accepted,
schema-valid Event batch is committed with its Job. A process crash leaves a
leased Job for recovery; it cannot create a second accepted Event batch.
"""

from __future__ import annotations

from typing import Any

from .analyzer import CandidateEvent
from .display_labels import record_hint
from .service_errors import ServiceStoreError


class ServiceAnalyzerWorker:
    def __init__(self, store: Any, analyzer: Any) -> None:
        self.store = store
        self.analyzer = analyzer

    def process_one(self, *, session_id: str | None = None) -> dict[str, Any] | None:
        claim = self.store.claim_job(session_id=session_id)
        if claim is None:
            return None
        try:
            return self._process_claim(claim)
        except Exception as exc:
            # Persist only a stable error code; exception messages and Analyzer
            # traces may contain meeting content. A lost worker process instead
            # leaves the lease to expire and be reclaimed.
            code = getattr(exc, "code", "analyzer_worker_error")
            try:
                self.store.fail_job(
                    claim["session_id"], claim["job_id"], attempt=claim["attempt"],
                    error={"code": code if isinstance(code, str) else "analyzer_worker_error"},
                )
            except ServiceStoreError as mark_error:
                if mark_error.code not in {"stale_claim", "session_closed"}:
                    raise
            raise

    def _process_claim(self, claim: dict[str, Any]) -> dict[str, Any]:
        sid = claim["session_id"]
        before = self.store.replay(sid)
        if before.state["graph"]["revision"] != claim["start_revision"]:
            raise ServiceStoreError("revision_mismatch", "Graph changed before Analyzer began")
        utterances = [
            utterance for utterance in before.state["utterances"]
            if claim["evidence_id"] in utterance["evidence_ids"]
        ]
        if len(utterances) != 1:
            raise ServiceStoreError("job_input_invalid", "Job must resolve to one Utterance")
        candidates = self.analyzer.analyze(
            utterances[0], before.state["graph"], before.events,
        )
        trace = getattr(self.analyzer, "last_trace", None)
        if isinstance(trace, dict) and (trace.get("validation_error") or trace.get("critical_errors")):
            raise ServiceStoreError("analyzer_output_invalid", "Analyzer reported invalid output")
        staged = before
        events: list[dict[str, Any]] = []
        accepted_candidates: list[dict[str, Any]] = []
        delta: dict[str, Any] = {}
        for candidate in candidates:
            if not isinstance(candidate, CandidateEvent):
                raise ServiceStoreError("analyzer_output_invalid", "Analyzer returned an invalid candidate")
            if candidate.session_id != sid or claim["evidence_id"] not in candidate.source_evidence_ids:
                raise ServiceStoreError("analyzer_output_invalid", "Candidate belongs to another Job")
            event = candidate.to_event(staged.state["graph"]["last_event_sequence"] + 1)
            staged = self.store.runner.apply_event(staged, event)
            record_hint(staged, candidate)
            node_id = f"node:{sid}:{candidate.event_id}"
            if node_id in staged.presentation and node_id not in before.presentation:
                delta[node_id] = staged.presentation[node_id]
            events.append(event)
            accepted_candidates.append({
                "event_id": candidate.event_id,
                "event_type": candidate.event_type,
                "payload": candidate.payload,
                "presentation": candidate.presentation,
            })
        result = self.store.accept_job_result(
            sid, claim["job_id"], attempt=claim["attempt"],
            start_revision=claim["start_revision"],
            accepted_output={
                "contract_version": claim["contract_version"],
                "candidates": accepted_candidates,
            },
            events=events,
            presentation_hints=delta,
        )
        return {
            "session_id": sid,
            "job_id": claim["job_id"],
            "event_count": len(events),
            "graph_revision": result.state["graph"]["revision"],
        }
