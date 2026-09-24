# RONRO ドキュメント案内

現在の製品名は **論路（RONRO）**、会議中の共有画面は **論点図** です。最初に[README](../README.md)を読み、用途に応じて以下を参照してください。

## 現行の案内

- 参加者向け：[ライブパイロットガイド](pilot/ronro-live-pilot-guide.md)
- 進行役向け：[進行役チェックリスト](pilot/ronro-live-pilot-facilitator-checklist.md)
- 配備・確認：[Kubernetes Pilot Deployment](deployment/kubernetes-pilot-deployment.md)、[Pilot Day Checklist](deployment/kubernetes-pilot-checklist.md)
- 名称と互換性：[論路 Naming Decision](product/ronro-naming.md)
- 安全上の注意：[Security Policy](../SECURITY.md)

画面画像は制御された合成会議による表示例であり、実会議の結果やAnalyzerの精度を示すものではありません。現行のFocused Flowの例は[パイロットガイド](pilot/ronro-live-pilot-guide.md)にもあります。

## 設計・評価の履歴

[MVP要件](requirements/discussion-map-ai-facilitator-mvp.md)、[UX RFC](rfc/0003-discussion-map-ux-and-layout.md)、[評価記録](evaluation/)は、各時点の判断を追える資料です。旧作業名や、現在とは異なる画面・設定が記録されていても、履歴として保持します。現行設定を確認する際は、これらの過去資料ではなく、コード・[`deploy/kubernetes/base/configmap.yaml`](../deploy/kubernetes/base/configmap.yaml)・上記の現行案内を参照してください。

Kubernetesの現行アプリケーション名は `ronro-pilot` です。旧 `discussion-map-pilot` は移行元の記録にだけ残します。一方、互換ファイル名や内部シンボルは参照を壊さないため維持しており、製品名と同一にする目的で一括置換しません。
