# `tests/` — unit tests

17 tests over the two modules where a silent regression would be most
dangerous: the scoring primitives and the taint graph.

```bash
python -m pytest -q        # from the project root
```

`pytest.ini` sets `pythonpath = .` so `from app...` resolves without
installing the package.

## What is covered

### `test_scoring.py` — 12 tests

**Intent divergence** — low when the action's tokens are covered by the
declared goal, high when unrelated, and *unaffected by technical
identifiers*. That last one guards a real false-positive risk: passing
`EM-2006` to a tool is normal work, and an earlier version of the tokenizer
would have scored it as divergence.

**Action sensitivity** — the `incident_update` pair is the interesting one.
Status `investigating` is low sensitivity; status `closed` is high. Same
tool, different consequence — this is the distinction that stops a hostile
log line from closing an incident.

**Reversibility** — `email_draft` is reversible, `email_send` is not.

**Risk fusion** — `test_compute_risk_monotonic_in_taint` asserts that risk
increases with taint, all else equal. The weights are hand-tuned, so this
pins the property that matters even if the constants are retuned.

**Threshold matrix** — allow at low risk on a low-sensitivity action, block
at high risk on a high-sensitivity one, and
`test_threshold_matrix_high_sensitivity_blocks_earlier_than_low`, which
asserts the *relationship* between tiers rather than any single constant.

**Redaction** — long tokens are masked, short plain text is left alone. The
second test is the false-positive guard: redacting ordinary prose would
corrupt legitimate rewrites.

### `test_taint_graph.py` — 5 tests

**Direct untrusted source is fully tainted** and **trusted source has zero
taint** — the baseline mapping from trust level to score.

**`test_multi_hop_taint_decays_but_never_below_floor`** — the most important
test in the suite. It pins the anti-laundering property: taint dilutes with
graph distance, but a genuinely untrusted origin never decays below
`FLOOR = 0.3`. Without this floor an attacker could copy poisoned content
memory-to-memory until the taint reached zero. If someone tunes `DECAY`
later, this test is what stops the laundering path from reopening.

**`test_worst_ancestor_wins_over_average`** — one adversarial ancestor taints
the result regardless of how many benign ancestors accompany it. Averaging
would let an attacker dilute a payload with benign padding.

**`test_no_referenced_ids_means_zero_taint`** — an action referencing no
prior content starts clean.

## What is not covered

Stated plainly, because the gaps are real:

- **No test for `decide()` itself.** Every test targets a primitive. The
  orchestration in `decision.py` — early exits, the confirmation-digest
  path, the memory-tagging branch, the rewrite-to-escalate degradation — is
  exercised only through full simulator runs, not by this suite.
- **No test for `action_digest` canonicalization.** The claim that `1000.0`
  and `1000` produce the same digest while a changed recipient does not is
  currently unverified by a test.
- **No HTTP-level test.** `/v1/decision` request validation and the
  `DefenseDecision` rewrite invariant are not covered.
- **No test for `trace_store.py`,** including the silent-failure path.

The scorecards in `results_*.json` provide end-to-end evidence, but they are
not a substitute for these: a scorecard tells you the score moved, not which
branch broke.
