"""chiwen Knowledge Kit - MCP Server

使用 MCP SDK 注册所有 MCP 工具，通过标准 MCP 协议提供服务。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from enum import Enum

from mcp.server.fastmcp import FastMCP


def _serialize(obj):
    """将对象转为 JSON 兼容的结构，处理 dataclass 与 Enum。"""
    if is_dataclass(obj):
        data = asdict(obj)
    elif isinstance(obj, (dict, list, str, int, float, bool)) or obj is None:
        data = obj
    else:
        data = {"value": str(obj)}

    def _convert(d):
        if isinstance(d, dict):
            return {k: _convert(v) for k, v in d.items()}
        if isinstance(d, list):
            return [_convert(i) for i in d]
        if isinstance(d, Enum):
            return d.value
        return d

    return _convert(data)

from .code_reader import CodeReaderInput, scan_project
from .doc_generator import init_docs
from .doc_code_lens import run_doc_code_lens
from .git_changelog import run_git_changelog
from .onboard import onboard
from .status import export_markdown, get_status
from .sync import sync_docs
from .models import DocCodeLensInput, GitChangelogInput

mcp = FastMCP(
    name="chiwen-knowledge-kit",
    instructions="chiwen Knowledge Kit MCP 工具集，提供代码扫描、文档分析等能力。",
)


@mcp.tool(
    name="code-reader",
    description=(
        "深度扫描代码库，提取结构化项目知识。"
        "返回项目信息、目录结构、入口文件、模块、数据模型、API 路由、依赖和扫描元数据。"
    ),
)
def code_reader(
    project_root: str,
    depth: int = 3,
    focus: list[str] | None = None,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> str:
    """扫描项目代码库并返回结构化知识 JSON。

    Args:
        project_root: 项目根目录绝对路径（必填）
        depth: 扫描深度，默认 3
        focus: 聚焦特定模块列表，默认扫描全部
        include_patterns: 文件包含模式列表，默认 ["*"]
        exclude_patterns: 排除模式列表，默认 ["node_modules", ".git"]

    Returns:
        CodeReaderOutput 的 JSON 字符串
    """
    # 验证必填参数
    if not project_root or not project_root.strip():
        return json.dumps(
            {"error": "参数错误：project_root 为必填项，不能为空"},
            ensure_ascii=False,
        )

    # 验证路径存在
    if not os.path.isdir(project_root):
        return json.dumps(
            {"error": f"路径不存在或不是目录：{project_root}"},
            ensure_ascii=False,
        )

    input_params = CodeReaderInput(
        project_root=project_root,
        depth=depth,
        focus=focus if focus is not None else [],
        include_patterns=include_patterns if include_patterns is not None else ["*"],
        exclude_patterns=(
            exclude_patterns
            if exclude_patterns is not None
            else ["node_modules", ".git"]
        ),
    )

    try:
        result = scan_project(input_params)
        return json.dumps(_serialize(result), ensure_ascii=False)
    except Exception as e:
        return json.dumps(
            {"error": f"扫描失败：{e}"},
            ensure_ascii=False,
        )


@mcp.tool(
    name="init-docs",
    description="初始化生成 .docs/ 文档体系（确定性生成，避免不同 LLM 输出差异）。",
)
def init_docs_tool(
    project_root: str,
    overwrite: bool = False,
    mode: str = "error",
    lock_ttl_seconds: int = 600,
) -> str:
    if not project_root or not project_root.strip():
        return json.dumps(
            {"error": "参数错误：project_root 为必填项，不能为空"},
            ensure_ascii=False,
        )

    if not os.path.isdir(project_root):
        return json.dumps(
            {"error": f"路径不存在或不是目录：{project_root}"},
            ensure_ascii=False,
        )

    if overwrite:
        mode = "overwrite"

    try:
        result = init_docs(project_root, mode=mode, lock_ttl_seconds=lock_ttl_seconds)
        return json.dumps(_serialize(result), ensure_ascii=False)
    except Exception as e:
        return json.dumps(
            {"error": f"初始化失败：{e}"},
            ensure_ascii=False,
        )


@mcp.tool(
    name="doc-code-lens",
    description=(
        "文档与代码的双向透视镜，检测文档与代码之间的不一致（drift）。"
        "返回 drift 总览统计、Forward Drift 列表、Reverse Drift 列表和修复建议。"
    ),
)
def doc_code_lens(
    project_root: str,
    doc_path: str | None = None,
    mode: str = "full",
) -> str:
    """检测文档与代码之间的 drift 并返回分析报告 JSON。

    Args:
        project_root: 项目根目录绝对路径（必填）
        doc_path: 指定文档路径，None 则检查全部文档
        mode: 检测模式，可选 forward / reverse / full，默认 full

    Returns:
        DocCodeLensOutput 的 JSON 字符串
    """
    # 验证必填参数
    if not project_root or not project_root.strip():
        return json.dumps(
            {"error": "参数错误：project_root 为必填项，不能为空"},
            ensure_ascii=False,
        )

    # 验证路径存在
    if not os.path.isdir(project_root):
        return json.dumps(
            {"error": f"路径不存在或不是目录：{project_root}"},
            ensure_ascii=False,
        )

    # 验证 .docs/ 目录存在
    docs_dir = os.path.join(project_root, ".docs")
    if not os.path.isdir(docs_dir):
        return json.dumps(
            {"error": f".docs/ 目录不存在，请先执行 init 命令：{docs_dir}"},
            ensure_ascii=False,
        )

    # 验证 mode 参数
    valid_modes = ("forward", "reverse", "full")
    if mode not in valid_modes:
        return json.dumps(
            {"error": f"参数错误：mode 必须为 {', '.join(valid_modes)} 之一，当前值：{mode}"},
            ensure_ascii=False,
        )

    input_params = DocCodeLensInput(
        project_root=project_root,
        doc_path=doc_path,
        mode=mode,
    )

    try:
        result = run_doc_code_lens(input_params)
        return json.dumps(_serialize(result), ensure_ascii=False)
    except Exception as e:
        return json.dumps(
            {"error": f"扫描失败：{e}"},
            ensure_ascii=False,
        )


@mcp.tool(
    name="sync-docs",
    description="同步 .docs/ 与代码（确定性修复能力矩阵与 drift，并更新 5_CHANGELOG.md）。",
)
def sync_docs_tool(
    project_root: str,
    allow_dirty: bool = False,
    allow_risky: bool = False,
    lock_ttl_seconds: int = 600,
) -> str:
    if not project_root or not project_root.strip():
        return json.dumps(
            {"error": "参数错误：project_root 为必填项，不能为空"},
            ensure_ascii=False,
        )

    if not os.path.isdir(project_root):
        return json.dumps(
            {"error": f"路径不存在或不是目录：{project_root}"},
            ensure_ascii=False,
        )

    try:
        result = sync_docs(
            project_root,
            allow_dirty=allow_dirty,
            allow_risky=allow_risky,
            lock_ttl_seconds=lock_ttl_seconds,
        )
        return json.dumps(_serialize(result), ensure_ascii=False)
    except Exception as e:
        return json.dumps(
            {"error": f"sync 失败：{e}"},
            ensure_ascii=False,
        )


@mcp.tool(
    name="status-report",
    description="生成文档健康度报告（可选写入 .docs/STATUS_REPORT.md）。",
)
def status_report(
    project_root: str,
    write_markdown: bool = False,
    output_path: str | None = None,
) -> str:
    if not project_root or not project_root.strip():
        return json.dumps(
            {"error": "参数错误：project_root 为必填项，不能为空"},
            ensure_ascii=False,
        )

    if not os.path.isdir(project_root):
        return json.dumps(
            {"error": f"路径不存在或不是目录：{project_root}"},
            ensure_ascii=False,
        )

    try:
        report = get_status(project_root)
        md_text = ""
        md_path = ""
        if write_markdown:
            md_text = export_markdown(report, output_path=output_path, project_root=project_root)
            md_path = output_path or os.path.join(project_root, ".docs", "STATUS_REPORT.md")
        return json.dumps(
            _serialize(
                {
                    "report": report,
                    "markdown": md_text,
                    "markdown_path": md_path,
                }
            ),
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps(
            {"error": f"status 失败：{e}"},
            ensure_ascii=False,
        )


@mcp.tool(
    name="onboard-user",
    description="创建 .docs/users/@{username}/ 个人空间（notepad.md + cache.md）并返回阅读清单。",
)
def onboard_user(
    project_root: str,
    username: str | None = None,
    overwrite: bool = False,
) -> str:
    if not project_root or not project_root.strip():
        return json.dumps(
            {"error": "参数错误：project_root 为必填项，不能为空"},
            ensure_ascii=False,
        )

    if not os.path.isdir(project_root):
        return json.dumps(
            {"error": f"路径不存在或不是目录：{project_root}"},
            ensure_ascii=False,
        )

    try:
        result = onboard(project_root, username=username, overwrite=overwrite)
        return json.dumps(_serialize(result), ensure_ascii=False)
    except Exception as e:
        return json.dumps(
            {"error": f"onboard 失败：{e}"},
            ensure_ascii=False,
        )


@mcp.tool(
    name="git-changelog",
    description=(
        "从 Git 历史提取协作知识。"
        "返回贡献者统计、模块活跃度、近期提交和过期文件列表。"
    ),
)
def git_changelog(
    project_root: str,
    since: str = "30 days ago",
    until: str = "now",
    top_n: int = 10,
    group_by: str = "person",
) -> str:
    """从 Git 历史提取协作知识并返回分析报告 JSON。

    Args:
        project_root: Git 仓库根目录绝对路径（必填）
        since: 起始时间，默认 "30 days ago"
        until: 结束时间，默认 "now"
        top_n: Top N 贡献者，默认 10
        group_by: 聚合方式，可选 person / module / file，默认 person

    Returns:
        GitChangelogOutput 的 JSON 字符串
    """
    # 验证必填参数
    if not project_root or not project_root.strip():
        return json.dumps(
            {"error": "参数错误：project_root 为必填项，不能为空"},
            ensure_ascii=False,
        )

    # 验证路径存在
    if not os.path.isdir(project_root):
        return json.dumps(
            {"error": f"路径不存在或不是目录：{project_root}"},
            ensure_ascii=False,
        )

    # 验证 group_by 参数
    valid_group_by = ("person", "module", "file")
    if group_by not in valid_group_by:
        return json.dumps(
            {"error": f"参数错误：group_by 必须为 {', '.join(valid_group_by)} 之一，当前值：{group_by}"},
            ensure_ascii=False,
        )

    input_params = GitChangelogInput(
        project_root=project_root,
        since=since,
        until=until,
        top_n=top_n,
        group_by=group_by,
    )

    try:
        result = run_git_changelog(input_params)
        return json.dumps(_serialize(result), ensure_ascii=False)
    except RuntimeError as e:
        return json.dumps(
            {"error": str(e)},
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps(
            {"error": f"分析失败：{e}"},
            ensure_ascii=False,
        )


if __name__ == "__main__":
    mcp.run()
