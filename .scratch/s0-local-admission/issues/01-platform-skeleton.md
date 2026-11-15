# 01: 平台骨架可启动

**What to build:** 部署者在干净本机执行 `frameread secrets init`、`docker compose run --rm migrate`、`docker compose up -d` 后，空库得到 `instance_state` 单例，api-admin 的内部 `/health/ready` 返回 PG、migration head、根密钥、Redis 各分项；任何请求出错都返回统一错误体与 `X-Request-ID`，日志为字段 allowlist 的 JSON。后续 Ticket 可以直接使用 UoW、写入门禁、KeyRing、错误码登记、`run_transaction` 与 OpenAPI 导出。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

**依据：** [M01 SPEC](../../m01-instance-platform/spec.md) 实现决定 3.1～3.9、测试决定 1、3～10、13～17、19、20；X1 的 S0 部分。REQ-11、REQ-13、REQ-14；AT-20 空库迁移、AT-21、AT-22 S0 子集（R10）。

- [ ] 依赖版本解析到具体 patch，写入 `uv.lock`；Compose 镜像固定 digest；无 floating latest（Q13）
- [ ] Compose 只含 S0 服务：gateway（仅占位，路由在 02）、api-admin、worker、control（占位进程，可只运行 live 心跳）、migrate、postgres、redis；全部非 root、只读根文件系统、资源限制、不挂 Docker socket；postgres 与 redis 不暴露宿主端口
- [ ] `frameread secrets init` 生成根密钥、PG role 与 Redis 密码、DSN/URL 文件；文件已存在时拒绝覆盖且内容不变（D02）
- [ ] postgres initdb 脚本创建 `frameread_migrate` 与 `frameread_app`；migrate 持 advisory lock（等待上限 60s）迁移，初始 revision 只含 S0 当前所需表（本 Ticket 为 `instance_state`），在空库生成 installation_id、instance_epoch、root_key_check 与 `policy_json` 默认值（D04、D08）
- [ ] 所有表带四个通用列；`updated_at` 触发器生效；`version` 条件更新 0 行时抛 `VERSION_CONFLICT`（Q9、U2）
- [ ] 启动顺序：连库 → 校验 head 完全相等 → 读 `instance_state` → 比对 `root_key_check` → 用 installation_id 派生四个子密钥；head 不符、密钥缺失或不符时拒绝启动，不生成新密钥（E7、D04）
- [ ] migrate 按 `API×5 + Worker 并发×2 + control×3 + 保留 5` 与 `max_connections` 静态比对，超出失败（U3）
- [ ] UoW（async 与 sync 同一组方法）、`gate.require(op)` 及门禁类别表、`db_now()`、`run_transaction`（仅 40001/40P01 重跑，总计最多 3 次）、`CommitOutcomeUnknown` 可用并有单测
- [ ] 全局错误码登记表与 HTTP 映射、`action` 词表；未预期异常返回 `500 INTERNAL_ERROR` 且不泄露异常内容；请求中间件生成 UUIDv4 request_id（Q8、D11）
- [ ] structlog JSON 与 allowlist processor，越界字段抛错；Docker 日志 10m×5（Q11、D12）
- [ ] live/ready 仅内网，ready 200/503 语义与分项结构按 D13；Redis 探针由 M01 注册；采集失败为 `null`+`unknown`；健康检查期间无出站请求
- [ ] Worker 与 control 的 live 以 tmpfs 心跳文件经 `frameread health live` 判定，Compose healthcheck 只用 live
- [ ] `frameread openapi export --app admin` 可导出 OpenAPI（前端类型生成在 02）
- [ ] GitHub Actions：锁文件一致性、迁移、后端单测与真实 PG/Redis 集成测试；测试夹具按模板库建独立库、每测 TRUNCATE（D38）
- [ ] `deploy/README.md` 写明以上启动命令
- [ ] 迁移失败测试：复制迁移目录追加失败 revision 运行，服务不启动、数据未被清空（E9）
