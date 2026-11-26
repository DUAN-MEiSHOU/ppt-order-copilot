#!/usr/bin/env python3
"""Standalone smoke test for P5 · 闲鱼 PPT 接单 Copilot（HITL）.

Check bodies are copied verbatim from the whole-portfolio tests/smoke_test.py.
Only the DATA section and the project under test are narrowed to this package.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(condition), detail))
    print(f"  [{'OK' if condition else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("DATA")
    for rel in ['data/ppt_chats_sample.json']:
        p = ROOT / rel
        check(f"{rel} exists", p.exists(),
              f"{len(list(p.glob('*')))} files" if p.is_dir()
              else f"{p.stat().st_size} B" if p.exists() else "")

    print()
    print("P5 PPT order copilot")
    from projects.p5_ppt_order_copilot.workflow import chat_by_id, run_order
    r5 = run_order(chat_by_id("c01_speech_to_ppt"), auto_approve=True, persist=False)
    check("quote in band", r5.price is not None and 10 <= r5.price <= 60, f"¥{r5.price}")
    check("approval gate fired", r5.interrupted)
    check("handoff text", "10–60" in r5.handoff or "报价明细" in r5.handoff)
    r5i = run_order(chat_by_id("c07_pii"), auto_approve=True, persist=False)
    check("PII not leaked", "13800138000" not in (r5i.report + r5i.handoff))

    print("\n" + "=" * 60)
    ok = sum(1 for _, c, _ in CHECKS if c)
    print(f"SMOKE TEST (standalone): {ok}/{len(CHECKS)} checks passed")
    return 0 if ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
