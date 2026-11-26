"""Hybrid RAG: BM25 + TF-IDF cosine fused with Reciprocal Rank Fusion.

Pure standard library on purpose: the whole corpus is small enough to index in
memory, so this runs offline with no embedding API, no vector DB and no model
download. `HybridRetriever` exposes the same interface an embedding-backed
retriever would, so swapping in BGE/OpenAI embeddings + Qdrant is a one-class
change (see docs/ARCHITECTURE.md).

Chinese queries work: the tokenizer emits both CJK unigrams and bigrams.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

STOPWORDS = set("""a an and are as at be by for from has have in is it its of on or that the to was
were will with this these those you your we our they their if then else not no but can should may
about into over under than so such when where which who how what why do does did done using use used
one two also more most some any all each other new now here there i me my he she his her them us
的 了 和 与 是 在 有 为 对 中 也 就 都 而 及 或 一个 这个 那个 可以 需要 使用 如何 什么 为什么""".split())

CJK = re.compile(r"[\u4e00-\u9fff]+")
WORD = re.compile(r"[a-z0-9_]+")

# Bilingual query rewriting. The corpus is mostly English (official MCP spec,
# Anthropic engineering notes, HF course), while users often ask in Chinese.
# A tiny domain glossary bridges the language gap without an embedding model;
# `docs/ARCHITECTURE.md` reports the measured recall delta of this A/B.
TERM_MAP = {
    "授权": "authorization", "认证": "authentication", "安全": "security",
    "工具": "tools", "传输": "transport", "规范": "specification",
    "技能": "skills", "工作流": "workflow", "智能体": "agent",
    "检索": "retrieval", "评估": "evaluation", "状态": "state",
    "审批": "approval", "记忆": "memory", "引用": "citation",
    "护栏": "guardrails", "轨迹": "trace", "规划": "planning",
    "并行": "parallelization", "路由": "routing", "反思": "reflection",
    "提示注入": "prompt injection", "渐进式": "progressive disclosure",
    "人工": "human in the loop", "客户端": "client", "服务端": "server",
    "资源": "resources", "提示词": "prompts", "停止条件": "stopping condition",
    "报错": "error", "修复": "repair", "数据库": "database",
}


def expansion_terms(query: str) -> list[str]:
    return [en for zh, en in TERM_MAP.items() if zh in query]


def _idf(term: str, n_docs: int, df: int) -> float:
    """Cap IDF for CJK terms.

    Only 2 of 30 documents are Chinese, so raw IDF makes a single Chinese
    character outweigh an entire English phrase and every Chinese query lands
    on the same 2 documents. Capping is a pragmatic fix for language imbalance
    (a production system would use a multilingual embedding instead).
    """
    value = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
    return min(value, 1.25) if CJK.search(term) else value


def expand_query(query: str, enabled: bool = True) -> str:
    """Append English equivalents for CJK domain terms (query rewriting)."""
    if not enabled:
        return query
    extra = expansion_terms(query)
    return query + (" " + " ".join(extra) if extra else "")


def tokenize(text: str) -> list[str]:
    text = (text or "").lower()
    tokens = [t for t in WORD.findall(text) if len(t) > 1 and t not in STOPWORDS]
    for run in CJK.findall(text):
        tokens.extend(ch for ch in run if ch not in STOPWORDS)
        tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def clean_markdown(text: str) -> str:
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"\A\s*---\s*\n.*?\n---\s*\n", " ", text, flags=re.S)  # YAML frontmatter
    text = re.sub(r"```.*?```", " ", text, flags=re.S)     # code blocks are noise for retrieval
    text = re.sub(r"<[A-Za-z][^>]*>", " ", text)           # mdx components
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    section: str
    text: str
    source_url: str
    start_line: int

    @property
    def label(self) -> str:
        return f"{self.title} › {self.section}"


class Corpus:
    """Load .md/.mdx documents and split them into heading-aware chunks."""

    def __init__(self, root: str | Path, chunk_chars: int = 900, overlap: int = 120):
        self.root = Path(root)
        self.chunk_chars = chunk_chars
        self.overlap = overlap
        self.chunks: list[Chunk] = []
        self.docs: list[dict] = []
        self._build()

    def _build(self) -> None:
        for path in sorted(self.root.glob("*.m*")):
            if path.name == "manifest.json":
                continue
            raw = path.read_text(encoding="utf-8", errors="replace")
            source_match = re.search(r"<!-- source: (\S+) -->", raw[:400])
            source = source_match.group(1) if source_match else f"local://{path.name}"
            title = path.stem.replace("__", " · ")
            self.docs.append({"doc_id": path.name, "title": title,
                              "source": source, "chars": len(raw)})
            sections = self._split_headings(raw)
            for sec_title, sec_text, line_no in sections:
                for i, piece in enumerate(self._window(sec_text)):
                    self.chunks.append(Chunk(
                        chunk_id=f"{path.stem}::s{len(self.chunks)}",
                        doc_id=path.name, title=title,
                        section=sec_title or "Overview", text=piece,
                        source_url=source, start_line=line_no + i * 12))

    @staticmethod
    def _split_headings(raw: str) -> list[tuple[str, str, int]]:
        lines = raw.splitlines()
        out: list[tuple[str, str, int]] = []
        heading, buf, start = "Overview", [], 1
        for i, line in enumerate(lines, 1):
            if re.match(r"^#{1,6}\s+\S", line):
                if "".join(buf).strip():
                    out.append((heading, clean_markdown("\n".join(buf)), start))
                heading = re.sub(r"^#+\s*", "", line).strip()
                buf, start = [], i
            else:
                buf.append(line)
        if "".join(buf).strip():
            out.append((heading, clean_markdown("\n".join(buf)), start))
        return out

    def _window(self, text: str) -> Iterable[str]:
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if len(text) <= self.chunk_chars:
            yield text
            return
        start = 0
        while start < len(text):
            end = min(len(text), start + self.chunk_chars)
            if end < len(text):
                cut = text.rfind("\n", start + self.chunk_chars // 2, end)
                if cut > start:
                    end = cut
            yield text[start:end].strip()
            if end >= len(text):
                break
            start = max(start + 1, end - self.overlap)

    def stats(self) -> dict:
        return {"documents": len(self.docs), "chunks": len(self.chunks),
                "total_chars": sum(c for c in (len(x.text) for x in self.chunks))}


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.n = len(docs)
        self.lengths = [len(d) for d in docs]
        self.avgdl = sum(self.lengths) / max(1, self.n)
        self.tf: list[Counter] = [Counter(d) for d in docs]
        df: Counter = Counter()
        for d in docs:
            df.update(set(d))
        self.idf = {t: _idf(t, self.n, n) for t, n in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        out = [0.0] * self.n
        q_counts = Counter(query)
        for term, qtf in q_counts.items():
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, tf in enumerate(self.tf):
                f = tf.get(term, 0)
                if not f:
                    continue
                norm = f + self.k1 * (1 - self.b + self.b * self.lengths[i] / max(1e-9, self.avgdl))
                out[i] += idf * qtf * f * (self.k1 + 1) / norm
        return out


class Tfidf:
    def __init__(self, docs: list[list[str]]):
        self.n = len(docs)
        df: Counter = Counter()
        for d in docs:
            df.update(set(d))
        self.idf = {t: _idf(t, self.n, n) for t, n in df.items()}
        self.vecs: list[dict[str, float]] = []
        for d in docs:
            counts = Counter(d)
            vec = {t: (1 + math.log(c)) * self.idf.get(t, 0.0) for t, c in counts.items()}
            norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            self.vecs.append({t: v / norm for t, v in vec.items()})

    def scores(self, query: list[str]) -> list[float]:
        counts = Counter(query)
        qvec = {t: (1 + math.log(c)) * self.idf.get(t, 0.0) for t, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in qvec.values())) or 1.0
        qvec = {t: v / norm for t, v in qvec.items()}
        return [sum(w * vec.get(t, 0.0) for t, w in qvec.items()) for vec in self.vecs]


@dataclass
class Hit:
    chunk: Chunk
    score: float
    bm25_rank: int | None = None
    tfidf_rank: int | None = None
    snippet: str = ""

    def citation(self, index: int) -> str:
        return (f"[{index}] {self.chunk.label} — {self.chunk.source_url} "
                f"(chunk {self.chunk.chunk_id.rsplit('::', 1)[-1]})")


class HybridRetriever:
    def __init__(self, corpus: Corpus, rrf_k: int = 60, w_bm25: float = 1.0, w_tfidf: float = 1.0,
                 query_expansion: bool = True, title_boost: int = 2):
        self.corpus = corpus
        # Headings are repeated in the token stream so they carry more weight in
        # both BM25 and TF-IDF ("stdio transport" should beat a passing mention).
        self.tokens = [tokenize(c.text) + tokenize(c.title + " " + c.section) * title_boost
                       for c in corpus.chunks]
        self.bm25 = BM25(self.tokens)
        self.tfidf = Tfidf(self.tokens)
        self.rrf_k, self.w_bm25, self.w_tfidf = rrf_k, w_bm25, w_tfidf
        self.query_expansion = query_expansion

    def search(self, query: str, top_k: int = 5, *, diversity: bool = True,
               doc_filter: list[str] | None = None,
               query_expansion: bool | None = None) -> list[Hit]:
        use_expansion = self.query_expansion if query_expansion is None else query_expansion
        q = tokenize(query)
        if use_expansion:
            bridge = tokenize(" ".join(expansion_terms(query)))
            # CJK queries emit many unigram/bigram tokens; up-weight the English
            # bridge terms so the English corpus can actually compete.
            q += bridge * (3 if CJK.search(query) else 2)
        if not q:
            return []
        bs, ts = self.bm25.scores(q), self.tfidf.scores(q)
        b_order = sorted(range(len(bs)), key=lambda i: -bs[i])[:max(top_k * 4, 20)]
        t_order = sorted(range(len(ts)), key=lambda i: -ts[i])[:max(top_k * 4, 20)]
        b_rank = {i: r + 1 for r, i in enumerate(b_order)}
        t_rank = {i: r + 1 for r, i in enumerate(t_order)}
        fused: dict[int, float] = defaultdict(float)
        for i, r in b_rank.items():
            fused[i] += self.w_bm25 / (self.rrf_k + r)
        for i, r in t_rank.items():
            fused[i] += self.w_tfidf / (self.rrf_k + r)
        candidates = sorted(fused, key=lambda i: -fused[i])

        chosen: list[int] = []
        selected_tokens: list[set[str]] = []
        for i in candidates:
            chunk = self.corpus.chunks[i]
            if doc_filter and not any(f in chunk.doc_id for f in doc_filter):
                continue
            if diversity and selected_tokens:
                cur = set(self.tokens[i])
                overlap = max(len(cur & s) / max(1, len(cur | s)) for s in selected_tokens)
                if overlap > 0.72:            # MMR-style redundancy filter
                    continue
            chosen.append(i)
            selected_tokens.append(set(self.tokens[i]))
            if len(chosen) >= top_k:
                break
        hits = []
        for i in chosen:
            c = self.corpus.chunks[i]
            snippet = re.sub(r"\s+", " ", c.text)[:220]
            hits.append(Hit(c, round(fused[i], 6), b_rank.get(i), t_rank.get(i), snippet))
        return hits

    def build_context(self, hits: list[Hit], max_chars: int = 6000) -> str:
        parts, used = [], 0
        for i, h in enumerate(hits, 1):
            block = f"[{i}] {h.chunk.label}\n{h.chunk.text}\n(source: {h.chunk.source_url})\n"
            if used + len(block) > max_chars:
                break
            parts.append(block)
            used += len(block)
        return "\n---\n".join(parts)


def groundedness(answer: str, hits: list[Hit]) -> float:
    """Fraction of answer content tokens covered by retrieved evidence.

    A lightweight, deterministic proxy for faithfulness — no LLM judge required.
    """
    a = set(tokenize(answer))
    ev = set()
    for h in hits:
        ev |= set(tokenize(h.chunk.text))
    return round(len(a & ev) / max(1, len(a)), 4)


def retrieval_metrics(cases: list[dict], retriever: HybridRetriever, k: int = 5) -> dict:
    """cases: [{"query": str, "gold_files": [str], "required_terms": [str]}]"""
    recalls, reciprocal, ndcgs, term_hits = [], [], [], []
    for case in cases:
        hits = retriever.search(case["query"], top_k=k)
        files = [h.chunk.doc_id for h in hits]
        gold = case.get("gold_files", [])
        ranks = [i + 1 for i, f in enumerate(files) if any(g in f for g in gold)]
        if gold:
            recalls.append(1.0 if ranks else 0.0)
            reciprocal.append(1.0 / ranks[0] if ranks else 0.0)
            dcg = sum(1.0 / math.log2(r + 1) for r in ranks)
            idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(gold), k)))
            ndcgs.append(dcg / idcg if idcg else 0.0)
        joined = " ".join(h.chunk.text.lower() for h in hits)
        req = case.get("required_terms", [])
        term_hits.append(sum(1 for t in req if t.lower() in joined) / max(1, len(req)))
    mean = lambda xs: round(sum(xs) / len(xs), 4) if xs else 0.0  # noqa: E731
    return {
        "cases": len(cases), "k": k,
        "recall@k": mean(recalls), "mrr": mean(reciprocal), "ndcg": mean(ndcgs),
        "evidence_term_coverage": mean(term_hits),
    }
