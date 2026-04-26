# chiwen MCP 工具链

> 代码目录：`src/chiwen_mcp/`

## 概述

chiwen-knowledge-kit 的核心实现。通过 MCP 协议对外暴露 7 个工具，内部包含代码扫描、文档生成、drift 检测、同步修复、健康度报告、成员引导等完整功能。

## 源文件与职责

| 文件 | 职责 | 关键 API |
|:--|:--|:--|
| `server.py` | MCP Server 入口，注册 7 个工具 | `code_reader`、`doc_code_lens`、`sync_docs_tool` |
| `code_reader.py` | 代码扫描引擎 | `scan_project`、`CodeReaderInput` |
| `doc_code_lens.py` | drift 检测（forward + reverse） | `run_doc_code_lens`、`check_forward_drift` |
| `doc_generator.py` | init 命令骨架生成 | `init_docs`、`LLM_GENERATED_FILES` |
| `sync.py` | sync 命令修复逻辑 | `sync_docs`、`apply_reverse_fixes` |
| `status.py` | 健康度报告 | `get_status`、`export_markdown` |
| `onboard.py` | 成员引导 | `onboard`、`get_reading_list` |
| `git_changelog.py` | Git 历史分析 | `run_git_changelog` |
| `models.py` | 共享数据模型（30+ dataclass） | `CodeReaderOutput`、`ForwardDrift` |
| `collaboration.py` | 文件锁、Git 集成 | `acquire_docs_lock`、`is_git_repo` |
| `changelog_utils.py` | Changelog 追加 | `append_changelog` |
| `template_engine.py` | 自定义模板引擎 | `TemplateEngine` |
| `integrations.py` | CI/Hook/Cron 模板 | `generate_ci_config` |

## 关键设计

### init 四阶段流程

code_reader 扫描 → init_docs 骨架（跳过 LLM_GENERATED_FILES）→ LLM 撰写全局文档 → LLM 撰写模块文档。`skipped_for_llm` 字段协调 MCP 工具和 LLM 的分工。

### drift 检测

多因子加权评分：精确名称匹配 40% + 关键词覆盖率 25% + 代码结构匹配 20% + 路径相关性 15%。modules/ 存在时，sync 不向全局能力矩阵追加裸函数名。

### 多人协作

文件锁 + Git dirty 检查 + HEAD 一致性检查 + merge=union 策略。

## 依赖关系

- 外部：mcp、pydantic
- 被依赖：src/skill/SKILL.md（Skill 编排层）
