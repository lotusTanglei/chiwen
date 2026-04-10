"""Tests for git-changelog MCP tool."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from chiwen_mcp.git_changelog import (
    _infer_module,
    _is_doc_file,
    run_git_changelog,
)
from chiwen_mcp.models import GitChangelogInput, GitChangelogOutput
from chiwen_mcp.server import git_changelog, mcp


# ── Helper: create a git repo with commits ──


def _init_git_repo(tmp_path: Path) -> None:
    """Initialize a git repo with some commits for testing."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test User",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test User",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    cwd = str(tmp_path)

    subprocess.run(["git", "init"], cwd=cwd, capture_output=True, env=env)
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=cwd, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=cwd,
        capture_output=True,
    )

    # First commit: src/main.py
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("print('hello')\n")
    subprocess.run(["git", "add", "."], cwd=cwd, capture_output=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=cwd,
        capture_output=True,
        env=env,
    )

    # Second commit: docs/README.md
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "README.md").write_text("# Project\n")
    subprocess.run(["git", "add", "."], cwd=cwd, capture_output=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "Add docs"],
        cwd=cwd,
        capture_output=True,
        env=env,
    )


# ── Unit tests: helper functions ──


class TestInferModule:
    def test_root_file(self):
        assert _infer_module("README.md") == "(root)"

    def test_nested_file(self):
        assert _infer_module("src/main.py") == "src"

    def test_deeply_nested(self):
        assert _infer_module("src/utils/helpers.py") == "src"

    def test_backslash_path(self):
        assert _infer_module("src\\main.py") == "src"


class TestIsDocFile:
    def test_markdown(self):
        assert _is_doc_file("README.md") is True

    def test_rst(self):
        assert _is_doc_file("docs/guide.rst") is True

    def test_python(self):
        assert _is_doc_file("main.py") is False

    def test_case_insensitive(self):
        assert _is_doc_file("CHANGELOG.MD") is True


# ── Unit tests: MCP tool registration ──


class TestGitChangelogToolRegistration:
    def test_tool_registered(self):
        tools = mcp._tool_manager._tools
        assert "git-changelog" in tools

    def test_tool_has_description(self):
        tool = mcp._tool_manager._tools["git-changelog"]
        assert tool.description
        assert len(tool.description) > 0

    def test_tool_input_schema_has_required_project_root(self):
        tool = mcp._tool_manager._tools["git-changelog"]
        schema = tool.parameters
        assert "project_root" in schema.get("required", [])

    def test_tool_input_schema_has_all_fields(self):
        tool = mcp._tool_manager._tools["git-changelog"]
        props = tool.parameters.get("properties", {})
        expected_fields = {"project_root", "since", "until", "top_n", "group_by"}
        assert expected_fields.issubset(set(props.keys()))


# ── Unit tests: server tool function ──


class TestGitChangelogToolFunction:
    def test_empty_project_root_returns_error(self):
        result = git_changelog(project_root="")
        data = json.loads(result)
        assert "error" in data

    def test_nonexistent_path_returns_error(self):
        result = git_changelog(project_root="/nonexistent/path/xyz")
        data = json.loads(result)
        assert "error" in data

    def test_invalid_group_by_returns_error(self, tmp_path: Path):
        result = git_changelog(project_root=str(tmp_path), group_by="invalid")
        data = json.loads(result)
        assert "error" in data
        assert "group_by" in data["error"]

    def test_non_git_repo_returns_error(self, tmp_path: Path):
        result = git_changelog(project_root=str(tmp_path))
        data = json.loads(result)
        assert "error" in data

    def test_valid_git_repo_returns_json(self, tmp_path: Path):
        _init_git_repo(tmp_path)
        result = git_changelog(project_root=str(tmp_path))
        data = json.loads(result)
        assert "error" not in data
        expected_keys = {"contributors", "module_activity", "recent_commits", "stale_files"}
        assert expected_keys.issubset(set(data.keys()))

    def test_default_parameters(self, tmp_path: Path):
        _init_git_repo(tmp_path)
        result = git_changelog(project_root=str(tmp_path))
        data = json.loads(result)
        assert "error" not in data
        # Should have at least one contributor
        assert len(data["contributors"]) >= 1

    def test_scan_exception_returns_error(self, tmp_path: Path, monkeypatch):
        import chiwen_mcp.server as server_module

        def _boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(server_module, "run_git_changelog", _boom)

        result = git_changelog(project_root=str(tmp_path))
        data = json.loads(result)
        assert "error" in data
        assert "boom" in data["error"]


# ── Integration tests: core logic ──


class TestRunGitChangelog:
    def test_non_git_repo_raises(self, tmp_path: Path):
        input_params = GitChangelogInput(project_root=str(tmp_path))
        with pytest.raises(RuntimeError, match="Git"):
            run_git_changelog(input_params)

    def test_empty_history_returns_empty(self, tmp_path: Path):
        """Git repo with commits outside the time range returns empty output."""
        _init_git_repo(tmp_path)
        input_params = GitChangelogInput(
            project_root=str(tmp_path),
            since="2000-01-01",
            until="2000-01-02",
        )
        result = run_git_changelog(input_params)
        assert isinstance(result, GitChangelogOutput)
        assert result.contributors == []
        assert result.recent_commits == []

    def test_contributors_populated(self, tmp_path: Path):
        _init_git_repo(tmp_path)
        input_params = GitChangelogInput(project_root=str(tmp_path))
        result = run_git_changelog(input_params)
        assert len(result.contributors) >= 1
        c = result.contributors[0]
        assert c.name == "Test User"
        assert c.email == "test@example.com"
        assert c.commits >= 1
        assert c.files_changed >= 1
        assert c.last_active != ""

    def test_module_activity_populated(self, tmp_path: Path):
        _init_git_repo(tmp_path)
        input_params = GitChangelogInput(project_root=str(tmp_path))
        result = run_git_changelog(input_params)
        assert len(result.module_activity) >= 1
        modules = [m.module for m in result.module_activity]
        assert "src" in modules

    def test_recent_commits_populated(self, tmp_path: Path):
        _init_git_repo(tmp_path)
        input_params = GitChangelogInput(project_root=str(tmp_path))
        result = run_git_changelog(input_params)
        assert len(result.recent_commits) >= 2
        # Second commit has doc file
        doc_commit = [c for c in result.recent_commits if c.doc_files_changed]
        assert len(doc_commit) >= 1

    def test_stale_files_populated(self, tmp_path: Path):
        _init_git_repo(tmp_path)
        input_params = GitChangelogInput(project_root=str(tmp_path))
        result = run_git_changelog(input_params)
        assert len(result.stale_files) >= 1
        # Recently committed files should not be abandoned
        for sf in result.stale_files:
            assert sf.days_since_change >= 0

    def test_top_n_limits_contributors(self, tmp_path: Path):
        _init_git_repo(tmp_path)
        input_params = GitChangelogInput(project_root=str(tmp_path), top_n=1)
        result = run_git_changelog(input_params)
        assert len(result.contributors) <= 1

    def test_contributor_top_modules_not_empty(self, tmp_path: Path):
        _init_git_repo(tmp_path)
        input_params = GitChangelogInput(project_root=str(tmp_path))
        result = run_git_changelog(input_params)
        for c in result.contributors:
            assert len(c.top_modules) >= 1
