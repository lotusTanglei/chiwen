"""Tests for MCP server tool registration."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from chiwen_mcp.server import code_reader, doc_code_lens, mcp


class TestMCPToolRegistration:
    """Verify code-reader is properly registered as an MCP tool."""

    def test_tool_registered(self):
        """code-reader tool should be registered in the MCP server."""
        tools = mcp._tool_manager._tools
        assert "code-reader" in tools

    def test_tool_has_description(self):
        """code-reader tool should have a non-empty description."""
        tool = mcp._tool_manager._tools["code-reader"]
        assert tool.description
        assert len(tool.description) > 0

    def test_tool_input_schema_has_required_project_root(self):
        """Input schema should require project_root."""
        tool = mcp._tool_manager._tools["code-reader"]
        schema = tool.parameters
        assert "project_root" in schema.get("required", [])

    def test_tool_input_schema_has_all_fields(self):
        """Input schema should include all CodeReaderInput fields."""
        tool = mcp._tool_manager._tools["code-reader"]
        props = tool.parameters.get("properties", {})
        expected_fields = {"project_root", "depth", "focus", "include_patterns", "exclude_patterns"}
        assert expected_fields.issubset(set(props.keys()))


class TestCodeReaderToolFunction:
    """Test the code-reader tool function directly."""

    def test_empty_project_root_returns_error(self):
        """Empty project_root should return a JSON error."""
        result = code_reader(project_root="")
        data = json.loads(result)
        assert "error" in data

    def test_nonexistent_path_returns_error(self):
        """Non-existent path should return a JSON error."""
        result = code_reader(project_root="/nonexistent/path/xyz")
        data = json.loads(result)
        assert "error" in data

    def test_valid_project_returns_json(self, tmp_path: Path):
        """Valid project root should return a valid JSON with all output fields."""
        (tmp_path / "main.py").write_text("print('hello')\n")
        result = code_reader(project_root=str(tmp_path))
        data = json.loads(result)
        assert "error" not in data
        expected_keys = {
            "project_info", "structure", "entry_points", "modules",
            "data_models", "api_routes", "dependencies", "scan_meta",
        }
        assert expected_keys.issubset(set(data.keys()))

    def test_default_parameters(self, tmp_path: Path):
        """Default parameters should be applied when not specified."""
        (tmp_path / "hello.py").write_text("x = 1\n")
        result = code_reader(project_root=str(tmp_path))
        data = json.loads(result)
        assert "error" not in data
        # scan_meta should have non-negative values
        meta = data["scan_meta"]
        assert meta["total_files"] >= 0
        assert meta["total_lines"] >= 0
        assert meta["scan_duration_ms"] >= 0

    def test_scan_exception_returns_error(self, tmp_path: Path, monkeypatch):
        """Scan exceptions should be caught and returned as JSON error."""
        import chiwen_mcp.server as server_module

        def _boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(server_module, "scan_project", _boom)

        result = code_reader(project_root=str(tmp_path))
        data = json.loads(result)
        assert "error" in data
        assert "boom" in data["error"]


class TestDocCodeLensToolRegistration:
    """Verify doc-code-lens is properly registered as an MCP tool."""

    def test_tool_registered(self):
        """doc-code-lens tool should be registered in the MCP server."""
        tools = mcp._tool_manager._tools
        assert "doc-code-lens" in tools

    def test_tool_has_description(self):
        """doc-code-lens tool should have a non-empty description."""
        tool = mcp._tool_manager._tools["doc-code-lens"]
        assert tool.description
        assert len(tool.description) > 0

    def test_tool_input_schema_has_required_project_root(self):
        """Input schema should require project_root."""
        tool = mcp._tool_manager._tools["doc-code-lens"]
        schema = tool.parameters
        assert "project_root" in schema.get("required", [])

    def test_tool_input_schema_has_all_fields(self):
        """Input schema should include all DocCodeLensInput fields."""
        tool = mcp._tool_manager._tools["doc-code-lens"]
        props = tool.parameters.get("properties", {})
        expected_fields = {"project_root", "doc_path", "mode"}
        assert expected_fields.issubset(set(props.keys()))


class TestDocCodeLensToolFunction:
    """Test the doc-code-lens tool function directly."""

    def test_empty_project_root_returns_error(self):
        """Empty project_root should return a JSON error."""
        result = doc_code_lens(project_root="")
        data = json.loads(result)
        assert "error" in data

    def test_nonexistent_path_returns_error(self):
        """Non-existent path should return a JSON error."""
        result = doc_code_lens(project_root="/nonexistent/path/xyz")
        data = json.loads(result)
        assert "error" in data

    def test_missing_docs_dir_returns_error(self, tmp_path: Path):
        """Project without .docs/ directory should return a JSON error."""
        result = doc_code_lens(project_root=str(tmp_path))
        data = json.loads(result)
        assert "error" in data
        assert ".docs/" in data["error"]

    def test_invalid_mode_returns_error(self, tmp_path: Path):
        """Invalid mode parameter should return a JSON error."""
        (tmp_path / ".docs").mkdir()
        result = doc_code_lens(project_root=str(tmp_path), mode="invalid")
        data = json.loads(result)
        assert "error" in data
        assert "mode" in data["error"]

    def test_valid_project_returns_json(self, tmp_path: Path):
        """Valid project with .docs/ should return a valid JSON with all output fields."""
        docs_dir = tmp_path / ".docs"
        docs_dir.mkdir()
        (tmp_path / "main.py").write_text("print('hello')\n")
        result = doc_code_lens(project_root=str(tmp_path))
        data = json.loads(result)
        assert "error" not in data
        expected_keys = {"summary", "forward_drift", "reverse_drift", "recommendations"}
        assert expected_keys.issubset(set(data.keys()))

    def test_default_mode_is_full(self, tmp_path: Path):
        """Default mode should be 'full' and return valid output."""
        docs_dir = tmp_path / ".docs"
        docs_dir.mkdir()
        result = doc_code_lens(project_root=str(tmp_path))
        data = json.loads(result)
        assert "error" not in data
        assert "summary" in data

    def test_scan_exception_returns_error(self, tmp_path: Path, monkeypatch):
        """Scan exceptions should be caught and returned as JSON error."""
        docs_dir = tmp_path / ".docs"
        docs_dir.mkdir()

        import chiwen_mcp.server as server_module

        def _boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(server_module, "run_doc_code_lens", _boom)

        result = doc_code_lens(project_root=str(tmp_path))
        data = json.loads(result)
        assert "error" in data
        assert "boom" in data["error"]
