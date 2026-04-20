"""chiwen Knowledge Kit - code-reader MCP 核心扫描逻辑

深度扫描代码库，提取结构化项目知识。
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    ApiRoute,
    CodeReaderOutput,
    DataModel,
    Dependencies,
    EntryPoint,
    FileNode,
    Module,
    ProjectInfo,
    ScanMeta,
)


# ── 输入参数模型 ──


@dataclass
class CodeReaderInput:
    """code-reader MCP 工具的输入参数"""

    project_root: str
    depth: int = 3
    focus: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=lambda: ["*"])
    exclude_patterns: list[str] = field(
        default_factory=lambda: ["node_modules", ".git"]
    )


# ── 常量 ──

# 入口文件识别模式
ENTRY_POINT_PATTERNS: dict[str, str] = {
    "main.py": "main",
    "app.py": "main",
    "index.py": "main",
    "manage.py": "main",
    "wsgi.py": "main",
    "asgi.py": "main",
    "server.py": "main",
    "index.ts": "main",
    "index.js": "main",
    "main.ts": "main",
    "main.js": "main",
    "app.ts": "main",
    "app.js": "main",
    "server.ts": "main",
    "server.js": "main",
    "main.go": "main",
    "main.rs": "main",
    "Makefile": "config",
    "Dockerfile": "config",
    "docker-compose.yml": "config",
    "docker-compose.yaml": "config",
}

# 路由文件识别模式
ROUTER_FILE_PATTERNS: list[str] = [
    "routes", "router", "urls", "endpoints", "api",
]

# 层级推断关键词
LAYER_KEYWORDS: dict[str, list[str]] = {
    "controller": ["controller", "handler", "view", "endpoint", "api", "route"],
    "service": ["service", "usecase", "use_case", "interactor", "logic"],
    "model": ["model", "entity", "schema", "dto", "type", "domain"],
    "repository": ["repository", "repo", "dao", "store", "persistence", "db"],
    "middleware": ["middleware", "interceptor", "guard", "filter", "pipe"],
    "config": ["config", "setting", "env", "constant"],
    "util": ["util", "helper", "common", "shared", "lib", "tool"],
    "test": ["test", "spec", "__test__", "__tests__"],
}

# 主要框架识别
FRAMEWORK_INDICATORS: dict[str, str] = {
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "express": "Express",
    "next": "Next.js",
    "nuxt": "Nuxt.js",
    "react": "React",
    "vue": "Vue",
    "angular": "Angular",
    "spring": "Spring",
    "gin": "Gin",
    "actix": "Actix",
    "axum": "Axum",
    "nest": "NestJS",
    "koa": "Koa",
    "hapi": "Hapi",
    "sveltekit": "SvelteKit",
    "svelte": "Svelte",
    "remix": "Remix",
    "astro": "Astro",
}

# 语言识别（按扩展名）
LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".swift": "Swift",
    ".dart": "Dart",
}


# ── 辅助函数 ──


def _is_excluded(path: str, exclude_patterns: list[str]) -> bool:
    """检查路径是否匹配任何排除模式。

    对路径的每个部分进行 fnmatch 匹配。
    """
    parts = Path(path).parts
    for pattern in exclude_patterns:
        for part in parts:
            if fnmatch.fnmatch(part, pattern):
                return True
        # 也对完整相对路径做匹配
        if fnmatch.fnmatch(path, pattern):
            return True
    return False


def _is_included(path: str, include_patterns: list[str]) -> bool:
    """检查路径是否匹配任何包含模式。"""
    name = Path(path).name
    for pattern in include_patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
        if fnmatch.fnmatch(path, pattern):
            return True
    return False


def _safe_read_text(filepath: str, max_bytes: int = 1_048_576) -> str | None:
    """安全读取文本文件，处理编码异常和权限不足。

    返回 None 表示跳过该文件。
    """
    try:
        size = os.path.getsize(filepath)
        if size > max_bytes:
            return None
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except (PermissionError, OSError):
        return None


def _count_lines(filepath: str) -> int:
    """统计文件行数，出错返回 0。"""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except (PermissionError, OSError):
        return 0


def _infer_purpose(rel_path: str) -> str:
    """根据文件/目录名推断用途。"""
    name = Path(rel_path).stem.lower()
    full_name = Path(rel_path).name.lower()

    # 配置文件
    config_names = {
        "package.json", "pyproject.toml", "cargo.toml", "go.mod",
        "tsconfig.json", "webpack.config.js", "vite.config.ts",
        ".eslintrc", ".prettierrc", "jest.config.js", "setup.py",
        "setup.cfg", "requirements.txt", "pipfile", "gemfile",
        "makefile", "dockerfile", "docker-compose.yml",
    }
    if full_name in config_names:
        return "config"

    # README
    if name.startswith("readme"):
        return "documentation"

    # 测试文件
    if "test" in name or "spec" in name or name.startswith("test_"):
        return "test"

    # 层级推断
    for layer, keywords in LAYER_KEYWORDS.items():
        for kw in keywords:
            if kw in name:
                return layer

    return ""


def _infer_layer(name: str, rel_path: str) -> str:
    """推断模块所属层级。"""
    lower_name = name.lower()
    lower_path = rel_path.lower()
    combined = f"{lower_name} {lower_path}"

    for layer, keywords in LAYER_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                return layer
    return "unknown"


# ── 项目信息提取 ──


def _detect_project_info(project_root: str) -> ProjectInfo:
    """通过包管理器配置文件识别项目信息。"""
    info = ProjectInfo()
    root = Path(project_root)

    # package.json (Node.js)
    pkg_json = root / "package.json"
    if pkg_json.is_file():
        content = _safe_read_text(str(pkg_json))
        if content:
            try:
                data = json.loads(content)
                info.name = data.get("name", "")
                info.package_manager = _detect_node_package_manager(root)

                # 检测框架
                all_deps = {}
                all_deps.update(data.get("dependencies", {}))
                all_deps.update(data.get("devDependencies", {}))
                info.framework = _detect_framework_from_deps(all_deps)

                # 检测语言
                if (root / "tsconfig.json").is_file() or any(
                    root.glob("**/*.ts")
                ):
                    info.language = "TypeScript"
                else:
                    info.language = "JavaScript"

                # monorepo 检测
                if "workspaces" in data:
                    info.monorepo = True
                    workspaces = data["workspaces"]
                    if isinstance(workspaces, list):
                        info.packages = workspaces
                    elif isinstance(workspaces, dict):
                        info.packages = workspaces.get("packages", [])
            except (json.JSONDecodeError, KeyError):
                pass

    # pyproject.toml (Python)
    pyproject = root / "pyproject.toml"
    if pyproject.is_file() and not info.name:
        content = _safe_read_text(str(pyproject))
        if content:
            info.language = "Python"
            info.package_manager = "pip"

            # 简单解析 TOML（不引入额外依赖）
            name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
            if name_match:
                info.name = name_match.group(1)

            # 检测框架
            for fw_key, fw_name in FRAMEWORK_INDICATORS.items():
                if fw_key in content.lower():
                    info.framework = fw_name
                    break

            # 检测 poetry
            if "[tool.poetry]" in content:
                info.package_manager = "poetry"
            elif "[tool.hatch]" in content or "hatchling" in content:
                info.package_manager = "hatch"

    # Cargo.toml (Rust)
    cargo = root / "Cargo.toml"
    if cargo.is_file() and not info.name:
        content = _safe_read_text(str(cargo))
        if content:
            info.language = "Rust"
            info.package_manager = "cargo"
            name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
            if name_match:
                info.name = name_match.group(1)
            # workspace = monorepo
            if "[workspace]" in content:
                info.monorepo = True

    # go.mod (Go)
    gomod = root / "go.mod"
    if gomod.is_file() and not info.name:
        content = _safe_read_text(str(gomod))
        if content:
            info.language = "Go"
            info.package_manager = "go modules"
            mod_match = re.search(r"module\s+(\S+)", content)
            if mod_match:
                info.name = mod_match.group(1).split("/")[-1]

    # pom.xml (Java/Maven)
    pom = root / "pom.xml"
    if pom.is_file() and not info.name:
        info.language = "Java"
        info.package_manager = "maven"

    # build.gradle (Java/Gradle)
    gradle = root / "build.gradle"
    gradle_kts = root / "build.gradle.kts"
    if (gradle.is_file() or gradle_kts.is_file()) and not info.name:
        info.language = "Java"
        info.package_manager = "gradle"

    # 如果仍未检测到名称，使用目录名
    if not info.name:
        info.name = root.name

    # 如果仍未检测到语言，通过文件扩展名统计
    if not info.language:
        info.language = _detect_language_by_extension(root)

    # lerna.json / pnpm-workspace.yaml monorepo 检测
    if (root / "lerna.json").is_file():
        info.monorepo = True
    if (root / "pnpm-workspace.yaml").is_file():
        info.monorepo = True

    return info


def _detect_node_package_manager(root: Path) -> str:
    """检测 Node.js 包管理器。"""
    if (root / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (root / "yarn.lock").is_file():
        return "yarn"
    if (root / "bun.lockb").is_file():
        return "bun"
    return "npm"


def _detect_framework_from_deps(deps: dict) -> str:
    """从依赖列表中检测框架。"""
    for dep_name in deps:
        dep_lower = dep_name.lower()
        for fw_key, fw_name in FRAMEWORK_INDICATORS.items():
            if fw_key in dep_lower:
                return fw_name
    return ""


def _detect_language_by_extension(root: Path) -> str:
    """通过文件扩展名统计推断主语言。"""
    ext_count: dict[str, int] = {}
    try:
        for item in root.rglob("*"):
            if item.is_file():
                ext = item.suffix.lower()
                if ext in LANGUAGE_EXTENSIONS:
                    lang = LANGUAGE_EXTENSIONS[ext]
                    ext_count[lang] = ext_count.get(lang, 0) + 1
    except (PermissionError, OSError):
        pass

    if ext_count:
        return max(ext_count, key=ext_count.get)  # type: ignore[arg-type]
    return ""


# ── 目录遍历 ──


def _scan_directory(
    project_root: str,
    depth: int,
    include_patterns: list[str],
    exclude_patterns: list[str],
    focus: list[str],
) -> tuple[list[FileNode], int, int]:
    """递归遍历目录，返回 (文件节点列表, 文件总数, 代码总行数)。"""
    nodes: list[FileNode] = []
    total_files = 0
    total_lines = 0
    root = Path(project_root)

    def _walk(current: Path, current_depth: int) -> None:
        nonlocal total_files, total_lines

        if current_depth > depth:
            return

        try:
            entries = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name))
        except (PermissionError, OSError):
            return

        for entry in entries:
            rel_path = str(entry.relative_to(root))

            # 排除模式过滤
            if _is_excluded(rel_path, exclude_patterns):
                continue

            # focus 参数：仅在顶层目录过滤
            if focus and current_depth == 0 and entry.is_dir():
                if not any(
                    fnmatch.fnmatch(entry.name, f) or entry.name == f
                    for f in focus
                ):
                    # 仍然记录目录节点，但不深入
                    nodes.append(FileNode(
                        path=rel_path,
                        type="dir",
                        purpose=_infer_purpose(rel_path),
                        line_count=0,
                    ))
                    continue

            if entry.is_dir():
                nodes.append(FileNode(
                    path=rel_path,
                    type="dir",
                    purpose=_infer_purpose(rel_path),
                    line_count=0,
                ))
                _walk(entry, current_depth + 1)
            elif entry.is_file():
                # 包含模式过滤（仅对文件）
                if not _is_included(rel_path, include_patterns):
                    continue

                line_count = _count_lines(str(entry))
                total_files += 1
                total_lines += line_count

                nodes.append(FileNode(
                    path=rel_path,
                    type="file",
                    purpose=_infer_purpose(rel_path),
                    line_count=line_count,
                ))

    _walk(root, 0)
    return nodes, total_files, total_lines


# ── 入口文件检测 ──


def _detect_entry_points(
    project_root: str, structure: list[FileNode]
) -> list[EntryPoint]:
    """识别入口文件。"""
    entries: list[EntryPoint] = []
    seen: set[str] = set()

    for node in structure:
        if node.type != "file":
            continue
        name = Path(node.path).name.lower()

        # 精确匹配入口文件模式
        if name in ENTRY_POINT_PATTERNS:
            entry_type = ENTRY_POINT_PATTERNS[name]
            if node.path not in seen:
                seen.add(node.path)
                entries.append(EntryPoint(
                    file=node.path,
                    type=entry_type,
                    description=f"{entry_type} entry point",
                ))

        # 路由文件
        stem = Path(node.path).stem.lower()
        if any(kw in stem for kw in ROUTER_FILE_PATTERNS) and node.path not in seen:
            seen.add(node.path)
            entries.append(EntryPoint(
                file=node.path,
                type="router",
                description="route definitions",
            ))

    return entries


# ── 模块推断 ──


def _infer_modules(
    project_root: str,
    structure: list[FileNode],
    focus: list[str],
) -> list[Module]:
    """通过文件命名约定和导入关系推断模块层级和依赖。"""
    root = Path(project_root)
    modules: list[Module] = []
    ignored_module_dirs = {
        ".git",
        ".docs",
        ".venv",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        "coverage",
        "tests",
        "test",
    }

    source_root: str | None = None
    module_groups: dict[str, list[FileNode]] = {}

    src_children: dict[str, list[FileNode]] = {}
    for node in structure:
        parts = Path(node.path).parts
        if len(parts) >= 2 and parts[0] == "src" and parts[1] not in ignored_module_dirs:
            src_children.setdefault(parts[1], []).append(node)

    if src_children:
        source_root = "src"
        module_groups = src_children
    else:
        top_dirs: dict[str, list[FileNode]] = {}
        for node in structure:
            parts = Path(node.path).parts
            if not parts:
                continue
            top_dir = parts[0]
            if top_dir in ignored_module_dirs:
                continue
            top_dirs.setdefault(top_dir, []).append(node)
        module_groups = top_dirs

    known_modules = set(module_groups.keys())

    for module_name, nodes in module_groups.items():
        dir_rel_path = (
            str(Path(source_root) / module_name) if source_root else module_name
        )
        dir_path = root / dir_rel_path
        if not dir_path.is_dir():
            continue

        if focus and not any(
            fnmatch.fnmatch(module_name, f) or module_name == f for f in focus
        ):
            continue

        module_files = [n for n in nodes if n.type == "file"]
        if not module_files:
            continue

        layer = _infer_layer(module_name, dir_rel_path)
        public_api = _extract_public_api(root, module_files)
        dependencies = _extract_dependencies(
            root,
            module_files,
            known_modules=known_modules,
            source_root=source_root,
        )

        modules.append(
            Module(
                name=module_name,
                path=dir_rel_path,
                layer=layer,
                dependencies=dependencies,
                public_api=public_api,
            )
        )

    return modules


def _extract_public_api(root: Path, files: list[FileNode]) -> list[str]:
    """从模块文件中提取公开 API。"""
    apis: list[str] = []

    for node in files:
        filepath = str(root / node.path)
        content = _safe_read_text(filepath)
        if not content:
            continue

        ext = Path(node.path).suffix.lower()

        if ext == ".py":
            # Python: def/class 定义（非下划线开头）
            for match in re.finditer(
                r"^(?:def|class)\s+([A-Za-z][A-Za-z0-9_]*)", content, re.MULTILINE
            ):
                name = match.group(1)
                if not name.startswith("_"):
                    apis.append(name)

        elif ext in (".js", ".ts", ".tsx", ".jsx"):
            # JS/TS: export 语句
            for match in re.finditer(
                r"export\s+(?:default\s+)?(?:function|class|const|let|var|interface|type|enum)\s+([A-Za-z][A-Za-z0-9_]*)",
                content,
            ):
                apis.append(match.group(1))

        elif ext == ".go":
            # Go: 大写开头的函数/类型
            for match in re.finditer(
                r"^func\s+(?:\([^)]+\)\s+)?([A-Z][A-Za-z0-9_]*)", content, re.MULTILINE
            ):
                apis.append(match.group(1))

    return list(dict.fromkeys(apis))  # 去重保序


def _extract_public_api_by_file(root: Path, files: list[FileNode]) -> dict[str, list[str]]:
    """从模块文件中提取公开 API，按源文件分组。

    返回 {文件名(不含路径): [API 名称列表]}，跳过 __init__.py 等无 API 的文件。
    """
    result: dict[str, list[str]] = {}

    for node in files:
        filepath = str(root / node.path)
        content = _safe_read_text(filepath)
        if not content:
            continue

        ext = Path(node.path).suffix.lower()
        filename = Path(node.path).stem  # 不含扩展名

        # 跳过 __init__ 等辅助文件
        if filename.startswith("__"):
            continue

        apis: list[str] = []

        if ext == ".py":
            for match in re.finditer(
                r"^(?:def|class)\s+([A-Za-z][A-Za-z0-9_]*)", content, re.MULTILINE
            ):
                name = match.group(1)
                if not name.startswith("_"):
                    apis.append(name)

        elif ext in (".js", ".ts", ".tsx", ".jsx"):
            for match in re.finditer(
                r"export\s+(?:default\s+)?(?:function|class|const|let|var|interface|type|enum)\s+([A-Za-z][A-Za-z0-9_]*)",
                content,
            ):
                apis.append(match.group(1))

        elif ext == ".go":
            for match in re.finditer(
                r"^func\s+(?:\([^)]+\)\s+)?([A-Z][A-Za-z0-9_]*)", content, re.MULTILINE
            ):
                apis.append(match.group(1))

        if apis:
            result[filename] = list(dict.fromkeys(apis))

    return result


def _extract_dependencies(
    root: Path,
    files: list[FileNode],
    known_modules: set[str],
    source_root: str | None = None,
) -> list[str]:
    """从导入语句中提取模块间依赖。"""
    deps: set[str] = set()

    for node in files:
        filepath = str(root / node.path)
        content = _safe_read_text(filepath)
        if not content:
            continue

        ext = Path(node.path).suffix.lower()
        parts = Path(node.path).parts
        if source_root and len(parts) >= 2 and parts[0] == source_root:
            current_module = parts[1]
        else:
            current_module = parts[0] if parts else ""

        if ext == ".py":
            # Python: from X import ... / import X
            for match in re.finditer(
                r"^(?:from|import)\s+([A-Za-z_][A-Za-z0-9_.]*)", content, re.MULTILINE
            ):
                top = match.group(1).split(".")[0]
                if top != current_module and top in known_modules:
                    deps.add(top)

        elif ext in (".js", ".ts", ".tsx", ".jsx"):
            # JS/TS: import ... from '...' / require('...')
            for match in re.finditer(
                r"""(?:import\s+.*?from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))""",
                content,
            ):
                path_str = match.group(1) or match.group(2)
                if path_str.startswith("."):
                    # 相对导入 → 解析到模块
                    resolved = (Path(node.path).parent / path_str).parts
                    if resolved:
                        top = resolved[0]
                        if source_root and top == source_root and len(resolved) >= 2:
                            top = resolved[1]
                        if top != current_module and top in known_modules:
                            deps.add(top)

    return sorted(deps)


# ── 数据模型提取 ──


def _extract_data_models(
    project_root: str, structure: list[FileNode]
) -> list[DataModel]:
    """提取数据模型定义。"""
    models: list[DataModel] = []
    root = Path(project_root)

    for node in structure:
        if node.type != "file":
            continue

        ext = Path(node.path).suffix.lower()
        if ext not in (".py", ".ts", ".js", ".tsx", ".jsx"):
            continue

        filepath = str(root / node.path)
        content = _safe_read_text(filepath)
        if not content:
            continue

        if ext == ".py":
            # Python dataclass / Pydantic BaseModel / Django Model
            for match in re.finditer(
                r"^class\s+(\w+)\s*\(.*?(?:BaseModel|Model|dataclass|TypedDict|NamedTuple).*?\):",
                content,
                re.MULTILINE,
            ):
                class_name = match.group(1)
                fields = _extract_python_class_fields(content, match.end())
                models.append(DataModel(
                    name=class_name,
                    location=node.path,
                    fields=fields,
                ))

        elif ext in (".ts", ".tsx"):
            # TypeScript interface / type
            for match in re.finditer(
                r"(?:export\s+)?(?:interface|type)\s+(\w+)\s*(?:=\s*)?\{",
                content,
            ):
                type_name = match.group(1)
                fields = _extract_ts_fields(content, match.end())
                models.append(DataModel(
                    name=type_name,
                    location=node.path,
                    fields=fields,
                ))

    return models


def _extract_python_class_fields(content: str, start_pos: int) -> list[str]:
    """提取 Python 类的字段定义。"""
    fields: list[str] = []
    lines = content[start_pos:].split("\n")
    for line in lines[:30]:  # 最多看 30 行
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("class "):
            # 字段模式: name: type 或 name = ...
            field_match = re.match(r"(\w+)\s*[:=]", stripped)
            if field_match:
                fname = field_match.group(1)
                if not fname.startswith("_") and fname not in ("class", "def", "return", "self"):
                    fields.append(fname)
        elif stripped.startswith("class ") or stripped.startswith("def "):
            break
    return fields


def _extract_ts_fields(content: str, start_pos: int) -> list[str]:
    """提取 TypeScript interface/type 的字段。"""
    fields: list[str] = []
    brace_count = 1
    pos = start_pos
    current_field = ""

    while pos < len(content) and brace_count > 0:
        ch = content[pos]
        if ch == "{":
            brace_count += 1
        elif ch == "}":
            brace_count -= 1
        elif brace_count == 1:
            if ch in (":", ";", "\n"):
                field_match = re.match(r"\s*(\w+)", current_field)
                if field_match and ch == ":":
                    fields.append(field_match.group(1))
                current_field = ""
            else:
                current_field += ch
        pos += 1

    return fields


# ── API 路由提取 ──


def _extract_api_routes(
    project_root: str, structure: list[FileNode]
) -> list[ApiRoute]:
    """提取 API 路由定义。"""
    routes: list[ApiRoute] = []
    root = Path(project_root)

    for node in structure:
        if node.type != "file":
            continue

        ext = Path(node.path).suffix.lower()
        if ext not in (".py", ".ts", ".js", ".tsx", ".jsx"):
            continue

        filepath = str(root / node.path)
        content = _safe_read_text(filepath)
        if not content:
            continue

        if ext == ".py":
            routes.extend(_extract_python_routes(content, node.path))
        elif ext in (".js", ".ts", ".tsx", ".jsx"):
            routes.extend(_extract_js_routes(content, node.path))

    return routes


def _extract_python_routes(content: str, file_path: str) -> list[ApiRoute]:
    """提取 Python 路由（FastAPI / Flask / Django）。"""
    routes: list[ApiRoute] = []

    # FastAPI: @app.get("/path") / @router.post("/path")
    for match in re.finditer(
        r'@\w+\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']',
        content,
        re.IGNORECASE,
    ):
        method = match.group(1).upper()
        path = match.group(2)
        # 尝试找到下一行的函数名
        handler = _find_next_function(content, match.end())
        routes.append(ApiRoute(
            method=method,
            path=path,
            handler=f"{file_path}:{handler}" if handler else file_path,
            description="",
        ))

    # Flask: @app.route("/path", methods=["GET"])
    for match in re.finditer(
        r'@\w+\.route\s*\(\s*["\']([^"\']+)["\'](?:.*?methods\s*=\s*\[([^\]]+)\])?',
        content,
    ):
        path = match.group(1)
        methods_str = match.group(2)
        methods = ["GET"]
        if methods_str:
            methods = [m.strip().strip("'\"").upper() for m in methods_str.split(",")]
        handler = _find_next_function(content, match.end())
        for method in methods:
            routes.append(ApiRoute(
                method=method,
                path=path,
                handler=f"{file_path}:{handler}" if handler else file_path,
                description="",
            ))

    return routes


def _extract_js_routes(content: str, file_path: str) -> list[ApiRoute]:
    """提取 JavaScript/TypeScript 路由（Express / Koa / Hapi）。"""
    routes: list[ApiRoute] = []

    # Express: app.get('/path', handler) / router.post('/path', handler)
    for match in re.finditer(
        r'(?:app|router|server)\.(get|post|put|delete|patch|all)\s*\(\s*["\']([^"\']+)["\']',
        content,
        re.IGNORECASE,
    ):
        method = match.group(1).upper()
        if method == "ALL":
            method = "GET"  # 简化处理
        path = match.group(2)
        routes.append(ApiRoute(
            method=method,
            path=path,
            handler=file_path,
            description="",
        ))

    return routes


def _find_next_function(content: str, start_pos: int) -> str:
    """在给定位置之后找到下一个函数定义名。"""
    remaining = content[start_pos:start_pos + 200]
    match = re.search(r"(?:def|function|async\s+def|async\s+function)\s+(\w+)", remaining)
    return match.group(1) if match else ""


# ── 依赖提取 ──


def _extract_project_dependencies(project_root: str) -> Dependencies:
    """提取项目依赖信息。"""
    deps = Dependencies()
    root = Path(project_root)

    # package.json
    pkg_json = root / "package.json"
    if pkg_json.is_file():
        content = _safe_read_text(str(pkg_json))
        if content:
            try:
                data = json.loads(content)
                direct = list(data.get("dependencies", {}).keys())
                dev = list(data.get("devDependencies", {}).keys())
                deps.direct = direct + dev
                # major = 非 dev 依赖
                deps.major = direct
            except (json.JSONDecodeError, KeyError):
                pass

    # pyproject.toml
    pyproject = root / "pyproject.toml"
    if pyproject.is_file() and not deps.direct:
        content = _safe_read_text(str(pyproject))
        if content:
            # 简单提取 dependencies
            dep_match = re.search(
                r"dependencies\s*=\s*\[(.*?)\]", content, re.DOTALL
            )
            if dep_match:
                dep_str = dep_match.group(1)
                for m in re.finditer(r'"([a-zA-Z][\w.-]*)', dep_str):
                    deps.direct.append(m.group(1))
                deps.major = deps.direct[:]

    # requirements.txt
    req_txt = root / "requirements.txt"
    if req_txt.is_file() and not deps.direct:
        content = _safe_read_text(str(req_txt))
        if content:
            for line in content.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    pkg = re.split(r"[>=<!\[]", line)[0].strip()
                    if pkg:
                        deps.direct.append(pkg)
            deps.major = deps.direct[:]

    # Cargo.toml
    cargo = root / "Cargo.toml"
    if cargo.is_file() and not deps.direct:
        content = _safe_read_text(str(cargo))
        if content:
            in_deps = False
            for line in content.split("\n"):
                if re.match(r"\[dependencies\]", line):
                    in_deps = True
                    continue
                if line.startswith("[") and in_deps:
                    in_deps = False
                if in_deps:
                    dep_match = re.match(r"(\w[\w-]*)\s*=", line)
                    if dep_match:
                        deps.direct.append(dep_match.group(1))
            deps.major = deps.direct[:]

    return deps


# ── 主扫描函数 ──


def scan_project(input_params: CodeReaderInput) -> CodeReaderOutput:
    """执行项目扫描，返回结构化项目知识。

    Args:
        input_params: 扫描参数

    Returns:
        CodeReaderOutput 包含完整的项目知识

    Raises:
        ValueError: 当 project_root 路径不存在时
    """
    project_root = input_params.project_root

    # 验证路径
    if not os.path.isdir(project_root):
        raise ValueError(f"project_root 路径不存在或不是目录: {project_root}")

    start_time = time.monotonic()
    scan_start = datetime.now(timezone.utc)

    # 1. 项目信息提取
    project_info = _detect_project_info(project_root)

    # 2. 目录遍历
    structure, total_files, total_lines = _scan_directory(
        project_root,
        input_params.depth,
        input_params.include_patterns,
        input_params.exclude_patterns,
        input_params.focus,
    )

    # 3. 入口文件检测
    entry_points = _detect_entry_points(project_root, structure)

    # 4. 模块推断
    modules = _infer_modules(project_root, structure, input_params.focus)

    # 5. 数据模型提取
    data_models = _extract_data_models(project_root, structure)

    # 6. API 路由提取
    api_routes = _extract_api_routes(project_root, structure)

    # 7. 依赖提取
    dependencies = _extract_project_dependencies(project_root)

    # 8. 扫描元数据
    elapsed_ms = int((time.monotonic() - start_time) * 1000)
    scan_meta = ScanMeta(
        total_files=total_files,
        total_lines=total_lines,
        scan_duration_ms=elapsed_ms,
        scanned_at=scan_start.isoformat(),
    )

    return CodeReaderOutput(
        project_info=project_info,
        structure=structure,
        entry_points=entry_points,
        modules=modules,
        data_models=data_models,
        api_routes=api_routes,
        dependencies=dependencies,
        scan_meta=scan_meta,
    )
