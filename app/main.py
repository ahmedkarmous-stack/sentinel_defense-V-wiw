from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.decision import decide
from app.models import DefenseDecision, DefenseRequest
from app.trace_store import STORE

app = FastAPI(title="SENTINEL defense - taint graph", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/decision", response_model=DefenseDecision)
def decision(request: DefenseRequest) -> DefenseDecision:
    return decide(request)


@app.get("/api/runs")
def list_runs() -> list[dict]:
    return STORE.list_runs()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> list[dict]:
    return STORE.get_run(run_id)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> str:
    return DASHBOARD_HTML


DASHBOARD_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>SENTINEL — Observability</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, Segoe UI, Roboto, sans-serif; background: #0b1220; color: #e8ecf4; display: flex; height: 100vh; }
  #sidebar { width: 260px; background: #0f1830; border-right: 1px solid #1e2a4a; overflow-y: auto; flex-shrink: 0; }
  #sidebar h1 { font-size: 14px; letter-spacing: 2px; padding: 16px; margin: 0; color: #d4a24e; border-bottom: 1px solid #1e2a4a; }
  .run-item { padding: 12px 16px; cursor: pointer; border-bottom: 1px solid #16213f; font-size: 13px; }
  .run-item:hover { background: #16213f; }
  .run-item.active { background: #1c2a52; border-left: 3px solid #d4a24e; }
  .run-item .steps { color: #8993ab; font-size: 11px; margin-top: 4px; }
  #main { flex: 1; overflow-y: auto; padding: 20px 28px; }
  #main h2 { font-size: 15px; color: #8993ab; font-weight: 500; margin-bottom: 16px; }
  .card { background: #0f1830; border: 1px solid #1e2a4a; border-radius: 8px; padding: 14px 16px; margin-bottom: 12px; }
  .card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
  .step-label { font-size: 12px; color: #8993ab; font-family: monospace; }
  .action-label { font-size: 14px; font-weight: 600; margin-left: 10px; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; }
  .badge-allow { background: #16382a; color: #4ade80; }
  .badge-block { background: #3a1620; color: #f87171; }
  .badge-escalate { background: #3a2a12; color: #fbbf24; }
  .badge-rewrite { background: #14283a; color: #60a5fa; }
  .risk-row { display: flex; align-items: center; gap: 10px; margin: 6px 0; }
  .risk-label { width: 110px; font-size: 11px; color: #8993ab; flex-shrink: 0; }
  .risk-bar-bg { flex: 1; height: 8px; background: #16213f; border-radius: 4px; overflow: hidden; }
  .risk-bar-fill { height: 100%; border-radius: 4px; }
  .risk-value { width: 42px; font-size: 11px; font-family: monospace; text-align: right; flex-shrink: 0; }
  .chips { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { background: #16213f; color: #a8b3cc; font-size: 10px; padding: 3px 8px; border-radius: 10px; font-family: monospace; }
  .explanation { margin-top: 8px; font-size: 12px; color: #a8b3cc; font-style: italic; }
  .rewrite-box { margin-top: 10px; padding: 8px 10px; background: #0a1628; border-left: 2px solid #60a5fa; font-size: 11px; font-family: monospace; color: #93c5fd; }
  .empty { color: #566085; text-align: center; margin-top: 80px; font-size: 13px; }
</style>
</head>
<body>
  <div id="sidebar">
    <h1>SENTINEL TRACE</h1>
    <div id="runs"></div>
  </div>
  <div id="main"><div class="empty">Sélectionne un run à gauche</div></div>

<script>
let currentRun = null;

function colorForScore(v) {
  if (v < 0.3) return '#4ade80';
  if (v < 0.6) return '#fbbf24';
  return '#f87171';
}

function riskRow(label, value) {
  if (value === undefined || value === null) return '';
  const pct = Math.round(value * 100);
  return `<div class="risk-row">
    <div class="risk-label">${label}</div>
    <div class="risk-bar-bg"><div class="risk-bar-fill" style="width:${pct}%; background:${colorForScore(value)}"></div></div>
    <div class="risk-value">${value.toFixed(2)}</div>
  </div>`;
}

function renderEntry(e) {
  const s = e.scores || {};
  const chips = (e.reason_codes || []).map(c => `<span class="chip">${c}</span>`).join('');
  const taintChips = (e.taint_sources || []).map(c => `<span class="chip">taint: ${c}</span>`).join('');
  let rewriteHtml = '';
  if (e.rewritten_action) {
    rewriteHtml = `<div class="rewrite-box">rewritten -> ${e.rewritten_action.type}${e.rewritten_action.tool ? ' / ' + e.rewritten_action.tool : ''}</div>`;
  }
  return `<div class="card">
    <div class="card-top">
      <div>
        <span class="step-label">step ${e.step_id}</span>
        <span class="action-label">${e.action_type}${e.tool ? ' · ' + e.tool : ''}</span>
      </div>
      <span class="badge badge-${e.decision}">${e.decision}</span>
    </div>
    ${riskRow('trust', s.trust_score)}
    ${riskRow('taint', s.taint_score)}
    ${riskRow('divergence', s.divergence_score)}
    ${riskRow('risk (final)', e.risk_score)}
    ${riskRow('confidence', e.confidence)}
    <div class="chips">${chips}${taintChips}</div>
    ${e.explanation ? `<div class="explanation">${e.explanation}</div>` : ''}
    ${rewriteHtml}
  </div>`;
}

async function refreshRuns() {
  const res = await fetch('/api/runs');
  const runs = await res.json();
  const container = document.getElementById('runs');
  container.innerHTML = runs.map(r => `
    <div class="run-item ${r.run_id === currentRun ? 'active' : ''}" onclick="selectRun('${r.run_id}')">
      <div>${r.run_id}</div>
      <div class="steps">${r.steps} steps · last: ${r.last_decision || '-'}</div>
    </div>
  `).join('');
}

async function refreshTrace(forceScrollBottom) {
  if (!currentRun) return;
  const res = await fetch(`/api/runs/${currentRun}`);
  const entries = await res.json();
  const main = document.getElementById('main');
  const wasAtBottom = main.scrollTop + main.clientHeight >= main.scrollHeight - 40;
  main.innerHTML = `<h2>${currentRun} — ${entries.length} steps</h2>` + entries.map(renderEntry).join('');
  if (forceScrollBottom || wasAtBottom) {
    main.scrollTop = main.scrollHeight;
  }
}

function selectRun(runId) {
  currentRun = runId;
  refreshRuns();
  refreshTrace(true);
}

setInterval(refreshRuns, 1500);
setInterval(refreshTrace, 1000);
refreshRuns();
</script>
</body>
</html>
"""