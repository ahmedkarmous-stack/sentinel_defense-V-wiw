"""In-memory + JSONL trace store, keyed by run_id, for the live observability dashboard."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TRACE_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "traces"
TRACE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class TraceStore:
    _runs: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, run_id: str, entry: dict[str, Any]) -> None:
        with self._lock:
            self._runs.setdefault(run_id, []).append(entry)
        try:
            path = TRACE_DIR / f"{run_id}.jsonl"
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"run_id": run_id, "steps": len(entries), "last_decision": entries[-1]["decision"] if entries else None}
                for run_id, entries in sorted(self._runs.items())
            ]

    def get_run(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._runs.get(run_id, []))

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()


STORE = TraceStore()