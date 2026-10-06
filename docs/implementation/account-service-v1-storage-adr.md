# Account Service v1 — Content Store ADR (P1)

Status: Content-store choice accepted for implementation; Key Registry deployment and 7-day irrecoverability remain unverified.

## Decision

Use PostgreSQL as the transactional content database for Account Service v1. Keep it separate from the current single-Session Pilot runtime. The additive migration is [`0001_account_service.sql`](../../migrations/0001_account_service.sql); Service routes are not enabled by applying it.

The service writes each accepted Final together with its Analyzer Job in one transaction. A Worker claims a Job with a lease and PostgreSQL row locking; acceptance of output, ordered Canonical Events, Graph revision/checkpoint, and Job completion is another Session-serialized transaction. A stale claim or Graph revision cannot append Events. `session_ended` and frozen final revision are accepted together; later Worker output cannot mutate the meeting. Events remain the replay source of truth; a checkpoint is a rebuildable cache.

Meeting content columns use per-Session AES-256-GCM with authenticated context consisting of Session, record kind, and record identity. This includes owner identity, Evidence/Utterance text, Canonical Event payload, Analyzer output, and checkpoint. A Provider item ID is stored as a keyed digest, not raw text. Keys are never stored in the content database. Session IDs and processing state remain plaintext operational metadata; their re-identification risk must be reviewed with logs and backups before release.

The production API must generate opaque Session/Event/Evidence/Job identifiers; it must not accept participant names or free text as indexed identifiers. The database migration is applied by a separate privileged identity. The live application identity should have only the DML permissions needed for its Session-scoped operations, not routine DDL access.

The `SessionKeyRegistry` protocol is a separate boundary. `InMemoryTestKeyRegistry` exists only for synthetic tests and is rejected unless the PostgreSQL adapter is explicitly placed in test mode. Before any real meeting uses this adapter, implement a durable, separately operated Key Registry and prove both key availability under node loss and key destruction within seven days including its own copies. A content-DB backup alone is neither recovery proof nor deletion proof.

## Current evidence and remaining work

- Local PostgreSQL integration uses synthetic data only: encrypted rows, reopen/replay, duplicate Final, atomic rollback, Session isolation, stale revision, failed-Job retry, incomplete end, and checkpoint rebuild. A content-DB dump restored into a separate database replayed the same Events while the test key was available; after deleting that key, the restored content was unreadable. This does **not** prove a durable Key Registry or the seven-day production deadline.
- This is not yet wired to Live STT, Analyzer Worker, authenticated HTTP/WSS, PDF, or deletion. The current Pilot remains on its existing path.
- P1 still requires a durable Key Registry integration, live ingest/Worker adapter, migration/version procedure, backup restore with keys, and performance testing. P2–P6 remain separate gates.
- In a two-system create (Key Registry then content DB), an uncertain DB commit must not trigger immediate key deletion. Orphan-key reconciliation is required before service exposure.
