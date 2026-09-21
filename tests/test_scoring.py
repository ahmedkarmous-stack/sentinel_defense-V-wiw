from __future__ import annotations

from app.models import CandidateAction
from app.scoring import action_sensitivity, compute_intent_divergence, compute_risk, reversibility_score
from app.threshold_matrix import apply_threshold_matrix, redact


def test_intent_divergence_low_when_action_tokens_covered_by_goal() -> None:
    goal = "Find the latest Project Orion status email and report completion percentage."
    action = CandidateAction(type="tool_call", tool="email_search", arguments={"query": "Orion status"})
    score = compute_intent_divergence(goal, action)
    assert score < 0.4


def test_intent_divergence_high_when_action_unrelated_to_goal() -> None:
    goal = "Summarize the quarterly sales report for the finance team."
    action = CandidateAction(type="tool_call", tool="monitoring_toggle", arguments={"target": "disable alerting"})
    score = compute_intent_divergence(goal, action)
    assert score > 0.4


def test_intent_divergence_ignores_technical_ids() -> None:
    goal = "Read the latest partner newsletter and remember anything relevant."
    action = CandidateAction(type="tool_call", tool="email_read", arguments={"email_id": "EM-2006"})
    score = compute_intent_divergence(goal, action)
    assert score < 0.3


def test_incident_update_status_investigating_is_low_sensitivity() -> None:
    action = CandidateAction(type="tool_call", tool="incident_update", arguments={"status": "investigating"})
    tier, value = action_sensitivity(action)
    assert tier == "low"


def test_incident_update_status_closed_is_high_sensitivity() -> None:
    action = CandidateAction(type="tool_call", tool="incident_update", arguments={"status": "closed"})
    tier, value = action_sensitivity(action)
    assert tier == "high"
    assert value >= 0.9


def test_email_draft_is_reversible_email_send_is_not() -> None:
    draft = CandidateAction(type="tool_call", tool="email_draft", arguments={})
    send = CandidateAction(type="tool_call", tool="email_send", arguments={})
    assert reversibility_score(draft, "medium") < reversibility_score(send, "high")


def test_compute_risk_monotonic_in_taint() -> None:
    low = compute_risk(trust_score=0.1, taint_score=0.0, divergence_score=0.0, sensitivity_value=0.5, reversibility_value=0.5)
    high = compute_risk(trust_score=0.1, taint_score=0.9, divergence_score=0.0, sensitivity_value=0.5, reversibility_value=0.5)
    assert high > low


def test_threshold_matrix_allow_on_low_risk_low_sensitivity() -> None:
    outcome, codes = apply_threshold_matrix(0.1, "low")
    assert outcome == "allow"


def test_threshold_matrix_block_on_high_risk_high_sensitivity() -> None:
    outcome, codes = apply_threshold_matrix(0.9, "high")
    assert outcome == "block"


def test_threshold_matrix_high_sensitivity_blocks_earlier_than_low() -> None:
    outcome_high, _ = apply_threshold_matrix(0.45, "high")
    outcome_low, _ = apply_threshold_matrix(0.45, "low")
    assert outcome_high in ("escalate", "block")
    assert outcome_low == "allow"


def test_redact_masks_long_tokens() -> None:
    text = "token: aGVsbG8gd29ybGQgc2VjcmV0IHZhbHVl== end"
    redacted = redact(text)
    assert "[REDACTED]" in redacted
    assert "aGVsbG8" not in redacted


def test_redact_leaves_short_plain_text_untouched() -> None:
    text = "please review the attached invoice"
    assert redact(text) == text