# 論路（RONRO）Naming Decision

## Name

- Product / Prototype Name: **論路**
- Reading: **ろんろ**
- Roman notation: **RONRO**
- Primary descriptive phrase: **議論の現在地を共有する**

## Product Meaning

「論路」は、議論の道筋をたどり、どこから来て今どこにいるのか、どの論点へ戻ったのか、何が残り、次にどこへ進むのかを共有する名前である。

## Shared Artifact

論路が会議中に生成・更新し、共有画面へ表示する図を **論点図** と呼ぶ。

利用者向けには、次のように説明する。

> 論路は、会議中の議論を「論点図」として整理し、参加者が議論の現在地を共有するための試作システムです。

必要に応じて、現在の論点、決定候補、未解決事項、次の対応などを発言から整理し、議論の進行に合わせて論点図を更新すると説明する。

## Positioning

論路は、会議が終わった後に読むためのAI議事録ではない。会議中に論点図を見ながら、「今、何を議論しているか」「何が決まりつつあるか」「何がまだ残っているか」を共有することを目指す。

## Naming Hierarchy

| 層 | 利用者向けの呼称 | 内部で維持する呼称 |
| --- | --- | --- |
| Product | 論路 | 既存のDiscussion Map関連のCode Symbol / Routeは維持 |
| Shared View / Visual Artifact | 論点図 | Discussion Graphから生成する既存Projectionを維持 |
| Concept | 議論の現在地 | Current Topic、Discussion Flowなどの内部概念は維持 |
| Internal Architecture | 原則として表示しない | Discussion Graph、Event Stream、Materializer、Analyzer、Projection、Transcript Evidenceなど |

## Pilot Usage

Pilot #1では、共有画面の左上に **論路**、小さな説明として **議論の現在地を共有する** を表示する。画面の主役は論路のブランドではなく、会議中に育つ論点図と現在の議論である。

参加者には次のように案内する。

- 「論路を操作する」ことは求めない
- 共有画面に自動更新される論点図を、ときどき見る
- 「論点図を見ると、今どこを話しているか分かるか」を体験する
- 必要な表示修正は進行役が行う

Shared Viewでは、`Discussion Map`、`Map`、`RONRO`を常時表示しない。初回Guideでのみ「論路（ろんろ）」と読みを添え、RONROは文書の識別・metadata用途に限る。

## File and Historical Policy

参加者へ配布する正規パスは `ronro-live-pilot-guide.md` とPDFとする。既存の `discussion-map-live-pilot-guide.md` とPDFは、外部リンク・生成スクリプト・既存の参照を壊さないため、Pilot #1では同一内容の互換パスとして維持する。内容と表紙タイトルは論路へ更新する。新しいScreenshotは`ronro-shared-view-stage-*.png`として保存し、旧ScreenshotはHistorical Artifactとして残す。

RD、RFC、過去Evaluation、Run ReportなどのHistorical Decision Recordは当時の名称を保持する。必要な場合は、このNaming Decisionへの参照を追加するが、過去文書の用語を遡って書き換えない。

## Search Audit Policy

Repository内の旧名称は、意味に応じて次のように扱う。

- Participant-facing Shared View / Guide / Protocol / Feedback: 論路または論点図へ更新
- Internal runtime metadata: `product_name=論路`、`shared_artifact_name=論点図`を追加し、既存の内部Metric名・Code Symbolは維持
- STT terminology fixtureやAnalyzer回帰Fixture: 当時の入力・評価条件として維持
- RFC、RD、Historical Evaluation: Historical integrityのため維持
- Repository名、Route、Kubernetes resource、Module名: 今回は変更しない

## Non-goals

今回のNaming Migrationでは、次を行わない。

- Internal Architecture全面Rename
- `DiscussionGraph`、`map projection`、Event SchemaなどのCode Symbol変更
- Repository名、`/shared` Route、Kubernetes topologyの変更
- Canonical Schema、Event Stream、Materializer、Analyzer、STTの変更
- 新しいUI FeatureやBranding Areaの追加

## Future Work

Pilot後に必要性を確認したうえで、`Post-Pilot Naming Cleanup`として次を検討する。

- Repository / package / internal routeの整理
- Code Symbolの段階的な別名化
- Historical Documentから現行Guideへの参照整理
- 旧名称を含む技術用語・Fixtureの分類整理

Pilot #1では、参加者向けSurfaceとmetadataだけを論路へ揃え、既存Architectureの安定性を優先する。
