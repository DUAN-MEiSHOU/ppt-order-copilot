#!/usr/bin/env python3
"""Fetch real open-source data for the agent portfolio.

Everything in `data/` is downloaded from public GitHub repositories through the
GitHub REST API (no token required, ~60 req/h unauthenticated). The script is
idempotent: already-downloaded files are skipped, so it can be re-run after a
rate-limit hit. If the network is unavailable the repository still works,
because a small snapshot of every dataset is committed under `data/`.

Usage:
    python scripts/fetch_data.py            # incremental download (default)
    python scripts/fetch_data.py --force    # re-download everything
    python scripts/fetch_data.py --full-tickets  # also keep the full 8k-ticket CSV
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAG = DATA / "rag_docs"
API = "https://api.github.com"
CTX = ssl.create_default_context()
HEADERS = {
    "User-Agent": "agent-portfolio-data-fetcher",
    "Accept": "application/vnd.github+json",
}

# (repository, default branch, path prefixes / exact paths, max files, output prefix)
RAG_SOURCES = [
    ("modelcontextprotocol/modelcontextprotocol", "main",
     ["docs/specification/2026-07-28/"], 16, "mcp"),
    ("qfc-network/ai-infra", "main",
     ["anthropic/building-effective-agents/en.md",
      "anthropic/building-effective-agents/zh.md"], 2, "anthropic"),
    ("bernierllc/claude-skills", "main",
     ["agent_skills_spec.md", "mcp-builder/SKILL.md"], 2, "skills"),
    ("huggingface/agents-course", "main",
     ["units/en/unit1/", "units/en/unit2/"], 8, "hf-course"),
    ("langchain-ai/deepagents", "main",
     ["examples/text-to-sql-agent/README.md",
      "examples/text-to-sql-agent/AGENTS.md"], 2, "deepagents"),
]

BINARY_SOURCES = [
    ("lerocha/chinook-database", "master",
     "ChinookDatabase/DataSources/Chinook_Sqlite.sqlite", DATA / "chinook.db"),
    ("ARULGNANAKUMAR/Customer-Support-Ticket-Triage-System", "main",
     "customer_support_tickets.csv", DATA / "tickets_full.csv"),
]


def api_get(path: str, tries: int = 3):
    url = path if path.startswith("http") else API + path
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30, context=CTX) as resp:
                return json.load(resp)
        except Exception as exc:  # noqa: BLE001 - network robustness
            last = exc
            if "rate limit" in str(exc).lower() or "403" in str(exc):
                print("  ! GitHub rate limit reached; re-run later. Already-downloaded files are kept.")
                raise
            time.sleep(1 + i)
    raise RuntimeError(f"GET {url} failed: {last}")


def tree(repo: str, branch: str) -> list[dict]:
    data = api_get(f"/repos/{repo}/git/trees/{branch}?recursive=1")
    if data.get("truncated"):
        print(f"  ! tree for {repo} was truncated; using the first entries")
    return [x for x in data.get("tree", []) if x["type"] == "blob"]


def blob(repo: str, sha: str) -> bytes:
    data = api_get(f"/repos/{repo}/git/blobs/{sha}")
    if data.get("encoding") != "base64":
        raise RuntimeError(f"unexpected encoding {data.get('encoding')}")
    return base64.b64decode(re.sub(r"\s+", "", data["content"]))


def safe_name(repo: str, path: str, prefix: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", path).strip("-")
    if len(slug) > 90:
        slug = slug[-90:]
    return f"{prefix}__{slug}"


def fetch_rag(force: bool) -> int:
    RAG.mkdir(parents=True, exist_ok=True)
    manifest = []
    n = 0
    for repo, branch, prefixes, limit, prefix in RAG_SOURCES:
        try:
            entries = tree(repo, branch)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! skip {repo}: {exc}")
            continue
        chosen = []
        for p in prefixes:
            if p.endswith("/"):
                chosen += [e for e in entries
                           if e["path"].startswith(p)
                           and e["path"].endswith((".md", ".mdx"))
                           and "schema.mdx" not in e["path"]]
            else:
                chosen += [e for e in entries if e["path"] == p]
        seen = set()
        chosen = [e for e in chosen if not (e["path"] in seen or seen.add(e["path"]))]
        for entry in chosen[:limit]:
            out = RAG / safe_name(repo, entry["path"], prefix)
            if out.exists() and not force:
                n += 1
                manifest.append({"file": out.name, "source": f"https://github.com/{repo}/blob/{branch}/{entry['path']}"})
                continue
            try:
                raw = blob(repo, entry["sha"])
            except Exception as exc:  # noqa: BLE001
                print(f"  ! skip {entry['path']}: {exc}")
                continue
            header = (f"<!-- source: https://github.com/{repo}/blob/{branch}/{entry['path']} -->\n"
                      f"<!-- repo: {repo} | fetched by scripts/fetch_data.py -->\n\n")
            out.write_bytes(header.encode("utf-8") + raw)
            manifest.append({"file": out.name, "source": f"https://github.com/{repo}/blob/{branch}/{entry['path']}"})
            n += 1
            print(f"  + {out.name} ({len(raw)} B)")
    (RAG / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return n


def fetch_binary(force: bool, full_tickets: bool) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    for repo, branch, path, out in BINARY_SOURCES:
        if out.exists() and not force:
            print(f"  = {out.name} already present")
            continue
        try:
            entries = tree(repo, branch)
            match = next((e for e in entries if e["path"] == path), None)
            if match is None:
                print(f"  ! {path} not found in {repo}")
                continue
            raw = blob(repo, match["sha"])
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {out.name}: {exc}")
            continue
        out.write_bytes(raw)
        print(f"  + {out.name} ({len(raw)} B)")
    build_ticket_sample(full_tickets)


def build_ticket_sample(keep_full: bool) -> None:
    """Stratified sample so every ticket category is represented offline."""
    src = DATA / "tickets_full.csv"
    dst = DATA / "tickets_sample.csv"
    if not src.exists():
        if not dst.exists():
            print("  ! ticket CSV unavailable; the committed snapshot will be used")
        return
    with src.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    by_type: dict[str, list[dict]] = {}
    for r in rows:
        by_type.setdefault((r.get("Ticket Type") or "UNKNOWN").strip(), []).append(r)
    per_group = max(20, 400 // max(1, len(by_type)))
    sample: list[dict] = []
    for key in sorted(by_type):
        group = by_type[key]
        step = max(1, len(group) // per_group)
        sample.extend(group[::step][:per_group])
    sample = sample[:400]
    fields = list(rows[0].keys()) if rows else []
    with dst.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(sample)
    print(f"  + tickets_sample.csv: {len(sample)} stratified rows / {len(rows)} total, "
          f"{len(by_type)} categories")
    if not keep_full:
        src.unlink(missing_ok=True)
        print("  - removed tickets_full.csv (re-run with --full-tickets to keep it)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--full-tickets", action="store_true")
    args = ap.parse_args()
    print("Fetching open-source corpora via GitHub REST API ...")
    try:
        n = fetch_rag(args.force)
        print(f"RAG corpus: {n} documents in {RAG}")
        fetch_binary(args.force, args.full_tickets)
    except Exception as exc:  # noqa: BLE001
        print(f"Fetch aborted: {exc}")
        return 1
    print("Done. See data/SOURCES.md for provenance and licenses.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
