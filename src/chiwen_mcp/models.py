"""chiwen Knowledge Kit - 共享数据模型

所有 MCP 工具共享的数据模型定义。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ── code-reader 数据模型 ──


@dataclass
class ProjectInfo:
    """项目基本信息"""

    name: str = ""
    language: str = ""
    framework: str = ""
    package_manager: str = ""
    monorepo: bool = False
    packages: list[str] = field(default_factory=list)


@dataclass
class FileNode:
    """目录/文件节点"""

    path: str = ""
    type: str = "file"  # "dir" | "file"
    purpose: str = ""
    line_count: int = 0


@dataclass
class EntryPoint:
    """入口文件"""

    file: str = ""
    type: str = "main"  # "main" | "router" | "config" | "handler"
    description: str = ""


@dataclass
class Module:
    """模块信息，支持递归子模块"""

    name: str = ""
    path: str = ""
    layer: str = ""
    dependencies: list[str] = field(default_factory=list)
    public_api: list[str] = field(default_factory=list)
    children: list[Module] = field(default_factory=list)


@dataclass
class DataModel:
    """数据模型定义"""

    name: str = ""
    location: str = ""
    fields: list[str] = field(default_factory=list)


@dataclass
class ApiRoute:
    """API 路由"""

    method: str = "GET"  # "GET" | "POST" | "PUT" | "DELETE" | "PATCH"
    path: str = ""
    handler: str = ""
    description: str = ""


@dataclass
class Dependencies:
    """项目依赖"""

    direct: list[str] = field(default_factory=list)
    major: list[str] = field(default_factory=list)


@dataclass
class ScanMeta:
    """扫描元数据"""

    total_files: int = 0
    total_lines: int = 0
    scan_duration_ms: int = 0
    scanned_at: str = ""  # ISO8601


@dataclass
class CodeReaderOutput:
    """code-reader MCP 工具的完整输出"""

    project_info: ProjectInfo = field(default_factory=ProjectInfo)
    structure: list[FileNode] = field(default_factory=list)
    entry_points: list[EntryPoint] = field(default_factory=list)
    modules: list[Module] = field(default_factory=list)
    data_models: list[DataModel] = field(default_factory=list)
    api_routes: list[ApiRoute] = field(default_factory=list)
    dependencies: Dependencies = field(default_factory=Dependencies)
    scan_meta: ScanMeta = field(default_factory=ScanMeta)


# ── doc-code-lens 枚举 ──


class Confidence(Enum):
    """置信度等级"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DriftType(Enum):
    """Drift 类型"""

    EXACT = "exact"
    PARTIAL = "partial"
    MISSING = "missing"


class Priority(Enum):
    """修复优先级"""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class Action(Enum):
    """建议动作"""

    UPDATE_DOC = "update_doc"
    CREATE_DOC = "create_doc"
    VERIFY_MANUALLY = "verify_manually"


# ── doc-code-lens 数据模型 ──


@dataclass
class DocCodeLensInput:
    """doc-code-lens MCP 工具的输入参数"""

    project_root: str
    doc_path: str | None = None
    mode: str = "full"  # "forward" | "reverse" | "full"


@dataclass
class DriftSummary:
    """Drift 检测总览统计"""

    total_checked: int = 0
    in_sync: int = 0
    drifted: int = 0
    missing_in_code: int = 0
    missing_in_doc: int = 0


@dataclass
class MatchedFile:
    """代码中的匹配文件"""

    file: str = ""
    line: int = 0
    confidence: Confidence = Confidence.LOW


@dataclass
class ForwardDrift:
    """文档→代码 drift 项"""

    doc_claim: str = ""
    doc_file: str = ""
    doc_location: str = ""
    matched_files: list[MatchedFile] = field(default_factory=list)
    confidence: Confidence = Confidence.LOW
    drift_type: DriftType = DriftType.MISSING
    drift_detail: str = ""


@dataclass
class ReverseDrift:
    """代码→文档 drift 项"""

    file: str = ""
    location: str = ""
    capability: str = ""
    doc_mentioned: bool = False
    doc_files: list[str] = field(default_factory=list)


@dataclass
class Recommendation:
    """修复建议"""

    priority: Priority = Priority.P2
    action: Action = Action.VERIFY_MANUALLY
    target: str = ""
    reason: str = ""


@dataclass
class DocCodeLensOutput:
    """doc-code-lens MCP 工具的完整输出"""

    summary: DriftSummary = field(default_factory=DriftSummary)
    forward_drift: list[ForwardDrift] = field(default_factory=list)
    reverse_drift: list[ReverseDrift] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)


# ── Changelog 数据模型 ──


@dataclass
class ChangelogEntry:
    """变更日志条目"""

    date: str = ""  # YYYY-MM-DD
    change_type: str = ""  # 能力同步 / 架构更新 / ADR新增 / ...
    target_doc: str = ""  # 目标文档文件名
    summary: str = ""  # 变更摘要


@dataclass
class ChangelogGroup:
    """按日期分组的变更日志"""

    date: str = ""
    changes: list[ChangelogEntry] = field(default_factory=list)


@dataclass
class ChangelogDoc:
    """完整的 Changelog 文档模型"""

    title: str = ""
    header_lines: list[str] = field(default_factory=list)  # 标题和提示行
    groups: list[ChangelogGroup] = field(default_factory=list)


# ── git-changelog 数据模型 ──


@dataclass
class GitChangelogInput:
    """git-changelog MCP 工具的输入参数"""

    project_root: str
    since: str = "30 days ago"
    until: str = "now"
    top_n: int = 10
    group_by: str = "person"  # "person" | "module" | "file"


@dataclass
class Contributor:
    """贡献者信息"""

    name: str = ""
    email: str = ""
    commits: int = 0
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    top_modules: list[str] = field(default_factory=list)
    last_active: str = ""  # ISO8601


@dataclass
class ModuleActivity:
    """模块活跃度"""

    module: str = ""
    commits: int = 0
    last_changed: str = ""  # ISO8601
    top_contributors: list[str] = field(default_factory=list)


@dataclass
class CommitInfo:
    """提交信息"""

    hash: str = ""
    message: str = ""
    author: str = ""
    date: str = ""  # ISO8601
    files: list[str] = field(default_factory=list)
    doc_files_changed: bool = False


@dataclass
class StaleFile:
    """过期文件"""

    path: str = ""
    last_changed: str = ""  # ISO8601
    days_since_change: int = 0
    likely_abandoned: bool = False


@dataclass
class GitChangelogOutput:
    """git-changelog MCP 工具的完整输出"""

    contributors: list[Contributor] = field(default_factory=list)
    module_activity: list[ModuleActivity] = field(default_factory=list)
    recent_commits: list[CommitInfo] = field(default_factory=list)
    stale_files: list[StaleFile] = field(default_factory=list)
