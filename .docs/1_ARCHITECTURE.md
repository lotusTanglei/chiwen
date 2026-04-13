# chiwen-knowledge-kit 架构与流程

## 1. 技术选型

- 主语言：Python
- 主框架：无（纯 Python + MCP SDK）
- 数据库：无
- 包管理器：hatch
- Monorepo 结构：否

## 2. 分层架构

- **MCP 工具层**（`src/chiwen_mcp/`）：数据采集和分析计算
  - `code_reader.py` — 代码扫描引擎
  - `doc_code_lens.py` — 文档与代码 drift 检测
  - `git_changelog.py` — Git 历史分析
  - `models.py` — 共享数据模型
  - `server.py` — MCP Server 注册入口
- **Skill 编排层**（`src/skill/`）：流程编排和用户交互
  - `project-knowledge.md` → `SKILL.md` — AI Steering 指令文件
- **业务逻辑层**（`src/chiwen_mcp/`）：命令实现
  - `doc_generator.py` — init 命令文档生成
  - `sync.py` — sync 命令同步逻辑
  - `status.py` — status 命令健康度报告
  - `onboard.py` — onboard 命令入职引导
  - `changelog_utils.py` — Changelog 追加工具
  - `integrations.py` — CI/Hook/Cron 集成模板
- **测试层**（`tests/`）：单元测试和集成测试

## 3. 模块职责映射

| 层级 | 核心文件/目录 | 职责说明 |
|:--|:--|:--|
| MCP 工具 | `src/chiwen_mcp/code_reader.py` | 深度扫描代码库，提取结构化项目知识 |
| MCP 工具 | `src/chiwen_mcp/doc_code_lens.py` | 文档与代码双向 drift 检测（forward + reverse） |
| MCP 工具 | `src/chiwen_mcp/git_changelog.py` | 从 Git 历史提取贡献者、模块活跃度、过期文件 |
| MCP 注册 | `src/chiwen_mcp/server.py` | FastMCP 注册 3 个工具，提供 MCP 协议入口 |
| 数据模型 | `src/chiwen_mcp/models.py` | 所有 MCP 工具共享的 dataclass 定义 |
| 命令实现 | `src/chiwen_mcp/doc_generator.py` | init 命令：基于扫描结果生成 6 个文档 |
| 命令实现 | `src/chiwen_mcp/sync.py` | sync 命令：drift 修复 + 能力矩阵同步 |
| 命令实现 | `src/chiwen_mcp/status.py` | status 命令：健康度报告生成 |
| 命令实现 | `src/chiwen_mcp/onboard.py` | onboard 命令：个人空间创建 + 阅读清单 |
| 工具 | `src/chiwen_mcp/changelog_utils.py` | 5_CHANGELOG.md 解析和追加 |
| 工具 | `src/chiwen_mcp/integrations.py` | CI/pre-commit/cron 配置模板生成 |
| Skill | `src/skill/SKILL.md` | AI Steering 指令文件 |
| 测试 | `tests/` | 253 个单元测试和集成测试 |

## 4. 核心执行流程

入口文件：`src/chiwen_mcp/server.py`（MCP Server 启动入口）

用户通过 AI 聊天发出命令 → Skill 编排层解析命令 → 调用对应 MCP 工具 → 工具返回 JSON 结果 → Skill 层处理结果并生成/更新文档 → 向用户展示摘要

## 5. ADR 快速索引

> 完整记录见 `4_DECISIONS.md`

| ADR编号 | 决策摘要 | 日期 |
|:--|:--|:--|
| — | 暂无决策记录 | — |
