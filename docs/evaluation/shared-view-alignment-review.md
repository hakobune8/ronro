# Shared View Alignment Review

## 目的

Live Pilot #1の前に、共有画面がProduct RDの中心価値である「議論の現在地を、参加者が会議中に自然に確認できるDiscussion Map」を保っているかを確認した。

確認したSource of Truthは次の順序である。

1. `docs/requirements/discussion-map-ai-facilitator-mvp.md`
2. `docs/rfc/0003-discussion-map-ux-and-layout.md`
3. `docs/architecture/mvp-architecture-summary.md`
4. `docs/evaluation/m5-ux-review.md`
5. `docs/evaluation/long-session-map-compaction-spike.md`
6. `docs/pilot/discussion-map-live-pilot-guide.md`
7. `prototype/web/index.html` と既存のProjection / Live API
8. `docs/pilot/assets/` の既存UI Screenshot

## 結論

現行の`/`画面は、Developer UIとしては必要な機能を備えている。しかしShared Displayとして見ると、Product Visionを完全には維持していない。

主な理由は、Mapの周囲に次の情報と操作が常時表示されるためである。

- Fixture選択、Replay、Zoomなどの開発操作
- Live Audioの状態・Partial Transcript・Event Log
- Evaluation入力とObserver Marker
- Revision、Session ID、件数ベースのStatus Rail
- Selected Node、Human Commands、Debug JSON

これらは評価・開発・進行役には有用だが、参加者が3〜5m離れて見る共有画面では、議論の内容よりUIの構造と数字が目立つ。Current Topicも右側カードとLaneの両方に分散し、Mapそのものが「会議中の成果物」ではなく、操作可能な管理画面に見えやすい。

したがって、既存のCanonical State、Event、Materializer、Projection、Human Commandを変更せず、Presentation責務だけを分離する。

```text
Canonical Discussion State
        ├─ Shared Discussion View   見るための画面。読み取り専用
        ├─ Facilitator Control View 必要時の修正・確認
        └─ Evaluation / Developer View Metrics・Queue・Debug・Observer
```

## Product Principle

Pilot #1では、次をShared Viewの原則とする。

> Shared Displayは原則として「見る画面」であり、「操作する画面」ではない。

Human Correction Architectureは維持する。ただし、Human-in-the-loopは全参加者が共有画面を操作することを意味しない。修正・確認は既存Command APIを使うFacilitator / Observer側で行い、その結果だけがShared Viewへ反映される。

## RD / RFCとのAlignment

### Product RD

RDは、会議終了後の議事録ではなく、会議中にDiscussion Mapを共有し、参加者が現在の論点、意見、決定、未決事項、Topicの移動を理解することを中心価値としている。また、共有ディスプレイを基本とし、個人端末からの操作はMVPの必須条件ではない。

### RFC-0003

RFC-0003は、Current Topic、Discussion Flow、Candidate / Confirmedの区別、16:9共有ディスプレイ、安定したMap、控えめなProcessing表示を重視している。一方、現行実装はM5〜L6のDeveloper / Evaluation用途を一枚の画面へ積み上げたため、Shared Displayに不要な責務まで露出している。

## 乖離の追跡

| 段階 | 追加されたもの | 現在のUIへの影響 |
| --- | --- | --- |
| RD | 会議中の共有Map、Current Topic、Flow、Human Correction | 共有画面が中心であるべきという原点を定義 |
| RFC-0003 | Map Canvas、Current Topic、Status Rail、Recent Flow、控えめなStatus | 内容と補助情報を分ける設計が定義された |
| M4 | Rename、Merge、Parking、Confirm、ResolveなどのHuman Command | 操作対象とCommand確認のためのDetail領域が必要になった |
| M5 | Stable Lane、Card Stack、Compact表示、Zoom、Replay | 画面を検証するための開発操作と件数表示が増えた |
| Compaction | Current Topic展開、過去Topic要約、Critical Rail | 長時間Mapには有効だが、要約件数がShared Viewへ残った |
| L6 | Evaluation Mode、Marker、Feedback、Metrics、Partial / Final表示 | Pilot計測を一画面で行う構成になった |
| Current UI | 開発・評価・Facilitator・参加者向けの全責務を`/`へ統合 | Dashboard / Control UIとして見え、内容の優先順位が弱くなった |

これは設計の破綻ではなく、Developer UIを先に育てた結果としてPresentation責務が未分離だったことによる収束である。

## 現行要素の分類

### A. Shared View Essential

- Current Topicの内容
- Current Topic配下のIdea / Option / Concern
- 決まりそうなこと（Candidate Decision）
- 確定した決定（Confirmed Decision）
- まだ決まっていないこと（Open Item）
- 次にやること（Action）
- 話の流れ（Recent Flow）
- 過去Topicの控えめな表示
- 最小限のListening / Processing / Updated状態

### B. Facilitator Control

- Decision Confirm / Revoke
- Rename
- Merge
- Parking / Restore
- Current Topic変更
- Open Item Resolve / Reopen
- Action Update
- 必要なNodeの詳細確認

これらは既存画面に残す。新しいCommand Architectureは追加しない。

### C. Evaluation / Developer

- Topic / Node / Candidate / Open / Actionなどの件数
- Revision、Queue depth、Latency、Graph / Render count
- Partial Transcript、Final Transcript、Normalized Utterance
- Evidence ID、Event Log、Graph JSON
- Replay、Fixture、Sequence、Zoom
- Evaluation入力、Marker、Feedback、Post-session Golden

### D. Remove / Defer from Pilot Shared View

- 共有画面上のReplay / Zoom / Fixture操作
- 常時表示のMetric Card
- Selected NodeとCommand Button
- Debug Event Log / Graph JSON
- EvaluationフォームとObserver Marker
- Evidence IDや内部Statusの詳細
- 件数だけを大きく見せるStatus表示

## Shared Viewの採用方針

新しい`/shared`は、既存の`/`を置き換えず、同じBackend Snapshotを読み取り専用で表示するDerived Presentationとする。

- 中央: 現在のトピックと主要な内容
- 下段: 決まりそうなこと、まだ決まっていないこと、次にやること
- 下部: 話の流れ
- 周辺: 過去Topic、あとで話すこと
- 右上: 小さな「聞いています / 整理中 / 更新しました」表示

数字はShared Viewの主役にしない。Canonical Graphに存在するNodeやEvidenceを削除・変更せず、表示する情報量だけを制御する。

## Review Criteria

1920×1080で、次を満たすことを確認する。

- Current Topicの内容が最初に目に入る
- 数字より内容が目立つ
- 共有画面に操作UIがない
- 3〜5mからCurrent Topic、決定候補、未解決事項、Actionが読める
- Candidateが確定済みに見えない
- 話の流れが短く理解できる
- 過去Topicが現在の議論を邪魔しない
- Topic Return時に戻ったTopicが中心へ戻る
- Facilitator側のHuman CorrectionがShared Viewへ反映される
- Shared ViewからCanonical Mutationを送信できない

## 最小変更の判断

変更対象はShared ViewのHTML / JavaScript / Routeと、Pilot Guideの参加者向け説明に限定する。Analyzer、STT、Event、Materializer、Queue、Live Session、Evaluation Metrics、Kubernetes構成は変更しない。

## Before / After

| 区分 | 現行`/`での扱い | Shared Viewでの扱い |
| --- | --- | --- |
| 削除 | 件数カード、Revision、Queue / Latency、Event Log、Debug JSON、Replay / Zoom、Commandボタン | 共有画面には出さない。Developer / Evaluation側で保持 |
| Facilitatorへ移動 | Confirm、Revoke、Rename、Merge、Parking、Resolve、Action Update、Current Topic変更 | 既存Command APIと既存画面を継続利用 |
| Evaluationへ移動 | Partial / Final Transcript、Evidence ID、Marker、評価入力、詳細メトリクス | Evaluation / Developer Viewに限定 |
| 維持 | Current Topic、Idea / Option / Concern、決定候補、未解決事項、Action、話の流れ、過去Topic、Parking | 参加者向けの自然な日本語で表示 |
| 強調 | Current Topicの内容、現在Topicの主要項目、決まりそうなこと、まだ決まっていないこと、次にやること | 1920×1080で内容を最初に読める階層へ変更 |

`/shared`は読み取り専用の参加者向けRouteであり、`/`のFacilitator / Developer画面を置き換えない。Shared ViewのJavaScriptにはCanonical Mutation Commandを持たせず、Backend Snapshotを取得して表示するだけにしている。Facilitator側の修正は既存Live Snapshotに反映され、Shared Viewは次の更新で追従する。

## 画面検証

初回Alignmentでは既存の`ui-large` Demo Scenarioを使ってShared Viewの構造を確認した。Final Passでは、Pilot向けの意味のあるDiscussionを通る`pilot-shared` Demo Scenarioを使い、次の3段階を実画面で再確認した。

- Stage 1: [会議開始](../pilot/assets/shared-view-stage-1.png)
- Stage 2: [議論中](../pilot/assets/shared-view-stage-2.png)
- Stage 3: [議論が進んだ状態](../pilot/assets/shared-view-stage-3.png)

1920×1080の16:9表示で、Current Topicが最初に目に入り、決定候補・未解決事項・Action・話の流れを内容として読めることを確認した。Stage 3では過去Topicを控えめに残し、Parkingを「あとで話すこと」として小さく表示している。画面にはParticipant操作ボタン、件数中心のKPI、内部状態の詳細を置いていない。

Shared View用の読み取り専用Route、Projection入力の非破壊性、内部Command UIの不在を`tests/test_shared_view.py`で確認した。既存Canonical Contract、Analyzer / STT、Queue、Live Session、Evaluation Metrics、Kubernetes構成は変更していない。

## Pilot Gate

本Alignment Reviewと新Shared Viewの1920×1080確認が完了するまで、Live Pilot #1は開始しない。確認後も、Pilotは既存Pre-flightとProtocolに従って明示的に開始する。

## Content-first Final Pass

初回の`/shared`実装を土台に、Pilot #1向けのPresentation refinementを行った。Layout Architecture、Canonical State、Projection責務の分離、Facilitator View、Evaluation Viewは変更していない。

### Final Passの判断

Shared Viewは、UIの構造や件数を見る画面ではなく、議論の内容と現在地を見る画面として整った。主な変更は次のとおりである。

- Fixture-likeな「主要な観点 6」「方針候補 1」のような表示を、意味のある日本語の内容へ置き換えた
- Topic Type、番号、Node ID、件数はShared Viewの表示から除外した
- Idea / Option / Concernは文章を主役にし、左端の控えめな線だけで補助的に区別した
- Current Topicの本文を最も大きく表示し、右側の決定候補・未解決事項・次にやることは淡い背景で支えた
- 余白を維持し、カードを増やして画面を埋めないようにした
- フッターを「普段どおりに話してください。Mapは議論とともに更新されます。」へ簡素化した
- Shared Viewには操作ボタン、Debug情報、Metric、Participant向けの修正要求を置いていない

### Demo Scenario

Pilot用の`pilot-shared` Fixtureは、既存のCanonical Events → Graph → Projection → `/shared`経路を通る。Screenshot専用HTMLへ文章を直接書き込んではいない。

- Stage 1は「MVPで何を実現するか」を中心に、現在の内容、決定候補、未解決事項、次にやることを表示する
- Stage 2は「MVPの範囲 → 画像生成の扱い → MVPの範囲」とTopic Returnを表示する
- Stage 3は「MVPの範囲 → 画像生成の扱い → 料金と運用 → MVPの範囲 → パイロットをどう評価するか」と、さらに進んだTopic Returnを表示する
- Stage 3では、過去Topic、決定候補、未解決事項、次にやること、保留中のオンライン会議連携を同時に確認できる

### 1920×1080 Screenshot Review

実Shared Viewを1920×1080で再取得した。

- [Stage 1 — 会議開始](../pilot/assets/shared-view-stage-1.png)
- [Stage 2 — 議論中](../pilot/assets/shared-view-stage-2.png)
- [Stage 3 — 議論が進んだ状態](../pilot/assets/shared-view-stage-3.png)

3段階とも、Current Topicの内容が最初に目に入り、文章が数字より目立つ。操作UI、Debug情報、Metricはなく、決定候補は`◇`と疑問形で候補のまま表示される。未解決事項と次にやることは内容として読め、話の流れはTopic Returnを含む順序として表示される。Stage 3のParkingは内容がある場合だけ小さく表示される。

Current Topicのカード幅は1920×1080で日本語が自然な1〜2行程度に収まり、縦方向に細く折り返される表示は発生しなかった。3〜5m離れた共有画面で読むことを想定し、右側の色と情報量はCurrent Topicより弱く保っている。

### Before / After — Final Pass

| 観点 | Final Pass前 | Final Pass後 |
| --- | --- | --- |
| 内容 | Node Typeと番号に見えるFixture風ラベルが残る | 内容そのものを表示し、番号・識別子を出さない |
| Metrics | 共有画面の主役になり得る | Shared Viewから除外し、Evaluation / Developer Viewに限定 |
| Category | Idea / Option / Concernの分類が視線を引く | 控えめな左線で補助的に示す |
| Current Topic | 構造の一部として見える | 本文をVisual Centerにする |
| 右側3領域 | 背景と情報量がやや強い | 淡い背景と少ない項目で補助にする |
| Footer | 修正を参加者に意識させる | 普段どおり話すことだけを案内する |
| 操作 | Shared Viewから操作する前提が残り得る | Shared Viewは読み取り専用。修正はFacilitator側 |

### Final Gate

Content-first Final Passとして、1920×1080の3段階で「内容が先に読める」「Current Topicが主役」「決定候補が確定に見えない」「未解決事項とActionが読める」「Topic Returnが分かる」「操作・Debug・Metricがない」を確認した。Canonical Contract、Product Logic、Analyzer、STT、Queue、Live Session、Human Command API、Evaluation Metrics、Kubernetes構成は変更していない。

Shared Viewはpilot-001向けにFreezeできるPresentation状態である。Live Pilot #1自体は、明示的な開始操作と既存のPilot Gateを満たすまで開始しない。

## Public-sector / Engineering Final Pass

Pilot #1で想定する技術協議・業務打合せに合わせ、既存のContent-first Shared Viewへ最後のPresentation refinementを加えた。Layout Architecture、Canonical Graph、Projectionの責務分離、Analyzer / STT、Queue、Live Session、Facilitator View、Evaluation Viewは変更していない。

### 表現の選択

右側3領域の見出しは、参加者が一読して意味を取りやすく、技術協議でも自然な次の表現へ統一した。

- `決定候補` — 候補であることを明示し、補助文「まだ確定ではありません」を添える
- `未解決事項` — 件数ではなく、まだ答えが出ていない内容を表示する
- `次の対応` — 会議後の担当管理を強く想起させず、次に進める内容を表示する

「審議事項」「要処置事項」「懸案管理」のような堅い表現は採用していない。Candidate / Open / Actionの状態は内容と控えめな記号・左線で補助し、分類名が内容より目立たないようにした。

### 視覚調整

右側カードについて、次の3案を比較した。

| 案 | 特徴 | 判断 |
| --- | --- | --- |
| A | 状態ごとに淡い背景色を面で使う | 区別は容易だが、右側が先に目に入りやすい |
| B | 白〜Neutral背景と状態色の左線 | 内容を優先しながら領域を識別できる |
| C | Neutral背景と見出しだけを色付け | 落ち着くが、遠距離では領域の境界が弱い |

Shared ViewではBを採用し、Cの見出しの控えめさを組み合わせた。大きな色面・強い影・KPIカードは使わず、Decision / Open / Actionは色だけに依存しない見出し、記号、文章で識別できる。決定候補は緑やチェックを使わず、`◇`と「まだ確定ではありません」で確定済みとの混同を避けた。

Flowは丸いカード列ではなく、細い区切りと矢印による「話の流れ」として表示する。Topic Returnは同じ内容の再登場として残し、履歴が長い場合は先頭を`…`で省略して直近の軌跡を見せる。CanonicalなFlow履歴は変更しない。過去Topicは小さな中立色のチップへ抑え、現在Topicの内容をVisual Heroとする。

### Five-second / Distance Review

1920×1080のStage 1〜3を、3〜5m離れた会議室の共有ディスプレイとして確認した。5秒で細部を読むことではなく、次の階層が認識できることをAcceptanceとした。

1. 今話していること
2. 主要な論点
3. 決定候補
4. 未解決事項
5. 次の対応

Current Topicの本文が最初に目に入り、右側は補助情報として見える。決定候補・未解決事項・次の対応は件数ではなく内容を表示し、操作UI、Debug情報、Latency、Queue、Revision、内部IDはShared Viewに出していない。Current Topicは日本語の主要項目を1〜2行程度で表示し、縦に細く折り返される状態は発生していない。

### 技術協議の会議室に置く観点

画面全体は白〜薄いNeutralを基調に、青・琥珀・紫・緑を控えめな線と文字へ限定した。これにより、行政資料風の表や強い紺色、KPIダッシュボード、開発者コンソール、付箋ボードの印象を避け、内容が整理された落ち着いた共有画面として見えることを狙った。実際のPilotでは、参加者がMapを一瞬見る場面で現在地が分かるかを観察し、見た目の印象だけで完了とはしない。

### Final Passの変更境界

- 変更したもの: Shared Viewの見出し、背景・左線・余白、FlowのPresentation、Demo Scenarioの表示用Goal
- 維持したもの: Current Topic、Topic Return、決定候補の安全表示、Read-only責務、2秒Render Coalescing、既存Projection入力
- 変更していないもの: Canonical Contract、Event / Materializer、Analyzer / Prompt、STT、Queue、Live Session、Human Command API、Evaluation Metrics、Kubernetes

Shared Viewは`pilot-001`向けのPresentation Freeze候補である。Live Pilot #1は、明示的な開始操作まで開始しない。

## Naming Migration — 論路 / 論点図

Live Pilot #1に向け、参加者向けの名称を次のように確定した。

- Product / Prototype: `論路`（ろんろ / RONRO）
- Shared View / Visual Artifact: `論点図`
- Description: `議論の現在地を共有する`

Shared ViewのHeaderは`論路`、副題は`議論の現在地を共有する`とし、参加者向けの本文・見出し・Footerでは旧称の`Discussion Map`や`Map`を使わない。`論点図`は会議中に画面へ表示される図を指し、参加者には「論路を操作する」のではなく、「論点図を見ながら議論の現在地を共有する」と説明する。

今回のNaming移行で変更した参加者向けSurfaceは、Shared View、Pilot Guide、Pilot Protocol、Participant Feedbackの文言、Live EvaluationのPilot metadataである。Current Topic、決定候補、未解決事項、次の対応、話の流れなどのContent-firstな階層は維持した。

一方、過去のRD / RFC / Evaluation記録、内部Architecture用語、Code Symbol、内部Metric名、既存Route、既存の互換File Pathは変更していない。`Discussion Map`を含む旧ScreenshotもHistorical Artifactとして保持し、最終Guide PDFには含めていない。Guideの既存Pathは既存Link互換性のため維持し、Naming変更は内容と参加者向け表示を優先した。

Naming後の実Shared View Screenshotは次の3段階で取得した。

- [Stage 1 — 会議開始](../pilot/assets/ronro-shared-view-stage-1.png)
- [Stage 2 — 議論中](../pilot/assets/ronro-shared-view-stage-2.png)
- [Stage 3 — 議論が進んだ状態](../pilot/assets/ronro-shared-view-stage-3.png)

3段階とも、`論路`は小さなProduct identityに留まり、Current Topicと論点図の内容がVisual Heroである。Shared Viewに旧称、操作UI、Debug情報、Metricsは表示されず、決定候補は確定済みに見えない。Canonical Contract、Product Logic、Analyzer、STT、Queue、Live Session、Human Command API、Evaluation Metrics、Kubernetes構成は変更していない。

Naming MigrationとVisual確認を完了し、Shared Viewは`pilot-001`向けにFreeze可能な状態と判断する。Live Pilot #1はまだ開始していない。
