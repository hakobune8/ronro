"""Optional, persisted presentation hints; never part of Canonical semantics.

Validation is conservative structural checking, not an entailment proof.
All rejected/missing/stale hints leave the Canonical node visible.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

VERSION = "display-label-v1"
POLICY_VERSION = "display-label-policy-v2"
MAX_LENGTH = 72
GENERIC = {"その他", "未分類", "others", "other", "misc", "今後の課題", "対応が必要", "検討する", "重要な点"}

INSTRUCTION = """
PRESENTATION HINT — display-label-policy-v2 (non-Canonical)
For every node intent also return display_label (string or null) in this SAME
inference. Canonical label and all semantic intent rules remain authoritative.
display_label is a short Japanese proposition for participants 3–5m from a
meeting-room display to understand within seconds. Prefer 1–3 lines, allow up
to 5 lines rather than deleting meaning (40px, down to 36px if needed).
72 characters is only a ceiling, NOT a target. Shortness is subordinate to
semantic preservation. A longer safe label or null is better than a short
misleading one. Do not compress a concise Canonical label unnecessarily.
Preserve the subject, core proposition, essential technical terms, negation,
material numbers/comparisons, and strength: proposal/estimate/provisional/
confirmed/concern/necessity must not become a stronger claim or a decision.
Preserve tense and aspect: already proposed vs will propose, checked vs planned,
in progress vs required. Do not erase these distinctions into a timeless noun.
Do not invent facts, generic categories, transcript-style prose or ellipsis.
If already concise, reuse label. If safe shortening is not possible use null.
For Actions preserve the action verb. Owner/due are rendered separately from
the authoritative action fields: do NOT embed owner/due assignments in the hint.
Do not change node selection, identity, associations or semantic classifications
in order to produce a short display. A hint is not a whole-discussion summary.

STANDALONE PROPOSITION CHECK (before returning each hint)
Read the hint WITHOUT its Topic heading or neighboring cards. It must name the
actual subject and retain the Canonical predicate and its time/state. Never
replace the subject with '各プロセス', '複数箇所', '指標' or '対応' alone.
Keep comparisons together with their comparator and direction. Preserve scope
qualifiers (only, major, tentative) and causal limitations essential to the claim.
Do not relocate a required subject/state into another Topic merely to shorten
this node. Do not rewrite Canonical content to justify a shorter display label.
You may remove redundant connective prose or formula details when not the core
claim, but NOT the named quantity, the proposal/reporting state or its limits.
Silently compare your candidate with its Canonical label. If subject, predicate,
time/state, negation, scope or material comparison differs, keep more original
wording, reuse the original if within the ceiling, or return null. No new call.

GENERIC STATE EXAMPLES (not extraction triggers)
'共有手順を提案した' must remain past: NOT '共有手順を提案する' or '共有手順を提案'.
'点検方法を検討する' is consideration: NOT '点検を実施する'.
'資料は確認予定' is not '資料は確認済み'; '確認済みではない' is not '確認済み'.
'会場Aより広く会場Bより狭い' must retain BOTH comparisons, not just '広い'.
These examples constrain presentation only; they do not change Node types.
"""


def content_hash(node: Mapping[str, Any]) -> str:
    value = {k: node.get(k) for k in ("type", "label", "action")}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _validate_v1(value: Any, node: Mapping[str, Any]) -> tuple[str | None, str]:
    if value is None:
        return None, "missing"
    if not isinstance(value, str):
        return None, "malformed"
    value = value.strip()
    if not value or len(value) > MAX_LENGTH or any(ord(c) < 32 for c in value):
        return None, "size_or_control"
    if value.lower() in GENERIC or any(c in value for c in ("<", ">", "…")):
        return None, "generic_or_markup"
    canonical = str(node.get("label", ""))
    # Owner/due are structural, not free-form generated assignments. Fail closed
    # for recognizable assignment/date/name forms not grounded in Canonical text.
    patterns = (r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", r"\d{1,2}月\d{1,2}日",
                r"(?:明日|明後日|来週|来月|次回)(?:まで|中)?",
                r"[^\s、。／：（）()]+(?:さん|氏)", r"(?:担当|期限|締切|owner|due)\s*[:：]\s*[^、。／]+")
    if any(token not in canonical for p in patterns for token in re.findall(p, value, re.I)):
        return None, "unsupported_execution_metadata"
    if node.get("type") == "action":
        subjects = re.findall(r"(?:^|[、。\s])([^、。\s]+?)(?:が|は)", value)
        if any(subject not in canonical for subject in subjects):
            return None, "unsupported_execution_subject"
    # Guard obvious unsupported quantities; preserving *all* numbers is not
    # required. Semantic criticality and non-pattern natural language need review.
    if set(re.findall(r"\d+(?:\.\d+)?", value)) - set(re.findall(r"\d+(?:\.\d+)?", canonical)):
        return None, "unsupported_number"
    for marker in ("暫定", "推定", "提案", "懸念", "必要", "検討", "できない", "できず"):
        if marker in canonical and marker not in value:
            return None, "safety_marker_missing"
    # Conservative lexical guards for selected state distinctions, NOT a
    # general Japanese tense/entailment parser. Rephrases can safely fall back.
    for marker in ("提案した", "提案された", "提案する", "確認済み", "確認予定", "未確認", "対策中", "検討中"):
        if marker in canonical and marker not in value:
            return None, "temporal_state_missing"
    return value, "accepted"


def validate_label(value: Any, node: Mapping[str, Any]) -> tuple[str | None, str]:
    """v2 guards; retained v1 policy supports immutable historical replay."""
    if isinstance(value, str):
        # A generated line break is whitespace, not a reason to discard a safe
        # proposition. Actual wrapping belongs to the browser measurement.
        value = re.sub(r"[\r\n]+", " ", value)
    value, reason = _validate_v1(value, node)
    if value is None:
        return None, reason
    canonical = str(node.get("label", ""))
    # Preserve observed state forms, including polite and passive forms. The
    # rule is intentionally conservative; it is not a Japanese entailment proof.
    state = r"(?:提案|確認|検討|実施|承認|決定|試算|把握)(?:されている|されていた|されなかった|されない|された|していない|していた|している|しました|します|しない|した|する|済み|予定|中)"
    if set(re.findall(state, canonical)) != set(re.findall(state, value)):
        return None, "temporal_state_changed"
    negation = r"できない|できず|ではない|でない|していない|しない|未確認|未実施|不要"
    if set(re.findall(negation, canonical)) != set(re.findall(negation, value)):
        return None, "negation_changed"
    # Keep explicit comparator phrases, not only the adjective/direction.
    comparison = r"[^、。・（）()\s]+?より(?:大きい|大きく|小さい|小さく|多い|多く|少ない|少なく|広い|広く|狭い|狭く|高い|高く|低い|低く)"
    for phrase in re.findall(comparison, canonical):
        if phrase not in value:
            return None, "comparison_missing"
    for marker in ("主要", "のみ", "だけ", "全て"):
        if marker in canonical and marker not in value:
            return None, "scope_missing"
    return value, "accepted"


def record_hint(result: Any, candidate: Any) -> None:
    """Call only AFTER its canonical event was accepted; first write wins."""
    if candidate.event_type != "node_detected" or candidate.presentation is None:
        return
    node_id = f"node:{candidate.session_id}:{candidate.event_id}"
    node = next((n for n in result.state["graph"]["nodes"] if n["id"] == node_id), None)
    if node is None:
        return
    label, reason = validate_label(candidate.presentation.get("display_label"), node)
    result.presentation.setdefault(node_id, {
        "version": VERSION, "policy": POLICY_VERSION, "event_id": candidate.event_id,
        "sequence": result.state["graph"]["last_event_sequence"],
        "content_hash": content_hash(node), "display_label": label, "reason": reason,
    })


def display_projection(graph: Mapping[str, Any], records: Mapping[str, Any] | None = None) -> dict[str, Any]:
    values = {}
    for node in graph.get("nodes", []):
        record = records.get(node["id"], {}) if isinstance(records, Mapping) else {}
        label, reason = None, "missing"
        if isinstance(record, dict) and record:
            sequence = record.get("sequence")
            if record.get("version") == VERSION and record.get("content_hash") == content_hash(node) and type(sequence) is int and 0 <= sequence <= graph.get("last_event_sequence", 0):
                policy = record.get("policy", "display-label-policy-v1")
                validator = {"display-label-policy-v1": _validate_v1, POLICY_VERSION: validate_label}.get(policy)
                label, reason = validator(record.get("display_label"), node) if validator else (None, "unknown_policy")
                if label is None:
                    reason = record.get("reason", reason)
            else:
                reason = "stale_or_unknown_version"
        action = node.get("action") or {}
        values[node["id"]] = {
            "text": label or node["label"], "fallback": label is None, "reason": reason,
            "owner": action.get("owner") if node["type"] == "action" else None,
            "due_date": action.get("due_date") if node["type"] == "action" else None,
        }
    return values
