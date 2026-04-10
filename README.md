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

在项目根目录创建 `.trae/mcp.json`：

```json
{
  "mcpServers": {
    "chiwen-knowledge-kit": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/lotusTanglei/chiwen", "chiwen-knowledge-kit"],
      "disabled": false
    }
  }
}
```

#### 2. 安装 Rules（等同于 Skill）

Trae 使用 Rules 文件来指导 AI 行为。将 Skill 文件下载为 Trae 的 Rules：

```bash
mkdir -p .trae/rules
curl -o .trae/rules/project-knowledge.md \
  https://raw.githubusercontent.com/lotusTanglei/chiwen/main/src/skill/project-knowledge.md
```

#### 3. 使用

在 Trae 的 AI 聊天中直接说 `init`、`sync`、`status` 或 `onboard`，AI 会自动读取 Rules 并调用 MCP 工具。

---

### Claude Code（Anthropic CLI）

#### 1. 配置 MCP 工具

运行以下命令注册 MCP server：

```bash
claude mcp add chiwen-knowledge-kit \
  --command uvx \
  --args "--from" "git+https://github.com/lotusTanglei/chiwen" "chiwen-knowledge-kit"
```

或者在项目根目录创建 `.mcp.json`：

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

#### 2. 安装 Rules（等同于 Skill）

Claude Code 使用 `CLAUDE.md` 或 `.claude/rules/` 来指导 AI 行为：

```bash
mkdir -p .claude/rules
curl -o .claude/rules/project-knowledge.md \
  https://raw.githubusercontent.com/lotusTanglei/chiwen/main/src/skill/project-knowledge.md
```

#### 3. 使用

在 Claude Code 中直接说 `init`、`sync`、`status` 或 `onboard`，AI 会自动读取 Rules 并调用 MCP 工具。

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
