"""Sensitivity-indexed decision thresholds and safe-rewrite construction."""

from __future__ import annotations

import re

from app.models import CandidateAction

THRESHOLD_MATRIX = {
    "low": {"allow_below": 0.65, "rewrite_below": None, "escalate_below": 0.85},
    "medium": {"allow_below": 0.3, "rewrite_below": 0.6, "escalate_below": 0.85},
    "high": {"allow_below": 0.15, "rewrite_below": 0.35, "escalate_below": 0.6},
}

REWRITE_TARGETS = {
    "email_send": "email_draft",
    "payment_execute": "payment_prepare",
    "payment_confirm": "payment_prepare",
    "incident_close": "incident_update",
}

SECRET_PATTERN = re.compile(
    r"[A-Za-z0-9+/]{24,}={0,2}|[0-9a-fA-F]{32,}|\b[A-Za-z0-9_\-]{20,}\b"
)


def redact(value: str) -> str:
    return SECRET_PATTERN.sub("[REDACTED]", value)


def content_has_secret(action: CandidateAction) -> bool:
    texts = [action.content or ""]
    texts.extend(str(v) for v in action.arguments.values())
    return any(SECRET_PATTERN.search(t) for t in texts)


def build_rewritten_action(action: CandidateAction) -> CandidateAction | None:
    safe_arguments = {k: (redact(v) if isinstance(v, str) else v) for k, v in action.arguments.items()}
    safe_content = redact(action.content) if action.content else action.content

    target_tool = REWRITE_TARGETS.get(action.tool or "")
    if target_tool is None:
        if not content_has_secret(action):
            return None
        target_tool = action.tool

    return CandidateAction(
        type="tool_call",
        tool=target_tool,
        arguments=safe_arguments,
        content=safe_content,
        final=action.final,
    )


def apply_threshold_matrix(risk_score: float, tier: str) -> tuple[str, list[str]]:
    thresholds = THRESHOLD_MATRIX[tier]

    if risk_score < thresholds["allow_below"]:
        return "allow", ["RISK_WITHIN_TOLERANCE"]

    if thresholds["rewrite_below"] is not None and risk_score < thresholds["rewrite_below"]:
        return "rewrite", ["MODERATE_RISK_SAFER_ALTERNATIVE"]

    if risk_score < thresholds["escalate_below"]:
        return "escalate", ["ELEVATED_RISK_HUMAN_REVIEW_REQUIRED"]

    return "block", ["CRITICAL_RISK_THRESHOLD_EXCEEDED"]