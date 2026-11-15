# 批次 A Grill 决定（S0）

日期：2026-11-15，用户逐条确认。供 `/to-spec` 编写 M01、M02、M03、M04、M12 模块 SPEC 使用；已回写 [SPEC_V1](../../docs/prototype/SPEC_V1.md) 的条目注明章节，模块 SPEC 确认后本文仅作追溯。编号沿用 Grill 中的 Q 号。

## M01 实例门禁与平台底座

| Q | 决定 |
| --- | --- |
| 1 | 逐模块对齐全部 V1 职责，标注 S0 落地范围；五模块 SPEC 确认后才 `/to-tickets` S0 |
| 2 | 迁移按切片增量 revision；未合入 `main` 可改可合并，合入后只追加；V1 不 squash；AT-20 基线取 S7 head（SPEC §7.2） |
| 3 | Repository 只构造 SQLAlchemy 语句，由 async/sync 两个薄执行器运行；`AsyncUnitOfWork`/`UnitOfWork` 同一组方法（`lock_instance`、`gate.require`、`commit`），门禁与锁顺序规则只写一份 |
| 4 | `backend/src/frameread/settings.py`，pydantic-settings；非敏感项读 `settings.toml`，凭据只接受 `*_FILE`，缺失或为空启动失败；按进程拆 Settings 子集 |
| 5 | HKDF-SHA256，salt=`installation_id`，info=`frameread/v1/{encryption,session-csrf,cursor,share}`，S0 全部实现 |
| 6 | `instance_state.root_key_check`，各进程启动比对（SPEC §6.1） |
| 7 | postgres initdb 脚本建 `frameread_migrate`、`frameread_app`（public role 归 S7/M15）；`frameread secrets init` 写 `deploy/secrets/`（gitignore），存在即拒绝覆盖；migrate 持 advisory lock 迁移并初始化单例；其余服务校验 head 与 key check |
| 8 | `500 INTERNAL_ERROR`（SPEC §4.1）；错误码为 domain StrEnum + HTTP 映射，前端经 OpenAPI 类型获取 |
| 9 | `updated_at` 由通用 BEFORE UPDATE 触发器维护；`version` 由 Repository 条件更新显式递增，0 行即 `VERSION_CONFLICT` |
| 10 | `run_transaction(fn)` 仅对 `40001/40P01` 整体重跑，最多 3 次带抖动；COMMIT 阶段断连抛 `CommitOutcomeUnknown`，不重跑 |
| 11 | structlog JSON + allowlist processor（越界字段抛错）；中间件生成 `request_id`，写 `X-Request-ID` 与错误体；轮转用 Docker `json-file` 的 max-size/max-file |
| 12 | live/ready 仅内网；`register_probe(name, fn, severity)`；PG+migration head、root key 失败为 unavailable，Redis 与 Worker 心跳为 degraded，采集失败为 null+unknown；Compose healthcheck 只用 live |
| 13 | S0 Compose：gateway、api-admin、worker、control、migrate、postgres、redis；非 root、只读根文件系统、资源限制、不挂 Docker socket 从 S0 起；首个 Ticket 锁定 patch 版本与镜像 digest |
| 14 | `policy_json` 为运行时唯一来源，`settings.toml` 仅空库初始化；`frameread policy set` 在实例锁内修改并递增 `config_revision`；不一致只记 warning（SPEC §6.1、§19） |
| 15 | `frameread maintenance set normal\|draining\|frozen`；`restore_state` 在 S0 仅由测试 fixture 写入；测试 T1/T2 在三种非 normal 状态下 `503 MAINTENANCE`，找回与只读不受影响 |
| 16 | Typer CLI `frameread`：`secrets init`、`maintenance set`、`policy set`、`openapi export`、`admin set-password`；直接使用 sync UoW |
| 17 | `frameread openapi export --app admin` → `frontend/src/gen/admin.openapi.json` → `openapi-typescript` 生成 `src/gen/admin.ts`，提交仓库；CI 重新生成并 diff；运行时只用 `fetch` |
| 18 | migrate 启动按 API×5 + Worker 并发×2（主任务与心跳各一，与 SPEC §7 一致）+ control×3 + 保留 5 与 `max_connections` 静态比对，超出失败 |

## M03 任务运行时

| Q | 决定 |
| --- | --- |
| 19 | S0 video KindHandler 骨架：Claim 后写 `stage_key=acquire`、`output_json={"skeleton": true}`，随心跳检查取消；取消 → canceled，deadline → failed `PIPELINE_NOT_AVAILABLE`；页面标注"S0 骨架：不会生成文章"；S1 删除，不留开关；kill/barrier 夹具只在 `tests/` |
| 20 | `Idempotency-Key` 头必填 UUID，缺失或非法 `422`；前端在提交时生成并存 sessionStorage，未得到明确 `202`/`4xx` 前沿用；scope 按 SPEC §3 固定取值；digest 按 SPEC §3.1，规范化由用例负责；同键不同 digest `409 IDEMPOTENCY_CONFLICT` 并带原 `task_id` |
| 21 | `CommitOutcomeUnknown` 后换新连接按 (scope, key) 查一次：一致 `202`、不一致 `409`、未找到 `503 ADMISSION_UNCONFIRMED`；不轮询，不提示换键 |
| 22 | 执行槽 `resource_key=execution:{pool}`，槽行预建，T1 `FOR UPDATE SKIP LOCKED` 取空槽；调小容量时多余槽 `retired`（SPEC §6.2） |
| 23 | 每个 Celery child 一个任务；T2 后心跳线程独立 Session、10s 续租；续租失败或取消设置 `threading.Event`；`ctx.checkpoint()/fenced()/cancel_requested()` 检查后抛 `LeaseLost`（不写结果）或 `CancelRequested`（走 T7）；未预期异常 failed `INTERNAL_ERROR` |
| 24 | control 为单进程同步 tick 调度，每循环短事务、批量、SKIP LOCKED；S0 实现 dispatcher、等待位提升、deadline、终态清理、lease 失联重排与 §9.3 换代（同一套代码），以及取消收敛；调用相关分支 S1 接 M08 |
| 25 | S0 故障均用外部手段：受理时不启动 control、测试直接重复 `apply_async`、客户端提前断开、`asyncio.gather` 并发；真实 PG/Redis/独立 Worker；代码内故障点留待 S4 |
| 26 | S0 注入 `NoProviderCallsRecovery`（始终无在途调用），S1 由 M08 替换并删除 |
| 27 | 关键事件保留按 SPEC §18.2 默认 7 天，天数入 `policy_json`；清理在 S8，S0 只写入 |

## M04 任务状态同步

| Q | 决定 |
| --- | --- |
| 28 | Vite + React + TypeScript strict + React Router；TanStack Query；CSS Modules + 少量 token，不用组件库；Vitest + Playwright；admin/public 同一工程两个入口，public 从 S7 起 |
| 29 | S0 轮询：详情 2s（终态停止）、列表 5s；按 SPEC §18.2 合并（同 epoch 低 revision 丢弃，epoch 变化清空并提示），合并为纯函数并有 Vitest 单测；S1 起轮询作为断线回退 |
| 30 | 列表 keyset `(created_at, id)`，cursor 子 key HMAC 签名，含 `scope=admin-task-list` 与过滤摘要，过滤变化旧游标 `422`；S0 仅支持 `kind`、`status` 过滤 |
| 31 | `TaskSnapshot` 字段完整保留：`draft_summary=null`；`result` 仅成功终态有值；`unknown_call_count` S0 返回 0（无外部调用），S1 改查 `provider_calls`；`allowed_actions` 服务端推导，S0 仅 `cancel` |
| 32 | SSE（S1）用 `sse-starlette` `EventSourceResponse`，15s ping，每轮检查会话，单连接 64 事件上限 |
| 33 | 任务接口全部只在 admin app，依赖 `require_admin` |

## M02 管理访问与入口隔离

| Q | 决定 |
| --- | --- |
| 34 | `argon2-cffi` 默认参数；`frameread admin set-password` stdin 输入两次写 `deploy/secrets/admin_password_hash`；`credential_generation` = hash 文件 SHA-256 前 16 位，api-admin 启动读取；轮换后重启 api-admin |
| 35 | 只统计失败：按来源 HMAC(session-csrf 子 key, gateway 转发的客户端 IP) 15 分钟 5 次，全局 15 分钟 30 次，超限 `429` + `Retry-After`；成功不清计数 |
| 36 | 仅 12h 绝对过期，无空闲超时；`last_seen_at` 至多 5 分钟写一次；退出置 `deleted_at`；control 每日物理删除过期超 1 天的行（逻辑删除规则的例外） |
| 37 | nginx（digest 固定）；S0 只开 `127.0.0.1:8080`，`/manage/` 静态、`/api/v1/admin/` 反代；固定子网与 gateway IP，uvicorn `--forwarded-allow-ips` 仅该 IP |
| 38 | `ADMIN_ORIGINS` 精确列表，默认 `http://127.0.0.1:8080`、`http://localhost:8080`，Host 同表校验；`settings.dev.toml` 另加 `http://localhost:5173`；CI 检查生产配置无非 8080 的 http origin |
| 39 | 启动 `GET /session`，`401` 跳 `/manage/login`，CSRF 存内存；fetch 封装加 `X-CSRF-Token`；`401` 带原路径跳登录，`403 CSRF_REJECTED` 重取 session 后提示刷新，不自动重放；登录页只有密码框 |
| 40 | S0 只建 `admin_app.py`；验证 docs/redoc/openapi.json 关闭，无会话 `401`、无 CSRF `403`；public app 与负向测试在 S7 |

## M12 视频解读用例（S0 范围）

| Q | 决定 |
| --- | --- |
| 41 | `VideoTaskCreate` 保留完整字段；S0 配置字段为 null 时 digest 用 sentinel、`provider_revision_id` 留空；非 null 返回 `422 INVALID_INPUT`（S1 移除）；AT-02"改变默认模型"在 S1 验收 |
| 42 | 短链不在 API 联网：按规范化短链受理，Worker 在 acquire 经 M09 解析并填 `source_id`；匹配返回 `match:null, reason=short_link_unresolved`（SPEC §4）；S0 只实现 URL 规范化纯函数，短链仅校验 host |
| 43 | T1 在实例锁内读 control 的磁盘采样，超线或采样过期均 `503 DEPENDENCY_UNAVAILABLE`（`disk_low`）；S1 实现，采样字段归属待 M09 |
| 44 | `/tasks/{id}/retries` 仅接受 video，其他 kind `409 INVALID_TRANSITION`；S3 实现 |
| 45 | S0 页面：提交表单（URL、mode、depth、focus）与任务详情（快照、骨架提示、取消）；`intent` 固定 `new`，`reinterpret` 返回 `422` 至 S3 |
| 46 | `domain/identities.py` 纯函数 `normalize_video_input` 与 `request_digest`；`parse_video_url` 归 M09，S0 先实现；表驱动单测覆盖 p 参数、youtu.be、list=、追踪参数、userinfo、非 443、非 HTTPS |
