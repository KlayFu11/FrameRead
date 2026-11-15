# 01: 平台骨架可启动

**What to build:** 部署者在干净本机执行 `frameread secrets init`、`docker compose run --rm migrate`、`docker compose up -d` 后，空库得到 `instance_state` 单例，api-admin 的内部 `/health/ready` 返回 PG、migration head、根密钥、Redis 各分项；任何请求出错都返回统一错误体与 `X-Request-ID`，日志为字段 allowlist 的 JSON。后续 Ticket 可以直接使用 UoW、写入门禁、KeyRing、错误码登记、`run_transaction` 与 OpenAPI 导出。

**Blocked by:** None (can start immediately)

**Status:** resolved

**依据：** [M01 SPEC](../../m01-instance-platform/spec.md) 实现决定 3.1～3.9、测试决定 1、3～10、13～17、19、20；X1 的 S0 部分。REQ-11、REQ-13、REQ-14；AT-20 空库迁移、AT-21、AT-22 S0 子集（R10）。

- [x] 依赖版本解析到具体 patch，写入 `uv.lock`；Compose 镜像固定 digest；无 floating latest（Q13）
- [x] Compose 只含 S0 服务：gateway（仅占位，路由在 02）、api-admin、worker、control（占位进程，可只运行 live 心跳）、migrate、postgres、redis；全部非 root、只读根文件系统、资源限制、不挂 Docker socket；postgres 与 redis 不暴露宿主端口
- [x] `frameread secrets init` 生成根密钥、PG role 与 Redis 密码、DSN/URL 文件；文件已存在时拒绝覆盖且内容不变（D02）
- [x] postgres initdb 脚本创建 `frameread_migrate` 与 `frameread_app`；migrate 持 advisory lock（等待上限 60s）迁移，初始 revision 只含 S0 当前所需表（本 Ticket 为 `instance_state`），在空库生成 installation_id、instance_epoch、root_key_check 与 `policy_json` 默认值（D04、D08）
- [x] 所有表带四个通用列；`updated_at` 触发器生效；`version` 条件更新 0 行时抛 `VERSION_CONFLICT`（Q9、U2）
- [x] 启动顺序：连库 → 校验 head 完全相等 → 读 `instance_state` → 比对 `root_key_check` → 用 installation_id 派生四个子密钥；head 不符、密钥缺失或不符时拒绝启动，不生成新密钥（E7、D04）
- [x] migrate 按 `API×5 + Worker 并发×2 + control×3 + 保留 5` 与 `max_connections` 静态比对，超出失败（U3）
- [x] UoW（async 与 sync 同一组方法）、`gate.require(op)` 及门禁类别表、`db_now()`、`run_transaction`（仅 40001/40P01 重跑，总计最多 3 次）、`CommitOutcomeUnknown` 可用并有单测
- [x] 全局错误码登记表与 HTTP 映射、`action` 词表；未预期异常返回 `500 INTERNAL_ERROR` 且不泄露异常内容；请求中间件生成 UUIDv4 request_id（Q8、D11）
- [x] structlog JSON 与 allowlist processor，越界字段抛错；Docker 日志 10m×5（Q11、D12）
- [x] live/ready 仅内网，ready 200/503 语义与分项结构按 D13；Redis 探针由 M01 注册；采集失败为 `null`+`unknown`；健康检查期间无出站请求
- [x] Worker 与 control 的 live 以 tmpfs 心跳文件经 `frameread health live` 判定，Compose healthcheck 只用 live
- [x] `frameread openapi export --app admin` 可导出 OpenAPI（前端类型生成在 02）
- [x] GitHub Actions：锁文件一致性、迁移、后端单测与真实 PG/Redis 集成测试；测试夹具使用模板库复制独立库（D38，隔离方式见 Answer；远端运行未验证）
- [x] `deploy/README.md` 写明以上启动命令
- [x] 迁移失败测试：复制迁移目录追加失败 revision 运行，服务不启动、数据未被清空（E9）

## Answer

- **实现与收尾**：初始实现 `364faf1`；收尾实现 `431aa59`（`feat/s0-ticket-01-close`），补齐准确 CLI 与运行时网络证据。
- **运行的检查**：`uv lock --check`、`ruff check src tests`、`ruff format --check src tests`、`mypy`（strict）均通过；`.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`（真实 PostgreSQL 17 与 Redis 7.4）177 passed，无 skip。
- **实际部署**：在新数据卷上按 `deploy/README.md` 执行 `secrets init → build → run --rm migrate → up -d --wait`，6 个服务就绪，`scripts/check_compose_s0.sh` 输出 OK；分别停止 Redis 与 PostgreSQL，ready 依次为 `200 degraded`、`503 unavailable`，依赖恢复后自动回到 ready。
- **证据**：[docs/validation/s0/01-platform-skeleton.md](../../../docs/validation/s0/01-platform-skeleton.md)。
- **CLI 与网络证据**：独立 Linux 容器内调用准确 CLI 24 次，最长 0.369s，小于 Compose 3s 超时；同窗调用 live/ready 各 12 次，ready 均成功，外部接口 TX 增量为 0 包、0 字节；独立网关对照包使计数增加 1 包。方法为接口计数观测，非抓包，详见验证记录。
- **验证限制**：GitHub Actions 工作流已实现，本地等价检查已执行；未 push、未在远端运行。当前宿主为 Windows Docker Desktop，不代表 Linux 宿主兼容性已验证。Worker 心跳探针随 Ticket 06 验收。
- **审查后的偏离说明**：
  - qa/utility 池与 SPEC §8.2、§9.3 其余策略键随首个使用它们的 Ticket 加入。
  - 连接池大小保持常量，与 U3 的预算公式一致。
  - 测试隔离使用“模板库复制独立库”，替代“共用库每测 TRUNCATE”，隔离程度更强（D38 目标不变）。
  - migrate 这一一次性工具使用 `depends_on: service_healthy`，常驻服务仍自行重连。
  - worker/control 使用 `frameread health live` 的标准库快速分发，完整维护 CLI 按需加载；原 `frameread-live` 继续兼容。
