# RONRO Account Service v1 — 実装計画

| 項目 | 内容 |
| --- | --- |
| Status | 開発計画。実装・配備・GAの承認ではない |
| 開発ブランチ | `feat/account-service-v1` |
| 入力 | [RFC-0007](../rfc/0007-service-readiness-improvement-inventory.md)、[RFC-0008](../rfc/0008-account-based-service-architecture.md)、[実装設計案](account-service-v1-design.md) |
| 原則 | 現行Pilotの動作を保ち、Service経路を段階的に追加。Canonical Event/Graphの意味は変更しない |

## 1. スコープと設計照合

個人アカウントで会議を起動し、2～8名・同時4会議・約2時間を検証する。時間超過だけでは終了させない。休憩・再開、障害後の継続、会議後の閲覧専用CanvasとPDF、RONRO管理下の会議データを終了から7日以内に復元不能にする仕組みを実装対象とする。出席者への共有は起動ユーザーが出力したPDFに限る。本運用の生音声保存、会議後の訂正、受取人アカウント、公開リンク、課金・組織共同所有は対象外。

実装前照合で、既存設計の状態表に欠けていた`resuming`の過渡状態と、不完全終了時の最終revision固定後に遅延JobがGraphを変えない条件を[実装設計案](account-service-v1-design.md)へ追記した。これ以外に、開発着手を一律に止める未定義の契約は確認していない。ただし次の採用判断・実証が済むまで、公開サービスの完成や7日削除保証を宣言しない。

## 2. 先に固定する境界と判断ゲート

| 判断・証拠 | 決める時点 | 未達時の扱い |
| --- | --- | --- |
| OIDC issuer/subject、Web Session、表示専用資格、運用主体のADR | 既存ZITADELをRONRO専用Clientで利用する方針は[Identity ADR](account-service-v1-identity-adr.md)に固定。実Client登録・接続確認はP2中 | ローカルの偽ログインを本番へ出さない。 |
| DB・オブジェクト保存・Key Registry、平文メタデータ／ログ一覧、鍵の復旧と7日以内破棄のADR | 永続化の本格実装前に候補を選び、PDF/削除の受入れ前に復元試験 | 復元不能性が証明できなければGA不可。Providerや配布済みPDFに同じ7日期限を約束しない。 |
| HTTP/WSSのSession routing、旧世代fencing、更新・rollback手順 | 多Session/障害復旧の受入れ前 | 進行中会議を止める`Recreate`を通常更新として承認しない。 |
| Provider側の実契約・組織/Project設定、出席者説明・同意、限定的なエラー解析の承認者 | 実利用前 | Pilotの同意/録音条件を本運用へ流用しない。 |
| 品質SLO、問い合わせ/事故連絡の担当、利用者評価の合否値 | GA判定前 | 数値未定でも安全違反は許容しない。 |

実装中の参照環境では採用候補を使って検証できるが、ADRと実証が終わる前に本番要件を満たしたと扱わない。7日以内の復元不能化は会議本文だけでなく、owner対応、ログ、キャッシュ、WAL/バックアップ、鍵の復元用コピーまで含める。鍵を早く失えば可用性も失うため、複製故障と破棄の両方を試験する。

## 3. 段階的な実装とコミット境界

各段階を独立したレビュー可能なコミット群/PRにする。順序依存がある作業は前段の受入れ後に統合し、現行Pilotの経路をService経路へ暗黙に切り替えない。各段階で既存テスト、追加した契約試験、同じEvent列のreplay一致を必須とする。

| 段階 | 実装する境界 | 合格条件 |
| --- | --- | --- |
| P0 基準固定 | 既存Pilotのテスト/挙動、Canonical Schema・Event/Projection replay、評価APIの経路を記録。認証・保存・鍵・routing ADRの候補を作る。 | 既存テストGreen。意図しないPublic APIと平文保存先の棚卸しができる。 |
| P1 永続正本 | `store`のSession別永続アダプタ、migration、Evidence＋Job原子受理、Analyzer出力＋Event＋revision＋Job原子受理、claim/再試行、checkpoint再生。 | Crash前後/重複Final/Job、古いHuman revision、別Session混入、バックアップ復元後のreplayを試験。メモリFIFOを正本にしない。 |
| P2 本人確認/認可 | OIDC、owner紐付け、API/WSSのSession権限、短命なShared View表示資格、CSRF/Origin、評価API分離。 | 他人のSession/Command/PDF/音声を拒否し存否も漏らさない。失効・退会・別Tab・別表示端末を試験。 |
| P3 会議継続 | Capture状態、pause→resuming→listening、接続generation、gap記録、Provider item相関、復旧、Drain、固定`final_revision`。 | 休憩はgapにしない。BGM/長い無発話で自動終了しない。失敗時も会議継続と欠落警告を分ける。遅延Final/Jobは終了後のGraphを変えない。 |
| P4 並行実行 | 新規SessionのAdmission、Session内順序とSession間の公平なWorker、backlog/費用の計測、配備更新/rollback。 | 4会議×2時間超、2～8人相当の音響条件、5件目拒否でも既存4件を維持。障害/更新で復旧可能範囲とgapを確認。 |
| P5 会議後成果物/削除 | 固定revisionのFinal Canvas→印刷用HTML→PDF、欠落注記、Session別鍵、7日満了/明示削除/退会、全保存先の削除照合。 | `ended`/`ended_incomplete`を区別。Graph破損時はPDF拒否。PDF越権/再生成/長いNode。期限後のバックアップ＋Key Registry復元試験で会議を再構成できない。 |
| P6 運用/受入れ | 通常は内容なしの監視・Alert/Runbook、限定エラー解析の承認監査、脅威レビュー、利用者説明、実機/負荷/Pilot評価。 | 危険な自動確定/Owner/Due捏造/Graph破損/静かなEvidence欠落なし。3–5m Shared ViewとPDFをHuman評価。担当とGA合否を確定。 |

P1の保存方式検証とP5の鍵/削除試験は一つの設計依存として並行で準備する。P2が終わるまで複数ユーザー向け経路を公開しない。P1が終わるまでPod喪失からの回復を約束しない。P5が終わるまで「会議後PDFを預かるサービス」と案内しない。P6の監視・脅威テストは最後に一括実施せず各段階へ追加する。

## 4. 横断的な受入れシナリオ

1. 一人のownerで開始→論点/Relation訂正→休憩→再開→終了Drain→同じrevisionのPDF→7日削除。終了後にGraphが変わらない。
2. 途中でBrowser/Pod/Provider/Workerを個別に落とし、復帰、再送、旧generationの遅延イベントを確認。未Final音声の復元不能はgapとして残し、黙って完全終了にしない。
3. `ended_incomplete`では実測した可能性のある時間帯、または範囲不明をPDFへ記載。旧Jobが後着してもPDFの中身を変更しない。
4. 別アカウント、失効した表示資格、削除済みSession、評価経路、WSS再接続で越権できない。
5. 4会議並行/約2時間超の継続中に1会議が遅れても他会議はDrainでき、新規受付停止が既存Sessionを終了させない。
6. Session削除と退会後、現用コピー/キャッシュ/ログ/バックアップ/鍵を照合し復元不能を証明する。配布済みPDFとProvider保持は別扱いと説明する。

## 5. 配備・移行・ロールバック

初期実装は候補環境の新Service経路に閉じ、現行Pilotを自動移行・上書きしない。旧データのowner紐付けは本人・同意・7日期限を個別確認するまで実施しない。DB migrationは追加→併用→旧経路停止の順とし、旧版が読めないEvent/Analyzer出力/Projectionを出す前に互換性を検証する。新規Sessionの割当てと進行中Sessionの移管を分ける。rollback不能なmigrationや鍵破棄後の復元を前提にした手順を作らない。

最初の計画コミットは実装計画の記録だけとした。後続コミットでも配備、Pilot切替、GA宣言は行わない。製品コード変更は段階ごとにレビューする。

## 6. 実装進捗（候補ブランチ）

| 段階 | 現在の進捗 | 未達の受入れ条件 |
| --- | --- | --- |
| P0 | 基準固定済み。 | なし。 |
| P1 | 暗号化PostgreSQL Store、versioned migration、原子受理・replay、Final相関、lease付きWorkerを合成データで検証。 | 永続Key Registry、認証済みLive経路、監督付きWorker、配備資格・復元・性能実証。 |
| P2 | 所有者照合とSession限定・短命・取消可能なShared View表示資格をDB境界で検証。既存ZITADELの専用Client採用をHuman承認・ADR化。Code + S256 PKCE、専用Secretによる`client_secret_basic`候補、合成RS256 ID Tokenを検証。同一ブラウザ結合・一回限り認可試行、HMAC化主体/Session、複数Tabで使えるCSRF、失効可能なWeb Session、会議ownerのread/mutate/WSS境界をPostgreSQLで検証。分離したloopback HTTP候補でログイン→Callback→Session→Logoutと、ownerのSession/Canvas読出し・表示資格のCanvas限定読出しを合成データで試験。 | RONRO専用Client登録と実認証、永続identity keyとその復旧/ローテーション、会議作成/変更/音声WSS route接続と継続中の失効反映、退会、評価API隔離、別端末/実IdP統合試験。新しい候補は公開経路に未接続。 |
| P3 | Service Captureの永続状態、操作Key/CAS、接続generation、休憩区間と取込み不能区間の区別、フレーム受理台帳・連番/時刻断絶検知、終了時のCapture fenceを合成データで検証。Provider item別のcommit/completion/Final照合、逆順完了、未知範囲・空完了による完全Drain拒否を合成データで検証。 | 実WSS/Providerとの接続、Provider appendの受領証明とlocal frame範囲の確定、未知範囲の欠落判定、Pod/Provider障害復旧とDrainのEnd-to-End。 |
| P4 | Session間の公平Job claimと、PostgreSQL advisory lockによる原子的な新規Session Admissionを合成データで検証。 | 4会議×2時間超、実運用での容量計測、配備更新・rollback。 |
| P5 | Session別暗号化の基礎、終了受理時の`ended_at`と7日後`expires_at`の原子記録、期限欠落Sessionの検出を合成データで検証。所有者照合済み固定revisionの読出し、同じCanvas座標に基づく印刷用概要とCanonical詳細のPDFを合成データで生成・描画検証。 | 認証済みHTTP配信、非公開PDF保存、所有者削除／退会、期限到来処理、鍵破棄、全保存先照合、バックアップ復元不能性。PDF生成・期限記録だけではサービス公開や削除を保証しない。 |
| P6 | 各段階の安全テストを継続。 | 監視/Alert/Runbook、承認監査、脅威レビュー、Human/負荷/Pilot受入れ。 |

この表は実装済み範囲と未達ゲートを分けるためのもの。未達の段階を完了と解釈しない。
