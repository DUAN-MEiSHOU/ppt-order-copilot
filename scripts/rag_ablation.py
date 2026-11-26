#!/usr/bin/env python3
"""RAG ablation: quantify the two retrieval fixes described in the report.

    python scripts/rag_ablation.py

Variants (same corpus, same 10 gold questions from p1_research_agent/eval_set.json):
  A  no bilingual query rewriting, IDF cap ON
  B  bilingual query rewriting ON,  IDF cap ON   (shipped configuration)
  C  bilingual query rewriting ON,  IDF cap OFF  (ablates the language-imbalance fix)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import agentkit.rag as rag  # noqa: E402
from agentkit import Corpus, HybridRetriever  # noqa: E402

CASES = json.loads((ROOT / "projects/p1_research_agent/eval_set.json").read_text(
    encoding="utf-8"))["cases"]
OUT = ROOT / "evals" / "reports" / "rag_ablation.json"


def evaluate(retriever: HybridRetriever, k: int = 5) -> dict:
    recall, mrr, term_cov = [], [], []
    for c in CASES:
        hits = retriever.search(c["payload"]["question"], top_k=k)
        files = [h.chunk.doc_id for h in hits]
        gold = c["expected"]["gold_files"]
        ranks = [i + 1 for i, f in enumerate(files) if any(g in f for g in gold)]
        recall.append(1.0 if ranks else 0.0)
        mrr.append(1.0 / ranks[0] if ranks else 0.0)
        joined = " ".join(h.chunk.text.lower() for h in hits)
        terms = c["expected"]["required_terms"]
        term_cov.append(sum(1 for t in terms if t.lower() in joined) / max(1, len(terms)))
    mean = lambda xs: round(sum(xs) / len(xs), 4)  # noqa: E731
    return {"recall@5": mean(recall), "mrr": mean(mrr),
            "evidence_term_coverage": mean(term_cov), "cases": len(CASES)}


def main() -> int:
    corpus = Corpus(ROOT / "data" / "rag_docs")
    print(f"corpus: {corpus.stats()}")

    a = evaluate(HybridRetriever(corpus, query_expansion=False))
    b = evaluate(HybridRetriever(corpus, query_expansion=True))

    original = rag._idf

    def uncapped(term, n_docs, df):
        return math.log(1 + (n_docs - df + 0.5) / (df + 0.5))

    rag._idf = uncapped
    try:
        c = evaluate(HybridRetriever(corpus, query_expansion=True))
    finally:
        rag._idf = original

    result = {
        "A_no_query_rewriting": a,
        "B_shipped_rewriting_plus_idf_cap": b,
        "C_no_idf_cap": c,
        "delta_B_minus_A": {k: round(b[k] - a[k], 4) for k in ("recall@5", "mrr", "evidence_term_coverage")},
        "delta_B_minus_C": {k: round(b[k] - c[k], 4) for k in ("recall@5", "mrr", "evidence_term_coverage")},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSaved to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
