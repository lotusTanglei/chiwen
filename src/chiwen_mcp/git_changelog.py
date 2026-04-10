"""chiwen Knowledge Kit - git-changelog MCP 核心逻辑

从 Git 历史提取协作知识：贡献者统计、模块活跃度、近期提交、过期文件检测。
使用 subprocess 调用 git 命令，不引入额外 git 库。
"""

from __future__ import annotations

import subprocess
from collections import defaultdict
from datetime import datetime, timezone

from .models import (
    CommitInfo,
    Contributor,
    GitChangelogInput,
    GitChangelogOutput,
    ModuleActivity,
    StaleFile,
)

# 过期文件阈值（天）
_STALE_THRESHOLD_DAYS = 90

# 文档文件扩展名
_DOC_EXTENSIONS = {".md", ".rst", ".txt", ".adoc"}


def _run_git(args: list[str], cwd: str) -> str:
    """执行 git 命令并返回 stdout。

    Raises:
        RuntimeError: 非 Git 仓库或 git 命令执行失败
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        raise RuntimeError("git 命令未找到，请确保已安装 Git")
    except subprocess.TimeoutExpired:
        raise RuntimeError("git 命令执行超时")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not a git repository" in stderr.lower():
            raise RuntimeError(f"不是 Git 仓库：{cwd}")
        raise RuntimeError(f"git 命令失败：{stderr}")

    return result.stdout


def _infer_module(file_path: str) -> str:
    """通过文件路径前缀推断所属模块。

    取路径的第一级目录作为模块名。
    如果文件在根目录，模块名为 "(root)"。
    """
    parts = file_path.replace("\\", "/").split("/")
    if len(parts) <= 1:
        return "(root)"
    return parts[0]


def _is_doc_file(file_path: str) -> bool:
    """判断文件是否为文档文件。"""
    lower = file_path.lower()
    return any(lower.endswith(ext) for ext in _DOC_EXTENSIONS)


def _parse_iso_date(date_str: str) -> datetime:
    """解析 ISO8601 日期字符串。"""
    # git log --format=%aI 输出格式如 2024-01-15T10:30:00+08:00
    try:
        return datetime.fromisoformat(date_str.strip())
    except (ValueError, AttributeError):
        return datetime.now(timezone.utc)


def _get_commits(
    cwd: str, since: str, until: str
) -> list[dict]:
    """从 git log 提取提交历史。

    返回包含 hash, message, author_name, author_email, date, files 的字典列表。
    """
    # 使用 --format 自定义输出，用特殊分隔符分隔字段
    sep = "<<SEP>>"
    record_sep = "<<RECORD>>"
    fmt = f"{record_sep}%H{sep}%s{sep}%aN{sep}%aE{sep}%aI"

    args = [
        "log",
        f"--since={since}",
        f"--until={until}",
        f"--format={fmt}",
        "--name-only",
    ]

    output = _run_git(args, cwd)
    if not output.strip():
        return []

    commits: list[dict] = []
    # 按 record_sep 分割，跳过第一个空元素
    records = output.split(record_sep)

    for record in records:
        record = record.strip()
        if not record:
            continue

        lines = record.split("\n")
        if not lines:
            continue

        # 第一行包含 hash, message, author_name, author_email, date
        header = lines[0]
        parts = header.split(sep)
        if len(parts) < 5:
            continue

        commit_hash = parts[0].strip()
        message = parts[1].strip()
        author_name = parts[2].strip()
        author_email = parts[3].strip()
        date_str = parts[4].strip()

        # 剩余行是变更的文件名
        files = [f.strip() for f in lines[1:] if f.strip()]

        commits.append({
            "hash": commit_hash,
            "message": message,
            "author_name": author_name,
            "author_email": author_email,
            "date": date_str,
            "files": files,
        })

    return commits


def _get_numstat(
    cwd: str, since: str, until: str
) -> dict[str, dict[str, int]]:
    """获取每个提交中每个文件的增删行数。

    返回 {commit_hash: {file_path: {"added": N, "removed": N}}}
    """
    sep = "<<SEP>>"
    record_sep = "<<RECORD>>"
    fmt = f"{record_sep}%H{sep}"

    args = [
        "log",
        f"--since={since}",
        f"--until={until}",
        f"--format={fmt}",
        "--numstat",
    ]

    output = _run_git(args, cwd)
    if not output.strip():
        return {}

    result: dict[str, dict[str, int]] = {}
    records = output.split(record_sep)

    for record in records:
        record = record.strip()
        if not record:
            continue

        lines = record.split("\n")
        if not lines:
            continue

        # 第一行: hash<<SEP>>
        header = lines[0]
        commit_hash = header.split(sep)[0].strip()
        if not commit_hash:
            continue

        file_stats: dict[str, int] = {}
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                added_str, removed_str, file_path = parts[0], parts[1], parts[2]
                # 二进制文件显示为 "-"
                added = int(added_str) if added_str != "-" else 0
                removed = int(removed_str) if removed_str != "-" else 0
                file_stats[file_path] = added  # 暂存 added
                # 用特殊 key 存 removed
                result.setdefault(commit_hash, {})
                result[commit_hash][file_path] = added
                result[commit_hash][f"__removed__{file_path}"] = removed

    return result


def _build_contributors(
    commits: list[dict],
    numstat: dict[str, dict[str, int]],
    top_n: int,
) -> list[Contributor]:
    """构建贡献者统计列表。"""
    # 按 (name, email) 聚合
    contrib_map: dict[tuple[str, str], dict] = {}

    for commit in commits:
        key = (commit["author_name"], commit["author_email"])
        if key not in contrib_map:
            contrib_map[key] = {
                "name": commit["author_name"],
                "email": commit["author_email"],
                "commits": 0,
                "files_changed_set": set(),
                "lines_added": 0,
                "lines_removed": 0,
                "modules": defaultdict(int),
                "last_active": "",
            }

        info = contrib_map[key]
        info["commits"] += 1

        # 更新最后活跃时间
        if not info["last_active"] or commit["date"] > info["last_active"]:
            info["last_active"] = commit["date"]

        # 文件和行数统计
        commit_stats = numstat.get(commit["hash"], {})
        for f in commit["files"]:
            info["files_changed_set"].add(f)
            module = _infer_module(f)
            info["modules"][module] += 1
            info["lines_added"] += commit_stats.get(f, 0)
            info["lines_removed"] += commit_stats.get(f"__removed__{f}", 0)

    # 排序并取 top_n
    sorted_contribs = sorted(
        contrib_map.values(), key=lambda x: x["commits"], reverse=True
    )[:top_n]

    result: list[Contributor] = []
    for c in sorted_contribs:
        # top_modules: 按提交数排序取前 5
        top_modules = sorted(
            c["modules"].items(), key=lambda x: x[1], reverse=True
        )[:5]
        result.append(
            Contributor(
                name=c["name"],
                email=c["email"],
                commits=c["commits"],
                files_changed=len(c["files_changed_set"]),
                lines_added=c["lines_added"],
                lines_removed=c["lines_removed"],
                top_modules=[m[0] for m in top_modules],
                last_active=c["last_active"],
            )
        )

    return result


def _build_module_activity(
    commits: list[dict],
) -> list[ModuleActivity]:
    """构建模块活跃度列表。"""
    module_map: dict[str, dict] = {}

    for commit in commits:
        for f in commit["files"]:
            module = _infer_module(f)
            if module not in module_map:
                module_map[module] = {
                    "commits_set": set(),
                    "last_changed": "",
                    "contributors": defaultdict(int),
                }

            info = module_map[module]
            info["commits_set"].add(commit["hash"])

            if not info["last_changed"] or commit["date"] > info["last_changed"]:
                info["last_changed"] = commit["date"]

            info["contributors"][commit["author_name"]] += 1

    result: list[ModuleActivity] = []
    for module, info in sorted(
        module_map.items(), key=lambda x: len(x[1]["commits_set"]), reverse=True
    ):
        top_contributors = sorted(
            info["contributors"].items(), key=lambda x: x[1], reverse=True
        )[:5]
        result.append(
            ModuleActivity(
                module=module,
                commits=len(info["commits_set"]),
                last_changed=info["last_changed"],
                top_contributors=[c[0] for c in top_contributors],
            )
        )

    return result


def _build_recent_commits(commits: list[dict]) -> list[CommitInfo]:
    """构建近期提交列表。"""
    result: list[CommitInfo] = []
    for commit in commits:
        doc_changed = any(_is_doc_file(f) for f in commit["files"])
        result.append(
            CommitInfo(
                hash=commit["hash"],
                message=commit["message"],
                author=commit["author_name"],
                date=commit["date"],
                files=commit["files"],
                doc_files_changed=doc_changed,
            )
        )
    return result


def _build_stale_files(
    cwd: str,
    stale_threshold_days: int = _STALE_THRESHOLD_DAYS,
) -> list[StaleFile]:
    """检测过期文件。

    通过 git log 获取每个被跟踪文件的最后修改时间，
    超过阈值的标记为 likely_abandoned。
    """
    # 获取所有被跟踪的文件
    try:
        tracked_output = _run_git(["ls-files"], cwd)
    except RuntimeError:
        return []

    tracked_files = [f.strip() for f in tracked_output.strip().split("\n") if f.strip()]
    if not tracked_files:
        return []

    now = datetime.now(timezone.utc)
    stale_files: list[StaleFile] = []

    for file_path in tracked_files:
        try:
            date_output = _run_git(
                ["log", "-1", "--format=%aI", "--", file_path], cwd
            )
        except RuntimeError:
            continue

        date_str = date_output.strip()
        if not date_str:
            continue

        last_changed = _parse_iso_date(date_str)
        days_since = (now - last_changed).days

        stale_files.append(
            StaleFile(
                path=file_path,
                last_changed=date_str,
                days_since_change=days_since,
                likely_abandoned=days_since >= stale_threshold_days,
            )
        )

    # 按 days_since_change 降序排列
    stale_files.sort(key=lambda x: x.days_since_change, reverse=True)
    return stale_files


def run_git_changelog(input_params: GitChangelogInput) -> GitChangelogOutput:
    """执行 git-changelog 分析。

    Args:
        input_params: 输入参数

    Returns:
        GitChangelogOutput 包含贡献者、模块活跃度、近期提交、过期文件

    Raises:
        RuntimeError: 非 Git 仓库或 git 命令执行失败
    """
    cwd = input_params.project_root
    since = input_params.since
    until = input_params.until
    top_n = input_params.top_n

    # 验证是否为 Git 仓库
    _run_git(["rev-parse", "--git-dir"], cwd)

    # 获取提交历史
    commits = _get_commits(cwd, since, until)

    if not commits:
        return GitChangelogOutput()

    # 获取行数统计
    numstat = _get_numstat(cwd, since, until)

    # 构建各项输出
    contributors = _build_contributors(commits, numstat, top_n)
    module_activity = _build_module_activity(commits)
    recent_commits = _build_recent_commits(commits)
    stale_files = _build_stale_files(cwd)

    return GitChangelogOutput(
        contributors=contributors,
        module_activity=module_activity,
        recent_commits=recent_commits,
        stale_files=stale_files,
    )
