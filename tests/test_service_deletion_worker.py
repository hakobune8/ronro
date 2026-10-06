"""Deletion supervisor behavior without meeting content or external keys."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from prototype.service_crypto import ServiceCryptoError
from prototype.service_deletion_worker import ServiceDeletionWorker


class _TwoPollStop:
    def __init__(self) -> None:
        self.polls = 0
        self.waits: list[float] = []

    def is_set(self) -> bool:
        self.polls += 1
        return self.polls > 2

    def wait(self, timeout: float) -> None:
        self.waits.append(timeout)


class ServiceDeletionWorkerTests(unittest.TestCase):
    def test_expected_key_failure_does_not_stop_polling(self):
        worker = ServiceDeletionWorker(Mock(), poll_seconds=0.1)
        worker.process_one = Mock(side_effect=[
            ServiceCryptoError("key_deletion_unverified"), None,
        ])
        stop = _TwoPollStop()
        with self.assertLogs("prototype.service_deletion_worker", level="WARNING") as logs:
            worker.run_until_stopped(stop)
        self.assertEqual(worker.process_one.call_count, 2)
        self.assertEqual(stop.waits, [0.1, 0.1])
        self.assertIn("key_deletion_unverified", logs.output[0])
