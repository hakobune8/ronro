# Account Service v1 — P0 基準と変更境界

Status: P0 baseline recorded. This does not approve a production service.

## 基準

- Branch: `feat/account-service-v1`。起点: `9e1673e`（計画文書のみ）。
- 既存テスト: `.venv/bin/python -m unittest discover -v`、310 tests、OK（2026-10-06）。Sandbox内のlocalhost bind制限で4件が一度失敗したため、localhost bind可能な実行環境で全件を再実行した。製品の失敗とは分類しない。
- Canonical契約: `schemas/`、`prototype/store.py`、`prototype/materializer.py`、`prototype/replay.py`。Event sequence、Graph revision、Human `expected_revision`は保持する。
- 現行Pilotの正本: `prototype/live_session.py`と`prototype/live_queue.py`内の単一Session／メモリ状態。Pod再起動を跨ぐ継続や4会議同時利用の正本ではない。
- 現行HTTP: `prototype/server.py`の`/api/live`、`/live`、`/api/fixtures`等はサービス認証を持たない。`controller_id`は同一Pilot内の操作競合防止であり本人確認ではない。
- 生音声: 現行Pilot録音は同意付き評価用の別経路。本運用のService経路には持ち込まない。

## P0 境界監査

| 領域 | 現状 | Service側の禁止事項／次段階 |
| --- | --- | --- |
| Canonical Event/Graph | Event StoreがSession順序を検査。MaterializerはEvent列から再生。 | Service都合のpause、owner、PDF、削除をCanonical意味に混ぜない。P1で永続アダプタを作る。 |
| Evidence/Queue | FinalとQueueはプロセスメモリ。Analyzer Workerは単一。 | QueueをPod間共有可能と扱わない。P1でEvidenceとJobを同時に耐久受理する。 |
| Capture/STT | Provider item相関と再接続のPilot挙動がある。 | P3までPod喪失からの完全復元を約束しない。未Final音声の欠落可能性を隠さない。 |
| HTTP/WSS | Developer/Pilot経路に認証・所有権確認がない。 | P2完了前に多ユーザー公開しない。Fixture・評価APIをService公開面から切り離す。 |
| Shared View/Final | CanvasとProjectionは存在する。会議後PDFはない。 | P5で固定revisionの同じGraphからPDFを作る。会議後に新しいLLMで再解釈しない。 |
| 保存・削除 | Pilot評価ファイルの7日削除とService削除は別。 | Service側の7日復元不能化をPilotの削除試験で代用しない。 |

## 採用ADRの順番

1. P1を実装する前に、Session境界・SQLトランザクション・migration・暗号化境界をレビューする。PostgreSQLは参照構成だが、テスト用ローカルDBを本番正本と取り違えない。
2. P2前にOIDC issuer/subject、Cookie/CSRF、表示専用資格、API/WSS認可境界を決める。現行`controller_id`を認証へ昇格しない。
3. P3/P4前にSession routingとgeneration fencing、rolling update/rollbackを決める。
4. P5前にKey Registry・PDF保存・バックアップ/WAL/ログを含む7日以内の復元不能化を試験で実証する。鍵の早期喪失による可用性も故障注入で確認する。
5. P6/実利用前にProvider側設定、出席者説明、限定エラー解析の承認者、事故連絡、GA品質基準を確定する。

P0は既存実装の安全性を保証するものではなく、各変更が壊してはならない基準を固定する段階である。次はP1の永続正本を現行Pilotから分離して実装する。
