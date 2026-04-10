"""Tests for code-reader MCP core scanning logic."""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

import pytest

from chiwen_mcp.code_reader import (
    CodeReaderInput,
    _is_excluded,
    _is_included,
    _infer_purpose,
    scan_project,
)


# ── Fixtures ──


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal project structure for testing."""
    # package.json
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "test-project",
        "dependencies": {"express": "^4.18.0", "lodash": "^4.17.0"},
        "devDependencies": {"jest": "^29.0.0"},
    }))

    # src directory
    src = tmp_path / "src"
    src.mkdir()
    (src / "index.ts").write_text("export const main = () => {};\n")
    (src / "app.ts").write_text(textwrap.dedent("""\
        import express from 'express';
        const app = express();
        app.get('/api/users', (req, res) => {});
        app.post('/api/users', (req, res) => {});
        export default app;
    """))

    # src/controllers
    controllers = src / "controllers"
    controllers.mkdir()
    (controllers / "userController.ts").write_text(textwrap.dedent("""\
        export class UserController {
            getUser() {}
            createUser() {}
        }
    """))

    # src/models
    models = src / "models"
    models.mkdir()
    (models / "user.ts").write_text(textwrap.dedent("""\
        export interface User {
            id: string;
            name: string;
            email: string;
        }
    """))

    # src/services
    services = src / "services"
    services.mkdir()
    (services / "userService.ts").write_text("export class UserService {}\n")

    # node_modules (should be excluded)
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "express").mkdir()
    (nm / "express" / "index.js").write_text("module.exports = {};")

    # .git (should be excluded)
    git = tmp_path / ".git"
    git.mkdir()
    (git / "config").write_text("[core]")

    # tsconfig.json
    (tmp_path / "tsconfig.json").write_text("{}")

    return tmp_path


@pytest.fixture
def tmp_python_project(tmp_path: Path) -> Path:
    """Create a minimal Python project structure."""
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent("""\
        [project]
        name = "my-python-app"
        dependencies = [
            "fastapi>=0.100.0",
            "uvicorn>=0.20.0",
        ]

        [build-system]
        requires = ["hatchling"]
        build-backend = "hatchling.build"
    """))

    app = tmp_path / "app"
    app.mkdir()
    (app / "__init__.py").write_text("")
    (app / "main.py").write_text(textwrap.dedent("""\
        from fastapi import FastAPI

        app = FastAPI()

        @app.get("/api/items")
        def list_items():
            return []

        @app.post("/api/items")
        async def create_item():
            return {}
    """))

    models = app / "models"
    models.mkdir()
    (models / "__init__.py").write_text("")
    (models / "item.py").write_text(textwrap.dedent("""\
        from dataclasses import dataclass

        @dataclass
        class Item(dataclass):
            name: str
            price: float
            quantity: int
    """))

    return tmp_path


# ── Helper function tests ──


class TestIsExcluded:
    def test_excludes_node_modules(self):
        assert _is_excluded("node_modules/express/index.js", ["node_modules"])

    def test_excludes_git(self):
        assert _is_excluded(".git/config", [".git"])

    def test_does_not_exclude_normal_path(self):
        assert not _is_excluded("src/index.ts", ["node_modules", ".git"])

    def test_excludes_nested_match(self):
        assert _is_excluded("a/b/node_modules/c.js", ["node_modules"])

    def test_glob_pattern(self):
        assert _is_excluded("dist/bundle.js", ["dist"])

    def test_wildcard_pattern(self):
        assert _is_excluded("build/output.js", ["build*"])


class TestIsIncluded:
    def test_wildcard_includes_all(self):
        assert _is_included("src/index.ts", ["*"])

    def test_specific_pattern(self):
        assert _is_included("src/index.ts", ["*.ts"])

    def test_not_included(self):
        assert not _is_included("src/index.ts", ["*.py"])


class TestInferPurpose:
    def test_config_file(self):
        assert _infer_purpose("package.json") == "config"

    def test_test_file(self):
        assert _infer_purpose("test_main.py") == "test"

    def test_readme(self):
        assert _infer_purpose("README.md") == "documentation"

    def test_controller(self):
        assert _infer_purpose("userController.ts") == "controller"

    def test_service(self):
        assert _infer_purpose("userService.ts") == "service"

    def test_model(self):
        assert _infer_purpose("userModel.ts") == "model"


# ── scan_project tests ──


class TestScanProject:
    def test_invalid_path_raises(self):
        inp = CodeReaderInput(project_root="/nonexistent/path/xyz")
        with pytest.raises(ValueError, match="路径不存在"):
            scan_project(inp)

    def test_basic_scan_node_project(self, tmp_project: Path):
        inp = CodeReaderInput(project_root=str(tmp_project))
        result = scan_project(inp)

        # project_info
        assert result.project_info.name == "test-project"
        assert result.project_info.language == "TypeScript"
        assert result.project_info.framework == "Express"

        # structure should not contain node_modules or .git
        paths = [n.path for n in result.structure]
        for p in paths:
            assert "node_modules" not in p
            assert ".git" not in p

        # scan_meta
        assert result.scan_meta.total_files > 0
        assert result.scan_meta.total_lines >= 0
        assert result.scan_meta.scan_duration_ms >= 0
        assert result.scan_meta.scanned_at != ""

    def test_basic_scan_python_project(self, tmp_python_project: Path):
        inp = CodeReaderInput(project_root=str(tmp_python_project))
        result = scan_project(inp)

        assert result.project_info.name == "my-python-app"
        assert result.project_info.language == "Python"
        assert result.project_info.framework == "FastAPI"

    def test_exclude_patterns(self, tmp_project: Path):
        inp = CodeReaderInput(
            project_root=str(tmp_project),
            exclude_patterns=["node_modules", ".git", "src"],
        )
        result = scan_project(inp)

        paths = [n.path for n in result.structure]
        for p in paths:
            assert not p.startswith("src")

    def test_include_patterns(self, tmp_project: Path):
        inp = CodeReaderInput(
            project_root=str(tmp_project),
            include_patterns=["*.json"],
        )
        result = scan_project(inp)

        file_nodes = [n for n in result.structure if n.type == "file"]
        for n in file_nodes:
            assert n.path.endswith(".json")

    def test_focus_parameter(self, tmp_project: Path):
        inp = CodeReaderInput(
            project_root=str(tmp_project),
            focus=["src"],
        )
        result = scan_project(inp)

        # Modules should only include focused ones
        module_names = [m.name for m in result.modules]
        for name in module_names:
            assert name == "src"

    def test_depth_limit(self, tmp_project: Path):
        inp = CodeReaderInput(
            project_root=str(tmp_project),
            depth=0,
        )
        result = scan_project(inp)

        # With depth 0, should only see top-level items
        for node in result.structure:
            parts = Path(node.path).parts
            assert len(parts) <= 1

    def test_api_routes_extracted(self, tmp_project: Path):
        inp = CodeReaderInput(project_root=str(tmp_project))
        result = scan_project(inp)

        # Should find Express routes
        assert len(result.api_routes) > 0
        methods = [r.method for r in result.api_routes]
        assert "GET" in methods
        assert "POST" in methods

    def test_api_routes_python(self, tmp_python_project: Path):
        inp = CodeReaderInput(project_root=str(tmp_python_project))
        result = scan_project(inp)

        assert len(result.api_routes) > 0
        paths = [r.path for r in result.api_routes]
        assert "/api/items" in paths

    def test_entry_points_detected(self, tmp_project: Path):
        inp = CodeReaderInput(project_root=str(tmp_project))
        result = scan_project(inp)

        entry_files = [e.file for e in result.entry_points]
        # Should detect index.ts and app.ts as entry points
        assert any("index.ts" in f for f in entry_files)
        assert any("app.ts" in f for f in entry_files)

    def test_dependencies_extracted(self, tmp_project: Path):
        inp = CodeReaderInput(project_root=str(tmp_project))
        result = scan_project(inp)

        assert "express" in result.dependencies.direct
        assert "lodash" in result.dependencies.major
        assert "jest" in result.dependencies.direct

    def test_scan_meta_iso8601(self, tmp_project: Path):
        inp = CodeReaderInput(project_root=str(tmp_project))
        result = scan_project(inp)

        # Verify ISO8601 format
        from datetime import datetime
        ts = result.scan_meta.scanned_at
        # Should parse without error
        datetime.fromisoformat(ts)

    def test_output_has_all_fields(self, tmp_project: Path):
        inp = CodeReaderInput(project_root=str(tmp_project))
        result = scan_project(inp)

        # Verify all top-level fields exist
        assert result.project_info is not None
        assert isinstance(result.structure, list)
        assert isinstance(result.entry_points, list)
        assert isinstance(result.modules, list)
        assert isinstance(result.data_models, list)
        assert isinstance(result.api_routes, list)
        assert result.dependencies is not None
        assert result.scan_meta is not None

    def test_empty_directory(self, tmp_path: Path):
        inp = CodeReaderInput(project_root=str(tmp_path))
        result = scan_project(inp)

        assert result.project_info.name == tmp_path.name
        assert result.scan_meta.total_files == 0
        assert result.scan_meta.total_lines == 0

    def test_data_models_extracted(self, tmp_python_project: Path):
        inp = CodeReaderInput(project_root=str(tmp_python_project))
        result = scan_project(inp)

        model_names = [m.name for m in result.data_models]
        assert "Item" in model_names

    def test_modules_inferred(self, tmp_project: Path):
        inp = CodeReaderInput(project_root=str(tmp_project))
        result = scan_project(inp)

        module_names = [m.name for m in result.modules]
        assert "src" in module_names
