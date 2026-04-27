# Windows 上安装并修复 Docker Desktop

如果当前项目无法执行 `docker` 或 `docker compose`，并且安装 Docker Desktop 时看到类似下面的报错：

```text
For security reasons C:\ProgramData\DockerDesktop must be owned by an elevated account
```

说明问题不在项目，而在 Windows 本机的 Docker Desktop 安装状态。

## 当前已定位到的阻塞

这台机器目前出现了两个实际问题：
- `docker` 命令还没有进入 PATH
- `C:\ProgramData\DockerDesktop` 当前所有者不是管理员组，而是普通用户

在这种状态下，项目里的 Compose 文件虽然已经准备好了，但没法真正跑起来。

## 最短修复路径

需要用管理员 PowerShell 执行一次修复脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\repair-docker-desktop.ps1
```

这个脚本会做这些事情：
- 检查 `DockerDesktopInstaller.exe` 是否存在
- 如果 `C:\ProgramData\DockerDesktop` 已存在，则尝试把所有者改成管理员组
- 给管理员组补齐完整权限
- 尝试更新 WSL
- 重新以管理员权限启动 Docker Desktop 安装器

## 执行前提

这一步必须满足至少一个条件：
- 当前 Windows 用户本身有管理员权限
- 或者你知道管理员账户密码，可以在 UAC 弹窗里授权

如果没有管理员权限，脚本也没法完成系统层面的修复。

## 修复完成后的验证

重启电脑或至少重开 PowerShell 后，执行：

```powershell
docker version
docker compose config
```

然后回到项目目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 compose-config
```

如果想直接启动 SQLite 开发环境：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 compose-up
```

如果想启动 PostgreSQL 联调环境：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 compose-up-pg
```

## 失败时优先检查

1. `docker` 仍然找不到
- 说明 Docker Desktop 没有安装成功，或者 PATH 还没刷新
- 先完全关闭终端，再新开 PowerShell 试一次

2. `wsl --status` 或 `wsl --update` 报权限错误
- 说明当前 PowerShell 不是管理员
- 必须右键“以管理员身份运行 PowerShell”

3. 仍然报 `C:\ProgramData\DockerDesktop` 权限错误
- 删除旧的残留目录前，先确认里面没有你需要保留的数据
- 然后再次用管理员权限执行修复脚本

## 项目侧现状

项目里和 Docker / Compose 相关的部分已经准备好了：
- [docker-compose.yml](/F:/kaifa/nlp-study-companion/docker-compose.yml)
- [Dockerfile](/F:/kaifa/nlp-study-companion/Dockerfile)
- [scripts/dev.ps1](/F:/kaifa/nlp-study-companion/scripts/dev.ps1)

也就是说，当前剩下的是桌面环境修复，不是代码侧缺功能。
