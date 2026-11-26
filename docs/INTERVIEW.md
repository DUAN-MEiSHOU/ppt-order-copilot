# 面试讲法与高频追问

> 配套 [`TECHNICAL_REPORT.md`](TECHNICAL_REPORT.md)。目标不是背稿，而是**被追问三轮不塌**：每一句结论都能指向具体文件、具体代码路径、具体数字。
> 建议先跑一遍 `python evals/run_all.py` 和 `python tests/smoke_test.py`，再来看这份文档。

---

## 0. 使用方式

| 场景 | 用哪一节 | 时长 |
|---|---|---|
| 「自我介绍 / 简单说说你的项目」 | §1.1 30 秒版 | 30s |
| 「挑一个最有代表性的项目讲讲」 | §1.2 90 秒版 + §2 任选一张白板图 | 2min |
| 「详细介绍一下这套作品集」 | §1.3 5 分钟版 | 5min |
| 技术面深挖 / 交叉追问 | §4 高频追问 + §2 白板稿 | 10–20min |
| 现场演示 / 共享屏幕 | §6 demo 脚本 | 3min |
| 反问环节 | §8 | 1min |

**三条铁律**

1. **先讲取舍，再讲实现**：「为什么这样设计」永远比「我用了什么」值钱。
2. **每个数字都要能说出来源**：`evals/report.html`、`evals/report.json`、`runs/*.json`。
3. **主动暴露边界**：合成数据、离线策略、2 个失败 case、没做 Streamable HTTP —— 主动说，比被问出来强得多。

---

## 1. 三档讲法

### 1.1 30 秒版（背下来）

> "我做了一套 5 个项目的 Agent 工程作品集，共享一个手写的零依赖内核：agent loop、工具契约、状态机、混合检索、护栏、轨迹和评估。三个真实工作流——带引用的技术调研、SQL 报错自修复、客服工单多角色协同；一个手写 MCP Server + Agent Skills；还有一个来自我自己副业的人机协同接单 Copilot。全部离线可跑，55 个评测用例通过 53 个，两个失败案例我保留下来专门讲失败分析。"

### 1.2 90 秒版（单项目深挖开场，以 P1 为例）

> "最代表性的是 P1 带引用的调研 Agent。它面向一个具体工作流：给技术问题，多轮检索本地 30 篇开源文档，读原文、校验依据，最后输出每条结论都带来源编号的简报。
> 我手写了一个 ReAct 风格的 agent loop，模型自己决定检索几轮、读哪个 chunk、什么时候收尾，同时用 `max_steps`、`max_tool_calls`、`max_total_tokens` 三层预算兜底，检测到重复工具调用会注入反思提示。检索是 BM25 + TF-IDF 余弦，RRF 融合，MMR 去冗余。
> 做的过程中发现两个真问题：一是语料以英文为主但用户常问中文，加了领域双语词表做 query rewriting；二是 30 篇里只有 2 篇中文，中文单字 IDF 高达 5.1，导致任何中文问题都被同一批中文文档霸榜，所以对 CJK term 的 IDF 设了上限。我做了 A/B 消融：改写贡献 +0.20 recall@5，IDF 修复再贡献 +0.10，最终 0.80。
> 防幻觉上离线模式输出抽取式简报，结论句必须是文档原句，用 groundedness 量化证据覆盖，实测 0.98。这个数我不吹成『正确率』——它只是个词覆盖代理指标。"

### 1.3 5 分钟版（时间轴）

| 时间 | 讲什么 | 落点 |
|---|---|---|
| 0:00–0:30 | 30 秒版 + 一句定位：「不是 5 个玩具，是一条能力递进」 | `README.md` §1 |
| 0:30–1:10 | **为什么这样选**：从岗位能力模型反推，7 个高频考察项；调研了 MCP 规范、Agent Skills、Anthropic《Building Effective Agents》、deepagents 示例 | 技术报告 §2 |
| 1:10–2:00 | **共享内核**：手写 8 个模块，画 agent loop 白板图，讲三层预算、工具契约、最小权限 | §2.1 白板图 A |
| 2:00–3:10 | **三个工作流**：P1 agent（检索角度不可预知）/ P2 workflow + 小 agentic 修复核心 / P3 显式状态机 + HITL。点出「生产系统大多是 workflow，只在必要处嵌小 agent」 | §2.2 白板图 B |
| 3:10–3:50 | **协议与生态**：手写 MCP JSON-RPC over stdio，tools/resources/prompts 三类能力，client 起真子进程验证；3 个 SKILL.md + 渐进式披露省 60% 上下文 | `docs/ARCHITECTURE.md` |
| 3:50–4:20 | **边界判断（P5）**：闲鱼/微信没有合规消息 API，主动砍掉消息通道，保留导入 + 结构化 + 人工发送；金额必须人工拍板 | 技术报告 §1.2 |
| 4:20–5:00 | **怎么知道它好用**：统一 trace + eval harness、53/55、5/5 gate、23/23 冒烟、消融实验、2 个故意保留的失败案例与改进方向 | `evals/report.html` |

**收尾一句**："如果只看功能描述会觉得平平无奇，我真正想展示的是**能被测量、能被追问、能被替换**的工程判断。"

---

## 2. 白板稿（三张图，30 秒能画完）

### 2.1 图 A · agent loop 与三层预算

```
while steps < max_steps:
    r = llm.chat(messages, tools=schemas)
    if not r.tool_calls: return FINISH          # 自然终止
    if tool_calls + len(r.tool_calls) > max_tool_calls: return BUDGET_EXCEEDED
    for call in r.tool_calls:
        res = registry.call(name, args)          # schema 校验 + permission + side_effect
        messages.append(role="tool", content="<tool_output> ... </tool_output>")  # DATA，不是指令
    if repeated_identical_call: inject_reflection()
    if tool_error: inject_recovery_instruction()  # 错误回灌 → 自修复
    if tokens > max_total_tokens: return BUDGET_EXCEEDED
return STEP_LIMIT_EXCEEDED                       # 永不无限循环
```

配套口播：「终止条件有四类——自然结束、步数耗尽、工具次数耗尽、token 耗尽；工具错误不当异常抛出，而是回灌给模型让它改参数，这是 P2 自修复的基础。」

### 2.2 图 B · workflow vs agent（本作品集的立场）

```
workflow（开发者定控制流）            agent（模型定控制流）
  已知步骤 / 含不可逆动作              检索角度 / 子任务数不可预知
  P3 工单、P5 报价、P2 主体           P1 调研、P2 报错修复核心
         └──────── 共用 agentkit.trace / eval ────────┘
```

配套口播：「Anthropic 那篇的结论我认同——能写死就别让模型自由发挥。P3、P5 涉及金额和对外发送，几乎全是 workflow + 人工审批。」

### 2.3 图 C · 混合检索流水线

```
30 docs → heading-aware chunk (900/120) → 420 chunks
        → BM25 ┐
               ├→ RRF(k=60) → MMR(Jaccard>0.72 丢弃) → title boost → top-k
        → TFIDF┘
    ↑ query rewriting: 中文 → TERM_MAP → 英文桥接词（按语言加权）
    ↑ CJK IDF cap = 1.25（修复语言偏置）
                    → [n] 引用 → 抽取式简报 → groundedness
```

配套口播：「全部可解释、零依赖。上生产只需替换 `HybridRetriever.search()` 返回 `Hit` 列表，其余不动。」

---

## 3. 五个项目各 30 秒

| 项目 | 讲法 |
|---|---|
| **P1** | "带引用的调研 Agent：多轮检索 30 篇真实开源文档，抽取式简报每条结论带来源，recall@5 从 0.60 优化到 0.80，groundedness 0.98，两个中文困难 case 我留着讲失败分析。" |
| **P2** | "Text-to-SQL：先读全库 schema，生成 SQL 过只读白名单，真实 SQLite 报错后用 `difflib` 模糊匹配重写再执行，3 个注入错误用例 100% 修好，2 个危险 SQL 100% 拦截，报告带真实数字和 SVG 图表。" |
| **P3** | "工单协作：Triage / Knowledge / Writer / Critic / Policy 五角色，Critic 不通过就回 draft 重写最多 2 轮；风险分级由确定性代码裁定，高风险写 checkpoint 中断，人工 resume 后才发；发送只写本地 outbox。" |
| **P4** | "手写 MCP Server：零依赖 JSON-RPC 2.0 over stdio，`initialize` 能力协商、tools/resources/prompts 三类能力、未知方法 `-32601`；client 起真实子进程握手验证。另外 3 个符合规范的 SKILL.md，渐进式披露省 60% 上下文。" |
| **P5** | "来自我真实副业：闲鱼 PPT 代做。平台消息 API 不合规，我不碰；只做聊天导入 → 三类需求抽取 → 按页数和设计类型的可解释报价（钳制 10–60 元）→ 金额人工审批 → 制作 brief 和可复制话术 → 修改轮次超轮加价。" |

---

## 4. 高频追问与应答

### 4.1 架构与选型

**Q：为什么不用 LangChain / LangGraph / AutoGen？**
> "两个原因。一是面试要能解释 state、edge、interrupt、budget 的语义，用框架容易变成调 API；二是我想证明依赖方向可控——`projects → agentkit → 标准库` 单向，`agentkit` 不 import 任何 project。但我不是反对框架：`docs/ARCHITECTURE.md` 里写了替换映射，`Graph` 的 node/conditional_edge/interrupt 和 LangGraph 的 `StateGraph`/`Command(resume=...)` 概念一一对应，加一个适配层就能换；`ToolRegistry` 产出的 schema 已经是 function calling / MCP 格式，P4 还给了 FastMCP 适配器。"

**Q：零第三方依赖是不是为了炫技？**
> "主要是可复现性：断网、无 key、任意 Python 3.10+ 环境都能跑通全部 demo 和 55 个评测用例，面试官当场 `python evals/run_all.py` 就能验证我报的数字。代价我认：没有向量检索、没有真正的 JSON Schema 库、没有并发隔离。所以我在架构里把每个自研抽象都标了生产对应物和替换成本，`requirements.txt` 里列了可选依赖但全部注释掉。"

**Q：workflow 和 agent 你怎么选？**
> "看控制流归属能不能预先确定。检索角度、要不要再查一轮、报错后怎么改——这类不确定性交给模型（P1、P2 修复核心）。涉及金额、对外发送、合规审批的步骤必须写死并设人工闸门（P3、P5）。我的立场是生产里 workflow 占大头，agent 只嵌在必要处。"

**Q：为什么 5 个项目要共享内核，不怕耦合吗？**
> "共享的是机制不是业务：`loop / tools / state / rag / guard / trace / eval`。这样评测口径统一、trace 格式统一、安全策略改一处全项目生效。解耦靠单向依赖和接口替换，P4 复用的是 P1/P2/P3 的函数而不是复制代码。"

### 4.2 评测与可观测（这一块最能拉开差距）

**Q：你怎么知道它好用？**
> "`agentkit/eval.py` 里有版本化 `eval_set.json`、数值指标和阈值门禁。`python evals/run_all.py` 跑 5 个 suite 共 55 个 case，生成 `evals/report.html` 和 `report.json`，任一指标低于阈值退出码非 0。当前 `gate = PASS`，53/55，5/5 suite 通过，冒烟 23/23。trace 里每次 LLM / tool / node / gate 都是一个 span，记录参数、耗时、token、成本估算、状态，落盘 `runs/*.json`。"

**Q：为什么有 2 个 case 不过还不修？**
> "故意留的。`r09_changelog_hard` 是口语化中文 + 日期型意图，改写词没命中 `changelog.mdx`；`r08_injection_least_privilege` 是跨语料多意图，证据句少于 3 条，系统选择少引用而不是编造引用——这其实是正确的 abstention。我把 `citation_rate` 阈值从 1.0 调到 0.8 是按工程实际设门禁，不是删用例。改进方向是 LLM query decomposition、cross-encoder rerank、多语 embedding。面试里能讲清楚自己系统在哪失效，比报 100% 更可信。"

**Q：指标怎么定的？会不会挑好测的测？**
> "每个指标对应一个失败模式：recall@5/MRR 对应检索漏召，groundedness 对应幻觉引用，self_repair_rate 对应环境反馈修复，guard_block_rate 对应危险 SQL，escalation_precision 对应误升级，context_saved_ratio 对应渐进式披露。对抗用例是 explicitly 放进去的——P2 有 DROP TABLE 和注入，P3 有提示注入和高额退款，P5 有 PII 和指令覆盖。阈值写在 `eval_set.json` 里可审计。"

**Q：trace 里记什么？成本怎么算？**
> "span 类型有 llm / tool / node / gate，字段包含 name、输入摘要、输出摘要、耗时、token 估算、状态、错误信息。`Tracer.totals()` 汇总 `llm_calls / tool_calls / tool_errors / tokens_in / tokens_out / est_cost_usd / blocked`。P1 单次 demo 实测 6 次 LLM 调用、5 次工具调用、11,955 tokens（in 11,385 / out 570）、约 $0.003427、12.5 ms。**注意离线模式的成本是按 token 单价的估算值，不是真实账单**，我每次都会主动说明这一点。"

**Q：groundedness = 0.98，能说明答案正确吗？**
> "不能。它是词覆盖代理指标——结论句词元被检索证据覆盖的比例，只能证明『有出处』，不能证明因果正确或推理无误。而且我特意只统计结论句，早期版本把整份报告的标题、URL、诊断文字都算进去，指标被稀释到 0.31，修完才 0.98。线上应该换 LLM-as-judge 配人工抽检校准，再补 fact-level 的 entailment 检查。"

**Q：离线模式是不是把答案硬编码了，算造假吗？**
> "不是。它跑的是同一个 `AgentLoop`、同一套 `ToolRegistry`、真实的 SQLite 查询和真实的 30 篇文档检索，产出真实 trace 和真实数字；唯一被替换的是 `BaseLLM.chat()` 里『下一步调哪个工具』的决策，写成项目内可读的确定性策略（`ScriptedLLM`）。这是标准的 test double / deterministic harness，用途是让评测可复现、CI 可跑。切换 `--api` 只换 `llm` 对象，loop 和工具一行不改。但我从不把离线结果说成『模型智能』——报告里所有数字都标注了 `scripted-offline`。"

### 4.3 RAG 与检索

**Q：为什么不用向量库 / 怎么用 embedding？**
> "420 个 chunk 的规模，BM25 + TF-IDF + RRF 在零依赖下足够且完全可解释，能直接看出为什么命中。`HybridRetriever` 的接口设计成返回 `Hit` 列表，上生产换 BGE-M3 + Qdrant + cross-encoder rerank 只需实现一个 `search()`。这也是我留的 P1 改进方向之一，目标 recall@5 ≥ 0.9。"

**Q：中文检索那个 IDF 问题具体怎么发现、怎么验证的？**
> "跑 10 个中文评测问题时发现 top1 总是同两篇中文文档。查 IDF：`log(1+(420-2+0.5)/(2+0.5))≈5.1`，而英文词普遍 2–3，中文单字天然霸榜。修法是对 CJK term 的 IDF 上限截断到 1.25。为了不靠感觉，我写了 `scripts/rag_ablation.py` 做三变体：A 无改写 recall@5 0.60，B 上线配置 0.80，C 关掉 IDF cap 0.70，所以改写贡献 +0.20、IDF 修复 +0.10。原始数据在 `evals/reports/rag_ablation.json`。生产上正解还是多语 embedding，cap 是个可解释的过渡方案。"

**Q：怎么保证引用不是编造的？**
> "离线模式是抽取式：简报里每条结论直接取自检索到的原文句子，`compose_brief` 不生成新事实，chunk 保留 `source_url` / `section` / `chunk_id`，`[n]` 能反查到 `data/SOURCES.md`。同时用 groundedness 监控。真实 LLM 模式下这层约束会变弱，所以我把它列为已知限制，线上需要引用校验器逐条回查原文。"

**Q：分块策略怎么定的？**
> "heading-aware，900 字符 / 120 overlap，保留章节标题参与检索并做 title boost。因为语料是 mdx 规范文档，按标题切比定长切更能保住语义完整。还顺手修了个坑：抓取文件头部先有 HTML 注释再有 YAML frontmatter，清洗顺序反了会把 `title: sidebarTitle:` 这类噪声混进 snippet，改成先剥注释再剥 frontmatter。"

### 4.4 工具、SQL 与安全

**Q：Tool calling 的契约怎么保证？**
> "`Tool` 从 Python 函数签名生成 JSON Schema，`ToolRegistry.call()` 在调用点校验 required / type / enum / 未知字段，校验失败返回结构化 `ToolResult(error=...)` 而不是抛异常穿透 loop。权限用 `permission` 白名单，副作用用 `side_effect` 标记——未经批准 `send_reply` 这类工具直接被拒。工具输出统一 `<tool_output>` 包裹并截断 6000 字符，系统提示里明确它是 DATA 不是指令。"

**Q：SQL 护栏真挡得住吗？绕过注入怎么办？**
> "分层：`validate_sql` 先剥注释和字符串字面量再检查，拒绝多语句、非 SELECT/WITH 开头、DML/DDL/PRAGMA/ATTACH、`sqlite_master` 探测和危险函数；`enforce_limit` 自动补 `LIMIT 500`；执行用 `file:...?mode=ro` 只读 URI 连接。评测里 `s09_guard_drop`、`s10_guard_injection` 都 100% 拦截且未执行。**但这只是应用层防线，生产必须再做数据库账号级只读 + 独立 schema + 查询超时 + 资源配额**，这条我写在风险登记里。"

**Q：自修复是不是其实就是第二次硬编码正确答案？**
> "不是。流程是：注入一个泛化的表名拼写错误（`inject_schema_error` 对任意 `FROM` 后的表名加 s/_v2）→ SQLite 返回真实 `no such table: Invoices` → `repair_sql` 从报错文本里正则抽错误对象，拿第一轮 `describe_table` 缓存的**全库 schema** 做 `difflib.get_close_matches` 模糊匹配 → 重写 SQL → 重试。同样支持 `no such column`。3 个不同意图的注入用例都修好了，self_repair_rate = 1.00。这里有个我自己踩过的真实 bug：策略读 tool message 时没解包 `ToolResult` 外层 `{"result": ...}`，导致看不见错误，自修复率一度是 0。"

**Q：提示注入怎么防？**
> "四层：中英注入模式检测（`INJECTION_PATTERNS`）、外部内容统一包裹并截断、确定性风险分级（`assess_ticket`，模型不能下调风险等级）、不可逆动作前 checkpoint 人工审批。P3 的 `t09_prompt_injection` 和 P5 的 `o06_prompt_injection` 都是对抗用例，前者升级为 critical 并中断，后者标记 `中文指令覆盖` 且价格仍按规则算。**残余风险我明说**：正则覆盖有限，语义型/编码型注入会漏，线上要补 LLM judge 和输入编码归一化。"

**Q：PII 脱敏覆盖全吗？**
> "覆盖邮箱、手机号、身份证、微信号，评测里 `pii_clean_rate` 硬阈值 1.00，P3 和 P5 都有用例。**中文姓名、住址、银行卡、订单号没覆盖**，这是明确的残余风险；生产要上 NER + 词典 + 出口侧二次扫描（防止模型从上下文复原）。"

### 4.5 MCP、Skills 与 HITL

**Q：MCP 和 function calling 有什么区别？**
> "function calling 是模型与**同一进程内**工具的调用约定；MCP 是把工具、资源、提示词变成**跨进程的标准服务**，有 `initialize` 能力协商、协议版本、传输层（stdio / Streamable HTTP）、错误码。我这层 `ToolRegistry` 生成的 schema 与 MCP `tools/list` 格式一致，P4 的 server 相当于把它包装成协议端点。"

**Q：tools / resources / prompts 三者怎么分？**
> "tools 是模型可调用、有副作用潜力的动作，参数由模型填；resources 是应用/用户可控的只读上下文（`docs://corpus/stats`、`schema://chinook` 等 4 个）；prompts 是服务端预置的可复用提示模板（`research_brief`、`sql_analysis`），由用户或客户端显式选用。区分的关键是**谁掌握控制权**。"

**Q：Skills 和 MCP 什么关系？为什么两个都要做？**
> "MCP 解决『能力怎么接进来』，Skills 解决『什么时候该用哪份知识』。SKILL.md 有 YAML frontmatter（name/description/version/license/metadata/allowed-tools，name 与目录名一致），三阶段渐进式披露：Discovery 只读 name+description（797 字符），Activation 才读完整正文，references/ 和 scripts/ 按需加载。全量加载要 7,524 字符，激活 1 个技能实测节省 47%–61% 上下文。我用 `skill_loader.py` 把这个节省量化成了 `context_saved_ratio = 0.6057` 进评测。"

**Q：Human-in-the-loop 具体怎么实现？能恢复吗？**
> "节点返回 `Interrupt` 时，`Graph` 先 `state.update(patch)` 再写 JSON checkpoint，落 `runs/`，然后 `resume(checkpoint, approved=True/False, reviewer=...)` 从 `resume_node` 继续。这里修过一个真 bug：初版在写 checkpoint 之前就 return Interrupt，导致审批原因和 `risk_level` 没进快照，resume 后风险状态丢失，`escalation_precision` 一度只有 0.7；改成先 update 再中断后回到 1.00。checkpoint 目前是单文件、无并发隔离，多租户场景要换存储后端。"

**Q：为什么多 Agent 不用现成框架？五角色会不会太重？**
> "角色数不是为了炫，是对应五个真实职责：分类、找证据、写回复、审核、风险裁定。其中 Policy 故意**不让模型做**——风险等级用确定性 `assess_ticket()`，模型只能解释。Critic 不通过时回 draft 重写，最多 2 轮后由人工兜底，是 evaluator-optimizer 模式。用框架能少写代码，但我想让『谁在什么条件下把控制流交给谁』在 `graph.py` 里一眼可见，还能导出 Mermaid 图给面试官看。"

### 4.6 P5 与业务判断

**Q：为什么不做闲鱼/微信自动收发消息？**
> "闲鱼没有面向个人开发者的公开消息/订单 API，微信个人号也没有合规机器人接口；逆向、抓包、模拟登录会触发风控、随客户端改版失效，还有账号和条款风险。用户明确说过中间过程若牵扯 API 不好实现就放弃，所以我砍掉消息通道，保留后半段：聊天记录导入/粘贴、需求三分类、按页数和设计类型的可解释报价、需求确认单、制作 brief、修改轮次与超轮加价、人工发送话术。未来若有官方 API，只替换 `handoff` 节点，状态与报价逻辑不变。"

**Q：报价为什么用规则不用 LLM？**
> "金额是对外承诺，必须可审计、可复现、可解释。`pricing.py` 里三类任务基价 + 页数 + 附加项 + 加急系数，最后 `max(10, min(60, raw))` 钳制到真实业务区间；评测里 `price_in_range`、`price_reproducible` 都是硬阈值 1.00。LLM 可以用来做需求抽取，但**裁定权不给模型**。而且金额进 `approval_gate` 必须人工确认，`approval_gate_rate = 1.00`。顺带修了两个中文解析坑：`第 5 页` 不能当总页数、`不着急` 不能被识别成加急。"

**Q：PPT 聊天数据是真实的吗？**
> "不是，是项目内写的 10 段合成对话，文件里 `_note` 明确标注，不含真实客户信息。客服工单数据集也是合成数据，类型标签和正文基本不相关。这两个我主动说明：它们能验证流程、状态机、护栏和评测管线，**不能证明业务效果**。生产替换方案写在各项目 README 和 `docs/DATA_SOURCES.md`。"

### 4.7 工程与成长

**Q：开发中印象最深的 bug 是什么？**
> 挑一个讲透，别流水账。推荐讲 **P2 自修复失效**：现象是 `--inject-error` demo 输出 `Query finished without a report.`，`EXECUTED=False`；定位到 `_last_tool()` 读 tool message 时没解包 `ToolResult` 外层 `{"result": ...}`，策略拿不到错误信息；修法是解包 + 调整 policy 分支顺序（先 blocked / error / fixed_sql / report / chart，最后才输出报告）；泛化上把硬编码的 `buggy_sql` 换成 `inject_schema_error()`，并让 `repair_sql` 同时支持 `no such table` 和 `no such column`；最终 3 个注入用例 100% 修复。这个例子能同时讲清 debug 路径、可观测性价值和泛化意识。

其他可备用的真实 bug（都能指向具体修复）：
- `agentkit/__init__.py` 漏导出 `expansion_terms` → P1 ImportError；
- `clean_markdown()` 清洗顺序错误 → mdx frontmatter 噪声混进 snippet；
- P3 中断前未 `state.update(patch)` → 审批后风险状态丢失；
- P3 Critic 重写用字符串替换禁用词 → 生成语义荒谬的回复，改成按 checklist 重新起草；
- P5 `Requirements` dataclass 经 `json.dump(default=str)` 后变成字符串，改用 `asdict()` 存、节点里重建；
- P2 `describe_table` 缓存分支里 `all_cols` 未绑定；图表 Markdown 相对路径错；
- Mermaid 终止节点自环 `done --> done([DONE])`。

**Q：给你两周继续做，先做什么？**
> "第一优先级是接真实 LLM 跑同一套 eval，出『离线策略 vs 真实模型』对比表，因为现在的数字都来自确定性策略，这是最大短板。第二是 P1 加 query decomposition + cross-encoder rerank 冲 recall@5 ≥ 0.9；顺带把 groundedness 换成 LLM-as-judge 并做人工校准。第三是补 P4 的 Streamable HTTP + OAuth，以及 P3 的并发 checkpoint 存储与 OTel 导出。"

**Q：上生产还差什么？**
> "数据库账号级只读与配额、多租户隔离与并发 checkpoint、真正的向量/多语检索与 rerank、LLM-as-judge + 人工抽检、PII 的 NER 覆盖与出口二次扫描、语义型注入的 LLM judge、真实模型下的成本/延迟压测、审计日志不可篡改存储。这些都在 `docs/RISK_REGISTER.md` 的残余风险表里。"

---

## 5. 数字速记卡

| 数字 | 含义 | 出处 |
|---|---|---|
| **53/55** | 评测通过率，5/5 suite gate PASS | `evals/report.json` |
| **23/23** | 端到端冒烟断言 | `tests/smoke_test.py` |
| **30 / 420 / 205,374** | RAG 文档数 / chunk 数 / 字符数 | `data/rag_docs/manifest.json` |
| **0.60 → 0.80** | recall@5 消融前后 | `evals/reports/rag_ablation.json` |
| **0.9826** | groundedness（词覆盖代理指标） | `evals/report.json` |
| **5.0 / 4.2** | P1 / P2 平均工具调用次数 | 同上 |
| **11,955 tokens / ~$0.0034** | P1 单次 demo 估算（离线模式，非真实账单） | `runs/*.json` · demo 输出 |
| **1.00 / 1.00** | SQL 自修复率 / 护栏拦截率 | `evals/report.json` |
| **0.6057** | 渐进式披露上下文节省 | 同上（P4 `context_saved_ratio`） |
| **¥10–¥60** | P5 报价钳制区间；样例 ¥49 / ¥18 / ¥11 / ¥60 / ¥10 | `pricing.py`、`evals/report.json` |
| **USA 523.06 · Iron Maiden 138.60 · 5.65 / 412** | P2 真实 SQL 结果 | `evals/reports/sql_report.md` |

---

## 6. 现场 3 分钟 demo 脚本（共享屏幕时照着敲）

```bash
cd agent-portfolio

# 1) 30 秒：证明「能跑、有真实数字、有门禁」
python evals/run_all.py
#   指着输出说：gate = PASS, 53/55, 5 个 suite 全过；打开 evals/report.html 看逐 case 指标
#   若需要展示整体设计：python scripts/build_report_html.py 后打开 docs/TECHNICAL_REPORT.html

# 2) 40 秒：证明 agent loop + 引用可溯源
python projects/p1_research_agent/run_demo.py "MCP 授权流程和安全注意事项" --save
#   指着 [1][2][3] 引用和来源清单，说明能反查到 GitHub URL

# 3) 40 秒：证明环境反馈驱动的自修复
python projects/p2_sql_agent/run_demo.py "按国家统计总收入" --inject-error --save
#   指着 REPAIRED=True、USA 523.06 和生成的 SVG 图表

# 4) 40 秒：证明 HITL 不是口号
python projects/p3_support_swarm/run_demo.py --risk
#   指着「待人工审批」、checkpoint 路径、resume 后状态变化

# 5) 30 秒：证明协议与技能
python projects/p4_mcp_and_skills/run_demo.py --save
#   指着 initialize 返回的 capability negotiation、5 tools / 4 resources / 2 prompts、
#   以及 stats 里的 saved_ratio（按激活的技能不同，演示约 46.8%，评测最优配置 60.57%）
```

> 若面试官要求看真实模型效果：`cp .env.example .env` 填 key 后对同一条命令加 `--api`，并强调「同一套 eval 可以直接对比，指标口径不变」。

---

## 7. 不要说的话（会塌的坑）

| ❌ 不要说 | ✅ 换成 |
|---|---|
| "我的系统准确率 98%" | "groundedness 是词覆盖代理指标 0.98，只能证明有出处，不等于答案正确" |
| "模型自己学会了修 SQL" | "离线模式下是确定性策略 + 真实报错 + schema 模糊匹配；接真实模型时机制相同但决策来自模型" |
| "客服工单用的真实业务数据，效果很好" | "数据集是合成的，只验证流程/护栏/评测管线，不据此下业务结论" |
| "已经接了闲鱼和微信自动回复" | "主动放弃平台消息自动化，人工对外发送是设计约束" |
| "全部 100% 通过" | "53/55，两个困难 case 故意保留，这是我讲失败分析的入口" |
| "成本 $0.0035/次" 不加限定 | "离线模式按 token 单价的**估算值**，不是真实账单" |
| "用了 RAG / 多 Agent / MCP" 只报名词 | 每个名词后面跟一句「为什么」和一个数字 |

---

## 8. 反问面试官（体现工程判断）

1. "贵司现在线上 agent 的控制流是 workflow 主导还是 agent 主导？哪些环节允许模型自主决定步数？"
2. "人工审批的触发条件是怎么定的？checkpoint 存哪儿、谁来 resume、超时怎么处理？"
3. "eval 是离线回归门禁还是线上采样评估？有没有把 LLM-as-judge 和人工抽检做过一致性校准？"
4. "MCP 工具接入时，权限模型是做到工具级还是参数级？外部内容怎么标记成 DATA？"
5. "现在最痛的是延迟、成本、还是可观测性？如果三者只能先优化一个，团队会选哪个？"

---

## 9. 对应关系速查

| 被问到 | 打开这个文件 |
|---|---|
| 「这 5 个到底能干嘛」/ 现场讲功能 | [`FEATURES.md`](FEATURES.md) · `evals/reports/*.md` 真实产物 |
| 整体架构 / 依赖方向 / 框架替换 | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| 调研过程 / 选型 / 完整实测 / 已知限制 | [`TECHNICAL_REPORT.md`](TECHNICAL_REPORT.md) · [可展示 HTML 版](TECHNICAL_REPORT.html) |
| 数据真伪 / 许可证 / 诚实边界 | [`DATA_SOURCES.md`](DATA_SOURCES.md) · [`data/SOURCES.md`](../data/SOURCES.md) |
| 安全 / 权限 / 残余风险 / 回滚 | [`RISK_REGISTER.md`](RISK_REGISTER.md) |
| 逐 case 指标 / 阈值 / 失败明细 | [`evals/report.html`](../evals/report.html) · [`evals/report.json`](../evals/report.json) |
| 某个项目怎么讲 | 各项目 `README.md` 末尾的「面试怎么讲」 |
