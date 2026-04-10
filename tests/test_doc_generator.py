"""Tests for doc_generator module — init 命令文档生成逻辑。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from chiwen_mcp.doc_generator import (
    generate_architecture,
    generate_capabilities,
    generate_changelog,
    generate_decisions,
    generate_index,
    generate_roadmap,
    init_docs,
    update_gitignore,
)
from chiwen_mcp.models import (
    ApiRoute,
    CodeReaderOutput,
    Dependencies,
    EntryPoint,
    Module,
    ProjectInfo,
    ScanMeta,
)


# ── Fixtures ──


@pytest.fixture
def sample_output() -> CodeReaderOutput:
    """构造一个典型的 CodeReaderOutput 用于测试。"""
    return CodeReaderOutput(
        project_info=ProjectInfo(
            name="test-project",
            language="Python",
            framework="FastAPI",
            package_manager="pip",
            monorepo=False,
            packages=[],
        ),
        modules=[
            Module(
                name="auth",
                path="src/auth",
                layer="应用层",
                dependencies=["db"],
                public_api=["login", "logout", "register"],
            ),
            Module(
                name="db",
                path="src/db",
                layer="数据层",
                dependencies=[],
                public_api=["connect", "query"],
            ),
        ],
        entry_points=[
            EntryPoint(file="main.py", type="main", description="应用入口"),
        ],
        api_routes=[
            ApiRoute(
                method="POST",
                path="/api/login",
                handler="auth.login",
                description="用户登录",
            ),
            ApiRoute(
                method="GET",
                path="/api/users",
                handler="users.list",
                description="用户列表",
            ),
        ],
        dependencies=Dependencies(
            direct=["fastapi", "uvicorn", "sqlalchemy"],
            major=["fastapi"],
        ),
        scan_meta=ScanMeta(
            total_files=42,
            total_lines=3500,
            scan_duration_ms=120,
            scanned_at="2025-01-01T00:00:00Z",
        ),
    )


@pytest.fixture
def empty_output() -> CodeReaderOutput:
    """空的 CodeReaderOutput，模拟空项目。"""
    return CodeReaderOutput(
        project_info=ProjectInfo(name="empty-project"),
    )


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """创建一个临时项目目录用于 init_docs 测试。"""
    # 创建 pyproject.toml 使其被识别为 Python 项目
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "tmp-test"\n', encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")
    return tmp_path


# ── generate_index ──


class TestGenerateIndex:
    def test_contains_project_name(self):
        content = generate_index("my-project")
        assert "# my-project 知识文档索引" in content

    def test_contains_doc_table(self):
        content = generate_index("proj")
        assert "| 文件 | 职责 | 更新方式 |" in content
        assert "0_INDEX.md" in content
        assert "1_ARCHITECTURE.md" in content
        assert "2_CAPABILITIES.md" in content
        assert "3_ROADMAP.md" in content
        assert "4_DECISIONS.md" in content
        assert "5_CHANGELOG.md" in content

    def test_contains_external_links_section(self):
        content = generate_index("proj")
        assert "## 外部资源链接" in content


# ── generate_architecture ──


class TestGenerateArchitecture:
    def test_five_sections(self, sample_output: CodeReaderOutput):
        content = generate_architecture(sample_output)
        assert "## 1. 技术选型" in content
        assert "## 2. 分层架构" in content
        assert "## 3. 模块职责映射" in content
        assert "## 4. 核心执行流程" in content
        assert "## 5. ADR 快速索引" in content

    def test_tech_stack_info(self, sample_output: CodeReaderOutput):
        content = generate_architecture(sample_output)
        assert "Python" in content
        assert "FastAPI" in content
        assert "pip" in content

    def test_module_mapping_table(self, sample_output: CodeReaderOutput):
        content = generate_architecture(sample_output)
        assert "| 层级 | 核心文件/目录 | 职责说明 |" in content
        assert "auth" in content
        assert "db" in content

    def test_entry_points_listed(self, sample_output: CodeReaderOutput):
        content = generate_architecture(sample_output)
        assert "main.py" in content

    def test_api_routes_listed(self, sample_output: CodeReaderOutput):
        content = generate_architecture(sample_output)
        assert "/api/login" in content
        assert "/api/users" in content

    def test_adr_index_empty(self, sample_output: CodeReaderOutput):
        content = generate_architecture(sample_output)
        assert "4_DECISIONS.md" in content
        assert "暂无决策记录" in content

    def test_empty_output(self, empty_output: CodeReaderOutput):
        content = generate_architecture(empty_output)
        assert "## 1. 技术选型" in content
        assert "## 2. 分层架构" in content
        assert "暂无模块层级信息" in content


# ── generate_capabilities ──


class TestGenerateCapabilities:
    def test_no_checked_items(self, sample_output: CodeReaderOutput):
        content = generate_capabilities(sample_output)
        assert "[x]" not in content

    def test_all_items_unchecked(self, sample_output: CodeReaderOutput):
        content = generate_capabilities(sample_output)
        # 每个 public_api 和 api_route 都应该有 [ ]
        assert content.count("- [ ]") >= 5  # 3 auth + 2 db + 2 routes

    def test_module_sections(self, sample_output: CodeReaderOutput):
        content = generate_capabilities(sample_output)
        assert "## auth" in content
        assert "## db" in content

    def test_api_routes_section(self, sample_output: CodeReaderOutput):
        content = generate_capabilities(sample_output)
        assert "## API 路由" in content
        assert "POST /api/login" in content

    def test_warning_header(self, sample_output: CodeReaderOutput):
        content = generate_capabilities(sample_output)
        assert "虚假勾选" in content

    def test_empty_output(self, empty_output: CodeReaderOutput):
        content = generate_capabilities(empty_output)
        assert "[x]" not in content


# ── generate_roadmap ──


class TestGenerateRoadmap:
    def test_three_sections(self):
        content = generate_roadmap("proj")
        assert "## 近期计划" in content
        assert "## 中期计划" in content
        assert "## 远期愿景" in content

    def test_project_name(self):
        content = generate_roadmap("my-app")
        assert "# my-app 路线图" in content


# ── generate_decisions ──


class TestGenerateDecisions:
    def test_adr_format_sections(self):
        content = generate_decisions("proj")
        assert "## 状态" in content
        assert "## 背景" in content
        assert "## 决策" in content
        assert "## 后果" in content

    def test_positive_negative_consequences(self):
        content = generate_decisions("proj")
        assert "### 正面" in content
        assert "### 负面" in content

    def test_project_name(self):
        content = generate_decisions("my-app")
        assert "# my-app 架构决策记录" in content


# ── generate_changelog ──


class TestGenerateChangelog:
    def test_contains_init_entry(self):
        content = generate_changelog("proj")
        assert "[初始化]" in content
        assert "全部文档" in content

    def test_contains_table_header(self):
        content = generate_changelog("proj")
        assert "| 变更类型 | 文档 | 摘要 |" in content

    def test_auto_maintenance_warning(self):
        content = generate_changelog("proj")
        assert "不建议手动编辑" in content


# ── update_gitignore ──


class TestUpdateGitignore:
    def test_creates_gitignore_if_missing(self, tmp_path: Path):
        update_gitignore(str(tmp_path))
        gitignore = tmp_path / ".gitignore"
        assert gitignore.exists()
        assert ".docs/users/*/notepad.md" in gitignore.read_text()

    def test_appends_entry(self, tmp_path: Path):
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("node_modules/\n", encoding="utf-8")
        result = update_gitignore(str(tmp_path))
        assert result is True
        content = gitignore.read_text()
        assert "node_modules/" in content
        assert ".docs/users/*/notepad.md" in content

    def test_skips_if_exists(self, tmp_path: Path):
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text(".docs/users/*/notepad.md\n", encoding="utf-8")
        result = update_gitignore(str(tmp_path))
        assert result is False
        # 不应重复追加
        content = gitignore.read_text()
        assert content.count(".docs/users/*/notepad.md") == 1

    def test_handles_no_trailing_newline(self, tmp_path: Path):
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("node_modules/", encoding="utf-8")  # 无尾换行
        update_gitignore(str(tmp_path))
        content = gitignore.read_text()
        # 应该在新行追加
        assert "node_modules/\n.docs/users/*/notepad.md\n" == content


# ── init_docs ──


class TestInitDocs:
    def test_creates_docs_directory(self, tmp_project: Path):
        init_docs(str(tmp_project))
        assert (tmp_project / ".docs").is_dir()

    def test_generates_all_files(self, tmp_project: Path):
        result = init_docs(str(tmp_project))
        docs_dir = tmp_project / ".docs"
        expected_files = [
            "0_INDEX.md",
            "1_ARCHITECTURE.md",
            "2_CAPABILITIES.md",
            "3_ROADMAP.md",
            "4_DECISIONS.md",
            "5_CHANGELOG.md",
        ]
        for fname in expected_files:
            assert (docs_dir / fname).exists(), f"{fname} should exist"

    def test_result_summary(self, tmp_project: Path):
        result = init_docs(str(tmp_project))
        assert "files" in result
        assert "scan_meta" in result
        assert "project_name" in result
        assert "gitignore_updated" in result
        assert len(result["files"]) == 6

    def test_capabilities_no_checked(self, tmp_project: Path):
        init_docs(str(tmp_project))
        caps = (tmp_project / ".docs" / "2_CAPABILITIES.md").read_text()
        assert "[x]" not in caps

    def test_architecture_five_sections(self, tmp_project: Path):
        init_docs(str(tmp_project))
        arch = (tmp_project / ".docs" / "1_ARCHITECTURE.md").read_text()
        assert "## 1. 技术选型" in arch
        assert "## 2. 分层架构" in arch
        assert "## 3. 模块职责映射" in arch
        assert "## 4. 核心执行流程" in arch
        assert "## 5. ADR 快速索引" in arch

    def test_gitignore_updated(self, tmp_project: Path):
        init_docs(str(tmp_project))
        gitignore = tmp_project / ".gitignore"
        assert gitignore.exists()
        assert ".docs/users/*/notepad.md" in gitignore.read_text()
