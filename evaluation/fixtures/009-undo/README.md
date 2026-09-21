# Fixture 009: Undo

## Purpose

Prototype 1で採用するUndo範囲を最小化し、最新のrename_nodeだけをInverse Eventで戻せることを確認する。

## Input Discussion

- AI: 「MVP範囲」
- Human: Node名を「MVPの中心範囲」へ変更
- Human: 直前のRenameをUndo

## Expected Events

rename_nodeの直後にundo_last_correctionをAppendする。過去Eventは削除しない。

## Expected Graph Behavior

- Revision 4ではLabelがMVPの中心範囲
- Revision 5ではLabelがMVP範囲へ復元
- Node ID、Evidence、全Event履歴は維持

## Requirement / RFC Decision

- RD 16: Human Correction
- RFC-0001: UndoはInverse Event
- Architecture Summary: Prototype 1では最新Human Correctionに限定

## Assumptions

Prototype 1ではrename_nodeだけをUndo対象にする。Merge、Parking Lot、Decision ConfirmのUndoはDeferredする。

