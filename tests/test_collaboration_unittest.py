from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from chiwen_mcp.changelog_utils import append_changelog
from chiwen_mcp.changelog_utils import parse_changelog
from chiwen_mcp.collaboration import acquire_docs_lock, lock_file_path, release_docs_lock
from chiwen_mcp.doc_generator import init_docs
from chiwen_mcp.sync import sync_docs


class TestDocsLock(unittest.TestCase):
    def test_lock_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            docs_dir = os.path.join(td, ".docs")
            acquire_docs_lock(docs_dir, ttl_seconds=60)
            try:
                with self.assertRaises(RuntimeError):
                    acquire_docs_lock(docs_dir, ttl_seconds=60)
            finally:
                release_docs_lock(docs_dir)

    def test_expired_lock_is_replaced(self):
        with tempfile.TemporaryDirectory() as td:
            docs_dir = os.path.join(td, ".docs")
            os.makedirs(docs_dir, exist_ok=True)
            lock_path = lock_file_path(docs_dir)
            with open(lock_path, "w", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "created_at": 1,
                            "ttl_seconds": 1,
                            "pid": 1,
                            "user": "u",
                            "host": "h",
                            "expires_at": 2,
                        },
                        ensure_ascii=False,
                    )
                )
            info = acquire_docs_lock(docs_dir, ttl_seconds=60)
            try:
                self.assertTrue(info.expires_at > 2)
            finally:
                release_docs_lock(docs_dir)


class TestInitDocsModes(unittest.TestCase):
    def test_init_error_mode_rejects_existing_docs(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "main.py").write_text("print('x')\n", encoding="utf-8")
            docs_dir = Path(td, ".docs")
            docs_dir.mkdir()
            Path(docs_dir, "0_INDEX.md").write_text("x\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                init_docs(td, mode="error", lock_ttl_seconds=60)


class TestChangelogStableAppend(unittest.TestCase):
    def test_append_dedup_and_stable_order(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "5_CHANGELOG.md")
            Path(path).write_text(
                "# x\n\n## 2026-01-01\n\n| 变更类型 | 文档 | 摘要 |\n|:--|:--|:--|\n| [能力同步] | 2_CAPABILITIES.md | a |\n",
                encoding="utf-8",
            )
            from chiwen_mcp.models import ChangelogEntry

            entries = [
                ChangelogEntry(
                    date="2026-01-01",
                    change_type="能力同步",
                    target_doc="2_CAPABILITIES.md",
                    summary="a",
                ),
                ChangelogEntry(
                    date="2026-01-01",
                    change_type="drift 检测",
                    target_doc="多个文档",
                    summary="b",
                ),
            ]
            content = append_changelog(path, entries)
            self.assertEqual(content.count("| [能力同步] | 2_CAPABILITIES.md | a |"), 1)
            self.assertIn("| [drift 检测] | 多个文档 | b |", content)

    def test_parse_merges_duplicate_date_groups(self):
        content = "\n".join(
            [
                "# x",
                "",
                "## 2026-01-01",
                "",
                "| 变更类型 | 文档 | 摘要 |",
                "|:--|:--|:--|",
                "| [能力同步] | 2_CAPABILITIES.md | a |",
                "",
                "## 2026-01-01",
                "",
                "| 变更类型 | 文档 | 摘要 |",
                "|:--|:--|:--|",
                "| [drift 检测] | 多个文档 | b |",
                "",
            ]
        )
        doc = parse_changelog(content)
        self.assertEqual(len(doc.groups), 1)
        self.assertEqual(doc.groups[0].date, "2026-01-01")
        self.assertEqual(len(doc.groups[0].changes), 2)


class TestGitDirtyDetection(unittest.TestCase):
    def test_git_repo_detection_optional(self):
        if shutil.which("git") is None:
            self.skipTest("git not available")
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["git", "init"], cwd=td, check=True, capture_output=True)
            Path(td, "a.txt").write_text("x\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=td, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "init"],
                cwd=td,
                check=True,
                capture_output=True,
                env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
            )
            Path(td, ".docs").mkdir()
            Path(td, ".docs", "x.md").write_text("x\n", encoding="utf-8")
            out = subprocess.run(
                ["git", "status", "--porcelain", "--", ".docs"],
                cwd=td,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertTrue(out)

    def test_sync_rejects_dirty_docs_by_default(self):
        if shutil.which("git") is None:
            self.skipTest("git not available")
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["git", "init"], cwd=td, check=True, capture_output=True)
            Path(td, "main.py").write_text("print('x')\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=td, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "init"],
                cwd=td,
                check=True,
                capture_output=True,
                env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
            )
            docs_dir = Path(td, ".docs")
            docs_dir.mkdir()
            Path(docs_dir, "2_CAPABILITIES.md").write_text("# x\n", encoding="utf-8")
            Path(docs_dir, "5_CHANGELOG.md").write_text("# x\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                sync_docs(td, allow_dirty=False, allow_risky=True, lock_ttl_seconds=60)

    def test_sync_rejects_risky_head_change_by_default(self):
        if shutil.which("git") is None:
            self.skipTest("git not available")
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["git", "init"], cwd=td, check=True, capture_output=True)
            Path(td, "main.py").write_text("print('x')\n", encoding="utf-8")
            docs_dir = Path(td, ".docs")
            docs_dir.mkdir()
            Path(docs_dir, "2_CAPABILITIES.md").write_text("# x\n", encoding="utf-8")
            Path(docs_dir, "5_CHANGELOG.md").write_text("# x\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=td, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "init"],
                cwd=td,
                check=True,
                capture_output=True,
                env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
            )
            state_path = Path(docs_dir, ".chiwen.state.json")
            state_path.write_text(
                json.dumps({"git": {"head": "deadbeef"}}, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                sync_docs(td, allow_dirty=True, allow_risky=False, lock_ttl_seconds=60)


if __name__ == "__main__":
    unittest.main()
