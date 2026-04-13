"""chiwen Knowledge Kit - 文档模板引擎

支持自定义文档模板，基于 string.Template 的 $variable 语法。
用户可在 .docs/templates/ 目录下放置自定义模板覆盖内置默认模板。
"""

from __future__ import annotations

import os
import string
from dataclasses import dataclass, field


@dataclass
class TemplateResult:
    """模板渲染结果"""

    content: str
    used_custom: bool  # 是否使用了自定义模板
    warnings: list[str] = field(default_factory=list)


@dataclass
class InitTemplatesResult:
    """init_templates 结果"""

    exported: list[str]  # 成功导出的文件列表
    skipped: list[str]  # 已存在被跳过的文件列表


# ── 内置默认模板 ──

BUILTIN_TEMPLATES: dict[str, str] = {
    "0_INDEX.md": """\
# $project_name 知识文档索引

> 本文档体系由 chiwen Knowledge Kit 自动生成和维护

## 文档清单

| 文件 | 职责 | 更新方式 |
|:--|:--|:--|
| 0_INDEX.md | 本文件，索引 | AI 自动维护 |
| 1_ARCHITECTURE.md | 架构、模块映射、数据流 | AI 扫描代码生成，drift 时自动更新 |
| 2_CAPABILITIES.md | 能力矩阵（Checkbox） | AI 检测代码变更后同步 |
| 3_ROADMAP.md | 路线图（近/中/远期） | 人工维护，AI 辅助格式化 |
| 4_DECISIONS.md | 架构决策记录（ADR） | 人工记录，AI 辅助格式化 |
| 5_CHANGELOG.md | 文档变更日志 | AI 全自动维护 |
| users/@{{username}}/ | 个人空间 | 个人维护 |

## 外部资源链接

- 测试计划：{{链接到团队实际使用的测试平台}}
- 项目管理：{{链接到 Jira / Linear / GitHub Projects 等}}
""",
    "1_ARCHITECTURE.md": """\
# $project_name 架构与流程

## 1. 技术选型

$modules

## 2. 入口文件

$entry_points

## 3. API 路由

$api_routes

## 4. 依赖

$dependencies
""",
    "2_CAPABILITIES.md": """\
# $project_name 能力矩阵

> 本文件由 AI 自动维护，仅对真实可用能力打勾。
> 虚假勾选（文档写了代码没实现）是最高级别的文档事故。

$capabilities
""",
    "3_ROADMAP.md": """\
# $project_name 路线图

## 近期计划（Next Sprint / Next Month）

- 进行中项目
  - 验收标准：...

## 中期计划（Next Quarter）

- 计划项目1
  - 目标：...

## 远期愿景（Future）

- 愿景描述
""",
    "4_DECISIONS.md": """\
# $project_name 架构决策记录（ADR）

> 本文件记录项目中的重大架构决策。每条 ADR 包含状态、背景、决策和后果四个章节。

## ADR 格式说明

每条 ADR 应遵循以下格式：

---

# ADR-{序号}：{决策标题}

## 状态

Accepted | Deprecated | Superseded by ADR-{XXX}

## 背景

{做这个决策时的上下文和问题陈述}

## 决策

{核心决策内容}

## 后果

### 正面

- ...

### 负面

- ...

---
日期：{YYYY-MM-DD}

---

> 请在下方添加新的 ADR 记录。
""",
    "5_CHANGELOG.md": """\
# $project_name 文档变更日志

> 本文件由 AI 自动维护，不建议手动编辑

## $generated_at

| 变更类型 | 文档 | 摘要 |
|:--|:--|:--|
| [初始化] | 全部文档 | 由 init 命令自动生成文档骨架 |
""",
}

SUPPORTED_TEMPLATES = list(BUILTIN_TEMPLATES.keys())


class TemplateEngine:
    """文档模板引擎。

    支持的模板文件：
    - 0_INDEX.md, 1_ARCHITECTURE.md, 2_CAPABILITIES.md
    - 3_ROADMAP.md, 4_DECISIONS.md, 5_CHANGELOG.md

    模板变量（$variable 语法）：
    - $project_name: 项目名称
    - $generated_at: 生成时间（ISO 8601）
    - $modules: 模块列表（Markdown 格式）
    - $capabilities: 能力列表（Markdown 格式）
    - $entry_points: 入口文件列表
    - $api_routes: API 路由列表
    - $dependencies: 依赖列表
    """

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.templates_dir = os.path.join(project_root, ".docs", "templates")

    def load_template(self, template_name: str) -> tuple[string.Template, bool]:
        """加载模板，优先自定义模板，兜底内置模板。

        Returns:
            (Template 对象, 是否为自定义模板)
        """
        # 尝试加载自定义模板
        custom_path = os.path.join(self.templates_dir, template_name)
        if os.path.isfile(custom_path):
            with open(custom_path, encoding="utf-8") as f:
                custom_content = f.read()
            return string.Template(custom_content), True

        # 兜底内置默认模板
        builtin_content = BUILTIN_TEMPLATES.get(template_name, "")
        return string.Template(builtin_content), False

    def render(
        self,
        template_name: str,
        variables: dict[str, str],
    ) -> TemplateResult:
        """渲染模板。语法错误时回退到内置默认模板。"""
        template, is_custom = self.load_template(template_name)
        warnings: list[str] = []

        if is_custom:
            try:
                # 先用 substitute 检测语法错误（无效占位符）
                # substitute 会对无效的 ${...} 语法抛出 ValueError
                template.substitute(variables)
            except KeyError:
                # KeyError 表示缺少变量，不是语法错误，safe_substitute 可以处理
                pass
            except (ValueError, TypeError) as e:
                warnings.append(
                    f"自定义模板 '{template_name}' 语法错误，回退到内置默认模板: {e}"
                )
                # 回退到内置默认模板
                builtin_content = BUILTIN_TEMPLATES.get(template_name, "")
                builtin_template = string.Template(builtin_content)
                content = builtin_template.safe_substitute(variables)
                return TemplateResult(
                    content=content, used_custom=False, warnings=warnings
                )

            # 语法正确，使用 safe_substitute 渲染（容忍缺失变量）
            content = template.safe_substitute(variables)
            return TemplateResult(
                content=content, used_custom=True, warnings=warnings
            )

        # 使用内置模板
        content = template.safe_substitute(variables)
        return TemplateResult(content=content, used_custom=False, warnings=warnings)

    @staticmethod
    def init_templates(project_root: str) -> InitTemplatesResult:
        """将内置默认模板导出到 .docs/templates/。

        已存在的同名文件不覆盖。
        """
        templates_dir = os.path.join(project_root, ".docs", "templates")
        os.makedirs(templates_dir, exist_ok=True)

        exported: list[str] = []
        skipped: list[str] = []

        for name, content in BUILTIN_TEMPLATES.items():
            filepath = os.path.join(templates_dir, name)
            if os.path.isfile(filepath):
                skipped.append(name)
            else:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                exported.append(name)

        return InitTemplatesResult(exported=exported, skipped=skipped)
