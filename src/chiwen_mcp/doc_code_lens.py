"""chiwen Knowledge Kit - doc-code-lens MCP 核心逻辑

文档与代码的双向透视镜。
Forward 模式：解析文档中的声明，在代码中搜索对应实现，未找到则标记为 drift。
Reverse 模式：扫描代码中的公开 API，检查文档中是否有对应记录，未记录则标记为 reverse_drift。
Full 模式：同时执行 Forward + Reverse 检测。
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, field
from pathlib import Path

from .code_reader import CodeReaderInput, scan_project
from .models import (
    Action,
    CodeReaderOutput,
    Confidence,
    DocCodeLensInput,
    DocCodeLensOutput,
    DriftSummary,
    DriftType,
    ForwardDrift,
    MatchedFile,
    Module,
    Priority,
    Recommendation,
    ReverseDrift,
)


# ── 文档声明数据结构 ──


class DocClaim:
    """从文档中提取的单个声明。"""

    def __init__(
        self,
        name: str,
        status: str,
        module: str,
        doc_file: str,
        doc_location: str,
    ):
        self.name = name
        self.status = status  # "[x]", "[ ]", "(废弃)", "(规划中)"
        self.module = module
        self.doc_file = doc_file
        self.doc_location = doc_location


class ModuleDescription:
    """从架构文档中提取的模块描述。"""

    def __init__(self, name: str, path: str, layer: str, doc_file: str, doc_location: str):
        self.name = name
        self.path = path
        self.layer = layer
        self.doc_file = doc_file
        self.doc_location = doc_location


# ── 文档解析 ──


def parse_capabilities(doc_content: str, doc_file: str = "2_CAPABILITIES.md") -> list[DocClaim]:
    """解析 2_CAPABILITIES.md，提取能力声明列表。

    支持的格式：
    - `- [x] 能力名称` → 已实现
    - `- [ ] 能力名称` → 未实现
    - `- (废弃) 能力名称` → 已废弃
    - `- (规划中) 能力名称` → 规划中

    按 `## 模块名` 分组。

    Args:
        doc_content: 2_CAPABILITIES.md 的文本内容
        doc_file: 文档文件名（用于标注来源）

    Returns:
        DocClaim 列表
    """
    claims: list[DocClaim] = []
    current_module = ""
    line_num = 0

    for line in doc_content.splitlines():
        line_num += 1
        stripped = line.strip()

        # 检测模块标题（## 开头）
        module_match = re.match(r"^##\s+(.+)$", stripped)
        if module_match:
            current_module = module_match.group(1).strip()
            continue

        # 检测能力声明
        # [x] 或 [ ] 格式
        checkbox_match = re.match(r"^-\s+\[([ xX])\]\s+(.+)$", stripped)
        if checkbox_match:
            check = checkbox_match.group(1)
            name = checkbox_match.group(2).strip()
            status = "[x]" if check.lower() == "x" else "[ ]"
            claims.append(DocClaim(
                name=name,
                status=status,
                module=current_module,
                doc_file=doc_file,
                doc_location=f"line {line_num}",
            ))
            continue

        # (废弃) 格式
        deprecated_match = re.match(r"^-\s+\(废弃\)\s+(.+)$", stripped)
        if deprecated_match:
            name = deprecated_match.group(1).strip()
            claims.append(DocClaim(
                name=name,
                status="(废弃)",
                module=current_module,
                doc_file=doc_file,
                doc_location=f"line {line_num}",
            ))
            continue

        # (规划中) 格式
        planned_match = re.match(r"^-\s+\(规划中\)\s+(.+)$", stripped)
        if planned_match:
            name = planned_match.group(1).strip()
            claims.append(DocClaim(
                name=name,
                status="(规划中)",
                module=current_module,
                doc_file=doc_file,
                doc_location=f"line {line_num}",
            ))
            continue

    return claims


def parse_architecture(doc_content: str, doc_file: str = "1_ARCHITECTURE.md") -> list[ModuleDescription]:
    """解析 1_ARCHITECTURE.md，提取模块描述。

    从「模块职责映射」表格中提取模块信息。
    表格格式：| 层级 | 核心文件/目录 | 职责说明 |

    Args:
        doc_content: 1_ARCHITECTURE.md 的文本内容
        doc_file: 文档文件名

    Returns:
        ModuleDescription 列表
    """
    modules: list[ModuleDescription] = []
    in_table = False
    header_passed = False
    line_num = 0

    for line in doc_content.splitlines():
        line_num += 1
        stripped = line.strip()

        # 检测「模块职责映射」章节
        if re.match(r"^##\s+.*模块职责映射", stripped):
            in_table = True
            header_passed = False
            continue

        # 遇到下一个 ## 标题时退出表格解析
        if in_table and re.match(r"^##\s+", stripped) and "模块职责映射" not in stripped:
            in_table = False
            continue

        if not in_table:
            continue

        # 跳过表头行和分隔行
        if stripped.startswith("|") and ("层级" in stripped or "---" in stripped or ":--" in stripped):
            header_passed = True
            continue

        if not header_passed:
            continue

        # 解析表格行
        table_match = re.match(r"^\|(.+)\|(.+)\|(.+)\|$", stripped)
        if table_match:
            layer = table_match.group(1).strip()
            path_raw = table_match.group(2).strip()
            desc = table_match.group(3).strip()

            # 提取路径（去掉反引号）
            path_clean = path_raw.strip("`").strip()

            # 从职责说明中提取模块名（格式：模块名（公开 API：...））
            name_match = re.match(r"^(.+?)（", desc)
            name = name_match.group(1).strip() if name_match else desc

            if layer == "—" and path_clean == "—":
                continue

            modules.append(ModuleDescription(
                name=name,
                path=path_clean,
                layer=layer,
                doc_file=doc_file,
                doc_location=f"line {line_num}",
            ))

    return modules


# ── Forward Drift 检测 ──


def _normalize_name(name: str) -> str:
    """将名称标准化为可比较的形式。

    将驼峰、下划线、连字符等统一为小写单词列表。

    Args:
        name: 原始名称

    Returns:
        标准化后的小写字符串
    """
    # 去掉常见前缀/后缀修饰
    cleaned = name.strip()
    # 将驼峰拆分为单词
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", cleaned)
    # 将下划线和连字符替换为空格
    words = re.sub(r"[_\-/]", " ", words)
    # 去掉非字母数字字符（保留中文）
    words = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", words)
    return words.lower().strip()


def _extract_keywords(name: str) -> list[str]:
    """从名称中提取关键词列表。

    Args:
        name: 能力名称或模块名称

    Returns:
        关键词列表（小写）
    """
    normalized = _normalize_name(name)
    # 按空格分割，过滤掉太短的词
    words = [w for w in normalized.split() if len(w) > 1]
    return words


def _search_in_code(
    claim_name: str,
    code_modules: list[Module],
    code_files_content: dict[str, str],
) -> tuple[list[MatchedFile], Confidence, DriftType]:
    """在代码中搜索与文档声明匹配的实现。

    搜索策略：
    1. 精确匹配：在模块公开 API 或文件内容中找到完全匹配
    2. 部分匹配：关键词部分匹配
    3. 未找到：无任何匹配

    Args:
        claim_name: 文档中的能力声明名称
        code_modules: code-reader 扫描到的模块列表
        code_files_content: 文件路径 → 文件内容的映射

    Returns:
        (匹配文件列表, 置信度, drift类型) 元组
    """
    matched_files: list[MatchedFile] = []
    keywords = _extract_keywords(claim_name)
    claim_lower = _normalize_name(claim_name)

    if not keywords:
        return [], Confidence.LOW, DriftType.MISSING

    # 策略 1：在模块公开 API 中精确匹配
    for mod in code_modules:
        for api in mod.public_api:
            api_lower = _normalize_name(api)
            if claim_lower == api_lower or claim_lower in api_lower or api_lower in claim_lower:
                matched_files.append(MatchedFile(
                    file=mod.path,
                    line=0,
                    confidence=Confidence.HIGH,
                ))

    if matched_files:
        return matched_files, Confidence.HIGH, DriftType.EXACT

    # 策略 2：在文件内容中搜索关键词
    partial_matches: list[MatchedFile] = []
    for filepath, content in code_files_content.items():
        content_lower = content.lower()
        matched_count = sum(1 for kw in keywords if kw in content_lower)
        match_ratio = matched_count / len(keywords) if keywords else 0

        if match_ratio >= 0.8:
            # 高匹配度 - 尝试找到具体行号
            line_num = _find_keyword_line(content, keywords)
            partial_matches.append(MatchedFile(
                file=filepath,
                line=line_num,
                confidence=Confidence.HIGH,
            ))
        elif match_ratio >= 0.5:
            line_num = _find_keyword_line(content, keywords)
            partial_matches.append(MatchedFile(
                file=filepath,
                line=line_num,
                confidence=Confidence.MEDIUM,
            ))

    if partial_matches:
        # 按置信度排序，取最高的
        best_confidence = max(m.confidence.value for m in partial_matches)
        if best_confidence == Confidence.HIGH.value:
            return partial_matches, Confidence.HIGH, DriftType.EXACT
        return partial_matches, Confidence.MEDIUM, DriftType.PARTIAL

    # 策略 3：宽松关键词搜索
    loose_matches: list[MatchedFile] = []
    for filepath, content in code_files_content.items():
        content_lower = content.lower()
        matched_count = sum(1 for kw in keywords if kw in content_lower)
        if matched_count > 0 and len(keywords) > 0:
            match_ratio = matched_count / len(keywords)
            if match_ratio >= 0.3:
                line_num = _find_keyword_line(content, keywords)
                loose_matches.append(MatchedFile(
                    file=filepath,
                    line=line_num,
                    confidence=Confidence.LOW,
                ))

    if loose_matches:
        return loose_matches, Confidence.LOW, DriftType.PARTIAL

    # 未找到任何匹配
    return [], Confidence.HIGH, DriftType.MISSING


def _find_keyword_line(content: str, keywords: list[str]) -> int:
    """在文件内容中找到关键词首次出现的行号。

    Args:
        content: 文件内容
        keywords: 关键词列表

    Returns:
        行号（1-based），未找到返回 0
    """
    for i, line in enumerate(content.splitlines(), 1):
        line_lower = line.lower()
        if any(kw in line_lower for kw in keywords):
            return i
    return 0


def _read_code_files(project_root: str, structure: list) -> dict[str, str]:
    """读取项目中的代码文件内容（排除 .docs/ 目录下的文件）。

    Args:
        project_root: 项目根目录
        structure: code-reader 扫描到的文件结构

    Returns:
        文件相对路径 → 文件内容的映射
    """
    files_content: dict[str, str] = {}
    # 排除 .docs/ 目录下的文件，避免文档内容干扰代码搜索
    excluded_prefixes = (".docs/", ".docs\\")
    for node in structure:
        if node.type != "file":
            continue
        if any(node.path.startswith(p) for p in excluded_prefixes):
            continue
        filepath = os.path.join(project_root, node.path)
        try:
            with open(filepath, encoding="utf-8", errors="ignore") as f:
                content = f.read()
            files_content[node.path] = content
        except (OSError, IOError):
            continue
    return files_content


def check_forward_drift(
    doc_claims: list[DocClaim],
    code_modules: list[Module],
    code_files_content: dict[str, str],
) -> list[ForwardDrift]:
    """对每个文档声明在代码中搜索匹配，生成 Forward Drift 列表。

    仅检查状态为 [x]（已实现）的声明。
    [ ]、(废弃)、(规划中) 的声明不参与 drift 检测。

    Args:
        doc_claims: 文档中提取的声明列表
        code_modules: code-reader 扫描到的模块列表
        code_files_content: 文件路径 → 文件内容的映射

    Returns:
        ForwardDrift 列表
    """
    drifts: list[ForwardDrift] = []

    for claim in doc_claims:
        # 仅检查标记为 [x] 的声明
        if claim.status != "[x]":
            continue

        matched_files, confidence, drift_type = _search_in_code(
            claim.name, code_modules, code_files_content
        )

        if drift_type == DriftType.MISSING:
            drifts.append(ForwardDrift(
                doc_claim=claim.name,
                doc_file=claim.doc_file,
                doc_location=claim.doc_location,
                matched_files=[],
                confidence=Confidence.HIGH,
                drift_type=DriftType.MISSING,
                drift_detail=f"文档声称 '{claim.name}' 已实现，但在代码中未找到对应实现",
            ))
        elif drift_type == DriftType.PARTIAL:
            drifts.append(ForwardDrift(
                doc_claim=claim.name,
                doc_file=claim.doc_file,
                doc_location=claim.doc_location,
                matched_files=matched_files,
                confidence=confidence,
                drift_type=DriftType.PARTIAL,
                drift_detail=f"文档声称 '{claim.name}' 已实现，代码中找到部分匹配但不完全确定",
            ))

    return drifts


# ── 修复建议生成 ──


def generate_recommendations(drifts: list[ForwardDrift]) -> list[Recommendation]:
    """基于 drift 项生成修复建议。

    优先级规则：
    - MISSING + HIGH confidence → P0（update_doc：降级为 [ ] 或移除 [x]）
    - MISSING + MEDIUM/LOW confidence → P1（verify_manually）
    - PARTIAL + HIGH confidence → P1（update_doc）
    - PARTIAL + MEDIUM/LOW confidence → P2（verify_manually）

    Args:
        drifts: ForwardDrift 列表

    Returns:
        Recommendation 列表
    """
    recommendations: list[Recommendation] = []

    for drift in drifts:
        if drift.drift_type == DriftType.MISSING:
            if drift.confidence == Confidence.HIGH:
                recommendations.append(Recommendation(
                    priority=Priority.P0,
                    action=Action.UPDATE_DOC,
                    target=drift.doc_file,
                    reason=f"能力 '{drift.doc_claim}' 在代码中未找到实现，建议将 [x] 降级为 [ ] 或添加 drift 说明",
                ))
            else:
                recommendations.append(Recommendation(
                    priority=Priority.P1,
                    action=Action.VERIFY_MANUALLY,
                    target=drift.doc_file,
                    reason=f"能力 '{drift.doc_claim}' 可能在代码中不存在，建议人工确认",
                ))
        elif drift.drift_type == DriftType.PARTIAL:
            if drift.confidence in (Confidence.HIGH, Confidence.MEDIUM):
                recommendations.append(Recommendation(
                    priority=Priority.P1,
                    action=Action.UPDATE_DOC,
                    target=drift.doc_file,
                    reason=f"能力 '{drift.doc_claim}' 在代码中仅部分匹配，建议更新文档描述",
                ))
            else:
                recommendations.append(Recommendation(
                    priority=Priority.P2,
                    action=Action.VERIFY_MANUALLY,
                    target=drift.doc_file,
                    reason=f"能力 '{drift.doc_claim}' 匹配度较低，建议人工确认实现状态",
                ))

    return recommendations


# ── Reverse Drift 检测 ──


def check_reverse_drift(
    code_modules: list[Module],
    code_files_content: dict[str, str],
    doc_claims: list[DocClaim],
) -> list[ReverseDrift]:
    """扫描代码中的公开 API，检查文档中是否有对应记录。

    对每个模块的 public_api 中的每个 API，在文档声明中搜索匹配。
    未在文档中记录的能力标记为 ReverseDrift。

    Args:
        code_modules: code-reader 扫描到的模块列表
        code_files_content: 文件路径 → 文件内容的映射
        doc_claims: 文档中提取的声明列表

    Returns:
        ReverseDrift 列表
    """
    reverse_drifts: list[ReverseDrift] = []

    # 构建文档声明的关键词索引，用于快速匹配
    claim_keywords_map: list[tuple[DocClaim, list[str]]] = []
    for claim in doc_claims:
        kws = _extract_keywords(claim.name)
        claim_keywords_map.append((claim, kws))

    # 所有文档声明的标准化名称集合
    claim_names_normalized = {_normalize_name(c.name) for c in doc_claims}

    for mod in code_modules:
        for api_name in mod.public_api:
            api_normalized = _normalize_name(api_name)
            api_keywords = _extract_keywords(api_name)

            if not api_keywords:
                continue

            # 策略 1：精确匹配 — API 名称与某个文档声明完全匹配
            exact_match = False
            matched_doc_files: list[str] = []
            for claim_norm in claim_names_normalized:
                if api_normalized == claim_norm or api_normalized in claim_norm or claim_norm in api_normalized:
                    exact_match = True
                    break

            if exact_match:
                continue

            # 策略 2：关键词匹配 — API 的关键词在文档声明中有足够覆盖
            keyword_match = False
            for claim, claim_kws in claim_keywords_map:
                if not claim_kws:
                    continue
                # 检查 API 关键词是否被文档声明覆盖
                matched_count = sum(1 for kw in api_keywords if kw in claim_kws)
                ratio = matched_count / len(api_keywords)
                if ratio >= 0.5:
                    keyword_match = True
                    matched_doc_files.append(claim.doc_file)
                    break

            if keyword_match:
                continue

            # 未匹配 — 标记为 reverse drift
            reverse_drifts.append(ReverseDrift(
                file=mod.path,
                location=f"module:{mod.name}",
                capability=api_name,
                doc_mentioned=False,
                doc_files=matched_doc_files,
            ))

    return reverse_drifts


def generate_reverse_recommendations(reverse_drifts: list[ReverseDrift]) -> list[Recommendation]:
    """基于 reverse drift 项生成修复建议。

    所有 reverse drift 建议动作为 create_doc 或 update_doc。
    优先级：P1（代码中存在但文档未记录的能力应尽快补充文档）。

    Args:
        reverse_drifts: ReverseDrift 列表

    Returns:
        Recommendation 列表
    """
    recommendations: list[Recommendation] = []

    for drift in reverse_drifts:
        recommendations.append(Recommendation(
            priority=Priority.P1,
            action=Action.UPDATE_DOC,
            target="2_CAPABILITIES.md",
            reason=f"代码能力 '{drift.capability}'（文件: {drift.file}）未在文档中记录，建议补充到能力矩阵",
        ))

    return recommendations


# ── 主函数 ──


def run_doc_code_lens(input_params: DocCodeLensInput) -> DocCodeLensOutput:
    """doc-code-lens 主函数。

    支持三种模式：
    - forward: 检查文档声明在代码中是否有对应实现
    - reverse: 检查代码能力在文档中是否有记录
    - full: 同时执行 forward + reverse

    流程：
    1. 验证参数
    2. 检查 .docs/ 目录是否存在
    3. 读取文档内容
    4. 调用 code-reader 扫描代码
    5. 按模式执行 Drift 检测
    6. 生成修复建议
    7. 汇总统计

    Args:
        input_params: DocCodeLensInput 参数

    Returns:
        DocCodeLensOutput 完整输出

    Raises:
        ValueError: 当 project_root 不存在或 .docs/ 目录不存在时
    """
    project_root = input_params.project_root

    # 验证路径
    if not project_root or not project_root.strip():
        raise ValueError("参数错误：project_root 为必填项，不能为空")

    if not os.path.isdir(project_root):
        raise ValueError(f"路径不存在或不是目录：{project_root}")

    # 检查 .docs/ 目录
    docs_dir = os.path.join(project_root, ".docs")
    if not os.path.isdir(docs_dir):
        raise ValueError(f".docs/ 目录不存在，请先执行 init 命令：{docs_dir}")

    # 读取文档内容
    doc_claims: list[DocClaim] = []
    arch_modules: list[ModuleDescription] = []

    # 解析 2_CAPABILITIES.md
    cap_path = os.path.join(docs_dir, "2_CAPABILITIES.md")
    if input_params.doc_path:
        cap_path = os.path.join(docs_dir, input_params.doc_path)

    if os.path.isfile(cap_path):
        with open(cap_path, encoding="utf-8") as f:
            cap_content = f.read()
        doc_file_name = os.path.basename(cap_path)
        doc_claims = parse_capabilities(cap_content, doc_file_name)

    # 解析 1_ARCHITECTURE.md（仅在非指定文档模式下）
    if not input_params.doc_path:
        arch_path = os.path.join(docs_dir, "1_ARCHITECTURE.md")
        if os.path.isfile(arch_path):
            with open(arch_path, encoding="utf-8") as f:
                arch_content = f.read()
            arch_modules = parse_architecture(arch_content)

    # 调用 code-reader 扫描代码
    cr_input = CodeReaderInput(project_root=project_root)
    cr_output = scan_project(cr_input)

    # 读取代码文件内容
    code_files_content = _read_code_files(project_root, cr_output.structure)

    mode = input_params.mode or "full"

    # 执行 Forward Drift 检测
    forward_drifts: list[ForwardDrift] = []

    if mode in ("forward", "full"):
        forward_drifts = check_forward_drift(
            doc_claims, cr_output.modules, code_files_content
        )

        # 检查架构文档中的模块是否在代码中存在
        for arch_mod in arch_modules:
            found = False
            for code_mod in cr_output.modules:
                if (_normalize_name(arch_mod.name) == _normalize_name(code_mod.name)
                        or arch_mod.path == code_mod.path):
                    found = True
                    break
            if not found and arch_mod.path != "—":
                # 检查路径是否实际存在
                full_path = os.path.join(project_root, arch_mod.path)
                if not os.path.exists(full_path):
                    forward_drifts.append(ForwardDrift(
                        doc_claim=f"模块 '{arch_mod.name}' (路径: {arch_mod.path})",
                        doc_file=arch_mod.doc_file,
                        doc_location=arch_mod.doc_location,
                        matched_files=[],
                        confidence=Confidence.HIGH,
                        drift_type=DriftType.MISSING,
                        drift_detail=f"架构文档中描述的模块 '{arch_mod.name}' 在代码中未找到",
                    ))

    # 执行 Reverse Drift 检测
    reverse_drifts: list[ReverseDrift] = []

    if mode in ("reverse", "full"):
        reverse_drifts = check_reverse_drift(
            cr_output.modules, code_files_content, doc_claims
        )

    # 生成修复建议（合并 forward + reverse）
    recommendations = generate_recommendations(forward_drifts)
    recommendations.extend(generate_reverse_recommendations(reverse_drifts))

    # 汇总统计
    total_checked = len(doc_claims) + len(arch_modules)
    # reverse 模式下，每个模块的每个 public_api 也算检查项
    if mode in ("reverse", "full"):
        total_api_count = sum(len(mod.public_api) for mod in cr_output.modules)
        total_checked += total_api_count

    drifted = len(forward_drifts) + len(reverse_drifts)
    in_sync = total_checked - drifted

    summary = DriftSummary(
        total_checked=total_checked,
        in_sync=max(0, in_sync),
        drifted=drifted,
        missing_in_code=sum(1 for d in forward_drifts if d.drift_type == DriftType.MISSING),
        missing_in_doc=len(reverse_drifts),
    )

    return DocCodeLensOutput(
        summary=summary,
        forward_drift=forward_drifts,
        reverse_drift=reverse_drifts,
        recommendations=recommendations,
    )
