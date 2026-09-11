# 设计文档：CLAUDE.md 改造为 Spec 驱动的 AI 开发流程

- 日期：2026-07-14
- 分支：sprint_credit_limit
- 状态：已完成（修订版 v2：spec 体系由 Kiro 三件套改为 superpowers 原生工作流）

## 1. 背景与目标

当前 CLAUDE.md 采用「7 阶段迭代流程 + TASK_STATE.md 任务记忆系统」，文档负担重（每个迭代 7 份文档）、状态维护规则复杂（5 个保存触发点）。本次改造将其替换为 **superpowers 原生的 spec 驱动开发体系**：

- 每个功能两份产物：spec 设计文档（需求 + 设计合一）+ 实施计划（checkbox 任务清单）
- 阶段门禁：需求与设计确认 → 计划确认 → 才能写代码
- 计划文件的 checkbox 即持久化进度，取代 TASK_STATE.md
- AI 实际执行的技能流程（brainstorming → writing-plans → 执行）与项目文档规范完全一致，不维护两套体系
- 全部文档用中文撰写
- 新建一份**系统需求基线文档**，全面描述当前系统，后续每个 spec 完成后增量合并进基线

## 2. 新目录结构

```
docs/
├── superpowers/
│   ├── specs/                          # 功能 spec：需求+设计合一的单文件
│   │   └── YYYY-MM-DD-<feature>-design.md
│   └── plans/                          # 实施计划：checkbox 任务清单（即进度）
│       └── YYYY-MM-DD-<feature>.md
├── INDEX.md                            # 保留，更新指向新体系
├── system/
│   ├── requirements.md                 # 新增：系统需求基线文档（见第 4 节）
│   └── SUMMARY.md / architecture.md / database.md / api.md / modules/
│                                       # 保留，作为长期系统知识
└── templates/
    └── spec-design-template.md         # 唯一模板：spec 设计文档（中文）
                                        # 计划格式由 superpowers:writing-plans 技能约定，不另设模板
```

spec 设计文档内部结构（模板固化）：

1. **需求章节**：用户故事 + EARS 验收标准（中文）
2. **设计章节**：架构、数据模型、接口、错误处理、测试策略、影响分析

删除：

- `docs/iterations/` 整个目录（含 INDEX.md、SUMMARY.md、iter-001~006）
- `docs/templates/` 下 7 个旧模板（已完成）及过渡期产生的 3 个 Kiro 模板
- `docs/TASK_STATE.md`

## 3. CLAUDE.md 改造

删除三大章节：「Documentation System（7 阶段流程）」「开发完成检查清单」「Task Memory System」。替换为一个 **Spec 驱动开发（Spec-Driven Development）** 章节，包含以下规则：

### 3.1 阶段门禁

任何新功能开发必须依次产出并经用户确认：

1. `docs/superpowers/specs/YYYY-MM-DD-<feature>-design.md` — 需求章节（用户故事 + EARS）与设计章节，**用户确认后**才进入下一步
2. `docs/superpowers/plans/YYYY-MM-DD-<feature>.md` — 实施计划（checkbox 任务），**用户确认后**才能开始写代码

配套技能：需求探索用 brainstorming，计划编写用 writing-plans，执行用 subagent-driven-development 或 executing-plans。

### 3.2 EARS 验收标准（中文格式）

```
当 <触发条件/事件> 时，系统应 <预期行为>。
在 <前置状态> 下，当 <触发条件> 时，系统应 <预期行为>。
```

每条验收标准可直接映射为 pytest 测试用例，与现有 TDD 要求衔接。

### 3.3 任务执行规则

- 一次只执行一个 task，按计划顺序进行
- 每个 task 遵循 TDD：先写失败测试 → 实现 → 重构
- task 完成后立即将计划中的 `- [ ]` 改为 `- [x]` 并提交代码
- 提交前 `pytest backend/tests/` 必须全部通过
- 每个 task 标注它覆盖的需求编号（追溯性）

### 3.4 会话恢复规则

新对话启动时，扫描 `docs/superpowers/plans/*.md` 中的未勾选项；若存在，主动提示用户：
「检测到未完成的计划：<feature>，进度 x/y。是否继续？」

### 3.5 需求基线增量更新规则

每个计划的全部 task 完成后，将其 spec 设计文档需求章节的内容合并进 `docs/system/requirements.md` 对应模块章节（新增或修订条目），并在基线文档的变更记录表中登记。**代码提交 ≠ spec 完成，基线文档同步更新后才算完成。**

### 3.6 保留章节

Project Overview、Commands、Architecture、Key Patterns、Development Notes、Testing（含 TDD 规则、外部 API mock 规则、冒烟测试要求）原样保留，仅微调引用。

## 4. 系统需求基线文档（docs/system/requirements.md）

全新撰写的全面需求文档，描述系统**当前实际状态**（而非历史设计意图），来源：

- 现有代码（routes/services/templates 实际行为）
- `backend/reqspec.md`（早期需求规格书，682 行）
- 6 个历史迭代文档（iter-001~006 新增的功能）

结构按现有 8 个系统模块划分章节（与 `docs/system/modules/` 对齐），并为模块文档未覆盖的路由（FCB、credit、api）增设章节；每个模块内为编号的需求条目（用户故事 + EARS 验收标准），文档尾部带变更记录表。

`backend/reqspec.md` 与 `backend/techspec.md` 保留为历史参考，文件头部加注说明「已被 docs/system/requirements.md 取代」；CLAUDE.md 中的引用改指新基线。

## 5. 历史迭代迁移

6 个历史迭代（iter-001-invoice-download ~ iter-006-loan-rejected-notify）各转换为**一份完成态 spec 设计文档** `docs/superpowers/specs/2026-07-14-<name>-design.md`（状态标「已完成（历史迁移）」）：

- 需求章节：从原 1-requirement / 2-prd 提炼（若无 2-prd 则依据设计反推补写 EARS）
- 设计章节：从原 3-design / 5-development 提炼
- 不补写历史计划文件（任务清单对已完成功能无意义），实际变更以 git 历史为准
- 转换完成后删除 `docs/iterations/`

## 6. 边界

- 不修改任何应用代码（backend/、scripts/、模板等），纯文档/流程改造
- 在 `sprint_credit_limit` 分支上进行
- 不引入新工具或依赖

## 7. 实施顺序

1. 撰写 spec 设计文档模板（并移除过渡期的 3 个 Kiro 模板）
2. 撰写系统需求基线文档（工作量最大，需通读代码与旧文档）
3. 迁移 6 个历史迭代到 docs/superpowers/specs/
4. 重写 CLAUDE.md
5. 更新 docs/INDEX.md、加注 reqspec/techspec
6. 删除旧目录与文件
