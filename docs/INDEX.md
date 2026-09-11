# 文档索引 (L1)

> 此文件为全局文档目录，每次对话按需查阅。

## 系统文档（长期知识）

- [系统需求基线](system/requirements.md) — 全部功能需求的唯一权威基线（spec 完成后增量更新）
- [系统模块摘要](system/SUMMARY.md) — L2 各模块一句话概述
- [系统架构](system/architecture.md) — 分层架构、技术栈、应用工厂
- [数据库设计](system/database.md) — MongoDB 集合、字段、索引
- [API 接口](system/api.md) — 全部 API 端点列表
- 模块详情（L3）：`docs/system/modules/` 下 8 个模块文档

## 功能 spec 与实施计划

- `docs/superpowers/specs/YYYY-MM-DD-<feature>-design.md` — 每个功能的需求+设计文档
- `docs/superpowers/plans/YYYY-MM-DD-<feature>.md` — 实施计划，checkbox 即进度
- 新对话启动时扫描 plans 中未勾选项（详见 CLAUDE.md）

## Claude 工作规范

- `docs/claude/` — 拆分自 CLAUDE.md，经 `@import` 每次会话自动加载：架构模式 / 编码行为准则 / spec 流程 / 测试规范

## 文档模板

- [spec 设计文档模板](templates/spec-design-template.md) — 需求+设计合一；计划格式由 superpowers:writing-plans 技能约定

## 历史参考

- `backend/reqspec.md`、`backend/techspec.md` — 早期规格书，已被 `docs/system/requirements.md` 取代
