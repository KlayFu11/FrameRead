# 本地部署（S0）

在宿主机用 Docker Compose 运行 FrameRead。本文只覆盖当前切片已实现的部分；完整部署说明在 S8 补齐。所有命令在仓库根目录执行。

## 前置条件

- Docker Engine 与 Compose v2（Linux amd64；Windows Docker Desktop 的运行验收结果由本次验证记录补充）
- 生成密钥需要 [uv](https://docs.astral.sh/uv/)：在 `backend/` 下执行 `uv sync`

## 首次启动

1. 生成根密钥与连接凭据。目录内已有任一文件时命令拒绝执行，不会覆盖：

   ```sh
   (cd backend && uv run frameread secrets init --dir ../deploy/secrets)
   ```

   `deploy/secrets/` 已被 git 忽略。根密钥丢失后已有加密数据无法恢复，请自行备份该目录。

2. 单独设置管理员密码。命令从 stdin 连续读取两次，不通过参数接收密码；`secrets init` 不生成管理员 hash：

   ```sh
   uv run --project backend frameread admin set-password --out deploy/secrets/admin_password_hash
   ```

   只有 api-admin 挂载该 secret；worker、control 与 migrate 不挂载。hash 文件缺失、为空或无效时 api-admin 启动失败。

3. 构建镜像并执行迁移。gateway 镜像用固定 digest 的 Node 构建前端，使用 `packageManager` 固定的 pnpm 和 `pnpm-lock.yaml`，最终由固定 digest 的 nginx 服务静态文件，不需要单独启动 Vite。迁移在空库上建表并初始化实例；`deploy/settings.toml` 中的 `[policy]` 只在这一步写入数据库：

   ```sh
   docker compose -f deploy/compose.yaml build
   docker compose -f deploy/compose.yaml run --rm migrate
   ```

4. 启动服务并查看状态：

   ```sh
   docker compose -f deploy/compose.yaml up -d
   docker compose -f deploy/compose.yaml ps
   docker compose -f deploy/compose.yaml logs --tail=100 api-admin worker control
   ```

打开 `http://127.0.0.1:8080/manage/`，输入管理员密码进入管理外壳。管理入口只发布到宿主 `127.0.0.1:8080`；api-admin 不发布宿主端口。gateway 只提供 `/manage/` 静态页面与 `/api/v1/admin/` 反代，其他路径（包括 docs、OpenAPI 与健康端点）返回 `404`。

## 密码轮换

```sh
uv run --project backend frameread admin set-password --out deploy/secrets/admin_password_hash --force
docker compose -f deploy/compose.yaml up -d --force-recreate api-admin
docker compose -f deploy/compose.yaml restart gateway
```

CLI 原子替换 hash 文件后，重新创建 api-admin 会重新挂载 secret 并读取新 hash，既有会话随 `credential_generation` 变化而失效。gateway 在 API 重建后重启，以重新解析其容器地址。密码写入文件本身不改变已运行进程的凭据。

## 网关、来源与本地调试

gateway 在 `internal` 网络固定为 `172.28.0.10`（子网 `172.28.0.0/24`），uvicorn 只信任该地址的代理信息；修改子网时须同步更新 gateway IP 与 `--forwarded-allow-ips`。nginx 用 `$remote_addr` 覆盖 `X-Forwarded-For`，并移除 `X-Forwarded-Host`、`X-Forwarded-Proto` 与 `Forwarded`，Host 原样传给管理 API。授权只依赖应用对 Host 与 Origin 的精确校验。

loopback 端口发布下，Docker 可能把真实来源转换成网桥地址，导致多个客户端共享来源限流键；此时单来源限流等同于对这些客户端的合并限流。本次 Windows Docker Desktop 实测来源为 `172.20.0.1`，5 次错误密码仅形成一个来源键，来源与全局计数均为 5，伪造 `X-Forwarded-For` 未形成其他来源键。方法与平台限制见 [Ticket 02 验证记录](../docs/validation/s0-ticket02/02-admin-login-shell.md#来源与日志)。其他宿主环境需重新观测，不能将此地址写入应用配置。

gateway 访问日志只记录 `event`、生成的 `request_id`、状态码与耗时，不记录来源 IP、URL、query、请求头和 body。nginx 原生错误日志关闭，以避免其中携带请求或来源信息；后端事件由应用 allowlist 日志提供。

`settings.toml` 只允许 8080 管理源。需要 Vite 开发时，把 api-admin 挂载配置替换为 `settings.dev.toml`，后者额外允许 `http://localhost:5173`；前端仍通过 Vite 的 `/api` 代理访问 gateway。不要将开发配置用于默认部署。

## 健康检查

`/health/live` 与 `/health/ready` 只在容器内网提供，gateway 不转发。查看依赖分项：

```sh
docker compose -f deploy/compose.yaml exec api-admin python -c "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:8000/health/ready'); sys.stdout.write(r.read().decode())"
```

`ready` 与 `degraded` 返回 200，`unavailable` 与 `unknown` 返回 503。worker 与 control 没有 HTTP 端口，由轻量入口 `frameread health live --name worker|control` 检查 tmpfs 心跳文件判断存活；原 `frameread-live` 入口继续兼容。

## 升级与故障

- 升级前停止写服务，再运行 `migrate`，成功后启动新版本。迁移失败时数据库保持失败前的 schema 与数据，服务拒绝启动；不要清库或手工 downgrade。
- 修改 `settings.toml` 中的 `[policy]` 不会影响已初始化的实例，启动日志会提示 `policy_differs_from_settings`。
- 根密钥与实例不符时 api-admin、worker、control 拒绝启动。

## 资源限制

各服务以非 root 运行、根文件系统只读、去掉全部 capability，并设置 CPU、内存与进程数上限（见 `deploy/compose.yaml`）。这些数值是 S0 起点，尚未经过负载测量。
