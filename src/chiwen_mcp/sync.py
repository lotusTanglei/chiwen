"""chiwen Knowledge Kit - sync 命令逻辑

实现 sync 命令的 Python 代码逻辑：
- 调用 doc-code-lens（forward 模式）检查文档与代码一致性
- 对 drift 项生成修复内容
- 实现能力矩阵同步规则
- 更新文档后自动追加 5_CHANGELOG.md
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date

from .changelog_utils import append_changelog
from .code_reader import CodeReaderInput, scan_project
from .doc_code_lens import (
    DocClaim,
    check_forward_drift,
    parse_capabilities,
    run_doc_code_lens,
)
from .models import (
    ChangelogEntry,
    Confidence,
    DocCodeLensInput,
    DocCodeLensOutput,
    DriftType,
    ForwardDrift,
)


@dataclass
class SyncResult:
    """sync 命令的结果摘要。"""

    drift_count: int = 0
    fix_count: int = 0
    changelog_updated: bool = False
    details: list[str] = field(default_factory=list)


@dataclass
class FixContent:
    """单个 drift 项的修复内容。"""

    drift: ForwardDrift
    fix_description: str = ""
    target_file: str = ""
    action: str = ""  # "downgrade" | "deprecate" | "add" | "update"


def generate_fix_content(drift: ForwardDrift) -> FixContent:
    """为单个 drift 项生成修复内容。

    根据 drift 类型和置信度决定修复策略：
    - MISSING + HIGH confidence → 降级 [x] 为 [ ] 并附 drift 说明
    - MISSING + MEDIUM/LOW → 建议人工确认
    - PARTIAL → 更新文档描述

    Args:
        drift: ForwardDrift 项

    Returns:
        FixContent 修复内容
    """
    fix = FixContent(drift=drift, target_file=drift.doc_file)

    if drift.drift_type == DriftType.MISSING:
        if drift.confidence == Confidence.HIGH:
            fix.action = "downgrade"
            fix.fix_description = (
                f"将 '{drift.doc_claim}' 从 [x] 降级为 [ ]，"
                f"原因：代码中未找到对应实现"
            )
        else:
            fix.action = "update"
            fix.fix_description = (
                f"'{drift.doc_claim}' 可能在代码中不存在，建议人工确认"
            )
    elif drift.drift_type == DriftType.PARTIAL:
        fix.action = "update"
        fix.fix_description = (
            f"'{drift.doc_claim}' 在代码中仅部分匹配，建议更新文档描述"
        )
    else:
        fix.action = "update"
        fix.fix_description = f"'{drift.doc_claim}' 需要更新"

    return fix


def apply_capability_fixes(
    capabilities_path: str,
    forward_drifts: list[ForwardDrift],
    code_capabilities: set[str],
) -> tuple[str, list[str]]:
    """修复能力矩阵，返回更新后的内容和变更描述列表。

    能力矩阵同步规则：
    1. 新增可用能力 → 添加并标记 [x]
    2. 移除的能力 → 标记 (废弃) 并保留记录
    3. 代码中不再存在的 [x] 能力 → 降级为 [ ] 并附 drift 说明
    4. 禁止出现虚假勾选

    Args:
        capabilities_path: 2_CAPABILITIES.md 文件路径
        forward_drifts: Forward Drift 列表（来自 doc-code-lens）
        code_capabilities: 代码中实际存在的能力名称集合

    Returns:
        (更新后的文件内容, 变更描述列表) 元组
    """
    # 读取现有内容
    content = ""
    if os.path.isfile(capabilities_path):
        with open(capabilities_path, encoding="utf-8") as f:
            content = f.read()

    if not content:
        return content, []

    changes: list[str] = []

    # 解析现有能力声明
    existing_claims = parse_capabilities(content)

    # 构建 drift 项的 doc_claim 集合（MISSING 类型且 HIGH confidence）
    drift_claims: set[str] = set()
    for drift in forward_drifts:
        if (
            drift.drift_type == DriftType.MISSING
            and drift.confidence == Confidence.HIGH
            and drift.doc_file in ("2_CAPABILITIES.md", os.path.basename(capabilities_path))
        ):
            drift_claims.add(drift.doc_claim)

    # 构建已有能力名称集合（用于检测新增能力）
    existing_names: set[str] = set()
    for claim in existing_claims:
        existing_names.add(claim.name)

    # 规则 3：代码中不再存在的 [x] 能力 → 降级为 [ ] 并附 drift 说明
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        checkbox_match = re.match(r"^(-\s+)\[([ xX])\]\s+(.+)$", stripped)
        if checkbox_match:
            prefix = checkbox_match.group(1)
            check = checkbox_match.group(2)
            name = checkbox_match.group(3).strip()

            if check.lower() == "x" and name in drift_claims:
                # 降级为 [ ] 并附 drift 说明
                new_line = f"{prefix}[ ] {name} <!-- drift: 代码中未找到对应实现 -->"
                new_lines.append(new_line)
                changes.append(f"降级: '{name}' [x] → [ ]（代码中未找到实现）")
                continue

        new_lines.append(line)

    content = "\n".join(new_lines)

    # 规则 1：新增可用能力 → 添加并标记 [x]
    new_capabilities = code_capabilities - existing_names
    if new_capabilities:
        # 在文件末尾添加新能力（在最后一个模块分组下）
        additions: list[str] = []
        for cap_name in sorted(new_capabilities):
            additions.append(f"- [x] {cap_name}")
            changes.append(f"新增: '{cap_name}' 标记为 [x]")

        if additions:
            # 找到最后一个非空行的位置，在其后追加
            addition_block = "\n## 新增能力\n\n" + "\n".join(additions)
            # 确保内容末尾有换行
            if content and not content.endswith("\n"):
                content += "\n"
            content += addition_block + "\n"

    # 规则 2：检测已废弃的能力（在 existing 中标记为 [x] 但不在 code_capabilities 中，
    # 且不在 drift_claims 中 —— drift_claims 已经被规则 3 处理了）
    # 注意：这里只处理那些明确被"移除"的能力（即之前存在于代码中，现在不存在了）
    # 由于我们无法区分"从未实现"和"曾经实现后被移除"，
    # 规则 2 的触发依赖于 forward_drift 中的信息

    # 写入文件
    with open(capabilities_path, "w", encoding="utf-8") as f:
        f.write(content)

    return content, changes


def sync_docs(project_root: str) -> SyncResult:
    """sync 命令主函数，执行完整 sync 流程。

    流程：
    1. 检查 .docs/ 是否存在
    2. 调用 doc-code-lens（forward 模式）检查一致性
    3. 如果有 drift 项，生成修复内容
    4. 执行能力矩阵修复
    5. 追加 5_CHANGELOG.md
    6. 返回结果摘要

    Args:
        project_root: 项目根目录绝对路径

    Returns:
        SyncResult 结果摘要

    Raises:
        ValueError: 当 project_root 不存在或 .docs/ 目录不存在时
    """
    result = SyncResult()

    # 验证路径
    if not project_root or not project_root.strip():
        raise ValueError("参数错误：project_root 为必填项，不能为空")

    if not os.path.isdir(project_root):
        raise ValueError(f"路径不存在或不是目录：{project_root}")

    docs_dir = os.path.join(project_root, ".docs")
    if not os.path.isdir(docs_dir):
        raise ValueError(f".docs/ 目录不存在，请先执行 init 命令：{docs_dir}")

    # 步骤 1：调用 doc-code-lens（forward 模式）
    lens_input = DocCodeLensInput(
        project_root=project_root,
        mode="forward",
    )
    lens_output = run_doc_code_lens(lens_input)

    result.drift_count = lens_output.summary.drifted

    # 如果无 drift 项，直接返回
    if result.drift_count == 0:
        result.details.append("文档与代码一致，无需更新")
        return result

    # 步骤 2：为每个 drift 项生成修复内容
    fixes: list[FixContent] = []
    for drift in lens_output.forward_drift:
        fix = generate_fix_content(drift)
        fixes.append(fix)

    # 步骤 3：收集代码中实际存在的能力
    # 通过 code-reader 扫描获取代码能力
    cr_input = CodeReaderInput(project_root=project_root)
    cr_output = scan_project(cr_input)

    code_capabilities: set[str] = set()
    for module in cr_output.modules:
        for api in module.public_api:
            code_capabilities.add(api)

    # 步骤 4：执行能力矩阵修复
    capabilities_path = os.path.join(docs_dir, "2_CAPABILITIES.md")
    if os.path.isfile(capabilities_path):
        _, cap_changes = apply_capability_fixes(
            capabilities_path,
            lens_output.forward_drift,
            code_capabilities,
        )
        result.fix_count += len(cap_changes)
        result.details.extend(cap_changes)

    # 步骤 5：追加 5_CHANGELOG.md
    changelog_path = os.path.join(docs_dir, "5_CHANGELOG.md")
    today = date.today().isoformat()

    changelog_entries: list[ChangelogEntry] = []
    if result.fix_count > 0:
        changelog_entries.append(ChangelogEntry(
            date=today,
            change_type="能力同步",
            target_doc="2_CAPABILITIES.md",
            summary=f"sync 修复 {result.fix_count} 项能力矩阵 drift",
        ))

    if result.drift_count > 0:
        changelog_entries.append(ChangelogEntry(
            date=today,
            change_type="drift 检测",
            target_doc="多个文档",
            summary=f"检测到 {result.drift_count} 项 drift，已处理 {result.fix_count} 项",
        ))

    if changelog_entries:
        append_changelog(changelog_path, changelog_entries)
        result.changelog_updated = True
        result.details.append(
            f"已追加 {len(changelog_entries)} 条变更记录到 5_CHANGELOG.md"
        )

    return result
