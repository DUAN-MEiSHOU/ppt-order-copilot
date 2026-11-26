# P5 · 闲鱼 PPT 接单 Copilot（HITL） — 独立包

本目录是从 `agent-portfolio` 拆出的**可独立运行**的单个项目包。源仓库未被改动：所有复制过来的文件与源文件逐字节一致；包内只新增了 3 个打包适配文件（见下）。

## 一句话功能

粘贴聊天记录 → 抽三类需求 / 页数 / 风格 / 附加项 → 信息缺失则列追问清单并拒绝报价 → 可解释公式算价并钳制到 ¥10–¥60 → 金额无条件人工审批 → 产出制作 brief、修改轮次规则与可直接复制的客户话术。刻意不接闲鱼 / 微信任何消息接口。

## 独立性说明

- 本包自带完整的 `agentkit/` 共享核副本（9 个模块），**不依赖原仓库、不依赖其它项目包**。
- 保留了原仓库的目录层级（`projects/p5_ppt_order_copilot/`、`data/`、`evals/`、`docs/` …），因此 `from projects.p5_ppt_order_copilot import ...` 与 `ROOT / "data" / ...` 无需任何修改即可运行。
- 无跨项目依赖。
- `evals/run_all.py` 与 `tests/smoke_test.py` 是**全仓聚合入口**（引用全部 5 个项目），不属于任何单项目，故未收入本包；替代入口为 `evals/run_eval.py` 与 `tests/smoke_standalone.py`。

## 目录结构

```
├── agentkit/                     共享核完整副本：loop / tools / state / rag / guard / eval / trace / llm
├── projects/
│   ├── __init__.py
│   ├── p5_ppt_order_copilot/               完整项目源码 + README + eval.py + eval_set.json
├── data/                         本包所需数据（原样复制，未裁剪内容）
│   ├── SOURCES.md                全仓数据溯源与许可证
│   ├── ppt_chats_sample.json
├── evals/
│   ├── __init__.py
│   ├── report.html / report.json  全仓 5-suite 基线评测报告（供 docs 内链，非本包单独结果）
│   ├── reports/                  本项目的真实示例产物
│   └── run_eval.py               [新增] 单包评测入口
├── tests/
│   └── smoke_standalone.py       [新增] 单包冒烟测试
├── scripts/                      可复现的数据抓取 / 消融 / HTML 报告生成脚本（全仓版）
├── docs/                         全仓级 6 份 Markdown + 技术报告 HTML（原样，内链有效）
├── runs/                         示例 trace / checkpoint / outbox
├── README.md                     全仓总览（原样保留，讲全部 5 个项目）
├── PACKAGE.md                    [新增] 本文件
├── .env.example                  真实 LLM 模式配置样例
└── requirements.txt              核心零第三方依赖；可选依赖已注释
```

> 本项目自己的 README 在 `projects/p5_ppt_order_copilot/README.md`（**原位保留**，其中的 `../../docs/...` 相对链接有效）。
> `docs/` 与根 `README.md` 是整套作品集的文档，描述全部 5 个项目；本包只含其中第 5 个项目的代码。

## 快速开始（在本包根目录执行）

```bash
python --version                 # 3.10+，核心链路无需 pip install

# 1) 跑一次真实 demo（离线确定性模式，真实工具 + 真实数据）
python projects/p5_ppt_order_copilot/run_demo.py --chat c01_speech_to_ppt --save

# 2) 跑本项目的 10 个评测用例 + 回归门禁
python evals/run_eval.py

# 3) 单包端到端冒烟
python tests/smoke_standalone.py

# 4) 可选：接真实模型（复制 .env.example 为 .env 并填 LLM_API_KEY 后加 --api）
#    P4 是被动协议服务，可直接启动 stdio 服务端供任意 MCP 客户端连接
python projects/p5_ppt_order_copilot/run_demo.py --chat c01_speech_to_ppt --api
```

产物落在 `evals/reports/`、`evals/standalone_report.html` 与 `runs/`。

## 数据

随包携带 `data/ppt_chats_sample.json`（10 段**合成**聊天样例，不含真实个人信息；明确标注不是真实客户对话）。

数据来源、许可证与诚实边界见 `data/SOURCES.md` 与 `docs/DATA_SOURCES.md`。工单数据与 PPT 聊天样例是**合成数据**，只用于验证流程、护栏与评测，不代表真实业务语义。

## 本包新增的 3 个文件（非项目改动）

| 文件 | 作用 |
|---|---|
| `PACKAGE.md` | 本说明 |
| `evals/run_eval.py` | 只调用本项目的 `suite()` 并输出单包 HTML 报告 |
| `tests/smoke_standalone.py` | 从全仓冒烟中取出本项目检查项，检查体逐字复制 |

其余全部文件均从源仓库原样复制。运行时新生成的 `evals/standalone_report.html`、`runs/*.json` 属于产物，不是项目内容改动。

## 单包内链边界（按本次要求未改动任何文档）

拆包后有几类链接在单包内指向不存在的文件，都属于「只读复制 + 按项目裁剪」的固有结果。本次要求不对项目内容做改动，因此**没有改写任何文档去修链接**，只在此如实披露：

| 类型 | 原因 |
|---|---|
| 全仓根 `README.md` 指向其它 4 个项目的 README | 单包只含本项目源码，其余项目刻意不打包 |
| `data/rag_docs/manifest.json`（仅不含语料的包） | 语料按项目裁剪，manifest 只随需要 RAG 语料的包携带 |
| 第三方语料内部相对链接（`.png`、同目录其它章节） | 抓取时只下载了 30 篇正文文档；**这些链接在整仓里同样就是断的**，与拆包无关 |

本项目自己的 `projects/p5_ppt_order_copilot/README.md` 及其 `../../docs/...` 链接全部有效。整仓实测：项目文档 0 断链，26 条断链全部来自第三方语料内部。

## 诚实边界

离线模式使用 `ScriptedLLM`（真实 agent loop + 真实工具 + 真实数据/数据库，只把「下一步调哪个工具」写成确定性策略），不代表模型智能；成本是按 token 单价的估算值，不是真实账单。接真实 LLM 后需用同一套 eval 重跑对比。
