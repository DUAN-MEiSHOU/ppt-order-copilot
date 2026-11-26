"""Evaluation harness: versioned task sets, numeric metrics, regression gate.

A demo that works once is easy; a repo that reports "recall@5=0.91, 3.2 tool
calls/run, 0 blocked escalations missed" is what an interviewer can trust.
The gate fails the run if any metric drops below its threshold.
"""
from __future__ import annotations

import html
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


@dataclass
class EvalCase:
    id: str
    payload: dict
    expected: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    metrics: dict[str, float] = field(default_factory=dict)
    details: dict = field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0.0

    def as_dict(self) -> dict:
        return {"case_id": self.case_id, "passed": self.passed,
                "metrics": self.metrics, "details": self.details,
                "error": self.error, "duration_ms": round(self.duration_ms, 1)}


@dataclass
class EvalReport:
    suite: str
    results: list[CaseResult]
    metrics: dict[str, float]
    thresholds: dict[str, float]
    gate_passed: bool
    gate_failures: list[str]
    created_at: str = ""

    def as_dict(self) -> dict:
        return {"suite": self.suite, "created_at": self.created_at,
                "cases": len(self.results),
                "passed": sum(1 for r in self.results if r.passed),
                "metrics": self.metrics, "thresholds": self.thresholds,
                "gate_passed": self.gate_passed, "gate_failures": self.gate_failures,
                "results": [r.as_dict() for r in self.results]}


class EvalSuite:
    def __init__(self, name: str, cases: list[EvalCase],
                 runner: Callable[[EvalCase], dict],
                 thresholds: dict[str, float] | None = None):
        self.name = name
        self.cases = cases
        self.runner = runner
        self.thresholds = thresholds or {}

    @classmethod
    def from_json(cls, name: str, path: str | Path,
                  runner: Callable[[EvalCase], dict]) -> "EvalSuite":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        cases = [EvalCase(id=c["id"], payload=c.get("payload", {}),
                          expected=c.get("expected", {}), tags=c.get("tags", []))
                 for c in data["cases"]]
        return cls(name, cases, runner, data.get("thresholds", {}))

    def run(self) -> EvalReport:
        results: list[CaseResult] = []
        for case in self.cases:
            t0 = time.perf_counter()
            try:
                out = self.runner(case) or {}
                metrics = {k: float(bool(v)) if isinstance(v, bool) else float(v)
                           for k, v in (out.get("metrics") or {}).items()}
                results.append(CaseResult(
                    case.id, bool(out.get("passed", False)), metrics,
                    out.get("details", {}), out.get("error"),
                    (time.perf_counter() - t0) * 1000))
            except Exception as exc:  # noqa: BLE001
                results.append(CaseResult(case.id, False, {}, {},
                                          f"{type(exc).__name__}: {exc}",
                                          (time.perf_counter() - t0) * 1000))
        aggregated: dict[str, float] = {}
        keys = sorted({k for r in results for k in r.metrics})
        for key in keys:
            vals = [r.metrics[key] for r in results if key in r.metrics]
            aggregated[key] = round(sum(vals) / len(vals), 4) if vals else 0.0
        aggregated["case_pass_rate"] = round(
            sum(1 for r in results if r.passed) / max(1, len(results)), 4)
        failures = [f"{k}: {aggregated.get(k, 0)} < {v}"
                    for k, v in self.thresholds.items() if aggregated.get(k, 0) < v]
        return EvalReport(self.name, results, aggregated, self.thresholds,
                          not failures, failures, datetime.now().isoformat(timespec="seconds"))


def render_html(reports: list[EvalReport], path: str | Path, *,
                title: str = "Agent Portfolio — Evaluation Report") -> Path:
    """Dependency-free, self-contained HTML report (dark theme)."""
    def bar(v: float) -> str:
        pct = max(0, min(100, v * 100))
        color = "#4ade80" if pct >= 85 else ("#fbbf24" if pct >= 60 else "#f87171")
        return (f'<div class="bar"><i style="width:{pct:.1f}%;background:{color}"></i></div>'
                f'<span class="num">{v:.3f}</span>')

    total_cases = sum(len(r.results) for r in reports)
    total_pass = sum(1 for r in reports for x in r.results if x.passed)
    gates_ok = all(r.gate_passed for r in reports)
    parts = [f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#0d1117;color:#e6edf3;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.6}}
.wrap{{max-width:1100px;margin:0 auto;padding:40px 24px 80px}}
h1{{font-size:28px;margin:0 0 6px}}h2{{font-size:19px;margin:36px 0 14px;padding-left:11px;border-left:3px solid #58a6ff}}
.sub{{color:#8b949e;font-size:13px;margin-bottom:28px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:12px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px}}
.card b{{display:block;font-size:26px;color:#79c0ff}}.card span{{color:#8b949e;font-size:12px}}
table{{width:100%;border-collapse:collapse;background:#161b22;border:1px solid #30363d;border-radius:8px;overflow:hidden;font-size:13px}}
th,td{{padding:9px 12px;text-align:left;border-bottom:1px solid #21262d;vertical-align:middle}}
th{{background:#1c2128;color:#8b949e;font-weight:600}}tr:last-child td{{border-bottom:none}}
.bar{{display:inline-block;width:110px;height:7px;background:#21262d;border-radius:4px;overflow:hidden;vertical-align:middle;margin-right:8px}}
.bar i{{display:block;height:100%}}.num{{font-variant-numeric:tabular-nums;color:#c9d1d9}}
.ok{{color:#4ade80}} .bad{{color:#f87171}} .tag{{display:inline-block;background:#1f6feb22;border:1px solid #1f6feb55;
color:#79c0ff;border-radius:10px;padding:1px 8px;font-size:11px;margin-right:5px}}
code{{background:#21262d;padding:1px 5px;border-radius:4px;font-size:12px}}
footer{{margin-top:40px;color:#6e7681;font-size:12px}}
</style></head><body><div class="wrap"><h1>{html.escape(title)}</h1>
<div class="sub">Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · deterministic offline mode ·
all numbers are reproducible via <code>python evals/run_all.py</code></div>
<div class="cards">
<div class="card"><b>{len(reports)}</b><span>eval suites</span></div>
<div class="card"><b>{total_cases}</b><span>eval cases</span></div>
<div class="card"><b>{total_pass}/{total_cases}</b><span>cases passed</span></div>
<div class="card"><b class="{'ok' if gates_ok else 'bad'}">{'PASS' if gates_ok else 'FAIL'}</b><span>regression gate</span></div>
</div>"""]
    for rep in reports:
        parts.append(f'<h2>{html.escape(rep.suite)} <span class="tag {"" if rep.gate_passed else "bad"}">'
                     f'{"GATE PASS" if rep.gate_passed else "GATE FAIL"}</span></h2>')
        parts.append('<table><tr><th>metric</th><th>score</th><th>threshold</th></tr>')
        for key in sorted(rep.metrics):
            thr = rep.thresholds.get(key)
            status = "" if thr is None or rep.metrics[key] >= thr else ' class="bad"'
            parts.append(f'<tr><td><code>{html.escape(key)}</code></td><td>{bar(rep.metrics[key])}</td>'
                         f'<td{status}>{f"≥ {thr}" if thr is not None else "—"}</td></tr>')
        parts.append('</table>')
        if rep.gate_failures:
            parts.append('<p class="bad">Gate failures: ' +
                         html.escape("; ".join(rep.gate_failures)) + '</p>')
        parts.append('<table><tr><th>case</th><th>result</th><th>metrics</th><th>notes</th></tr>')
        for r in rep.results:
            m = ", ".join(f"{k}={v:.2f}" for k, v in r.metrics.items()) or "—"
            note = html.escape(str(r.error or r.details.get("note") or "")[:160])
            parts.append(f'<tr><td><code>{html.escape(r.case_id)}</code></td>'
                         f'<td class="{"ok" if r.passed else "bad"}">{"PASS" if r.passed else "FAIL"}</td>'
                         f'<td>{html.escape(m)}</td><td>{note}</td></tr>')
        parts.append('</table>')
    parts.append('<footer>Metrics are computed from deterministic scripted policies over real '
                 'open-source data. Point LLM_API_KEY at a real endpoint to re-run the same '
                 'suites against a live model and compare.</footer></div></body></html>')
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts), encoding="utf-8")
    return out
