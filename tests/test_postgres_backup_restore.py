"""Optional synthetic PostgreSQL backup/restore proof for P1."""

from __future__ import annotations

import os
import subprocess
import unittest
import uuid
from pathlib import Path

import psycopg
from psycopg.conninfo import make_conninfo

from prototype.postgres_service_store import PostgresServiceStore
from prototype.schema import SchemaValidator
from prototype.service_crypto import InMemoryTestKeyRegistry, ServiceCryptoError
from tests.test_service_store import event, final


ROOT = Path(__file__).resolve().parents[1]
TEST_DSN = os.getenv("RONRO_TEST_POSTGRES_DSN")
TEST_CONTAINER = os.getenv("RONRO_TEST_POSTGRES_CONTAINER")


def _docker(*args: str, input_bytes: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["docker", "exec"] + (["-i"] if input_bytes is not None else []) + [TEST_CONTAINER, *args],
        input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=True, timeout=60,
    )
    return result.stdout


@unittest.skipUnless(TEST_DSN and TEST_CONTAINER, "Local synthetic backup test is not configured")
class PostgresBackupRestoreTests(unittest.TestCase):
    def test_event_replay_survives_content_backup_but_not_key_deletion(self):
        session_id = f"test-backup-{uuid.uuid4()}"
        restored_db = f"ronro_restore_{uuid.uuid4().hex[:12]}"
        registry = InMemoryTestKeyRegistry()
        validator = SchemaValidator(ROOT / "schemas")
        source = PostgresServiceStore(TEST_DSN, validator, registry, allow_test_key_registry=True)
        source.migrate()
        source.create_session(session_id, "synthetic-backup-owner")
        try:
            source.append_events(session_id, [
                event(session_id, 1, "session_created", {"title": "合成復元会議", "goal": "検討"}),
                event(session_id, 2, "session_started", {}),
            ])
            evidence, utterance = final(session_id, 1)
            source.accept_final(
                session_id, evidence, utterance, job_id="backup-job",
                contract_version="v1", provider_item_id="backup-provider",
            )
            claim = source.claim_job(session_id=session_id, now=100)
            source.accept_job_result(
                session_id, "backup-job", attempt=claim["attempt"],
                start_revision=claim["start_revision"], accepted_output={"test": "合成"},
                events=[event(
                    session_id, 3, "node_detected", {"node_type": "idea", "label": "復元案"},
                    actor="analyzer", evidence_ids=[evidence["id"]],
                )],
            )
            expected = source.replay(session_id).state
            dump = _docker("pg_dump", "-U", "postgres", "-Fc", "-d", "ronro_test")
            _docker("createdb", "-U", "postgres", restored_db)
            try:
                _docker("pg_restore", "-U", "postgres", "-d", restored_db,
                        "--no-owner", input_bytes=dump)
                restored = PostgresServiceStore(
                    make_conninfo(TEST_DSN, dbname=restored_db), validator,
                    registry, allow_test_key_registry=True,
                )
                self.assertEqual(restored.replay(session_id).state, expected)
                self.assertEqual(restored.owner_user_id(session_id), "synthetic-backup-owner")
                registry.delete_key(session_id)
                with self.assertRaisesRegex(ServiceCryptoError, "key_unavailable"):
                    restored.replay(session_id)
            finally:
                _docker("dropdb", "-U", "postgres", "--force", restored_db)
        finally:
            # Only synthetic rows are targeted; no real meeting data is used.
            with psycopg.connect(TEST_DSN) as connection:
                connection.execute("DELETE FROM service_session WHERE session_id = %s", (session_id,))


if __name__ == "__main__":
    unittest.main()
