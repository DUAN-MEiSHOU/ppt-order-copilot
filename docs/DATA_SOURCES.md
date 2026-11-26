# 数据来源、许可证与诚实边界

所有外部数据由 `scripts/fetch_data.py` 通过 **GitHub REST API**（`/git/trees?recursive=1` + `/git/blobs/{sha}`，base64 解码）抓取，已随仓库落地，断网也能运行。每篇 RAG 文档头部保留了原始 URL。

## 1. RAG 文档语料（`data/rag_docs/`，30 篇 / 420 chunks / 205,374 字符）

| 来源仓库 | 内容 | 许可/说明 |
|---|---|---|
| `modelcontextprotocol/modelcontextprotocol` | 2026-07-28 规范的架构、授权、安全、传输、模式、changelog 等 16 篇 | 官方规范仓库，文档公开；引用时保留 URL |
| `bernierllc/claude-skills` | `agent_skills_spec.md`、`mcp-builder/SKILL.md` | 仓库含 Apache-2.0 LICENSE |
| `qfc-network/ai-infra` | Anthropic《Building Effective Agents》中英整理 | 对公开工程博客的整理与转述；原始出处 `anthropic.com/engineering/building-effective-agents` |
| `huggingface/agents-course` | Unit 1 的 8 篇 mdx 章节 | 仓库含 LICENSE（Apache-2.0） |
| `langchain-ai/deepagents` | `examples/text-to-sql-agent` 的 README 与 AGENTS.md | 官方示例文档 |

> 说明：本项目只把上述文档作为**本地检索语料**用于技术演示，不重新分发、不声称原创；`data/rag_docs/manifest.json` 逐文件记录来源 URL。商用前请按各自许可证另行确认。

## 2. Chinook SQLite（`data/chinook.db`，1,007,616 B）

- 来源：`lerocha/chinook-database` → `ChinookDatabase/DataSources/Chinook_Sqlite.sqlite`
- 内容：11 张表 / 347 专辑 / 275 艺人 / 59 客户 / 412 发票 / 2240 发票行 / 3503 曲目 / 25 流派 / 8 员工
- 用途：P2、P4 的 Text-to-SQL；只读打开，绝不写入
- 说明：开源示例数据库，数据为构造的音乐商店样例，不是真实交易数据

## 3. 客服工单（`data/tickets_sample.csv`，400 条）

- 来源：公开 `customer_support_tickets.csv`（8,469 条）的 GitHub 镜像，经 `scripts/fetch_data.py` 分层抽样 400 条，保证 5 个类别各 80 条
- 字段：Ticket ID / Type / Subject / Description / Status / Resolution / Priority / Channel / Satisfaction 等 17 列
- 知识库：126 条 `Closed` 且带 Resolution 的历史工单 + 5 份项目内 SOP = 131 个可检索文档

> **诚实边界（重要）**：该数据集是**合成数据**（Faker 风格）。实测 `Ticket Type` 与 `Ticket Subject`/`Description` 基本不相关，`Resolution` 多为无意义占位文本。因此它**只适合验证流程、状态机、护栏与评测管线，不适合得出任何业务语义结论**。面试时主动说明这一点，比含糊带过更加分。生产替换：真实工单库 + 领域 SOP + 脱敏流水线。

## 4. PPT 接单聊天（`data/ppt_chats_sample.json`，10 段）

- 来源：**项目内为演示编写的合成对话**，文件内 `_note` 字段已明确标注
- 不含任何真实客户信息；其中出现的邮箱/手机/微信号均为示例占位
- 价格规则（三类任务、10–60 元区间、按页数与设计类型定价）来自用户口述的真实业务，不是从数据推断

## 5. 项目内编写的内容（非开源数据，明确标注）

- `projects/p3_support_swarm/knowledge.py` 中的 5 份 SOP
- 3 个 SKILL.md、`references/`、`docs/`、各 README
- 所有 eval_set.json 的 golden 标注

## 6. 网络与可复现性

| 通道 | 实测 | 处理 |
|---|---|---|
| `api.github.com` | 200 | 主通道 |
| `raw.githubusercontent.com` | 超时 | 不用 |
| `huggingface.co` | 隧道 502 | 不用；改用 GitHub 上的语料与镜像 |
| PyPI | 200 | 核心不依赖 |

```bash
python scripts/fetch_data.py              # 幂等增量下载
python scripts/fetch_data.py --force      # 强制重下
python scripts/fetch_data.py --full-tickets  # 保留完整 8469 条工单
```

脚本未认证限流 60 req/h，已下载文件会自动跳过，被限流后重跑即可续传。

## 7. 引用建议

简历/面试中建议这样表述数据来源：

> "RAG 语料来自 MCP 2026-07-28 官方规范、Agent Skills 规范、Hugging Face Agents Course 等 30 篇公开文档，用 GitHub API 抓取并保留原始 URL；Text-to-SQL 用开源 Chinook 库；客服流程用公开工单数据集的分层抽样（我注明它是合成数据，只用于流程验证）。"
