# chiwen-knowledge-kit 架构与流程

## 1. 技术选型

- 主语言：Python 3.11+
- 通信协议：MCP（Model Context Protocol），通过 FastMCP SDK 注册工具
- 包管理器：hatch
- 核心依赖：mcp（MCP SDK）、pydantic（数据校验）
- 测试框架：pytest + hypothesis（属性测试）
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

用户通过 AI 聊天发出命令 → Skill 层解析命令并调用 MCP 工具 → 工具执行业务逻辑返回 JSON → Skill 层处理结果并与用户交互。

## 3. 模块职责映射

| 层级 | 核心文件/目录 | 职责说明 |
|:--|:--|:--|
| MCP Server | `src/chiwen_mcp/server.py` | 注册 7 个 MCP 工具（code-reader、init-docs、doc-code-lens、sync-docs、status-report、onboard-user、git-changelog），统一入口 |
| 数据采集 | `src/chiwen_mcp/code_reader.py` | 深度扫描代码库，提取项目信息、模块结构、入口文件、API 路由、依赖关系，支持 Python/JS/TS/Go/Rust |
| 数据采集 | `src/chiwen_mcp/doc_code_lens.py` | 文档与代码双向 drift 检测：Forward（文档声称有但代码没有）+ Reverse（代码有但文档没记录），使用多因子加权评分算法 |
| 数据采集 | `src/chiwen_mcp/git_changelog.py` | 从 Git 历史提取贡献者统计、模块活跃度、近期提交、过期文件列表 |
| 业务逻辑 | `src/chiwen_mcp/doc_generator.py` | init 命令：调用 code_reader 扫描后生成骨架文件（INDEX/ROADMAP/DECISIONS/CHANGELOG），核心文档由 LLM 撰写 |
| 业务逻辑 | `src/chiwen_mcp/sync.py` | sync 命令：调用 doc_code_lens（full 模式），修复 forward drift（降级虚假勾选）+ 追加 reverse drift（补充未记录能力） |
| 业务逻辑 | `src/chiwen_mcp/status.py` | status 命令：生成健康度报告（同步率、drift 清单、贡献者、过期文档），可导出 Markdown |
| 业务逻辑 | `src/chiwen_mcp/onboard.py` | onboard 命令：创建个人空间（notepad.md + cache.md），输出项目阅读清单 |
| 业务逻辑 | `src/chiwen_mcp/template_engine.py` | 自定义文档模板引擎，基于 string.Template，支持 .docs/templates/ 覆盖默认模板 |
| 业务逻辑 | `src/chiwen_mcp/integrations.py` | 生成 GitHub Actions、GitLab CI、pre-commit hook、cron 定时任务配置模板 |
| 基础设施 | `src/chiwen_mcp/models.py` | 所有模块共用的 30+ 个 dataclass 定义（CodeReaderOutput、ForwardDrift、HealthReport 等） |
| 基础设施 | `src/chiwen_mcp/changelog_utils.py` | 解析和追加 5_CHANGELOG.md，保留手动编辑内容 |
| 基础设施 | `src/chiwen_mcp/collaboration.py` | 文件锁（防止多人同时写 .docs/）、状态文件（记录 Git HEAD）、dirty/risky 检查 |
| Skill 编排 | `src/skill/SKILL.md` | AI Steering 指令文件，定义 init/sync/onboard/status 四个命令的完整流程和 LLM 撰写指引 |

## 4. 核心执行流程

入口文件：`src/chiwen_mcp/server.py`（通过 `chiwen-knowledge-kit` 命令启动 MCP Server）

**init 流程（三阶段）**：
1. code-reader 扫描项目 → 返回 CodeReaderOutput
2. init-docs 生成骨架文件（INDEX/ROADMAP/DECISIONS/CHANGELOG）
3. LLM 基于 CodeReaderOutput 撰写 ARCHITECTURE 和 CAPABILITIES

**sync 流程**：
1. doc-code-lens（full 模式）检测双向 drift
2. Forward drift：虚假勾选 [x] 降级为 [ ]
3. Reverse drift：未记录的代码能力追加到能力矩阵
4. 追加 5_CHANGELOG.md

**status 流程**：
1. doc-code-lens 检测 drift → 计算同步率
2. git-changelog 获取贡献者和过期文档
3. 汇总生成健康度报告

## 5. ADR 快速索引

暂无 ADR 记录，请在 `4_DECISIONS.md` 中添加。
