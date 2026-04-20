"""chiwen Knowledge Kit - 文档生成器

基于 code-reader 扫描结果生成 .docs/ 目录下的所有知识文档。
由 init 命令调用，负责将 CodeReaderOutput 转化为结构化 Markdown 文档。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from .code_reader import CodeReaderInput, scan_project
from .models import ApiRoute, CodeReaderOutput, Module
from .collaboration import acquire_docs_lock, git_head, is_git_repo, release_docs_lock, write_state
from .template_engine import TemplateEngine


def generate_index(project_name: str) -> str:
    """生成 0_INDEX.md 内容。

    包含文档清单表格和外部资源链接区域。

    Args:
        project_name: 项目名称

    Returns:
        0_INDEX.md 的完整 Markdown 内容
    """
    return f"""# {project_name} 知识文档索引

> 本文档体系由 chiwen Knowledge Kit 自动生成和维护

## 文档清单

| 文件 | 职责 | 更新方式 |
|:--|:--|:--|
| 0_INDEX.md | 本文件，索引 | AI 自动维护 |
| 1_ARCHITECTURE.md | 架构、模块映射、数据流 | AI 扫描代码生成，drift 时自动更新 |
| 2_CAPABILITIES.md | 能力矩阵（Checkbox） | AI 检测代码变更后同步 |
| 3_ROADMAP.md | 路线图（近/中/远期） | 人工维护，AI 辅助格式化 |
| 4_DECISIONS.md | 架构决策记录（ADR） | 人工记录，AI 辅助格式化 |
| 5_CHANGELOG.md | 文档变更日志 | AI 全自动维护 |
| users/@{{username}}/ | 个人空间 | 个人维护 |

## 外部资源链接

- 测试计划：{{链接到团队实际使用的测试平台}}
- 项目管理：{{链接到 Jira / Linear / GitHub Projects 等}}
"""


def generate_architecture(code_reader_output: CodeReaderOutput) -> str:
    """生成 1_ARCHITECTURE.md 内容。

    包含五个章节：技术选型、分层架构、模块职责映射、核心执行流程、ADR 快速索引。

    Args:
        code_reader_output: code-reader 扫描结果

    Returns:
        1_ARCHITECTURE.md 的完整 Markdown 内容
    """
    info = code_reader_output.project_info
    modules = code_reader_output.modules
    entry_points = code_reader_output.entry_points
    api_routes = code_reader_output.api_routes
    deps = code_reader_output.dependencies

    project_name = info.name or "未命名项目"

    # 章节 1：技术选型
    monorepo_desc = "是" if info.monorepo else "否"
    packages_desc = ""
    if info.monorepo and info.packages:
        packages_desc = "，子包：" + "、".join(info.packages)

    tech_section = f"""## 1. 技术选型

- 主语言：{info.language or '未检测到'}
- 主框架：{info.framework or '未检测到'}
- 数据库：未检测到
- 包管理器：{info.package_manager or '未检测到'}
- Monorepo 结构：{monorepo_desc}{packages_desc}"""

    # 章节 2：分层架构
    layers: dict[str, list[Module]] = {}
    for mod in modules:
        layer = mod.layer or "未分类"
        layers.setdefault(layer, []).append(mod)

    if layers:
        layer_lines = []
        for layer_name, mods in layers.items():
            mod_names = "、".join(m.name for m in mods)
            layer_lines.append(f"- **{layer_name}**：{mod_names}")
        layer_desc = "\n".join(layer_lines)
    else:
        layer_desc = "暂无模块层级信息。"

    arch_section = f"""## 2. 分层架构

{layer_desc}"""

    # 章节 3：模块职责映射
    if modules:
        table_rows = []
        for mod in modules:
            layer = mod.layer or "未分类"
            path = mod.path or "—"
            apis = "、".join(mod.public_api) if mod.public_api else "—"
            table_rows.append(f"| {layer} | `{path}` | {mod.name}（公开 API：{apis}） |")
        module_table = "\n".join(table_rows)
    else:
        module_table = "| — | — | 暂无模块信息 |"

    mapping_section = f"""## 3. 模块职责映射

| 层级 | 核心文件/目录 | 职责说明 |
|:--|:--|:--|
{module_table}"""

    # 章节 4：核心执行流程
    flow_parts = []
    if entry_points:
        flow_parts.append("### 入口文件\n")
        for ep in entry_points:
            flow_parts.append(f"- `{ep.file}`（{ep.type}）：{ep.description or '—'}")

    if api_routes:
        flow_parts.append("\n### API 路由\n")
        for route in api_routes:
            flow_parts.append(
                f"- `{route.method} {route.path}` → `{route.handler}`"
                + (f"：{route.description}" if route.description else "")
            )

    if not flow_parts:
        flow_parts.append("暂无入口文件和 API 路由信息。")

    flow_section = f"""## 4. 核心执行流程

{chr(10).join(flow_parts)}"""

    # 章节 5：ADR 快速索引
    adr_section = """## 5. ADR 快速索引

> 完整记录见 `4_DECISIONS.md`

| ADR编号 | 决策摘要 | 日期 |
|:--|:--|:--|
| — | 暂无决策记录 | — |"""

    return f"""# {project_name} 架构与流程

{tech_section}

{arch_section}

{mapping_section}

{flow_section}

{adr_section}
"""


def generate_capabilities(code_reader_output: CodeReaderOutput) -> str:
    """生成 2_CAPABILITIES.md 内容。

    基于 modules 和 api_routes 提取能力项，按模块分组。
    所有能力项标记为 [ ] 待确认状态，禁止出现 [x]。

    Args:
        code_reader_output: code-reader 扫描结果

    Returns:
        2_CAPABILITIES.md 的完整 Markdown 内容
    """
    info = code_reader_output.project_info
    modules = code_reader_output.modules
    api_routes = code_reader_output.api_routes
    project_name = info.name or "未命名项目"

    sections: list[str] = []

    # 按模块分组列出能力
    for mod in modules:
        section_lines = [f"## {mod.name}"]
        if mod.public_api:
            for api in mod.public_api:
                section_lines.append(f"- [ ] {api}")
        else:
            section_lines.append("- [ ] （暂无检测到的能力项）")
        sections.append("\n".join(section_lines))

    # API 路由作为独立能力组
    if api_routes:
        route_lines = ["## API 路由"]
        for route in api_routes:
            desc = f"{route.method} {route.path}"
            if route.description:
                desc += f" — {route.description}"
            route_lines.append(f"- [ ] {desc}")
        sections.append("\n".join(route_lines))

    if not sections:
        sections.append("暂无检测到的能力项。请执行 `sync` 命令更新。")

    capabilities_body = "\n\n".join(sections)

    return f"""# {project_name} 能力矩阵

> 本文件由 AI 自动维护，仅对真实可用能力打勾。
> 虚假勾选（文档写了代码没实现）是最高级别的文档事故。

{capabilities_body}
"""


def generate_roadmap(project_name: str) -> str:
    """生成 3_ROADMAP.md 空模板。

    包含近期计划、中期计划、远期愿景三个章节。

    Args:
        project_name: 项目名称

    Returns:
        3_ROADMAP.md 的完整 Markdown 内容
    """
    return f"""# {project_name} 路线图

## 近期计划（Next Sprint / Next Month）

- 进行中项目
  - 验收标准：...

## 中期计划（Next Quarter）

- 计划项目1
  - 目标：...

## 远期愿景（Future）

- 愿景描述
"""


def generate_decisions(project_name: str) -> str:
    """生成 4_DECISIONS.md 空模板。

    包含 ADR 格式说明，每条 ADR 含状态、背景、决策、后果四个章节。

    Args:
        project_name: 项目名称

    Returns:
        4_DECISIONS.md 的完整 Markdown 内容
    """
    return f"""# {project_name} 架构决策记录（ADR）

> 本文件记录项目中的重大架构决策。每条 ADR 包含状态、背景、决策和后果四个章节。

## ADR 格式说明

每条 ADR 应遵循以下格式：

---

# ADR-{{序号}}：{{决策标题}}

## 状态

Accepted | Deprecated | Superseded by ADR-{{XXX}}

## 背景

{{做这个决策时的上下文和问题陈述}}

## 决策

{{核心决策内容}}

## 后果

### 正面

- ...

### 负面

- ...

---
日期：{{YYYY-MM-DD}}

---

> 请在下方添加新的 ADR 记录。
"""


def generate_changelog(project_name: str) -> str:
    """生成 5_CHANGELOG.md 空模板。

    包含格式说明，按日期分组，每条记录含变更类型、目标文档、变更摘要。

    Args:
        project_name: 项目名称

    Returns:
        5_CHANGELOG.md 的完整 Markdown 内容
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"""# {project_name} 文档变更日志

> 本文件由 AI 自动维护，不建议手动编辑

## {today}

| 变更类型 | 文档 | 摘要 |
|:--|:--|:--|
| [初始化] | 全部文档 | 由 init 命令自动生成文档骨架 |
"""


def update_gitignore(project_root: str) -> bool:
    """追加 .docs/users/*/notepad.md 到 .gitignore。

    如果 .gitignore 不存在则创建；如果条目已存在则跳过。

    Args:
        project_root: 项目根目录路径

    Returns:
        True 表示追加了条目，False 表示条目已存在或无需操作
    """
    gitignore_path = os.path.join(project_root, ".gitignore")
    entry = ".docs/users/*/notepad.md"

    existing_content = ""
    if os.path.isfile(gitignore_path):
        with open(gitignore_path, encoding="utf-8") as f:
            existing_content = f.read()

    # 检查条目是否已存在（按行匹配）
    lines = existing_content.splitlines()
    for line in lines:
        if line.strip() == entry:
            return False

    # 追加条目
    with open(gitignore_path, "a", encoding="utf-8") as f:
        # 如果文件非空且不以换行结尾，先加一个换行
        if existing_content and not existing_content.endswith("\n"):
            f.write("\n")
        f.write(f"{entry}\n")

    return True


def update_gitattributes(project_root: str) -> bool:
    gitattributes_path = os.path.join(project_root, ".gitattributes")
    entries = [
        ".docs/2_CAPABILITIES.md merge=union",
        ".docs/5_CHANGELOG.md merge=union",
    ]

    existing_content = ""
    if os.path.isfile(gitattributes_path):
        with open(gitattributes_path, encoding="utf-8") as f:
            existing_content = f.read()

    lines = existing_content.splitlines()
    existing = {line.strip() for line in lines if line.strip()}

    to_add = [e for e in entries if e not in existing]
    if not to_add:
        return False

    with open(gitattributes_path, "a", encoding="utf-8") as f:
        if existing_content and not existing_content.endswith("\n"):
            f.write("\n")
        for e in to_add:
            f.write(e + "\n")

    return True


def _build_template_variables(
    project_name: str,
    output: CodeReaderOutput,
) -> dict[str, str]:
    """从 CodeReaderOutput 构建模板变量字典。

    所有变量值均为已格式化的 Markdown 文本字符串。

    Args:
        project_name: 项目名称
        output: code-reader 扫描结果

    Returns:
        模板变量字典，包含 project_name, generated_at, modules,
        capabilities, entry_points, api_routes, dependencies
    """
    info = output.project_info
    modules = output.modules
    entry_points = output.entry_points
    api_routes = output.api_routes
    deps = output.dependencies

    # modules: 模块信息（Markdown 格式）
    if modules:
        mod_lines = []
        for mod in modules:
            layer = mod.layer or "未分类"
            path = mod.path or "—"
            apis = "、".join(mod.public_api) if mod.public_api else "—"
            mod_lines.append(f"- **{mod.name}**（{layer}）：`{path}`，公开 API：{apis}")
        modules_md = "\n".join(mod_lines)
    else:
        modules_md = "暂无模块信息。"

    # entry_points: 入口文件列表
    if entry_points:
        ep_lines = []
        for ep in entry_points:
            ep_lines.append(f"- `{ep.file}`（{ep.type}）：{ep.description or '—'}")
        entry_points_md = "\n".join(ep_lines)
    else:
        entry_points_md = "暂无入口文件信息。"

    # api_routes: API 路由列表
    if api_routes:
        route_lines = []
        for route in api_routes:
            route_lines.append(
                f"- `{route.method} {route.path}` → `{route.handler}`"
                + (f"：{route.description}" if route.description else "")
            )
        api_routes_md = "\n".join(route_lines)
    else:
        api_routes_md = "暂无 API 路由信息。"

    # dependencies: 依赖列表
    if deps.direct:
        dep_lines = [f"- {d}" for d in deps.direct]
        dependencies_md = "\n".join(dep_lines)
    else:
        dependencies_md = "暂无依赖信息。"

    # capabilities: 能力矩阵内容
    cap_sections: list[str] = []
    for mod in modules:
        section_lines = [f"## {mod.name}"]
        if mod.public_api:
            for api in mod.public_api:
                section_lines.append(f"- [ ] {api}")
        else:
            section_lines.append("- [ ] （暂无检测到的能力项）")
        cap_sections.append("\n".join(section_lines))

    if api_routes:
        route_section_lines = ["## API 路由"]
        for route in api_routes:
            desc = f"{route.method} {route.path}"
            if route.description:
                desc += f" — {route.description}"
            route_section_lines.append(f"- [ ] {desc}")
        cap_sections.append("\n".join(route_section_lines))

    if not cap_sections:
        capabilities_md = "暂无检测到的能力项。请执行 `sync` 命令更新。"
    else:
        capabilities_md = "\n\n".join(cap_sections)

    # generated_at: 当前日期
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return {
        "project_name": project_name,
        "generated_at": generated_at,
        "modules": modules_md,
        "capabilities": capabilities_md,
        "entry_points": entry_points_md,
        "api_routes": api_routes_md,
        "dependencies": dependencies_md,
    }


def init_docs(project_root: str, mode: str = "error", lock_ttl_seconds: int = 600) -> dict:
    """主函数：调用 code-reader 扫描项目并生成所有文档。

    流程：
    1. 调用 code-reader 扫描项目
    2. 创建 .docs/ 目录
    3. 使用 TemplateEngine 渲染并生成全部 6 个文档文件
    4. 更新 .gitignore

    Args:
        project_root: 项目根目录绝对路径

    Returns:
        包含生成结果摘要的字典：
        - files: 生成的文件列表
        - scan_meta: 扫描统计信息
        - project_name: 项目名称
        - gitignore_updated: 是否更新了 .gitignore
    """
    # 1. 调用 code-reader 扫描项目
    input_params = CodeReaderInput(project_root=project_root)
    output = scan_project(input_params)

    project_name = output.project_info.name or os.path.basename(project_root)

    docs_dir = os.path.join(project_root, ".docs")
    os.makedirs(docs_dir, exist_ok=True)

    if mode not in ("error", "overwrite", "fill_missing"):
        raise ValueError(f"mode 必须为 error/overwrite/fill_missing 之一，当前值：{mode}")

    if mode == "error":
        existing = [f for f in os.listdir(docs_dir) if f.endswith(".md")]
        if existing:
            raise ValueError(f".docs/ 已存在，如需覆盖生成请使用 mode=overwrite：{docs_dir}")

    lock = acquire_docs_lock(docs_dir, ttl_seconds=lock_ttl_seconds)
    try:
        engine = TemplateEngine(project_root)
        variables = _build_template_variables(project_name, output)

        template_names = [
            "0_INDEX.md",
            "1_ARCHITECTURE.md",
            "2_CAPABILITIES.md",
            "3_ROADMAP.md",
            "4_DECISIONS.md",
            "5_CHANGELOG.md",
        ]

        files_generated = []
        for template_name in template_names:
            result = engine.render(template_name, variables)
            filepath = os.path.join(docs_dir, template_name)
            if mode == "fill_missing" and os.path.exists(filepath):
                continue
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(result.content)
            files_generated.append(filepath)

        gitignore_updated = update_gitignore(project_root)
        gitattributes_updated = update_gitattributes(project_root)

        git_available = is_git_repo(project_root)
        state = {
            "tool": "init",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project_root": project_root,
            "project_name": project_name,
            "lock": lock.to_dict(),
            "mode": mode,
            "files": [os.path.relpath(p, project_root) for p in files_generated],
            "git": {
                "available": git_available,
                "head": git_head(project_root) if git_available else "",
            },
        }
        write_state(docs_dir, state)

        return {
            "files": files_generated,
            "scan_meta": {
                "total_files": output.scan_meta.total_files,
                "total_lines": output.scan_meta.total_lines,
                "scan_duration_ms": output.scan_meta.scan_duration_ms,
                "modules_count": len(output.modules),
            },
            "project_name": project_name,
            "gitignore_updated": gitignore_updated,
            "gitattributes_updated": gitattributes_updated,
        }
    finally:
        release_docs_lock(docs_dir)
