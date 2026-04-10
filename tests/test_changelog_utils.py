"""Tests for changelog_utils module — Changelog 追加逻辑。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from chiwen_mcp.changelog_utils import (
    append_changelog,
    format_changelog_entry,
    parse_changelog,
)
from chiwen_mcp.models import ChangelogEntry, ChangelogGroup


# ── parse_changelog ──


class TestParseChangelog:
    def test_parse_empty_content(self):
        doc = parse_changelog("")
        assert doc.groups == []

    def test_parse_header_only(self):
        content = "# 项目 文档变更日志\n\n> 本文件由 AI 自动维护，不建议手动编辑\n"
        doc = parse_changelog(content)
        assert doc.groups == []
        assert any("文档变更日志" in line for line in doc.header_lines)

    def test_parse_single_group(self):
        content = (
            "# proj 文档变更日志\n\n"
            "> 本文件由 AI 自动维护\n\n"
            "## 2025-01-15\n\n"
            "| 变更类型 | 文档 | 摘要 |\n"
            "|:--|:--|:--|\n"
            "| [初始化] | 全部文档 | 由 init 命令自动生成文档骨架 |\n"
        )
        doc = parse_changelog(content)
        assert len(doc.groups) == 1
        assert doc.groups[0].date == "2025-01-15"
        assert len(doc.groups[0].changes) == 1
        assert doc.groups[0].changes[0].change_type == "初始化"
        assert doc.groups[0].changes[0].target_doc == "全部文档"

    def test_parse_multiple_groups(self):
        content = (
            "# proj 文档变更日志\n\n"
            "## 2025-01-20\n\n"
            "| 变更类型 | 文档 | 摘要 |\n"
            "|:--|:--|:--|\n"
            "| [能力同步] | 2_CAPABILITIES.md | 新增 auth 能力 |\n"
            "\n"
            "## 2025-01-15\n\n"
            "| 变更类型 | 文档 | 摘要 |\n"
            "|:--|:--|:--|\n"
            "| [初始化] | 全部文档 | 由 init 命令自动生成 |\n"
        )
        doc = parse_changelog(content)
        assert len(doc.groups) == 2
        assert doc.groups[0].date == "2025-01-20"
        assert doc.groups[1].date == "2025-01-15"

    def test_parse_multiple_entries_in_group(self):
        content = (
            "# proj\n\n"
            "## 2025-01-20\n\n"
            "| 变更类型 | 文档 | 摘要 |\n"
            "|:--|:--|:--|\n"
            "| [能力同步] | 2_CAPABILITIES.md | 新增 auth 能力 |\n"
            "| [架构更新] | 1_ARCHITECTURE.md | 新增适配层说明 |\n"
        )
        doc = parse_changelog(content)
        assert len(doc.groups) == 1
        assert len(doc.groups[0].changes) == 2
        assert doc.groups[0].changes[0].change_type == "能力同步"
        assert doc.groups[0].changes[1].change_type == "架构更新"

    def test_preserves_header_lines(self):
        content = (
            "# my-project 文档变更日志\n"
            "\n"
            "> 本文件由 AI 自动维护，不建议手动编辑\n"
            "\n"
            "## 2025-01-15\n\n"
            "| 变更类型 | 文档 | 摘要 |\n"
            "|:--|:--|:--|\n"
            "| [初始化] | 全部文档 | init |\n"
        )
        doc = parse_changelog(content)
        header_text = "\n".join(doc.header_lines)
        assert "my-project 文档变更日志" in header_text
        assert "不建议手动编辑" in header_text


# ── format_changelog_entry ──


class TestFormatChangelogEntry:
    def test_basic_format(self):
        entry = ChangelogEntry(
            date="2025-01-15",
            change_type="能力同步",
            target_doc="2_CAPABILITIES.md",
            summary="新增 XX 能力打勾",
        )
        result = format_changelog_entry(entry)
        assert result == "| [能力同步] | 2_CAPABILITIES.md | 新增 XX 能力打勾 |"

    def test_different_types(self):
        entry = ChangelogEntry(
            date="2025-01-15",
            change_type="架构更新",
            target_doc="1_ARCHITECTURE.md",
            summary="新增适配层说明",
        )
        result = format_changelog_entry(entry)
        assert "[架构更新]" in result
        assert "1_ARCHITECTURE.md" in result

    def test_adr_entry(self):
        entry = ChangelogEntry(
            date="2025-01-15",
            change_type="ADR新增",
            target_doc="4_DECISIONS.md",
            summary="ADR-007：引入缓存层",
        )
        result = format_changelog_entry(entry)
        assert "[ADR新增]" in result
        assert "ADR-007" in result


# ── append_changelog ──


class TestAppendChangelog:
    def test_append_to_existing_file(self, tmp_path: Path):
        changelog = tmp_path / "5_CHANGELOG.md"
        changelog.write_text(
            "# proj 文档变更日志\n\n"
            "> 本文件由 AI 自动维护，不建议手动编辑\n\n"
            "## 2025-01-15\n\n"
            "| 变更类型 | 文档 | 摘要 |\n"
            "|:--|:--|:--|\n"
            "| [初始化] | 全部文档 | 由 init 命令自动生成文档骨架 |\n",
            encoding="utf-8",
        )

        entries = [
            ChangelogEntry(
                date="2025-01-20",
                change_type="能力同步",
                target_doc="2_CAPABILITIES.md",
                summary="新增 auth 能力打勾",
            ),
        ]

        result = append_changelog(str(changelog), entries)

        # 原有内容保留
        assert "初始化" in result
        assert "全部文档" in result
        assert "2025-01-15" in result

        # 新记录存在
        assert "2025-01-20" in result
        assert "[能力同步]" in result
        assert "新增 auth 能力打勾" in result

    def test_append_to_same_date_group(self, tmp_path: Path):
        changelog = tmp_path / "5_CHANGELOG.md"
        changelog.write_text(
            "# proj 文档变更日志\n\n"
            "## 2025-01-15\n\n"
            "| 变更类型 | 文档 | 摘要 |\n"
            "|:--|:--|:--|\n"
            "| [初始化] | 全部文档 | init |\n",
            encoding="utf-8",
        )

        entries = [
            ChangelogEntry(
                date="2025-01-15",
                change_type="能力同步",
                target_doc="2_CAPABILITIES.md",
                summary="新增能力",
            ),
        ]

        result = append_changelog(str(changelog), entries)

        # 同一日期分组下应有两条记录
        assert result.count("2025-01-15") == 1  # 只有一个日期标题
        assert "[初始化]" in result
        assert "[能力同步]" in result

    def test_new_date_group_appears_before_old(self, tmp_path: Path):
        changelog = tmp_path / "5_CHANGELOG.md"
        changelog.write_text(
            "# proj\n\n"
            "## 2025-01-10\n\n"
            "| 变更类型 | 文档 | 摘要 |\n"
            "|:--|:--|:--|\n"
            "| [初始化] | 全部文档 | init |\n",
            encoding="utf-8",
        )

        entries = [
            ChangelogEntry(
                date="2025-01-20",
                change_type="能力同步",
                target_doc="2_CAPABILITIES.md",
                summary="新增能力",
            ),
        ]

        result = append_changelog(str(changelog), entries)

        # 新日期应在旧日期之前
        pos_new = result.index("2025-01-20")
        pos_old = result.index("2025-01-10")
        assert pos_new < pos_old

    def test_preserves_manual_edits_in_header(self, tmp_path: Path):
        changelog = tmp_path / "5_CHANGELOG.md"
        original = (
            "# proj 文档变更日志\n\n"
            "> 本文件由 AI 自动维护，不建议手动编辑\n"
            "> 这是手动添加的注释行\n\n"
            "## 2025-01-15\n\n"
            "| 变更类型 | 文档 | 摘要 |\n"
            "|:--|:--|:--|\n"
            "| [初始化] | 全部文档 | init |\n"
        )
        changelog.write_text(original, encoding="utf-8")

        entries = [
            ChangelogEntry(
                date="2025-01-20",
                change_type="能力同步",
                target_doc="2_CAPABILITIES.md",
                summary="新增能力",
            ),
        ]

        result = append_changelog(str(changelog), entries)

        # 手动编辑的注释行应保留
        assert "这是手动添加的注释行" in result

    def test_empty_entries_returns_existing(self, tmp_path: Path):
        changelog = tmp_path / "5_CHANGELOG.md"
        original = "# proj\n\n## 2025-01-15\n"
        changelog.write_text(original, encoding="utf-8")

        result = append_changelog(str(changelog), [])
        assert result == original

    def test_nonexistent_file_with_entries(self, tmp_path: Path):
        changelog = tmp_path / "5_CHANGELOG.md"

        entries = [
            ChangelogEntry(
                date="2025-01-20",
                change_type="能力同步",
                target_doc="2_CAPABILITIES.md",
                summary="新增能力",
            ),
        ]

        result = append_changelog(str(changelog), entries)

        assert "2025-01-20" in result
        assert "[能力同步]" in result
        assert changelog.exists()

    def test_multiple_entries_different_dates(self, tmp_path: Path):
        changelog = tmp_path / "5_CHANGELOG.md"
        changelog.write_text(
            "# proj\n\n"
            "## 2025-01-10\n\n"
            "| 变更类型 | 文档 | 摘要 |\n"
            "|:--|:--|:--|\n"
            "| [初始化] | 全部文档 | init |\n",
            encoding="utf-8",
        )

        entries = [
            ChangelogEntry(
                date="2025-01-20",
                change_type="能力同步",
                target_doc="2_CAPABILITIES.md",
                summary="新增能力",
            ),
            ChangelogEntry(
                date="2025-01-18",
                change_type="架构更新",
                target_doc="1_ARCHITECTURE.md",
                summary="更新模块",
            ),
        ]

        result = append_changelog(str(changelog), entries)

        # 所有日期都应存在
        assert "2025-01-20" in result
        assert "2025-01-18" in result
        assert "2025-01-10" in result

        # 新日期在旧日期之前
        assert result.index("2025-01-20") < result.index("2025-01-18")
        assert result.index("2025-01-18") < result.index("2025-01-10")

    def test_file_written_correctly(self, tmp_path: Path):
        changelog = tmp_path / "5_CHANGELOG.md"
        changelog.write_text(
            "# proj\n\n"
            "## 2025-01-10\n\n"
            "| 变更类型 | 文档 | 摘要 |\n"
            "|:--|:--|:--|\n"
            "| [初始化] | 全部文档 | init |\n",
            encoding="utf-8",
        )

        entries = [
            ChangelogEntry(
                date="2025-01-20",
                change_type="能力同步",
                target_doc="2_CAPABILITIES.md",
                summary="新增能力",
            ),
        ]

        append_changelog(str(changelog), entries)

        # 验证文件内容与返回值一致
        written = changelog.read_text(encoding="utf-8")
        assert "[能力同步]" in written
        assert "[初始化]" in written
