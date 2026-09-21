# Architecture — SENTINEL defense

Root index of the code documentation. Each folder has its own `README.md`
describing what lives there and why.

| Folder | What it holds | Doc |
|---|---|---|
| `app/` | The defense itself: scoring, taint graph, decision logic, HTTP service, dashboard | [app/README.md](app/README.md) |
| `tests/` | Unit tests for the scoring primitives and the taint graph | [tests/README.md](tests/README.md) |
| `artifacts/` | Execution traces written at runtime (gitignored) | [artifacts/README.md](artifacts/README.md) |
| *(root)* | Scorecards, submission manifest, container and dependency config | [Root files](#root-files) |

## The one-paragraph version

The defense is an HTTP service. The simulator runs an LLM agent; before the
agent is allowed to perform any action, the simulator POSTs that candidate
action to `/v1/decision`, and this service answers `allow`, `block`,
`escalate` or `rewrite`. The interesting part is that the answer is not
computed from the current request alone: the service keeps a **provenance
graph per run**, so content that entered the conversation twenty steps ago
still carries its distrust forward when it is recalled later.

## How a decision is made

Five signals are computed, then fused:

```
trust ────────┐
taint ────────┤
divergence ───┼──► weighted sum ──► sigmoid ──► risk_score ──┐
sensitivity ──┤                                              │
reversibility ┘                                              ▼
                                        threshold matrix indexed by
                                        the action's sensitivity tier
                                                             │
                                     ┌───────────┬───────────┼───────────┐
                                     ▼           ▼           ▼           ▼
                                   allow      rewrite    escalate     block
```

The threshold matrix is the reason a single risk score can drive four
different outcomes: the same `0.45` risk is tolerated on a `document_read`
and blocked on a `payment_execute`. Sensitivity does not inflate the score,
it moves the bar.

## Why a graph and not a filter

The challenge's harder scenarios are built so that no single request looks
dangerous:

- **Memory poisoning** — a fake "policy" is written to memory early, then
  recalled in a later task where it looks like an established rule.
- **Multi-step** — one instruction is split across several records, each
  individually harmless.
- **Long horizon** — the attack spans more steps than the request's
  conversation window holds.

A defense that only inspects the current `DefenseRequest` cannot see any of
these, because `conversation` is a **sliding window**, not the full history.
The taint graph persists outside that window, keyed by `run_id`, so an
untrusted ancestor from step 2 is still reachable at step 40.

The second consequence is the **memory trust inheritance** rule the spec
calls for: anything written to memory after reading untrusted content
inherits that distrust, and on recall it is treated as evidence, never as
an instruction.

## Repository layout

```
.
├── app/                  the defense (see app/README.md)
│   ├── models.py         API schemas
│   ├── taint_graph.py    provenance graph, persists across requests
│   ├── scoring.py        the five signals → risk score
│   ├── threshold_matrix.py  risk + sensitivity → outcome; rewrites
│   ├── decision.py       orchestration, the entry point
│   ├── trace_store.py    observability storage
│   └── main.py           FastAPI service + dashboard
├── tests/                unit tests (see tests/README.md)
├── artifacts/            runtime traces, gitignored (see artifacts/README.md)
├── results_*.json        scorecards, committed as evidence
├── sentinel-submission.yaml   submission manifest
├── Dockerfile            container image for the defense
├── requirements.txt      runtime dependencies
└── pytest.ini            test configuration
```

## Root files

**`results_*.json`** — scorecards produced by the official evaluator. These
are committed deliberately: the technical report cites their numbers, and a
reader should be able to check a claim without re-running the simulator.

| File | What it is | `official_score` |
|---|---|---|
| `results_full_defense.json` | The full defense, public split | 0.988 |
| `results_mutation_attack.json` | Full defense under the mutation attacker | 0.991 |
| `results_ablation_no_taint.json` | Taint graph disabled — the ablation | 0.819 |
| `results_baseline_provenance.json` | Kit-provided provenance baseline | 0.988 |
| `results_baseline_allow_all.json` | Kit-provided allow-all baseline | 0.131 |

Two of these deserve an honest reading rather than a favourable one:

- The **ablation** is the evidence that the taint graph carries the method:
  removing it drops robustness from 1.0 to 0.8 and the score from 0.988 to
  0.819.
- The **provenance baseline scores 0.988302 against the full defense's
  0.988437** — a gap of about one ten-thousandth. On the public split this
  defense does not meaningfully beat a baseline the organizers shipped. The
  defensible claim is about behaviour under adaptive pressure and on the
  long-horizon families, not about the headline number. The report should
  say so plainly; the challenge rewards honest limits over claimed wins.

**`sentinel-submission.yaml`** — the manifest the organizers read: team
name, port, and the declaration of external models and datasets. This
defense uses neither, so both lists are empty by design, not by omission.

> **Still carries starter-kit placeholders** (`team: your-team-name`, a
> description of the example defense). Must be filled in before submission.

**`Dockerfile`** — `python:3.12-slim`, installs `requirements.txt`, copies
`app/`, drops to an unprivileged user (uid 10001) and serves on 8080. Only
`app/` is copied: tests, scorecards and traces are not part of the runtime
image.

**`requirements.txt`** — three pinned ranges: `fastapi`, `uvicorn`,
`pydantic`. No ML dependency, no network client; the defense is pure Python
logic and runs fully offline on CPU.

**`pytest.ini`** — sets `pythonpath = .` so `from app...` imports resolve,
and restricts discovery to `tests/`.

## Running it

```bash
# serve
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080

# dashboard
open http://127.0.0.1:8080/dashboard

# tests
python -m pytest -q
```

Reproduction commands for the scenario runs are in the root
[README.md](README.md).
