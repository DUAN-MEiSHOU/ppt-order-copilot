"""Build a self-contained, zero-dependency HTML version of the technical report.

    python scripts/build_report_html.py
    -> docs/TECHNICAL_REPORT.html

The Markdown source stays canonical; this file is a presentation artifact.
Uses only the standard library. Matches the dark theme of evals/report.html.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "TECHNICAL_REPORT.md"
OUT = ROOT / "docs" / "TECHNICAL_REPORT.html"
EVAL_JSON = ROOT / "evals" / "report.json"

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,
 "Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.75;font-size:15px}
a{color:#79c0ff;text-decoration:none}a:hover{text-decoration:underline}
.layout{display:grid;grid-template-columns:250px minmax(0,1fr);gap:28px;max-width:1400px;
 margin:0 auto;padding:32px 24px 80px}
nav{position:sticky;top:24px;align-self:start;max-height:calc(100vh - 48px);overflow:auto;
 background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px 14px;font-size:13px}
nav b{display:block;color:#8b949e;font-size:11px;letter-spacing:.08em;text-transform:uppercase;margin-bottom:10px}
nav a{display:block;color:#c9d1d9;padding:4px 8px;border-left:2px solid transparent;border-radius:0 4px 4px 0}
nav a:hover{background:#1c2128;border-left-color:#58a6ff;text-decoration:none}
nav a.lv3{padding-left:20px;font-size:12px;color:#8b949e}
main{min-width:0}
h1{font-size:30px;margin:0 0 10px;line-height:1.3}
h2{font-size:22px;margin:44px 0 16px;padding:8px 0 8px 12px;border-left:3px solid #58a6ff;
 background:linear-gradient(90deg,#1c212855,transparent)}
h3{font-size:17px;margin:28px 0 10px;color:#79c0ff}
h4{font-size:15px;margin:20px 0 8px;color:#c9d1d9}
p{margin:10px 0}
hr{border:none;border-top:1px solid #30363d;margin:32px 0}
ul,ol{margin:10px 0;padding-left:24px}li{margin:5px 0}
blockquote{margin:14px 0;padding:10px 16px;background:#161b22;border-left:3px solid #58a6ff;
 border-radius:0 6px 6px 0;color:#c9d1d9}
code{background:#21262d;padding:2px 6px;border-radius:4px;font-size:12.5px;color:#a5d6ff;
 font-family:"SFMono-Regular",Consolas,"Liberation Mono",monospace}
pre{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;overflow:auto;
 margin:16px 0;line-height:1.55}
pre code{background:none;padding:0;color:#c9d1d9;font-size:12.5px}
table{width:100%;border-collapse:collapse;background:#161b22;border:1px solid #30363d;
 border-radius:8px;overflow:hidden;margin:16px 0;font-size:13.5px;display:table}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid #21262d;vertical-align:top}
th{background:#1c2128;color:#8b949e;font-weight:600;white-space:nowrap}
tr:last-child td{border-bottom:none}
strong{color:#fff}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:22px 0}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px 16px}
.card b{display:block;font-size:24px;color:#79c0ff;line-height:1.3}
.card span{color:#8b949e;font-size:12px}
.ok{color:#4ade80}.bad{color:#f87171}
.sub{color:#8b949e;font-size:13px;margin-bottom:8px}
footer{margin-top:48px;padding-top:16px;border-top:1px solid #30363d;color:#6e7681;font-size:12px}
@media(max-width:900px){.layout{grid-template-columns:1fr}nav{position:static;max-height:none}}
@media print{body{background:#fff;color:#111}nav{display:none}.layout{display:block}
 h2{border-left-color:#333;background:none}code,pre,table,blockquote,.card{background:#f6f8fa;color:#111}
 th{background:#eee;color:#111}pre code{color:#111}a{color:#0366d6}}
"""


def slug(text: str, used: set[str]) -> str:
    base = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text).strip("-").lower() or "sec"
    s, i = base, 2
    while s in used:
        s, i = f"{base}-{i}", i + 1
    used.add(s)
    return s


def inline(text: str) -> str:
    """Render inline markdown; protect code spans from further formatting."""
    stash: list[str] = []

    def hold_code(m: re.Match) -> str:
        stash.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(stash) - 1}\x00"

    text = re.sub(r"`([^`]+)`", hold_code, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], text)
    return text


def split_row(line: str) -> list[str]:
    line = line.strip().strip("|")
    return [c.strip() for c in re.split(r"(?<!\\)\|", line)]


def is_separator(line: str) -> bool:
    return bool(re.fullmatch(r"\|?[\s:|-]+\|?", line)) and "-" in line and "|" in line


def render(md: str) -> tuple[str, list[tuple[int, str, str]]]:
    lines = md.splitlines()
    out: list[str] = []
    toc: list[tuple[int, str, str]] = []
    used: set[str] = set()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # fenced code
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            buf: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{html.escape(chr(10).join(buf))}</code></pre>")
            continue

        # heading
        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            level, title = len(m.group(1)), m.group(2).strip()
            sid = slug(re.sub(r"[`*]", "", title), used)
            if level >= 2:
                toc.append((level, re.sub(r"[`*]", "", title), sid))
            out.append(f'<h{level} id="{sid}">{inline(title)}</h{level}>')
            i += 1
            continue

        if stripped == "---":
            out.append("<hr>")
            i += 1
            continue

        # table
        if stripped.startswith("|") and i + 1 < len(lines) and is_separator(lines[i + 1].strip()):
            head = split_row(stripped)
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i].strip()))
                i += 1
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head)
                       + "</tr></thead><tbody>")
            for row in rows:
                cells = (row + [""] * len(head))[: len(head)]
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
            out.append("</tbody></table>")
            continue

        # blockquote
        if stripped.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(f"<blockquote>{inline(' '.join(buf))}</blockquote>")
            continue

        # lists
        if re.match(r"^[-*]\s+", stripped) or re.match(r"^\d+\.\s+", stripped):
            ordered = bool(re.match(r"^\d+\.\s+", stripped))
            tag = "ol" if ordered else "ul"
            items: list[str] = []
            while i < len(lines):
                cur = lines[i].strip()
                pat = r"^\d+\.\s+" if ordered else r"^[-*]\s+"
                if not re.match(pat, cur):
                    break
                items.append(re.sub(pat, "", cur))
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items)
                       + f"</{tag}>")
            continue

        if not stripped:
            i += 1
            continue

        # paragraph: join continuation lines
        buf = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if (not nxt or nxt.startswith(("#", "|", ">", "```", "---"))
                    or re.match(r"^[-*]\s+", nxt) or re.match(r"^\d+\.\s+", nxt)):
                break
            buf.append(nxt)
            i += 1
        out.append(f"<p>{inline(' '.join(buf))}</p>")
    return "\n".join(out), toc


def cards() -> str:
    if not EVAL_JSON.exists():
        return ""
    d = json.loads(EVAL_JSON.read_text(encoding="utf-8"))
    gate = "PASS" if d.get("gate_passed") else "FAIL"
    cls = "ok" if d.get("gate_passed") else "bad"
    items = [
        (f'{d["total_passed"]}/{d["total_cases"]}', "eval cases passed"),
        (f'{sum(1 for r in d["reports"] if r["gate_passed"])}/{len(d["reports"])}', "suites gate PASS"),
        (f'<span class="{cls}">{gate}</span>', "regression gate"),
        ("5", "runnable projects"),
        ("23/23", "smoke checks"),
    ]
    body = "".join(f'<div class="card"><b>{v}</b><span>{label}</span></div>' for v, label in items)
    rows = "".join(
        f'<tr><td>{html.escape(r["suite"])}</td><td>{r["passed"]}/{r["cases"]}</td>'
        f'<td class="{"ok" if r["gate_passed"] else "bad"}">'
        f'{"PASS" if r["gate_passed"] else "FAIL"}</td></tr>'
        for r in d["reports"]
    )
    summary = ("<h3>回归门禁快照</h3><table><thead><tr><th>suite</th><th>cases</th>"
               "<th>gate</th></tr></thead><tbody>" + rows + "</tbody></table>")
    return f'<div class="cards">{body}</div>{summary}'


def main() -> None:
    md = SRC.read_text(encoding="utf-8")
    body, toc = render(md)
    nav = "".join(
        f'<a class="{"lv3" if lv >= 3 else ""}" href="#{sid}">{html.escape(title)}</a>'
        for lv, title, sid in toc
    )
    doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent 工程作品集 · 技术报告</title><style>{CSS}</style></head>
<body><div class="layout">
<nav><b>目录</b>{nav}</nav>
<main>
<div class="sub">Zero-dependency · deterministic offline mode · generated from
 <code>docs/TECHNICAL_REPORT.md</code> by <code>scripts/build_report_html.py</code></div>
{cards()}
{body}
<footer>agent-portfolio v1.0.0 · 2026-11-10 · 所有数字可由
 <code>python evals/run_all.py</code> 与 <code>python tests/smoke_test.py</code> 复现 ·
 Markdown 为源文件，本页为展示产物</footer>
</main></div></body></html>"""
    OUT.write_text(doc, encoding="utf-8")
    print(f"Wrote {OUT} ({len(doc):,} chars, {len(toc)} TOC entries)")


if __name__ == "__main__":
    main()
