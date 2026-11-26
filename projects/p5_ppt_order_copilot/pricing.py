"""Requirement extraction + explainable pricing for the PPT-order workflow.

Business rules come from the user's real side business:
  - three job types: (A) polish an existing draft, (B) build a deck from a
    speech/script, (C) pure visual restyling;
  - price is driven by page count and job type, normally ¥10–60;
  - urgency, charts, animation and master-template work are surcharges;
  - 2 free revision rounds, extra rounds are charged.

No platform API is involved. Chat transcripts are IMPORTED (pasted/exported),
and the only outbound artefact is text a human copies into Xianyu / WeChat.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PRICE_MIN, PRICE_MAX = 10, 60
FREE_REVISIONS = 2
EXTRA_REVISION_FEE = 5

TYPE_RULES = {
    "speech_to_ppt": {
        "label": "演讲稿转 PPT",
        "keywords": ["演讲稿", "讲稿", "文稿", "逐字稿", "根据稿子", "按稿子", "内容是", "script", "speech"],
        "per_slide": 1.6, "setup": 12,
    },
    "optimize_draft": {
        "label": "初版优化",
        "keywords": ["初版", "已有ppt", "我做好了", "我做了个", "帮我改", "优化一下", "美化一下", "改一下", "draft"],
        "per_slide": 0.8, "setup": 8,
    },
    "visual_only": {
        "label": "纯视觉优化",
        "keywords": ["纯视觉", "只改样式", "配色", "排版", "换个模板", "视觉", "风格统一", "visual"],
        "per_slide": 0.6, "setup": 6,
    },
}

EXTRA_RULES = {
    "charts": {"label": "图表/数据可视化", "fee": 5,
               "keywords": ["图表", "数据图", "可视化", "chart"]},
    "animation": {"label": "动画/切换效果", "fee": 4,
                  "keywords": ["动画", "动效", "切换效果", "animation"]},
    "master": {"label": "母版/模板定制", "fee": 6,
               "keywords": ["母版", "定制模板", "企业模板", "master"]},
}

STYLE_KEYWORDS = ["简约", "商务", "科技", "学术", "答辩", "清新", "活泼", "高端", "极简", "国风"]
URGENT_KEYWORDS = ["今天", "今晚", "明天就要", "急", "加急", "24小时", "尽快", "马上要", "urgent"]


@dataclass
class Requirements:
    task_type: str = "unknown"
    task_label: str = ""
    pages: int | None = None
    style: str | None = None
    urgent: bool = False
    deadline: str | None = None
    extras: list[str] = field(default_factory=list)
    has_script: bool = False
    missing: list[str] = field(default_factory=list)
    confidence: float = 0.0


def extract_requirements(chat: str) -> Requirements:
    """Deterministic chat parser. A live LLM would replace this with chat_json."""
    text = (chat or "").lower()
    scores = {k: sum(1 for kw in v["keywords"] if kw in text)
              for k, v in TYPE_RULES.items()}
    # '演讲稿转 PPT' is the most specific signal; it wins ties.
    order = ["speech_to_ppt", "optimize_draft", "visual_only"]
    task = max(order, key=lambda k: (scores[k], 1 if k == "speech_to_ppt" else 0))
    if scores[task] == 0:
        task = "unknown"
    # "第 5 页" is a page reference, not the deck size — strip it first.
    sized = re.sub(r"第\s*\d{1,3}\s*页", " ", text)
    found = [int(x) for x in re.findall(r"(\d{1,3})\s*(?:页|张|p\b|slides?\b)", sized)]
    pages = min(max(max(found), 1), 200) if found else None
    style = next((s for s in STYLE_KEYWORDS if s in text), None)
    # "不着急" contains "急" but is the opposite of an urgent request.
    calm = re.sub(r"不着急|不急|不用急|不赶时间", " ", text)
    urgent = any(k in calm for k in URGENT_KEYWORDS)
    dm = re.search(r"(今天|今晚|明天|后天|周[一二三四五六日]|\d{1,2}\s*月\s*\d{1,2}\s*[日号])", text)
    extras = [k for k, v in EXTRA_RULES.items() if any(kw in text for kw in v["keywords"])]
    has_script = bool(re.search(r"演讲稿|讲稿|文稿|逐字稿|稿子", text))
    missing = []
    if task == "unknown":
        missing.append("制作类型（初版优化 / 演讲稿转 PPT / 纯视觉优化）")
    if pages is None:
        missing.append("页数")
    if not style:
        missing.append("风格偏好")
    if not dm:
        missing.append("交付时间")
    if task == "speech_to_ppt" and not has_script:
        missing.append("演讲稿文件是否可提供")
    conf = round(min(1.0, 0.35 + 0.2 * sum(1 for x in (task != "unknown", pages, style, dm))), 2)
    return Requirements(task_type=task,
                        task_label=TYPE_RULES.get(task, {}).get("label", "未明确"),
                        pages=pages, style=style, urgent=urgent,
                        deadline=dm.group(1) if dm else None,
                        extras=extras, has_script=has_script,
                        missing=missing, confidence=conf)


def quote(req: Requirements) -> dict:
    """Transparent, reproducible quote clamped to the real ¥10–60 band."""
    rule = TYPE_RULES.get(req.task_type)
    if rule is None:
        return {"price": None, "breakdown": [], "reason": "制作类型未明确，无法报价",
                "within_range": False, "clamped": False}
    pages = req.pages or 10          # explicit, auditable default when unknown
    breakdown = [{"item": f"基础服务费（{rule['label']}）", "amount": rule["setup"]},
                 {"item": f"按页计费 {pages} 页 × ¥{rule['per_slide']}/页",
                  "amount": round(pages * rule["per_slide"], 2)}]
    subtotal = rule["setup"] + pages * rule["per_slide"]
    for key in req.extras:
        ex = EXTRA_RULES[key]
        breakdown.append({"item": ex["label"], "amount": ex["fee"]})
        subtotal += ex["fee"]
    if req.urgent:
        uplift = round(subtotal * 0.3, 2)
        breakdown.append({"item": "加急（×1.30）", "amount": uplift})
        subtotal += uplift
    raw = round(subtotal)
    price = max(PRICE_MIN, min(PRICE_MAX, raw))
    breakdown.append({"item": f"区间钳制 [{PRICE_MIN}, {PRICE_MAX}]", "amount": price - raw})
    return {"price": price, "raw_price": raw, "breakdown": breakdown,
            "within_range": PRICE_MIN <= price <= PRICE_MAX,
            "clamped": price != raw, "pages_used": pages,
            "rule": f"setup({rule['setup']}) + per_slide({rule['per_slide']})×pages + extras + urgency, clamp[10,60]"}


def clarify(req: Requirements) -> list[str]:
    questions = []
    mapping = {
        "制作类型（初版优化 / 演讲稿转 PPT / 纯视觉优化）":
            "这次是【A 初版优化】、【B 按演讲稿做 PPT】还是【C 纯视觉优化】？",
        "页数": "大概多少页？报价按页数和设计类型算～",
        "风格偏好": "想要什么风格？简约 / 商务 / 科技 / 学术答辩 / 其他都可以说。",
        "交付时间": "什么时候需要？加急会按 1.3 倍计价。",
        "演讲稿文件是否可提供": "方便把演讲稿（Word/文本）发我吗？我需要它来组织每页内容。",
    }
    for m in req.missing:
        questions.append(mapping.get(m, f"请补充：{m}"))
    return questions


def revision_policy(round_no: int, base_price: int) -> dict:
    extra = max(0, round_no - FREE_REVISIONS)
    fee = extra * EXTRA_REVISION_FEE
    return {"round": round_no, "free_revisions": FREE_REVISIONS,
            "extra_rounds": extra, "fee": fee,
            "total_with_revisions": base_price + fee,
            "message": (f"第 {round_no} 轮修改在免费范围内（共 {FREE_REVISIONS} 轮）。"
                        if fee == 0 else
                        f"已超出免费 {FREE_REVISIONS} 轮，本轮需加收 ¥{fee}，累计 ¥{base_price + fee}。")}


def draft_handoff(req: Requirements, q: dict, questions: list[str], revision: dict) -> str:
    """Text for a HUMAN to copy into Xianyu / WeChat. Never sent by the agent."""
    lines = ["【可直接复制发送给客户的话术】", "",
             "你好～我整理了一下需求：",
             f"· 类型：{req.task_label}",
             f"· 页数：{req.pages or '待确认'} 页",
             f"· 风格：{req.style or '待确认'}",
             f"· 交付：{req.deadline or '待确认'}{'（加急）' if req.urgent else ''}"]
    if req.extras:
        lines.append("· 附加项：" + "、".join(EXTRA_RULES[e]["label"] for e in req.extras))
    lines += ["", "报价明细："]
    for item in q.get("breakdown", []):
        if item["amount"]:
            lines.append(f"  - {item['item']}：{item['amount']:+.0f} 元"
                         if isinstance(item["amount"], (int, float)) else f"  - {item['item']}")
    lines += [f"  = 合计 **¥{q.get('price')}**（价格区间 10–60 元）", ""]
    if questions:
        lines.append("还有几个点想跟你确认：")
        lines += [f"  {i}. {q2}" for i, q2 in enumerate(questions, 1)]
        lines.append("")
    lines += [f"修改规则：免费 {FREE_REVISIONS} 轮，超出每轮 +¥{EXTRA_REVISION_FEE}。",
              "确认没问题的话我就按这个排期开始做啦～"]
    return "\n".join(lines)
