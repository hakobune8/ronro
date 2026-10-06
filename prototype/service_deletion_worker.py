"""Fail-closed Account Service deletion worker candidate.

It fences access in PostgreSQL before touching the external Session key.
OpenBao currently refuses to claim irreversible deletion, so production
jobs remain retryable until its infrastructure deletion proof exists.
"""

from __future__ import annotations

import threading
import re
import logging
from typing import Any

from .service_crypto import ServiceCryptoError
from .service_errors import ServiceStoreError


LOGGER = logging.getLogger(__name__)


class ServiceDeletionWorker:
    def __init__(self, store: Any, *, poll_seconds: float = 10.0) -> None:
        if not 0.1 <= poll_seconds <= 300:
            raise ValueError("Deletion polling interval is invalid")
        self.store = store
        self.poll_seconds = poll_seconds

    def process_one(self) -> dict[str, Any] | None:
        self.store.begin_due_deletion()
        claim = self.store.claim_deletion_job()
        if claim is None:
            return None
        session_id = claim["session_id"]
        try:
            self.store.key_registry.delete_key(session_id)
            self.store.complete_deletion_job(
                session_id, claim_token=claim["claim_token"],
            )
        except Exception as exc:
            code = getattr(exc, "code", "deletion_worker_error")
            if not isinstance(code, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code) is None:
                code = "deletion_worker_error"
            try:
                self.store.fail_deletion_job(
                    session_id, claim_token=claim["claim_token"],
                    error_code=code,
                )
            except ServiceStoreError as mark_error:
                # An uncertain final commit may already have removed the Job.
                # Do not pretend success or recreate content; reconcile later.
                if mark_error.code not in {"stale_deletion_claim", "session_not_found"}:
                    raise
            raise ServiceCryptoError(code) from None
        return {"session_id": session_id, "state": "purged"}

    def run_until_stopped(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                outcome = self.process_one()
            except (ServiceCryptoError, ServiceStoreError) as exc:
                # Only stable error codes enter logs; neither IDs nor content do.
                LOGGER.warning("Service deletion retry pending: %s", exc.code)
                stop.wait(self.poll_seconds)
            else:
                if outcome is not None:
                    continue
                stop.wait(self.poll_seconds)
