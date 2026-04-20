# chiwen-knowledge-kit 能力矩阵

> 本文件由 AI 自动维护，仅对真实可用能力打勾。
> 虚假勾选（文档写了代码没实现）是最高级别的文档事故。

## MCP 工具（对外暴露的能力）

- [ ] code-reader — 深度扫描代码库，返回项目信息、模块结构、入口文件、API 路由、依赖关系
- [ ] init-docs — 生成 .docs/ 骨架文件（INDEX、ROADMAP、DECISIONS、CHANGELOG），核心文档由 LLM 撰写
- [ ] doc-code-lens — 文档与代码双向 drift 检测（forward + reverse + full 三种模式）
- [ ] sync-docs — 同步 .docs/ 与代码，修复 drift 并追加 changelog
- [ ] status-report — 生成文档健康度报告，可选导出 Markdown 文件
- [ ] onboard-user — 创建个人空间（notepad.md + cache.md）并返回阅读清单
- [ ] git-changelog — 从 Git 历史提取贡献者统计、模块活跃度、过期文件

## 文档生成（init 命令）

- [ ] 扫描项目代码并提取结构化知识（CodeReaderOutput）
- [ ] 生成 0_INDEX.md 文档索引
- [ ] 生成 3_ROADMAP.md 路线图模板
- [ ] 生成 4_DECISIONS.md ADR 模板
- [ ] 生成 5_CHANGELOG.md 变更日志模板
- [ ] 更新 .gitignore 排除 notepad.md
- [ ] 更新 .gitattributes 设置 merge=union 策略
- [ ] 支持自定义模板覆盖（.docs/templates/）
- [ ] 支持 overwrite / fill_missing 模式

## 文档同步（sync 命令）

- [ ] 调用 doc-code-lens full 模式检测双向 drift
- [ ] Forward drift 修复 — 虚假勾选 [x] 降级为 [ ] 并附 drift 说明
- [ ] Reverse drift 修复 — 未记录的代码能力自动追加到能力矩阵
- [ ] 新增代码能力自动标记 [x]
- [ ] 追加 5_CHANGELOG.md 变更记录（保留已有内容）
- [ ] Git dirty 检查（防止未提交变更被覆盖）
- [ ] Git HEAD 一致性检查（防止跨分支覆盖）

## 健康度报告（status 命令）

- [ ] 计算文档同步率（in_sync / total_checked）
- [ ] 汇总待处理 drift 项清单（forward + reverse）
- [ ] 集成 git-changelog 获取活跃贡献者
- [ ] 集成 git-changelog 获取过期文档列表
- [ ] git-changelog 不可用时优雅降级
- [ ] 导出 Markdown 报告文件（.docs/STATUS_REPORT.md）

## 成员引导（onboard 命令）

- [ ] 自动获取用户名（git config → USER → USERNAME）
- [ ] 创建个人空间 .docs/users/@{username}/
- [ ] 生成 notepad.md 私人笔记（不进 git）
- [ ] 生成 cache.md 工作偏好（工作风格 / 当前关注点 / 已知盲区）
- [ ] 输出项目阅读清单

## Drift 检测引擎

- [ ] Forward drift — 文档声称已实现，代码中搜索匹配
- [ ] Reverse drift — 代码中的公开 API，文档中搜索记录
- [ ] 多因子加权评分算法（精确名称匹配 40% + 关键词覆盖率 25% + 代码结构匹配 20% + 路径相关性 15%）
- [ ] 置信度三级映射（HIGH ≥ 0.7 / MEDIUM ≥ 0.4 / LOW < 0.4）
- [ ] 修复建议生成（P0/P1/P2 优先级）

## 协作与安全

- [ ] 文件锁机制（防止多人同时写 .docs/，TTL 自动过期）
- [ ] 状态文件记录上次操作的 Git HEAD
- [ ] .gitattributes merge=union 减少合并冲突

## 自动化集成

- [ ] GitHub Actions CI 配置模板
- [ ] GitLab CI 配置模板
- [ ] Git pre-commit hook
- [ ] pre-commit 框架 YAML 配置
- [ ] cron 定时健康度报告（周报/月报）

## 自定义模板引擎

- [ ] 从 .docs/templates/ 加载自定义模板（优先于内置模板）
- [ ] 基于 string.Template 的 $variable 语法
- [ ] 模板语法错误时自动回退到内置默认模板
- [ ] init_templates 导出内置模板供用户自定义
