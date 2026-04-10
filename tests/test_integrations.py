"""Tests for integrations module — 自动化集成配置模板。

测试覆盖：
- CI/PR check 配置模板生成（GitHub Actions, GitLab CI）
- Git pre-commit hook 脚本生成
- cron 定时任务配置模板生成
- 参数验证和错误处理
- 所有集成为可选配置，不影响核心功能
"""

from __future__ import annotations

import pytest

from chiwen_mcp.integrations import (
    generate_ci_config,
    generate_cron_config,
    generate_pre_commit_hook,
    generate_pre_commit_yaml_config,
)


class TestGenerateCiConfig:
    def test_github_actions_default(self):
        """GitHub Actions 配置应包含关键元素。"""
        config = generate_ci_config(provider="github")
        assert "doc-drift-check" in config
        assert "pull_request" in config
        assert "doc-code-lens" in config
        assert "actions/checkout" in config

    def test_github_actions_custom_root(self):
        """自定义 project_root 应反映在配置中。"""
        config = generate_ci_config(provider="github", project_root="/app")
        assert "/app" in config

    def test_gitlab_ci(self):
        """GitLab CI 配置应包含关键元素。"""
        config = generate_ci_config(provider="gitlab")
        assert "doc-drift-check" in config
        assert "merge_requests" in config
        assert "allow_failure: true" in config

    def test_unsupported_provider_raises(self):
        """不支持的 CI 提供商应抛出 ValueError。"""
        with pytest.raises(ValueError, match="不支持"):
            generate_ci_config(provider="jenkins")


class TestGeneratePreCommitHook:
    def test_default_hook(self):
        """默认 pre-commit hook 应包含关键元素。"""
        hook = generate_pre_commit_hook()
        assert "#!/bin/sh" in hook
        assert "pre-commit" in hook
        assert "doc-code-lens" in hook
        assert "--no-verify" in hook

    def test_custom_root(self):
        """自定义 project_root 应反映在脚本中。"""
        hook = generate_pre_commit_hook(project_root="/my/project")
        assert "/my/project" in hook

    def test_hook_is_non_blocking(self):
        """hook 应为 warning 级别，不阻断提交。"""
        hook = generate_pre_commit_hook()
        assert "exit 0" in hook


class TestGeneratePreCommitYamlConfig:
    def test_yaml_config(self):
        """pre-commit YAML 配置应包含关键元素。"""
        config = generate_pre_commit_yaml_config()
        assert "chiwen-doc-drift" in config
        assert "doc-code-lens" in config
        assert "repos:" in config


class TestGenerateCronConfig:
    def test_weekly_schedule(self):
        """周报配置应包含每周一的 cron 表达式。"""
        config = generate_cron_config(schedule="weekly")
        assert "0 9 * * 1" in config
        assert "周报" in config

    def test_monthly_schedule(self):
        """月报配置应包含每月 1 日的 cron 表达式。"""
        config = generate_cron_config(schedule="monthly")
        assert "0 9 1 * *" in config
        assert "月报" in config

    def test_custom_root_and_output(self):
        """自定义路径应反映在配置中。"""
        config = generate_cron_config(
            project_root="/app",
            schedule="weekly",
            output_path="/app/reports",
        )
        assert "/app" in config
        assert "/app/reports" in config

    def test_unsupported_schedule_raises(self):
        """不支持的调度频率应抛出 ValueError。"""
        with pytest.raises(ValueError, match="不支持"):
            generate_cron_config(schedule="daily")

    def test_github_actions_cron(self):
        """配置应包含 GitHub Actions 定时任务模板。"""
        config = generate_cron_config(schedule="weekly")
        assert "workflow_dispatch" in config
        assert "schedule" in config


class TestIntegrationsDoNotAffectCore:
    """验证集成模块不影响核心功能。"""

    def test_import_does_not_import_core(self):
        """导入 integrations 不应触发核心模块的副作用。"""
        # 仅验证模块可独立导入
        import chiwen_mcp.integrations as mod
        assert hasattr(mod, "generate_ci_config")
        assert hasattr(mod, "generate_pre_commit_hook")
        assert hasattr(mod, "generate_cron_config")

    def test_all_functions_return_strings(self):
        """所有生成函数应返回字符串。"""
        assert isinstance(generate_ci_config(), str)
        assert isinstance(generate_pre_commit_hook(), str)
        assert isinstance(generate_pre_commit_yaml_config(), str)
        assert isinstance(generate_cron_config(), str)
