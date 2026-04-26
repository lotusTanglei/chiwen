# Skill 编排层

> 代码目录：`src/skill/`

## 概述

定义 AI 如何使用 MCP 工具的流程指令。SKILL.md 是跨 IDE 的统一 Steering 文件。

## 源文件与职责

| 文件 | 职责 | 关键内容 |
|:--|:--|:--|
| `SKILL.md` | AI Steering 指令 | init/sync/status/onboard 流程定义、LLM 撰写指引 |

## 关键设计

四个命令（init/sync/status/onboard）+ 三套 LLM 撰写规范（Architecture、Capabilities、Module）+ 自定义模板参考机制。

## 依赖关系

- 依赖：chiwen_mcp 的所有 MCP 工具
- 被依赖：无（顶层编排）
