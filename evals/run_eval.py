#!/usr/bin/env python3
"""Standalone evaluation entry for this package (the whole-portfolio
evals/run_all.py imports all five suites and therefore is not included)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentkit.eval import render_html  # noqa: E402
from projects.p5_ppt_order_copilot.eval import suite  # noqa: E402


def main() -> int:
    rep = suite().run()
    n_pass = sum(1 for r in rep.results if r.passed)
    flag = "PASS" if rep.gate_passed else "FAIL"
    print(f"[{flag}] {rep.suite}: {n_pass}/{len(rep.results)} cases")
    for k, v in sorted(rep.metrics.items()):
        if k in rep.thresholds:
            print(f"    {k:26} {v:.4f}  (threshold >= {rep.thresholds[k]})")
    for f in rep.gate_failures:
        print(f"    !! {f}")
    out = ROOT / "evals" / "standalone_report.html"
    render_html([rep], out)
    print(f"HTML report: {out}")
    return 0 if rep.gate_passed else 1


if __name__ == "__main__":
    sys.exit(main())
