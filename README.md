# chiwen Knowledge Kit

AI 驱动的项目知识文档工具。小团队多人维护一套 `.docs/`，通过 MCP 工具链实现文档的自动生成、drift 检测与修复。

## 核心能力

| 命令 | 说明 |
|:--|:--|
| `init` | 扫描代码 → 生成骨架文件 → LLM 撰写架构文档和能力矩阵 |
| `sync` | 检测文档与代码的双向 drift，自动修复并追加 changelog |
| `status` | 生成文档健康度报告（同步率、贡献者、过期文档） |
| `onboard` | 创建个人空间和项目阅读清单 |

## 快速开始

chiwen Knowledge Kit = MCP 工具 + Skill 文件。MCP 工具提供代码扫描和文档分析能力，Skill 文件指导 AI 如何使用这些工具。

### 前置条件

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)（Python 包管理器，提供 `uvx` 命令）。

### Kiro

**1. 配置 MCP**

在 `.kiro/settings/mcp.json` 或 `~/.kiro/settings/mcp.json` 中添加：

```json
{
  "mcpServers": {
    "chiwen-knowledge-kit": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/lotusTanglei/chiwen", "chiwen-knowledge-kit"],
      "disabled": false,
      "autoApprove": ["code-reader", "init-docs", "doc-code-lens", "sync-docs", "status-report", "onboard-user", "git-changelog"]
    }
  }
}
```

**2. 安装 Skill**

```bash
mkdir -p .kiro/steering
curl -o .kiro/steering/project-knowledge.md \
  https://raw.githubusercontent.com/lotusTanglei/chiwen/main/src/skill/SKILL.md
```

**3. 使用**

聊天中输入 `#project-knowledge` 激活，然后说 `init`。

---

### Trae

**1. 配置 MCP**

设置 → MCP → Add MCP Server → Manual Configuration：

```json
{
  "mcpServers": {
    "chiwen-knowledge-kit": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/lotusTanglei/chiwen", "chiwen-knowledge-kit"]
    }
  }
}
```

**2. 安装 Skill**

下载 [SKILL.md](https://raw.githubusercontent.com/lotusTanglei/chiwen/main/src/skill/SKILL.md)，在设置 → Skill 中上传。

或作为 Project Rules：

```bash
mkdir -p .trae/rules
curl -o .trae/rules/project_rules.md \
  https://raw.githubusercontent.com/lotusTanglei/chiwen/main/src/skill/SKILL.md
```

**3. 使用**

聊天中直接说 `init`。

---

### Claude Code

**1. 配置 MCP**

```bash
claude mcp add chiwen-knowledge-kit \
  -- uvx --from "git+https://github.com/lotusTanglei/chiwen" chiwen-knowledge-kit
```

**2. 安装 Skill**

```bash
curl -o CLAUDE.md \
  https://raw.githubusercontent.com/lotusTanglei/chiwen/main/src/skill/SKILL.md
```

`CLAUDE.md` 每次会话自动加载。

**3. 使用**

直接说 `init`。

## 更新 MCP 工具

```bash
# 清除 uvx 缓存，拉取最新版本
uvx --from "git+https://github.com/lotusTanglei/chiwen@latest" chiwen-knowledge-kit

# 然后重启 AI IDE 会话
```

## 文档体系

```
.docs/
├── 0_INDEX.md           # 索引
├── 1_ARCHITECTURE.md    # 架构（LLM 撰写）
├── 2_CAPABILITIES.md    # 能力矩阵（LLM 撰写）
├── 3_ROADMAP.md         # 路线图
├── 4_DECISIONS.md       # 架构决策记录（ADR）
├── 5_CHANGELOG.md       # 变更日志（AI 自动维护）
└── users/@{username}/   # 个人空间
    ├── notepad.md       # 私人笔记（不进 git）
    └── cache.md         # 工作偏好
```

## MCP 工具

| 工具 | 职责 |
|:--|:--|
| `code-reader` | 深度扫描代码库，提取结构化项目知识 |
| `init-docs` | 生成骨架文件，返回 `skipped_for_llm` 告知 LLM 需要撰写哪些文档 |
| `doc-code-lens` | 文档与代码双向 drift 检测 |
| `sync-docs` | 修复 drift + 追加 changelog |
| `status-report` | 生成健康度报告 |
| `onboard-user` | 创建个人空间 |
| `git-changelog` | 从 Git 历史提取协作知识 |

## 多人协作

- `.docs/` 进 git，团队共享
- `.docs/users/*/notepad.md` 不进 git（个人笔记）
- `2_CAPABILITIES.md` 和 `5_CHANGELOG.md` 使用 `merge=union` 策略减少合并冲突
- `sync` 命令有 Git dirty 检查和 HEAD 一致性检查，防止覆盖
- 建议：先 `git pull --rebase` 再执行 `sync`

## 开发

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
