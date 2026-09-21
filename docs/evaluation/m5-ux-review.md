# M5 UX Review — Stable Discussion Map

## Review status

- Review date: 2026-09-19
- Scope: M5 Stable Discussion Map UI、ui-large、既存Evaluation Fixtures、M4 Human Command Integration
- M6 Fake Analyzer: M5.1レビュー時点では未着手（完了レビューは`docs/evaluation/prototype-1-review.md`）
- Review result: M5.1でMust Fixを解消。M6実装後もM5 UX Contractは維持されている

## Review goal and method

今回の評価対象は「Graphを表示できるか」ではなく、共有ディスプレイ上で参加者が同じMapを見続け、「既存のMapが議論とともに育っている」と認識できるかである。

以下を実施した。

- M5 Developer UIでSession Start、Replay Reset / Step / Play、Node選択、M4 Commandを確認
- 001、002、003、004、007、009、008、ui-largeをブラウザからLoad through EventでReplay
- 003でCandidate DecisionをConfirm、004でConfirmed DecisionをRevoke
- ui-largeをRevision 0からRevision 52までPlayで連続Replay
- ui-largeを1920×1080および2560×1440のViewportで確認
- M5のStableLayout、Map Projection、既存Fixture Testの内容を確認

ブラウザReplay中は、既存Nodeの位置を保持し、Auto pan / zoomが発生しないことも確認した。レビュー中にPrototype、Schema、RFC、Canonical Contractの変更は行っていない。

なお、この環境では開発依存の jsonschema が未インストールだったため、今回のレビュー時点で unittest の再実行は起動前に停止した。M5完了時点の既存テスト結果はGreenとして記録されているが、M6開始前に依存を導入した環境で再実行する必要がある。これはUX判定とは別の環境上の確認事項である。

## Overall result（M5.1実装前の初回レビュー）

| 観点 | 結果 | 所見 |
| --- | --- | --- |
| Current Topic | Pass | Lane、Current marker、Status Railの3箇所で一目で分かる |
| Candidate / Confirmed | Pass | Badge、Icon、Border、Labelが分離され、誤認しにくい |
| Stable Layout | Pass | Node IDを基準に既存位置を保持し、状態変更で再配置しない |
| Topic Return | Pass | 同じLaneへ戻り、Recent Flowにも戻りが残る |
| Human Commands | Pass with limitation | Node Detail経由で実行できる。大規模MapではDetailが下へ押し出される |
| Recent Flow | Pass | 002でTopic遷移とReturnを理解しやすい。5〜7件は妥当 |
| Status Rail | Partial | 要約として有効だが、大規模Mapでは一覧が長く重複する |
| Shared Display | Partial | 2560×1440では収まるが、1920×1080では6Laneの初期一覧が欠ける |
| Map grows | Pass with caveat | 位置関係は育つ。ただし横方向のOverview不足が残る |

## Scenario findings

| Scenario | Replay / Revision | 所見 | 判定 |
| --- | --- | --- | --- |
| Session Start | ui-large / Rev 0 | Header、Goal、Replay操作が見え、空のMapには「StepでTopic Laneが育つ」案内が出る | Pass |
| Basic Discussion | 001 / Rev 9 | 1つのCurrent LaneにTopicとIdeaが積み上がり、Current TopicとFlowが同じ論点を指す | Pass |
| Topic Transition | 002 / Rev 4〜8 | Discussion Map、Visual生成、料金モデルが順にLane化する | Pass |
| Topic Return | 002 / Rev 9 | Discussion Mapの同じNode / Laneへ戻り、Flowが「Discussion Map → Visual生成 → 料金モデル → Discussion Map」になる | Pass |
| Candidate Decision | 003 / Rev 3 | Candidate Badge、◇表示、破線カード、Node DetailのConfirm操作で未確定と分かる | Pass |
| Confirmed Decision | 003 / Rev 4 | UI操作でConfirmするとSolid表示、Confirmed Badge、✓表示、Status Railの件数が更新される | Pass |
| Decision Revoke | 004 / Rev 5 | ConfirmedからRevokedへ変わり、Nodeは消えず、状態LabelとMuted表示が残る | Pass |
| Parking / Restore | 007 / Rev 5〜7 | Parking時にCurrent Topicが解除され、Restoreだけでは戻らず、明示Focusで復帰する | Pass |
| Human Rename | 009 / Rev 4 | Labelだけが変わり、Node ID、Evidence、Lane、位置が維持される | Pass |
| Current Topic Override | 008 / Rev 6〜11 | human_corrected表示、明示変更まで維持、Parking時解除というContractが見える | Pass |
| ui-large | Rev 0〜52 | 6 Topic Lane、Candidate 5、Confirmed 1、Open Item 6、Action 6、Parked 1を表示 | Partial |

## Current Topic evaluation

Current Topicは、次の3つの表示が同時に働くため認識性が高い。

1. Current Laneの青い枠と「CURRENT」marker
2. 右側Current Topicカード
3. Lane内のTopic CardとStatus Railの表示

Basic、Topic Return、Current Topic Overrideでは、一見して現在の論点を特定できた。Topic Return時にも全体Mapは動かず、戻ったLaneだけがCurrentになるため自然である。Human Overrideは human_corrected と表示され、Derived状態と混同しない。

一方、5秒以内という時間目標は、M6 AnalyzerによるLiveなTopic切替がまだないため、厳密には未測定である。M6では頻繁なfocus eventを与え、Current Topicがちらつかないことを検証する必要がある。これは現時点のUI欠陥ではなく、M6のValidation Parameterとする。

## Stable Layout evaluation

| 操作 | 確認結果 |
| --- | --- |
| New Node追加 | 既存NodeのPositionを保持し、新しいCardだけを末尾に追加 |
| Rename | 009 Rev 3→4でNode ID、Lane、Order、位置を維持 |
| Confirm / Revoke | 003 Rev 3→4、004 Rev 4→5でCard位置を維持 |
| Topic Return | 002 Rev 6以降で元Topic Laneへ戻り、元位置を維持 |
| Parking | 007 Rev 4→5でParking Laneへ移動するが、home lane / orderを保持 |
| Restore | 007 Rev 5→6で元Lane / Orderへ戻る。Current Topicへは自動復帰しない |
| Merge | 006でTarget位置を維持し、SourceはArchived Historyへ送る |
| Replay | ui-large Rev 0→52でViewのScroll位置は自動変更されない |

Map Canvasには全体再配置、Fit-to-screen、Current Topicへの自動Centeringがない。この制約が、既存の関係を追える安定性につながっている。

## Information density and ui-large（M5.1実装前の初回レビュー）

ui-largeの最終状態は、6つのMain Topic Laneと1つのParking Laneを持ち、各Main Laneはおおむね6〜7枚のCardを持つ。Status RailにはDecision 6件、Open Item 6件、Action 6件が同時に列挙される。

1920×1080での実測値は次のとおりである。

- Map viewportの表示幅: 1568px
- Lane contentの幅: 1778px
- Lane幅: 284px
- 初期表示: 5Laneは完全表示、6Lane目は一部表示
- Map本体は横スクロール可能
- Status Railは長い一覧により、下部のSelected Node / Human Commandsが画面下へ押し出される

したがって、6Laneを同時に理解するという観点では未達である。6Lane目が存在することは分かるが、初期表示だけでは全LaneのHeaderと内容を同時に比較できない。2560×1440では6LaneがMap領域内に収まり、Overviewとして成立する。

Lane Collapseは有効であり、不要Laneを縮退すれば状況を整理できる。ただし初期状態では全LaneがExpandedであり、参加者が会議中に手動で整理することを前提にしている。

## Candidate / Confirmed Decision evaluation

CandidateとConfirmedは以下の複合表現で区別できる。

- Candidate: Candidate Label、◇、破線、淡い警告背景
- Confirmed: Confirmed Label、✓、実線、緑系の左Border
- Revoke後: Revoked Label、Muted表示、Nodeは履歴として残る

Confirm操作はNode Detailを開いた後に表示されるため、Candidateが会議を強く誘導する状態にはなっていない。Candidateを直接Confirmed Decisionとして読んでしまう余地は小さい。

## Recent Flow evaluation

Recent FlowはGraph Relationを代替せず、Topic Focus Eventから導出された補助Stripとして機能している。002のTopic Returnでは、Mapの空間的な戻りと、時間的な戻りを別々に確認できる。

ui-largeでは6件のFlowが表示され、情報量は許容範囲だった。現在の最大7件は維持してよい。5〜7件を初期値とし、M6でTopic切替が増えた場合のみ、古い項目を省略する検証を行う。

## Status Rail evaluation

Current Topicと6つのMetricは、Mapを補助するSummaryとして有効である。特にDecisionのCandidate / Confirmed件数、Open Item、Action、Parked件数はMapを読まずに状態の概況を把握できる。

ただし、ui-largeではStatus RailがDecision、Open Item、Actionの全件を列挙するため、Map Cardとの重複が大きい。長い一覧がSelected NodeのDetailとCommandを下へ押し出し、Human Correctionの操作経路を重くする。

推奨は、M6中に各一覧を上位3〜5件またはCurrent Topic関連に絞り、残りを「+N more」または選択時のDetailへ送ることである。Metricは常時残す。

## Parking / Archive evaluation

ParkingはMain Laneとは別の破線Laneに分離され、Parked状態もLabelとTypeで分かる。Parking時にCurrent Topicが解除され、Restoreだけでは自動復帰しないため、Canonical Contractとの整合も良い。

大規模MapではParking LaneがMain Mapの下側にあり、Map内スクロールが必要になる。完全に見失うわけではないが、Parkingされた論点を戻す操作は、Parked件数のSummaryまたは常時見える入口があると軽くなる。

## Human Command evaluation

Nodeを選択してNode Detailを開き、そこからConfirm、Revoke、Rename、Merge、Parking、Restore、Set Current Topic、Action Updateを実行する流れは、Developer Prototypeとして適切である。操作対象が明確で、Map Stateを直接MutationしていないこともM4のEvent Logで追跡できる。

Confirm / Revokeは1回の明示操作で完了し、Candidate / Confirmedの誤操作を起こしにくい。Rename、Parking、Current Topic変更もContextual Commandとして常時表示のボタン数を抑えている。

大規模MapではSelected NodeがStatus Railの長い一覧の後ろに配置されるため、Commandに到達するためのスクロールが必要になる。M6中にDetailの位置を上げる、または選択時にStatus Rail内で優先表示することをShould Fixとする。PromptベースのRename / Action UpdateはDeveloper PrototypeとしてCan Deferする。

## Shared display readability and motion

1920×1080で、CardのLabelは13px、Lane Headerは14px、Current Topicは16pxで表示される。TypeとStatusは、色だけでなくIcon、Text Label、Border Styleを併用しているため、基本的な判別性は確保されている。

文字やCardは離れた位置からの共有ディスプレイ利用として許容範囲だが、Status Railの小さい一覧を遠距離から読むことは主目的にしない方がよい。Main MapのTopicとCurrent Topicカードを優先する構造は妥当である。

Replay中はNew NodeのFadeや全体移動がなく、Status変更も静的なBadge更新に留まる。ui-largeをRev 0からRev 52までPlayしても、Scroll位置は自動変更されず、注意を奪うMotionは確認されなかった。

## “Map grows” test

Revision 0から52まで連続Replayした結果は次のとおりである。

- Rev 0: 空のMap
- Rev 3: MVP範囲Laneが追加
- Rev 9: MVP範囲LaneがCardを増やし、Current Topicが表示
- Rev 15: Discussion Map Laneが追加
- Rev 27: Visual生成Laneが追加
- Rev 52: 6つのMain Lane、Parking Lane、Decision / Open Item / Actionが揃う

Laneの追加は既存Laneの位置を変えず、Cardは同一Lane内へ積み上がる。Current Topicが移っても青いHighlightだけが変わり、既存のMapを描き直した印象は弱い。

よって「Mapが育つ」体験は成立している。ただし1920×1080では横幅の限界により、成長後の全体像が初期Viewportに収まらない。安定性は保たれているが、Overviewが不足しているという評価である。

## Review classification

### Must Fix Before M6

#### MF-01: 1920×1080で6LaneのOverviewを確保する

この指摘はM5.1で解消済み。以下の「M5.1 Follow-up Review」を参照。

M6でAnalyzerを接続するとTopicとCardが増えるため、現状のままでは新しいLaneがすぐに横スクロールの外側へ押し出される。M6前に、次のいずれかをMVP最小変更として決めて実装する必要がある。

- Current Lane以外をCompact Header / 件数表示へ縮退する
- Map上部に全Lane Headerを一覧するOverview Stripを追加する
- 非Current Laneの初期表示を折りたたみ、参加者が必要なLaneだけ展開できるようにする

条件は、Auto pan / zoomを導入せず、既存NodeのPosition Contractを維持すること、1920×1080で全Laneの存在とCurrent Topicを同時に把握できることである。

### Should Fix During M6

- SF-01: Status RailのDecision、Open Item、Action一覧を上位3〜5件またはCurrent Topic関連に制限し、残数を表示する
- SF-02: Selected Node / Human Commandsを大規模Mapでも画面内から発見しやすくする
- SF-03: Parking Laneを縮退表示し、Parked件数からRestore入口へ到達しやすくする
- SF-04: Live Analyzer接続時のCurrent TopicのHysteresis / Cooldown / 頻度を検証する
- SF-05: jsonschemaを含む開発環境でM1〜M5のRegression Testを再実行する

### Can Defer

- Reactや別Frontend Frameworkへの移行
- Production Design System、細かなVisual Polish
- Evidence全文Drawer、Speaker表示の詳細
- AI Observationの実表示
- 高度なGraph Editor、Drag & Drop、Free Graph Layout
- Pixel-perfect Browser E2E、Mobile対応、Production Persistence
- Candidateへの複数確認フローや高度なUndo UI

## M6へ進めるか（M5.1実装前の初回判定）

現時点では、**Must Fix MF-01を解消または明示的に受け入れるまではM6開始不可**と判定する。

M5のCanonical Contract、Stable Position、Current Topic、Decision表示、Recent Flow、M4 Command経路はM6へ進める基盤として十分である。MF-01を最小のCompact Overviewまたは初期Lane縮退で解消し、開発依存を導入してRegression Testを再実行できれば、M6 Fake Analyzerへ進める状態になる。

### M6開始条件

1. 1920×1080のui-largeで全Laneの存在とCurrent Topicを同時に把握できる
2. Auto pan / zoomなしで既存Node位置が維持される
3. M1〜M5のRegression Testが依存導入済み環境でGreenになる
4. Live相当の頻繁なTopic切替をM6のValidation Fixtureで評価する

## M5.1 Follow-up Review

### 採用した方式

Canonical GraphやEvent Streamへ変更を加えず、M5のMap ProjectionにLaneごとの要約値を追加し、HTML/JavaScriptのPresentation Stateで表示密度を制御した。

- Current Topic Lane: Expanded
- Non-current Topic Lane: Compact
- Compact内容: Topic名、Lane状態、Decision件数、Open Item件数、Action件数、Candidate / Confirmed / Parked Badge
- Parking / Archived: 初期はCompact。必要ならLane単位で手動Expand可能
- Current Topic変更: 新Current LaneだけをExpandedにし、他Laneの順序・Node ID・CanvasのScroll位置を変更しない
- Expand / Compact、Scroll、Zoom、Selected Node: Canonical Graphへ保存しないPresentation State

### 1920×1080確認結果

ui-large Revision 52を1920×1080相当で再確認した。

- 6つのTopic Headerが同時に表示された
- Current Topic「Evaluation」はExpanded、青いBorder、CURRENT marker、Status Railで判別できた
- 5つのNon-current LaneはCompactになり、Decision / Open / Action件数が読めた
- Parking LotもCompact Laneとして同じOverview内に表示された
- Map viewportの表示幅は1568px、Compact適用後の内容幅も1568pxで横スクロールが発生しなかった
- Current Topic Laneの詳細Cardは通常サイズを維持し、Compact化のための極端な縮小は行っていない

### Manual Expand / Topic Return

Discussion Map以外のLaneをExpandすると、そのLaneだけがCard Stackへ展開され、Canonical Graph JSONは変更されなかった。Topic Returnでは002のRev 6でVisual生成Lane、Rev 9でDiscussion Map LaneがCurrent / Expandedへ戻り、Recent Flowは既存どおり「Discussion Map → Visual生成 → 料金モデル → Discussion Map」と表示された。

ui-largeをRevision 0から52までPlayした場合も、最終状態は5つのCompact Topic Lane、1つのExpanded Current Topic Lane、1つのCompact Parking Laneとなり、Scroll位置は0のままだった。

### M5.1判定

MF-01は解消した。M5 UX ReviewのMust Fixは残っていない。Canonical Contract、Schema、Event Stream、Discussion Graph、Node Position Contractは変更していない。

M1〜M5のRegression Test 29件はGreen。M5.1追加テストでは、6 Lane要約、Current / Non-current表示Policy、Presentation Stateの非Mutation、既存Position保持、Topic Return、Replay Determinismを確認した。

したがって、M6 Fake Analyzerへ進める状態になった。ただし、ユーザー指示に従い、この作業ではM6実装を開始していない。
