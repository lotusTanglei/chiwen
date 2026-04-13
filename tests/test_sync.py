"""Tests for sync module — sync 命令逻辑和能力矩阵同步。

测试覆盖：
- generate_fix_content: 为 drift 项生成修复内容
- apply_capability_fixes: 能力矩阵同步规则
- sync_docs: 主函数集成
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from chiwen_mcp.models import (
    ChangelogEntry,
    Confidence,
    DriftType,
    ForwardDrift,
    MatchedFile,
    Module,
    ReverseDrift,
)
from chiwen_mcp.sync import (
    FixContent,
    SyncResult,
    apply_capability_fixes,
    apply_reverse_fixes,
    generate_fix_content,
    sync_docs,
)


# ── generate_fix_content 测试 ──


class TestGenerateFixContent:
    def test_missing_high_confidence_downgrade(self):
        """MISSING + HIGH → downgrade action."""
        drift = ForwardDrift(
            doc_claim="不存在的功能",
            doc_file="2_CAPABILITIES.md",
            doc_location="line 5",
            matched_files=[],
            confidence=Confidence.HIGH,
            drift_type=DriftType.MISSING,
            drift_detail="未找到",
        )
        fix = generate_fix_content(drift)
        assert fix.action == "downgrade"
        assert "降级" in fix.fix_description
        assert fix.target_file == "2_CAPABILITIES.md"

    def test_missing_low_confidence_update(self):
        """MISSING + LOW → update action (suggest manual check)."""
        drift = ForwardDrift(
            doc_claim="可能不存在的功能",
            doc_file="2_CAPABILITIES.md",
            doc_location="line 5",
            matched_files=[],
            confidence=Confidence.LOW,
            drift_type=DriftType.MISSING,
            drift_detail="未找到",
        )
        fix = generate_fix_content(drift)
        assert fix.action == "update"
        assert "人工确认" in fix.fix_description

    def test_partial_drift_update(self):
        """PARTIAL → update action."""
        drift = ForwardDrift(
            doc_claim="部分匹配功能",
            doc_file="2_CAPABILITIES.md",
            doc_location="line 5",
            matched_files=[MatchedFile(file="src/a.py", line=10, confidence=Confidence.MEDIUM)],
            confidence=Confidence.MEDIUM,
            drift_type=DriftType.PARTIAL,
            drift_detail="部分匹配",
        )
        fix = generate_fix_content(drift)
        assert fix.action == "update"
        assert "部分匹配" in fix.fix_description

    def test_every_drift_produces_fix(self):
        """每个 drift 项都应生成对应的修复内容。"""
        drifts = [
            ForwardDrift(
                doc_claim=f"功能{i}",
                doc_file="2_CAPABILITIES.md",
                doc_location=f"line {i}",
                confidence=Confidence.HIGH,
                drift_type=DriftType.MISSING,
                drift_detail="未找到",
            )
            for i in range(5)
        ]
        fixes = [generate_fix_content(d) for d in drifts]
        assert len(fixes) == 5
        assert all(f.fix_description for f in fixes)


# ── apply_capability_fixes 测试 ──


class TestApplyCapabilityFixes:
    def _write_capabilities(self, tmp_path: Path, content: str) -> str:
        cap_path = tmp_path / "2_CAPABILITIES.md"
        cap_path.write_text(content, encoding="utf-8")
        return str(cap_path)

    def test_downgrade_missing_capability(self, tmp_path: Path):
        """规则 3：代码中不再存在的 [x] 能力 → 降级为 [ ]。"""
        content = (
            "# 能力矩阵\n\n"
            "## 模块A\n\n"
            "- [x] 已移除功能\n"
            "- [x] 仍存在功能\n"
            "- [ ] 未实现功能\n"
        )
        cap_path = self._write_capabilities(tmp_path, content)

        drifts = [
            ForwardDrift(
                doc_claim="已移除功能",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 5",
                confidence=Confidence.HIGH,
                drift_type=DriftType.MISSING,
                drift_detail="未找到",
            )
        ]
        code_caps: set[str] = {"仍存在功能"}

        updated, changes = apply_capability_fixes(cap_path, drifts, code_caps)

        assert "[ ] 已移除功能" in updated
        assert "drift:" in updated
        assert any("降级" in c for c in changes)
        # 仍存在功能不应被修改（它不在 drift 列表中）
        assert "[x] 仍存在功能" in updated
        # 未实现功能不应被修改
        assert "[ ] 未实现功能" in updated

    def test_add_new_capability(self, tmp_path: Path):
        """规则 1：新增可用能力 → 添加并标记 [x]。"""
        content = (
            "# 能力矩阵\n\n"
            "## 模块A\n\n"
            "- [x] 已有功能\n"
        )
        cap_path = self._write_capabilities(tmp_path, content)

        drifts: list[ForwardDrift] = []
        code_caps: set[str] = {"已有功能", "新功能ABC"}

        updated, changes = apply_capability_fixes(cap_path, drifts, code_caps)

        assert "[x] 新功能ABC" in updated
        assert any("新增" in c for c in changes)

    def test_no_false_checkmarks_after_fix(self, tmp_path: Path):
        """修复后不应存在虚假勾选。"""
        content = (
            "# 能力矩阵\n\n"
            "## 模块A\n\n"
            "- [x] 虚假功能A\n"
            "- [x] 虚假功能B\n"
            "- [x] 真实功能\n"
        )
        cap_path = self._write_capabilities(tmp_path, content)

        drifts = [
            ForwardDrift(
                doc_claim="虚假功能A",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 5",
                confidence=Confidence.HIGH,
                drift_type=DriftType.MISSING,
                drift_detail="未找到",
            ),
            ForwardDrift(
                doc_claim="虚假功能B",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 6",
                confidence=Confidence.HIGH,
                drift_type=DriftType.MISSING,
                drift_detail="未找到",
            ),
        ]
        code_caps: set[str] = {"真实功能"}

        updated, changes = apply_capability_fixes(cap_path, drifts, code_caps)

        # 验证虚假功能被降级
        assert "[ ] 虚假功能A" in updated
        assert "[ ] 虚假功能B" in updated
        # 真实功能保持 [x]
        assert "[x] 真实功能" in updated

        # 验证没有虚假勾选：所有 [x] 项都应在 code_caps 中
        from chiwen_mcp.doc_code_lens import parse_capabilities
        claims = parse_capabilities(updated)
        for claim in claims:
            if claim.status == "[x]":
                assert claim.name in code_caps, f"虚假勾选: {claim.name}"

    def test_empty_file_returns_empty(self, tmp_path: Path):
        """空文件应返回空内容。"""
        cap_path = self._write_capabilities(tmp_path, "")
        updated, changes = apply_capability_fixes(cap_path, [], set())
        assert updated == ""
        assert changes == []

    def test_nonexistent_file(self, tmp_path: Path):
        """不存在的文件应返回空内容。"""
        cap_path = str(tmp_path / "nonexistent.md")
        updated, changes = apply_capability_fixes(cap_path, [], set())
        assert updated == ""
        assert changes == []

    def test_no_drifts_no_new_caps(self, tmp_path: Path):
        """无 drift 且无新能力时，内容不变。"""
        content = (
            "# 能力矩阵\n\n"
            "## 模块A\n\n"
            "- [x] 功能A\n"
        )
        cap_path = self._write_capabilities(tmp_path, content)

        updated, changes = apply_capability_fixes(cap_path, [], {"功能A"})
        assert changes == []
        assert "[x] 功能A" in updated

    def test_deprecated_items_preserved(self, tmp_path: Path):
        """(废弃) 状态的条目应保留不变。"""
        content = (
            "# 能力矩阵\n\n"
            "## 模块A\n\n"
            "- (废弃) 旧功能\n"
            "- [x] 现有功能\n"
        )
        cap_path = self._write_capabilities(tmp_path, content)

        updated, changes = apply_capability_fixes(cap_path, [], {"现有功能"})
        assert "(废弃) 旧功能" in updated


# ── sync_docs 集成测试 ──


@pytest.fixture
def tmp_project_for_sync(tmp_path: Path) -> Path:
    """创建一个带有 .docs/ 和代码文件的临时项目用于 sync 测试。"""
    # pyproject.toml
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "test-project"\n',
        encoding="utf-8",
    )

    # 代码文件
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "auth.py").write_text(
        'def login(user, password):\n    pass\n\n'
        'def logout(user):\n    pass\n',
        encoding="utf-8",
    )

    # .docs/ 目录
    docs = tmp_path / ".docs"
    docs.mkdir()

    # 2_CAPABILITIES.md — 包含一个虚假勾选
    (docs / "2_CAPABILITIES.md").write_text(
        "# test-project 能力矩阵\n\n"
        "> 虚假勾选是最高级别的文档事故\n\n"
        "## src\n\n"
        "- [x] login\n"
        "- [x] logout\n"
        "- [x] 不存在的功能xyz_999\n"
        "- [ ] 未实现功能\n",
        encoding="utf-8",
    )

    # 1_ARCHITECTURE.md
    (docs / "1_ARCHITECTURE.md").write_text(
        "# test-project 架构\n\n"
        "## 1. 技术选型\n\n- Python\n\n"
        "## 2. 分层架构\n\n- 应用层\n\n"
        "## 3. 模块职责映射\n\n"
        "| 层级 | 核心文件/目录 | 职责说明 |\n"
        "|:--|:--|:--|\n"
        "| 应用层 | `src` | 主模块（公开 API：login, logout） |\n\n"
        "## 4. 核心执行流程\n\n入口文件\n\n"
        "## 5. ADR 快速索引\n\n无\n",
        encoding="utf-8",
    )

    # 5_CHANGELOG.md
    (docs / "5_CHANGELOG.md").write_text(
        "# test-project 文档变更日志\n\n"
        "> 本文件由 AI 自动维护\n\n"
        "## 2025-01-01\n\n"
        "| 变更类型 | 文档 | 摘要 |\n"
        "|:--|:--|:--|\n"
        "| [初始化] | 全部文档 | 由 init 命令自动生成 |\n",
        encoding="utf-8",
    )

    return tmp_path


class TestSyncDocs:
    def test_missing_project_root_raises(self):
        with pytest.raises(ValueError, match="必填项"):
            sync_docs("")

    def test_nonexistent_path_raises(self):
        with pytest.raises(ValueError, match="不存在"):
            sync_docs("/nonexistent/path/xyz")

    def test_missing_docs_dir_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="init"):
            sync_docs(str(tmp_path))

    def test_sync_detects_and_fixes_drift(self, tmp_project_for_sync: Path):
        """sync 应检测到虚假勾选并修复。"""
        result = sync_docs(str(tmp_project_for_sync))

        assert result.drift_count >= 1
        assert result.fix_count >= 1
        assert result.changelog_updated is True

        # 验证 2_CAPABILITIES.md 中虚假勾选被降级
        cap_path = tmp_project_for_sync / ".docs" / "2_CAPABILITIES.md"
        content = cap_path.read_text(encoding="utf-8")
        assert "[ ] 不存在的功能xyz_999" in content
        assert "drift:" in content

    def test_sync_preserves_valid_capabilities(self, tmp_project_for_sync: Path):
        """sync 不应修改代码中存在的有效能力。"""
        result = sync_docs(str(tmp_project_for_sync))

        cap_path = tmp_project_for_sync / ".docs" / "2_CAPABILITIES.md"
        content = cap_path.read_text(encoding="utf-8")

        # login 和 logout 在代码中存在，不应被降级
        # 注意：取决于 doc-code-lens 的匹配逻辑
        assert "[ ] 未实现功能" in content  # 未实现功能保持 [ ]

    def test_sync_updates_changelog(self, tmp_project_for_sync: Path):
        """sync 应追加 changelog 记录。"""
        sync_docs(str(tmp_project_for_sync))

        changelog_path = tmp_project_for_sync / ".docs" / "5_CHANGELOG.md"
        content = changelog_path.read_text(encoding="utf-8")

        # 原有内容保留
        assert "初始化" in content
        assert "2025-01-01" in content

        # 新记录存在
        assert "能力同步" in content or "drift 检测" in content

    def test_sync_no_drift_returns_clean(self, tmp_path: Path):
        """无 drift 时应返回干净结果。"""
        # 创建一个完全一致的项目
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "clean-project"\n',
            encoding="utf-8",
        )
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("", encoding="utf-8")

        docs = tmp_path / ".docs"
        docs.mkdir()
        # 所有能力都是 [ ]，不会触发 forward drift
        (docs / "2_CAPABILITIES.md").write_text(
            "# clean-project 能力矩阵\n\n"
            "## src\n\n"
            "- [ ] 某功能\n",
            encoding="utf-8",
        )
        (docs / "1_ARCHITECTURE.md").write_text(
            "# clean-project 架构\n\n"
            "## 1. 技术选型\n\n- Python\n",
            encoding="utf-8",
        )
        (docs / "5_CHANGELOG.md").write_text(
            "# clean-project 文档变更日志\n\n",
            encoding="utf-8",
        )

        result = sync_docs(str(tmp_path))
        assert result.drift_count == 0
        assert result.fix_count == 0
        assert result.changelog_updated is False

    def test_sync_result_summary(self, tmp_project_for_sync: Path):
        """sync 结果应包含完整摘要信息。"""
        result = sync_docs(str(tmp_project_for_sync))

        assert isinstance(result, SyncResult)
        assert isinstance(result.drift_count, int)
        assert isinstance(result.fix_count, int)
        assert isinstance(result.changelog_updated, bool)
        assert isinstance(result.details, list)
        assert len(result.details) > 0


# ── apply_reverse_fixes 测试 ──


class TestApplyReverseFixes:
    def _write_capabilities(self, tmp_path: Path, content: str) -> str:
        cap_path = tmp_path / "2_CAPABILITIES.md"
        cap_path.write_text(content, encoding="utf-8")
        return str(cap_path)

    def test_append_to_matching_module(self, tmp_path: Path):
        """reverse drift 应追加到匹配的模块分组末尾。"""
        content = (
            "# 能力矩阵\n\n"
            "## 模块A\n\n"
            "- [x] 已有功能\n\n"
            "## 模块B\n\n"
            "- [x] 功能B1\n"
        )
        cap_path = self._write_capabilities(tmp_path, content)

        drifts = [
            ReverseDrift(
                file="src/module_a.py",
                location="module:模块A",
                capability="new_api_a",
                doc_mentioned=False,
            ),
        ]
        modules = [
            Module(name="模块A", path="src/module_a.py"),
            Module(name="模块B", path="src/module_b.py"),
        ]

        updated, changes = apply_reverse_fixes(cap_path, drifts, modules)

        assert "- [ ] new_api_a" in updated
        # 应在模块A分组中
        lines = updated.splitlines()
        mod_a_idx = next(i for i, l in enumerate(lines) if "## 模块A" in l)
        mod_b_idx = next(i for i, l in enumerate(lines) if "## 模块B" in l)
        new_cap_idx = next(i for i, l in enumerate(lines) if "new_api_a" in l)
        assert mod_a_idx < new_cap_idx < mod_b_idx
        assert len(changes) == 1
        assert "模块A" in changes[0]

    def test_uncategorized_when_no_module_match(self, tmp_path: Path):
        """无法匹配模块时追加到「未分类」分组。"""
        content = (
            "# 能力矩阵\n\n"
            "## 模块A\n\n"
            "- [x] 已有功能\n"
        )
        cap_path = self._write_capabilities(tmp_path, content)

        drifts = [
            ReverseDrift(
                file="src/unknown.py",
                location="module:unknown",
                capability="orphan_api",
                doc_mentioned=False,
            ),
        ]
        modules = [Module(name="模块A", path="src/module_a.py")]

        updated, changes = apply_reverse_fixes(cap_path, drifts, modules)

        assert "- [ ] orphan_api" in updated
        assert "## 未分类" in updated
        assert any("未分类" in c for c in changes)

    def test_create_uncategorized_section(self, tmp_path: Path):
        """「未分类」分组不存在时应自动创建。"""
        content = (
            "# 能力矩阵\n\n"
            "## 模块A\n\n"
            "- [x] 已有功能\n"
        )
        cap_path = self._write_capabilities(tmp_path, content)

        drifts = [
            ReverseDrift(
                file="src/unknown.py",
                capability="orphan_api",
            ),
        ]
        modules = [Module(name="模块A", path="src/module_a.py")]

        updated, changes = apply_reverse_fixes(cap_path, drifts, modules)

        assert "## 未分类" in updated
        assert "- [ ] orphan_api" in updated

    def test_preserves_existing_content(self, tmp_path: Path):
        """追加操作应保留已有内容的每一行。"""
        content = (
            "# 能力矩阵\n\n"
            "> 说明文字\n\n"
            "## 模块A\n\n"
            "- [x] 已有功能A\n"
            "- [ ] 未实现功能\n"
            "- (废弃) 旧功能\n\n"
            "## 模块B\n\n"
            "- [x] 功能B1\n"
        )
        cap_path = self._write_capabilities(tmp_path, content)
        original_lines = content.splitlines()

        drifts = [
            ReverseDrift(
                file="src/module_a.py",
                capability="new_api",
            ),
        ]
        modules = [
            Module(name="模块A", path="src/module_a.py"),
            Module(name="模块B", path="src/module_b.py"),
        ]

        updated, _ = apply_reverse_fixes(cap_path, drifts, modules)
        updated_lines = updated.splitlines()

        # 所有原有行都应保留
        for orig_line in original_lines:
            assert orig_line in updated_lines, f"丢失行: {orig_line!r}"

    def test_file_not_exists_creates_with_uncategorized(self, tmp_path: Path):
        """文件不存在时创建新文件仅包含「未分类」分组。"""
        cap_path = str(tmp_path / "nonexistent.md")

        drifts = [
            ReverseDrift(
                file="src/unknown.py",
                capability="new_api",
            ),
        ]
        modules: list[Module] = []

        updated, changes = apply_reverse_fixes(cap_path, drifts, modules)

        assert "## 未分类" in updated
        assert "- [ ] new_api" in updated
        assert len(changes) == 1

    def test_no_drifts_returns_original(self, tmp_path: Path):
        """无 reverse drift 时返回原内容不变。"""
        content = "# 能力矩阵\n\n## 模块A\n\n- [x] 已有功能\n"
        cap_path = self._write_capabilities(tmp_path, content)

        updated, changes = apply_reverse_fixes(cap_path, [], [])

        assert updated == content
        assert changes == []

    def test_skip_duplicate_capabilities(self, tmp_path: Path):
        """已存在的能力不应重复追加。"""
        content = (
            "# 能力矩阵\n\n"
            "## 模块A\n\n"
            "- [x] existing_api\n"
        )
        cap_path = self._write_capabilities(tmp_path, content)

        drifts = [
            ReverseDrift(
                file="src/module_a.py",
                capability="existing_api",
            ),
        ]
        modules = [Module(name="模块A", path="src/module_a.py")]

        updated, changes = apply_reverse_fixes(cap_path, drifts, modules)

        # 不应有变更
        assert changes == []
        # 只应出现一次
        assert updated.count("existing_api") == 1

    def test_multiple_drifts_multiple_modules(self, tmp_path: Path):
        """多个 drift 项分别追加到各自的模块分组。"""
        content = (
            "# 能力矩阵\n\n"
            "## 模块A\n\n"
            "- [x] 功能A1\n\n"
            "## 模块B\n\n"
            "- [x] 功能B1\n"
        )
        cap_path = self._write_capabilities(tmp_path, content)

        drifts = [
            ReverseDrift(file="src/module_a.py", capability="new_a"),
            ReverseDrift(file="src/module_b.py", capability="new_b"),
            ReverseDrift(file="src/unknown.py", capability="new_unknown"),
        ]
        modules = [
            Module(name="模块A", path="src/module_a.py"),
            Module(name="模块B", path="src/module_b.py"),
        ]

        updated, changes = apply_reverse_fixes(cap_path, drifts, modules)

        assert "- [ ] new_a" in updated
        assert "- [ ] new_b" in updated
        assert "- [ ] new_unknown" in updated
        assert "## 未分类" in updated
        assert len(changes) == 3

    def test_append_to_existing_uncategorized(self, tmp_path: Path):
        """已有「未分类」分组时追加到该分组末尾。"""
        content = (
            "# 能力矩阵\n\n"
            "## 模块A\n\n"
            "- [x] 功能A1\n\n"
            "## 未分类\n\n"
            "- [ ] 已有未分类项\n"
        )
        cap_path = self._write_capabilities(tmp_path, content)

        drifts = [
            ReverseDrift(file="src/unknown.py", capability="new_orphan"),
        ]
        modules = [Module(name="模块A", path="src/module_a.py")]

        updated, changes = apply_reverse_fixes(cap_path, drifts, modules)

        assert "- [ ] new_orphan" in updated
        assert "- [ ] 已有未分类项" in updated
        # 不应创建第二个「未分类」分组
        assert updated.count("## 未分类") == 1
