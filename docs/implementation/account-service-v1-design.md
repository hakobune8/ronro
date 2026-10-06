# RONRO Account Service v1 — 実装設計案

| 項目 | 内容 |
| --- | --- |
| Status | Proposed for Human Review。コード・配備・GAの承認ではない |
| Based on | [RFC-0007](../rfc/0007-service-readiness-improvement-inventory.md)、[RFC-0008](../rfc/0008-account-based-service-architecture.md) |
| Scope | 個人アカウント、同時4会議を検証、会議中の継続・復旧、会議後PDF、RONRO管理下の7日削除 |

## 1. 設計の境界と採用判断

本書はRFC-0008のサービス層を実装できる単位に落とす。現行の[Event Catalog](../architecture/discussion-event-catalog.md)とSchemaは変更しない。`created → active → finalizing → ended`のCanonical Session状態、`session_ended.drain_status`、Human Eventの`expected_revision`、EventのSession内連番を維持する。休憩・接続断・所有者・削除・PDFは**別のService Runtime状態**であり、議論上のNode／Relationではない。

採用する初期構成は、認証済みWeb/API、Session Capture Gateway、STT接続、耐久Job Worker、PostgreSQLのトランザクション記録、非公開PDFオブジェクト保存、読み取り専用Shared View。PostgreSQLとオブジェクト保存は**実装の参照構成**であり、機能契約は製品非依存にする。Redis、第二のLLM、全文検索、会議後の編集、受取人アカウント、公開共有リンクは初期依存にしない。DB／ストレージの提供製品と7日削除条件は配備ADRで確定する。

現行の`LiveSessionManager`は単一Sessionの開発・Pilot実装であり、単に`replicas`を増やして本設計を達成したと扱わない。`controller_id`はロック用の表示識別子であって本人確認ではない。既存のEvent Store、Materializer、Analyzer、Semantic Canvasは、Session単位の永続アダプタの内側で再利用する。Canonicalの出力は正本で、Projection／PDFは再生成可能な派生物とする。

### 初期サービスで確定した条件

- 起動ユーザーの個人アカウントが会議を預かる。会議後は誰も訂正しない。出席者への共有はPDFのみ。
- 2～8名・同時4会議・約2時間を**検証条件**とし、2時間経過を自動終了条件にしない。4会議を無条件に処理できるとの保証は容量試験前に公表しない。
- RONRO管理下の会議データは終了から最大7日で復元不能にする。退会・明示削除で前倒し。暗号化済みバックアップは鍵破棄後に物理削除が遅れてもよい。Provider側と配布済みPDFには7日要件を適用しない。
- 本運用では生音声を永続化しない。欠落可能性を隠さず、会議の継続とEvidence完全性を別に扱う。Pilot録音の同意・限定アクセス・7日削除は別構成のままとする。

## 2. 永続データと所有権

最小の論理レコードを以下とする。列名は実装時のmigrationで固定するが、識別子・一意制約・削除境界は本書の契約とする。全ての会議従属レコードは`session_id`を持ち、外部から渡された`owner_user_id`を信用せず、認証済み主体とDB上の所有者を毎回照合する。

| レコード | 必須情報／制約 | 正本・用途 |
| --- | --- | --- |
| `user` | 内部UUID、OIDC `issuer + subject`の一意組、退会状態 | 個人アカウント。メールアドレスを永続IDにしない。 |
| `session` | ランダムUUID、暗号化した`owner_user_id`・title・会議時刻、Canonical revision、Service Capture状態、capture generation、version、expiry | 所有権と会議境界。バックアップに平文の所有者対応やタイトルを残さない。 |
| `capture_interval` | session、generation、開始／終了、`listening / paused / disconnected`、gapの開始／終了／不明、理由 | 休憩と予期しない欠落を区別。未確定範囲に「欠落なし」を付けない。 |
| `provider_item` | session、connection generation、Provider item ID、ローカルframe範囲、commit ID、状態、解決／空Final／エラー | 同一音声区間のFinal重複と未解決itemを検出。Provider IDがない状態も明示。 |
| `evidence` | session、Evidence IDとsequence、Final text、時刻、Provider item参照 | 確定発話のみ。`(session_id, provider_item_id)`が判明する場合は一意。Partialは保存しない。 |
| `analysis_job` | session、Evidence ID、utterance順序、state、attempt、claim期限、入力版、受理出力、error | Evidenceの処理義務。`(session_id, evidence_id, analyzer_contract_version)`を一意にする。 |
| `canonical_event` | session、sequence、event_id、既存SchemaのEnvelope/Payload、actor、source Evidence | Session内の受理済みEvent列。`(session_id, sequence)`と`(session_id, event_id)`を一意にする。 |
| `graph_checkpoint` | session、revision、last sequence、Projection版、再生用状態 | キャッシュ。Event列から再生可能で、破損時には捨てて再構築。 |
| `pdf_export` | session、固定revision、生成版、状態、オブジェクト参照、生成時刻、expiry、ダウンロード監査 | 会議後のPDF。公開URLを保存しない。 |
| `service_audit` | session、暗号化した認証主体／Ticket参照、操作、結果、時刻 | 内容を原則含めない。会議・個人を識別可能な部分はSession鍵で保護する。 |
| `deletion_job` | session、期限、進行段階、試行回数、失敗理由コード | 全保存先の削除完了を追跡。本文は入れない。 |

Sessionの初回作成とowner紐付けは1トランザクション。Evidence受理と`analysis_job`作成も1トランザクションとし、Final受理を返す前に両方永続化する。WorkerはSessionごとの順序を保ちつつ、複数Session間は公平に処理する。解析API呼出しはDBトランザクション外で行い、**受理したAnalyzer出力、Event列、Graph revision、Job完了**をSession行のロック下で原子的に確定する。外部LLM呼出しの厳密な一度だけ実行は約束しないが、同じJobのEvent受理は一度にする。Worker喪失後は期限切れclaimを回収し、既に受理済みならLLMを再呼出しせず結果を返す。解析を開始したGraph revisionと受理時のrevisionが異なる場合は、結果を無条件に追加しない。特にHuman訂正を跨ぐ結果は最新Graph／訂正履歴で再検証または再解析し、古いEvidenceだけで訂正を覆さない。

Human訂正は認証・Session所有権と`expected_revision`を検証し、既存Event CatalogのHuman Eventとして同じEvent列にappendする。競合したら`revision_mismatch`として最新revisionを返し、古い意図を自動で別のNodeへ付け替えない。発話由来の訂正はEvidenceと解析経路を保持し、認証ユーザーのUI操作と偽装しない。訂正で否定されたRelationを古いEvidenceだけから再提案しない既存の抑止条件を維持する。

### 復旧・再生の不変条件

1. `canonical_event`はSession内で連続sequence。受理済みEventの内容を書き換えない。Checkpointは同じEvent列から一致して再生成できる。
2. 確定FinalにはEvidenceと処理すべきJobがあり、どのJobも`pending / processing / completed / failed`のいずれかで説明できる。黙って消えたJobを作らない。
3. 会議を跨ぐEvent・Evidence・Jobは混ぜない。DB問い合わせとオブジェクトキーの両方にSession境界を設ける。
4. STTの`item_id`、接続世代、ローカルframe範囲が分かる場合は相関を保持する。未知の範囲を推測して「処理済み」にしない。
5. PDFは`session_id + final_revision + renderer_version`に固定した派生物。新しいAnalyzer呼出しによる会議後の再解釈を行わない。

## 3. APIと権限の契約

認証方式はOIDC Authorization Code + PKCEを参照実装とする。バックエンドでissuer、audience、署名、期限を検証し、`issuer + subject`を内部user IDへ写像する。ブラウザには`Secure`／`HttpOnly`／`SameSite`のSession cookieを発行し、状態変更にはCSRF保護を適用する。認証製品名は配備ADRで選ぶ。`controller_id`、Session ID、URLの知識だけでは一切の操作権を得られない。

| 操作（概念経路） | 認可・冪等性 | 成功／失敗の契約 |
| --- | --- | --- |
| `POST /api/service/sessions` | 認証済み起動ユーザー。`Idempotency-Key`必須 | 同じKeyの再送は同じSessionを返す。容量超過は新規Sessionを作らず`capacity_unavailable`。 |
| `POST /api/service/sessions/{id}/capture/start` | owner、Session version、操作Key | `listening`へ。マイク権限がない場合は状態を偽って進めない。 |
| `POST /api/service/sessions/{id}/pause`／`resume` | owner、version、操作Key | `paused`／新しいgenerationで`listening`。再送は同じ結果。競合は409。 |
| `POST /api/service/sessions/{id}/end` | owner、version、操作Key | `finalizing`へ一度だけ遷移。Drain中の再送は進捗を返す。終了後の新規Audioを拒否。 |
| `POST /api/service/sessions/{id}/commands` | owner、Canonical `expected_revision`、操作Key | 会議中のみHuman Eventを受理。旧revision、曖昧な発話訂正はGraph無変更。 |
| `GET /api/service/sessions/{id}`／`canvas` | owner、または当該会議の短命な表示専用資格 | owner以外の会議一覧・Transcript/Evidenceを表示資格へ返さない。 |
| `POST /api/service/sessions/{id}/pdf`／`GET .../pdf` | owner、終了・固定revision確認 | 生成Jobは冪等。認証済み応答として配信し、公開・恒久URLを作らない。 |
| `DELETE /api/service/sessions/{id}`／`DELETE /api/service/account` | owner／本人、操作Key | 即座にアクセス停止と削除Job登録。重複呼出しは同じ削除状態。 |

実経路名は既存`/api/live`との並行移行を避けるための候補であり、URL命名のみ実装時に調整可能。**認可・状態・冪等性・エラーコードの意味は変更しない。** 正常な作成は201、処理中の終了・PDFは202、完了済みの再送は同じ結果、version／revision競合は409、期限切れ・削除済みは410、新規受付の容量不足は503（`Retry-After`付き）を返す。他人のSession IDの存否を漏らさず404とし、同一本人の権限不足は403とする。失敗応答は機械可読な`error.code`と利用者向けの短い説明を持つ。APIとWSSはSessionごとに権限を確認し、WebSocketでは`Origin`と接続開始時の資格に加えて、接続継続中も資格失効・Session終了・generation変更を反映する。CookieやトークンをURL query、ログ、PDFに埋めない。

Shared Viewは会議中の**Session限定・読み取り専用表示資格**をownerが当該画面に発行する。ownerが認証済みの画面から表示用Tabを開くか、会議開始前に一回限りのpairingで別ディスプレイを登録する。会議中のShared Viewへ参加者の操作を要求しない。表示資格は短命・更新可能・ownerが取消可能とし、会議終了・owner削除時には失効する。表示資格にはTranscript/Evidence、Command、PDF、他Sessionの権限を与えない。これは会議中の会議室表示であり、会議後の出席者共有リンクではない。PDFはownerがダウンロードし、RONRO外で出席者へ配布する。

アカウント退会で当該ユーザーの全会議へのアクセスを直ちに停止する。進行中会議は`finalizing`または不完全終了へ安全に移行させ、削除完了後に再取得できないことを確認する。所有者の移管・共同所有は初期スコープ外。

## 4. Capture、休憩、切断、終了

Canonical Session状態を増やさず、Service Capture状態を`created / listening / pausing / paused / resuming / reconnecting / finalizing / ended / ended_incomplete / deleting`とする。`resuming`は休憩から新しい接続世代の受理が確認されるまでの過渡状態であり、画面へ`listening`と偽って表示しない。各遷移はSession versionをCAS更新し、同じ操作Keyで重複実行しない。`ended_incomplete`はServiceの結果表示であり、既存Canonical `session_ended.drain_status=partial|failed`を別名へ書き換えない。

| 起点 | 入力 | 次状態 | 実行・記録 |
| --- | --- | --- | --- |
| created | start | listening | generation 1、開始時刻。失敗ならcreatedのまま理由を返す。 |
| listening | pause | pausing → paused | 新規frameを止め、進行中Provider itemを有界に収束。未解決itemは保持し、休憩区間を記録。Jobは処理継続可。 |
| paused | resume | resuming → listening | 同じSession／Graph、新generationのSTT接続。受理確認前は`resuming`、失敗時は再試行可能な状態を保持。休憩時間を欠落扱いしない。 |
| resuming | 接続失敗 | reconnecting | 再試行する。resume要求以降の取込み不能な範囲は、休憩区間と混同せず欠落可能性として記録。 |
| listening | Transport／Provider切断 | reconnecting | 最終受理frame、未解決item、未知の音声範囲を記録。既存Graphを維持して再接続。 |
| reconnecting | 再接続成功 | listening | 新generation。旧generationの遅延frame／Finalを新世代へ混入しない。後着Finalが当該旧itemに正しく相関できれば処理可。 |
| listening／paused／resuming／reconnecting | end | finalizing | 取込み停止、STT item・Job・Projection Drain。再送で二重終了しない。 |
| finalizing | 全状態解決 | ended | `session_ended`のcomplete、Queue 0/0/0、最終revision固定。 |
| finalizing | 期限内に解決不能 | ended_incomplete | 失敗item／Jobと可能な欠落区間を保存、`session_ended`のpartial/failed。完全扱いしない。 |

同一generation内のframeは連番・接続IDを検査する。短い再送は重複排除し、ギャップ・未知範囲・再生不能は`capture_interval`へ記録する。ブラウザの未送信音声を永続化しないため、タブ喪失時の完全復元は保証しない。サーバーがframeを受理したこと、Providerがitemをcommitしたこと、文字起こしFinalがEvidenceになったことは別段階として可視化する。長い無発話やBGMを終了条件にしない。Providerエラーは当該itemを隔離し、可能な範囲で接続を張り直す。再試行しても発話を復元できなければ、会議を続けつつ欠落可能性を残す。

起動ユーザーが明示的に終了したら、新規入力を止め、未解決Provider item、未処理Evidence、Analyzer Job、Canonical Event、Projectionの順にDrainする。期限切れを`ended`に丸めない。Podの更新／喪失後は永続記録から`reconnecting`を復元し、表示を「再接続待ち」にする。音声の欠落を推測で埋めない。孤立したSessionは期限付きの回復試行後、不完全終了へ進めて7日削除の起算点を持たせる。**2時間経過だけではこの遷移を起こさない。**

終了時に期限までに解決できなかったProvider item／Analyzer Jobは、不完全終了の理由として確定し、`session_ended`と`final_revision`を同じSession直列化境界で固定する。**固定後に届いた旧Job結果・旧世代Finalは、その会議のCanonical EventやPDFを後から変更できない。** 後着結果は安全な診断状態として扱い、欠落可能性を消さない。これにより「会議後は訂正しない」とPDFの再現性を両立する。完全終了では未解決item／Jobがないことを確認し、単にタイムアウトしただけで`ended`にしない。

## 5. 同時会議、Worker、配備更新

同時会議数は設定可能なAdmission上限を設け、初期値を**検証用4**とする。容量試験前は保証値として表示しない。上限到達時は新規開始を拒否し、既存会議を終了させない。2～8名は音声品質の検証条件であり、音声接続の数が参加人数と一致するとは仮定しない。2時間超でも継続するが、Queue遅延・Provider制限・費用を監視する。

Job WorkerはDBから期限付きclaimで取得し、Session内のEvidence順序を保つ。複数Sessionは公平に選び、一つの長発話・Analyzer retryが他Sessionの処理を永久に塞がない。Per-session backlogと全体backlogを分けて計測し、閾値超ではSessionを勝手に終了せず、遅延をownerと運用者へ示す。容量不足時の新規開始を制限する。Worker再起動時は期限切れclaimを回収し、受理済み出力を再利用する。

段階的更新では新Sessionを新versionへ割り当て、既存Sessionは接続を維持するか、持続化したcheckpointからgenerationを進めて再接続する。`Recreate`による強制切断を通常の更新手順にしない。旧versionのWorkerが新しいSession generationを書けないようフェンスを張る。ロールバックは**Event／Analyzer Output／Projection／DB migrationの互換性**を確認した版にのみ行う。新Schemaを先に追加し、旧版が読める間に切替え、後から旧Schemaを除去する。互換性のないmigrationを単一配備で同時に行わない。再接続中の未Final音声は失われ得るので、更新成功とEvidence完全性を同一視しない。

## 6. 会議後PDFと7日削除

PDF生成の入力は`final_revision`で固定した受理済みEvent列とCanvas Projection、Sessionの欠落区間、renderer versionのみ。別LLM要約は使わない。構成は、会議の全体像（複数Root／主要branch）→Decision候補と確定、Open Item、Action→詳細Nodeと関係の説明の順を初期案とし、大規模Graphは複数ページに分ける。各NodeのCanonical本文は詳細部で読めるようにし、全Nodeを一画面に縮小しない。オーナー・期限は明示済みの場合だけ掲載する。`ended_incomplete`は実測した欠落可能性の時間帯と「範囲不明」を区別してPDFに記す。Graph破損・final revision未確定なら完成PDFを出さず、エラーを返す。

実装は既存CanvasのFinal Projectionを入力にした**印刷専用HTML**と、版を固定したヘッドレスPDFレンダラを候補とする。レンダラは外部URLへアクセスせず、フォント／CSSを同梱する。同じEvent列・Projection版・Renderer版から同じ本文とページ構成が出ることをSnapshot試験で確認する。画面用の「全体を一度に見せる」縮尺を紙面へそのまま転用しない。最初のページは30秒程度で全体を把握できる概要、続くページは判読できる文字サイズの詳細とする。紙面のページ数・長いラベル・多数Node・複数Root・Relationなし・日本語改行を合成Graphで検証する。

PDFオブジェクトは非公開・サーバー側暗号化・無期限公開URLなし。配信はowner認証を通し、`Cache-Control: no-store`、安全なファイル名、短時間のサーバー側一時領域で行う。PDFメタデータやリンクにTranscript、内部ID、認証情報を含めない。ダウンロード後の配布・再配布・削除はRONROの管理外と出力画面で説明する。PDFは7日削除対象の派生物で、退会時は再ダウンロード不能にする。

削除は`expiry = ended_at + 7 days`を基準にし、期限までにアクセス停止→Job／Worker claim停止→Session専用復号鍵破棄→現用PDF・Event／Evidence・Graph・Log・Cache削除→照合の順に行う。明示削除・退会は前倒し。遅れたJob結果、古いWSS、遅延PDF生成が削除後にデータを再作成しないよう、全書込みでSessionの`deleting`状態とgenerationを検査する。削除失敗は再試行とアラートを行い、成功済みと表示しない。会議内容や個人識別子を含む監査ログも削除対象。

参照構成では会議ごとにランダムなData Encryption Key（DEK）を作り、会議本文・Event Payload・Evidence・PDF・内容を含むログ／キャッシュをアプリケーション層で暗号化する。復号鍵を管理するKey Registryは、通常DBバックアップ／WAL／オブジェクト履歴とは分離する。鍵の現用コピーと、もし存在するなら鍵の復元用コピーを**同じ7日期限内に破棄できること**を必須にする。鍵は短時間だけメモリに置き、Job結果・例外ログ・ダンプへ出さない。Key Registryは少なくとも単一ノード喪失に耐える複製を持つが、鍵の長期スナップショットは作らない。鍵自体が失われた場合は会議記録を復元できないため、複製の故障注入試験と監視を行う。

会議タイトル、ownerとの対応、時刻などの**平文メタデータ**が通常DBバックアップに残れば、鍵を破棄しても7日要件を満たしたとは言えない。参照実装ではowner ID・title・会議の詳細時刻・会議内容をSession鍵で暗号化し、DBに平文で置くのはランダムSession ID、処理状態、revision、削除期限などの最小運用値に限る。認可時はSession IDから鍵と暗号化owner IDを取得して照合する。ownerの会議一覧は、初期規模では未期限切れSessionを走査・復号して作り、永続的な平文owner→Session索引を作らない。高速化が必要なら**期限内に破棄できる非永続キャッシュ**を使い、バックアップ対象にしない。Session IDと運用値だけでも本人へ再結合できる別ログ・索引があれば漏えい経路になるため、その組合せを脅威レビューと復元試験に含める。集計監視は個人・会議の再識別ができない形にする。実装時のストレージADRは平文列・索引・ログ・一時ファイルを列挙し、保護境界を明示する。

**保存先の採用ゲート**: 現用DB・レプリカ・PDFオブジェクト・キャッシュ・バックアップ・WAL／スナップショット・Key Registryを列挙し、終了から7日を超えてRONRO管理下の会議データを復元できないことを実証する。暗号化済みバックアップの物理削除が遅れることはHuman判断により許容するが、鍵がバックアップやログから復元できるなら不可。期限後のバックアップ復元試験で本文・所有者対応・監査内容が読み出せないことを確認する。鍵破棄を「全コピーの物理削除」と説明しない。選ぶDB／鍵管理／オブジェクト提供形態で復元不能性を証明できない場合は**GA不可**とし、7日要件を無断で緩めない。Provider側と配布済みPDFはこの期限の対象外だが、利用者へ別に説明する。

## 7. セキュリティ、運用、利用者への説明

公開サービス化前に、アカウント乗っ取り、Session ID推測、Shared View資格の漏えい、WSSの越権、CSRF、PDFの誤配布、削除後の遅延Worker、評価API露出、Provider key漏えいを脅威シナリオとしてレビューする。Secretは配備基盤から注入し、repo・PDF・ログへ出さない。評価／Fixture APIはサービス経路から切り離す。TransportはTLS/WSS。認可の否定ケース、ログの機微情報検査、依存ライブラリとイメージの脆弱性対処をリリース手順に含める。

通常監視は内容なしのSession状態・再接続・Provider item未解決・Evidence gap・Queue depth／age／failure・GraphとRendered revision差・PDF／削除Job・費用を使う。アラートには検知→担当への通知→利用者への状態表示→復旧／不完全終了→事後記録を対応付ける。具体的な通知先・当番・応答時間はGA前に確定する。内容を伴うエラー解析は、解析担当者とは別の承認者がTicket・対象・項目・理由・有効期限を承認し、全閲覧を監査する。承認者を確保できない運用では、この権限経路を有効化しない。

起動ユーザーには開始前に、会議中の音声処理、RONRO管理下の7日保持、Provider側の別条件、会議後PDFの外部持ち出しと失効不能、休憩・切断・欠落可能性を説明する。出席者への説明方法と同意の運用はPilotと本運用を混同せず、提供地域の法務・運営判断としてGA前に確定する。参加者にアカウント操作を要求しない。障害時には「会議は継続中」「処理が遅延」「この時間帯に欠落可能性」等を区別し、根拠のない完全性表示をしない。

## 8. 受入れ試験と実装順序

以下は実装を進めるための**正誤判定可能な契約試験**。実会議に対する品質SLO・サポート応答時間などの数値は、合意どおりPilot評価を経てGA時に確定する。数値未定を理由に安全違反を許容しない。

| Work package | 実装内容 | 必須の試験・証拠 | 対応SR |
| --- | --- | --- | --- |
| W1 永続正本 | Session、Evidence＋Job原子記録、受理Event＋Graph＋Job原子更新、replay | crash直前／直後、重複Final、重複Job、旧revision訂正、別Session混入、Checkpoint再生成 | 02, 03, 06 |
| W2 認証・所有 | OIDC、Session認可、Shared View表示資格、API/WSS隔離 | 他userのSession／PDF／Command拒否、失効資格拒否、CSRF、Origin、評価API非公開 | 04, 07 |
| W3 Capture継続 | pause/resume、generation fencing、再接続、欠落区間、Drain | 休憩は欠落扱いしない、BGM/無発話で終了しない、Pod/Provider障害で既存Graph保持、未知区間は不完全 | 02, 08, 09 |
| W4 並行処理 | Admission、Session内順序、公平なWorker、負荷観測 | 4並行会議×2時間超、2～8人相当の音響条件、5件目拒否時に既存会議維持、費用記録 | 01, 10 |
| W5 PDF・削除 | 固定revision PDF、欠落注記、Session鍵、7日以内の復元不能化、退会 | ended／ended_incomplete出力、Graph破損時拒否、時刻不明の警告、PDF越権、鍵破棄後のバックアップ復元試験 | 05, 12 |
| W6 運用・品質 | Alert／Runbook、脅威レビュー、実機Shared View、Pilot評価 | Class 3安全事象0、訂正持続、3～5m読解確認、内容閲覧の承認監査、障害告知訓練 | 06, 07, 08, 11, 13 |

順序はW1→W2→W3→W4/W5→W6。W2の認可が完了するまで複数ユーザー向け公開経路を有効化しない。W1の永続化が完了するまでPod喪失からの復旧を約束しない。W5のPDFと削除が完了するまで、PDFだけで出席者へ共有できるサービスとは案内しない。W6は後回しの検証だけでなく、各packageと並行して失敗を観測する。

各packageは単体試験、状態遷移・DBトランザクション試験、障害注入、権限否定試験、既存Canonical replayとの互換試験を通す。候補環境で一会議の開始→訂正→休憩→再開→終了→PDF→削除を実証し、その後に4会議並行試験へ進む。既存Pilotからのデータ移行は自動で行わず、移行対象・既存7日期限・同意範囲を別途確認する。

## 9. 配備前の未確定事項

実装チームが推測で埋めてはいけないのは、(1)採用するOIDC基盤とDB／オブジェクト保存の運用主体、(2)Key Registryと平文メタデータを含めた7日以内の復元不能化を実証する保存方式、(3)正式なPilot／GA品質SLO・事故連絡担当、(4)本運用の参加者説明・同意文面、(5)実際のProvider組織／プロジェクト条件である。これらは**実装開始を一律に止める条件ではない**が、それぞれ該当packageの本番受入れ前に決めて証拠を残す。

外部連携・課金・組織共同所有はRFC-0007のSR-14として初期サービスから除外する。除外事項を実装漏れと数えない。

## 10. 既存コードへの変更境界

| 既存箇所 | 再利用・変更方針 | 避けること |
| --- | --- | --- |
| `prototype/store.py`、`prototype/replay.py`、`prototype/materializer.py` | Storeの永続アダプタを追加し、既存Schema validationとMaterializerの純粋適用を再利用する。 | MaterializerからDB、時計、Providerへ直接アクセスすること。 |
| `prototype/live_queue.py`、`prototype/live_continuous.py` | Evidence＋Jobの耐久受理、claim／再試行、Session別順序、公平なWorkerへ分離する。 | 既存のメモリFIFOをPod間共有できると見なすこと。 |
| `prototype/live_stt.py`、`prototype/live_transport.py`、`prototype/live_session.py` | Provider item相関を維持し、capture generationと休憩・再接続・欠落区間をService Runtimeに永続化する。 | 接続を張り直しただけで過去の未Final音声が回復したと表示すること。 |
| `prototype/server.py`、`prototype/web/*` | 認証／Session認可を通る新サービス経路を作り、Pilot／Fixture経路を明確に分離する。 | `controller_id`をログインと同等に扱うこと。 |
| `prototype/semantic_canvas.py`、Projection関連 | 同じFinal ProjectionからShared Viewと印刷専用HTML/PDFを導く。 | 会議後だけ別のGraphや新しいLLM要約を作ること。 |
| `schemas/*` | 初期段階ではCanonical Schemaを維持し、Service Runtime／DB migrationを別管理する。 | 休憩・認証・PDFの都合でDiscussion Eventの意味を変更すること。 |

最初の実装PRは永続化インターフェースと移行試験を対象とし、現行Pilotの挙動を維持する。続くPRで認証・新APIを候補環境だけに公開し、Capture復旧、PDF、削除、負荷試験を段階的に追加する。各段階で既存テストと、同じEvent列によるreplay一致を確認する。旧Pilotデータを黙って新アカウントへ紐づけない。
