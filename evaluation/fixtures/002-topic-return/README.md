# Fixture 002: Topic Return

## Purpose

一度離れたTopicへ戻るとき、既存Node IDを再利用し、Duplicate Topicを生成しないことを確認する。

## Input Discussion

- A: 「Discussion Mapを中心にしましょう」
- B: 「Visual生成も欲しいですね」
- C: 「価格の話もあります」
- A: 「さっきのDiscussion Mapの話に戻ると…」

## Expected Events

Topic Focusの順序は Discussion Map → Visual生成 → 料金モデル → Discussion Map である。最後の遷移は最初のDiscussion Map Node IDを参照する。

## Expected Graph Behavior

- Discussion Map Nodeは1つだけ
- Topic Returnで新しいDiscussion Map Nodeを作らない
- Current TopicはDiscussion Map
- Recent Flow相当の元データはtopic_focus_changed Eventのsequenceから再現できる

## Requirement / RFC Decision

- RD 9: Discussion Flow
- RD 10: Current Topic
- RFC-0001: Stable Node Identity
- RFC-0003: Recent Topic History

## Assumptions

料金モデルはDiscussion Mapと別Topicとして扱う。Visual生成Topicは別Nodeであり、ArtifactはこのFixtureの対象外とする。

