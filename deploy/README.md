# 本地部署（S0）

在宿主机用 Docker Compose 运行 FrameRead。本文只覆盖当前切片已实现的部分；完整部署说明在 S8 补齐。所有命令在仓库根目录执行。

## 前置条件

- Docker Engine 与 Compose v2（Linux amd64；Windows Docker Desktop 为待验证环境）
- 生成密钥需要 [uv](https://docs.astral.sh/uv/)：在 `backend/` 下执行 `uv sync`

## 首次启动

1. 生成根密钥与连接凭据。目录内已有任一文件时命令拒绝执行，不会覆盖：

   ```sh
   (cd backend && uv run frameread secrets init --dir ../deploy/secrets)
   ```

   `deploy/secrets/` 已被 git 忽略。根密钥丢失后已有加密数据无法恢复，请自行备份该目录。

2. 构建镜像并执行迁移。迁移在空库上建表并初始化实例；`deploy/settings.toml` 中的 `[policy]` 只在这一步写入数据库：

   ```sh
   docker compose -f deploy/compose.yaml build
   docker compose -f deploy/compose.yaml run --rm migrate
   ```

3. 启动服务并查看状态：

   ```sh
   docker compose -f deploy/compose.yaml up -d
   docker compose -f deploy/compose.yaml ps
   docker compose -f deploy/compose.yaml logs --tail=100 api-admin worker control
   ```

管理入口监听 `127.0.0.1:8080`（S0 尚无页面，登录与页面在后续 Ticket 加入）。

## 健康检查

`/health/live` 与 `/health/ready` 只在容器内网提供，gateway 不转发。查看依赖分项：

```sh
docker compose -f deploy/compose.yaml exec api-admin python -c "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:8000/health/ready'); sys.stdout.write(r.read().decode())"
```

`ready` 与 `degraded` 返回 200，`unavailable` 与 `unknown` 返回 503。worker 与 control 没有 HTTP 端口，由轻量入口 `frameread-live --name worker|control` 检查 tmpfs 心跳文件判断存活。

## 升级与故障

- 升级前停止写服务，再运行 `migrate`，成功后启动新版本。迁移失败时数据库保持失败前的 schema 与数据，服务拒绝启动；不要清库或手工 downgrade。
- 修改 `settings.toml` 中的 `[policy]` 不会影响已初始化的实例，启动日志会提示 `policy_differs_from_settings`。
- 根密钥与实例不符时 api-admin、worker、control 拒绝启动。

## 资源限制

各服务以非 root 运行、根文件系统只读、去掉全部 capability，并设置 CPU、内存与进程数上限（见 `deploy/compose.yaml`）。这些数值是 S0 起点，尚未经过负载测量。
