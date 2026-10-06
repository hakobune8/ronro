# Account Service v1 運用観測・一次対応（候補）

Status: **未配備の候補**。監視先・当番・応答時間・実鍵破棄の受入れは未確定。既存Pilotに適用しない。

`prototype/service_observability.py`はPostgreSQLのDB時計で集計した件数だけを返す。Session ID、owner、Transcript、Evidence、Cookie、鍵、個別エラー詳細は返さない。監視プロセスにはDBの集計読出し権限だけを与えること。現時点で公開HTTPのmetrics endpointや通知先はないため、コードがあるだけでは監視が稼働しているとは扱わない。

| Alert code | 意味・優先度の暫定判断 | 一次対応 |
| --- | --- | --- |
| `retention_deadline_breached` | 期限を過ぎてもSession行が残存。削除保証の違反疑い。最優先。 | 削除Worker、Key Registry、Jobの状態とバックアップを照合。復元不能を確認するまで「削除済み」と表示しない。事故対応担当へ即時連絡する。 |
| `retention_due_unfenced` | 期限10分前でも終了Sessionが削除待ちになっていない。Worker停止の早期警告。 | Workerの起動・期限選択を確認。未着手のまま期限を迎えさせない。 |
| `retention_deadline_missing` | 終了Sessionに期限がない。 | 終了受理記録を照合し、`created_at`から期限を推定しない。データを上書きせず修復手順を承認に回す。 |
| `deletion_retry_pending` | 鍵／DB削除が失敗し再試行待ち。 | 内容を含まない`last_error_code`とWorker稼働を確認する。Jobを手動で消さず、鍵破棄・バックアップ復元不能性の確認後に再試行。 |
| `deletion_job_stalled` | 削除Jobが5分以上残存。Worker停止・外部鍵削除の滞留の疑い。 | Jobのclaimと直近エラーコードを照合。期限超過前に担当へ連絡する。 |
| `deletion_worker_claim_expired` | Workerのclaimが期限切れ。 | Worker障害と二重起動を確認。DBのleaseによる再claimに任せ、Sessionを手動消去しない。 |
| `drain_deadline_overdue` | 終了待ちの期限超過。 | Drain supervisorと未解決Job/itemを確認。不完全なら`ended_incomplete`として欠落可能性を明示し、完全終了を偽らない。 |
| `analysis_job_failed` | Analyzer Job失敗が残存。 | queueの失敗を隠さず、会議継続・再試行・欠落の状態を区別する。Transcript本文は通常ログへ出さない。 |
| `possible_evidence_gap` | Capture不能区間が記録された。 | 当該会議の利用者表示と最終PDFの欠落注記を照合。「Evidence欠落なし」と断言しない。 |

期限到来処理は`ended_at + 7日`の**15分前**から開始する。これは再試行の余裕であり、7日以内の復元不能性の証明ではない。OpenBaoは現状、鍵削除を検証できないため成功を返さない。`deletion_retry_pending`と`retention_deadline_breached`が出続ける状態を正常運用として扱わない。

内容閲覧を伴うエラー解析は、この集計監視とは別の承認・監査経路が必要。承認者、通知先、当番、GAの合否閾値、実バックアップ復元試験が定まるまで、P6およびサービス公開の受入れは未完了。
