# RONRO ドキュメント案内

現在の製品名は **論路（RONRO）**、会議中の共有画面は **論点図** です。最初に[README](../README.md)を読み、用途に応じて以下を参照してください。Coreの単独Web PilotとnatadeCOCO Spot向けContentは、実装・配備・データ取扱いが異なります。

## natadeCOCO Spot向けContent

- [Core / Content / Platformの境界と現在の検証状況](architecture/spot-content-current-status.md) — 最初に読む現状整理。実機受入れ・Local Secureは未完了。
- [RFC-0009](rfc/0009-ronro-as-natadecoco-local-ai-content.md) — 移行アーキテクチャと当初の判断。後の操作権限変更は現状整理を優先。
- [Content契約](architecture/natadecoco-content-contract.md)、[PR単位の実装計画](implementation/natadecoco-content-implementation-plan.md) — 初期設計と履歴。Host専用操作、手動削除、Platform終了ガードを必須とした箇所は現在のContent候補と一致しない。
- [UI / Artworkブリーフ](product/natadecoco-ronro-ux-artwork-brief.md) — 制作時の受入れ観点。実際のContent資産と実機結果は別途確認する。
- [Spot向けContentリポジトリ](https://github.com/hakobune8/natade-coco-ronro) — 現行コードとControllerの操作契約。

## Coreの単独Web Pilot

- 参加者向けライブパイロットガイド：[Markdown](pilot/ronro-live-pilot-guide.md) / [配布用PDF](pilot/ronro-live-pilot-guide.pdf)
- 進行役向け：[進行役チェックリスト](pilot/ronro-live-pilot-facilitator-checklist.md)
- 配備・確認：[Kubernetes Pilot Deployment](deployment/kubernetes-pilot-deployment.md)、[Pilot Day Checklist](deployment/kubernetes-pilot-checklist.md)
- 名称と互換性：[論路 Naming Decision](product/ronro-naming.md)
- 安全上の注意：[Security Policy](../SECURITY.md)

## サービス化の過去案・設計履歴

- [RFC-0007](rfc/0007-service-readiness-improvement-inventory.md) — 単独サービス化の課題整理。
- [RFC-0008](rfc/0008-account-based-service-architecture.md)、[Account Service v1設計](implementation/account-service-v1-design.md)、[実装計画](implementation/account-service-v1-implementation-plan.md) — アカウント型Webサービス案。Spot版の現行データ保持・共有・認可契約として読まない。

画面画像は制御された合成会議による表示例であり、実会議の結果やAnalyzerの精度を示すものではありません。現行Semantic Canvasの段階別の例は[パイロットガイド](pilot/ronro-live-pilot-guide.md)にもあります。

## 設計・評価の履歴

[MVP要件](requirements/discussion-map-ai-facilitator-mvp.md)、[UX RFC](rfc/0003-discussion-map-ux-and-layout.md)、[評価記録](evaluation/)は、各時点の判断を追える資料です。旧作業名や、現在とは異なる画面・設定が記録されていても、履歴として保持します。現行設定を確認する際は、これらの過去資料ではなく、コード・[`deploy/kubernetes/base/configmap.yaml`](../deploy/kubernetes/base/configmap.yaml)・上記の現行案内を参照してください。

単独Web PilotのKubernetesアプリケーション名は `ronro-pilot` です。Spot ContentのFleet配布名ではありません。旧 `discussion-map-pilot` は移行元の記録にだけ残します。旧名の参加者向けPilotガイド互換ファイルは廃止し、上記の `ronro-live-pilot-guide` を唯一の配布先とします。その他の歴史的なファイル名や内部シンボルは、製品名と同一にする目的で一括置換しません。
