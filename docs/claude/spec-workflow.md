# Spec 驱动开发（Spec-Driven Development）

项目采用 superpowers 原生的 spec 驱动开发。每个功能两份产物，全部用中文撰写：

| 产物 | 路径 | 内容 |
|------|------|------|
| spec 设计文档 | `docs/superpowers/specs/YYYY-MM-DD-<feature>-design.md` | 需求（用户故事 + EARS 验收标准）+ 设计（架构、数据模型、接口、测试策略），模板见 `docs/templates/spec-design-template.md` |
| 实施计划 | `docs/superpowers/plans/YYYY-MM-DD-<feature>.md` | checkbox 任务清单，即持久化进度 |

配套技能：需求探索用 brainstorming，计划编写用 writing-plans，执行用 subagent-driven-development 或 executing-plans。

## 阶段门禁（必须遵守）

任何新功能开发必须依次完成，**每一步经用户确认后才能进入下一步**：

1. 写 spec 设计文档（需求章节 + 设计章节）→ 用户确认
2. 写实施计划 → 用户确认 → 才能开始写代码

严禁跳过阶段直接写代码，即使需求看起来很简单。

## EARS 验收标准格式

```
当 <触发条件/事件> 时，系统应 <预期行为>。
在 <前置状态> 下，当 <触发条件> 时，系统应 <预期行为>。
```

每条验收标准应能直接映射为一个 pytest 测试用例。

## 任务执行规则

- 一次只执行一个 task，按实施计划顺序进行
- 每个 task 遵循 TDD：先写失败测试 → 实现 → 重构
- task 完成后立即把计划中的 `- [ ]` 改为 `- [x]` 并提交代码（进度以计划文件为准，无需额外状态文件）
- 提交前 `pytest backend/tests/` 必须全部通过
- 每个 task 标注 `_覆盖需求：N.M_` 保持追溯性

## 会话恢复规则（必须遵守）

每次新对话开始时，扫描 `docs/superpowers/plans/*.md` 中的未勾选项（`- [ ]`）。若存在，主动提示用户：

> 「检测到未完成的计划：<feature>，进度 x/y。是否继续？」

若全部完成，正常开始新任务。

## 需求基线增量更新（必须遵守）

`docs/system/requirements.md` 是系统需求的唯一权威基线。每个实施计划的全部 task 完成后：

1. 将该 spec 设计文档需求章节的内容合并进基线对应模块章节（新增 `REQ-<模块>-NNN` 条目或修订既有条目）
2. 在基线文档末尾的变更记录表登记一行

> ⚠️ **代码提交 ≠ spec 完成**。基线文档同步更新后，一个 spec 才算真正完成。

## 文档索引

全局文档索引见 `docs/INDEX.md`；系统长期知识（架构/数据库/API/模块详情）在 `docs/system/`，开发前按需查阅。
