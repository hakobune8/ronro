# Fixture 001: Basic Discussion

## Purpose

最小の正常系として、Transcript EvidenceからTopic、Idea、Current Topic、Relationが生成されることを確認する。

## Input Discussion

- A: 「MVPはDiscussion Mapを中心にしたいです」
- B: 「文字起こしも必要ですよね」
- A: 「必要ですが、中心価値ではないと思います」

## Expected Events

Analyzerは、MVPの中心価値Topic、Discussion Map Idea、文字起こしIdeaを生成する。Topic FocusはMVPの中心価値へ移る。Topicが2つのIdeaをcontainsし、Idea同士はrelated_toで関連付けられる。

## Expected Graph Behavior

- NodeはTopic 1つ、Idea 2つ
- Current TopicはMVPの中心価値
- Topicの重複生成はない
- RelationはTopic contains Idea 2本とIdea related_to Idea 1本

## Requirement / RFC Decision

- RD: Discussion Map、Current Topic、Idea / Opinion
- RFC-0001: GraphはCurrent StateのMaterialized View
- RFC-0002: Final Evidenceを基準にCandidate Eventを生成
- RFC-0003: Current TopicをMap上で強調する

## Assumptions

固定TranscriptはFinal Evidenceとして扱う。Session Lifecycle EventもEvent Streamに含め、Graph Revisionは全ての有効Event適用後に増加する。

