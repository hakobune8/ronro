"""Synthetic supervision tests; no Provider, user, or real meeting data."""

from __future__ import annotations

import threading
import unittest
from unittest.mock import Mock

from prototype.service_worker_supervisor import ServiceWorkerSupervisor
from prototype.service_errors import ServiceStoreError


class ServiceWorkerSupervisorTests(unittest.TestCase):
    def test_failed_analyzer_does_not_stop_other_workers_or_log_content(self):
        reached_retry = threading.Event()
        calls = 0

        def analyzer_process():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("private synthetic transcript must never be logged")
            reached_retry.set()
            return None

        analyzer = Mock(process_one=analyzer_process)
        drain = Mock(process_one=Mock(return_value=None))
        deletion = Mock(process_one=Mock(return_value=None))
        maintenance = Mock(return_value=(0, 0))
        supervisor = ServiceWorkerSupervisor(
            analyzer_workers=[analyzer], drain_supervisor=drain,
            deletion_worker=deletion, auth_maintenance=maintenance,
            analyzer_poll_seconds=0.1, drain_poll_seconds=0.1,
            deletion_poll_seconds=0.1, maintenance_poll_seconds=0.1,
        )
        with self.assertLogs("prototype.service_worker_supervisor", level="WARNING") as logs:
            supervisor.start()
            try:
                self.assertTrue(reached_retry.wait(timeout=2))
                self.assertTrue(supervisor.stop(timeout_seconds=2))
            finally:
                supervisor.stop(timeout_seconds=2)
        snapshot = supervisor.snapshot()
        self.assertGreaterEqual(snapshot["analyzer_0"]["attempts"], 2)
        self.assertEqual(snapshot["analyzer_0"]["failures"], 1)
        self.assertGreater(drain.process_one.call_count, 0)
        self.assertGreater(deletion.process_one.call_count, 0)
        self.assertGreater(maintenance.call_count, 0)
        self.assertFalse(any(part["alive"] for part in snapshot.values()))
        self.assertIn("component=analyzer_0 code=worker_failure", logs.output[0])
        self.assertNotIn("private synthetic transcript", str(logs.output))

    def test_stop_reports_in_flight_worker_instead_of_claiming_stopped(self):
        entered = threading.Event()
        release = threading.Event()

        def analyzer_process():
            entered.set()
            release.wait(timeout=3)
            return None

        supervisor = ServiceWorkerSupervisor(
            analyzer_workers=[Mock(process_one=analyzer_process)],
            drain_supervisor=Mock(process_one=Mock(return_value=None)),
            deletion_worker=Mock(process_one=Mock(return_value=None)),
            analyzer_poll_seconds=0.1, drain_poll_seconds=0.1,
            deletion_poll_seconds=0.1,
        )
        supervisor.start()
        try:
            self.assertTrue(entered.wait(timeout=2))
            self.assertFalse(supervisor.stop(timeout_seconds=0.01))
        finally:
            release.set()
            self.assertTrue(supervisor.stop(timeout_seconds=2))

    def test_invalid_or_duplicate_start_is_rejected(self):
        with self.assertRaises(ValueError):
            ServiceWorkerSupervisor(
                analyzer_workers=[], drain_supervisor=Mock(), deletion_worker=Mock(),
            )
        supervisor = ServiceWorkerSupervisor(
            analyzer_workers=[Mock(process_one=Mock(return_value=None))],
            drain_supervisor=Mock(process_one=Mock(return_value=None)),
            deletion_worker=Mock(process_one=Mock(return_value=None)),
        )
        supervisor.start()
        try:
            with self.assertRaises(RuntimeError):
                supervisor.start()
        finally:
            self.assertTrue(supervisor.stop(timeout_seconds=2))

    def test_untrusted_exception_code_is_not_logged(self):
        class UntrustedError(RuntimeError):
            code = "private_meeting_title"

        self.assertEqual(ServiceWorkerSupervisor._error_code(UntrustedError()),
                         "worker_failure")
        self.assertEqual(ServiceWorkerSupervisor._error_code(
            ServiceStoreError("session_closed", "Synthetic content")),
            "session_closed")

    def test_composition_uses_existing_durable_worker_boundaries(self):
        store = Mock()
        store.claim_job.return_value = None
        store.supervise_next_end_intent.return_value = None
        store.supervise_next_drain.return_value = None
        store.claim_deletion_job.return_value = None
        store.begin_due_deletion.return_value = None
        identity = Mock()
        identity.purge_expired_auth_records.return_value = (0, 0)
        supervisor = ServiceWorkerSupervisor.from_service_components(
            store=store, identity=identity, analyzers=[Mock()],
        )
        supervisor.start()
        try:
            self.assertEqual(set(supervisor.snapshot()), {
                "analyzer_0", "drain", "deletion", "auth_maintenance",
            })
        finally:
            self.assertTrue(supervisor.stop(timeout_seconds=2))
