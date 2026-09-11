# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python/Flask financial management system (再保理数据同步系统 - Refactoring Data Synchronization System) for managing financing orders, repayment records, bank statements, and data aggregation. Uses MongoDB for storage and Bootstrap 5.3 for the frontend via Jinja2 templates.

## Commands

```bash
# Run development server (port 5000)
python run_flask.py

# Run tests
pytest backend/tests/

# Docker build and run
docker build -t refactoring-system .
docker run -p 5000:5000 refactoring-system

# Create admin user
python scripts/create_admin_user.py

# Run data aggregation manually
python scripts/run_aggregate.py

# Initialize database
python scripts/init_db.py
```

## 详细规范（自动加载）

以下文件通过 import 每次会话自动加载，效力等同于写在本文件中：

- 架构与关键模式：@docs/claude/architecture.md
- 编码行为准则：@docs/claude/coding-principles.md
- Spec 驱动开发流程：@docs/claude/spec-workflow.md
- 测试规范（TDD、外部 API mock）：@docs/claude/testing.md

## 快速索引

- 全局文档索引：`docs/INDEX.md`
- 系统需求基线（唯一权威）：`docs/system/requirements.md`
- 系统长期知识（架构/数据库/API/模块详情）：`docs/system/`
