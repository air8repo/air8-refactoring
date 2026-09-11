# Spec 驱动开发流程改造 — 实施计划（v2：superpowers 体系）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 将项目的 AI 开发流程从「7 阶段迭代 + TASK_STATE.md」改造为 superpowers 原生 spec 驱动开发（spec 设计文档 + 实施计划两件套），并产出全新的系统需求基线文档。

**Architecture:** 纯文档改造，不动应用代码。`docs/templates/` 收敛为 1 个 spec 设计文档模板；撰写 `docs/system/requirements.md` 需求基线（覆盖全部实际功能）；6 个历史迭代各转换为一份完成态 spec 设计文档；重写 CLAUDE.md 流程章节；清理旧体系文件。

**Tech Stack:** Markdown 文档；验证手段为 `ls`/`grep` 检查与人工阅读。

**设计文档:** `docs/superpowers/specs/2026-07-14-spec-driven-workflow-design.md`（修订版 v2）

## Global Constraints

- 所有新文档一律用中文撰写
- EARS 验收标准中文格式：「当 <触发条件> 时，系统应 <预期行为>」或「在 <前置状态> 下，当 <触发条件> 时，系统应 <预期行为>」
- 不修改 `backend/`、`scripts/` 下任何应用代码
- 工作分支：`sprint_credit_limit`
- 每个 Task 独立提交，commit message 用英文 `docs:` 前缀

---

### Task 1: 创建 spec 设计文档模板，移除过渡期的 3 个 Kiro 模板

**Files:**
- Create: `docs/templates/spec-design-template.md`
- Delete: `docs/templates/requirements-template.md`、`docs/templates/design-template.md`、`docs/templates/tasks-template.md`（上一轮过渡期产生的 Kiro 模板）

**Interfaces:**
- Produces: spec 设计文档模板，Task 2/3 撰写文档时遵循其结构；需求编号格式 `需求 N`、验收标准编号 `N.M`

- [x] **Step 1: 写入 spec-design-template.md**

```markdown
# 设计文档：<功能名称>

- 日期：YYYY-MM-DD
- 分支：<branch>
- 状态：草稿 / 已确认 / 已完成

## 第一部分：需求

### 简介

<一段话描述功能背景、要解决的问题和目标。>

### 需求 1：<需求名称>

**用户故事**：作为<角色>，我希望<能力>，以便<价值>。

**验收标准**：

1. 当 <触发条件> 时，系统应 <预期行为>。
2. 在 <前置状态> 下，当 <触发条件> 时，系统应 <预期行为>。

### 需求 2：<需求名称>

**用户故事**：……

**验收标准**：

1. ……

### 非功能需求（可选）

- 性能 / 安全 / 兼容性等约束，逐条列出。

### 边界与排除项

- 明确本功能不做什么，防止范围蔓延。

## 第二部分：设计

### 概述

<技术方案一段话概述，说明整体思路。>

### 架构

<涉及的分层与模块：路由 → 服务 → 数据库。新增/修改的文件列表及各自职责。>

### 数据模型

<涉及的 MongoDB 集合、字段定义、索引。无数据变更则写"无"。>

### 接口设计

<新增/修改的路由端点、函数签名、参数与返回值。>

### 错误处理

<各失败场景的处理方式与用户提示。>

### 测试策略

<单元测试/冒烟测试的覆盖点；外部 API 一律 mock（见 CLAUDE.md 外部 API Mock 规则）。>

### 影响分析

<对现有功能的影响面，需要回归验证的部分。>
```

- [x] **Step 2: 删除 3 个 Kiro 模板**

```bash
git rm docs/templates/requirements-template.md docs/templates/design-template.md docs/templates/tasks-template.md
```

- [x] **Step 3: 验证**

Run: `ls docs/templates/`
Expected: 仅 1 个文件：`spec-design-template.md`

- [x] **Step 4: 提交**

```bash
git add docs/templates/
git commit -m "docs: replace Kiro templates with single superpowers spec-design template"
```

---

### Task 2: 撰写系统需求基线文档 docs/system/requirements.md

**Files:**
- Create: `docs/system/requirements.md`
- 阅读来源（只读）：`backend/reqspec.md`、`docs/system/modules/*.md`（8 个）、`docs/system/SUMMARY.md`、`docs/iterations/SUMMARY.md`、`docs/iterations/iter-00[1-6]-*/1-requirement.md` 与 `3-design.md`、`backend/app/routes/*.py`（重点：`fcb.py`、`credit.py`、`tools.py`、`api.py` 这些模块文档未覆盖的路由）

**Interfaces:**
- Produces: 需求基线文档，条目编号 `REQ-<模块>-NNN`（如 `REQ-AUTH-001`）；Task 4 的 CLAUDE.md 和 Task 5 的 INDEX.md 引用路径 `docs/system/requirements.md`

- [x] **Step 1: 通读来源文档与路由代码**

按 Files 列表阅读。特别注意：需求基线描述**当前系统实际行为**，以代码为准；`backend/reqspec.md` 中与现状不符的内容以代码为准修正。

- [x] **Step 2: 撰写文档骨架与全部章节**

文档结构（章节与模块对应关系固定如下）：

```markdown
# 再保理系统需求基线文档

> 本文档为系统需求的唯一权威基线，描述系统当前实际行为。
> 每个功能 spec（`docs/superpowers/specs/*-design.md`）对应的计划完成后，须将其需求合并进本文档对应章节并登记变更记录。
> 取代 `backend/reqspec.md`（历史参考）。

## 1. 引言
### 1.1 文档目的
### 1.2 术语定义        ← 从 backend/reqspec.md 迁移并补充 FCB、Dummy 发票等新术语

## 2. 用户认证与权限（REQ-AUTH-xxx）      ← 来源 modules/auth.md
## 3. 数据导入（REQ-IMPORT-xxx）          ← 来源 modules/import.md + iter-005/006
## 4. 数据导出（REQ-EXPORT-xxx）          ← 来源 modules/export.md
## 5. 数据聚合（REQ-AGG-xxx）             ← 来源 modules/aggregation.md
## 6. 批次管理（REQ-BATCH-xxx）           ← 来源 modules/batch.md
## 7. 仪表盘（REQ-DASH-xxx）              ← 来源 modules/dashboard.md
## 8. 数据维护（REQ-MAINT-xxx）           ← 来源 modules/maintenance.md
## 9. 工具集（REQ-TOOLS-xxx）             ← 来源 modules/tools.md + iter-001/002
## 10. FCB 模块（REQ-FCB-xxx）            ← 来源 iter-003/004 + routes/fcb.py
## 11. 额度管理（REQ-CREDIT-xxx）         ← 来源 routes/credit.py（如为空壳则如实注明）
## 12. 对外 API（REQ-API-xxx）            ← 来源 routes/api.py + iter-005
## 13. 国际化与通用（REQ-COMMON-xxx）     ← i18n、语言切换、登录保护等横切需求
## 14. 非功能需求（REQ-NFR-xxx)           ← 文件大小限制、幂等导入、性能等

## 15. 变更记录

| 日期 | 来源 spec | 变更内容 |
|------|-----------|----------|
| 2026-07-14 | （初始基线） | 依据现有代码与历史迭代建立基线 |
```

每个模块章节内的需求条目格式（用户故事 + EARS，与 spec-design-template.md 需求部分一致）：

```markdown
### REQ-IMPORT-001 银行对账单导入

**用户故事**：作为运营人员，我希望上传银行对账单 Excel 并幂等导入，以便重复上传不产生脏数据。

**验收标准**：

1. 当 用户上传 .xlsx/.xls 格式的银行对账单文件 时，系统应 按唯一键 upsert 写入 `refactoring_bank_statement` 集合。
2. 当 上传文件超过 16MB 或扩展名不合法 时，系统应 拒绝导入并提示错误。
```

- [x] **Step 3: 自查**

逐项核对：14 个功能章节全部有内容、无"TBD/待补充"、每条需求都有用户故事和至少 1 条 EARS 验收标准、编号无重复无跳号、6 个历史迭代的功能都能在基线中找到对应条目（iter-001/002→工具集，iter-003/004→FCB，iter-005/006→数据导入/对外 API）。

- [x] **Step 4: 提交**

```bash
git add docs/system/requirements.md
git commit -m "docs: add comprehensive system requirements baseline"
```

---

### Task 3: 迁移 6 个历史迭代到 docs/superpowers/specs/，删除 docs/iterations/

**Files:**
- Create: `docs/superpowers/specs/2026-07-14-invoice-download-design.md`（源：`docs/iterations/iter-001-invoice-download/`）
- Create: `docs/superpowers/specs/2026-07-14-create-dummy-invoice-design.md`（源：iter-002）
- Create: `docs/superpowers/specs/2026-07-14-fcb-module-design.md`（源：iter-003）
- Create: `docs/superpowers/specs/2026-07-14-fcb-daily-export-design.md`（源：iter-004）
- Create: `docs/superpowers/specs/2026-07-14-bank-settlement-fields-design.md`（源：iter-005）
- Create: `docs/superpowers/specs/2026-07-14-loan-rejected-notify-design.md`（源：iter-006）
- Delete: `docs/iterations/` 整个目录

**Interfaces:**
- Consumes: Task 1 的 spec-design-template.md 结构
- Produces: 6 份完成态 spec 设计文档，作为新体系的历史示例

- [x] **Step 1: 逐个迭代转换（6 次循环）**

对每个 `docs/iterations/iter-00N-<name>/`：

1. 读取其中存在的阶段文档（`1-requirement.md`、`2-prd.md`、`3-design.md`、`5-development.md`，缺哪个跳过哪个）
2. 按模板写 `docs/superpowers/specs/2026-07-14-<name>-design.md`：
   - 文件头状态标「已完成（历史迁移）」
   - 需求部分：简介取自 1-requirement；用户故事与验收标准取自 2-prd（若无 2-prd，则依据 1-requirement 和 3-design 反推补写 EARS 验收标准）
   - 设计部分：取自 3-design 提炼，保留涉及文件、关键实现、数据模型；实际变更文件列表取自 5-development 并入「架构」小节；无对应内容的小节写「无」
3. **不**补写历史计划文件（已完成功能的任务清单无意义，实际变更以 git 历史为准）

- [x] **Step 2: 验证**

Run: `ls docs/superpowers/specs/`
Expected: 7 个文件（本次改造自身的设计文档 + 6 份历史迁移文档）
Run: `grep -L "已完成（历史迁移）" docs/superpowers/specs/2026-07-14-*-design.md | grep -v workflow`
Expected: 无输出（6 份迁移文档均标注完成态）

- [x] **Step 3: 删除旧迭代目录并提交**

```bash
git rm -r docs/iterations/
git add docs/superpowers/specs/
git commit -m "docs: migrate 6 iterations to superpowers spec docs, remove docs/iterations"
```

---

### Task 4: 重写 CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`（整体重写，保留的章节原文不动）

**Interfaces:**
- Consumes: `docs/system/requirements.md`（Task 2）、`docs/superpowers/specs/`（Task 3）、模板（Task 1）

- [x] **Step 1: 重写 CLAUDE.md**

保留原文不动的章节：`## Project Overview`、`## Commands`、`## Architecture`、`## Key Patterns`、`## Testing`（环境配置 / 外部 API Mock 规则 / TDD 开发流程 / 回归测试 4 小节全部保留，其中「7 阶段流程」字样改为「spec 流程」）。

`## Development Notes` 中这一行：

> - Specs are in `backend/techspec.md` (technical) and `backend/reqspec.md` (requirements), both in Chinese.

替换为：

> - 系统需求基线见 `docs/system/requirements.md`（唯一权威）。`backend/reqspec.md` 与 `backend/techspec.md` 为历史参考。

删除整个 `## Documentation System`（含 7 阶段流程、开发完成检查清单）和整个 `## Task Memory System` 章节，在原位置替换为以下内容（原样写入）：

```markdown
## Spec 驱动开发（Spec-Driven Development）

项目采用 superpowers 原生的 spec 驱动开发。每个功能两份产物，全部用中文撰写：

| 产物 | 路径 | 内容 |
|------|------|------|
| spec 设计文档 | `docs/superpowers/specs/YYYY-MM-DD-<feature>-design.md` | 需求（用户故事 + EARS 验收标准）+ 设计（架构、数据模型、接口、测试策略），模板见 `docs/templates/spec-design-template.md` |
| 实施计划 | `docs/superpowers/plans/YYYY-MM-DD-<feature>.md` | checkbox 任务清单，即持久化进度 |

配套技能：需求探索用 brainstorming，计划编写用 writing-plans，执行用 subagent-driven-development 或 executing-plans。

### 阶段门禁（必须遵守）

任何新功能开发必须依次完成，**每一步经用户确认后才能进入下一步**：

1. 写 spec 设计文档（需求章节 + 设计章节）→ 用户确认
2. 写实施计划 → 用户确认 → 才能开始写代码

严禁跳过阶段直接写代码，即使需求看起来很简单。

### EARS 验收标准格式

```
当 <触发条件/事件> 时，系统应 <预期行为>。
在 <前置状态> 下，当 <触发条件> 时，系统应 <预期行为>。
```

每条验收标准应能直接映射为一个 pytest 测试用例。

### 任务执行规则

- 一次只执行一个 task，按实施计划顺序进行
- 每个 task 遵循 TDD：先写失败测试 → 实现 → 重构
- task 完成后立即把计划中的 `- [x]` 改为 `- [x]` 并提交代码（进度以计划文件为准，无需额外状态文件）
- 提交前 `pytest backend/tests/` 必须全部通过
- 每个 task 标注 `_覆盖需求：N.M_` 保持追溯性

### 会话恢复规则（必须遵守）

每次新对话开始时，扫描 `docs/superpowers/plans/*.md` 中的未勾选项（`- [x]`）。若存在，主动提示用户：

> 「检测到未完成的计划：<feature>，进度 x/y。是否继续？」

若全部完成，正常开始新任务。

### 需求基线增量更新（必须遵守）

`docs/system/requirements.md` 是系统需求的唯一权威基线。每个实施计划的全部 task 完成后：

1. 将该 spec 设计文档需求章节的内容合并进基线对应模块章节（新增 `REQ-<模块>-NNN` 条目或修订既有条目）
2. 在基线文档末尾的变更记录表登记一行

> ⚠️ **代码提交 ≠ spec 完成**。基线文档同步更新后，一个 spec 才算真正完成。

### 文档索引

全局文档索引见 `docs/INDEX.md`；系统长期知识（架构/数据库/API/模块详情）在 `docs/system/`，开发前按需查阅。
```

- [x] **Step 2: 验证**

Run: `grep -n "TASK_STATE\|7 阶段\|iterations" CLAUDE.md`
Expected: 无输出（旧体系引用全部清除）

- [x] **Step 3: 提交**

```bash
git add CLAUDE.md
git commit -m "docs: rewrite CLAUDE.md workflow to spec-driven development"
```

---

### Task 5: 更新索引、加注旧规格书、删除 TASK_STATE.md

**Files:**
- Modify: `docs/INDEX.md`（整体重写）
- Modify: `docs/system/SUMMARY.md`（如有 iterations/TASK_STATE 引用则清理）
- Modify: `backend/reqspec.md`、`backend/techspec.md`（各在标题下加一行注记）
- Delete: `docs/TASK_STATE.md`

**Interfaces:**
- Consumes: Task 2/3/4 产出的路径

- [x] **Step 1: 重写 docs/INDEX.md**

```markdown
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

## 文档模板

- [spec 设计文档模板](templates/spec-design-template.md) — 需求+设计合一；计划格式由 superpowers:writing-plans 技能约定

## 历史参考

- `backend/reqspec.md`、`backend/techspec.md` — 早期规格书，已被 `docs/system/requirements.md` 取代
```

- [x] **Step 2: 加注旧规格书**

在 `backend/reqspec.md` 第 1 行标题之后插入：

```markdown
> ⚠️ 本文档为历史参考，已被 [docs/system/requirements.md](../docs/system/requirements.md) 取代，不再维护。
```

在 `backend/techspec.md` 标题之后插入同样式注记（指向同一基线文档）。

- [x] **Step 3: 清理残留引用并删除 TASK_STATE.md**

Run: `grep -rn "TASK_STATE\|docs/iterations" docs/ CLAUDE.md README.md 2>/dev/null`
对 grep 命中的每一处（预期主要在 `docs/system/SUMMARY.md`，若无命中则跳过；本计划文件与设计文档中的提及属于历史记录，不算残留）删除或改写；然后：

```bash
git rm docs/TASK_STATE.md
```

- [x] **Step 4: 最终验证**

Run: `grep -rn "TASK_STATE\|docs/iterations\|7 阶段" docs/INDEX.md docs/system/ CLAUDE.md 2>/dev/null`
Expected: 无输出
Run: `pytest backend/tests/`（确认文档改动未破坏任何东西，纯保险）
Expected: 全部通过

- [x] **Step 5: 提交**

```bash
git add docs/ backend/reqspec.md backend/techspec.md
git commit -m "docs: update index, mark legacy specs superseded, remove TASK_STATE"
```
