"""Persistent multi-turn provenance taint graph.

The DefenseRequest conversation field is a sliding window (max_conversation_items),
not full run history. This module keeps its own graph per run_id across HTTP calls
so taint from outside that window is never lost -- this is what lets the defense
catch long-horizon and memory-poisoning attacks that a single-request defense misses.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models import ConversationItem, DefenseRequest, ProvenanceRecord

TRUST_SCORE = {
    "system_policy": 0.0,
    "authenticated_user": 0.1,
    "trusted_internal": 0.2,
    "untrusted_internal": 0.5,
    "untrusted_external": 0.7,
    "adversary_controlled": 1.0,
}

DECAY = 0.85
FLOOR = 0.3
FLOOR_TRIGGER = 0.5


@dataclass
class TaintNode:
    node_id: str
    trust_level: str
    trust_score: float
    parents: tuple[str, ...]
    step_id: int


@dataclass
class RunGraph:
    nodes: dict[str, TaintNode] = field(default_factory=dict)
    declared_intent: str | None = None
    steps_seen: int = 0

    def add_provenance(self, record: ProvenanceRecord, step_id: int) -> None:
        if record.id in self.nodes:
            return
        score = TRUST_SCORE.get(record.provenance.trust_level, 0.5)
        self.nodes[record.id] = TaintNode(
            node_id=record.id,
            trust_level=record.provenance.trust_level,
            trust_score=score,
            parents=(),
            step_id=step_id,
        )

    def link_memory_write(self, memory_node_id: str, parent_ids: list[str], step_id: int) -> None:
        inherited_level = max(
            (self.nodes[p].trust_level for p in parent_ids if p in self.nodes),
            key=lambda lvl: TRUST_SCORE.get(lvl, 0.0),
            default="authenticated_user",
        )
        self.nodes[memory_node_id] = TaintNode(
            node_id=memory_node_id,
            trust_level=inherited_level,
            trust_score=TRUST_SCORE["authenticated_user"],
            parents=tuple(parent_ids),
            step_id=step_id,
        )

    def ancestors_with_hops(self, start_ids: list[str]) -> list[tuple[TaintNode, int]]:
        visited: dict[str, int] = {}
        frontier = [(nid, 0) for nid in start_ids if nid in self.nodes]
        while frontier:
            node_id, hops = frontier.pop()
            if node_id in visited and visited[node_id] <= hops:
                continue
            visited[node_id] = hops
            node = self.nodes[node_id]
            for parent_id in node.parents:
                if parent_id in self.nodes:
                    frontier.append((parent_id, hops + 1))
        return [(self.nodes[nid], hops) for nid, hops in visited.items()]


_RUNS: dict[str, RunGraph] = {}


def get_run_graph(run_id: str) -> RunGraph:
    if run_id not in _RUNS:
        _RUNS[run_id] = RunGraph()
    return _RUNS[run_id]


def ingest_request(request: DefenseRequest, graph: RunGraph) -> list[str]:
    for record in request.provenance:
        graph.add_provenance(record, request.step_id)

    graph.declared_intent = request.user_goal

    referenced_ids: list[str] = []
    for item in request.conversation:
        referenced_ids.extend(item.provenance_ids)
    if request.observation is not None:
        referenced_ids.extend(request.observation.provenance_ids)

    graph.steps_seen = max(graph.steps_seen, request.step_id)
    return list(dict.fromkeys(referenced_ids))


def compute_taint_score(
    referenced_ids: list[str], graph: RunGraph, current_step_id: int = 0
) -> tuple[float, list[str]]:
    ancestors = graph.ancestors_with_hops(referenced_ids)
    if not ancestors:
        return 0.0, []

    worst_score = 0.0
    worst_sources: list[str] = []
    for node, hops in ancestors:
        if hops == 0:
            distance = max(0, current_step_id - node.step_id)
            diluted = node.trust_score * (DECAY**distance)
        else:
            raw = node.trust_score * (DECAY**hops)
            diluted = max(raw, FLOOR) if node.trust_score > FLOOR_TRIGGER else raw

        if diluted > worst_score:
            worst_score = diluted
            worst_sources = [node.node_id]
        elif diluted == worst_score and node.node_id not in worst_sources:
            worst_sources.append(node.node_id)

    return round(min(1.0, worst_score), 4), worst_sources


def register_memory_write(request: DefenseRequest, graph: RunGraph, referenced_ids: list[str]) -> None:
    action = request.candidate_action
    if action.type != "memory_write":
        return
    memory_node_id = f"mem-{request.run_id}-{request.step_id}"
    graph.link_memory_write(memory_node_id, referenced_ids, request.step_id)