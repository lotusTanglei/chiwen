# chiwen-knowledge-kit 能力矩阵

> 本文件由 AI 自动维护，仅对真实可用能力打勾。
> 虚假勾选（文档写了代码没实现）是最高级别的文档事故。

## MCP 工具

- [ ] code-reader — 深度扫描代码库，返回项目结构化知识
- [ ] init-docs — 生成骨架文件，返回 skipped_for_llm
- [ ] doc-code-lens — 文档与代码双向 drift 检测
- [ ] sync-docs — 同步文档与代码，修复 drift
- [ ] status-report — 生成健康度报告
- [ ] onboard-user — 创建个人空间
- [ ] git-changelog — Git 历史分析

## 文档生成

- [ ] 四阶段 init 流程（扫描 → 骨架 → 全局文档 → 模块文档）
- [ ] 自定义模板覆盖（.docs/templates/）
- [ ] 镜像代码目录的模块文档结构（modules/）

## 文档同步

- [ ] Forward drift 修复（虚假勾选降级）
- [ ] Reverse drift 修复（未记录能力追加到模块文档）
- [ ] Git dirty 检查和 HEAD 一致性检查

## 健康度报告

- [ ] 同步率计算
- [ ] 活跃贡献者和过期文档
- [ ] Markdown 报告导出

## 协作与安全

- [ ] 文件锁机制（防止多人同时写 .docs/）
- [ ] .gitattributes merge=union 减少合并冲突

## 自动化集成

- [ ] GitHub Actions / GitLab CI 配置模板
- [ ] Git pre-commit hook
- [ ] cron 定时健康度报告
