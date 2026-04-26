# chiwen-knowledge-kit 架构与流程

## 1. 技术选型

- 主语言：Python 3.11+
- 通信协议：MCP（Model Context Protocol），通过 FastMCP SDK 注册工具
- 包管理器：hatch
- 核心依赖：mcp（MCP SDK）、pydantic（数据校验）
- 测试：pytest + hypothesis（属性测试）
- 无数据库、无 Web 框架 — 纯工具链项目

## 2. 分层架构

```
┌─────────────────────────────────────────────────┐
│  Skill 编排层（SKILL.md）                        │
│  AI 读取指令 → 编排 init/sync/status/onboard 流程 │
├─────────────────────────────────────────────────┤
│  MCP Server（server.py）                         │
│  注册 7 个 MCP 工具，通过标准协议对外暴露能力       │
├─────────────────────────────────────────────────┤
│  业务逻辑层                                      │
│  doc_generator · sync · status · onboard         │
│  template_engine · integrations                  │
├─────────────────────────────────────────────────┤
│  数据采集层（MCP 工具核心）                        │
│  code_reader · doc_code_lens · git_changelog     │
├─────────────────────────────────────────────────┤
│  基础设施层                                      │
│  models · changelog_utils · collaboration        │
└─────────────────────────────────────────────────┘
```

## 3. 模块职责映射

| 层级 | 核心文件/目录 | 职责说明 |
|:--|:--|:--|
| MCP Server | `src/chiwen_mcp/server.py` | 注册 7 个 MCP 工具，统一入口 |
| 数据采集 | `src/chiwen_mcp/code_reader.py` | 深度扫描代码库，提取项目结构化知识 |
| 数据采集 | `src/chiwen_mcp/doc_code_lens.py` | 文档与代码双向 drift 检测 |
| 数据采集 | `src/chiwen_mcp/git_changelog.py` | Git 历史分析 |
| 业务逻辑 | `src/chiwen_mcp/doc_generator.py` | init 命令：生成骨架文件 |
| 业务逻辑 | `src/chiwen_mcp/sync.py` | sync 命令：修复 drift |
| 业务逻辑 | `src/chiwen_mcp/status.py` | status 命令：健康度报告 |
| 业务逻辑 | `src/chiwen_mcp/onboard.py` | onboard 命令：成员引导 |
| 业务逻辑 | `src/chiwen_mcp/template_engine.py` | 自定义文档模板引擎 |
| 业务逻辑 | `src/chiwen_mcp/integrations.py` | CI/Hook/Cron 配置模板 |
| 基础设施 | `src/chiwen_mcp/models.py` | 共享数据模型 |
| 基础设施 | `src/chiwen_mcp/changelog_utils.py` | Changelog 解析和追加 |
| 基础设施 | `src/chiwen_mcp/collaboration.py` | 文件锁、状态文件、Git 集成 |
| Skill | `src/skill/SKILL.md` | AI Steering 指令文件 |

## 4. 核心执行流程

入口：`src/chiwen_mcp/server.py`（`chiwen-knowledge-kit` 命令启动 MCP Server）

**init**：code-reader 扫描 → init-docs 骨架 → LLM 撰写全局文档 → LLM 撰写模块文档
**sync**：doc-code-lens 检测 drift → 修复能力矩阵 → 追加 changelog
**status**：doc-code-lens + git-changelog → 健康度报告

## 5. ADR 快速索引

暂无 ADR 记录，请在 `4_DECISIONS.md` 中添加。
