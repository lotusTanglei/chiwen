# Skill 编排层

> 代码目录：`src/skill/`

## 概述

定义 AI 如何使用 MCP 工具的流程指令。SKILL.md 是跨 IDE 的统一 Steering 文件，Kiro/Trae/Claude Code 各自从这里拷贝到对应位置。

## 源文件与职责

| 文件 | 职责 | 关键内容 |
|:--|:--|:--|
| `SKILL.md` | AI Steering 指令 | init/sync/status/onboard 四个命令的完整流程定义、LLM 撰写指引 |

## 关键设计

### 四个命令

- **init**：四阶段流程（code-reader 扫描 → init-docs 骨架 → LLM 撰写全局文档 → LLM 撰写模块文档）
- **sync**：优先调用 sync-docs MCP，退化为 doc-code-lens + 手动修复
- **status**：优先调用 status-report MCP，退化为 doc-code-lens + git-changelog
- **onboard**：优先调用 onboard-user MCP，退化为手动创建

### LLM 撰写指引

SKILL.md 中定义了三套撰写规范：
- Architecture_Doc：5 个固定章节，模块职责映射用三列表格
- Capabilities_Doc：checkbox 格式，按功能域分组，自然语言描述
- Module_Doc：镜像代码目录，每个模块一个 README.md

## 依赖关系

- 依赖：chiwen_mcp 提供的所有 MCP 工具
- 被依赖：无（顶层编排）
