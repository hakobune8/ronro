# Fixture 004: Confirmed Decision to Revoked

## Purpose

Confirmed DecisionをHuman CorrectionでRevokeし、過去のDecisionとEvent履歴を消さずにCurrent Graphから正式Decisionとして除外できることを確認する。

## Input Discussion

- A: 「Visual生成はMVPに含める」
- Human: Confirm操作
- Human: 「やはりMVPでは外す」
- Human: Revoke操作

## Expected Events

AnalyzerはCandidateのみ作成する。ConfirmとRevokeはHuman EventとしてAppendする。

## Expected Graph Behavior

- Candidate → Confirmed → Revoked
- Node IDは全期間で同一
- Revoked NodeはEvent StreamとEvidenceを保持
- Revoked DecisionはMinutesの正式Decisionsへ再導入しない

## Requirement / RFC Decision

- RFC-0001: Decision Revokeは削除ではなくState Transition
- RFC-0005: Revoked Decisionは正式Decisionから除外

## Assumptions

Revoke操作はDecision Nodeを自動的にCandidateやopen_itemへ戻さない。

