from __future__ import annotations

from app.models import CandidateAction, DefenseRequest, ObservationView, Provenance, ProvenanceRecord
from app.taint_graph import compute_taint_score, get_run_graph, ingest_request, register_memory_write


def make_provenance(record_id: str, trust_level: str) -> ProvenanceRecord:
    return ProvenanceRecord(
        id=record_id,
        provenance=Provenance(
            source_type="email",
            source_id=record_id,
            trust_level=trust_level,
            origin_actor="tester",
            retrieved_via="tool_call",
            sensitivity="internal",
        ),
    )


def make_request(
    run_id: str,
    step_id: int,
    observation_ids: list[str],
    provenance_records: list[ProvenanceRecord],
    action: CandidateAction,
    user_goal: str = "test goal",
) -> DefenseRequest:
    return DefenseRequest(
        run_id=run_id,
        step_id=step_id,
        user_goal=user_goal,
        conversation=[],
        observation=ObservationView(kind="tool_result", content="x", provenance_ids=observation_ids),
        candidate_action=action,
        policy_context={"allowed_tools": ["email_send", "email_draft", "document_read", "memory_write"]},
        provenance=provenance_records,
        history_digest={},
    )


def test_direct_untrusted_source_is_fully_tainted() -> None:
    graph = get_run_graph("run-direct")
    prov = [make_provenance("obs-1", "adversary_controlled")]
    action = CandidateAction(type="tool_call", tool="email_send", arguments={}, content="hi")
    req = make_request("run-direct", 1, ["obs-1"], prov, action)
    ingest_request(req, graph)

    score, sources = compute_taint_score(["obs-1"], graph)
    assert score == 1.0
    assert sources == ["obs-1"]


def test_trusted_source_has_zero_taint() -> None:
    graph = get_run_graph("run-trusted")
    prov = [make_provenance("obs-1", "system_policy")]
    action = CandidateAction(type="tool_call", tool="email_send", arguments={}, content="hi")
    req = make_request("run-trusted", 1, ["obs-1"], prov, action)
    ingest_request(req, graph)

    score, sources = compute_taint_score(["obs-1"], graph)
    assert score == 0.0


def test_multi_hop_taint_decays_but_never_below_floor() -> None:
    graph = get_run_graph("run-multihop")
    prov = [make_provenance("obs-1", "adversary_controlled")]
    write_action = CandidateAction(type="memory_write", tool=None, arguments={}, content="summary")
    req1 = make_request("run-multihop", 1, ["obs-1"], prov, write_action)
    ingest_request(req1, graph)
    register_memory_write(req1, graph, ["obs-1"])

    memory_node_id = "mem-run-multihop-1"
    score_one_hop, _ = compute_taint_score([memory_node_id], graph)
    assert 0.3 <= score_one_hop < 1.0

    req2 = make_request("run-multihop", 2, [memory_node_id], prov, write_action)
    ingest_request(req2, graph)
    register_memory_write(req2, graph, [memory_node_id])

    second_memory_node_id = "mem-run-multihop-2"
    score_two_hops, _ = compute_taint_score([second_memory_node_id], graph)
    assert 0.3 <= score_two_hops < score_one_hop


def test_no_referenced_ids_means_zero_taint() -> None:
    graph = get_run_graph("run-empty")
    score, sources = compute_taint_score([], graph)
    assert score == 0.0
    assert sources == []


def test_worst_ancestor_wins_over_average() -> None:
    graph = get_run_graph("run-worst")
    prov = [
        make_provenance("obs-clean", "system_policy"),
        make_provenance("obs-dirty", "adversary_controlled"),
    ]
    action = CandidateAction(type="tool_call", tool="email_send", arguments={}, content="hi")
    req = make_request("run-worst", 1, ["obs-clean", "obs-dirty"], prov, action)
    ingest_request(req, graph)

    score, sources = compute_taint_score(["obs-clean", "obs-dirty"], graph)
    assert score == 1.0
    assert "obs-dirty" in sources