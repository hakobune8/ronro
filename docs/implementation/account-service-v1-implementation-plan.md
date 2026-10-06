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
| OIDC issuer/subject、Web Session、表示専用資格、運用主体のADR | 既存ZITADELにRONRO専用PKCE Web Clientを登録。実Token交換・接続確認はP2中（[Identity ADR](account-service-v1-identity-adr.md)） | ローカルの偽ログインを本番へ出さない。 |
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
| P1 | 暗号化PostgreSQL Store、versioned migration、原子受理・replay、Final相関、lease付きWorkerを合成データで検証。OpenBao専用KV v2領域へのCAS=0作成/読出しアダプタと、HTTPS/CA/ローテーション可能なtokenファイルからの接続設定を合成HTTPで検証したが、実mount/policy接続・破棄は未実施。 | 永続Key Registryの実接続と7日削除証明、認証済みLive経路、監督付きWorker、配備資格・復元・性能実証。 |
| P2 | 所有者照合とSession限定・短命・取消可能なShared View表示資格をDB境界で検証。既存ZITADELにRONRO専用Project/Web Clientを登録し、Human確認のうえCode + S256 PKCE / `none`・固定Callbackを選択（[Identity ADR](account-service-v1-identity-adr.md)）。合成RS256 ID Token、同一ブラウザ結合・一回限り認可試行、HMAC化主体/Session、複数Tabで使えるCSRF、失効可能なWeb Session、会議ownerのread/mutate/WSS境界をPostgreSQLで検証。分離したloopback HTTP候補でログイン→Callback→Session→Logout、Owner + CSRFによる新規会議作成、ownerのSession/Canvas読出し、表示資格のCanvas限定読出しとowner限定発行・取消を合成データで試験。別portのloopback Service音声WSS候補でOwner/Cookie/Origin、別owner拒否、接続中のWeb Session失効を合成DBで試験。 | 実ZITADEL認証・Token交換、永続identity keyとその復旧/ローテーション、公開音声WSS route接続、別ディスプレイpairing/更新、退会、評価API隔離、別端末/実IdP統合試験。新しい候補は公開経路に未接続。 |
| P3 | 永続Capture状態、操作Key/CAS、接続generation、休憩と取込み不能区間、フレーム連番／時計、Provider item→Final/Evidenceの相関を合成DBで検証。loopbackのOwner限定HTTP／音声WSSで開始・休憩・再開、同一Socketの停止確認、入力中End意図→停止→Drain、停止未確認時の欠落記録と不完全終了を合成検証。DB接続leaseで別Gateway競合・旧世代をフェンス。DB期限と公平選択を持つDrain Supervisor候補は、Job/item解決後の固定revisionと期限時の部分終了を合成検証。 | 実Browser UIの終了操作と実ProviderのEnd-to-End、Supervisorの配備／監視、Provider受領の証明、実複数Pod配置・Pod/Provider障害復旧、4会議での継続性。Gatewayはloopback限定で配備可能な完成版ではない。 |
| P4 | Session間の公平Job claimと、PostgreSQL advisory lockによる原子的な新規Session Admissionを合成データで検証。 | 4会議×2時間超、実運用での容量計測、配備更新・rollback。 |
| P5 | Session別暗号化の基礎、終了受理時の`ended_at`と7日後`expires_at`の原子記録、期限欠落Sessionの検出を合成データで検証。所有者照合済み固定revisionの読出し、同じCanvas座標に基づく印刷用概要とCanonical詳細のPDFを合成データで生成・描画検証。loopback専用HTTP候補で終了済みSessionのOwner限定PDF取得を試験（no-store、表示資格では不可）。所有者削除要求／期限到来を先にアクセス遮断するDB Job、合成鍵Registryでの鍵破棄確認後のDB cascade削除、失敗時の再試行を追加。 | 実認証済み公開HTTP配信、非公開PDF保存、退会連動、OpenBao実環境での鍵破棄とバックアップ復元不能性、全保存先照合、7日以内の履行実証。OpenBao側のmount/policy/snapshot運用変更はこの段階のRONRO側接続実装に含めない。OpenBaoアダプタは安全に鍵破棄を証明できないため削除成功を返さず、Jobは遮断状態で再試行する。PDF生成・期限記録・合成削除試験だけではサービス公開や7日削除を保証しない。 |
| P6 | 各段階の安全テストを継続。 | 監視/Alert/Runbook、承認監査、脅威レビュー、Human/負荷/Pilot受入れ。 |

P2/P5の退会候補では、本人認証・Origin/CSRF確認後、アカウント資格の失効と所有Sessionのアクセス遮断／削除Job登録を同一DBトランザクションで行う。認証後に遅れて届いた新規会議作成は、同じユーザー行をトランザクション内でロックして再確認する。退会応答の通信失敗後に同じCookieで再送できるよう、本人ID・会議ID・内容を含まない24時間の受領記録を残す。これは削除完了の証明ではなく、再送への`deleting`応答に限る。所有者を復号できない会議がある場合、退会を部分確定せず失敗させる。異常時の運用復旧、実OpenBao鍵破棄、バックアップ検証が済むまで退会・7日削除を本番提供済みと扱わない。

P5の期限到来削除は7日満了を待たず、その15分前から削除Jobを開始する候補に変更した。P6の内容なし集計カウンタと暫定対応表は[運用観測・一次対応](account-service-v1-operational-runbook.md)に記録した。通知先・当番・実鍵／バックアップの検証は未実装であり、カウンタと文書だけで7日削除や運用受入れを達成したとは扱わない。

P1/P3/P6のWorker監督候補は、複数Analyzer・Drain・削除・認証期限掃除を独立したループで稼働させ、1ループの例外が他を止めない。ログはcomponent名と安全なerror codeのみとし、Analyzer Jobの失敗を自動で成功扱い／無条件再試行しない。停止時には処理中のWorkerが残れば「停止済み」と報告しない。これはローカルSupervisor部品と合成テストであり、公開Serviceの起動経路、通知、複数Pod配置・Pod故障復旧の検証には進んでいない。

この表は実装済み範囲と未達ゲートを分けるためのもの。未達の段階を完了と解釈しない。

### P3候補の停止・終了境界

ローカル候補では、HTTPのpause要求だけでは音声停止を確定しない。同じ音声WebSocket上で最後のPCM frameの後に`capture_stop`と最終sequenceを送り、Gatewayが受理台帳の末尾と照合し、Provider itemを有界に収束させた後に`capture_paused`を返す。停止制御が届かない／番号が一致しない／itemが未解決なら`paused`とはせず、再接続と欠落可能性を記録する。`pausing`中も停止制御より前に到着したframeを順序どおり処理する。

Ownerの`POST /api/service/sessions/{id}/end`は停止済み`paused`／取込み不能が記録済みの`reconnecting`から直ちに`finalizing`へ進む。`listening`／`pausing`からはDBへ終了意図を記録して停止確認を待つ。`resuming`では停止確認不能の可能性を明示し、欠落区間を残して`finalizing`へ進む。Canonical `session_finalizing`とintake fenceを同一トランザクションで確定し、Job／Provider itemが残る間は最終revisionを固定しない。すべて解決すれば`ended`、欠落区間があれば`ended_incomplete`とする。期限切れによる未解決Job／itemの不完全終了は信頼されたWorkerがDB時刻で判定し、HTTPクライアントは期限成立を指定できない。Gateway間の接続占有はPostgreSQLの30秒leaseを5秒ごとに更新し、期限切れなら取込み不能を記録してgenerationを進める。接続IDは会議鍵によるdigestのみDB保存し、PCMは保存しない。現時点では常駐Workerの配備・起動監督、実Browser／Provider統合、実複数Pod・Pod障害復旧のEnd-to-Endは未達である。

### P3候補のDrain監督

`ServiceDrainSupervisor`候補は停止待ちの終了意図と`finalizing`会議を巡回し、DB時刻で停止期限・Job／Provider item解決・Drain期限を判定する。停止待ちの会議が他会議のDrainを妨げない。終了要求と期限は同じトランザクションで確定する。Drain期限は候補既定300秒（Store設定で30〜3600秒）；無音や会議時間の上限ではなく、明示的な終了要求後のDrainにだけ適用する。未解決のまま期限が来た場合は`ended_incomplete`とし、`ended`と偽らない。Supervisor再起動後も期限と最終revisionはDBから再開し、同時Workerは`SKIP LOCKED`とSession直列化で二重終了しない。現段階の検証は合成PostgreSQLであり、プロセスの起動／監視、実Providerと実BrowserのEnd-to-Endは未達である。

### P3候補の入力中End

Ownerが音声入力中にEndを要求すると、同一operation keyの終了意図を永続化して`pausing`を返す。Browserは新規PCM送信を止め、最後のframe sequenceを同じWebSocketの`capture_stop`で送り、Gatewayは受理済み末尾と照合してProvider itemを有界に収束させる。確認後のみ`paused → finalizing`へ進む。終了意図がある間は別Socketの再接続とCapture再開を拒否する。停止制御の不達、誤った末尾、Provider／Socket障害では完全停止を装わず、接続断または停止期限（候補90秒）を記録して欠落可能性を残す。これらは会議時間や無音期間による自動Endではない。合成HTTP／WSS／DBでは同じ操作の再送、異なる操作Keyの拒否、停止成功、停止未確認、二重終了防止を確認した。実BrowserのUI操作と実Providerの結合は未達である。
