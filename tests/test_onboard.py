"""onboard 命令单元测试"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from chiwen_mcp.onboard import (
    generate_cache,
    generate_notepad,
    get_reading_list,
    get_username,
    onboard,
)


# ── get_username 测试 ──


class TestGetUsername:
    """测试用户名获取优先级逻辑"""

    def test_git_config_first_priority(self):
        """git config user.name 优先级最高"""
        with patch("chiwen_mcp.onboard.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "gituser\n"
            result = get_username()
        assert result == "gituser"

    def test_env_user_second_priority(self):
        """环境变量 USER 为第二优先级"""
        with (
            patch("chiwen_mcp.onboard.subprocess.run") as mock_run,
            patch.dict(os.environ, {"USER": "envuser"}, clear=False),
        ):
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            result = get_username()
        assert result == "envuser"

    def test_env_username_third_priority(self):
        """环境变量 USERNAME 为第三优先级"""
        with (
            patch("chiwen_mcp.onboard.subprocess.run") as mock_run,
            patch.dict(os.environ, {"USER": "", "USERNAME": "winuser"}, clear=False),
        ):
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            result = get_username()
        assert result == "winuser"

    def test_returns_none_when_all_fail(self):
        """全部获取失败时返回 None"""
        with (
            patch("chiwen_mcp.onboard.subprocess.run") as mock_run,
            patch.dict(os.environ, {"USER": "", "USERNAME": ""}, clear=False),
        ):
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            result = get_username()
        assert result is None

    def test_git_not_installed(self):
        """git 未安装时回退到环境变量"""
        with (
            patch(
                "chiwen_mcp.onboard.subprocess.run", side_effect=FileNotFoundError
            ),
            patch.dict(os.environ, {"USER": "fallback"}, clear=False),
        ):
            result = get_username()
        assert result == "fallback"

    def test_git_timeout(self):
        """git 命令超时时回退到环境变量"""
        import subprocess

        with (
            patch(
                "chiwen_mcp.onboard.subprocess.run",
                side_effect=subprocess.TimeoutExpired("git", 5),
            ),
            patch.dict(os.environ, {"USER": "timeout_fallback"}, clear=False),
        ):
            result = get_username()
        assert result == "timeout_fallback"


# ── generate_notepad 测试 ──


class TestGenerateNotepad:
    def test_contains_username(self):
        content = generate_notepad("alice")
        assert "@alice" in content

    def test_contains_private_notice(self):
        content = generate_notepad("bob")
        assert "Git" in content or "git" in content.lower()


# ── generate_cache 测试 ──


class TestGenerateCache:
    def test_contains_username(self):
        content = generate_cache("alice")
        assert "@alice" in content

    def test_three_sections(self):
        content = generate_cache("alice")
        assert "工作风格" in content
        assert "当前关注点" in content
        assert "已知" in content and "盲区" in content


# ── get_reading_list 测试 ──


class TestGetReadingList:
    def test_correct_order(self):
        reading_list = get_reading_list()
        files = [item["file"] for item in reading_list]
        assert files == ["0_INDEX.md", "1_ARCHITECTURE.md", "2_CAPABILITIES.md"]

    def test_has_descriptions(self):
        reading_list = get_reading_list()
        for item in reading_list:
            assert "description" in item
            assert len(item["description"]) > 0


# ── onboard 主函数测试 ──


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """创建带 .docs/ 目录的临时项目"""
    docs_dir = tmp_path / ".docs"
    docs_dir.mkdir()
    return tmp_path


class TestOnboard:
    def test_creates_user_directory(self, tmp_project: Path):
        result = onboard(str(tmp_project), username="alice")
        assert result["success"] is True
        user_dir = tmp_project / ".docs" / "users" / "@alice"
        assert user_dir.is_dir()

    def test_creates_notepad_and_cache(self, tmp_project: Path):
        result = onboard(str(tmp_project), username="alice")
        assert len(result["files_created"]) == 2
        notepad = tmp_project / ".docs" / "users" / "@alice" / "notepad.md"
        cache = tmp_project / ".docs" / "users" / "@alice" / "cache.md"
        assert notepad.is_file()
        assert cache.is_file()

    def test_notepad_content(self, tmp_project: Path):
        onboard(str(tmp_project), username="alice")
        notepad = tmp_project / ".docs" / "users" / "@alice" / "notepad.md"
        content = notepad.read_text(encoding="utf-8")
        assert "@alice" in content

    def test_cache_content_has_three_sections(self, tmp_project: Path):
        onboard(str(tmp_project), username="alice")
        cache = tmp_project / ".docs" / "users" / "@alice" / "cache.md"
        content = cache.read_text(encoding="utf-8")
        assert "工作风格" in content
        assert "当前关注点" in content
        assert "盲区" in content

    def test_returns_reading_list(self, tmp_project: Path):
        result = onboard(str(tmp_project), username="alice")
        files = [item["file"] for item in result["reading_list"]]
        assert files == ["0_INDEX.md", "1_ARCHITECTURE.md", "2_CAPABILITIES.md"]

    def test_already_exists(self, tmp_project: Path):
        # 先创建一次
        onboard(str(tmp_project), username="alice")
        # 再次调用
        result = onboard(str(tmp_project), username="alice")
        assert result["success"] is False
        assert result["already_exists"] is True

    def test_no_username_returns_error(self, tmp_project: Path):
        with (
            patch("chiwen_mcp.onboard.get_username", return_value=None),
        ):
            result = onboard(str(tmp_project))
        assert result["success"] is False
        assert result["username"] is None

    def test_auto_detect_username(self, tmp_project: Path):
        with patch("chiwen_mcp.onboard.get_username", return_value="autouser"):
            result = onboard(str(tmp_project))
        assert result["success"] is True
        assert result["username"] == "autouser"
