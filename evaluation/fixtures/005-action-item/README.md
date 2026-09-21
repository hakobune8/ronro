# Fixture 005: Action Item

## Purpose

Actionとして扱う発言と、単なる提案・可能性を区別する。OwnerとDue Dateを推測せず、Transcript Evidenceに明示された場合だけAnalyzer生成時に設定できること、Human Commandで後から修正できることを確認する。

## Input Discussion

- Case A: 「次回までにVisual Prototypeを作ります」
- Case B: 「Visual Prototypeも作った方がいいかもしれません」
- Case C: 「山田さん、2026-09-25までにPrototypeお願いします」

## Expected Events

- Case Aはaction Nodeを生成する
- Case Bはopen_itemとして記録し、action Nodeを生成しない
- Case Cはaction Nodeを生成する
- Case CのOwner / Dueは、Evidenceを参照するAnalyzerのnode_detected Payloadで生成時に設定する
- Human update_actionは、生成後のDue Date修正を表す

## Expected Graph Behavior

- Action A: descriptionのみ、owner=null、due_date=null
- Case B: open_item
- Action C: 生成時点ではowner=山田さん、due_date=2026-09-25。Human Correction後のFinal Graphではdue_date=2026-09-26
- いずれのOwner / Dueも、発言者や会議慣行から推測しない

## Requirement / RFC Decision

- RD 8.8: Action Item
- RFC-0001: ActionはDecisionと別のLifecycle
- RFC-0005: Owner / Due Dateを推測しない
- Architecture Summary: Actionは抽出時点で存在させ、Owner / DueはEvidenceまたはHuman Correctionでのみ設定する

## Assumptions

node_detected Payloadのaction.owner / action.due_dateは必須フィールドとして保持する。非null値はEvent Envelopeのsource_evidence_idsで根拠を追跡し、明示されない値はnullとする。Human update_actionはEvidenceがなくても明示的な修正Commandとして値を設定・修正できる。Final GraphではHuman CorrectionがAnalyzer由来値に優先する。
