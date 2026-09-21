"""Composite risk scoring: trust, taint, intent divergence, action sensitivity."""

from __future__ import annotations

import math
import re

from app.models import CandidateAction, DefenseRequest
from app.taint_graph import TRUST_SCORE

ACTION_SENSITIVITY = {
    "email_send": ("high", 1.0),
    "email_draft": ("medium", 0.2),
    "email_read": ("low", 0.0),
    "email_search": ("low", 0.0),
    "payment_confirm": ("high", 1.0),
    "payment_execute": ("high", 1.0),
    "payment_prepare": ("medium", 0.3),
    "ticket_update": ("medium", 0.4),
    "ticket_read": ("low", 0.0),
    "incident_update": ("low", 0.15),
    "incident_create": ("low", 0.2),
    "incident_close": ("high", 0.9),
    "remediation_prepare": ("medium", 0.3),
    "remediation_execute": ("high", 1.0),
    "monitoring_toggle": ("high", 1.0),
    "document_read": ("low", 0.0),
    "document_search": ("low", 0.0),
    "wiki_search": ("low", 0.0),
    "account_summary": ("low", 0.0),
    "alert_read": ("low", 0.0),
    "asset_lookup": ("low", 0.0),
    "case_document_read": ("low", 0.0),
    "case_note_create": ("low", 0.15),
    "customer_lookup": ("low", 0.0),
    "intel_search": ("low", 0.0),
    "policy_search": ("low", 0.0),
}
DEFAULT_SENSITIVITY = ("medium", 0.5)

STATUS_CONSEQUENTIAL = {
    "ticket_update": {"closed", "resolved"},
    "incident_update": {"closed", "resolved"},
}

STOPWORDS = {
    "the", "a", "an", "to", "of", "and", "for", "with", "on", "in", "at",
    "so", "is", "are", "call", "also", "our", "we", "it", "this", "that",
}


def tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


TECHNICAL_ID_PATTERN = re.compile(r"^[a-z]{0,4}\d+$|^\d+$")


def compute_intent_divergence(declared_intent: str | None, action: CandidateAction) -> float:
    if declared_intent is None:
        return 0.2

    goal_tokens = tokenize(declared_intent)
    if not goal_tokens:
        return 0.2

    semantic_parts = [action.content or ""]
    semantic_parts.extend(str(v) for v in action.arguments.values())
    action_tokens = tokenize(" ".join(semantic_parts))
    action_tokens = {t for t in action_tokens if not TECHNICAL_ID_PATTERN.match(t)}

    if not action_tokens:
        return 0.0

    covered = len(action_tokens & goal_tokens)
    recall = covered / len(action_tokens)
    return round(max(0.0, min(0.7, (1.0 - recall) * 0.7)), 4)


def action_sensitivity(action: CandidateAction) -> tuple[str, float]:
    if action.tool is None:
        return ("low", 0.0)
    tier, value = ACTION_SENSITIVITY.get(action.tool, DEFAULT_SENSITIVITY)
    status = action.arguments.get("status")
    if action.tool in STATUS_CONSEQUENTIAL and isinstance(status, str):
        if status in STATUS_CONSEQUENTIAL[action.tool]:
            return ("high", 0.9)
        return ("low", 0.1)
    return (tier, value)


def reversibility_score(action: CandidateAction, tier: str) -> float:
    if action.tool in {"email_draft", "payment_prepare"}:
        return 0.2
    if tier == "high":
        return 1.0
    if tier == "medium":
        return 0.5
    return 0.0


WEIGHTS = {
    "trust": 1.6,
    "taint": 2.2,
    "divergence": 0.9,
    "sensitivity": 1.2,
    "reversibility": 0.6,
}
BIAS = -2.6


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def compute_risk(
    trust_score: float,
    taint_score: float,
    divergence_score: float,
    sensitivity_value: float,
    reversibility_value: float,
) -> float:
    z = (
        BIAS
        + WEIGHTS["trust"] * trust_score
        + WEIGHTS["taint"] * taint_score
        + WEIGHTS["divergence"] * divergence_score
        + WEIGHTS["sensitivity"] * sensitivity_value
        + WEIGHTS["reversibility"] * reversibility_value
    )
    return round(sigmoid(z), 4)


def direct_trust_score(request: DefenseRequest) -> float:
    if request.observation is None or not request.observation.provenance_ids:
        return TRUST_SCORE["authenticated_user"]
    records = {r.id: r.provenance.trust_level for r in request.provenance}
    levels = [records[pid] for pid in request.observation.provenance_ids if pid in records]
    if not levels:
        return TRUST_SCORE["authenticated_user"]
    return max(TRUST_SCORE.get(lvl, 0.0) for lvl in levels)