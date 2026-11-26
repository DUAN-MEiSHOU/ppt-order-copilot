# 数据来源清单（Provenance & Licenses）

本文件是 `scripts/fetch_data.py` 的数据出处说明，也是 P1 / P4 RAG 语料的**逐文件溯源表**。配合 [`docs/DATA_SOURCES.md`](../docs/DATA_SOURCES.md)（许可证、诚实边界、网络约束）阅读。

- 抓取方式：**GitHub REST API** —— `/repos/{repo}/git/trees/{branch}?recursive=1` 列目录，`/repos/{repo}/git/blobs/{sha}` 取 base64 内容。本机 `raw.githubusercontent.com` 超时、`huggingface.co` 隧道 502，因此不走直链。
- 落地位置：`data/rag_docs/`，**30 篇 / 420 chunks / 205,374 字符**；每篇文件头部两行注释保留原始 URL 与仓库信息，`manifest.json` 记录机器可读映射。
- 幂等：已存在文件默认跳过，`--force` 强制重下；未认证 GitHub API 限流 60 req/h，被限流后重跑即可续传。
- 用途声明：仅作为**本地检索语料**用于技术演示与评测，不重新分发、不声称原创。

## 1. 来源仓库汇总

| # | 仓库 | 文件数 | 内容 | 许可证 / 说明 |
|---|---|---:|---|---|
| 1 | [`modelcontextprotocol/modelcontextprotocol`](https://github.com/modelcontextprotocol/modelcontextprotocol) | 16 | 2026-07-28 规范：架构、授权、安全、传输、模式、版本、changelog | 官方规范仓库，文档公开；引用保留 URL |
| 2 | [`huggingface/agents-course`](https://github.com/huggingface/agents-course) | 8 | Unit 1 的 mdx 章节（actions / messages / agent steps / quiz 等） | 仓库含 Apache-2.0 LICENSE |
| 3 | [`qfc-network/ai-infra`](https://github.com/qfc-network/ai-infra) | 2 | Anthropic《Building Effective Agents》中英整理 | 对公开工程博客的整理与转述；原始出处 `anthropic.com/engineering/building-effective-agents` |
| 4 | [`bernierllc/claude-skills`](https://github.com/bernierllc/claude-skills) | 2 | `agent_skills_spec.md`、`mcp-builder/SKILL.md` | 仓库含 Apache-2.0 LICENSE |
| 5 | [`langchain-ai/deepagents`](https://github.com/langchain-ai/deepagents) | 2 | `examples/text-to-sql-agent` 的 README 与 AGENTS.md | 官方示例文档，P2 选题与 Chinook 用法的参考 |

RAG 语料之外还有两类外部数据：

| 数据 | 文件 | 来源 | 说明 |
|---|---|---|---|
| Chinook SQLite | `data/chinook.db`（1,007,616 B） | [`lerocha/chinook-database`](https://github.com/lerocha/chinook-database) → `ChinookDatabase/DataSources/Chinook_Sqlite.sqlite` | 11 表 / 412 发票 / 3,503 曲目；开源示例库，只读打开，数据为构造样例而非真实交易 |
| 客服工单 | `data/tickets_sample.csv`（400 条） | 公开 `customer_support_tickets.csv`（8,469 条）的 GitHub 镜像，分层抽样，5 类各 80 条 | **合成数据**，只用于流程/护栏/评测验证，见 §3 |

## 2. 逐文件溯源表（30 篇）

文件名带仓库前缀以避免冲突；`source` 列为抓取时的原始 blob URL。

### 2.1 MCP 官方规范（16 篇）

| 本地文件 | 原始路径（相对 `modelcontextprotocol/modelcontextprotocol/blob/main/`） |
|---|---|
| `mcp__docs-specification-2026-07-28-architecture-index.mdx` | `docs/specification/2026-07-28/architecture/index.mdx` |
| `mcp__docs-specification-2026-07-28-basic-authorization-authorization-server-discovery.mdx` | `docs/specification/2026-07-28/basic/authorization/authorization-server-discovery.mdx` |
| `mcp__docs-specification-2026-07-28-basic-authorization-client-registration.mdx` | `docs/specification/2026-07-28/basic/authorization/client-registration.mdx` |
| `mcp__docs-specification-2026-07-28-basic-authorization-index.mdx` | `docs/specification/2026-07-28/basic/authorization/index.mdx` |
| `mcp__docs-specification-2026-07-28-basic-authorization-security-considerations.mdx` | `docs/specification/2026-07-28/basic/authorization/security-considerations.mdx` |
| `mcp__docs-specification-2026-07-28-basic-index.mdx` | `docs/specification/2026-07-28/basic/index.mdx` |
| `mcp__docs-specification-2026-07-28-basic-patterns-cancellation.mdx` | `docs/specification/2026-07-28/basic/patterns/cancellation.mdx` |
| `mcp__docs-specification-2026-07-28-basic-patterns-index.mdx` | `docs/specification/2026-07-28/basic/patterns/index.mdx` |
| `mcp__docs-specification-2026-07-28-basic-patterns-mrtr.mdx` | `docs/specification/2026-07-28/basic/patterns/mrtr.mdx` |
| `mcp__docs-specification-2026-07-28-basic-patterns-progress.mdx` | `docs/specification/2026-07-28/basic/patterns/progress.mdx` |
| `mcp__docs-specification-2026-07-28-basic-patterns-subscriptions.mdx` | `docs/specification/2026-07-28/basic/patterns/subscriptions.mdx` |
| `mcp__docs-specification-2026-07-28-basic-transports-index.mdx` | `docs/specification/2026-07-28/basic/transports/index.mdx` |
| `mcp__docs-specification-2026-07-28-basic-transports-stdio.mdx` | `docs/specification/2026-07-28/basic/transports/stdio.mdx` |
| `mcp__docs-specification-2026-07-28-basic-transports-streamable-http.mdx` | `docs/specification/2026-07-28/basic/transports/streamable-http.mdx` |
| `mcp__docs-specification-2026-07-28-basic-versioning.mdx` | `docs/specification/2026-07-28/basic/versioning.mdx` |
| `mcp__docs-specification-2026-07-28-changelog.mdx` | `docs/specification/2026-07-28/changelog.mdx` |

### 2.2 Hugging Face Agents Course Unit 1（8 篇）

| 本地文件 | 原始路径（相对 `huggingface/agents-course/blob/main/units/en/unit1/`） |
|---|---|
| `hf-course__units-en-unit1-README.md` | `README.md` |
| `hf-course__units-en-unit1-actions.mdx` | `actions.mdx` |
| `hf-course__units-en-unit1-agent-steps-and-structure.mdx` | `agent-steps-and-structure.mdx` |
| `hf-course__units-en-unit1-conclusion.mdx` | `conclusion.mdx` |
| `hf-course__units-en-unit1-dummy-agent-library.mdx` | `dummy-agent-library.mdx` |
| `hf-course__units-en-unit1-final-quiz.mdx` | `final-quiz.mdx` |
| `hf-course__units-en-unit1-introduction.mdx` | `introduction.mdx` |
| `hf-course__units-en-unit1-messages-and-special-tokens.mdx` | `messages-and-special-tokens.mdx` |

### 2.3 其余（6 篇）

| 本地文件 | 原始 URL |
|---|---|
| `anthropic__anthropic-building-effective-agents-en.md` | `github.com/qfc-network/ai-infra/blob/main/anthropic/building-effective-agents/en.md` |
| `anthropic__anthropic-building-effective-agents-zh.md` | `github.com/qfc-network/ai-infra/blob/main/anthropic/building-effective-agents/zh.md` |
| `skills__agent_skills_spec.md` | `github.com/bernierllc/claude-skills/blob/main/agent_skills_spec.md` |
| `skills__mcp-builder-SKILL.md` | `github.com/bernierllc/claude-skills/blob/main/mcp-builder/SKILL.md` |
| `deepagents__examples-text-to-sql-agent-README.md` | `github.com/langchain-ai/deepagents/blob/main/examples/text-to-sql-agent/README.md` |
| `deepagents__examples-text-to-sql-agent-AGENTS.md` | `github.com/langchain-ai/deepagents/blob/main/examples/text-to-sql-agent/AGENTS.md` |

完整的 `file → source` 映射以 [`rag_docs/manifest.json`](rag_docs/manifest.json) 为准；P1 简报里的 `[n]` 引用可经 `Chunk.source_url` 反查到本表。

## 3. 非开源 / 项目内编写的数据（明确标注，避免误认）

| 数据 | 文件 | 性质 |
|---|---|---|
| 客服工单 | `data/tickets_sample.csv` | 上游公开数据集本身为**合成数据**（Faker 风格）。实测 `Ticket Type` 与 `Ticket Subject`/`Description` 基本不相关，`Resolution` 多为占位文本。因此只验证流程、状态机、护栏、评测管线，**不用于任何业务语义结论**。生产替换：真实工单库 + 领域 SOP + 脱敏流水线 |
| PPT 接单聊天 | `data/ppt_chats_sample.json`（10 段） | **项目内编写的合成对话**，文件内 `_note` 已标注；不含真实客户信息，出现的邮箱/手机/微信号均为示例占位。定价规则来自业务口述，不是从数据推断 |
| SOP | `projects/p3_support_swarm/knowledge.py`（5 份） | 项目内编写的策略文本，**非开源数据** |
| 技能包与文档 | `projects/p4_mcp_and_skills/skills/`、`docs/`、各 `README.md` | 项目内编写 |
| 评测标注 | 各 `eval_set.json` 的 golden | 人工标注，用于门禁，不是外部数据 |

> 面试时主动说明「哪部分是真实开源数据、哪部分是合成数据、合成数据能证明什么、不能证明什么」，比含糊带过更加分。

## 4. 可复现命令

```bash
python scripts/fetch_data.py                 # 幂等增量下载（已存在则跳过）
python scripts/fetch_data.py --force        # 强制重下全部
python scripts/fetch_data.py --full-tickets # 保留完整 8,469 条工单（默认抽样后删除）
python scripts/rag_ablation.py              # 检索改写的 A/B 消融，产物 evals/reports/rag_ablation.json
```

> 注意：`--force` 会更新语料内容，可能导致 `eval_set.json` 中的 golden 与检索指标漂移。若上游文档改版，请先跑 `python evals/run_all.py` 确认门禁，再更新 golden 并在技术报告中记录版本变化。

## 5. 引用建议

简历 / 面试中建议这样表述：

> "RAG 语料来自 MCP 2026-07-28 官方规范、Agent Skills 规范、Hugging Face Agents Course 等 30 篇公开文档，用 GitHub API 抓取并保留原始 URL；Text-to-SQL 用开源 Chinook 库；客服流程用公开工单数据集的分层抽样（我注明它是合成数据，只用于流程验证）。"
