"""chiwen Knowledge Kit - status 命令逻辑

实现 status 命令的 Python 代码逻辑（Phase 3 增强版）：
- 调用 doc-code-lens（mode=full）检查文档一致性
- 调用 git-changelog 获取协作知识数据
- 生成健康度报告：同步率 + 贡献者 + 过期文档 + 待处理 drift
- git-changelog 调用失败时（非 Git 仓库等）优雅降级，不影响核心报告
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .doc_code_lens import run_doc_code_lens
from .git_changelog import run_git_changelog
from .models import (
    Contributor,
    DocCodeLensInput,
    ForwardDrift,
    GitChangelogInput,
    ReverseDrift,
    StaleFile,
)


@dataclass
class HealthReport:
    """文档健康度报告。

    Attributes:
        sync_rate: 同步率 = in_sync / total_checked，范围 [0, 1]。
                   当 total_checked == 0 时为 1.0。
        total_checked: 总检查项数。
        in_sync: 同步项数。
        drifted: drift 项数。
        active_contributors: 最近 30 天活跃贡献者列表。
        stale_docs: 过期文档列表（长期未更新的文档）。
        pending_drifts: 待处理的 drift 项清单（Forward + Reverse）。
        git_available: git-changelog 是否可用（非 Git 仓库时为 False）。
        git_error: git-changelog 调用失败时的错误信息。
    """

    sync_rate: float = 1.0
    total_checked: int = 0
    in_sync: int = 0
    drifted: int = 0
    active_contributors: list[Contributor] = field(default_factory=list)
    stale_docs: list[StaleFile] = field(default_factory=list)
    pending_drifts: list[ForwardDrift | ReverseDrift] = field(default_factory=list)
    git_available: bool = False
    git_error: str = ""


def _filter_stale_docs(stale_files: list[StaleFile]) -> list[StaleFile]:
    """从过期文件列表中筛选出文档文件。

    仅保留 .docs/ 目录下的文件或 .md/.rst/.txt/.adoc 扩展名的文件。

    Args:
        stale_files: git-changelog 返回的全部过期文件列表

    Returns:
        仅包含文档文件的过期列表
    """
    doc_extensions = {".md", ".rst", ".txt", ".adoc"}
    result: list[StaleFile] = []
    for sf in stale_files:
        path_lower = sf.path.lower()
        is_doc = path_lower.startswith(".docs/") or path_lower.startswith(".docs\\")
        is_doc_ext = any(path_lower.endswith(ext) for ext in doc_extensions)
        if is_doc or is_doc_ext:
            result.append(sf)
    return result


def _render_report_md(report: HealthReport) -> str:
    """将 HealthReport 渲染为 Markdown 文本。

    章节结构：
    1. 标题 + 生成时间戳（ISO 8601）
    2. 概览：同步率（百分比，一位小数）、总检查项、drift 项数
    3. Forward Drift 详情表格（文档声明、文档文件、drift 类型、置信度）
    4. Reverse Drift 详情表格（代码文件、能力名称、是否已记录）
    5. 活跃贡献者列表（或「Git 信息不可用」提示）
    6. 过期文档列表（或「Git 信息不可用」提示）
    """
    lines: list[str] = []

    # 1. 标题 + ISO 8601 时间戳
    timestamp = datetime.now(timezone.utc).isoformat()
    lines.append("# 文档健康度报告")
    lines.append("")
    lines.append(f"> 生成时间：{timestamp}")
    lines.append("")

    # 2. 概览
    sync_pct = f"{report.sync_rate * 100:.1f}%"
    lines.append("## 概览")
    lines.append("")
    lines.append(f"- 同步率：{sync_pct}")
    lines.append(f"- 总检查项：{report.total_checked}")
    lines.append(f"- Drift 项数：{report.drifted}")
    lines.append("")

    # 3. Forward Drift 详情表格
    lines.append("## Forward Drift 详情")
    lines.append("")
    forward_drifts = [d for d in report.pending_drifts if isinstance(d, ForwardDrift)]
    if forward_drifts:
        lines.append("| 文档声明 | 文档文件 | drift 类型 | 置信度 |")
        lines.append("| --- | --- | --- | --- |")
        for d in forward_drifts:
            lines.append(
                f"| {d.doc_claim} | {d.doc_file} | {d.drift_type.value} | {d.confidence.value} |"
            )
    else:
        lines.append("无 Forward Drift。")
    lines.append("")

    # 4. Reverse Drift 详情表格
    lines.append("## Reverse Drift 详情")
    lines.append("")
    reverse_drifts = [d for d in report.pending_drifts if isinstance(d, ReverseDrift)]
    if reverse_drifts:
        lines.append("| 代码文件 | 能力名称 | 是否已记录 |")
        lines.append("| --- | --- | --- |")
        for d in reverse_drifts:
            documented = "是" if d.doc_mentioned else "否"
            lines.append(f"| {d.file} | {d.capability} | {documented} |")
    else:
        lines.append("无 Reverse Drift。")
    lines.append("")

    # 5. 活跃贡献者列表
    lines.append("## 活跃贡献者")
    lines.append("")
    if not report.git_available:
        lines.append("Git 信息不可用")
    elif report.active_contributors:
        for c in report.active_contributors:
            lines.append(f"- {c.name}（{c.email}）— {c.commits} 次提交")
    else:
        lines.append("无活跃贡献者。")
    lines.append("")

    # 6. 过期文档列表
    lines.append("## 过期文档")
    lines.append("")
    if not report.git_available:
        lines.append("Git 信息不可用")
    elif report.stale_docs:
        for s in report.stale_docs:
            lines.append(f"- {s.path}（{s.days_since_change} 天未更新）")
    else:
        lines.append("无过期文档。")
    lines.append("")

    return "\n".join(lines)


def export_markdown(
    report: HealthReport,
    output_path: str | None = None,
    project_root: str = "",
) -> str:
    """将 HealthReport 渲染为 Markdown 并写入文件。

    Args:
        report: 健康度报告
        output_path: 输出文件路径，None 则写入 .docs/STATUS_REPORT.md
        project_root: 项目根目录（用于计算默认输出路径）

    Returns:
        渲染后的 Markdown 文本
    """
    md_text = _render_report_md(report)

    if output_path is None:
        output_path = os.path.join(project_root, ".docs", "STATUS_REPORT.md")

    parent_dir = os.path.dirname(output_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_text)

    return md_text


def get_status(project_root: str) -> HealthReport:
    """status 命令主函数，生成文档健康度报告。

    Phase 3 增强版流程：
    1. 验证参数和 .docs/ 目录
    2. 调用 doc-code-lens（mode=full）检查文档一致性
    3. 调用 git-changelog 获取协作知识（失败时优雅降级）
    4. 计算同步率
    5. 汇总贡献者、过期文档、待处理 drift
    6. 返回 HealthReport

    Args:
        project_root: 项目根目录绝对路径

    Returns:
        HealthReport 健康度报告

    Raises:
        ValueError: 当 project_root 不存在或 .docs/ 目录不存在时
    """
    if not project_root or not project_root.strip():
        raise ValueError("参数错误：project_root 为必填项，不能为空")

    if not os.path.isdir(project_root):
        raise ValueError(f"路径不存在或不是目录：{project_root}")

    docs_dir = os.path.join(project_root, ".docs")
    if not os.path.isdir(docs_dir):
        raise ValueError(f".docs/ 目录不存在，请先执行 init 命令：{docs_dir}")

    # 1. 调用 doc-code-lens（mode=full）
    lens_input = DocCodeLensInput(
        project_root=project_root,
        mode="full",
    )
    lens_output = run_doc_code_lens(lens_input)

    summary = lens_output.summary
    total_checked = summary.total_checked
    in_sync = summary.in_sync
    drifted = summary.drifted

    # 计算同步率
    if total_checked == 0:
        sync_rate = 1.0
    else:
        sync_rate = in_sync / total_checked

    # 确保 sync_rate 在 [0, 1] 范围内
    sync_rate = max(0.0, min(1.0, sync_rate))

    # 汇总待处理 drift 项
    pending_drifts: list[ForwardDrift | ReverseDrift] = []
    pending_drifts.extend(lens_output.forward_drift)
    pending_drifts.extend(lens_output.reverse_drift)

    # 2. 调用 git-changelog（失败时优雅降级）
    active_contributors: list[Contributor] = []
    stale_docs: list[StaleFile] = []
    git_available = False
    git_error = ""

    try:
        git_input = GitChangelogInput(
            project_root=project_root,
            since="30 days ago",
            until="now",
            top_n=10,
        )
        git_output = run_git_changelog(git_input)
        git_available = True
        active_contributors = git_output.contributors
        stale_docs = _filter_stale_docs(git_output.stale_files)
    except (RuntimeError, OSError) as e:
        git_error = str(e)

    return HealthReport(
        sync_rate=sync_rate,
        total_checked=total_checked,
        in_sync=in_sync,
        drifted=drifted,
        active_contributors=active_contributors,
        stale_docs=stale_docs,
        pending_drifts=pending_drifts,
        git_available=git_available,
        git_error=git_error,
    )
