# chiwen-knowledge-kit 路线图

## v0.1.0（当前版本）

- [x] code-reader MCP 工具
- [x] doc-code-lens MCP 工具（forward + reverse + full）
- [x] git-changelog MCP 工具
- [x] init 命令（扫描代码 → 生成 5+X 文档骨架 → 自动 onboard）
- [x] sync 命令（drift 检测 → 能力矩阵同步 → changelog 追加）
- [x] status 命令（健康度报告 + git 集成）
- [x] onboard 命令（个人空间 + 阅读清单）
- [x] CI / pre-commit / cron 集成模板

## v0.2.0（下一版本）

- [ ] doc-code-lens 置信度算法优化
- [ ] sync 命令支持 reverse drift 自动修复
- [ ] status 命令输出 Markdown 报告文件
- [ ] 支持自定义文档模板

## v0.3.0

- [ ] 多语言项目支持增强（Go、Rust、Java）
- [ ] 增量扫描（仅扫描变更文件）
- [ ] 文档版本对比（diff 两次 sync 之间的变化）

## 远期愿景

- [ ] 发布到 PyPI
- [ ] Web Dashboard（可视化健康度报告）
