# 文档协作防覆盖 Spec

## Why
多人协作时，团队成员在不同分支/不同时间运行 init、sync 容易导致 `.docs/` 被整体重写、产生大范围 diff 与 Git 合并冲突，甚至误覆盖他人手工维护内容。

## What Changes
- 为 init / sync 增加“协作安全”默认策略：默认不覆盖、尽量增量修改、输出可审计的变更摘要
- 为 `.docs/` 引入可选的锁与状态元数据，减少并发运行造成的相互覆盖
- 提升生成的确定性：对能力项、分组、输出顺序做稳定化，降低不同环境/不同时间的 diff 波动
- 在 Git 仓库中增加可选的工作区保护：支持在工作区脏/文档被改动时 fail-fast 或显式允许

## Impact
- Affected specs: init、sync、能力矩阵生成、changelog 追加、协作安全
- Affected code:
  - `src/chiwen_mcp/doc_generator.py`
  - `src/chiwen_mcp/sync.py`
  - `src/chiwen_mcp/changelog_utils.py`
  - `src/chiwen_mcp/code_reader.py`
  - `src/chiwen_mcp/server.py`
  - `src/skill/SKILL.md`

## ADDED Requirements
### Requirement: 协作安全（锁）
系统 SHALL 在对 `.docs/` 进行写操作前支持“互斥锁”机制，避免同一工作区内的并发 init/sync 相互覆盖。

#### Scenario: 成功获取锁
- **WHEN** 用户触发 init 或 sync
- **AND** `.docs/.chiwen.lock` 不存在或已过期
- **THEN** 系统创建锁并继续执行
- **AND** 执行完成后释放锁

#### Scenario: 锁冲突
- **WHEN** 用户触发 init 或 sync
- **AND** `.docs/.chiwen.lock` 存在且未过期
- **THEN** 系统终止执行并返回明确错误信息（包含锁持有信息、建议等待/手动清理方式）

### Requirement: 协作安全（状态元数据）
系统 SHALL 在 `.docs/` 目录内维护状态元数据文件，用于记录上次生成/同步的关键信息，帮助判断“本次执行是否可能覆盖他人改动”。

#### Scenario: 记录状态
- **WHEN** init 或 sync 成功完成
- **THEN** 系统更新状态元数据（包含 generator 版本、执行时间、生成策略、受影响文档列表）

#### Scenario: 检测潜在覆盖风险
- **WHEN** sync 执行前检测到状态元数据与当前工作区/目标文档不一致（例如：状态文件指向的基线与当前不匹配）
- **THEN** 系统按策略 fail-fast 或要求显式确认参数（例如 `allow_risky=true`）后才继续

### Requirement: Git 工作区保护（可选）
系统 SHALL 在检测到 Git 仓库时支持“工作区保护”策略，减少多人协作下未提交变更导致的覆盖与冲突。

#### Scenario: 默认保护（fail-fast）
- **WHEN** 在 Git 仓库中运行 sync
- **AND** 工作区存在未提交变更（至少包含 `.docs/`）
- **THEN** 系统默认终止并提示先提交/暂存或在参数中显式允许

#### Scenario: 显式允许脏工作区
- **WHEN** 在 Git 仓库中运行 sync
- **AND** 用户显式传入允许参数（例如 `allow_dirty=true`）
- **THEN** 系统继续执行并在结果摘要中标记该风险

### Requirement: 确定性输出（减少 diff）
系统 SHALL 以确定性规则生成/更新 `2_CAPABILITIES.md`，使同一代码输入在不同执行环境下产出稳定一致。

#### Scenario: 稳定排序
- **WHEN** sync 需要追加/更新能力项
- **THEN** 新增能力项按稳定规则排序（例如按分组后字母序/自然序）
- **AND** 避免随机顺序导致的 diff 抖动

## MODIFIED Requirements
### Requirement: init 默认不覆盖
init（或等价的文档初始化入口） SHALL 在 `.docs/` 已存在时默认不覆盖已有文件，除非显式指定覆盖策略。

#### Scenario: `.docs/` 已存在（默认）
- **WHEN** 用户执行 init
- **AND** `.docs/` 已存在
- **THEN** 系统拒绝整体重写并返回可选策略提示（覆盖 / 仅补齐缺失文件 / 取消）

### Requirement: sync 以增量方式更新能力矩阵
sync SHALL 尽量以“最小变更”更新 `2_CAPABILITIES.md`，避免整文件重写引发大范围合并冲突。

#### Scenario: 仅追加缺失能力
- **WHEN** 代码新增能力，文档缺失
- **THEN** sync 仅在对应分组追加缺失项
- **AND** 不重排用户已存在的条目（除非开启格式化参数）

## REMOVED Requirements
### Requirement: 由 LLM 直接生成能力矩阵（默认路径）
**Reason**：LLM 在多人协作场景下会产生不可控的输出差异，放大合并冲突与误覆盖风险。  
**Migration**：默认改为确定性工具生成；LLM 仅用于编排与展示，或在显式开关下参与润色但不得改动结构化锚点。  
