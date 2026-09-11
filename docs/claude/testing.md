# Testing 规范

## 环境配置

- 生产数据库：`refactoring`（DevelopmentConfig，唯一的运行环境）
- 测试数据库：`refactoring_test`（TestingConfig，仅测试使用）
- 运行测试：`pytest backend/tests/`
- 运行覆盖率：`pytest backend/tests/ --cov=backend/app`

## 外部 API Mock 规则

项目所有外部 API 均指向 `n8n.air8.cn`，无测试环境。测试中必须 mock：
- `backend.app.routes.tools.requests.get` — invoice download、dummy invoice
- `backend.app.services.import_service.requests.get` — API 导入

## TDD 开发流程（必须遵守）

后续迭代遵循 TDD，在 spec 流程中体现为：
1. 每个 task **必须先写测试用例，再进入开发**（测试先行）
2. 先写失败的测试 → 再写代码让测试通过 → 最后重构
3. 每次提交代码前运行 `pytest backend/tests/` 确保全部通过

## 回归测试

`test_smoke.py` 包含关键路由冒烟测试，每次迭代必须全部通过。
新功能必须附带对应的测试文件（`test_<feature>.py`）。
