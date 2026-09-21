# Fixture 013 — Open Item Lifecycle

## Purpose

Open ItemをCanonical Nodeの`status`だけで`active`（open）/`resolved`へ遷移させ、`reopen_open_item`で再び`active`へ戻せることを検証する。Resolve / ReopenはHuman EventとしてEvent Streamに残り、Replayして同じFinal Graphを再現できなければならない。

## Input Discussion

1. 「Visual Artifactの扱いを確認します」
2. 「Visual生成の完了条件は何ですか？」

## Expected Events

- TopicとOpen ItemをAnalyzer Eventで作成する。
- `resolve_open_item`: active → resolved
- `reopen_open_item`: resolved → active
- `resolve_open_item`: active → resolved

AnalyzerがOpen Itemを自動Resolvedへ変更するEventは含めない。Human CommandがCanonical Eventを生成する前提である。

## Expected Graph Behavior

- Open Item Node IDは全Lifecycleで維持する。
- 最終状態は`resolved`。
- Evidence、Creation Event、Resolve / Reopen Eventは保持する。
- Resolved ItemはPresentation Projectionの通常Visible Cardから外せるが、Canonical Graphから削除しない。
- Graph Revisionは有効Eventごとに9まで進む。

## Requirement / RFC Decision

- Architecture Baseline: Event Stream = History、Graph = Current State
- RFC-0001 / RFC-0003: Human CorrectionはEventとしてReplay可能
- RFC-0005: Open / Unresolved ItemをMinutesの構造化Stateとして扱う
- Open Item Lifecycle Amendment: active（open）/ resolved、Human-only Resolve / Reopen

## Assumptions

- `active`がOpen ItemのCanonicalなOpen状態である。
- Resolve / ReopenにTranscript Evidenceは必須ではないため、Human Eventの`source_evidence_ids`は空配列を許可する。
- Duplicate / Similar Itemの統合やParkingはこのFixtureの責務ではない。
