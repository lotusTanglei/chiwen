"""chiwen Knowledge Kit - sync 命令逻辑

实现 sync 命令的 Python 代码逻辑：
- 调用 doc-code-lens（full 模式）检查文档与代码双向一致性
- 对 forward drift 项生成修复内容
- 对 reverse drift 项自动追加到能力矩阵
- 实现能力矩阵同步规则
- 更新文档后自动追加 5_CHANGELOG.md
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date

from .changelog_utils import append_changelog
from .collaboration import (
    acquire_docs_lock,
    git_docs_dirty,
    git_head,
    is_git_repo,
    read_state,
    release_docs_lock,
    write_state,
)
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
    Module,
    ReverseDrift,
)


@dataclass
class SyncResult:
    """sync 命令的结果摘要。"""

    drift_count: int = 0
    fix_count: int = 0
    reverse_fix_count: int = 0
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
    modules_dir: str = "",
) -> tuple[str, list[str]]:
    """修复能力矩阵，返回更新后的内容和变更描述列表。

    能力矩阵同步规则：
    1. 新增可用能力 → 添加并标记 [x]（仅在无 modules/ 目录时执行）
    2. 移除的能力 → 标记 (废弃) 并保留记录
    3. 代码中不再存在的 [x] 能力 → 降级为 [ ] 并附 drift 说明
    4. 禁止出现虚假勾选

    当 modules_dir 存在时，内部 API 变更由模块文档处理，
    全局能力矩阵不追加裸函数名。

    Args:
        capabilities_path: 2_CAPABILITIES.md 文件路径
        forward_drifts: Forward Drift 列表（来自 doc-code-lens）
        code_capabilities: 代码中实际存在的能力名称集合
        modules_dir: .docs/modules/ 目录路径（存在时跳过新增能力追加）

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
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        checkbox_match = re.match(r"^(-\s+)\[([ xX])\]\s+(.+)$", stripped)
        if checkbox_match:
            prefix = checkbox_match.group(1)
            check = checkbox_match.group(2)
            name = checkbox_match.group(3).strip()

            if name in seen:
                continue
            seen.add(name)

            if check.lower() == "x" and name in drift_claims:
                # 降级为 [ ] 并附 drift 说明
                new_line = f"{prefix}[ ] {name} <!-- drift: 代码中未找到对应实现 -->"
                new_lines.append(new_line)
                changes.append(f"降级: '{name}' [x] → [ ]（代码中未找到实现）")
                continue

        new_lines.append(line)

    content = "\n".join(new_lines)

    # 规则 1：新增可用能力 → 添加并标记 [x]
    # 当 modules/ 目录存在时，内部 API 由模块文档管理，不追加到全局能力矩阵
    has_modules = modules_dir and os.path.isdir(modules_dir)
    if not has_modules:
        new_capabilities = code_capabilities - existing_names
        if new_capabilities:
            additions: list[str] = []
            for cap_name in sorted(new_capabilities):
                additions.append(f"- [x] {cap_name}")
                changes.append(f"新增: '{cap_name}' 标记为 [x]")

            if additions:
                addition_block = "\n## 新增能力\n\n" + "\n".join(additions)
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


def _append_to_module_api_table(mod_doc_path: str, content: str, api_name: str) -> None:
    """将新 API 追加到模块文档的公开 API 表格末尾。"""
    lines = content.splitlines()
    insert_pos = -1
    in_api_section = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^##\s+公开\s*API", stripped):
            in_api_section = True
            continue
        if in_api_section and re.match(r"^##\s+", stripped) and "公开" not in stripped:
            insert_pos = i
            break
        if in_api_section and stripped.startswith("|") and "---" not in stripped and "函数" not in stripped:
            insert_pos = i + 1

    if insert_pos == -1:
        insert_pos = len(lines)

    new_row = f"| `{api_name}` | （待补充说明） |"
    lines.insert(insert_pos, new_row)

    with open(mod_doc_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        if not lines[-1].endswith("\n"):
            f.write("\n")


def apply_reverse_fixes(
    capabilities_path: str,
    reverse_drifts: list[ReverseDrift],
    code_modules: list[Module],
    modules_dir: str = "",
) -> tuple[str, list[str]]:
    """将 reverse drift 项追加到能力矩阵和模块文档。

    规则：
    1. 如果 modules_dir 存在且对应模块文档存在，将 API 追加到模块文档的公开 API 表格
    2. 否则追加到 2_CAPABILITIES.md 的对应模块分组
    3. 无法匹配模块时追加到「未分类」分组
    4. 保留已有内容不被修改

    Args:
        capabilities_path: 2_CAPABILITIES.md 文件路径
        reverse_drifts: ReverseDrift 列表
        code_modules: code-reader 扫描到的模块列表
        modules_dir: .docs/modules/ 目录路径（为空则回退到全局模式）

    Returns:
        (更新后的文件内容, 变更描述列表)
    """
    if not reverse_drifts:
        # 无 reverse drift 项，读取原内容原样返回
        if os.path.isfile(capabilities_path):
            with open(capabilities_path, encoding="utf-8") as f:
                return f.read(), []
        return "## 未分类\n", []

    # 如果 modules/ 目录存在，优先将 API 追加到模块文档
    module_doc_handled: set[str] = set()  # 已在模块文档中处理的 API 名称
    changes: list[str] = []

    if modules_dir and os.path.isdir(modules_dir):
        for drift in reverse_drifts:
            # 从 drift.file 推断模块文档文件名
            # drift.file 格式如 "src/chiwen_mcp"，源文件名需要从 drift.location 提取
            # 或者直接用 drift.capability 在模块文档中查找
            # 简单策略：遍历 modules/*.md，找到包含该模块路径的文档
            for fname in os.listdir(modules_dir):
                if not fname.endswith(".md"):
                    continue
                mod_doc_path = os.path.join(modules_dir, fname)
                with open(mod_doc_path, encoding="utf-8") as f:
                    mod_content = f.read()

                # 检查该模块文档是否已包含此 API
                if drift.capability in mod_content:
                    module_doc_handled.add(drift.capability)
                    break

                # 检查源文件路径是否匹配
                stem = fname[:-3]  # 去掉 .md
                if stem in drift.file or drift.file.endswith(f"/{stem}.py"):
                    # 追加到该模块文档的公开 API 表格
                    _append_to_module_api_table(mod_doc_path, mod_content, drift.capability)
                    module_doc_handled.add(drift.capability)
                    changes.append(f"追加到模块文档 modules/{fname}: {drift.capability}")
                    break

    # 过滤掉已在模块文档中处理的 drift 项
    remaining_drifts = [d for d in reverse_drifts if d.capability not in module_doc_handled]

    if not remaining_drifts:
        if os.path.isfile(capabilities_path):
            with open(capabilities_path, encoding="utf-8") as f:
                return f.read(), changes
        return "## 未分类\n", changes

    # 读取现有内容
    if os.path.isfile(capabilities_path):
        with open(capabilities_path, encoding="utf-8") as f:
            content = f.read()
    else:
        content = "## 未分类\n"

    # 构建 file_path → module_name 映射
    file_to_module: dict[str, str] = {}
    for mod in code_modules:
        file_to_module[mod.path] = mod.name

    # 解析现有内容中的 ## 分组名称，收集已有能力名称（避免重复追加）
    existing_capabilities: set[str] = set()
    for line in content.splitlines():
        stripped = line.strip()
        checkbox_match = re.match(r"^-\s+\[[ xX]\]\s+(.+)$", stripped)
        if checkbox_match:
            existing_capabilities.add(checkbox_match.group(1).strip())
        deprecated_match = re.match(r"^-\s+\(废弃\)\s+(.+)$", stripped)
        if deprecated_match:
            existing_capabilities.add(deprecated_match.group(1).strip())
        planned_match = re.match(r"^-\s+\(规划中\)\s+(.+)$", stripped)
        if planned_match:
            existing_capabilities.add(planned_match.group(1).strip())

    # 将 reverse drift 按目标模块分组
    module_additions: dict[str, list[str]] = {}  # module_name → [capability_name, ...]
    uncategorized: list[str] = []

    for drift in remaining_drifts:
        cap_name = drift.capability
        # 跳过已存在的能力
        if cap_name in existing_capabilities:
            continue

        # 根据 file 字段匹配模块
        matched_module = file_to_module.get(drift.file)

        # 如果精确匹配失败，尝试前缀匹配
        if not matched_module:
            for mod_path, mod_name in file_to_module.items():
                if drift.file.startswith(mod_path) or mod_path.startswith(drift.file):
                    matched_module = mod_name
                    break

        if matched_module:
            module_additions.setdefault(matched_module, []).append(cap_name)
        else:
            uncategorized.append(cap_name)

    # 如果没有需要追加的内容，直接返回
    if not module_additions and not uncategorized:
        return content, []

    changes: list[str] = []
    lines = content.splitlines()

    # 解析文档结构：找到每个 ## 分组的范围
    # section_map: module_name → (section_header_index, section_end_index)
    sections: list[tuple[str, int]] = []  # (section_name, header_line_index)
    for i, line in enumerate(lines):
        stripped = line.strip()
        section_match = re.match(r"^##\s+(.+)$", stripped)
        if section_match:
            sections.append((section_match.group(1).strip(), i))

    # 为每个模块分组找到插入位置（分组最后一个 - [ ] 或 - [x] 条目之后）
    def find_insert_position(section_name: str) -> int:
        """找到指定分组的插入位置（分组末尾最后一个条目之后）。

        Returns:
            插入行索引，-1 表示未找到该分组
        """
        section_idx = -1
        for idx, (name, line_idx) in enumerate(sections):
            if name == section_name:
                section_idx = idx
                break

        if section_idx == -1:
            return -1

        start = sections[section_idx][1]
        # 确定分组结束位置
        if section_idx + 1 < len(sections):
            end = sections[section_idx + 1][1]
        else:
            end = len(lines)

        # 从分组末尾向前找最后一个列表条目
        last_item_pos = start  # 默认在标题行之后
        for i in range(start + 1, end):
            stripped = lines[i].strip()
            if stripped.startswith("- "):
                last_item_pos = i

        # 如果没有找到列表条目，插入在标题行之后
        if last_item_pos == start:
            return start + 1
        return last_item_pos + 1

    # 收集所有插入操作：(line_index, [new_lines])
    # 使用倒序插入避免索引偏移
    insertions: list[tuple[int, list[str]]] = []

    for module_name in sorted(module_additions.keys()):
        cap_names = sorted(set(module_additions[module_name]))
        pos = find_insert_position(module_name)
        if pos == -1:
            # 分组不存在，归入未分类
            uncategorized.extend(cap_names)
            continue
        new_lines = []
        for cap in cap_names:
            new_lines.append(f"- [ ] {cap}")
            changes.append(f"追加到「{module_name}」: {cap}")
        insertions.append((pos, new_lines))

    # 处理未分类项
    if uncategorized:
        uncategorized = sorted(set(uncategorized))
        pos = find_insert_position("未分类")
        new_lines = []
        for cap in uncategorized:
            new_lines.append(f"- [ ] {cap}")
            changes.append(f"追加到「未分类」: {cap}")

        if pos == -1:
            # 「未分类」分组不存在，在文件末尾创建
            tail_lines = ["\n## 未分类\n"]
            tail_lines.extend(new_lines)
            insertions.append((len(lines), tail_lines))
        else:
            insertions.append((pos, new_lines))

    # 按插入位置倒序排列，从后往前插入
    insertions.sort(key=lambda x: x[0], reverse=True)
    for pos, new_lines in insertions:
        for i, new_line in enumerate(new_lines):
            lines.insert(pos + i, new_line)

    updated_content = "\n".join(lines)
    # 确保文件以换行符结尾
    if updated_content and not updated_content.endswith("\n"):
        updated_content += "\n"

    seen: set[str] = set()
    deduped_lines: list[str] = []
    for line in updated_content.splitlines():
        stripped = line.strip()
        m = re.match(r"^-\s+\[[ xX]\]\s+(.+)$", stripped)
        if not m:
            deduped_lines.append(line)
            continue
        name = m.group(1).strip()
        if name in seen:
            continue
        seen.add(name)
        deduped_lines.append(line)
    updated_content = "\n".join(deduped_lines)
    if updated_content and not updated_content.endswith("\n"):
        updated_content += "\n"

    with open(capabilities_path, "w", encoding="utf-8") as f:
        f.write(updated_content)

    return updated_content, changes


def sync_docs(
    project_root: str,
    allow_dirty: bool = False,
    allow_risky: bool = False,
    lock_ttl_seconds: int = 600,
) -> SyncResult:
    """sync 命令主函数，执行完整 sync 流程。

    流程：
    1. 检查 .docs/ 是否存在
    2. 调用 doc-code-lens（full 模式）检查双向一致性
    3. 如果有 forward drift 项，生成修复内容并执行能力矩阵修复
    4. 如果有 reverse drift 项，自动追加到能力矩阵
    5. 追加 5_CHANGELOG.md（包含 forward 和 reverse drift 修复记录）
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

    if is_git_repo(project_root) and not allow_dirty and git_docs_dirty(project_root):
        raise ValueError("检测到 .docs/ 存在未提交变更，请先提交/暂存，或传 allow_dirty=true 继续")

    state = read_state(docs_dir)
    if state is not None:
        last_head = ""
        try:
            last_head = str(state.get("git", {}).get("head", ""))
        except Exception:
            last_head = ""

        if (
            last_head
            and is_git_repo(project_root)
            and git_head(project_root) != last_head
            and not allow_risky
        ):
            raise ValueError(
                "检测到当前 Git HEAD 与上次 sync/init 记录不一致，"
                "可能存在跨分支覆盖风险，请传 allow_risky=true 继续"
            )

    lock = acquire_docs_lock(docs_dir, ttl_seconds=lock_ttl_seconds)
    modified_files: list[str] = []
    try:
        lens_input = DocCodeLensInput(
            project_root=project_root,
            mode="full",
        )
        lens_output = run_doc_code_lens(lens_input)

        result.drift_count = lens_output.summary.drifted

        if result.drift_count == 0:
            result.details.append("文档与代码一致，无需更新")
            return result

        fixes: list[FixContent] = []
        for drift in lens_output.forward_drift:
            fix = generate_fix_content(drift)
            fixes.append(fix)

        cr_input = CodeReaderInput(project_root=project_root)
        cr_output = scan_project(cr_input)

        code_capabilities: set[str] = set()
        for module in cr_output.modules:
            for api in module.public_api:
                code_capabilities.add(api)

        capabilities_path = os.path.join(docs_dir, "2_CAPABILITIES.md")
        modules_dir = os.path.join(docs_dir, "modules")
        if os.path.isfile(capabilities_path):
            _, cap_changes = apply_capability_fixes(
                capabilities_path,
                lens_output.forward_drift,
                code_capabilities,
                modules_dir=modules_dir,
            )
            result.fix_count += len(cap_changes)
            result.details.extend(cap_changes)
            if cap_changes:
                modified_files.append("2_CAPABILITIES.md")

        if lens_output.reverse_drift:
            _, reverse_changes = apply_reverse_fixes(
                capabilities_path,
                lens_output.reverse_drift,
                cr_output.modules,
                modules_dir=modules_dir,
            )
            result.reverse_fix_count = len(reverse_changes)
            result.details.extend(reverse_changes)
            if reverse_changes and "2_CAPABILITIES.md" not in modified_files:
                modified_files.append("2_CAPABILITIES.md")

        changelog_path = os.path.join(docs_dir, "5_CHANGELOG.md")
        today = date.today().isoformat()

        changelog_entries: list[ChangelogEntry] = []
        if result.fix_count > 0:
            changelog_entries.append(
                ChangelogEntry(
                    date=today,
                    change_type="能力同步",
                    target_doc="2_CAPABILITIES.md",
                    summary=f"sync 修复 {result.fix_count} 项能力矩阵 drift",
                )
            )

        if result.drift_count > 0:
            changelog_entries.append(
                ChangelogEntry(
                    date=today,
                    change_type="drift 检测",
                    target_doc="多个文档",
                    summary=f"检测到 {result.drift_count} 项 drift，已处理 {result.fix_count} 项",
                )
            )

        if result.reverse_fix_count > 0:
            changelog_entries.append(
                ChangelogEntry(
                    date=today,
                    change_type="reverse drift 修复",
                    target_doc="2_CAPABILITIES.md",
                    summary=f"自动追加 {result.reverse_fix_count} 项未记录的代码能力到能力矩阵",
                )
            )

        if changelog_entries:
            append_changelog(changelog_path, changelog_entries)
            result.changelog_updated = True
            result.details.append(
                f"已追加 {len(changelog_entries)} 条变更记录到 5_CHANGELOG.md"
            )
            modified_files.append("5_CHANGELOG.md")

        write_state(
            docs_dir,
            {
                "tool": "sync",
                "generated_at": date.today().isoformat(),
                "project_root": project_root,
                "lock": lock.to_dict(),
                "allow_dirty": allow_dirty,
                "allow_risky": allow_risky,
                "files": modified_files,
                "git": {
                    "available": is_git_repo(project_root),
                    "head": git_head(project_root) if is_git_repo(project_root) else "",
                },
            },
        )

        return result
    finally:
        release_docs_lock(docs_dir)
