# chiwen Knowledge Kit

AI 驱动的项目知识文档工具。将项目隐性知识自动转化为结构化文档，通过 Skill + MCP 工具链实现文档的自动生成、drift 检测与修复。

## 核心能力

- **init** — AI 扫描代码，一键生成 `.docs/` 知识文档（架构、能力矩阵、路线图、ADR、变更日志）
- **sync** — AI 自动检测文档与代码的 drift 并修复，保持文档永不过时
- **status** — 生成文档健康度报告（同步率、活跃贡献者、过期文档）
- **onboard** — 新成员入职引导，创建个人空间和阅读清单

## 安装

chiwen Knowledge Kit 由两部分组成：MCP 工具（提供代码扫描和文档分析能力）和 Skill/Rules 文件（指导 AI 如何使用这些工具）。以下是各平台的配置方法。

### Kiro

#### 1. 配置 MCP 工具

在 `.kiro/settings/mcp.json` 或 `~/.kiro/settings/mcp.json` 中添加：

```json
{
  "mcpServers": {
    "chiwen-knowledge-kit": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/lotusTanglei/chiwen", "chiwen-knowledge-kit"],
      "disabled": false,
      "autoApprove": ["code-reader", "doc-code-lens", "git-changelog"]
    }
  }
}
```

#### 2. 安装 Skill

```bash
mkdir -p .kiro/skills
curl -o .kiro/skills/project-knowledge.md \
  https://raw.githubusercontent.com/lotusTanglei/chiwen/main/src/skill/project-knowledge.md
```

#### 3. 使用

在 Kiro 聊天中输入 `#project-knowledge` 激活 Skill，然后说 `init`、`sync`、`status` 或 `onboard`。

---

### Trae（字节跳动）

#### 1. 配置 MCP 工具

方式一（推荐）：通过 Trae 设置界面配置

1. 点击 Trae 右上角设置图标 → 选择 MCP
2. 点击 "Add MCP Server" → 选择 "Manual Configuration"
3. 粘贴以下配置：

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

方式二：项目级配置文件

需要先在 Settings → Beta 中开启 "Enable Project MCP"，然后在项目根目录创建 `.trae/mcp.json`：

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

#### 2. 安装 Project Rules

Trae 使用 `.trae/rules/project_rules.md` 来指导 AI 行为。将 Skill 文件下载为 Trae 的 Project Rules：

```bash
mkdir -p .trae/rules
curl -o .trae/rules/project_rules.md \
  https://raw.githubusercontent.com/lotusTanglei/chiwen/main/src/skill/project-knowledge.md
```

也可以在 Trae 中点击设置图标 → Rules → Project Rules 区域点击 "+ 创建 project_rules.md"，然后将 `src/skill/project-knowledge.md` 的内容粘贴进去。

#### 3. 使用

在 Trae 的 AI 聊天中直接说 `init`、`sync`、`status` 或 `onboard`，AI 会自动读取 Rules 并调用 MCP 工具。

---

### Claude Code（Anthropic CLI）

#### 1. 配置 MCP 工具

方式一（推荐）：通过 CLI 命令注册

```bash
claude mcp add chiwen-knowledge-kit \
  -- uvx --from "git+https://github.com/lotusTanglei/chiwen" chiwen-knowledge-kit
```

方式二：项目级配置文件

在项目根目录创建 `.mcp.json`：

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

#### 2. 安装 Project Instructions

Claude Code 使用项目根目录的 `CLAUDE.md` 来读取项目指令。将 Skill 内容追加到 `CLAUDE.md`：

```bash
curl -s https://raw.githubusercontent.com/lotusTanglei/chiwen/main/src/skill/project-knowledge.md >> CLAUDE.md
```

或者创建子目录级别的指令文件：

```bash
mkdir -p .claude
curl -o .claude/CLAUDE.md \
  https://raw.githubusercontent.com/lotusTanglei/chiwen/main/src/skill/project-knowledge.md
```

> 注意：`CLAUDE.md` 会在每次 Claude Code 会话开始时自动加载，无需手动激活。

#### 3. 使用

在 Claude Code 中直接说 `init`、`sync`、`status` 或 `onboard`，AI 会自动读取指令并调用 MCP 工具。

## 文档体系（5+X）

```
.docs/
├── 0_INDEX.md           # 索引
├── 1_ARCHITECTURE.md    # 架构
├── 2_CAPABILITIES.md    # 能力矩阵
├── 3_ROADMAP.md         # 路线图
├── 4_DECISIONS.md       # 架构决策记录
├── 5_CHANGELOG.md       # 变更日志（AI 自动维护）
└── users/@{username}/   # 个人空间
```

## MCP 工具

| 工具 | 职责 |
|:--|:--|
| `code-reader` | 深度扫描代码库，提取结构化项目知识 |
| `doc-code-lens` | 文档与代码双向 drift 检测 |
| `git-changelog` | 从 Git 历史提取协作知识 |

## 开发

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
