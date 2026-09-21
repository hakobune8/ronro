# Fixture 008: Current Topic Human Override

## Purpose

Current TopicのSemantic候補とHuman Overrideの責務境界を固定する。単にPricingに関するNodeが追加されても、Current Topicが自動で揺れないことを確認する。

## Input Discussion

- Analyzer: Current Topic = Pricing
- Human: 「いまはMVP範囲の話をしています」
- Analyzer: Pricingに関連するIdeaを検出
- Human: Override対象の「MVP範囲」をParking Lotへ移動
- Human: Restore後に明示的に「MVP範囲」へFocusを戻す

## Policy

Policy Aを採用する。

Humanのset_current_topicは、次に明示的なtopic_focus_changedまたはset_current_topicが適用されるまで優先する。Node検出、Relation検出、Confidenceの高低ではOverrideを解除しない。Override対象がparkedになった場合はprimary_topic_id=null相当へ解除し、restore_from_parking_lotだけでは復帰しない。

Override対象がparkedになったRevisionではCurrent Topicがnullになり、Restore直後もnullのままになる。その後、明示的なset_current_topicでのみMVP範囲へ戻る。Final Current TopicはMVP範囲で、modeはhuman_correctedである。

## Expected Graph Behavior

- Pricing TopicはEvent Streamに存在する
- MVP範囲TopicがHuman OverrideでCurrent Topicになる
- Pricing関連IdeaはPricing Topicにcontainsされる
- Override対象をParkingした時点でCurrent Topicが解除される
- RestoreだけではCurrent Topicへ戻らない
- 明示的なset_current_topicでのみCurrent Topicへ戻る

## Requirement / RFC Decision

- RFC-0002: Current Topic CandidateをAnalysis Pipelineが生成
- RFC-0003: 表示安定化とSemantic判定を分離
- Architecture Summary: Current Topic Human OverrideはEventとして保持

## Assumptions

次の明示的topic_focus_changedまたはset_current_topicを適用するPolicyと、一定時間・Confidenceで自動解除するPolicyは異なる。後者はこのFixtureの対象外であり、Prototype 1では採用しない。
