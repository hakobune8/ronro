# Fixture 010: Invalid Events

## Purpose

Materializerが不正Eventを受け取ったとき、Eventを適用せずGraph Stateを変更しないことを確認する。

## Base Input

events.jsonは、session_created、session_started、topic Node生成までのRevision 3のValid Streamである。invalid-cases.jsonの各Caseは、このBase Streamの後に適用するSuffixとして定義する。

## Invalid Cases

| Case | Expected result | Error code |
| --- | --- | --- |
| duplicate event_id | REJECT_EVENT / STATE_UNCHANGED | duplicate_event_id |
| sequence gap | REJECT_EVENT / STATE_UNCHANGED | sequence_gap |
| out-of-order sequence | REJECT_EVENT / STATE_UNCHANGED | duplicate_sequence |
| expected_revision mismatch | REJECT_EVENT / STATE_UNCHANGED | revision_mismatch |
| missing node | REJECT_EVENT / STATE_UNCHANGED | missing_reference |
| invalid decision transition | REJECT_EVENT / STATE_UNCHANGED | invalid_transition |
| relation referencing missing node | REJECT_EVENT / STATE_UNCHANGED | missing_reference |
| invalid node type | SCHEMA_REJECT | schema_invalid |
| invalid relation combination | REJECT_EVENT / STATE_UNCHANGED | unsupported_relation |

## Requirement / RFC Decision

- RFC-0001: Pure Materializer Contract
- RFC-0002: Retry / Reprocess時もInvalid EventをGraphへ反映しない
- Event Catalog: Invalid EventでRevisionを増やさない

## Assumptions

JSON Schemaの構造エラーとMaterializerの意味エラーを分離する。invalid node typeはSchemaで拒否し、既存Enum内だが意味的に不正なRelationやState TransitionはMaterializerで拒否する。
