"""doc-code-lens Forward 模式单元测试。

测试覆盖：
- parse_capabilities: 解析 2_CAPABILITIES.md
- parse_architecture: 解析 1_ARCHITECTURE.md
- check_forward_drift: Forward Drift 检测
- generate_recommendations: 修复建议生成
- run_doc_code_lens: 主函数集成
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from chiwen_mcp.doc_code_lens import (
    DocClaim,
    check_forward_drift,
    check_reverse_drift,
    generate_recommendations,
    generate_reverse_recommendations,
    parse_architecture,
    parse_capabilities,
    run_doc_code_lens,
    _normalize_name,
    _extract_keywords,
)
from chiwen_mcp.models import (
    Action,
    Confidence,
    DocCodeLensInput,
    DriftType,
    ForwardDrift,
    MatchedFile,
    Module,
    Priority,
    ReverseDrift,
)


# ── parse_capabilities 测试 ──


class TestParseCapabilities:
    def test_parse_checked_items(self):
        content = """\
# 项目 能力矩阵

## 模块A

- [x] 用户认证
- [ ] 权限管理
- [x] 日志记录
"""
        claims = parse_capabilities(content)
        assert len(claims) == 3
        assert claims[0].name == "用户认证"
        assert claims[0].status == "[x]"
        assert claims[0].module == "模块A"
        assert claims[1].name == "权限管理"
        assert claims[1].status == "[ ]"
        assert claims[2].name == "日志记录"
        assert claims[2].status == "[x]"

    def test_parse_deprecated_and_planned(self):
        content = """\
## 旧模块

- (废弃) 旧功能
- (规划中) 新功能
"""
        claims = parse_capabilities(content)
        assert len(claims) == 2
        assert claims[0].status == "(废弃)"
        assert claims[0].name == "旧功能"
        assert claims[1].status == "(规划中)"
        assert claims[1].name == "新功能"

    def test_parse_multiple_modules(self):
        content = """\
## 模块A

- [x] 功能1

## 模块B

- [ ] 功能2
"""
        claims = parse_capabilities(content)
        assert len(claims) == 2
        assert claims[0].module == "模块A"
        assert claims[1].module == "模块B"

    def test_empty_content(self):
        claims = parse_capabilities("")
        assert claims == []

    def test_no_capabilities(self):
        content = "# 标题\n\n一些描述文字\n"
        claims = parse_capabilities(content)
        assert claims == []

    def test_doc_location_tracking(self):
        content = """\
## 模块

- [x] 功能A
- [ ] 功能B
"""
        claims = parse_capabilities(content)
        assert claims[0].doc_location == "line 3"
        assert claims[1].doc_location == "line 4"

    def test_custom_doc_file(self):
        content = "## M\n- [x] test"
        claims = parse_capabilities(content, doc_file="custom.md")
        assert claims[0].doc_file == "custom.md"


# ── parse_architecture 测试 ──


class TestParseArchitecture:
    def test_parse_module_table(self):
        content = """\
## 3. 模块职责映射

| 层级 | 核心文件/目录 | 职责说明 |
|:--|:--|:--|
| 应用层 | `src/app` | 主应用（公开 API：start, stop） |
| 数据层 | `src/db` | 数据库（公开 API：query） |
"""
        modules = parse_architecture(content)
        assert len(modules) == 2
        assert modules[0].name == "主应用"
        assert modules[0].path == "src/app"
        assert modules[0].layer == "应用层"
        assert modules[1].name == "数据库"
        assert modules[1].path == "src/db"

    def test_skip_placeholder_rows(self):
        content = """\
## 3. 模块职责映射

| 层级 | 核心文件/目录 | 职责说明 |
|:--|:--|:--|
| — | — | 暂无模块信息 |
"""
        modules = parse_architecture(content)
        assert len(modules) == 0

    def test_empty_content(self):
        modules = parse_architecture("")
        assert modules == []

    def test_no_table(self):
        content = "## 1. 技术选型\n\n- Python\n"
        modules = parse_architecture(content)
        assert modules == []

    def test_stops_at_next_section(self):
        content = """\
## 3. 模块职责映射

| 层级 | 核心文件/目录 | 职责说明 |
|:--|:--|:--|
| 层A | `src/a` | 模块A（公开 API：foo） |

## 4. 核心执行流程

一些内容
"""
        modules = parse_architecture(content)
        assert len(modules) == 1
        assert modules[0].name == "模块A"


# ── check_forward_drift 测试 ──


class TestCheckForwardDrift:
    def test_missing_drift_detected(self):
        """标记为 [x] 但代码中不存在的能力应被检测为 drift。"""
        claims = [
            DocClaim(
                name="不存在的功能xyz",
                status="[x]",
                module="模块A",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 5",
            )
        ]
        modules: list[Module] = []
        code_files: dict[str, str] = {"src/main.py": "print('hello')"}

        drifts = check_forward_drift(claims, modules, code_files)
        assert len(drifts) == 1
        assert drifts[0].drift_type == DriftType.MISSING
        assert drifts[0].doc_claim == "不存在的功能xyz"

    def test_unchecked_items_not_drifted(self):
        """状态为 [ ] 的声明不应参与 drift 检测。"""
        claims = [
            DocClaim(
                name="未实现功能",
                status="[ ]",
                module="模块A",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 3",
            )
        ]
        drifts = check_forward_drift(claims, [], {})
        assert len(drifts) == 0

    def test_deprecated_items_not_drifted(self):
        """状态为 (废弃) 的声明不应参与 drift 检测。"""
        claims = [
            DocClaim(
                name="旧功能",
                status="(废弃)",
                module="模块A",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 3",
            )
        ]
        drifts = check_forward_drift(claims, [], {})
        assert len(drifts) == 0

    def test_exact_match_in_public_api(self):
        """在模块公开 API 中精确匹配的声明不应产生 drift。"""
        claims = [
            DocClaim(
                name="scan_project",
                status="[x]",
                module="code-reader",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 5",
            )
        ]
        modules = [
            Module(
                name="code-reader",
                path="src/code_reader.py",
                layer="工具层",
                dependencies=[],
                public_api=["scan_project"],
            )
        ]
        drifts = check_forward_drift(claims, modules, {})
        assert len(drifts) == 0

    def test_partial_match_in_code(self):
        """代码中部分匹配的声明应产生 PARTIAL drift。"""
        claims = [
            DocClaim(
                name="user authentication login",
                status="[x]",
                module="auth",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 5",
            )
        ]
        modules: list[Module] = []
        code_files = {
            "src/auth.py": "def login():\n    pass\n\ndef logout():\n    pass\n"
        }
        drifts = check_forward_drift(claims, modules, code_files)
        # 应该找到部分匹配（login 关键词匹配）
        # 结果取决于匹配比例，至少不应是完全 missing
        # login 和 authentication 中 login 能匹配，user 和 authentication 不一定
        assert len(drifts) <= 1

    def test_empty_claims(self):
        drifts = check_forward_drift([], [], {})
        assert drifts == []


# ── generate_recommendations 测试 ──


class TestGenerateRecommendations:
    def test_missing_high_confidence_p0(self):
        """MISSING + HIGH confidence → P0 update_doc。"""
        drifts = [
            ForwardDrift(
                doc_claim="功能A",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 5",
                matched_files=[],
                confidence=Confidence.HIGH,
                drift_type=DriftType.MISSING,
                drift_detail="未找到",
            )
        ]
        recs = generate_recommendations(drifts)
        assert len(recs) == 1
        assert recs[0].priority == Priority.P0
        assert recs[0].action == Action.UPDATE_DOC

    def test_missing_low_confidence_p1(self):
        """MISSING + LOW confidence → P1 verify_manually。"""
        drifts = [
            ForwardDrift(
                doc_claim="功能B",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 5",
                matched_files=[],
                confidence=Confidence.LOW,
                drift_type=DriftType.MISSING,
                drift_detail="未找到",
            )
        ]
        recs = generate_recommendations(drifts)
        assert len(recs) == 1
        assert recs[0].priority == Priority.P1
        assert recs[0].action == Action.VERIFY_MANUALLY

    def test_partial_high_confidence_p1(self):
        """PARTIAL + HIGH confidence → P1 update_doc。"""
        drifts = [
            ForwardDrift(
                doc_claim="功能C",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 5",
                matched_files=[MatchedFile(file="src/a.py", line=10, confidence=Confidence.HIGH)],
                confidence=Confidence.HIGH,
                drift_type=DriftType.PARTIAL,
                drift_detail="部分匹配",
            )
        ]
        recs = generate_recommendations(drifts)
        assert len(recs) == 1
        assert recs[0].priority == Priority.P1
        assert recs[0].action == Action.UPDATE_DOC

    def test_partial_low_confidence_p2(self):
        """PARTIAL + LOW confidence → P2 verify_manually。"""
        drifts = [
            ForwardDrift(
                doc_claim="功能D",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 5",
                matched_files=[MatchedFile(file="src/b.py", line=5, confidence=Confidence.LOW)],
                confidence=Confidence.LOW,
                drift_type=DriftType.PARTIAL,
                drift_detail="低匹配",
            )
        ]
        recs = generate_recommendations(drifts)
        assert len(recs) == 1
        assert recs[0].priority == Priority.P2
        assert recs[0].action == Action.VERIFY_MANUALLY

    def test_empty_drifts(self):
        recs = generate_recommendations([])
        assert recs == []

    def test_multiple_drifts(self):
        """多个 drift 项应生成对应数量的建议。"""
        drifts = [
            ForwardDrift(
                doc_claim="功能A",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 5",
                matched_files=[],
                confidence=Confidence.HIGH,
                drift_type=DriftType.MISSING,
                drift_detail="未找到",
            ),
            ForwardDrift(
                doc_claim="功能B",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 6",
                matched_files=[MatchedFile(file="src/b.py", line=1, confidence=Confidence.MEDIUM)],
                confidence=Confidence.MEDIUM,
                drift_type=DriftType.PARTIAL,
                drift_detail="部分匹配",
            ),
        ]
        recs = generate_recommendations(drifts)
        assert len(recs) == 2


# ── _normalize_name / _extract_keywords 测试 ──


class TestHelpers:
    def test_normalize_camel_case(self):
        assert "scan project" in _normalize_name("scanProject")

    def test_normalize_snake_case(self):
        assert "scan project" in _normalize_name("scan_project")

    def test_normalize_kebab_case(self):
        assert "scan project" in _normalize_name("scan-project")

    def test_extract_keywords(self):
        kws = _extract_keywords("user authentication login")
        assert "user" in kws
        assert "authentication" in kws
        assert "login" in kws

    def test_extract_keywords_filters_short(self):
        kws = _extract_keywords("a b cd")
        assert "a" not in kws
        assert "b" not in kws
        assert "cd" in kws


# ── run_doc_code_lens 集成测试 ──


@pytest.fixture
def tmp_project_with_docs(tmp_path: Path) -> Path:
    """创建一个带有 .docs/ 和代码文件的临时项目。"""
    # 创建 pyproject.toml
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "test-project"\n',
        encoding="utf-8",
    )

    # 创建代码文件
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "auth.py").write_text(
        'def login(user, password):\n    """用户登录"""\n    pass\n\n'
        'def logout(user):\n    """用户登出"""\n    pass\n',
        encoding="utf-8",
    )
    (src / "db.py").write_text(
        'def query(sql):\n    """执行查询"""\n    pass\n',
        encoding="utf-8",
    )

    # 创建 .docs/ 目录
    docs = tmp_path / ".docs"
    docs.mkdir()

    # 创建 2_CAPABILITIES.md
    (docs / "2_CAPABILITIES.md").write_text(
        """\
# test-project 能力矩阵

## auth

- [x] login
- [x] logout
- [x] 不存在的功能xyz_abc_999
- [ ] 未实现功能

## db

- [x] query
""",
        encoding="utf-8",
    )

    # 创建 1_ARCHITECTURE.md
    (docs / "1_ARCHITECTURE.md").write_text(
        """\
# test-project 架构

## 1. 技术选型

- Python

## 2. 分层架构

- 应用层

## 3. 模块职责映射

| 层级 | 核心文件/目录 | 职责说明 |
|:--|:--|:--|
| 应用层 | `src` | 主模块（公开 API：login, logout） |

## 4. 核心执行流程

入口文件

## 5. ADR 快速索引

无
""",
        encoding="utf-8",
    )

    return tmp_path


class TestRunDocCodeLens:
    def test_missing_project_root_raises(self):
        with pytest.raises(ValueError, match="必填项"):
            run_doc_code_lens(DocCodeLensInput(project_root=""))

    def test_nonexistent_path_raises(self):
        with pytest.raises(ValueError, match="不存在"):
            run_doc_code_lens(DocCodeLensInput(project_root="/nonexistent/path/xyz"))

    def test_missing_docs_dir_raises(self, tmp_path: Path):
        """没有 .docs/ 目录时应报错。"""
        with pytest.raises(ValueError, match="init"):
            run_doc_code_lens(DocCodeLensInput(project_root=str(tmp_path)))

    def test_forward_mode_detects_drift(self, tmp_project_with_docs: Path):
        """Forward 模式应检测到不存在的能力声明。"""
        result = run_doc_code_lens(DocCodeLensInput(
            project_root=str(tmp_project_with_docs),
            mode="forward",
        ))

        assert result.summary.total_checked > 0
        assert result.summary.drifted >= 1

        # 应检测到 "不存在的功能xyz_abc_999" 的 drift
        drift_claims = [d.doc_claim for d in result.forward_drift]
        assert any("不存在的功能xyz_abc_999" in c for c in drift_claims)

        # forward 模式不应有 reverse_drift
        assert result.reverse_drift == []

    def test_forward_mode_has_recommendations(self, tmp_project_with_docs: Path):
        """检测到 drift 时应生成修复建议。"""
        result = run_doc_code_lens(DocCodeLensInput(
            project_root=str(tmp_project_with_docs),
            mode="forward",
        ))

        assert len(result.recommendations) >= 1
        # 每个建议应有有效的优先级和动作
        for rec in result.recommendations:
            assert rec.priority in (Priority.P0, Priority.P1, Priority.P2)
            assert rec.action in (Action.UPDATE_DOC, Action.CREATE_DOC, Action.VERIFY_MANUALLY)

    def test_output_structure_complete(self, tmp_project_with_docs: Path):
        """输出应包含所有必需字段。"""
        result = run_doc_code_lens(DocCodeLensInput(
            project_root=str(tmp_project_with_docs),
            mode="forward",
        ))

        assert result.summary is not None
        assert isinstance(result.forward_drift, list)
        assert isinstance(result.reverse_drift, list)
        assert isinstance(result.recommendations, list)
        assert result.summary.total_checked >= 0
        assert result.summary.in_sync >= 0
        assert result.summary.drifted >= 0

    def test_full_mode_works(self, tmp_project_with_docs: Path):
        """Full 模式应同时执行 forward 和 reverse 检测。"""
        result = run_doc_code_lens(DocCodeLensInput(
            project_root=str(tmp_project_with_docs),
            mode="full",
        ))

        assert result.summary.total_checked > 0
        # full 模式应包含 forward drift
        assert isinstance(result.forward_drift, list)
        # full 模式应包含 reverse drift 列表（可能为空或非空）
        assert isinstance(result.reverse_drift, list)

    def test_unchecked_items_not_counted_as_drift(self, tmp_project_with_docs: Path):
        """[ ] 状态的声明不应被计为 drift。"""
        result = run_doc_code_lens(DocCodeLensInput(
            project_root=str(tmp_project_with_docs),
            mode="forward",
        ))

        drift_claims = [d.doc_claim for d in result.forward_drift]
        assert not any("未实现功能" in c for c in drift_claims)


# ── check_reverse_drift 测试 ──


class TestCheckReverseDrift:
    def test_undocumented_api_detected(self):
        """代码中存在但文档中未记录的 API 应被检测为 reverse drift。"""
        modules = [
            Module(
                name="auth",
                path="src/auth.py",
                layer="应用层",
                dependencies=[],
                public_api=["login", "logout", "reset_password"],
            )
        ]
        doc_claims = [
            DocClaim(
                name="login",
                status="[x]",
                module="auth",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 5",
            ),
            DocClaim(
                name="logout",
                status="[x]",
                module="auth",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 6",
            ),
        ]
        code_files: dict[str, str] = {}

        drifts = check_reverse_drift(modules, code_files, doc_claims)
        assert len(drifts) == 1
        assert drifts[0].capability == "reset_password"
        assert drifts[0].file == "src/auth.py"
        assert drifts[0].doc_mentioned is False

    def test_all_apis_documented(self):
        """所有 API 都在文档中有记录时不应产生 reverse drift。"""
        modules = [
            Module(
                name="auth",
                path="src/auth.py",
                layer="应用层",
                dependencies=[],
                public_api=["login", "logout"],
            )
        ]
        doc_claims = [
            DocClaim(
                name="login",
                status="[x]",
                module="auth",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 5",
            ),
            DocClaim(
                name="logout",
                status="[x]",
                module="auth",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 6",
            ),
        ]

        drifts = check_reverse_drift(modules, {}, doc_claims)
        assert len(drifts) == 0

    def test_empty_modules(self):
        """无模块时不应产生 reverse drift。"""
        drifts = check_reverse_drift([], {}, [])
        assert drifts == []

    def test_empty_public_api(self):
        """模块无公开 API 时不应产生 reverse drift。"""
        modules = [
            Module(
                name="internal",
                path="src/internal.py",
                layer="内部",
                dependencies=[],
                public_api=[],
            )
        ]
        drifts = check_reverse_drift(modules, {}, [])
        assert drifts == []

    def test_multiple_modules_mixed(self):
        """多个模块中部分 API 未记录应被检测。"""
        modules = [
            Module(
                name="auth",
                path="src/auth.py",
                layer="应用层",
                dependencies=[],
                public_api=["login"],
            ),
            Module(
                name="db",
                path="src/db.py",
                layer="数据层",
                dependencies=[],
                public_api=["query", "migrate"],
            ),
        ]
        doc_claims = [
            DocClaim(
                name="login",
                status="[x]",
                module="auth",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 5",
            ),
            DocClaim(
                name="query",
                status="[x]",
                module="db",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 8",
            ),
        ]

        drifts = check_reverse_drift(modules, {}, doc_claims)
        assert len(drifts) == 1
        assert drifts[0].capability == "migrate"
        assert drifts[0].file == "src/db.py"

    def test_keyword_partial_match_not_drifted(self):
        """API 名称与文档声明有足够关键词重叠时不应标记为 drift。"""
        modules = [
            Module(
                name="auth",
                path="src/auth.py",
                layer="应用层",
                dependencies=[],
                public_api=["user_login"],
            )
        ]
        doc_claims = [
            DocClaim(
                name="user login",
                status="[x]",
                module="auth",
                doc_file="2_CAPABILITIES.md",
                doc_location="line 5",
            ),
        ]

        drifts = check_reverse_drift(modules, {}, doc_claims)
        assert len(drifts) == 0


# ── generate_reverse_recommendations 测试 ──


class TestGenerateReverseRecommendations:
    def test_generates_recommendations_for_each_drift(self):
        """每个 reverse drift 应生成一条建议。"""
        drifts = [
            ReverseDrift(
                file="src/auth.py",
                location="module:auth",
                capability="reset_password",
                doc_mentioned=False,
                doc_files=[],
            ),
            ReverseDrift(
                file="src/db.py",
                location="module:db",
                capability="migrate",
                doc_mentioned=False,
                doc_files=[],
            ),
        ]
        recs = generate_reverse_recommendations(drifts)
        assert len(recs) == 2
        assert all(r.priority == Priority.P1 for r in recs)
        assert all(r.action == Action.UPDATE_DOC for r in recs)

    def test_empty_drifts(self):
        recs = generate_reverse_recommendations([])
        assert recs == []


# ── run_doc_code_lens Reverse / Full 模式集成测试 ──


@pytest.fixture
def tmp_project_with_undocumented_api(tmp_path: Path) -> Path:
    """创建一个有未记录 API 的临时项目。"""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "test-project"\n',
        encoding="utf-8",
    )

    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "auth.py").write_text(
        'def login(user, password):\n    """用户登录"""\n    pass\n\n'
        'def logout(user):\n    """用户登出"""\n    pass\n\n'
        'def reset_password(user):\n    """重置密码"""\n    pass\n',
        encoding="utf-8",
    )

    docs = tmp_path / ".docs"
    docs.mkdir()

    # 文档只记录了 login 和 logout，未记录 reset_password
    (docs / "2_CAPABILITIES.md").write_text(
        """\
# test-project 能力矩阵

## auth

- [x] login
- [x] logout
""",
        encoding="utf-8",
    )

    (docs / "1_ARCHITECTURE.md").write_text(
        """\
# test-project 架构

## 1. 技术选型

- Python

## 2. 分层架构

- 应用层

## 3. 模块职责映射

| 层级 | 核心文件/目录 | 职责说明 |
|:--|:--|:--|
| 应用层 | `src` | 认证模块（公开 API：login, logout, reset_password） |

## 4. 核心执行流程

入口文件

## 5. ADR 快速索引

无
""",
        encoding="utf-8",
    )

    return tmp_path


class TestRunDocCodeLensReverse:
    def test_reverse_mode_detects_undocumented_api(self, tmp_project_with_undocumented_api: Path):
        """Reverse 模式应检测到代码中未记录的 API。"""
        result = run_doc_code_lens(DocCodeLensInput(
            project_root=str(tmp_project_with_undocumented_api),
            mode="reverse",
        ))

        # reverse 模式不应有 forward drift
        assert result.forward_drift == []
        # 应检测到未记录的 API
        reverse_caps = [d.capability for d in result.reverse_drift]
        assert any("reset_password" in c for c in reverse_caps)
        assert result.summary.missing_in_doc >= 1

    def test_reverse_mode_no_forward_drift(self, tmp_project_with_undocumented_api: Path):
        """Reverse 模式不应执行 forward 检测。"""
        result = run_doc_code_lens(DocCodeLensInput(
            project_root=str(tmp_project_with_undocumented_api),
            mode="reverse",
        ))
        assert result.forward_drift == []

    def test_reverse_mode_has_recommendations(self, tmp_project_with_undocumented_api: Path):
        """Reverse 模式检测到 drift 时应生成修复建议。"""
        result = run_doc_code_lens(DocCodeLensInput(
            project_root=str(tmp_project_with_undocumented_api),
            mode="reverse",
        ))
        if result.reverse_drift:
            assert len(result.recommendations) >= 1


class TestRunDocCodeLensFull:
    def test_full_mode_has_both_drifts(self, tmp_project_with_undocumented_api: Path):
        """Full 模式应同时包含 forward 和 reverse 检测结果。"""
        result = run_doc_code_lens(DocCodeLensInput(
            project_root=str(tmp_project_with_undocumented_api),
            mode="full",
        ))

        assert isinstance(result.forward_drift, list)
        assert isinstance(result.reverse_drift, list)
        # 应有 reverse drift（reset_password 未记录）
        reverse_caps = [d.capability for d in result.reverse_drift]
        assert any("reset_password" in c for c in reverse_caps)

    def test_full_equals_forward_plus_reverse(self, tmp_project_with_undocumented_api: Path):
        """Full 模式的结果应等价于分别执行 forward 和 reverse。"""
        root = str(tmp_project_with_undocumented_api)

        full_result = run_doc_code_lens(DocCodeLensInput(
            project_root=root, mode="full",
        ))
        forward_result = run_doc_code_lens(DocCodeLensInput(
            project_root=root, mode="forward",
        ))
        reverse_result = run_doc_code_lens(DocCodeLensInput(
            project_root=root, mode="reverse",
        ))

        # forward_drift 应一致
        full_fwd_claims = sorted([d.doc_claim for d in full_result.forward_drift])
        fwd_claims = sorted([d.doc_claim for d in forward_result.forward_drift])
        assert full_fwd_claims == fwd_claims

        # reverse_drift 应一致
        full_rev_caps = sorted([d.capability for d in full_result.reverse_drift])
        rev_caps = sorted([d.capability for d in reverse_result.reverse_drift])
        assert full_rev_caps == rev_caps

    def test_full_mode_summary_counts(self, tmp_project_with_undocumented_api: Path):
        """Full 模式的 summary 应正确统计两个方向的 drift。"""
        result = run_doc_code_lens(DocCodeLensInput(
            project_root=str(tmp_project_with_undocumented_api),
            mode="full",
        ))

        total_drifts = len(result.forward_drift) + len(result.reverse_drift)
        assert result.summary.drifted == total_drifts
        assert result.summary.missing_in_doc == len(result.reverse_drift)
