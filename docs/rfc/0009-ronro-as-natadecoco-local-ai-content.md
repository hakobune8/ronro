# RFC-0009: RONRO as a natadeCOCO Local AI Content

| 項目 | 内容 |
| --- | --- |
| Status | Working architecture / 段階実装に着手。Platform契約・配備・機密会議利用は未承認 |
| Last Updated | 2026-10-09 |
| Scope | RONRO CoreとSpot向けContentの分離、AI Provider境界、音声・データ境界、GDK適合、段階的移行 |
| Inputs | [MVP要件](../requirements/discussion-map-ai-facilitator-mvp.md)、[Architecture Baseline](../architecture/mvp-architecture-summary.md)、[RFC-0001](0001-discussion-model.md)〜[RFC-0008](0008-account-based-service-architecture.md) |

実装判断を残さないための接続・状態・音声・PDFの詳細は[Spot Content契約](../architecture/natadecoco-content-contract.md)、Spotらしい入口・会議中UI・専用artworkは[UI / Artworkブリーフ](../product/natadecoco-ronro-ux-artwork-brief.md)、PR単位の依存順・試験・ゲートは[実装計画](../implementation/natadecoco-content-implementation-plan.md)に記す。段階実装の着手は承認されたが、Platform ownerの契約確認・Spot実機受入れ・機密会議利用・配備は別ゲートである。

2026-10-07 の実装順判断: [独立Content repository](https://github.com/hakobune8/natade-coco-ronro)の合成データ骨組みを先行し、`natade-coco-edge` の変更を保留する。この順序変更は、後述のHost認可・PDF受取前の終了保護が現行Platformだけで成立するという意味ではない。成立を実証できるまで実音声を伴う配備・機密会議向け宣言をしない。

**2026-10-09 の新しい利用者判断（旧Host専用案を上書き）**: PlatformのHostだけが既存ShellでSessionを開始・全体終了する。RONRO Content内の会議の中断・再開・終了・論点の訂正、および終了直後のPDF取得は、同じPlatform session/runに現時点で認証・接続している参加者なら行える。全体終了は会議Endの代用品ではなく強制終了であり、Drain/PDF受取を保証しない。全参加者のPDF受取窓はPDF readyから暫定30分で、**期限到達時のみ**Spot内記録を削除する。誰にも手動削除・受取終了による早期消去を許さない。以前の本文・表にあるHost限定、operation別Host lease必須、opt-in終了ガード必須、受取終了/明示破棄、非Host PDF拒否は歴史的な案であり、現在の実装条件ではない。最新版の詳細契約と移行順は[Spot Content契約](../architecture/natadecoco-content-contract.md)と[実装計画](../implementation/natadecoco-content-implementation-plan.md)を正とする。既存候補コードが更新・本番有効化済みという意味ではない。

**同日の補足 — Controller≠人**: スマホControllerは会議室のマイク/入力端点であり、1台を複数人で共有できる。PlatformのPlayer照合は「その端点が現在のsession/runに参加できる」ことを示すだけで、発話者、操作した人、進行役、Host本人を証明しない。上の「認証済み参加者」は認可対象としては**現在認可されたController**と読み替える。RONROは端点を人物IDやAction Ownerへ変換せず、Human-origin Eventも「人の入力」とAI提案の区別であり、実行者の本人確認ではない。PDFも端点への取得許可であって、各出席者への配布完了を保証しない。

## 1. Contextと調査基準

RONROは会議中の論点図を作る研究・Pilot用プロトタイプである。現行のライブ経路はブラウザAudioWorkletのPCMをRONROのPython WebSocketへ送り、OpenAI Realtime transcriptionでFinal Transcriptを得て、OpenAI互換Analyzerの候補Eventを検証・受理し、Event Store／MaterializerからGraphとSemantic Canvasを作る（[README](../../README.md)、[Pilot設定](../../deploy/kubernetes/base/configmap.yaml)、[Live STT](../../prototype/live_stt.py)、[Analyzer](../../prototype/real_analyzer.py)）。現行Pilotは音声を外部APIへ送る。録音は同意条件のあるPilot評価用の例外で、機密会議向け既定動作ではない。

機密会議ではアプリが外部APIを呼ばないだけでは足りない。マイク、ブラウザ、転送、STT、Analyzer、ログ、Pod／HostのEgress、管理面を通じたデータ流出まで境界を定義・実証する必要がある。**音声入力の第一候補は参加したスマートフォンControllerのマイク（同時最大8台）**とし、Spot内でSTT・Analyzerを行い、大画面へ表示する。Platform HostはSession開始・全体終了を担い、会議の中断・再開・終了・訂正・PDF取得は認証済みの参加者に開く。音声入力を1台へ限定しない。この方式では生音声がSpot外のスマホで発生する。「生音声は一瞬もSpot外に存在しない」という当初の文字通りの要件は満たせない。保証可能な目標を「参加端末からローカル経路でSpotへ送り、外部AI・Internetへ送らず、Spot内で処理する」と区切る。より強い物理境界が必要な会議ではSpot直結マイクを別Capture profileとして検討する。両者を同じ保証として案内しない。

調査したGDK `main` は [0ba3e224](https://github.com/hakobune8/natade-coco-gdk/tree/0ba3e224d503b131ab0d7969cc9e7dd82026a364)。`game.yaml` は `kind: Game`、必須Controller実装、game/run/result時間を要求する。**テンプレートの1〜4 playersはサンプル設定であり、8台へ指定できる**。Platformの[Session Manager](https://github.com/SSLHQ/natade-coco-edge/blob/44f52ae319de18bc3b8a0fa4c3c194fe9ae68b79/game-platform/services/session-manager/internal/session/state.go)と[Game Catalog API](https://github.com/SSLHQ/natade-coco-edge/blob/44f52ae319de18bc3b8a0fa4c3c194fe9ae68b79/game-platform/docs/api/game-catalog-openapi.yaml)はいずれも最大8を許す。**枠を8と宣言できることは8本の音声ストリームの処理保証ではない**ため、Content側の音声経路・資源・障害分離を別途実証する。GDKはDisplay SDK、Platform Controllerへのhandoff、Manifest検証、コンテナ／Fleet引渡しを提供するが、現行テンプレートのGoサーバーは静的配信のみで、RONROのPython API・音声取込・永続状態を扱わない（[GDK開発ガイド](https://github.com/hakobune8/natade-coco-gdk/blob/0ba3e224d503b131ab0d7969cc9e7dd82026a364/docs/game-development.md)、[GDK Manifest](https://github.com/hakobune8/natade-coco-gdk/blob/0ba3e224d503b131ab0d7969cc9e7dd82026a364/game.yaml)）。現行GDKを「既に一般Content対応済み」とは呼ばない。

関連Platform実装も補助的に確認した。`natade-coco-edge`の作業checkout `44f52ae` は別作業の未コミット変更を含むため、**配備済み契約の証明ではない**。そのChartにはゲームPodのIngress/Egress default-deny、Traefik／Catalogから8080へのIngress、単一ゲームコンテナ、read-only root等がある（[Chart](https://github.com/SSLHQ/natade-coco-edge/blob/44f52ae319de18bc3b8a0fa4c3c194fe9ae68b79/game-platform/deploy/charts/natadecoco-game/templates/networkpolicies.yaml)、[Network設計](https://github.com/SSLHQ/natade-coco-edge/blob/44f52ae319de18bc3b8a0fa4c3c194fe9ae68b79/docs/network.md)）。Platform変更の前に、実際の配備Runtime・Schema・CNIに照らして再確認する。

## 2. Goals / Non-goals / 継承する原則

Goals: (1) **段階的に**同時最大8台のスマホマイクからSpotへ生音声をローカル転送し、外部AI／Internetへ送らずSpot内で処理できる形態へ進む、(2) RONRO Core／ResearchとProduct Contentを分離する、(3) Live STTとAnalyzerを個別のProvider契約で交換できるようにする、(4) Platformの起動・認証・Session・配布契約を守る、(5) Event／Graph／Canvasの意味と会議中のReplayを保持する、(6) 最終段階でOfflineでも会議中の中核機能を継続可能にする。**Phase 1はCloud STT／Analyzerのままでよく、完全ローカル動作を初期リリースの前提にしない。** Spot直結マイクならより厳格な「Raw AudioがSpot外に存在しない」形態も将来可能だが、スマホマイク版の受入れ条件へ混ぜない。

Non-goals: このRFCで特定のローカルモデル・STTライブラリの性能や製品選定を確定しない。RONRO Coreの全面書換え、PythonからTypeScriptへの一括移植、natadeCOCO Platformの全面再設計、GDKの大規模改名／破壊的変更、機密モードの未検証な提供宣言、Pilot録音の機密モードへの転用をしない。

[Event Catalog](../architecture/discussion-event-catalog.md)の正式な表現を継承する: **Transcript = Evidence、Event Stream = History、Discussion Graph = Current State、Human Correction = Event**。Graphは受理済みEventから導く状態であり、AI候補は自動的に人間が確定した真実にならない。PartialとRaw AudioをCanonical Eventに混ぜない。MaterializerはLLM、Clock、Randomnessに依存させない。

## 3. Proposed Architectureと責務

```text
参加Controllerの押下中だけ有効なマイク（同時最大8台、途中参加可）→ 承認済みローカルWi-Fi／TLS
    → Spotの認可済みContent Audio Ingest（source別の順序・gap・重複管理／VAD）
    → STTProvider ── Final Transcript Evidence
    → RONRO Core Analyzer ── AnalyzerProvider（同一解析推論）
    → CandidateEvent → 検証／受理 → Event Store → Materializer
    → Discussion Graph + Event History → 同一Semantic Canvas（Live / Final）
                                             → GDK Display SDK／Spot大画面
進行役 → Platform認証／Controller Shell → Content Adapter → Human Command Event
Platform: Launcher、認証、Session／run、Realtime Gateway、Catalog、Fleet、Network Policy
AI Runtime: Spot内のSTT／Analyzer実行、またはモードで許可されたRemote接続
```

| Owner | 保持する責務 | 持たない責務 |
| --- | --- | --- |
| RONRO Core (`ronro`) | Evidence／CandidateEvent／Event Schema、Analyzer意味規則、STTのFinal契約、Event Store、Materializer、Replay、Graph、Canvas Projection、評価 | Launcher認証、Spotルーム管理、Fleet、特定ローカルモデル、PlatformのNetworkPolicy |
| Content Adapter (`natade-coco-ronro`) | Python Coreの組込、GDK launch/session/runへの対応、最大8本のController音声取込・整列、Display／進行役UI、Provider選択、一時データ消去、Content health、機密データを出さないログ | Platform credentialの発行、プレイヤーslot／room／reconnectの再実装 |
| GDK / SDK | Manifest検証、Display／Controllerの契約、Platform handoff、互換性検査、リリース証跡 | RONROの意味判断、音声の外部送信可否の最終保証 |
| natadeCOCO Platform | Launcher、本人確認・権限、Session Manager、Gateway、Catalog、Ingress、Fleet／k3s、実効NetworkPolicyと監査 | Transcriptの解析、Canonical Eventの生成、Graphの意味 |
| AI Runtime | モード別STT／Analyzer推論サービス、model load／health／resource limit | Canonical Eventの直接追加、Human確認状態の変更 |

ここでいう「AI Runtime」は**提案上の責務名**であり、GDKに既に共通Local AI Runtimeが実装済みという意味ではない。最初はContent内Adapterとして始めてもよく、複数Contentで共用する必要が確認されてからPlatform共通サービス化を判断する。

Platform SessionとRONRO discussion sessionは同一IDとは限らない。Adapterが対応表と接続世代を持ち、Platformの`playing/terminated`とRONROの`idle/active/paused/finalizing/handoff/failed/purged`を混同しない。`ended_incomplete`相当は完了結果であってphaseではない。中断はContentの取込状態であり、Platform Sessionの終了ではない。Platform Sessionの開始/全体終了は既存ShellのHost操作、RONRO会議の中断・再開・終了・訂正は現時点の認証済み参加者の操作とする。中断は全sourceの取込を停止し、その時点までの確定処理を整合させ、Graph／Display／Join可能なSessionを維持する。再開は新しい取込世代から始め、前世代の遅延Finalを新音声として誤処理しない。会議終了は全sourceを閉じて音声Drain、Queue Drain、Graph revision確定、PDF生成・受取機会、終了画面への切替へ進む。Hostの一時切断や全員の無音・離脱はEnd命令にならない。**会議終了とPlatform SessionのTerminateは別操作**とし、ContentはPDF readyからの期限到達時にだけ内容を消去する。Platformの即時`/control/end`は明示的な強制終了として扱い、実行すると会議不完全/PDF喪失の可能性がある。これをRONRO会議の正常終了やDrain済みの証拠としない。

## 4. Repository strategyと配布

第一候補名は **`hakobune8/natade-coco-ronro`**。候補 `natade-coco-content-ronro` はContent用途をより明示するが長い。`ronro-spot` はPlatformとの関係が曖昧。採番・DNSラベル・Catalog IDは新repo作成時に既存GDK検証器で確定する。

`ronro`は研究正本・評価HarnessとProvider非依存Coreを持ち続ける。新repoはGDKテンプレートを独立repoとして初期化し、UI／Content Adapter／Spot向け実行・配布を持つ。依存方向は `natade-coco-ronro → versioned RONRO Core` と `natade-coco-ronro → pinned GDK/platform set` の一方向。RONROからContent／GDKをimportしない。GDKからRONRO固有コードをimportしない。ローカル／Remote Provider実装はContent側またはAI Runtime側、Coreには契約とテストダブルを置く。

| 共有方法 | 評価 |
| --- | --- |
| 都度コピー | 最初の試作は速いが差分・セキュリティ修正が乖離する。正式方式にしない。 |
| version付きPython package（推奨） | RONRO Coreを明示的に切り出し、固定versionとhash／source SHAでContentが取得。Python backendを維持でき、独立テストとSBOMに載せられる。公開／私有配布先とライセンス適合は後続判断。 |
| Git commit依存 | PoCではpin可能だがbuild再現・監査・サプライチェーン管理が弱い。製品リリースの既定にしない。 |
| vendor snapshot | Offline buildに有効だが更新証跡が必要。GDKの`vendor/platform-set.json`とは別にRONRO Coreのsource SHA／archive hashを記録する。packageと併用可。 |

RONRO Coreの抽出前に現行`prototype`全体をpackage化したと主張しない。`server.py`・OpenAI client・Pilot録音・評価書込みをCore配布へ混ぜず、まず副作用と依存を棚卸しする。GDKのProtocol／Controller SDK／Display SDK／Game Schemaは[platform-setの一括更新契約](https://github.com/hakobune8/natade-coco-gdk/blob/0ba3e224d503b131ab0d7969cc9e7dd82026a364/vendor/platform-set.json)に従う。新Content repoはレビュー済みSHA・SemVer・image digest・SBOM・脆弱性結果・attestationをオペレータに渡し、Fleet配備はPlatform側が承認する。

## 5. AI Provider契約

既存の録音済み音声用[`STTProvider`](../../prototype/stt.py)は`transcribe(audio_path) → STTResult`であり、Live Sessionのstreaming／item相関契約ではない。[`RealtimeTranscriptionClient`](../../prototype/live_stt.py)は`append_audio/commit/receive_until_final`を持つが、現行AdapterはOpenAI特有のVAD・commit itemと密結合する。Analyzerには[`Provider.complete_json`](../../prototype/real_analyzer.py)があるが、Provider交換だけでPrompt／Schema適合が保証されるわけではない。以下は**将来の境界案**で、既存interfaceの改名やSchema変更をこのRFCでは行わない。

```python
class LiveSTTProvider(Protocol):
    async def open(self, *, session_id, source_id, config) -> STTSession: ...
    # STTSession: append(PCMFrame(source_id, seq, local_range)), events() ->
    # Partial | SpeechBoundary | Committed(source_id, item_id, commit_id, audio_range) |
    # Final(source_id, item_id, text, audio_range, provider_time) | ProviderFailure
    # finalize(reason) -> DrainResult(unresolved_ranges, unresolved_items)
    # close(); bounded retry/reconnect contract; duplicate/out-of-order tolerance

class AnalyzerProvider(Protocol):
    def complete(self, *, prompt_version, schema_version,
                 evidence_window, graph_context) -> StructuredProposal: ...
    # CandidateEvent(s) + optional non-Canonical presentation hints + usage/diagnostics
    # Provider has no EventStore/Materializer write permission.
```

STT AdapterはProvider固有item ID、**音声source ID**、ローカルPCM範囲、commit ID／理由、接続世代、Final／duplicate／gapを正規化する。Local STTに`commit`やProvider item概念がなければAdapterが安定したローカルTurn IDを発行し、Provider固有挙動をCoreへ強制しない。PartialはEphemeral、FinalだけがEvidence候補。source IDは端末ストリームの識別であって話者本人の確定ではなく、CanonicalなOwner等へ転用しない。Controllerの押下／解除はsource別の収音区間であり、解除はその区間の安全なFinal化を促すが、Canonical Eventや会議終了を直接生成しない。音声範囲が不明・欠けた場合は**source別**に欠落可能性を記録し、黙って完全なFinalにしない。無発話・BGM・一時切断だけでSessionを終了しない。終了時は全接続sourceの未確定音声と解析待ちを区別してDrainする。

Analyzer Providerは既存の単一解析推論で構造化候補を返す。候補のEvent化、Evidence参照・Schema・Lifecycle・Human correction precedence検査はRONRO側で行う。Local/RemoteのどちらでもPrompt／Output Schema版、Model ID、入力Context policy、timeout、失敗分類、traceに内容を含めないusageを保持する。`supports`／`opposes`／`discussion_provenance`は既存意味を変えず、Relationを時系列だけで捏造しない。候補が不正ならEventを追加しない。Replayは受理済みEventを使い、モデルを再実行しない。

## 6. Execution modeとデータ境界

Modeは実装の環境変数だけでなく、Platformが承認する**実効ポリシー**と対にする。名称は暫定で、現行`game.yaml`に`securityMode`／`security.audioPersistence`欄は**存在しない**。勝手に追加するとSchema検証で拒否される。後続で既存のsandbox profile／NetworkPolicyを優先し、必要最小限の宣言・Admission／Catalog検証をPlatform契約として提案する。

| Mode（暫定） | Audio/STT | Analyzer | Content egress | 使用条件 |
| --- | --- | --- | --- | --- |
| `local-secure`（暫定名） | 参加Controller端末（最大8台）→ローカルWi-Fi→Spot内STT | Spot内 | **Spot Content**のInternet deny。端末→SpotのローカルTLS以外に生音声を送らない | 端末とSpot双方の経路・Policy・ログを実測した場合のみ「Spot内AI処理」と表示。「音声がSpot外に存在しない」とは表示しない |
| `local-stt` | 参加Controller端末→Spot内STT | Remoteへ**Transcript等**送信 | 宛先限定。Raw Audioの外部Provider送信禁止 | 機密性の異なる別モード。Remote契約・送信内容の同意が必要 |
| `cloud-demo` | 参加Controller端末→Spot→Remote STT | Remote | Provider宛先限定 | **最初のGDK統合形態**。生音声とTranscriptの外部送信を明示・同意のうえ開発／デモに使う。機密モードと同じ安全表示をしない |
| `offline` | Spot内 | Spot内 | Sessionの中核処理に外部接続不要 | model/image/auth handoffを事前準備。`local-secure`と同じNetwork denyを求めるなら別途検証 |

`local-secure`の第一候補経路は、**参加スマホの押下中マイク（最大8台）→ ローカルWi-Fi／TLS → Spot上の認可済み音声入口 → Spot内STT → Spot内Analyzer → Spot内Event Store／Graph → Spotの大画面**。各Controllerは自分の音声だけを送る短命・Session／player／source限定権限を受ける。Platform Start/全体終了はHost、RONRO会議操作は現在の認証済み参加者が担う。音声をゲームの方向入力や一般のRealtime Gatewayへ混ぜず、接続先をSpotのローカルoriginに固定する設計とする。Controller SDKの制限付き`game-module`が`getUserMedia`や音声WSSを使えるかは未確認であり、GDK／Platform契約として先に検証する。Browser/OSのマイク権限、端末内の一時バッファ、他アプリやOS機能の保存・送信をPlatformのPod NetworkPolicyだけで保証できない。機密用途では管理・承認済み端末、事前説明、ブラウザ／OS設定の確認が必要で、個人端末の通信全体をRONROが遮断できるとは約束しない。Wi-Fiが切れた際に携帯回線や公開DNS経由へ静かに切り替わるなら**その端末の音声送信を止め**、Sessionはsource別の欠落可能性を表示して再接続待ちにする。他のマイクと議論は継続する。会議室LAN上のDisplay／Controllerが受け取るGraph由来テキストも機密データであり、承認済み端末・TLS・権限境界が必要。Providerのサーバー、モデル取得、メトリクス、Crash dump等の暗黙の外部送信も対象に含める。

### 複数マイクと途中参加

`game.yaml`のRONRO Content設定で`players.max: 8`を宣言する。これはテンプレート値の変更であり、**8台のためだけのGDK Schema拡張は不要**。Sessionの`joinPolicy: while-playing`と、全員が一時離脱しても自動終了しない`emptySessionPolicy: keep-alive`を既存Runtime契約に従って使う。Shared Viewの**右上に小さな参加QR**を開始後・中断中に表示し、Platform既存のJoin Page／Controller handoffへ誘導する。QRにBearer token・音声ticket・再接続handleを入れない。参加前のWi-Fi接続が必要なSpotでは、既存のWi-Fi入場導線とQRの役割を混同せず、同じ1回の案内で参加できる導線をP0.2で実機確認する。QRはCanvasの現在地・種別表示・字幕を覆わず、Final全体図／PDFには含めない。8枠が埋まればJoin Pageで満員を伝え、9台目を静かに置き換えない。再接続はPlatformの同一参加枠を回復し、重複ストリームを作らない。

### スマホの音声入力 — 押して話す

スマホの自動スクリーンロック中に常時収音しているつもりになる事故を避けるため、**各Controllerは大きな「押して話す」ボタンを押している間だけ収音・送信する**方式を第一候補とする。参加直後、ボタンを押していない時、会議中断中はマイクを待機状態にし、バックグラウンド収音や無操作での自動再開をしない。非押下時にはMediaStream track自体を停止することを設計目標とし、単なるPCM送信停止を「マイク停止」と表示しない。端末ブラウザでこの条件と発話開始遅延を両立できなければ、常時track維持を同等の挙動として黙って採用せず、Capture方式を再検討する。押下後もマイク権限・音声接続が確立するまで「準備中」とし、実際にPCMを送れる時だけ「収音中」と示す。権限拒否・端末ロック・画面非表示・接続断・タッチ取消はそのsourceの収音を停止し、明確に「音声を拾えていません」と表示する。押したままロックされてもreleaseイベントに依存せず、Spot側の短い入力lease／接続heartbeat期限で取込を閉じる（無発話だけでは閉じない）。再接続後の自動収音は禁止し、再度押下を要する。

ボタンを離したらそのsourceの現在の音声範囲を確定・Final化へ渡す。空・極短の押下で空commitを強制せず、意味のある未確定音声はbounded finalizeし、危険な空Final／範囲不明を黙って捨てない。複数人が同時に押すことは許すが、source別に処理し、同時発話・近接重複を一つの発話と決めつけない。参加者の会議中断／終了は押下中の全sourceに優先し、中断は音声を止めるだけで会議を終わらせない。Shared Viewの上部状態は、0台押下中なら「発話待ち」、実際に入力中なら「聞いています」、中断中なら「中断中」とし、収音していないのに「聞いています」と表示しない。Controllerにも同じ状態を示すが、Shared Viewに押下操作は要求しない。

これは**スクリーンロック中の取りこぼしをゼロにする対策ではない**。押し忘れた発話はEvidenceにならない。会議参加者が毎回スマホを押す負担、権限取得の開始遅延、長押しのしやすさ、画面ロック／ブラウザ切替時の挙動、3–5mでの共有状態の分かりやすさをP0.2／P1.3で実機確認する。必要な品質・会議への集中を満たせなければ、Spot直結の常時稼働マイクを別Capture profileとして比較し、この制約を隠さない。

Contentの音声入口は**sourceごとの独立したストリーム**としてsequence・接続世代・受信時刻・PCM範囲・VAD／Final／gapを保持する。Spot側の単調時計へ時刻を整列し、全sourceの確定Finalを会議のEvidence順へ統合する。同じ発話が複数スマホに入る近接マイク問題を検証し、確証のない自動混音・重複破棄でEvidenceを失わない。重なった別発話は単一話者だと装わず、重なり／順序不明を診断可能にする。Providerは最大8 source相当の同時処理・backpressure・公平性を支える必要があり、外部STTが同時Sessionを許すかはP0.2で実測する。1台の権限失効・断線・無音・BGM・端末ロックが他の取込や会議Sessionを終了させない。Endでは全sourceを閉じてからDrainし、未解決範囲をPDFへ反映する。Controllerの機器識別は**話者識別ではない**。

| データ | 機密向け既定の保持・転送・削除 | 例外／検証 |
| --- | --- | --- |
| Raw Audio | 各参加スマホとSpotの処理中揮発バッファのみ。端末→Spotの承認済みローカルTLS経路以外へ送らず、アプリのファイル／ログ／Crash dumpへ保存しない。終了・権限失効時にアプリ保持分を消去。 | 端末OS／他アプリの全挙動はRONROから保証できない。既存Pilot録音は**別用途・全員同意・7日・評価担当者限定**で、機密モードへ自動適用しない。 |
| Partial Transcript | 揮発。Canonical Eventにしない。 | UIへの公開可否を最小化。 |
| Final Transcript / Evidence | センシティブ。Session中と終了処理・PDF作成に必要な短い受取猶予中だけ保持し、猶予終了時にSpotから消去する。 | 会議後の完全Replayは提供しない。PDFに必要なEvidence整合性は削除前に検査し、欠落はPDFへ表示する。 |
| Event / Human訂正履歴 | 内容を含むセンシティブデータ。Session中の正本。終了処理・PDF作成・受取猶予が終わればSpotから消去する。 | `Event Stream = History`は稼働中の会議について成立する。PDF受取後の会議後監査・Replayを約束しない。 |
| Graph / Canvas / PDF | 内容を含むセンシティブな派生状態。Drain後の固定revisionからPDFを生成し、現在の当該run参加者のスマホControllerへ権限付きダウンロードとして渡す。受取期限後はSpot上のPDF・Graph・一時ファイルを消去する。 | 会議後Web閲覧・記録一覧・期限後の再ダウンロードは提供しない。スマホへ保存されたPDFと端末バックアップはSpot管理外。座標・`display_label`は非Canonical。 |
| Logs / metrics | 音声・全文Transcript・Evidence・Secretを出さず、接続／Queue／gap／revision等の最小診断値。 | 内容を含む障害調査は明示承認・監査・期限付き。 |
| Evaluation data | 合成を標準。実会議データは別同意、限定保管、公開Gitへ入れない。 | Pilot録音と製品モードを混同しない。 |

既存[RFC-0008](0008-account-based-service-architecture.md)は**アカウント型Webサービスの提案**としてRONRO管理データ7日以内復元不能・PDFのみ共有・終了後訂正なしを定めた。Spot Contentは別の製品形態であり、今回のHuman判断により**7日保存も直近20件保存も採用しない**。RFC-0008本文は当時の判断履歴として残し、本RFCがSpot形態の受取・消去方針を定める。既存Pilot録音の7日ルールは別用途として維持し、将来のSpot Contentへ持ち込まない。Provider側保持・配布済みPDFをSpot管理データと混同しない。PDFは外部持ち出しで回収できない。

Spot Contentに会議後の記録保管機能は設けない。会議中のEvent／Evidence／GraphはPDF作成まで必要であり、終了直後に当該runの認証済み参加者がスマホControllerから各自PDFを受け取るための**短い、上限付きの再試行窓**だけ残す。初期設計値はPDF準備完了から30分で、**期限到達時のみ**認可ticketを失効させ、SpotにあるPDF・Evidence・Event／訂正履歴・Graph・内容を含む一時ファイル／キャッシュを消去する。一人の受取や保存確認で窓を閉じず、参加者向け手動削除を設けない。削除失敗は非内容ログで検知・再試行し、次会議へ内容を見せない。短期一時領域をバックアップ・スナップショット・全文ログから除外し、暗黙の会議後保管を作らない。会議後のWeb閲覧・記録一覧・期限後の再ダウンロード・完全Replayは提供しない。PDFを受け取れず期限が切れた場合は記録が失われるため、Controllerで残り時間・失敗・期限切れを明示する。**現行Platformの`finished`結果表示は最大120秒かつrankings前提なので受取窓には使わない。** Platformは受取窓中`playing`を維持する想定だが、Platform Hostの全体終了は明示的な強制操作として区別し、実行時にはPDF喪失の可能性を示す。Contentがこれを禁止できるとは主張しない。

## 7. Network isolation / Platform policy

既存Platform ChartはゲームPodにIngress/Egress default-denyを適用するが、Kubernetes NetworkPolicyは**Pod境界の一部**にすぎない。承認前の実効テストが必要: CNIのegress実装、同Namespaceの追加Policyの和集合、DNS、Service／Node IP、IPv4/IPv6、hostNetwork、host firewall、Sidecar／推論Pod、ログ転送、container runtime、管理通信、model download。GDK Chartの現状は単一8080コンテナ・Traefik/CatalogからのIngressを想定し、Local AI別PodやPython APIを自動許可しない。必要な同一Spot通信を限定追加し、それ以外を拒否する。**Pod Egress denyはスマホの通信を制限しない**ため、専用ローカルWi-Fi／DNS／Ingress・端末側の送信先固定と経路試験を別ゲートにする。依存が取れないときは`local-secure`開始を**fail closed**にする。

Platformが所有する宣言・適用契約の最小候補は `audioPersistence=deny`、`rawAudioExport=deny`、`egressProfile=spot-local`、許可するSpot内サービスID。これは**提案フィールド**であり現行Manifest schemaではない。既存`game.yaml`の`runtime.offlineCapable`は資産のオフライン能力であってネットワーク遮断の証明ではなく、`capabilities.audio`だけでマイク認可・送信制御を表現できない。先にPlatformの既存sandbox／NetworkPolicy／Admission機構を調べ、重複せず最小拡張する。Manifestの宣言と実際のPod／host政策を照合し、ネットワーク否定試験の証跡を残す。初期`cloud-demo`にも**明示的なRemote Egress許可**が必要で、現行Chartのdefault-denyのままでは動かない。Kubernetes標準NetworkPolicyはFQDN宛先の動的許可を直接表現しないため、Platform管理の限定Egress proxy等を候補として検証し、全Internet宛を安易に開けない。Local Secureへ移る際はこの許可とProvider credentialを取り外すことを検査する。

Spot全体が中央管理面へ接続することと、ContentがInternetへ送れることを分ける。OfflineではSessionを起動・継続・終了できるだけの認証・model・イメージを事前配備し、中央が切れてもContentの必要機能が止まらないことを実機試験する。署名・更新・バックアップの管理経路は独立設計であり、会議内容をそこへ混載しない。

## 8. GDK compatibility / UX mapping

| 分類 | 現行契約とRONROへの扱い |
| --- | --- |
| そのまま活用 | Display SDKの認証済み起動・snapshot、Controller Shell handoff、同一originの`/games/<id>/`経路、最大8枠のManifest指定、`joinPolicy: while-playing`／`emptySessionPolicy: keep-alive`（対応Runtimeに限る）、Platform Join Page、Catalog／Fleet引渡し、pinned platform set、digest／SBOM／attestation、non-root/read-only等の基礎Sandbox。 |
| 小さな拡張が必要か検証 | `kind: Game`のまま使う場合、Content backendへの権限付きHTTP/WSS経路、各Controller moduleのマイク権限とsource限定の短命ticket、長時間・休憩・全source Drain、Contentの状態snapshotの復元、Local AIの明示通信許可を検証する。参加者の会議操作は既存Player照合をContent側で再利用するため、operation別Host権限検査とContent専用終了ガードは初期依存にしない。**8枠指定そのものは拡張対象ではない**。 |
| Game前提が強い／未採用 | 必須`players.min≥1`、controllerProfile選択肢、方向入力・rankings・`finishGame`、result画面・rematch。参加者数をplayer数へ偽装しない。2時間で自動終了させない。必要なら後続で後方互換なInteractive Content profile／別kindを検討し、一括名称変更しない。 |

**Phase 1の前提検証**: Platform HostがSessionを開始し、右上QRから参加者が**会議中に**加わり、1〜8台のControllerが押下中だけ音声を送ってもDisplay・Canvasが継続することを試す。参加者は押して話すことに加え、会議中断・再開・終了・訂正、終了直後のPDF取得を行える。8台同時押下、同じ発話の複数マイク収音、途中参加、1台だけの断線／再接続、全員の一時離脱、9台目拒否、2時間超、全source Drainを分けて検証する。`gameDurationSeconds`は現行GDK説明では情報値であり、RONRO会議EndをGame側`finishGame`やPlatform全体終了と同一視しない。Platformのエラー・空Session・更新時挙動は別途確認する。`keep-alive`はRuntime 1.1以上という[GDKの条件](https://github.com/hakobune8/natade-coco-gdk/blob/0ba3e224d503b131ab0d7969cc9e7dd82026a364/docs/empty-session-policy.md)に従う。

### 会議終了からPDF受取まで

認証済み参加者がスマホControllerで二段階確認を経て会議終了を指示したら、音声取込停止 → STT／Analyzer Drain → 受理済みEvent revision固定 → 同じSemantic Canvasから共有用PDF生成、の順とする。Controllerには全員へ「作成中」「PDFをダウンロード」「生成失敗／再試行」を表示し、Displayは同じCanvasのFinal全体図へ静かに移る。PDFは別の要約LLMが作る新しい記録ではなく、固定Graph revisionからの成果物。Candidate／Confirmed Decision、Open Item、Actionを区別し、`ended_incomplete`相当なら既知の欠落可能時間帯または範囲不明をPDFに明記する。会議後のGraph閲覧画面、記録一覧、クリック式の詳細UIは初期スコープに入れない。

PDF取得APIはPlatformに認可された当該Session/runの現在の参加者へ提供し、マイク用ticketでは取得できないようにする。秘密情報をURLへ置かず、`Cache-Control: no-store`と添付ファイル応答を基本とする。ダウンロード完了のHTTP応答はスマホ内への保存成功を証明しないため、Controllerは各自の受取操作と期限内の再試行を示す。Spotからスマホへ渡したPDFは利用者端末／クラウドバックアップへ保存され得て、Spot側の削除やアクセス失効では回収できない。この外部持ち出しを全参加者へダウンロード前に説明する。一人の取得を他の参加者の受取終了とみなさず、削除は期限到達時のみ。**`finished`もゲーム結果・ランキングもPDF受取には流用しない。**

| RONRO現行画面／機能 | Spot Contentでの割当 |
| --- | --- |
| `/`・`/shared` Semantic Canvas | Display。読み取り専用。同一CanvasのLive local camera／Final zoom-out。開始後・中断中は右上にコンパクトな途中参加QR、上部には実際の収音状態に合わせ「発話待ち／聞いています／中断中」を控えめに表示し、Final/PDFにQRは載せない。 |
| `/session`開始・会議操作・Human Command | Platform Session開始/全体終了は既存ShellのHost操作。RONRO会議の中断・再開・終了・訂正・PDF取得は同一runの認証済み参加者Controllerへ。押して話す導線と会議操作を区別し、Shared Viewには操作を要求しない。 |
| `/control`、評価API、debug情報 | 開発・評価専用。Contentの参加者Ingressから除外。 |
| `/live`音声WSS | 最大8台の認可済みControllerからSpot内originへのContent audio ingressへ適合。source別ticket・TLS・local-route検査を設け、Game controller inputのGatewayを音声transportとして流用しない。 |
| 会議後Web／PDF | 会議後Web閲覧画面は不要。固定Graph revisionから生成したPDFを当該runの認証済み参加者が各自のスマホControllerで期限内にダウンロードする。現行`prototype/service_final_record.py`に決定的なPDF rendererがあり、Spot用の参加者認可・一時保持・受渡しは未受入れ。 |

SpotのLauncher Catalog／Lobbyも利用者体験の一部とし、GDKの任意`presentation`契約に沿って**専用Catalog/Lobby artworkとaccentColorを初期Contentの成果物に含める**。画像はContent配布物としてbundleし、Canvasの背景や実会議結果の代用品にしない。Display／参加者Controller／Host Controllerはそれぞれ[UI / Artworkブリーフ](../product/natadecoco-ronro-ux-artwork-brief.md)の状態・可読性・操作の試験を通す。artworkが揃わない状態をSpot版完成と呼ばない。論路は参加者を評価・監視・競争させるゲームではない。「オープンでクリーン」は会議の一般公開ではなく、AIの暫定解釈を安心して訂正でき、参加者が通常どおり議論できる体験を指す。Speaker別の発言量・順位・押下時間をShared Viewへ出さず、確定していない候補を確定と見せない。PTTが会話を止めるなら中核UX不成立としてCapture方式へ戻り、見た目の改善だけで完了にしない。

## 9. RFC整合・代替案

| 既存記録 | 維持する点／今回の差分 |
| --- | --- |
| [RFC-0001](0001-discussion-model.md)／[0002](0002-realtime-discussion-analysis-pipeline.md)／[Event Catalog](../architecture/discussion-event-catalog.md) | Evidence→候補→受理済みEvent→Graphの一方向性、Partial非Canonical、Replay、Human確認を維持。Providerを換えてもEvent意味は変えない。 |
| [RFC-0003](0003-discussion-map-ux-and-layout.md)／[Canvas評価](../evaluation/semantic-canvas-candidate.md) | 旧6カード等は時点のProposal／履歴。現行実装は同一Semantic CanvasのLive/Final。新repoもこの実装を出発点とし、旧画面へ戻さない。 |
| [RFC-0004](0004-visual-artifact-generation-and-intervention.md)／[0005](0005-meeting-minutes-generation.md) | Visual／MinutesはProposedの別機能。移行の必須依存にしない。会議後PDFは[RFC-0008](0008-account-based-service-architecture.md)のPDF共有方針を継ぎ、Spot上の会議後Web閲覧を必須にしない。AI要約を新正本にしない。 |
| [RFC-0006](0006-discussion-item-references-and-recall.md) | Deferred。項目番号／音声参照解決を本移行で実装しない。 |
| [RFC-0007](0007-service-readiness-improvement-inventory.md)／[0008](0008-account-based-service-architecture.md) | 複数会議・休憩・安全・PDF・ユーザー権限は**対象形態に応じた未承認設計／受入れ課題**。旧Webサービス案の7日保存・起動アカウント帰属、途中案の直近20件保存はSpot Contentへ適用しない。終了直後に当該runの参加者各自へPDFを渡す短い再試行窓だけを設け、期限到達時に内容データを消去する。 |

| 案 | 長所 | 主な欠点 | 判断 |
| --- | --- | --- | --- |
| A. RONROを単独WebサービスとしてProduction化 | 現行経路を活かしやすい | Spot内音声処理・Platform lifecycleとの統合目標を満たしにくい | 今回の主経路にしない |
| B. `ronro`自体をGDK repoへ全面転換 | repoは一つ | 研究資産・Python Core・RFCの役割を混在させ、GDK更新とCanonical変更を結びつける | 採用しない |
| C. 専用`natade-coco-ronro` repo＋一方向Core依存 | Core／Product／Platformの境界を維持し、GDK契約を段階採用できる | package／release互換管理と小さなPlatform契約拡張が要る | **推奨** |

## 10. Migration / implementation plan（段階着手）

各Stepは独立PRを基本とする。前段ゲート未達なら後段の「機密向け」表示・配備をしない。現行Pilotから利用者データを暗黙移行しない。Phase番号は依存順であり、並行可能なテスト作業を禁止しない。**以下の表は2026-10-07時点の移行案を保持した履歴で、Host専用Content操作・終了ガード・手動purgeを含むセルは2026-10-09判断で失効した。現在の実装順・テスト・完了条件は[実装計画](../implementation/natadecoco-content-implementation-plan.md)の改訂節を正とする。**

| Step / repo | Component・変更内容 | Dependency | Test | Completion criteria |
| --- | --- | --- | --- | --- |
| P0.1 `ronro` | 現行Event／STT／Analyzer／Canvasを凍結Baselineとして整理。Final／item／Relation／訂正／Replay／Drainの契約Fixtureと差分検出を整備。 | RFC承認 | 既存全テスト、synthetic replay、機密データを使わない公開Fixture | 同じEvent列→同じGraph／Canvas、既存Pilot挙動無変更 |
| P0.2 `natade-coco-gdk`＋Platform契約repo | 1〜8台のControllerマイク・押下中収音、途中参加QR／Join Page、ホスト専用の開始・中断・再開・会議終了、長時間、権限付きbackend／音声WSS／PDF応答、ローカル経路、Content NetworkPolicyの**互換性スパイク**。8枠指定はManifest設定とし、operation別Host認可・opt-in終了ガードを不足契約としてADR／テストで確定。 | P0.1 | schema検証、`while-playing`＋`keep-alive`実効readback、QR→Wi-Fi→Join、8台接続・9台目拒否、押下でのマイク権限／開始遅延、非押下track停止、画面ロック・タッチ取消・背景化・再接続時の停止と再押下、host/participant権限分離、2時間超、中断中join、`playing`中のPDF取得と誤`/control/end`拒否、携帯回線failover・拒否経路試験 | 8台枠・途中参加・ホスト操作と押下中だけのContent音声経路の契約が確定。8台音声処理の未実測を接続枠テストで代用しない |
| P1.1 `ronro` | Provider非依存Live STT正規化／Analyzer境界を追加し、現行OpenAI Adapterをその実装へ移す。source ID・接続世代・押下／解除の音声範囲・中断／再開cutoffを扱い、Event Schema／Materializerは原則無変更。 | P0.1 | Fake STT／Analyzer、source別item相関、空／極短押下・解除後Final、空Final、重複／順序逆転、gap、中断後の遅延Final、Decision確認隔離、Replay | remote Adapterで現行挙動・全評価Fixtureが回帰せず、source間の誤相関と空commitによる会議終了がない |
| P1.2 `natade-coco-gdk`＋Platform契約repo | P0.2で不足したControllerマイク権限／Session／Chartだけを後方互換で拡張。ホスト権限と参加者音声権限を分離し、Content backend route、source別短命ticket、Drain後のホストController PDF handoff、Content終了ガード、Session snapshot／reconnect、初期Cloud向け限定Remote Egressを成立させる。8枠指定と既存Join契約は再実装しない。 | P0.2, P1.1 | 旧ゲーム回帰＋1〜8台スマホマイク→Content WSS、途中参加、ホストのみ開始／中断／再開／会議終了、PDF取得後のpurge/Platform Terminate・権限失効、終了競合／中断復帰、Remote Egress許可先／拒否先、policy rollback | 既存ゲームを壊さず初期Contentが必要とするPlatform契約が使え、無制限Internet許可が不要 |
| P1.3 `natade-coco-ronro` | GDKテンプレートから独立repoを作り、`players.max: 8`、固定Core package、GDKのpinned platform set、Display Semantic Canvasと右上Join QR、ホスト操作Controller、参加者の押下中収音Controller、source別音声取込・整列、固定revisionのPDF生成・ホストダウンロード、期限付き一時保持と消去を組込む。Python backendは同一Content image内の単一HTTP reverse-proxy配下か、Platform承認の内部Sidecar／Serviceで稼働。Python全面移植なし。Pilot録音と評価APIは既定で無効・非公開。Cloud送信を明示する。 | P1.1, P1.2 | `make validate/test/lint/build`相当、Python tests、HTTP/WSS同一origin、権限、Reload、run ID、UI 1920×1080、途中Join、1/4/8台で押下／解除・近接重複・同時発話・source別gap・空／極短押下・画面ロック・押したまま通信断・中断再開・全source Drain・PDF欠落警告・ダウンロード再試行／期限切れ後の復元否定 | Spot上でCloud STT／Analyzerを使う**明示的cloud-demo**が最大8台の押下中音声を安全に処理し、非押下・ロック中の無断収音なく、入力不能を表示できる。ホスト操作・訂正・Drain・終了直後PDF受取が可能。失敗を隠さず、会議後データを残さない。機密モードとは表示しない |
| P2.1 AI Runtime repoまたは`natade-coco-ronro` Adapter | Local STTをLiveSTTProviderへ接続。最大8 sourceのPCM／Final／gap契約、VAD・bounded fallback、modelのoffline preloadと資源上限を実装。 | P1.1, P1.3 | STT契約Fixture、日本語実音声は同意済み非公開評価、BGM／無音／長発話、近接重複／同時発話、途中参加／再接続、8 source負荷、スマホ／AP／Spotでpacket capture | 各スマホ→Spotのローカル経路以外へRaw Audio送信0、8 sourceの処理性能と欠落可視化を実測。Analyzer RemoteならTranscript送信を明示し`local-stt`と表示 |
| P3.1 AI Runtime repoまたはContent Adapter | Local Analyzerを既存Prompt／Output Schema契約へ接続。Schema不正はfail closed、候補Event受理はCoreのみ。 | P1.1, P2.1 | R1–R5等の構造・安全評価、Human訂正、Owner／Due／Decision非捏造、長時間Queue | 受入れ可能な意味品質・資源／遅延をHuman Reviewし、Cloudなしで議論継続可能 |
| P4.1 Platform契約repo／Fleet | 既存Chart default-denyを基にContent別Egress／Ingress profileを実効化。必要なら後方互換Manifest policyとAdmission検査、Spot内AI通信、スマホのローカル入口・認証、監査・CNI／host否定試験を追加。 | P0.2, P2.1, P3.1 | Internet／DNS／IPv6／Node IP／hostNetworkの否定試験、端末の送信先・携帯回線failover試験、Spot内依存の許可試験、policy drift／rollback | **ここで初めて**限定的な「Spot内AI処理」モードを有効化可能。Policy未適用／不明なら起動拒否 |
| P4.2 `natade-coco-ronro`＋Platform | P1.3の終了直後PDF受渡し・一時消去を機密モード／Offlineでも検証し、バックアップ・スナップショット・Crash dumpに会議内容が残らない境界と、QR／Host／参加者権限を監査する。旧RFC-0008の7日・アカウント帰属、途中案の20件保存とは異なることを説明文に明記。 | P4.1、P1.3 | 非ホストのPDF拒否、期限後の取得／復元拒否、再起動・削除失敗・backup restore否定、8台同時／途中参加／中断・再開／2時間超／Offline実機 | 機密モードでも会議後保管・再ダウンロードなし、PDF受取と一時消去が実証され、残余リスクをHuman Review可能。Preview・Pilot結果をProduction保証と混同しない |

P1の価値検証は**完全ローカルを待たない**。まずCloud経路でGDK上のLive Canvas、途中参加可能な最大8台のControllerマイク、ホスト操作、Session lifecycle、Human訂正、終了Drain・PDF受取を成立させる。P2／P3のLocal推論品質は特定製品・モデルをこのRFCで固定しない。P4のPlatform enforcementは実装作業としてP2／P3と並行設計できるが、**利用者へLocal Secureを約束できる順番**は音声経路と実効隔離の両方の試験後である。Cloud-demoに機密会議データを投入しない。

## 11. Risks、Open Questions、Acceptance Criteria

| Risk | 緩和／止める条件 |
| --- | --- |
| GDKのGame lifecycleが長時間Contentと不整合 | P0.2で実測。人為的なslot維持や`finishGame`偽装で埋めない。最小の後方互換契約変更を先行。 |
| GDKの静的GoサーバーとRONRO Python／2 port構成の差 | 単一origin・単一認可境界のbackend統合を検証し、Pythonを維持。コンテナ／Sidecar案をChartで比較。 |
| Local STT／Analyzerの品質・遅延・資源不足 | 各Provider契約と実会議型評価。到達前はCloud-demoまたは利用停止、機密モードへ自動fallbackしない。 |
| NetworkPolicyの見かけ上のdenyと実際の抜け道 | CNI／host／DNS／IPv6否定試験、追加Policy監査、実効状態とManifest宣言の照合。 |
| スマホマイクはSpot外にある／OSが独自送信し得る | 物理的なSpot内音声限定を主張しない。管理・承認済み端末、ローカルWi-Fi、音声専用ticket、端末/AP/Spotの経路試験。携帯回線failover時はCapture停止。より強い要件にはSpot直結マイクを提示。 |
| Shared Viewの参加QRを第三者が読み取る | QRを参加案内だけに使い、Bearer／音声ticketを含めない。SpotのJoin認可・8枠上限・参加監査を使い、終了時はQRを消す。画面撮影／遠隔配信時の取扱いをHuman運用で明示する。 |
| 8台の近接マイクで同一発話が重複／同時発話が欠ける | source別の音声相関・時刻整列・重複候補診断を実装し、誤って破棄しない。1／4／8台の重なりとSTT／Analyzer処理能力を実測し、8枠の存在を音声品質保証と取り違えない。 |
| 押し忘れ・自動ロック・権限取得遅延で発話を逃す | 押下中のみ収音を第一候補とし、Controller／Shared Viewで実際の入力状態を示す。押下→最初のPCMまでの遅延、長押し負担、ロック／復帰を実機・模擬会議で測り、会議への集中を損なうなら別Capture profileを比較する。入力されなかった発話を記録済みと表示しない。 |
| releaseイベント欠落でマイクが収音し続ける | タッチ取消・画面非表示・権限失効で端末trackを止め、Spotの期限付き入力leaseとheartbeatで停止を保証する。無発話だけでSessionを終了させない。 |
| ホスト中断と終了、途中参加・離脱が競合する | Host専用の冪等Commandと取込世代で制御。中断はSessionを維持し、終了のみ全source Drain。QR参加・再接続・9台目拒否・Host不在を試験する。 |
| Event／Evidenceを会議後削除するとReplayが欠ける | 会議中とPDF固定前のReplayだけを契約とする。終了後の完全Replayは意図的に提供せず、PDFで欠落可能性を説明する。Graphだけ残して監査可能と主張しない。 |
| PDFを受け取る前の端末故障・期限切れ | Controllerに受取猶予と失敗を明示し、最大30分の再試行を許す。期限後の記録は復旧できない。HTTP応答を端末保存成功とみなさない。 |
| Pilot録音／評価書込みの混入 | package境界で除外し、機密モードでは起動時に録音無効・private API非公開を検証。 |
| 旧ゲームのGDK互換を壊す | additive schema／SDK変更＋旧ゲームcontract test。GDK platform setは4件一括でpin。 |

Open Questions（各判断のOwnerはRFC承認時に割当）:

1. 最大8台の参加Controllerの「押して話す」について、Platform Controller Shell／SDKでの`getUserMedia`権限、押下時の開始遅延、非押下時のtrack停止、画面ロック・背景化・タッチ取消、端末OSの保存設定、Wi-Fi／携帯回線の経路切替、source別欠落表示をどう保証するか。毎回の押下負担が会議の自然な発話を阻害しないか。同室の近接マイクによる重複収音と同時発話の処理品質・資源上限は実測前に約束しない。
2. Platform SessionのOrganizerをHost権限へ対応させ、他の最大7台は音声だけ送れるようにできるか。開始・中断・再開・終了の権限と途中参加QR、2時間超、Host一時不在、全source Drainが`Game`互換Profileで成立するか。中断中のJoin Pageと空Session keep-aliveの実効Runtimeをどう確認するか。
3. Content backendのHTTP/WSSをどのPlatform ticket・origin・Ingress経路で認可するか。Display ticketを音声送信権限へ流用しない。
4. Spot内Local AI Runtimeは同Pod／別Pod／host serviceのどれが安全・運用容易か。GPU・モデル配布・署名・容量・offline再起動をどう扱うか。
5. PDF受取はPlatformを`playing`のまま維持し、`finished`を流用しない。opt-in終了ガードと期限後watchdogが配備Platformで成立するか、端末保存失敗／Pod消滅／期限切れでPDFを渡せない場合の表示、期限後の内容消去・backup除外・復元否定を誰が承認・監査するか。会議後記録の保存・再配布は提供しない。
6. 実配備CNI、他NetworkPolicy、host firewall、管理telemetryで`local-secure`のInternet denyを実効保証できるか。証拠の保管と定期再検証は誰が行うか。
7. Offline時にPlatform認証・起動権限をどう検証し、後日の監査／削除要求と整合させるか。

RFC採用・初期実装完了・機密モード受入れの判定を分ける。本RFCの**設計完了条件**は、現行RONRO／GDKと既存RFCの差分、Core／Adapter／Platformの責務、STT／Analyzer interface、最大8台のスマホ→Spot→Local AIの音声・データフローと保証限界、押下中だけの収音／非押下停止、ホスト操作／途中参加QR／PDF受取と消去、実効PolicyのOwner、GDKを壊さない経路、非誘導/非監視のUI/artwork、Phase別テスト・完了条件が説明できること。**初期Cloud-demoの実装完了条件**は、専用Launcher artworkとController/Display UI、PlatformとRONROの結合、source別欠落通知、会議中Replay／期限後消去、1／4／8台の押下中取込・非押下／ロック時の停止、途中参加／9台目拒否、Host中断再開／終了、PDF受取、長時間、3–5m画面Human Reviewと**自然な議論を続けられるかのHuman Review**が検証用Spot実機で通り、残る改善項目が影響・優先度・Owner・次の検証付きで整理されること。P0/P1安全・データ喪失・操作不能・PTTで会話が止まる問題は後続改善へ先送りしない。**機密/Local Secure受入れ**は別にLocal Provider品質、端末/AP/Spot packet capture、Egress拒否・Raw Audio非保存を要する。Cloud-demoの実機PASSだけでは機密会議を許可しない。本RFCの作成だけでどの製品ゲートも満たさない。

## 12. Decision

**推奨案 C — `ronro`をCore／Researchの正本として維持し、独立した`natade-coco-ronro`をSpot向けProduct Contentにする。** GDKの既存契約を優先し、成立しない箇所だけPlatform ownerと後方互換に拡張する。Local／Remote AIの選択はSTTとAnalyzerで独立する。第一候補のCaptureは最大8台の参加スマホControllerによる**押下中だけの収音**。Hostが開始・中断・再開・終了を担い、Shared View右上のQRから途中参加できる。機密向け主張は**各スマホ→Spotの承認済みローカル経路とSpot内AI処理**、端末・Platform双方の実効境界を実測した範囲に限定する。「Raw AudioがSpot外に存在しない」という強い主張はこの形態ではしない。これは**検証中のArchitecture仮説**であり、GDK/Platform変更は各Ownerと契約確認し、本番配備・機密会議利用は別に受入れ判断する。
