# Agent 工程作品集 · 技术报告

> **版本说明（2026-11-20）**：本文是原五项目作品集的历史总报告；P5 当前已经有 LangGraph 多角色流程，本文内旧报价状态图不代表新的 PPT 制作路径。P5 当前技术栈、持久化、澄清恢复与修改流程以 [`PROJECT_TECHNICAL_REPORT.md`](PROJECT_TECHNICAL_REPORT.md) 为准。

| 项目 | 内容 |
|---|---|
| 名称 | `agent-portfolio` — 面向 Agent / 大模型应用开发岗的工程作品集 |
| 版本 | v1.0.0 |
| 日期 | 2026-11-10 |
| 作者 | 万致远 |
| 代码规模 | 45 个 Python 文件 / 5,150 行；23 份项目 Markdown 文档 / 2,592 行（不含 `data/rag_docs/` 第三方语料）；另有自包含 HTML 展示版 `docs/TECHNICAL_REPORT.html` |
| 交付状态 | 5 个可运行项目全部完成；评测门禁 **PASS**；冒烟测试 **23/23** |
| 关键结论 | 55 个评测用例通过 53 个，5 个 suite 的回归门禁全部通过；2 个失败案例为**故意保留**的困难案例，用于展示失败分析能力 |

---

## 摘要

本报告记录一次完整的「从岗位能力模型反推作品集」的工程实践：先调研 2026 年 Agent 开发岗真实考察的能力项与开源生态，再从 GitHub 抓取**真实开源数据**与规范文档，最后交付 5 个相互关联、可离线运行、带数值化评测的 Agent 项目。

与常见的"调包 demo 合集"不同，本作品集的设计主线是**一条可讲清楚的能力递进**：

1. 先**手写** agent loop、工具契约、状态机、检索、护栏、轨迹 —— 证明理解原理；
2. 再用这条内核去实现三个真实工作流（调研 / 数据分析 / 客服工单）—— 证明能落地；
3. 再把能力封装成标准 MCP Server 与 Agent Skills —— 证明懂协议与生态；
4. 最后用一个来自本人真实副业的人机协同工作流 —— 证明会做**边界判断**（哪些该自动化、哪些必须留给人）；
5. 全程用统一 trace 与 eval harness 量化 —— 证明能回答"你怎么知道它好用"。

用户中途补充的「闲鱼 PPT 代做」方向经评估后**部分采纳**：放弃无合规接口可用的平台消息自动化，保留并深化了需求抽取、可解释定价、人工审批与修改轮次管理，形成第 5 个项目。

---

## 1. 任务定义与方向评估

### 1.1 原始需求

> 面试 agent 开发岗但项目少；需要几个**实际工作流**，能找到**开源数据/资料做 RAG**，有**开源 skill 和工具**；自行调研选取，评估方向可行性，能做就做，不能做就换一套；全程自主完成。

隐含的成功标准不是"文件数量"，而是：面试时能讲 5 分钟、能被追问三轮不塌、有可复现的数字、代码能被读。

### 1.2 补充方向：闲鱼 / 微信 PPT 代做工作流的可行性评估

用户补充的真实业务链路：闲鱼沟通 → 加微信 → 沟通制作细节（三类任务）→ 按页数与设计类型定价（10–60 元）→ 想法落实 → 反复修改。

| 子环节 | 技术可行性 | 合规 / 稳定性 | 结论 |
|---|---|---|---|
| 闲鱼自动收发消息、抓订单 | 无面向个人开发者的公开消息/订单 API；只能靠抓包、逆向、模拟登录 | 触发风控、随客户端改版失效、账号风险 | **放弃** |
| 微信个人号自动回复 | 无合规机器人接口；企业微信/公众号 API 触达不到个人好友会话 | 封号风险、违反平台条款 | **放弃** |
| 聊天记录导入（粘贴 / 导出文本） | 完全可行，零平台依赖 | 无风险 | **采用** |
| 需求三分类、页数/风格/交付时间抽取 | 可行（规则 + LLM 结构化输出） | — | **采用** |
| 可解释报价（10–60 元钳制）、需求确认单、制作 brief | 可行，纯确定性计算 | 金额是对外承诺，必须可审计 | **采用** |
| 修改轮次与超轮加价 | 可行，状态机 | — | **采用** |
| 生成可复制话术 | 可行；由人粘贴发送 | 保留人工对外的控制权 | **采用** |

**评估结论：方向可做，但需砍掉消息通道。** 这个取舍没有削弱项目，反而强化了它 —— 真实业务里"人必须拍板金额、人必须对外发言"本来就是硬约束，正好对应 Agent 岗最看重的 human-in-the-loop、guardrail 与能力边界。若未来出现官方 API，只需替换 `handoff` 节点，状态与报价逻辑不变。

### 1.3 交付范围

5 个项目 + 1 个共享内核 + 统一评估/文档体系，全部位于 `D:\WorkBuddy Workspace\2026-11-09-23-55-57\agent-portfolio\`。

> 本报告偏「为什么这样设计」。若要看「每个项目具体实现了哪些功能、输入什么、产出什么」，见 [`docs/FEATURES.md`](FEATURES.md)，其中逐条贴了 5 个真实运行产物。

---

## 2. 调研方法与发现

### 2.1 岗位能力模型（2026）

调研了 Agentic AI Engineer 路线图、招聘能力清单与面试题库，收敛出高频考察项：

| 能力 | 出现频率 | 本作品集对应 |
|---|---|---|
| 手写 agent loop / 停止条件 / 预算 | 极高 | `agentkit/loop.py`、P1、P2 |
| Tool / function calling 与 JSON Schema | 极高 | `agentkit/tools.py`、P2、P4 |
| RAG：分块、混合检索、重排、引用、检索评估 | 高 | `agentkit/rag.py`、P1、P3 |
| 多 Agent 编排 / 状态机 / 人在回路 | 高 | `agentkit/state.py`、P3、P5 |
| MCP 与 Agent Skills（协议、权限、渐进式披露） | 高（2026 新增权重） | P4 |
| 评估与可观测（轨迹、指标、回归门禁） | 高，且稀缺 | `agentkit/trace.py`、`agentkit/eval.py`、`evals/` |
| 安全：提示注入、PII、最小权限、沙箱 | 高 | `agentkit/guard.py`、P2/P3/P4/P5 |
| 成本 / 延迟 / 失败复盘 | 中高 | trace 成本估算、`docs/INTERVIEW.md` |

一个反复出现的判据：**"能报出『92% 任务成功率、平均 3 次工具调用、$0.04/次』的项目，比一百行功能描述更有说服力"**。这直接决定了本作品集必须自带 eval harness 与数值报告。

### 2.2 GitHub / 开源生态调研

| 来源 | 关键发现 | 对本项目的用途 |
|---|---|---|
| `anthropics/skills` | Agent Skills 开放标准：`SKILL.md` + YAML frontmatter；三阶段渐进式披露 | P4 的 skill 包与 `skill_loader.py` |
| `modelcontextprotocol/modelcontextprotocol` | 2026-07-28 规范：tools / resources / prompts、stdio 与 Streamable HTTP、授权与安全注意事项 | P4 手写 server + RAG 语料主体 |
| `PrefectHQ/fastmcp`、`modelcontextprotocol/python-sdk` | 官方/事实标准 SDK，装饰器式 API | P4 的可选生产适配器 |
| `langchain-ai/deepagents` `examples/text-to-sql-agent` | 官方示例用 Chinook 数据库 + skills 渐进式披露 | P2 选题与数据、RAG 语料 |
| `huggingface/agents-course` | Unit 1 公开 mdx 教程 | RAG 语料 |
| `qfc-network/ai-infra` | Anthropic《Building Effective Agents》中英整理 | RAG 语料 + 五种 workflow 模式的术语来源 |
| `lerocha/chinook-database` | 开源 SQLite 样例库 | P2 数据 |
| 公开 `customer_support_tickets.csv` 的 GitHub 镜像 | 8469 条工单、含类型/优先级/状态/解决方案 | P3 数据 |
| `bernierllc/claude-skills` `agent_skills_spec.md` | 完整 frontmatter 字段规范 | P4 skill 规范校验 |

### 2.3 环境约束与数据可得性

实测本机环境（Windows / Python 3.13）：

| 通道 | 结果 | 应对 |
|---|---|---|
| `api.github.com` | HTTP 200 可用 | 通过 **GitHub REST API**（tree + git blob，base64）抓取全部真实数据 |
| `raw.githubusercontent.com` | 超时 | 不走该通道 |
| `huggingface.co` | 隧道 502 不可达 | 不依赖 HF 直链；改用 GitHub 上的开源语料与镜像 |
| PyPI | HTTP 200 可用 | 但**核心依赖仍坚持零第三方库**，保证任何环境离线可跑 |

因此 `scripts/fetch_data.py` 用 tree API 一次列目录、blob API 逐文件下载，幂等可重跑（已下载文件跳过，规避 60 req/h 未认证限流）。所有抓取结果已随仓库落地，断网也能运行。

### 2.4 选题决策

选定 5 个项目，覆盖不同能力维度且共享同一内核，避免"5 个互不相关的玩具"：

| # | 项目 | 真实工作流 | 主打能力 | 开源数据 |
|---|---|---|---|---|
| P1 | RAG 深度调研 Agent | 技术问题 → 多轮检索 → 带引用简报 | 混合检索 / 引用 / 检索评估 | 30 篇 MCP/Skills/Agent 官方文档 |
| P2 | Text-to-SQL 自修复 Agent | 自然语言 → SQL → 报错自修复 → 洞察 + 图表 | 工具契约 / 护栏 / 环境反馈修复 | Chinook SQLite |
| P3 | 多 Agent 工单协作 | 分诊 → 检索 → 起草 → 审核 → 风险 → 人工审批 | 状态机 / evaluator-optimizer / HITL | 400 条工单（自 8469 条分层抽样） |
| P4 | MCP Server + Agent Skills | 把上述能力暴露为标准工具与技能 | 协议 / 权限 / 渐进式披露 | 复用 P1–P3 数据 |
| P5 | 闲鱼 PPT 接单 Copilot | 聊天导入 → 抽取 → 报价 → 人工确认 → brief/话术 | 边界判断 / 可解释定价 / HITL | 合成聊天样例（明确标注） |

---

## 3. 总体架构

### 3.1 分层

```
┌─────────────────────────────────────────────────────────────┐
│  交付层  5 个 README · docs/TECHNICAL_REPORT.md · evals/report.html │
├─────────────────────────────────────────────────────────────┤
│  项目层  P1 research │ P2 sql │ P3 support │ P4 mcp+skills │ P5 order │
├─────────────────────────────────────────────────────────────┤
│  共享内核 agentkit（零第三方依赖）                              │
│  llm · tools · loop · state · rag · guard · trace · eval       │
├─────────────────────────────────────────────────────────────┤
│  数据层  30 篇开源文档 / Chinook DB / 工单 CSV / 合成聊天样例     │
│          scripts/fetch_data.py（可复现抓取）                    │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 共享内核 `agentkit`

| 模块 | 职责 | 设计要点 |
|---|---|---|
| `llm.py` | 可插拔 LLM | `BaseLLM.chat` 统一接口；`OpenAICompatibleLLM` 用 urllib 实现 function calling（DeepSeek/OpenAI/Ollama 通用）；`ScriptedLLM` 是确定性策略替身；`chat_json` 带一次修复重试 |
| `tools.py` | 工具契约 | 函数签名 → JSON Schema；运行时校验 required/type/enum/未知字段；`permission` 白名单；`side_effect` 标记需审批；工具错误永不抛穿 agent loop |
| `loop.py` | agent loop | 手写 while 循环；`max_steps`/`max_tool_calls`/`max_total_tokens` 三层预算；重复调用检测并注入反思；错误回灌驱动自修复 |
| `state.py` | workflow graph | 显式 state、条件边、终止节点、JSON checkpoint、`Interrupt` / `resume()`、Mermaid 导出 |
| `rag.py` | 混合检索 | heading-aware 分块、BM25 + TF-IDF、RRF 融合、MMR 去冗余、双语查询改写、引用、`recall@k`/MRR/nDCG |
| `guard.py` | 护栏 | SQL 只读白名单、提示注入模式（中英）、PII 脱敏、风险分级、外部文本包装 |
| `trace.py` | 可观测 | span（llm/tool/node/gate）、参数、耗时、token、成本估算、JSON 轨迹 + Markdown 导出 |
| `eval.py` | 评估 | 版本化任务集、数值指标、阈值回归门禁、零依赖 HTML 报告 |

### 3.3 两种运行模式（重要，避免误解）

| 模式 | 触发 | 决策来源 | 用途 |
|---|---|---|---|
| **离线确定性模式**（默认） | 无 `LLM_API_KEY` | `ScriptedLLM`：项目内可读的确定性策略代码 | 断网可跑、评测可复现、CI 门禁 |
| **真实 LLM 模式** | 配置 `.env` 或 `--api` | OpenAI 兼容端点（DeepSeek / OpenAI / Ollama） | 真实生成、可对比同一套 eval |

**离线模式不是把结果硬编码**：它照样走完整的 agent loop、调用真实工具、查询真实数据库/语料、产生真实 trace 与真实数值，只是把"下一步调哪个工具"写成确定性策略。这是标准的 test double / deterministic harness 做法；切换只需替换 `llm` 对象，loop 与工具完全不变。报告中所有数字均来自离线确定性模式，可逐位复现。

### 3.4 能力矩阵

| 能力 | P1 | P2 | P3 | P4 | P5 |
|---|:--:|:--:|:--:|:--:|:--:|
| 手写 agent loop | ✓ | ✓ | | | |
| 工作流状态机 / HITL | | | ✓ | | ✓ |
| RAG + 引用 + 检索指标 | ✓ | | ✓ | ✓ | |
| 工具调用 / JSON Schema | ✓ | ✓ | | ✓ | |
| 错误自修复 | | ✓ | ✓ | | |
| 护栏 / 注入防护 / PII | ✓ | ✓ | ✓ | ✓ | ✓ |
| MCP / Agent Skills | | | | ✓ | |
| 多角色协作 / 审核回环 | | | ✓ | | |
| trace / eval / 回归门禁 | ✓ | ✓ | ✓ | ✓ | ✓ |

---

## 4. 关键技术实现

### 4.1 Agent loop 的三层预算与终止条件

```python
while steps < cfg.max_steps:
    response = llm.chat(messages, tools=schemas)
    if not response.tool_calls: return response.text        # 自然终止
    if tool_calls + len(response.tool_calls) > cfg.max_tool_calls: -> budget_exceeded
    for call in response.tool_calls:
        result = registry.call(call.name, call.arguments)   # 权限 + schema 校验
        messages.append({"role": "tool", "content": "<tool_output>...</tool_output>"})
    if repeated_identical_call: inject_reflection()
    if tool_error: inject_recovery_instruction()
return step_limit_exceeded                                   # 永不无限循环
```

`max_steps=8~10`、`max_tool_calls=8~10`、`max_total_tokens=60k~80k` 三道闸门；工具输出统一包裹、截断到 6000 字符，明确当作 DATA。

### 4.2 工具契约与最小权限

`ToolRegistry` 在调用点强制：`allowed_permissions`（默认只读）、`side_effect` 需 `allow_side_effect=True`（只有人工批准后才给）、参数校验失败返回结构化错误而非异常。P3 的 `send_reply` 与 P2 的 `query_sql` 是这套机制的两个极端示例。

### 4.3 混合检索与两个真实修复

**基线**：30 篇文档 → 420 个 heading-aware chunk（900 字符 / 120 overlap）→ BM25 + TF-IDF 余弦 → RRF（`k=60`）融合 → MMR 去冗余（Jaccard > 0.72 丢弃）→ 标题词重复加权。

**问题 1 · 跨语言**：语料以英文为主，用户常问中文。解决：`TERM_MAP` 领域双语词表做 query rewriting，把中文术语桥接成英文检索词（"授权"→authorization、"工具"→tools），并按查询语言调整桥接词权重。

**问题 2 · 语言不平衡导致 IDF 偏置**：只有 2/30 篇中文文档，中文单字 IDF 高达 `log(1+(420-2+0.5)/(2+0.5))≈5.1`，远超英文词，导致**任何中文问题都被同一批中文文档霸榜**。解决：对 CJK term 的 IDF 设上限 1.25（生产应换多语 embedding）。

**消融实验**（`scripts/rag_ablation.py`，10 个带 golden 的问题）：

| 变体 | recall@5 | MRR | 证据术语覆盖 |
|---|---:|---:|---:|
| A 无双语改写（IDF cap 开） | 0.60 | 0.60 | 0.55 |
| B 上线配置：改写 + IDF cap | **0.80** | **0.80** | **0.85** |
| C 改写开、IDF cap 关 | 0.70 | 0.70 | 0.70 |
| **B − A（改写贡献）** | **+0.20** | +0.20 | **+0.30** |
| **B − C（IDF 修复贡献）** | **+0.10** | +0.10 | +0.15 |

原始数据在 `evals/reports/rag_ablation.json`。

### 4.4 状态机、checkpoint 与人在回路

`Graph` 把节点、条件边、终止节点显式建模；节点返回 `Interrupt` 时先 `state.update(patch)` 再写 JSON checkpoint，**保证审批原因进入快照**（这是实现中修过的一个真实 bug）。`resume(checkpoint, approved=True)` 从 `resume_node` 继续。P3 与 P5 都用它，且都可导出 Mermaid 图。

### 4.5 SQL 护栏与环境反馈驱动的自修复

- 护栏：先剥注释与字符串字面量，再要求单条 `SELECT`/`WITH`；拒绝 DML/DDL/PRAGMA/ATTACH/多语句/`sqlite_master` 探测/危险函数；自动补 `LIMIT 500`；URI 只读连接。
- 自修复：注入"表名拼错"错误 → SQLite 返回真实 `no such table: Invoices` → 用第一轮缓存的**全库 schema** 做 `difflib` 模糊匹配 → 重写 SQL → 重试。该机制泛化到任意表/列名错误，不是"第二次硬编码正确答案"。

### 4.6 MCP 协议与 Agent Skills

- `server.py`：零依赖 JSON-RPC 2.0 over stdio，实现 `initialize`（capability negotiation，协议版本 2026-07-28）、`ping`、tools/list+call、resources/list+read、prompts/list+get、未知方法 `-32601`。工具输出用 `<tool_output>` 包裹；参数做注入检测并写 `_security_note`。
- `client.py`：**启动真实子进程**完成握手，用协议互通验证服务端，而不是自测函数。
- `server_fastmcp.py`：官方 SDK 等价实现（可选依赖）。
- 3 个符合规范的 SKILL.md（frontmatter 含 name/description/version/license/metadata/allowed-tools，name 与目录名一致），`skill_loader.py` 实现三阶段渐进式披露并量化：Discovery 仅 797 字符，全部加载需 7,524 字符，激活 1 个技能后上下文节省 **47%–61%**。

### 4.7 轨迹与成本

每次 LLM / tool / node / gate 调用都是 span，记录输入、输出、耗时、token、状态；`Tracer` 汇总 `llm_calls / tool_calls / tool_errors / tokens / est_cost_usd / blocked`，落盘 `runs/*.json`。示例：P1 单次调研（`MCP 授权流程和安全注意事项`）6 次 LLM 调用、5 次工具调用、11,955 tokens（in 11,385 / out 570）、约 $0.003427、12.5 ms（离线模式成本为按 token 的估算值，非真实账单）。

### 4.8 评估与回归门禁

`EvalSuite` 读取版本化 `eval_set.json`，逐 case 产出数值指标，聚合后与阈值比较；任一指标低于阈值则门禁 FAIL。`evals/run_all.py` 一次跑完 5 个 suite，生成 `evals/report.html`（零依赖深色主题）与 `report.json`，并以退出码表示是否可"发布"。

---

## 5. 数据、来源与许可

所有外部数据由 `scripts/fetch_data.py` 从 GitHub REST API 抓取，落地在 `data/`，每篇文档头部保留原始 URL。详见 `docs/DATA_SOURCES.md` 与 `data/SOURCES.md`。

| 数据 | 规模 | 来源 | 用途 |
|---|---|---|---|
| 技术文档语料 | 30 篇 / 420 chunks / 205,374 字符 | MCP 官方规范 2026-07-28、Agent Skills 规范、Anthropic《Building Effective Agents》中英整理、HF Agents Course、deepagents 示例文档 | P1 / P4 RAG |
| Chinook SQLite | 11 表 / 412 发票 / 3,503 曲目 / 1.0 MB | `lerocha/chinook-database` | P2 / P4 SQL |
| 客服工单 | 400 条分层抽样（源 8,469 条），其中 126 条已解决 | 公开 `customer_support_tickets.csv` 的 GitHub 镜像 | P3 知识库与评测 |
| 5 份 SOP | 项目内编写 | 明确标注**非开源数据** | P3 检索依据 |
| PPT 接单聊天 | 10 段合成对话 | **项目内合成，明确标注** | P5 流程演示 |

**诚实边界**：工单数据集是合成数据（类型与正文主题基本不相关、Resolution 为占位文本），只用于验证流程/护栏/评测管线，不得据此得出业务语义结论；PPT 聊天样例同样是合成数据，不含任何真实客户信息。生产替换方案写在各项目 README 的「数据说明」里。

---

## 6. 实测结果

### 6.1 总览

```
python evals/run_all.py   →  gate = PASS
TOTAL 53/55 cases passed · 5/5 suites gate PASS · smoke test 23/23
```

2 个未通过 case 位于 P1 且为**故意保留的困难案例**（见 6.3），门禁阈值按工程实际设定，未通过数据美化消除。

### 6.2 各项目指标

| 项目 | cases | 关键指标（实测） |
|---|---:|---|
| P1 RAG 深度调研 | 8/10 | recall@5 **0.80** · MRR **0.80** · groundedness **0.9826** · 证据术语覆盖 0.85 · citation_rate 0.80 · completion 1.00 · 平均 5.0 次工具调用 |
| P2 Text-to-SQL | 10/10 | 执行成功率 1.00 · 结果正确率 1.00 · **自修复率 1.00**（3 个注入错误用例）· 护栏拦截率 1.00（2 个对抗）· LIMIT 强制率 1.00 · 平均 4.2 次工具调用 |
| P3 工单协作 | 10/10 | 路由准确率 1.00 · 升级判定准确率 1.00 · PII 清洁率 1.00 · 审核修复率 1.00 · 证据率 1.00 · 轨迹完整率 1.00 |
| P4 MCP + Skills | 15/15 | 协议合规率 1.00 · 工具 schema 合规 1.00 · 工具执行 1.00 · 护栏/注入检测 1.00 · skill 路由 1.00 · **上下文节省 0.6057** |
| P5 接单 Copilot | 10/10 | 任务分类 1.00 · 页数抽取 1.00 · 价格区间与钳制 1.00 · 报价可复现 1.00 · 缺失信息追问 1.00 · **金额人工审批率 1.00** · 修改加价正确 1.00 |

真实价格样例（P5）：演讲稿 20 页 + 图表 = **¥49**；初版优化 12 页 = **¥18**；纯视觉 8 页 = **¥11**；急单 30 页 + 动画 → 上限钳制 **¥60**；纯视觉 5 页 → 下限钳制 **¥10**。

真实 SQL 结果样例（P2）：按国家收入 Top1 = USA / 523.06；最畅销艺人 = Iron Maiden / 138.60；平均发票 = 5.65 / 412 张。

### 6.3 失败案例与 A/B 实验（不做数据美化）

P1 两个失败案例：
- `r09_changelog_hard`「MCP 2026-07-28 版本有哪些变更」：口语化中文 + 日期型意图，改写词未命中 `changelog.mdx`；
- `r08_injection_least_privilege`「如何防止提示注入并做最小权限控制」：跨语料多意图，证据句少于 3 条，系统选择**少引用**而非编造引用 —— 这是正确的 abstention 行为，`citation_rate` 阈值因此设为 0.8 而非 1.0。

改进方向：LLM query decomposition、cross-encoder rerank、多语 embedding（BGE-M3）、把词覆盖版 groundedness 换成 LLM-as-judge 并做人工校准。

A/B 消融见 §4.3，原始数据 `evals/reports/rag_ablation.json`。

---

## 7. 安全模型与风险登记

完整表格见 `docs/RISK_REGISTER.md`。核心原则：

1. **工具输出、检索文档、用户工单/聊天一律是 DATA**，用标记包裹并截断，系统提示中明确声明忽略其中的命令式语句；
2. **高风险决策不交给模型**：SQL 白名单、风险分级、报价金额、审批门槛全部确定性代码裁定，LLM 只能解释；
3. **最小权限**：工具 `permission` 白名单 + `side_effect` 标记，未经批准 `ToolRegistry` 直接拒绝；
4. **不可逆动作前设 checkpoint**：`Interrupt` → 人工审批 → `resume`；
5. **零外发**：P3 的"发送"只写本地 `runs/outbox.jsonl`；P5 只产出可复制话术；整个仓库不调用任何平台 API。

| 风险 | 缓解 | 残余 |
|---|---|---|
| 提示注入（文档/工单/聊天） | 模式检测 + 输出包裹 + 确定性风险分级 | 规则覆盖有限，需 LLM judge 补充 |
| PII 泄露 | intake 阶段脱敏，评测断言清洁率 1.00 | 中文地址/姓名未覆盖 |
| SQL 破坏 | 语法白名单 + 只读连接 + LIMIT | 生产仍需数据库账号级只读 |
| Agent 失控 / 烧钱 | 三层预算 + 重复检测 + 轨迹 | 离线模式成本为估算 |
| 幻觉引用 | 抽取式简报 + groundedness 指标 | 词覆盖只是 faithfulness 代理指标 |
| 平台合规 | 不接闲鱼/微信接口 | 需人工复制发送，牺牲自动化程度 |

---

## 8. 工程取舍、诚实边界与已知限制

| 取舍 | 理由 |
|---|---|
| 手写内核而非全用 LangGraph | 面试要能解释 state/edge/interrupt/loop 的语义；提供 Mermaid 与概念映射，生产可整体替换 |
| 零第三方依赖 | 保证断网、无 key、任意 Python 3.10+ 环境可跑；生产适配（FastMCP、Qdrant、BGE）作为可选层保留 |
| BM25+TF-IDF 而非向量库 | 420 chunks 规模下足够且完全可解释；`HybridRetriever` 接口按可替换设计 |
| 离线 `ScriptedLLM` | 可复现评测/CI；绝不冒充"模型智能"，真实模式随时可切 |
| 2 个失败 case 保留 | 展示失败分析与阈值设定能力，比 100% 通过更可信 |
| 合成数据明确标注 | 避免把流程演示包装成业务结论 |

**已知限制**：P1 检索在中文口语化/多意图问题上仍有 20% 未命中；P2 离线 NL→SQL 是关键词模板，不覆盖嵌套/时间窗口；P3 数据集语义质量有限、checkpoint 单文件无并发隔离；P4 只实现 stdio，未实现 Streamable HTTP / OAuth / tasks；P5 需求抽取是中文规则引擎，未覆盖还价、取消、重复下单。

---

## 9. 复现指南

```bash
cd agent-portfolio

# 0) 零依赖，Python 3.10+ 即可
python -m compileall -q agentkit projects evals scripts

# 1) 重新抓取真实开源数据（可选，仓库已内置快照）
python scripts/fetch_data.py

# 2) 五个项目各跑一次
python projects/p1_research_agent/run_demo.py "MCP 授权流程和安全注意事项" --save
python projects/p2_sql_agent/run_demo.py "按国家统计总收入" --inject-error --save
python projects/p3_support_swarm/run_demo.py --risk            # 人工审批闭环
python projects/p4_mcp_and_skills/run_demo.py --save
python projects/p5_ppt_order_copilot/run_demo.py --chat c01_speech_to_ppt --save

# 3) 全量评测 + 回归门禁 + HTML 报告
python evals/run_all.py

# 4) 端到端冒烟
python tests/smoke_test.py

# 5) RAG 消融实验
python scripts/rag_ablation.py

# 6) 生成本报告的可展示 HTML（带目录导航 / 门禁快照 / 打印样式）
python scripts/build_report_html.py

# 7) 接真实模型（DeepSeek / OpenAI / Ollama 均可）
cp .env.example .env      # 填 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
python projects/p1_research_agent/run_demo.py --api "workflow 和 agent 的区别"
python evals/run_all.py   # 同一套评测对比真实模型
```

不需要 `pip install`（可选依赖见 `requirements.txt`）。报告产物：`docs/TECHNICAL_REPORT.html`、`evals/report.html`、`evals/report.json`、`evals/reports/*.md`、`evals/reports/*.svg`、`runs/*.json`。

---

## 10. 面试叙事

**30 秒总版**："我做了一套 5 个项目的 Agent 工程作品集，共享一个手写的零依赖内核：agent loop、工具契约、状态机、混合检索、护栏、轨迹和评估。三个真实工作流（带引用调研、SQL 自修复、工单多人协同），一个手写 MCP Server + Agent Skills，还有一个来自我自己副业的人机协同接单 Copilot。全部离线可跑，55 个评测用例有 53 个通过，两个失败案例我保留下来讲失败分析。"

**5 分钟版**与**高频追问**的完整话术见 `docs/INTERVIEW.md`；每个项目 README 末尾也有该项目的 30 秒 / 5 分钟 / 追问三档讲法。

**一句话数字**（建议背下来）：
> "recall@5 = 0.80（消融前 0.60），结论 groundedness = 0.98，平均 5 次工具调用/次，约 $0.0035/次；SQL 自修复率 100%，护栏拦截率 100%，金额审批覆盖率 100%，渐进式披露省掉约 60% 上下文。"

---

## 11. 后续工作

1. 接入真实 LLM 跑同一套 eval，产出"离线策略 vs 真实模型"对比表；
2. P1 增加 query decomposition 与 cross-encoder rerank，目标 recall@5 ≥ 0.9；
3. P3 引入 LangGraph 适配层与 Langfuse/OTel 导出，验证概念可迁移；
4. P4 补 Streamable HTTP + OAuth + `resources/subscribe`；
5. P5 换真实聊天导出（脱敏后）并用 `chat_json` 替换规则抽取，保留确定性校验层；
6. 增加并发/多租户隔离与 checkpoint 存储后端。

---

## 附录 A · 目录结构

```
agent-portfolio/
├── README.md                     作品集总览 + 能力矩阵 + 快速开始
├── docs/
│   ├── FEATURES.md                功能说明：5 个项目输入/动作/产物 + 真实示例
│   ├── TECHNICAL_REPORT.md        本文件（源文件）
│   ├── TECHNICAL_REPORT.html      自包含可展示版（build_report_html.py 生成）
│   ├── ARCHITECTURE.md            架构、数据流、框架替换映射
│   ├── DATA_SOURCES.md            数据来源、许可证、诚实边界
│   ├── INTERVIEW.md               面试讲法与高频追问
│   └── RISK_REGISTER.md           权限、护栏、失败模式、回滚
├── agentkit/                      共享内核（8 个模块）
├── data/                          真实开源数据 + SOURCES.md
├── scripts/fetch_data.py          可复现数据抓取
├── scripts/rag_ablation.py        检索消融实验
├── projects/p1_research_agent/    P1
├── projects/p2_sql_agent/         P2
├── projects/p3_support_swarm/     P3
├── projects/p4_mcp_and_skills/    P4（含 3 个 SKILL.md）
├── projects/p5_ppt_order_copilot/ P5
├── evals/run_all.py               评测门禁
├── evals/report.html / .json      评测报告
├── tests/smoke_test.py            端到端冒烟
└── runs/                          轨迹 / checkpoint / outbox
```

## 附录 B · 指标定义

| 指标 | 定义 |
|---|---|
| recall@5 | 首轮 top-5 检索结果中包含 golden 文档的问题占比 |
| MRR | 首个正确文档排名倒数的均值 |
| groundedness | 结论句词元被检索证据覆盖的比例（faithfulness 的词覆盖代理指标） |
| self_repair_rate | 注入错误后能依据环境报错自动重写并成功执行的比例 |
| guard_block_rate | 危险 SQL / 注入请求被拦截且未执行的比例 |
| escalation_precision | 应升级人工的升级、不应升级的不升级的比例 |
| context_saved_ratio | 1 −（Discovery 目录 + 已激活技能正文）/（全部技能正文） |
| completion_rate | 在预算内正常终止（非 step_limit / error）的比例 |
| case_pass_rate | 单 suite 内满足全部验收条件的用例占比 |
