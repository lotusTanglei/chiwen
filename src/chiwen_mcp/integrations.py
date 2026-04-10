"""chiwen Knowledge Kit - 自动化集成配置模板

提供 CI/PR check、Git pre-commit hook、cron 定时任务的配置模板。
所有集成为可选配置，不影响核心功能。

使用方式：
    from chiwen_mcp.integrations import (
        generate_ci_config,
        generate_pre_commit_hook,
        generate_cron_config,
    )
"""

from __future__ import annotations


def generate_ci_config(
    provider: str = "github",
    project_root: str = ".",
) -> str:
    """生成 CI/PR check 配置模板。

    在 PR 中调用 doc-code-lens 检查 drift，代码变更但文档未更新时返回 warning。

    Args:
        provider: CI 提供商，支持 "github"（GitHub Actions）和 "gitlab"（GitLab CI）
        project_root: 项目根目录路径，默认 "."

    Returns:
        配置文件内容字符串

    Raises:
        ValueError: 不支持的 provider
    """
    if provider == "github":
        return _github_actions_config(project_root)
    elif provider == "gitlab":
        return _gitlab_ci_config(project_root)
    else:
        raise ValueError(
            f"不支持的 CI 提供商：{provider}，支持 github 和 gitlab"
        )


def _github_actions_config(project_root: str) -> str:
    return f"""\
# .github/workflows/doc-drift-check.yml
# chiwen Knowledge Kit — 文档 Drift 检查
# 在 PR 中自动检查文档与代码的一致性

name: Doc Drift Check

on:
  pull_request:
    branches: [main, master]

jobs:
  doc-drift-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install chiwen Knowledge Kit
        run: pip install chiwen-knowledge-kit

      - name: Run doc-code-lens drift check
        run: |
          chiwen-mcp doc-code-lens \\
            --project-root "{project_root}" \\
            --mode full
        continue-on-error: true

      - name: Check for drift warnings
        run: |
          # 解析 drift 检查结果，如有 drift 则输出 warning
          chiwen-mcp doc-code-lens \\
            --project-root "{project_root}" \\
            --mode full \\
            --output-format json | python3 -c "
          import json, sys
          data = json.load(sys.stdin)
          drifted = data.get('summary', {{}}).get('drifted', 0)
          if drifted > 0:
              print(f'::warning::发现 {{drifted}} 个文档 drift 项，请检查文档是否需要更新')
              for d in data.get('forward_drift', []):
                  print(f'::warning file={{d[\"doc_file\"]}}::{{d[\"drift_detail\"]}}')
              sys.exit(0)  # warning 级别，不阻断 PR
          else:
              print('✅ 文档与代码一致，无 drift')
          "
"""


def _gitlab_ci_config(project_root: str) -> str:
    return f"""\
# .gitlab-ci.yml（追加以下内容）
# chiwen Knowledge Kit — 文档 Drift 检查

doc-drift-check:
  stage: test
  image: python:3.12-slim
  script:
    - pip install chiwen-knowledge-kit
    - chiwen-mcp doc-code-lens --project-root "{project_root}" --mode full
  allow_failure: true
  only:
    - merge_requests
"""


def generate_pre_commit_hook(project_root: str = ".") -> str:
    """生成 Git pre-commit hook 脚本。

    在本地提交前检查 drift，向开发者提供即时反馈。

    Args:
        project_root: 项目根目录路径，默认 "."

    Returns:
        pre-commit hook 脚本内容
    """
    return f"""\
#!/bin/sh
# .git/hooks/pre-commit
# chiwen Knowledge Kit — 提交前文档 Drift 检查
#
# 安装方式：
#   cp this-file .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit
#
# 或使用 pre-commit 框架：
#   在 .pre-commit-config.yaml 中添加对应配置

# 检查是否有 .docs/ 目录（未初始化则跳过）
if [ ! -d "{project_root}/.docs" ]; then
    exit 0
fi

# 检查是否有文档相关文件变更
DOC_CHANGES=$(git diff --cached --name-only | grep -E '\\.(py|ts|js|go|rs|java)$' || true)
if [ -z "$DOC_CHANGES" ]; then
    exit 0
fi

echo "🔍 chiwen: 检查文档与代码一致性..."

# 运行 drift 检查（仅 forward 模式，速度更快）
RESULT=$(chiwen-mcp doc-code-lens \\
    --project-root "{project_root}" \\
    --mode forward \\
    --output-format json 2>/dev/null) || exit 0

DRIFTED=$(echo "$RESULT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('summary', {{}}).get('drifted', 0))
except:
    print(0)
" 2>/dev/null)

if [ "$DRIFTED" -gt 0 ] 2>/dev/null; then
    echo "⚠️  发现 $DRIFTED 个文档 drift 项"
    echo "   建议运行 'chiwen sync' 更新文档"
    echo "   使用 'git commit --no-verify' 跳过此检查"
    # warning 级别，不阻断提交
fi

exit 0
"""


def generate_pre_commit_yaml_config() -> str:
    """生成 .pre-commit-config.yaml 格式的配置片段。

    适用于使用 pre-commit 框架的项目。

    Returns:
        YAML 配置片段
    """
    return """\
# .pre-commit-config.yaml（追加以下内容）
# chiwen Knowledge Kit — 文档 Drift 检查

repos:
  - repo: local
    hooks:
      - id: chiwen-doc-drift
        name: chiwen doc drift check
        entry: chiwen-mcp doc-code-lens --project-root . --mode forward
        language: system
        pass_filenames: false
        always_run: true
        verbose: true
"""


def generate_cron_config(
    project_root: str = ".",
    schedule: str = "weekly",
    output_path: str = "",
) -> str:
    """生成 cron 定时调用 status 的配置模板。

    定期生成健康度报告，支持周报和月报。

    Args:
        project_root: 项目根目录路径，默认 "."
        schedule: 调度频率，"weekly" 或 "monthly"
        output_path: 报告输出路径，默认为 .docs/reports/

    Returns:
        cron 配置和脚本内容

    Raises:
        ValueError: 不支持的 schedule
    """
    if schedule not in ("weekly", "monthly"):
        raise ValueError(
            f"不支持的调度频率：{schedule}，支持 weekly 和 monthly"
        )

    if not output_path:
        output_path = f"{project_root}/.docs/reports"

    if schedule == "weekly":
        cron_expr = "0 9 * * 1"  # 每周一 09:00
        label = "周报"
    else:
        cron_expr = "0 9 1 * *"  # 每月 1 日 09:00
        label = "月报"

    return f"""\
# chiwen Knowledge Kit — 定时健康度报告（{label}）
#
# 方式一：系统 crontab
# 运行 `crontab -e` 并添加以下行：
{cron_expr} cd {project_root} && chiwen-mcp status --project-root "{project_root}" --output-format json > {output_path}/status-$(date +\\%Y-\\%m-\\%d).json 2>&1

# 方式二：GitHub Actions 定时任务
# 将以下内容保存为 .github/workflows/doc-status-report.yml

name: Doc Status Report ({label})

on:
  schedule:
    - cron: "{cron_expr}"
  workflow_dispatch:  # 支持手动触发

jobs:
  status-report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install chiwen Knowledge Kit
        run: pip install chiwen-knowledge-kit

      - name: Generate status report
        run: |
          mkdir -p {output_path}
          chiwen-mcp status \\
            --project-root "{project_root}" \\
            --output-format json \\
            > {output_path}/status-$(date +%Y-%m-%d).json

      - name: Upload report artifact
        uses: actions/upload-artifact@v4
        with:
          name: doc-status-report
          path: {output_path}/
"""
