# chiwen MCP 工具链

> 代码目录：`src/chiwen_mcp/`

## 概述

chiwen-knowledge-kit 的核心实现。通过 MCP 协议对外暴露 7 个工具，内部包含代码扫描、文档生成、drift 检测、同步修复、健康度报告、成员引导等完整功能。

## 源文件与职责

| 文件 | 职责 | 关键 API |
|:--|:--|:--|
| `server.py` | MCP Server 入口，注册 7 个工具 | `code_reader`、`init_docs_tool`、`doc_code_lens` |
| `code_reader.py` | 代码扫描引擎，提取项目结构化知识 | `scan_project`、`CodeReaderInput` |
| `doc_code_lens.py` | 文档与代码双向 drift 检测 | `run_doc_code_lens`、`check_forward_drift`、`check_reverse_drift` |
| `doc_generator.py` | init 命令，生成骨架文件 | `init_docs`、`generate_architecture` |
| `sync.py` | sync 命令，修复 drift 并追加 changelog | `sync_docs`、`apply_reverse_fixes` |
| `status.py` | status 命令，生成健康度报告 | `get_status`、`export_markdown` |
| `onboard.py` | onboard 命令，创建个人空间 | `onboard`、`get_reading_list` |
| `git_changelog.py` | Git 历史分析 | `run_git_changelog` |
| `models.py` | 共享数据模型（30+ dataclass） | `CodeReaderOutput`、`ForwardDrift`、`HealthReport` |
| `collaboration.py` | 文件锁、状态文件、Git 集成 | `acquire_docs_lock`、`is_git_repo` |
| `changelog_utils.py` | 5_CHANGELOG.md 解析和追加 | `append_changelog`、`parse_changelog` |
| `template_engine.py` | 自定义文档模板引擎 | `TemplateEngine`、`init_templates` |
| `integrations.py` | CI/Hook/Cron 配置模板生成 | `generate_ci_config`、`generate_pre_commit_hook` |

## 关键设计

### init 三阶段流程

1. `code_reader` 扫描项目 → 返回 `CodeReaderOutput`
2. `init_docs` 生成骨架文件（INDEX/ROADMAP/DECISIONS/CHANGELOG）
3. LLM 基于扫描结果撰写 ARCHITECTURE、CAPABILITIES 和模块文档

`init_docs` 通过 `LLM_GENERATED_FILES` 常量控制跳过哪些文件，`skipped_for_llm` 字段告知 LLM 需要撰写什么。

### drift 检测算法

`doc_code_lens` 使用多因子加权评分：
- 精确名称匹配（40%）+ 关键词覆盖率（25%）+ 代码结构匹配（20%）+ 路径相关性（15%）
- 得分 ≥ 0.7 → HIGH，≥ 0.4 → MEDIUM，< 0.4 → LOW

Forward drift：文档声称 [x] 但代码没有 → 降级为 [ ]
Reverse drift：代码有但文档没记录 → 追加到模块文档或能力矩阵

### 多人协作安全

- `collaboration.py` 提供文件锁（`acquire_docs_lock`），防止多人同时写 `.docs/`
- sync 前检查 Git dirty 和 HEAD 一致性，防止覆盖
- `.gitattributes` 对 CAPABILITIES 和 CHANGELOG 使用 `merge=union` 减少冲突

## 依赖关系

- 外部依赖：mcp（MCP SDK）、pydantic
- 被依赖：`src/skill/SKILL.md`（Skill 编排层调用 MCP 工具）
