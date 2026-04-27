# NLP Study Companion

一个面向学习陪伴场景的全栈项目，当前已经具备这些核心能力：
- 用户注册、登录、登出与 Cookie 会话认证
- 聊天创建任务、学习计划与任务树
- 主任务 / 子任务管理、计划阶段视图、模板快速生成
- 学习提醒、统计面板、自动学习时长记录
- Alembic 迁移、Ruff、Mypy、Pytest、CI、Docker / Compose 基础工程化

## 技术栈

- 后端：FastAPI、SQLAlchemy、SQLite / PostgreSQL、Alembic
- 前端：原生 HTML、CSS、JavaScript
- 质量保障：Pytest、pytest-asyncio、Ruff、Mypy
- 运行方式：本地直跑、Docker、Docker Compose

## 目录结构

```text
backend/
  app/                      FastAPI 应用代码
  tests/                    后端测试
  .env.example              通用环境变量模板
  .env.development.example  开发环境模板
  .env.testing.example      测试环境模板
  .env.production.example   生产环境模板
frontend/                   前端静态资源
alembic/                    数据库迁移脚本
scripts/                    本地开发脚本
docs/                       部署、运维、发布前清单
```

## 环境分层

项目通过 `APP_ENV` 区分环境：
- `development`
- `testing`
- `production`

环境会影响这些默认值：
- `DATABASE_URL`
- `DEBUG` 与 `LOG_LEVEL`
- Cookie 的 `Secure` / `SameSite`
- `CORS_ORIGINS`

推荐使用这些模板：
- 开发：[backend/.env.development.example](/F:/kaifa/nlp-study-companion/backend/.env.development.example)
- 测试：[backend/.env.testing.example](/F:/kaifa/nlp-study-companion/backend/.env.testing.example)
- 生产：[backend/.env.production.example](/F:/kaifa/nlp-study-companion/backend/.env.production.example)

## 本地开发

### 方式一：直接本地运行

1. 安装依赖

```bash
pip install -r backend/requirements.txt
```

2. 准备环境变量

```bash
copy backend/.env.development.example backend/.env
```

3. 执行数据库迁移

```bash
alembic upgrade head
```

4. 启动应用

```bash
uvicorn app.main:app --reload --app-dir backend
```

5. 打开浏览器

- 首页：[http://127.0.0.1:8000](http://127.0.0.1:8000)
- 健康检查：[http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

### 方式二：Docker Compose 启动 SQLite 开发环境

```bash
docker compose up --build
```

这条命令会自动完成：
- 构建镜像
- 执行 `alembic upgrade head`
- 启动 `uvicorn --reload`
- 挂载本地 `backend/` 和 `frontend/`

### 方式三：Docker Compose 启动 PostgreSQL 开发环境

```bash
docker compose --profile postgres up --build
```

这条命令会额外启动：
- `postgres` 容器
- 使用 PostgreSQL 的 `app-postgres` 容器

访问地址：
- SQLite 模式应用：[http://127.0.0.1:8000](http://127.0.0.1:8000)
- PostgreSQL 模式应用：[http://127.0.0.1:8001](http://127.0.0.1:8001)

## 常用命令

项目提供统一脚本 [scripts/dev.ps1](/F:/kaifa/nlp-study-companion/scripts/dev.ps1)：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 help
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 test
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 lint
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 typecheck
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 migrate
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 release-check
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 compose-up
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 compose-up-pg
```

## 测试与代码质量

测试：

```bash
pytest backend/tests -q
```

代码质量：

```bash
ruff check backend alembic frontend
ruff format --check backend alembic frontend
mypy
```

数据库迁移：

```bash
alembic upgrade head
alembic revision --autogenerate -m "describe change"
alembic downgrade -1
```

## 发布前收尾

第五阶段的交付文档已经补在 `docs/` 目录里：
- 发布前检查清单：[docs/release-checklist.md](/F:/kaifa/nlp-study-companion/docs/release-checklist.md)
- 部署与运维说明：[docs/operations.md](/F:/kaifa/nlp-study-companion/docs/operations.md)

推荐每次准备交付前至少执行一次：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 release-check
```

## CI

仓库带基础 GitHub Actions，会在推送和 Pull Request 时自动执行：
- `ruff check backend alembic`
- `ruff format --check backend alembic`
- `mypy`
- `alembic upgrade head`
- `pytest backend/tests -q`

## 当前阶段说明

这个项目现在已经是“主链路可用”的状态：
- 聊天 -> 创建计划 / 任务
- 计划 -> 任务树 / 子任务
- 学习 -> 自动记录学习时长
- 统计 -> 学习趋势 / 阶段达成率 / 完成节奏

当前更适合继续做两类工作：
- 产品能力深化：聊天拆解、提醒策略、统计体验继续增强
- 上线前收尾：Docker 验证、PostgreSQL 联调、部署与备份演练
