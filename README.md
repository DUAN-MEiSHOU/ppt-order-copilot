# agent-portfolio · 面向 Agent / 大模型应用开发岗的工程作品集

> 5 个真实工作流 · 1 个手写共享内核 · 真实开源数据 · 零第三方依赖 · 数值化评测与回归门禁

这不是「调包 demo 合集」。设计主线是一条**能在面试里讲清楚的能力递进**：先手写 agent loop、工具契约、状态机、检索、护栏、轨迹，证明理解原理；再用这条内核落地三个真实工作流；然后封装成标准 MCP Server 与 Agent Skills，证明懂协议与生态；最后用一个来自真实副业的人机协同工作流，证明会做**边界判断**；全程用统一 trace 与 eval harness 量化，回答「你怎么知道它好用」。

| 项目 | 内容 |
|---|---|
| 版本 | v1.0.0（2026-11-10） |
| 运行环境 | Python 3.10+，**零第三方依赖、零 API key、断网可跑** |
| 代码规模 | 45 个 Python 文件 / 5,150 行；23 份项目 Markdown 文档 / 2,592 行 |
| 数据 | 30 篇开源文档 / 420 chunks、Chinook SQLite、400 条工单、10 段合成聊天 |
| 评测 | `gate = PASS` · **53/55 cases** · 5/5 suites · 冒烟 **23/23** |
| 报告 | [`docs/TECHNICAL_REPORT.md`](docs/TECHNICAL_REPORT.md) · [`evals/report.html`](evals/report.html) |

---

## 1. 五个项目

> 想直接看「每个项目输入什么、做什么、产出什么、跑出来长什么样」，读 [`docs/FEATURES.md`](docs/FEATURES.md)——里面逐条贴了 5 个 `evals/reports/` 的真实产物。

| # | 项目 | 真实工作流 | 主打能力 | 数据来源 |
|---|---|---|---|---|
| [P1](projects/p1_research_agent/README.md) | 带引用的深度调研 Agent | 技术问题 → 多轮检索 → 读原文 → 依据校验 → 带 `[n]` 引用简报 | 手写 agent loop / 混合检索 / 引用 / 检索评测 | 30 篇 MCP、Skills、Agents 公开文档 |
| [P2](projects/p2_sql_agent/README.md) | Text-to-SQL 自修复 Agent | 自然语言 → SQL → 真实报错 → 自修复 → 洞察 + SVG 图表 | 工具契约 / SQL 护栏 / 环境反馈驱动修复 | 开源 Chinook SQLite |
| [P3](projects/p3_support_swarm/README.md) | 多 Agent 客服工单协作 | 分诊 → 检索 → 起草 → Critic 审核 → 风险闸门 → 人工审批 | 显式状态机 / evaluator-optimizer / HITL | 400 条工单（自 8,469 条分层抽样） |
| [P4](projects/p4_mcp_and_skills/README.md) | MCP Server + Agent Skills | 把上面三项能力暴露为标准 tools / resources / prompts 与技能 | JSON-RPC 2.0 / 能力协商 / 渐进式披露 | 复用 P1–P3 |
| [P5](projects/p5_ppt_order_copilot/README.md) | 闲鱼 PPT 接单 Copilot | 聊天导入 → 需求抽取 → 可解释报价 → 人工确认 → 制作 brief / 话术 | 边界判断 / 确定性定价 / 修改轮次 / HITL | 10 段合成聊天（明确标注） |

**为什么有 P5**：闲鱼与微信个人号都没有面向个人开发者的合规消息接口，因此**主动放弃平台消息自动化**，只做「导入聊天 → 结构化 → 人工对外发送」的后半段。这个取舍不是妥协，而是把 human-in-the-loop 和最小权限从口号变成了架构约束。详见技术报告 §1.2。

## 2. 能力矩阵

| 能力 | P1 | P2 | P3 | P4 | P5 |
|---|:--:|:--:|:--:|:--:|:--:|
| 手写 agent loop / 三层预算 | ✓ | ✓ | | | |
| 工作流状态机 / checkpoint / HITL | | | ✓ | | ✓ |
| RAG + 引用 + 检索指标 | ✓ | | ✓ | ✓ | |
| 工具调用 / JSON Schema / 最小权限 | ✓ | ✓ | | ✓ | |
| 错误自修复（环境反馈驱动） | | ✓ | ✓ | | |
| 护栏 / 注入防护 / PII 脱敏 | ✓ | ✓ | ✓ | ✓ | ✓ |
| MCP / Agent Skills | | | | ✓ | |
| 多角色协作 / 审核回环 | | | ✓ | | |
| trace / eval / 回归门禁 | ✓ | ✓ | ✓ | ✓ | ✓ |

共享内核 [`agentkit/`](agentkit/)（8 个模块，只用标准库）：`llm` · `tools` · `loop` · `state` · `rag` · `guard` · `trace` · `eval`。依赖方向单向：`projects → agentkit → 标准库`，`agentkit` 不 import 任何 project。

## 3. 快速开始

```bash
cd agent-portfolio
python --version                       # 3.10+，无需 pip install

# 一次跑完 5 个 suite，生成 evals/report.html + report.json
python evals/run_all.py

# 端到端冒烟（23 项断言）
python tests/smoke_test.py

# 生成可展示的技术报告 HTML（docs/TECHNICAL_REPORT.html）
python scripts/build_report_html.py

# 五个项目各看一次真实输出
python projects/p1_research_agent/run_demo.py "MCP 授权流程和安全注意事项" --save
python projects/p2_sql_agent/run_demo.py "按国家统计总收入" --inject-error --save
python projects/p3_support_swarm/run_demo.py --risk
python projects/p4_mcp_and_skills/run_demo.py --save
python projects/p5_ppt_order_copilot/run_demo.py --chat c01_speech_to_ppt --save
```

**两种运行模式**（重要，避免误解）：

| 模式 | 触发 | 决策来源 | 用途 |
|---|---|---|---|
| 离线确定性（默认） | `LLM_API_KEY` 为空 | `ScriptedLLM`：项目内可读的确定性策略代码 | 断网可跑、评测可复现、CI 门禁 |
| 真实 LLM | 填 `.env` 或加 `--api` | OpenAI 兼容端点（DeepSeek / OpenAI / Ollama） | 真实生成，可跑**同一套 eval** 做对比 |

```bash
cp .env.example .env      # 填 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
python projects/p1_research_agent/run_demo.py --api "workflow 和 agent 的区别"
```

离线模式**不是把结果硬编码**：它照样走完整 agent loop、调用真实工具、查真实数据库与语料、产生真实 trace 和真实数值，只是把「下一步调哪个工具」写成确定性策略（标准 test double 做法）。切换只需替换 `llm` 对象，loop 与工具完全不变。报告中所有数字均来自该模式，可逐位复现。

## 4. 实测结果

```
python evals/run_all.py   →  gate = PASS
TOTAL 53/55 cases passed · 5/5 suites gate PASS · smoke test 23/23
```

| 项目 | cases | 代表指标 |
|---|---:|---|
| P1 调研 | 8/10 | recall@5 **0.80**（消融前 0.60）· MRR 0.80 · groundedness **0.983** · 平均 5.0 次工具调用 |
| P2 SQL | 10/10 | 执行成功率 1.00 · **自修复率 1.00**（3 个注入错误）· 护栏拦截率 1.00（2 个对抗） |
| P3 工单 | 10/10 | 路由 1.00 · 升级判定 1.00 · PII 清洁率 1.00 · 审核修复率 1.00 · 轨迹完整率 1.00 |
| P4 MCP+Skills | 15/15 | 协议合规 1.00 · 工具执行 1.00 · 注入检测 1.00 · **上下文节省 0.6057** |
| P5 接单 | 10/10 | 分类 1.00 · 价格区间/钳制 1.00 · 缺失追问 1.00 · **金额人工审批率 1.00** |

P1 的 2 个失败 case 是**故意保留**的困难案例（中文口语化日期意图、跨语料多意图），用于讲失败分析与 abstention 设计，没有通过调阈值或删用例美化数据。完整分析见技术报告 §6.3，检索修复的 A/B 消融见 [`scripts/rag_ablation.py`](scripts/rag_ablation.py) 与 `evals/reports/rag_ablation.json`。

## 5. 数据与诚实边界

所有外部数据由 [`scripts/fetch_data.py`](scripts/fetch_data.py) 通过 **GitHub REST API** 抓取（`raw.githubusercontent.com` 与 HuggingFace 直连在本机不可达），随仓库落地，断网可跑；每篇文档头部保留原始 URL，逐文件映射见 [`data/rag_docs/manifest.json`](data/rag_docs/manifest.json)。

- **真实开源数据**：30 篇公开技术文档、Chinook SQLite。
- **合成数据，明确标注**：客服工单数据集是 Faker 风格合成数据（类型标签与正文基本不相关、Resolution 多为占位文本），**只用于验证流程 / 状态机 / 护栏 / 评测管线，不得据此得出业务语义结论**；P5 聊天样例为项目内编写，不含真实客户信息。
- **项目内编写**：5 份 SOP、3 个 SKILL.md、全部文档与 eval golden。
- 本仓库**不调用任何平台 API**，P3 的「发送」只写本地 `runs/outbox.jsonl`，P5 只产出可复制话术。

详见 [`data/SOURCES.md`](data/SOURCES.md) 与 [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md)。

## 6. 文档索引

| 文档 | 用途 |
|---|---|
| [`docs/FEATURES.md`](docs/FEATURES.md) | **功能说明：5 个项目各自输入什么、做什么、产出什么（附真实产物示例）** |
| [`docs/TECHNICAL_REPORT.md`](docs/TECHNICAL_REPORT.md) | 主技术报告：调研、选型、架构、实现、取舍、评测、复现 |
| [`docs/TECHNICAL_REPORT.html`](docs/TECHNICAL_REPORT.html) | 技术报告的自包含可展示版（带目录导航、门禁快照、打印样式），由 `scripts/build_report_html.py` 生成 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 分层依赖、P1–P5 数据流图、workflow vs agent、框架替换映射 |
| [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) | 数据来源、许可证、诚实边界 |
| [`docs/INTERVIEW.md`](docs/INTERVIEW.md) | 30 秒 / 5 分钟讲法、白板稿、高频追问应答 |
| [`docs/RISK_REGISTER.md`](docs/RISK_REGISTER.md) | 威胁模型、权限矩阵、风险登记、失败模式与回滚 |
| 各项目 `README.md` | 单项目架构、数据、评测、30 秒 / 5 分钟 / 追问三档讲法 |
| [`evals/report.html`](evals/report.html) | 零依赖自包含数值报告 |

## 7. 目录结构

```
agent-portfolio/
├── README.md                      本文件
├── requirements.txt               核心零依赖 / 可选生产依赖
├── .env.example                   真实 LLM 模式配置模板
├── agentkit/                      共享内核（8 个模块）
├── data/                          开源数据 + SOURCES.md + rag_docs/manifest.json
├── scripts/                       fetch_data.py（抓取）· rag_ablation.py（消融）· build_report_html.py（HTML 报告）
├── projects/p1_research_agent/    P1
├── projects/p2_sql_agent/         P2
├── projects/p3_support_swarm/     P3
├── projects/p4_mcp_and_skills/    P4（含 3 个符合规范的 SKILL.md）
├── projects/p5_ppt_order_copilot/ P5
├── evals/                         run_all.py · report.html/.json · reports/*
├── tests/smoke_test.py            端到端冒烟
├── runs/                          轨迹 / checkpoint / outbox
└── docs/                          上述 6 份文档（FEATURES / 技术报告 / 架构 / 数据 / 面试 / 风险）
```

## 8. 一句话版本（面试可直接用）

> "我做了一套 5 个项目的 Agent 工程作品集，共享一个手写的零依赖内核：agent loop、工具契约、状态机、混合检索、护栏、轨迹和评估。三个真实工作流（带引用调研、SQL 自修复、工单多人协同）、一个手写 MCP Server + Agent Skills、一个来自我自己副业的人机协同接单 Copilot。全部离线可跑，55 个评测用例通过 53 个，两个失败案例我保留下来讲失败分析。"

**背下来的数字**：`recall@5 = 0.80（消融前 0.60）` · `groundedness = 0.98` · `平均 5 次工具调用/次` · `约 $0.0035/次` · `SQL 自修复率 100%` · `护栏拦截率 100%` · `金额审批覆盖率 100%` · `渐进式披露省约 60% 上下文`。

## 9. 许可

项目代码与文档由本人编写，用于学习与面试展示。第三方语料与数据库版权归各自所有者，许可证与引用建议见 [`data/SOURCES.md`](data/SOURCES.md)；商用前请按各自许可证另行确认。
