# RONRO ドキュメント案内

現在の製品名は **論路（RONRO）**、会議中の共有画面は **論点図** です。最初に[README](../README.md)を読み、用途に応じて以下を参照してください。

## 現行の案内

- 参加者向けライブパイロットガイド：[Markdown](pilot/ronro-live-pilot-guide.md) / [配布用PDF](pilot/ronro-live-pilot-guide.pdf)
- 進行役向け：[進行役チェックリスト](pilot/ronro-live-pilot-facilitator-checklist.md)
- 配備・確認：[Kubernetes Pilot Deployment](deployment/kubernetes-pilot-deployment.md)、[Pilot Day Checklist](deployment/kubernetes-pilot-checklist.md)
- 名称と互換性：[論路 Naming Decision](product/ronro-naming.md)
- 安全上の注意：[Security Policy](../SECURITY.md)
- サービス化に向けた課題整理：[RFC-0007](rfc/0007-service-readiness-improvement-inventory.md)（Draft。設計・提供の承認ではありません）
- サービス化の設計案：[RFC-0008](rfc/0008-account-based-service-architecture.md)（Human Review待ち。未実装）
- サービス化の実装設計案：[Account Service v1](implementation/account-service-v1-design.md)（Human Review待ち。現行Pilotには未適用）
- サービス化の実装計画：[Account Service v1 Plan](implementation/account-service-v1-implementation-plan.md)（開発順序と受入れゲート。未実装）
- natadeCOCO Spot向けContent移行：[RFC-0009](rfc/0009-ronro-as-natadecoco-local-ai-content.md)（段階実装に着手。Platform契約・配備・機密会議利用は別ゲート）
- RFC-0009の実装用詳細：[Content契約](architecture/natadecoco-content-contract.md)、[PR単位の実装計画](implementation/natadecoco-content-implementation-plan.md)（PR1着手、実機未検証）
- Spot版の画面・専用artwork：[UI / Artworkブリーフ](product/natadecoco-ronro-ux-artwork-brief.md)（制作・実機確認前）

画面画像は制御された合成会議による表示例であり、実会議の結果やAnalyzerの精度を示すものではありません。現行Semantic Canvasの段階別の例は[パイロットガイド](pilot/ronro-live-pilot-guide.md)にもあります。

## 設計・評価の履歴

[MVP要件](requirements/discussion-map-ai-facilitator-mvp.md)、[UX RFC](rfc/0003-discussion-map-ux-and-layout.md)、[評価記録](evaluation/)は、各時点の判断を追える資料です。旧作業名や、現在とは異なる画面・設定が記録されていても、履歴として保持します。現行設定を確認する際は、これらの過去資料ではなく、コード・[`deploy/kubernetes/base/configmap.yaml`](../deploy/kubernetes/base/configmap.yaml)・上記の現行案内を参照してください。

Kubernetesの現行アプリケーション名は `ronro-pilot` です。旧 `discussion-map-pilot` は移行元の記録にだけ残します。旧名の参加者向けPilotガイド互換ファイルは廃止し、上記の `ronro-live-pilot-guide` を唯一の配布先とします。その他の歴史的なファイル名や内部シンボルは、製品名と同一にする目的で一括置換しません。
