"""Tests for status module — status 命令逻辑和健康度报告。

测试覆盖：
- HealthReport 数据类（含新增字段 active_contributors, stale_docs）
- get_status: 主函数参数验证和集成
- sync_rate 计算逻辑
- git-changelog 集成与优雅降级
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from chiwen_mcp.models import (
    Confidence,
    Contributor,
    DriftType,
    ForwardDrift,
    StaleFile,
)
from chiwen_mcp.status import HealthReport, _filter_stale_docs, get_status


# ── HealthReport 数据类测试 ──


class TestHealthReport:
    def test_default_values(self):
        """默认 HealthReport 应表示健康状态。"""
        report = HealthReport()
        assert report.sync_rate == 1.0
        assert report.total_checked == 0
        assert report.in_sync == 0
        assert report.drifted == 0
        assert report.pending_drifts == []
        assert report.active_contributors == []
        assert report.stale_docs == []
        assert report.git_available is False
        assert report.git_error == ""

    def test_custom_values(self):
        """自定义值应正确设置。"""
        drift = ForwardDrift(
            doc_claim="test",
            doc_file="2_CAPABILITIES.md",
            doc_location="line 1",
            confidence=Confidence.HIGH,
            drift_type=DriftType.MISSING,
            drift_detail="missing",
        )
        contributor = Contributor(
            name="Alice",
            email="alice@example.com",
            commits=5,
            files_changed=3,
            lines_added=100,
            lines_removed=20,
            top_modules=["src"],
            last_active="2024-01-15T10:00:00+08:00",
        )
        stale = StaleFile(
            path=".docs/1_ARCHITECTURE.md",
            last_changed="2023-06-01T00:00:00+00:00",
            days_since_change=200,
            likely_abandoned=True,
        )
        report = HealthReport(
            sync_rate=0.75,
            total_checked=8,
            in_sync=6,
            drifted=2,
            active_contributors=[contributor],
            stale_docs=[stale],
            pending_drifts=[drift],
            git_available=True,
            git_error="",
        )
        assert report.sync_rate == 0.75
        assert report.total_checked == 8
        assert report.in_sync == 6
        assert report.drifted == 2
        assert len(report.pending_drifts) == 1
        assert len(report.active_contributors) == 1
        assert report.active_contributors[0].name == "Alice"
        assert len(report.stale_docs) == 1
        assert report.stale_docs[0].path == ".docs/1_ARCHITECTURE.md"
        assert report.git_available is True


# ── _filter_stale_docs 测试 ──


class TestFilterStaleDocs:
    def test_filters_docs_directory(self):
        """应保留 .docs/ 目录下的文件。"""
        files = [
            StaleFile(path=".docs/1_ARCHITECTURE.md", last_changed="", days_since_change=100, likely_abandoned=True),
            StaleFile(path="src/main.py", last_changed="", days_since_change=50, likely_abandoned=False),
        ]
        result = _filter_stale_docs(files)
        assert len(result) == 1
        assert result[0].path == ".docs/1_ARCHITECTURE.md"

    def test_filters_markdown_files(self):
        """应保留 .md 扩展名的文件。"""
        files = [
            StaleFile(path="README.md", last_changed="", days_since_change=120, likely_abandoned=True),
            StaleFile(path="src/app.py", last_changed="", days_since_change=30, likely_abandoned=False),
        ]
        result = _filter_stale_docs(files)
        assert len(result) == 1
        assert result[0].path == "README.md"

    def test_filters_multiple_doc_extensions(self):
        """应保留 .rst, .txt, .adoc 扩展名的文件。"""
        files = [
            StaleFile(path="docs/guide.rst", last_changed="", days_since_change=100, likely_abandoned=True),
            StaleFile(path="notes.txt", last_changed="", days_since_change=200, likely_abandoned=True),
            StaleFile(path="manual.adoc", last_changed="", days_since_change=150, likely_abandoned=True),
            StaleFile(path="src/lib.py", last_changed="", days_since_change=10, likely_abandoned=False),
        ]
        result = _filter_stale_docs(files)
        assert len(result) == 3

    def test_empty_list(self):
        """空列表应返回空列表。"""
        assert _filter_stale_docs([]) == []


# ── get_status 参数验证测试 ──


class TestGetStatusValidation:
    def test_empty_project_root_raises(self):
        with pytest.raises(ValueError, match="必填项"):
            get_status("")

    def test_whitespace_project_root_raises(self):
        with pytest.raises(ValueError, match="必填项"):
            get_status("   ")

    def test_nonexistent_path_raises(self):
        with pytest.raises(ValueError, match="不存在"):
            get_status("/nonexistent/path/xyz_abc_123")

    def test_missing_docs_dir_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="init"):
            get_status(str(tmp_path))


# ── get_status 集成测试 ──


@pytest.fixture
def clean_project(tmp_path: Path) -> Path:
    """创建一个无 drift 的干净项目。"""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "clean-project"\n',
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")

    docs = tmp_path / ".docs"
    docs.mkdir()
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
    return tmp_path


@pytest.fixture
def drifted_project(tmp_path: Path) -> Path:
    """创建一个有 drift 的项目（包含虚假勾选）。"""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "drifted-project"\n',
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "auth.py").write_text(
        "def login(user, password):\n    pass\n",
        encoding="utf-8",
    )

    docs = tmp_path / ".docs"
    docs.mkdir()
    (docs / "2_CAPABILITIES.md").write_text(
        "# drifted-project 能力矩阵\n\n"
        "## src\n\n"
        "- [x] login\n"
        "- [x] 不存在的功能xyz_999\n"
        "- [ ] 未实现功能\n",
        encoding="utf-8",
    )
    (docs / "1_ARCHITECTURE.md").write_text(
        "# drifted-project 架构\n\n"
        "## 1. 技术选型\n\n- Python\n",
        encoding="utf-8",
    )
    return tmp_path


class TestGetStatus:
    def test_clean_project_full_sync(self, clean_project: Path):
        """无 drift 的项目应返回高同步率。"""
        report = get_status(str(clean_project))

        assert isinstance(report, HealthReport)
        assert 0.0 <= report.sync_rate <= 1.0
        assert report.total_checked >= 0
        assert report.in_sync >= 0
        assert report.drifted >= 0
        assert report.in_sync + report.drifted == report.total_checked

    def test_drifted_project_has_pending_drifts(self, drifted_project: Path):
        """有 drift 的项目应返回待处理 drift 项。"""
        report = get_status(str(drifted_project))

        assert isinstance(report, HealthReport)
        assert report.drifted >= 1
        assert len(report.pending_drifts) >= 1
        assert report.sync_rate < 1.0

    def test_sync_rate_bounds(self, drifted_project: Path):
        """sync_rate 应在 [0, 1] 范围内。"""
        report = get_status(str(drifted_project))
        assert 0.0 <= report.sync_rate <= 1.0

    def test_sync_rate_calculation(self, drifted_project: Path):
        """sync_rate 应等于 in_sync / total_checked。"""
        report = get_status(str(drifted_project))

        if report.total_checked > 0:
            expected = report.in_sync / report.total_checked
            assert abs(report.sync_rate - expected) < 1e-9

    def test_empty_docs_project(self, tmp_path: Path):
        """只有空 .docs/ 目录的项目应正常返回。"""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "empty-docs"\n',
            encoding="utf-8",
        )
        docs = tmp_path / ".docs"
        docs.mkdir()

        report = get_status(str(tmp_path))

        assert isinstance(report, HealthReport)
        assert report.total_checked == 0
        assert report.sync_rate == 1.0
        assert report.pending_drifts == []

    def test_report_consistency(self, drifted_project: Path):
        """报告中的数值应保持一致性。"""
        report = get_status(str(drifted_project))

        assert report.in_sync + report.drifted == report.total_checked
        assert report.drifted == len(report.pending_drifts)


# ── git-changelog 集成测试 ──


class TestGetStatusGitIntegration:
    def test_non_git_repo_graceful_degradation(self, clean_project: Path):
        """非 Git 仓库应优雅降级，不影响核心报告。"""
        report = get_status(str(clean_project))

        assert isinstance(report, HealthReport)
        # 核心报告字段仍然正常
        assert 0.0 <= report.sync_rate <= 1.0
        assert report.total_checked >= 0
        # git 相关字段应标记不可用
        assert report.git_available is False
        assert report.git_error != ""
        assert report.active_contributors == []
        assert report.stale_docs == []

    def test_git_error_does_not_crash_status(self, drifted_project: Path):
        """git-changelog 失败不应导致 status 命令崩溃。"""
        report = get_status(str(drifted_project))

        # 即使 git 不可用，drift 检测仍然正常
        assert report.drifted >= 1
        assert len(report.pending_drifts) >= 1
        assert report.git_available is False

    def test_git_available_with_mock(self, clean_project: Path):
        """当 git-changelog 成功时，应填充贡献者和过期文档。"""
        from chiwen_mcp.models import GitChangelogOutput

        mock_contributor = Contributor(
            name="Bob",
            email="bob@example.com",
            commits=10,
            files_changed=5,
            lines_added=200,
            lines_removed=50,
            top_modules=["src"],
            last_active="2024-01-20T10:00:00+08:00",
        )
        mock_stale = StaleFile(
            path=".docs/3_ROADMAP.md",
            last_changed="2023-01-01T00:00:00+00:00",
            days_since_change=400,
            likely_abandoned=True,
        )
        mock_output = GitChangelogOutput(
            contributors=[mock_contributor],
            stale_files=[
                mock_stale,
                StaleFile(
                    path="src/old_code.py",
                    last_changed="2023-06-01T00:00:00+00:00",
                    days_since_change=200,
                    likely_abandoned=True,
                ),
            ],
        )

        with patch("chiwen_mcp.status.run_git_changelog", return_value=mock_output):
            report = get_status(str(clean_project))

        assert report.git_available is True
        assert report.git_error == ""
        assert len(report.active_contributors) == 1
        assert report.active_contributors[0].name == "Bob"
        # stale_docs 应只包含文档文件，不包含 src/old_code.py
        assert len(report.stale_docs) == 1
        assert report.stale_docs[0].path == ".docs/3_ROADMAP.md"
