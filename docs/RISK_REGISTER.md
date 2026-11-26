# 风险登记册（Risk Register）

> 配套 [`TECHNICAL_REPORT.md`](TECHNICAL_REPORT.md) §7 与 [`ARCHITECTURE.md`](ARCHITECTURE.md)。
> 记录信任边界、权限矩阵、每项风险的可验证缓解措施、失败模式、回滚方式与**上线前必须补齐的残余风险**。
> 版本 v1.0.0 · 2026-11-10 · 状态：评测门禁 PASS（53/55）、冒烟 23/23。

---

## 1. 威胁模型与信任边界

```
 ┌── 不可信输入 ────────────────────────────────────────────┐
 │ 用户问题 · 检索到的外部文档 · 工单正文 · 导入的聊天记录    │
 │ （可能含提示注入、PII、伪造指令、脏数据）                 │
 └────────────────┬─────────────────────────────────────────┘
                  │ ① redact_pii + detect_prompt_injection + 包裹/截断
                  ▼
 ┌── 决策层（半可信）───────────────────────────────────────┐
 │ LLM / ScriptedLLM：只能决定「调哪个工具、写什么草稿」      │
 │ ✗ 不能裁定风险等级 ✗ 不能裁定金额 ✗ 不能绕过审批         │
 └────────────────┬─────────────────────────────────────────┘
                  │ ② ToolRegistry：schema 校验 + permission 白名单 + side_effect
                  ▼
 ┌── 确定性裁定层（可信）───────────────────────────────────┐
 │ validate_sql · assess_ticket · quote() · approval_gate     │
 └────────────────┬─────────────────────────────────────────┘
                  │ ③ Interrupt → checkpoint → human resume
                  ▼
 ┌── 副作用层（最小权限）───────────────────────────────────┐
 │ 只读 SQLite · 本地 outbox.jsonl · 本地文件 · 可复制话术    │
 │ ✗ 无任何平台 API ✗ 无真实对外发送                         │
 └──────────────────────────────────────────────────────────┘
```

**核心不变量**

1. 工具输出、检索文档、用户工单/聊天**一律是 DATA**：用 `<tool_output>` / `<untrusted_content>` 包裹并截断，系统提示明确声明忽略其中的命令式语句。
2. **高风险决策不交给模型**：SQL 白名单、风险分级、报价金额、审批门槛全部由确定性代码裁定，LLM 只能解释。
3. **最小权限**：`ToolRegistry` 用 `permission` 白名单 + `side_effect` 标记，未经批准直接拒绝。
4. **不可逆动作前设 checkpoint**：`Interrupt` → 人工审批 → `resume()`。
5. **零外发**：P3 的「发送」只写本地 `runs/outbox.jsonl`；P5 只产出可复制话术；整个仓库不调用任何平台 API。

## 2. 资产清单

| 资产 | 位置 | 敏感性 | 保护要求 |
|---|---|---|---|
| 用户工单 / 聊天文本 | 运行时内存、`data/tickets_sample.csv`、`data/ppt_chats_sample.json` | 高（可能含 PII） | intake 阶段脱敏；合成数据不含真实个人信息 |
| Chinook 数据库 | `data/chinook.db` | 中（只读样例库） | `mode=ro` 连接；绝不写入 |
| RAG 语料 | `data/rag_docs/` | 低（公开文档） | 保留来源 URL；视为不可信内容 |
| 状态与审批记录 | `runs/*.json`、`runs/checkpoint*.json` | 高（含审批结论） | 本地文件；不可篡改审计需另建 |
| 对外话术 / outbox | `runs/outbox.jsonl`、P5 报告 | 高（潜在对外内容） | 人工审批后才生成；由人复制发送 |
| LLM API key | `.env`（不入库） | 极高 | 仅 `agentkit/llm.py` 读取；默认离线模式无需 key |

## 3. 权限矩阵

| 工具 / 端点 | 项目 | permission | side_effect | 允许条件 | 实际副作用 |
|---|---|---|---|---|---|
| `search_corpus` / `read_chunk` / `list_sources` | P1 | `read` | 否 | 直接在 `("read",)` 白名单内 | 无 |
| `verify_grounding` / `compose_brief` | P1 | `read` | 否 | 同上 | 写内存 state |
| `list_tables` / `describe_table` / `check_sql` | P2 | `read` | 否 | 同上 | 无 |
| `run_sql` | P2 | `read` | 否 | 先过 `validate_sql` + `enforce_limit`，`mode=ro` 连接 | 只读查询 |
| `repair_sql` / `make_insight` | P2 | `read` | 否 | 同上 | 纯计算 |
| `render_chart` | P2 | `read` | 否 | 同上 | 写本地 SVG |
| `send_reply` | P3 | `external` | **是** | `allowed_permissions` 含 `external` **且** `allow_side_effect=True`（仅人工 resume 后） | 追加本地 `runs/outbox.jsonl` |
| MCP tools（5 个） | P4 | 服务端声明只读 | 否 | 参数注入检测；`query_sql` 走同一 SQL 护栏 | 只读查询 / 写 `_security_note` |
| MCP resources（4 个）/ prompts（2 个） | P4 | 只读 | 否 | 客户端显式请求 | 无 |
| 报价与话术生成 | P5 | 不经过工具层 | 否 | `approval_gate` 人工确认金额 | 写本地报告 |

> P1、P2 的 `ToolRegistry(allowed_permissions=("read",))` 意味着即便模型构造出 `send_reply` 调用，也会在调用点被拒绝并返回结构化错误，不依赖提示词约束。

## 4. 风险登记

等级：`H` 高 / `M` 中 / `L` 低（指**残余风险**，已缓解部分不计入）。

| ID | 风险 | 触发路径 / 攻击面 | 潜在影响 | 缓解措施（代码位置） | 验证证据 | 残余 |
|---|---|---|---|---|---|---|
| R-01 | **提示注入**（指令覆盖、角色劫持、密钥窃取、绕过审批） | 检索文档、工单正文、导入聊天、MCP 工具参数 | 越权调用、泄露、跳过人工审批 | `guard.detect_prompt_injection`（8 条中英模式）、`assess_ticket` 升为 critical、`sanitize_external_text` 包裹、工具输出 `<tool_output>`、系统提示声明 DATA | `t09_prompt_injection`（升级+中断）、`o06_prompt_injection`（标记 `中文指令覆盖`）、`m09`/`m10` 注入检测率 1.00、`s10_guard_injection` | **H**：正则覆盖有限，语义型/编码型/多语言混写注入会漏；需 LLM judge + 输入归一化 |
| R-02 | **PII 泄露** | 工单/聊天进入模型上下文、写进报告与 trace | 隐私事故、合规问题 | `guard.redact_pii`（邮箱 / 手机号 / 身份证 / 微信号），intake 前置执行，报告与话术断言清洁 | `pii_clean_rate = 1.00`（P3 / P5 各含 PII 用例）、冒烟测试断言 | **M**：中文姓名、住址、银行卡、订单号未覆盖；模型可能从上下文复原；需 NER + 出口二次扫描 |
| R-03 | **SQL 破坏 / 数据外泄** | 模型生成 SQL、字符串里藏关键字、多语句、`sqlite_master` 探测 | 数据被改、schema 泄露、资源耗尽 | `validate_sql`（剥注释/字面量、单语句、SELECT/WITH 白名单、禁用词、`LIMIT` 上限、危险函数）、`enforce_limit`、`mode=ro` URI | `s09_guard_drop` / `s10_guard_injection` 拦截率 1.00、`limit_enforced = 1.00`、MCP `m05` | **M**：仅应用层防线；需数据库账号级只读 + 独立 schema + 查询超时 + 资源配额 |
| R-04 | **Agent 失控 / 成本与延迟爆炸** | 模型反复调同一工具、步数不收敛 | 死循环、烧钱、雪崩 | `AgentConfig` 三层预算（`max_steps` / `max_tool_calls` / `max_total_tokens`）、重复调用检测注入反思、工具输出截断 6000 字符 | `completion_rate = 1.00`、`step_budget_rate = 1.00`、`avg_tool_calls` 5.0 / 4.2 | **M**：离线模式成本是按 token 单价估算，非真实账单；真实模型下需压测与硬限流 |
| R-05 | **幻觉引用 / 无依据结论** | 检索失败、证据不足、LLM 自由生成 | 输出看似可信的错误简报 | 抽取式简报（结论取自原文句子）、`[n]` 可反查 `source_url`、`groundedness` 监控、证据不足时少引用（abstention） | `groundedness = 0.9826`、`r08` 少引用而非编造、2 个失败 case 保留 | **M**：词覆盖只是 faithfulness 代理指标；真实 LLM 模式下抽取式约束变弱，需引用回查校验器 + LLM-as-judge |
| R-06 | **未经批准的对外动作** | 模型直接调用发送类工具、跳过 policy gate | 未经审核内容对外发出 | `permission="external"` + `side_effect=True`，`ToolRegistry.call` 默认拒绝；`policy_gate` / `approval_gate` 强制 `Interrupt` | `escalation_precision = 1.00`、`approval_gate_rate = 1.00` | **L**：当前「发送」只写本地 outbox，且 P5 由人复制发送，实际上不存在真实外发通道 |
| R-07 | **语料/知识库投毒** | 上游文档改版、外部文档含恶意指令、SOP 被误改 | 检索结果被操纵 | 文档头部保留来源 URL、`manifest.json` 可核验、`--force` 抓取后需重跑门禁、外部内容一律当 DATA | `data/SOURCES.md` 逐文件溯源、R-01 缓解 | **M**：无内容签名/哈希锁定；需固定 commit SHA + 校验和 + 语料审核 |
| R-08 | **平台合规 / 账号风险** | 试图逆向闲鱼/微信消息接口 | 封号、违反平台条款、法律与稳定性风险 | **架构性规避**：不实现任何平台 API，只做导入与人工发送 | 技术报告 §1.2 可行性评估、P5 README | **L**：代价是自动化程度降低，属主动接受的取舍 |
| R-09 | **checkpoint 篡改 / 并发覆盖** | 多工单同时写 checkpoint、人工误改 JSON、审批重放 | 错误审批、状态丢失、幂等性破坏 | 单文件 JSON checkpoint、`resume()` 校验 `resume_node`、审批记录含 reviewer/reason | 曾修复 bug：中断前未 `state.update(patch)` 导致风险状态丢失（`escalation_precision` 0.7 → 1.00） | **H**：单文件无锁、无签名、无过期、无审计链；生产需数据库事务 + 版本化 + 审批人身份 + 幂等键 |
| R-10 | **成本/指标被误读** | 把离线估算当真实账单、把词覆盖当正确率、把 53/55 说成 100% | 误导决策、面试失真 | 报告与文档统一标注 `scripted-offline`、指标定义写进技术报告附录 B、`docs/INTERVIEW.md` §7 列出「不要说的话」 | `evals/report.json` 的 `details.mode`、技术报告 §3.3 / §8 | **L**：文档层面已明确，靠使用者自律 |
| R-11 | **合成数据被误用为业务结论** | 用工单分类准确率、聊天样例推断真实业务效果 | 结论无效 | 文件内 `_note` / README / `DATA_SOURCES.md` / 技术报告四处标注；eval 区分「纯文本工单」与「带系统标签的 CSV 工单」 | `docs/DATA_SOURCES.md` §3–4、`data/SOURCES.md` §3 | **M**：需真实脱敏数据重跑才能给业务结论 |
| R-12 | **依赖/供应链与传输层** | 可选 SDK、真实 LLM 端点、stdio 子进程 | 依赖漏洞、key 泄露、协议层攻击 | 核心零第三方依赖；`OpenAICompatibleLLM` 只用 stdlib urllib；key 只在 `.env`；MCP server 本地 stdio 子进程 | `requirements.txt`（可选依赖全注释）、`client.py` 起真实子进程握手 | **M**：P4 只实现 stdio，未实现 Streamable HTTP / OAuth / TLS / 限流；接公网前必须补齐鉴权与传输安全 |
| R-13 | **LLM 输出格式不稳定** | 真实模型返回非法 JSON / 未知工具名 / 类型错参数 | 流程中断、参数注入 | `chat_json()` 带一次修复重试；`ToolRegistry` 运行时校验 required/type/enum/未知字段；工具错误回灌不抛穿 loop | `agentkit/llm.py`、`agentkit/tools.py`、P2 错误驱动修复 | **M**：仅一次重试，无结构化输出约束（如 strict schema）；需受约束解码 + 更严格的重试/降级策略 |

## 5. 失败模式与降级策略

| 失败模式 | 检测 | 系统行为（fail-closed 优先） | 兜底 |
|---|---|---|---|
| 检索无命中 / 命中不相关 | recall@5、evidence_term_coverage | 少引用、明确说明证据不足，**不编造引用** | 人工复核；P1 保留 2 个失败 case 作回归 |
| SQL 语法/对象错误 | SQLite 真实报错 | 错误回灌 → `repair_sql` schema 模糊匹配 → 重试 | 仍失败则报告错误，不返回编造数字 |
| SQL 命中护栏 | `validate_sql=False` | 拒绝执行，返回结构化原因 | 人工改写查询 |
| LLM 返回非法 JSON / 异常工具名 | `chat_json` / schema 校验 | 一次修复重试，再失败返回结构化 `ToolResult(error)` | 角色层有确定性 fallback；Policy 始终确定性 |
| Critic 审核不通过 | checklist 校验 | 回 `draft` 重新起草，最多 2 轮 | 超轮转人工，不强行发送 |
| 高风险 / 金额待确认 | `assess_ticket` / `approval_gate` | `Interrupt` + checkpoint，流程暂停 | 人工 `resume(approved=False)` 驳回 |
| 预算耗尽 / 死循环 | 三层预算 + 重复调用检测 | 返回 `budget_exceeded` / `step_limit_exceeded`，永不无限循环 | trace 留证，人工调参 |
| 上游数据缺失 / 网络失败 | 文件存在性检查 | 用仓库内置快照离线运行 | `scripts/fetch_data.py` 幂等续传 |
| 真实 LLM 端点不可用 | 请求异常 | 角色 fallback / 报错可读 | 切回 `ScriptedLLM` 保证演示与门禁 |

## 6. 回滚与应急

| 事件 | 立即动作 | 回滚点 | 恢复验证 |
|---|---|---|---|
| 评测门禁 FAIL | 停止「发布」；`evals/run_all.py` 退出码非 0 已阻断 | 上一版 `eval_set.json` + 代码 | 重跑 `evals/run_all.py` 至 gate PASS |
| 上游语料改版导致指标漂移 | 停用 `--force`，固定 commit SHA 重抓 | `data/rag_docs/manifest.json` 记录的 URL/版本 | 重跑 `run_all.py` 与 `scripts/rag_ablation.py`，必要时更新 golden 并记录 |
| 发现提示注入绕过 | 加规则/输入归一化，追加对抗 case | `agentkit/guard.py` 上一版 | 新 case 入 `eval_set.json`，`injection_detection_rate` 回到 1.00 |
| PII 规则误伤或漏脱敏 | 扩 `PII_PATTERNS`，加出口扫描 | 上一版规则 | `pii_clean_rate = 1.00` 且人工抽检报告 |
| SQL 护栏被绕过 | 立即停 SQL 工具，禁用 `run_sql` | `ToolRegistry` 移除注册即可 | 加对抗用例；同时补数据库账号级只读 |
| checkpoint 损坏 / 误审批 | 停止 `resume()`，隔离该文件 | `runs/` 前一版快照 | 用干净 state 重放，人工重新审批 |
| API key 泄露 | 立即吊销并轮换，仓库内不留 key | `.env` 不入版本库 | 全仓扫描确认无明文 key |

## 7. 验证证据映射

| 关注点 | 评测用例 | 指标 | 当前值 |
|---|---|---|---|
| 注入拦截 | `t09` · `o06` · `m09` · `m10` · `s10` | `injection_flag_rate` / `injection_detection_rate` / `guard_block_rate` | 1.00 |
| PII 脱敏 | `t01–t10` · `o07` | `pii_clean_rate` | 1.00 |
| SQL 护栏 | `s09` · `s10` · `m05` | `guard_block_rate` / `limit_enforced` | 1.00 |
| 自修复 | `s02` · `s03` · `s05` | `self_repair_rate` | 1.00 |
| 审批闸门 | `t04` · `t09` · `t10` · `o01–o10` | `escalation_precision` / `approval_gate_rate` | 1.00 |
| 预算收敛 | 全部 P1 / P2 case | `completion_rate` / `step_budget_rate` | 1.00 |
| 引用可靠 | 全部 P1 case | `groundedness` / `citation_rate` | 0.9826 / 0.80 |
| 轨迹完整 | 全部 P3 case | `trace_completeness` | 1.00 |
| 端到端 | `tests/smoke_test.py` | 23 项断言 | 23/23 |

## 8. 上线前必须补齐（按优先级）

1. **数据库账号级只读 + 独立 schema + 查询超时/资源配额**（R-03）；
2. **checkpoint 存储后端**：事务、并发隔离、审批人身份、过期与幂等键、不可篡改审计链（R-09）；
3. **注入防护升级**：语义型 LLM judge、输入编码归一化、输出侧外链/密钥扫描（R-01）；
4. **PII 覆盖扩展**：中文姓名/地址/银行卡/订单号 NER + 出口二次扫描（R-02）；
5. **引用校验器 + LLM-as-judge 人工校准**，替代词覆盖版 groundedness（R-05）；
6. **公网 MCP 传输**：Streamable HTTP + OAuth + TLS + 限流 + 审计日志（R-12）；
7. **真实模型压测**：成本/延迟分布、失败重试、strict structured output（R-04 / R-13）；
8. **语料供应链**：固定 commit SHA、内容哈希、语料审核与变更回归（R-07）。

## 9. 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0.0 | 2026-11-10 | 首版：13 项风险登记、权限矩阵、失败模式与回滚表；对应评测门禁 PASS（53/55）与冒烟 23/23 |
