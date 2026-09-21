"""Realistic synthetic 30-minute Recorded Discussion dataset.

The transcript is deliberately kept outside the five-scenario Golden dataset.
It is a product-level density and readability workload, not a replacement for
the frozen analyzer benchmark.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


SESSION_ID = "recorded-30min-discussion-map"
DATASET_VERSION = "recorded-30min-discussion-v1"
START = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)


PHASES: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "opening",
        (
            ("A", "今日は、会議中にDiscussion Mapを見ながら議論を進めるMVPの形を決めたいです。"),
            ("B", "今どの論点にいるかが共有画面で分かるのが、中心価値だと思います。"),
            ("C", "これまでの話をその場で整理して、参加者が自分で修正できるのも大事ですよね。"),
            ("A", "うーん、まずは聞きながら全部を書き出すより、意味のある論点だけ見たいです。"),
            ("B", "スマホ側も何か必要になるんじゃないですかね。"),
            ("C", "ただ、同時操作が増えると会議が複雑になりそうです。"),
            ("A", "共有ディスプレイなら全員が同じものを見られます。"),
            ("B", "Mapは議論を止める管理画面ではなく、話し合うための補助ですよね。"),
            ("C", "それをどう測るかは、まだ決めきれていないです。"),
            ("A", "そうですね、そこは後で戻りましょう。"),
        ),
    ),
    (
        "mvp-scope",
        (
            ("B", "スマホUIはMVPから外す案でどうでしょう。"),
            ("C", "それでいきましょう。"),
            ("A", "そうすると最初の画面は共有ディスプレイ中心で考えられます。"),
            ("B", "参加者の手元は見なくても、Mapの状態が追えればよさそうです。"),
            ("C", "ただ、遠い席から文字が読めないのは心配です。"),
            ("A", "スマホを入れた方が便利だと思う場面もありますけど、今回はそこまでしなくていいと思います。"),
            ("B", "いったん対象外にして、必要なら次のフェーズで考えましょう。"),
            ("C", "決めたことと、まだ候補のことは見た目で区別したいです。"),
            ("A", "次回までに画面のたたき台を作ります。"),
            ("B", "了解です。"),
        ),
    ),
    (
        "map-layout",
        (
            ("C", "次はMapのレイアウトについて考えましょう。"),
            ("A", "Topicを横に並べて、今のTopicだけ少し詳しく見せるのがよさそうです。"),
            ("B", "Laneの中はカードの積み重ねで十分かもしれません。"),
            ("C", "それなら既存のカードが毎回動かなくて済みますね。"),
            ("A", "一方で、新しい話題が増えたときに全部が小さくなるのは懸念です。"),
            ("B", "Current TopicはStatus Railにも出しましょう。"),
            ("C", "今のTopic以外は、件数と重要な状態だけのCompact表示でよいと思います。"),
            ("A", "A案は全Laneを同じ大きさで表示する方法です。"),
            ("B", "B案は今のLaneをExpandedにして、他は縮退させる方法です。"),
            ("C", "共有画面ではどちらが追いやすいですか？"),
        ),
    ),
    (
        "compact-policy",
        (
            ("A", "共有ディスプレイでは、今のLaneを広くして他は縮退する案でどうでしょう。"),
            ("B", "その方針で進めましょう。"),
            ("C", "ただし、縮退したTopicが存在することは常に見えていてほしいです。"),
            ("A", "そうですね、名前とDecision、Open Item、Actionの数は残しましょう。"),
            ("B", "30分話した後でも、最初の論点が見つかるかは確認したいです。"),
            ("C", "Current Topicが変わっても自動で画面を飛ばさない方がよさそうです。"),
            ("A", "Topicに戻ったとき、同じLaneに戻ったと分かるのが大事ですね。"),
            ("B", "まあ、アニメーションは控えめでいいと思います。"),
            ("C", "レイアウトの試作を作って、既存Nodeの位置が保たれるか確認します。"),
            ("A", "わかりました。"),
        ),
    ),
    (
        "visual-artifact",
        (
            ("B", "Mapだけではイメージを共有しにくい話もありますね。"),
            ("C", "次にVisual Artifactの扱いを考えたいです。"),
            ("A", "抽象的なサービス像はConcept Imageにすると話しやすいかもしれません。"),
            ("B", "生成したVisualは正式な答えとして扱うんですか？"),
            ("C", "AIの画像がきれいだと、そちらへ議論が引っ張られるのが心配です。"),
            ("A", "自動で出すより、必要なときにGenerate Visualを押す方が安全です。"),
            ("B", "そうですね。"),
            ("C", "Architectureの構成はDiagramにした方が、画像より正確に共有できそうです。"),
            ("A", "MapからVisual Viewへ行って、またMapへ戻れる流れがよいと思います。"),
            ("B", "Visual生成は手動トリガーで進める案でどうでしょう。"),
        ),
    ),
    (
        "visual-policy",
        (
            ("C", "そうしましょう。"),
            ("A", "ただ、生成中もSTTとDiscussion Analysisは止めない前提です。"),
            ("B", "完成したら勝手に画面を奪わず、通知だけ出すのがよいですね。"),
            ("C", "生成物が今のDiscussionとずれていたら、元TopicとRevisionを確認できるようにしたいです。"),
            ("A", "一案だけだとAnchoringが強いので、必要なら複数案も考えたいです。"),
            ("B", "でも毎回二案出すと待ち時間とコストが増えますね。"),
            ("C", "MVPでは、いつ複数案にするかを決める必要があります。"),
            ("A", "その判断はまずPrototypeで見てみましょう。"),
            ("B", "次回までにVisual ViewのStatic Mockを作ります。"),
            ("C", "なるほど。"),
        ),
    ),
    (
        "architecture",
        (
            ("A", "話を実装の流れに戻して、Analyzerの構成を確認しましょう。"),
            ("B", "音声は最終的にはSTTですが、今はRecorded Transcriptからでよいです。"),
            ("C", "AnalyzerはCandidate Eventを返すだけで、Graphを直接変更しないことにしましょう。"),
            ("A", "Event Streamを履歴として残して、GraphはそこからMaterializeします。"),
            ("B", "Partial Transcriptでは正規Graphを更新しない前提でしたね。"),
            ("C", "途中の認識が揺れてMapが動くと、会議が止まるのが心配です。"),
            ("A", "Finalized Utterance単位でAnalysisする方が追いやすそうです。"),
            ("B", "この構成の方がよさそうですが、実際の遅延はまだ分かりません。"),
            ("C", "何秒までなら会議の流れを邪魔しないかはOpen Itemです。"),
            ("A", "まずRecorded Transcriptから始める方針でどうでしょう。"),
        ),
    ),
    (
        "digression",
        (
            ("B", "その方向で進めましょう。"),
            ("C", "あ、オンライン会議連携も最初から必要になるかもしれません。"),
            ("A", "それは便利そうですが、今の検証の中心からは少し外れますね。"),
            ("B", "まずMapを共有画面で使う価値を見てからにしましょう。"),
            ("C", "オンライン会議の参加者が多いと、Speaker表示も欲しくなりそうです。"),
            ("A", "オンライン会議連携はMVPから外しましょう。"),
            ("B", "次回までにEvent Catalogの不足がないか整理します。"),
            ("C", "それとスマホのコントローラーもあると便利ですよね。"),
            ("A", "ただ、操作が増えて会議の視線が分散するのはConcernです。"),
            ("B", "今回はMapの表示とHuman Correctionだけに絞りましょう。"),
        ),
    ),
    (
        "pricing",
        (
            ("C", "では、価格モデルの話に移りましょう。"),
            ("A", "最初はPoCとして月額で試す案があります。"),
            ("B", "従量課金にすると会議ごとの説明はしやすそうです。"),
            ("C", "どちらが初期顧客に説明しやすいかはOpen Itemですね。"),
            ("A", "私は月額の方がいいと思います。"),
            ("B", "価格の話は一度置いて、MVPの範囲に戻るのもありです。"),
            ("C", "候補の比較表を次回までに整理します。"),
            ("A", "そうですね。"),
            ("B", "PoCは月額で進める案でどうでしょう。"),
            ("C", "その方向で進めましょう。"),
        ),
    ),
    (
        "privacy",
        (
            ("A", "価格の話をしていると、利用データの扱いも気になりますね。"),
            ("B", "次にPrivacyとTranscriptの保存について考えましょう。"),
            ("C", "会議内容が外部Providerへ送られることはConcernです。"),
            ("A", "Speaker名を外して、Discussion Contextだけ送る案はあります。"),
            ("B", "Contextをどこまで小さくできるかはまだ分かりません。"),
            ("C", "Transcript全文は外部Providerへ送らない方針にしましょう。"),
            ("A", "了解です。"),
            ("B", "オンライン会議連携の話もPrivacyと関係しますが、今は戻らなくて大丈夫です。"),
            ("C", "それもそうですね。"),
            ("A", "次回までにPrivacy要件の草案を作ります。"),
        ),
    ),
    (
        "map-return",
        (
            ("B", "さっきのDiscussion Mapの話に戻ると、Privacyの表示もMapで追えるとよいですね。"),
            ("C", "Topicが増えたときに、いま何を話しているかが見えれば十分です。"),
            ("A", "Current TopicのLaneだけExpandedなら、全体との関係も失わずに済みそうです。"),
            ("B", "Recent Flowには直近のTopic移動だけ残すのがよいと思います。"),
            ("C", "ただ、Open Itemが多すぎると未解決の山に見えるのが心配です。"),
            ("A", "Resolvedなものは折りたたんで、未解決だけStatus Railに出す案がよさそうです。"),
            ("B", "Compact Overviewなら6つくらいのTopicは見渡せますね。"),
            ("C", "このままでも読めそうです。"),
            ("A", "共有ディスプレイではCompact Overviewを標準にする案でどうでしょう。"),
            ("B", "それでいきましょう。"),
        ),
    ),
    (
        "wrap-up",
        (
            ("C", "まだ、誰がPrivacyの草案を書くかは決まっていません。"),
            ("A", "Visual ArtifactのPrototypeは次回までに私が作ります。"),
            ("B", "料金モデルの比較は急がず、Parkingに置いておきましょう。"),
            ("C", "オンライン会議連携は、必要なら次のSessionで戻しましょう。"),
            ("A", "スマホコントローラーも今回はParkingのままでよいです。"),
            ("B", "今日の中心はDiscussion Mapが会議を前に進めるかどうかでした。"),
            ("C", "決定したことと候補のことを分けて確認できるのはよさそうです。"),
            ("A", "次のPrototypeで、30分分のMapが読めるかを確認するのがOpen Itemです。"),
            ("B", "田中さん、2026-09-26までにEvaluation結果を確認してください。"),
            ("C", "お疲れさまでした。"),
        ),
    ),
)


def build_recorded_30min_dataset() -> dict[str, Any]:
    utterance_specs = [item for _, phase in PHASES for item in phase]
    if len(utterance_specs) != 120:
        raise AssertionError(f"Expected 120 utterances, got {len(utterance_specs)}")

    evidence: list[dict[str, Any]] = []
    utterances: list[dict[str, Any]] = []
    for index, (speaker, text) in enumerate(utterance_specs, start=1):
        started = START + timedelta(seconds=(index - 1) * 15)
        ended = started + timedelta(seconds=15)
        timestamp = started.isoformat().replace("+00:00", "Z")
        ended_at = ended.isoformat().replace("+00:00", "Z")
        evidence_id = f"rec30-e{index:03d}"
        utterance_id = f"rec30-u{index:03d}"
        evidence.append(
            {
                "id": evidence_id,
                "session_id": SESSION_ID,
                "sequence": index,
                "timestamp": timestamp,
                "speaker": speaker,
                "text": text,
            }
        )
        utterances.append(
            {
                "id": utterance_id,
                "session_id": SESSION_ID,
                "sequence": index,
                "evidence_ids": [evidence_id],
                "text": text,
                "started_at": timestamp,
                "ended_at": ended_at,
            }
        )

    session = {
        "id": SESSION_ID,
        "title": "Discussion Map AI Facilitator — 30分Recorded Discussion",
        "goal": "Discussion Map AI FacilitatorのMVP範囲と会議中の利用価値を評価する",
        "created_at": START.isoformat().replace("+00:00", "Z"),
        "started_at": START.isoformat().replace("+00:00", "Z"),
        "ended_at": (START + timedelta(seconds=1800)).isoformat().replace("+00:00", "Z"),
    }
    return {
        "dataset_version": DATASET_VERSION,
        "session": session,
        "evidence": evidence,
        "utterances": utterances,
        "phase_boundaries": [
            {"phase": name, "first_sequence": index * 10 + 1, "last_sequence": index * 10 + 10}
            for index, (name, _) in enumerate(PHASES)
        ],
    }


def build_golden_annotations() -> dict[str, Any]:
    return {
        "golden_version": "recorded-30min-golden-v1",
        "policy": {
            "type_d": "Strong Proposal + unique Strong Agreement only",
            "strong_decision": "Explicit scope choice, adoption, rejection, or commitment",
            "weak_decision": "Preference, leaning, possibility, or non-committal proposal",
            "action": "Explicit execution intent only; do not infer owner or due date",
            "no_op": "Acknowledgement/filler without a meaningful Discussion State change",
        },
        "expected_topics": [
            {"label": "MVP範囲", "aliases": ["MVP対象", "スマホUI"]},
            {"label": "Discussion Map", "aliases": ["Map", "共有ディスプレイ"]},
            {"label": "Mapレイアウト", "aliases": ["レイアウト", "Topic Lane", "Compact Overview"]},
            {"label": "Visual Artifact", "aliases": ["Visual生成", "Visual View"]},
            {"label": "Architecture", "aliases": ["Analyzer", "Event Stream", "Graph"]},
            {"label": "価格モデル", "aliases": ["料金", "PoC価格"]},
            {"label": "Privacy", "aliases": ["Transcript保存", "データ扱い"]},
            {"label": "オンライン会議連携", "aliases": ["Online Meeting"]},
            {"label": "スマホコントローラー", "aliases": ["スマホ操作"]},
        ],
        "type_d_cases": [
            {"proposal_sequence": 11, "agreement_sequence": 12, "label": "スマホUIはMVP対象外", "expected": True},
            {"proposal_sequence": 31, "agreement_sequence": 32, "label": "Current Topic LaneをExpandedにする", "expected": True},
            {"proposal_sequence": 50, "agreement_sequence": 51, "label": "Visual生成は手動トリガー", "expected": True},
            {"proposal_sequence": 70, "agreement_sequence": 71, "label": "Recorded Transcriptから開始", "expected": True},
            {"proposal_sequence": 89, "agreement_sequence": 90, "label": "PoCは月額", "expected": True},
            {"proposal_sequence": 109, "agreement_sequence": 110, "label": "Compact Overviewを標準", "expected": True},
        ],
        "strong_decisions": [
            {"sequence": 76, "label": "オンライン会議連携はMVP対象外", "expected_confirmation": "confirm"},
            {"sequence": 96, "label": "Transcript全文は外部Providerへ送信しない", "expected_confirmation": "confirm"},
        ],
        "weak_decision_sequences": [5, 16, 68, 85, 106],
        "no_op_sequences": [4, 10, 17, 20, 24, 34, 38, 40, 47, 51, 56, 60, 71, 80, 88, 97, 99, 108, 110, 120],
        "open_item_sequences": [9, 30, 35, 44, 57, 69, 84, 95, 111, 118],
        "action_sequences": [19, 39, 59, 77, 87, 100, 112, 119],
        "topic_return_sequences": [101],
        "focus_transition_sequences": [21, 41, 61, 72, 81, 92, 101],
        "human_plan": [
            {"after_sequence": 12, "command": "confirm_latest_candidate", "reason": "Type D true candidate"},
            {"after_sequence": 32, "command": "confirm_latest_candidate", "reason": "Type D true candidate"},
            {"after_sequence": 51, "command": "confirm_latest_candidate", "reason": "Type D true candidate"},
            {"after_sequence": 80, "command": "revoke_label", "target": "オンライン会議連携", "reason": "simulate changed direction"},
            {"after_sequence": 71, "command": "confirm_latest_candidate", "reason": "Type D true candidate"},
            {"after_sequence": 76, "command": "confirm_latest_candidate", "reason": "Type A direct decision"},
            {"after_sequence": 90, "command": "confirm_latest_candidate", "reason": "Type D true candidate"},
            {"after_sequence": 96, "command": "confirm_latest_candidate", "reason": "Type A direct decision"},
            {"after_sequence": 110, "command": "confirm_latest_candidate", "reason": "Type D true candidate"},
            {"after_sequence": 82, "command": "park_topic", "target": "オンライン会議連携", "reason": "digression parking"},
            {"after_sequence": 84, "command": "park_topic", "target": "スマホをコントローラー", "reason": "digression parking"},
            {"after_sequence": 114, "command": "restore_topic", "target": "オンライン会議連携", "reason": "restore without automatic focus"},
        ],
        "parking_targets": ["オンライン会議連携", "スマホをコントローラー"],
    }
