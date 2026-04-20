"""chiwen Knowledge Kit - Changelog 追加工具

实现 5_CHANGELOG.md 的解析和追加逻辑。
追加前读取并验证现有内容格式，保留手动编辑内容。
新记录按日期分组追加，每条包含变更类型、目标文档、变更摘要。
"""

from __future__ import annotations

import re

from .models import ChangelogDoc, ChangelogEntry, ChangelogGroup

# 日期分组标题的正则：## YYYY-MM-DD
_DATE_HEADING_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$")

# 表格行的正则：| [类型] | 文档 | 摘要 |
_TABLE_ROW_RE = re.compile(
    r"^\|\s*\[([^\]]+)\]\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|$"
)

# 表格头和分隔行
_TABLE_HEADER = "| 变更类型 | 文档 | 摘要 |"
_TABLE_SEPARATOR = "|:--|:--|:--|"


def parse_changelog(content: str) -> ChangelogDoc:
    """解析现有 5_CHANGELOG.md 内容。

    解析规则：
    - 以 `#` 开头的一级标题行和紧随的提示行归入 header_lines
    - 以 `## YYYY-MM-DD` 开头的行标记一个日期分组
    - 日期分组内的表格数据行解析为 ChangelogEntry
    - 非表格内容（手动编辑的文字等）也保留在原始结构中

    Args:
        content: 5_CHANGELOG.md 的完整文本内容

    Returns:
        解析后的 ChangelogDoc 对象
    """
    doc = ChangelogDoc()
    lines = content.split("\n")

    group_map: dict[str, ChangelogGroup] = {}
    group_order: list[str] = []
    current_group: ChangelogGroup | None = None
    in_header = True  # 在遇到第一个日期分组前，都算 header

    for line in lines:
        date_match = _DATE_HEADING_RE.match(line)

        if date_match:
            in_header = False
            date_str = date_match.group(1)
            if date_str not in group_map:
                group_map[date_str] = ChangelogGroup(date=date_str)
                group_order.append(date_str)
            current_group = group_map[date_str]
            continue

        if in_header:
            doc.header_lines.append(line)
            continue

        # 在日期分组内，尝试解析表格数据行
        if current_group is not None:
            row_match = _TABLE_ROW_RE.match(line.strip())
            if row_match:
                entry = ChangelogEntry(
                    date=current_group.date,
                    change_type=row_match.group(1).strip(),
                    target_doc=row_match.group(2).strip(),
                    summary=row_match.group(3).strip(),
                )
                current_group.changes.append(entry)

    doc.groups = [group_map[d] for d in group_order]

    return doc


def format_changelog_entry(entry: ChangelogEntry) -> str:
    """格式化单条变更记录为表格行。

    Args:
        entry: 变更日志条目

    Returns:
        格式化的 Markdown 表格行，如 `| [能力同步] | 2_CAPABILITIES.md | 新增 XX 能力打勾 |`
    """
    return f"| [{entry.change_type}] | {entry.target_doc} | {entry.summary} |"


def append_changelog(changelog_path: str, entries: list[ChangelogEntry]) -> str:
    """追加新记录到 5_CHANGELOG.md。

    追加规则：
    - 保留已有内容不被修改
    - 新记录按日期分组追加
    - 如果当天已有分组，追加到该分组的表格末尾
    - 如果当天没有分组，在已有分组之前创建新的日期分组

    Args:
        changelog_path: 5_CHANGELOG.md 文件路径
        entries: 要追加的变更记录列表

    Returns:
        追加后的完整文件内容
    """
    if not entries:
        # 无新记录，读取并原样返回
        try:
            with open(changelog_path, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    # 读取现有内容
    existing_content = ""
    try:
        with open(changelog_path, encoding="utf-8") as f:
            existing_content = f.read()
    except FileNotFoundError:
        pass

    # 解析现有内容
    doc = parse_changelog(existing_content)

    # 按日期分组新记录
    new_groups: dict[str, list[ChangelogEntry]] = {}
    for entry in entries:
        new_groups.setdefault(entry.date, []).append(entry)

    # 合并：对每个日期，如果已有分组则追加，否则创建新分组
    existing_dates = {g.date: g for g in doc.groups}

    new_date_groups: list[ChangelogGroup] = []
    for date, date_entries in sorted(new_groups.items(), reverse=True):
        if date in existing_dates:
            # 追加到已有分组
            existing_keys = {
                (c.change_type, c.target_doc, c.summary)
                for c in existing_dates[date].changes
            }
            to_add = [
                e
                for e in date_entries
                if (e.change_type, e.target_doc, e.summary) not in existing_keys
            ]
            to_add.sort(key=lambda e: (e.change_type, e.target_doc, e.summary))
            existing_dates[date].changes.extend(to_add)
        else:
            # 创建新分组
            unique: dict[tuple[str, str, str], ChangelogEntry] = {}
            for e in date_entries:
                unique[(e.change_type, e.target_doc, e.summary)] = e
            sorted_entries = sorted(
                unique.values(), key=lambda e: (e.change_type, e.target_doc, e.summary)
            )
            group = ChangelogGroup(date=date, changes=sorted_entries)
            new_date_groups.append(group)

    # 新日期分组插入到最前面（最新日期在前）
    if new_date_groups:
        doc.groups = new_date_groups + doc.groups

    # 重新生成文件内容
    result = _render_changelog_doc(doc)

    # 写入文件
    with open(changelog_path, "w", encoding="utf-8") as f:
        f.write(result)

    return result


def _render_changelog_doc(doc: ChangelogDoc) -> str:
    """将 ChangelogDoc 渲染为 Markdown 文本。

    Args:
        doc: Changelog 文档模型

    Returns:
        完整的 Markdown 文本
    """
    parts: list[str] = []

    # 渲染 header
    if doc.header_lines:
        parts.append("\n".join(doc.header_lines))

    # 渲染每个日期分组
    for group in doc.groups:
        parts.append(f"## {group.date}")
        parts.append("")
        parts.append(_TABLE_HEADER)
        parts.append(_TABLE_SEPARATOR)
        for entry in group.changes:
            parts.append(format_changelog_entry(entry))
        parts.append("")

    result = "\n".join(parts)
    # 确保文件以换行结尾
    if result and not result.endswith("\n"):
        result += "\n"
    return result
