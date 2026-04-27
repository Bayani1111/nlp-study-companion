# 部署与运维说明

## 1. 运行模式

当前项目支持三种典型运行方式：
- 本地直跑：适合本机开发和调试
- Docker Compose + SQLite：适合单机演示和轻量开发
- Docker Compose + PostgreSQL：适合更接近生产的联调环境

## 2. 环境变量建议

开发环境可直接复制：

```powershell
copy backend/.env.development.example backend/.env
```

生产环境建议基于 [backend/.env.production.example](/F:/kaifa/nlp-study-companion/backend/.env.production.example) 单独维护，并重点确认这些变量：
- `APP_ENV=production`
- `SECRET_KEY`
- `DATABASE_URL`
- `CORS_ORIGINS`
- `DEBUG=false`
- `AUTH_COOKIE_SECURE=true`
- `LLM_API_KEY`

## 3. 本地运维常用命令

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 migrate
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 run
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 test
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 release-check
```

## 4. Docker / Compose

SQLite 开发：

```bash
docker compose up --build
```

PostgreSQL 联调：

```bash
docker compose --profile postgres up --build
```

停止服务：

```bash
docker compose down
```

校验配置：

```bash
docker compose config
```

## 5. 健康检查

应用内置健康检查接口：

- [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

建议反向代理或监控系统优先探测这个接口。

## 6. 日志建议

当前日志默认输出到控制台。

建议：
- 开发 / 测试：`LOG_LEVEL=DEBUG`
- 生产：`LOG_LEVEL=INFO`

如果后续要接日志系统，优先接这三类：
- 应用错误日志
- 提醒任务执行日志
- 认证与关键操作日志

## 7. SQLite 备份与恢复

如果当前仍在使用 SQLite，数据库文件通常是：
- 本地直跑：`study_companion.db`
- Compose：挂载卷内的 `/app/data/study_companion.db`

本地开发时可直接备份文件：

```powershell
Copy-Item .\study_companion.db .\study_companion.backup.db
```

恢复：

```powershell
Copy-Item .\study_companion.backup.db .\study_companion.db -Force
```

## 8. PostgreSQL 备份与恢复建议

如果切到 PostgreSQL，建议至少准备：
- 每日逻辑备份
- 发布前手动备份
- 恢复演练

常见思路：
- `pg_dump` 做逻辑备份
- `psql` 做恢复

如果后续准备正式上线，建议把 PostgreSQL 备份脚本单独固化到部署环境。

## 9. 发布建议顺序

推荐的发布顺序：
1. 在测试环境执行迁移
2. 执行 `release-check`
3. 备份数据库
4. 部署应用
5. 检查健康接口
6. 冒烟测试聊天、任务、计划、统计、提醒
7. 观察日志与异常
