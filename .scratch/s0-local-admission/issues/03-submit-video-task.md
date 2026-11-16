# 03: 提交视频任务并用原键找回

**What to build:** 部署者在 `/manage/videos/new` 填写 B 站或 YouTube 链接、解读模式、深度和关注点后提交，得到 `202` 与任务 ID，跳转到 `/manage/tasks/:id`，详情页每 2s 轮询快照，任务保持 queued（尚无 Worker 领取）。网络重发或并发重发同一操作只对应原任务；同键不同输入得到 `409`；执行槽与等待位都满时得到 `503 QUEUE_FULL` 且不留下任何记录；可以用原操作标识找回已受理的任务。

**Blocked by:** 02 管理员登录与管理外壳

**Status:** resolved

**依据：** [M12 SPEC](../../m12-video-usecase/spec.md) 请求契约、规范化与身份、受理协作、管理页面；[M03 SPEC](../../m03-task-runtime/spec.md) 受理（T1）、未确认与找回中的 `/operations`、执行槽、数据表与迁移；[M04 SPEC](../../m04-task-sync/spec.md) 快照读取、TaskSnapshot 字段、状态合并、轮询、任务视图。REQ-02、REQ-03、REQ-11；AT-02 新提交子场景（并发、冲突）、AT-04 受理部分、AT-19 422/409/503。

- [x] 纯函数 `parse_video_url`、`normalize_video_input`、`request_digest`，表驱动单测覆盖 D51 的 host 与路径、p 参数、`youtu.be` 规范为 watch URL、`list=` 与追踪参数、userinfo、非 443、非 HTTPS；`b23.tv` 只校验 host、规范为 `https://b23.tv/{code}`，不联网（Q42、Q46、D50、D51、E11）
- [x] `POST /video-tasks`：`VideoTaskCreate` 完整字段、`extra='forbid'`；配置字段非 null `422`；`intent=reinterpret` `422`（`intent_not_available`）；topic 必须有 focus（Q41、Q45、D55）
- [x] `Idempotency-Key` 必填 UUIDv4；scope 为 `video:new`；digest 中空配置写 `"$default"` sentinel，`effective_input_json` 带 `config_resolution: "unresolved"`（R6、D53）
- [x] `tasks`、`task_outbox`、`task_events`、`resource_slots` 迁移；枚举以 CHECK 固定；`UNIQUE(operation_scope, idempotency_key)`；migrate 入口在同一 UoW 内写策略后调用 `sync_execution_slots` 预建 `execution:video` 槽行（E7）
- [x] T1 在一个事务内：实例锁 → 同键查重与 digest 比对（先于门禁、容量与默认配置解析，已受理操作直接找回）→ 仅新受理执行 `gate.require(admit)` → 取空执行槽或等待位 → task + Outbox（pending/blocked）+ `accepted` 事件；`deadline_at = db_now() + total_timeout`（E1；SPEC §7.1、§9.1，维护状态下允许幂等找回）
- [x] 同键同 digest 返回原 `TaskAccepted`（`replayed=true`）；不同 digest `409 IDEMPOTENCY_CONFLICT` 带原 `task_id`；满额 `503 QUEUE_FULL` 且无任何新增行
- [x] `GET /operations/{scope}/{key}` 找到返回 `200`，未找到 `404`
- [x] `GET /tasks/{id}`：REPEATABLE READ 一致快照，字段完整（S0：`draft_summary=null`、`unknown_call_count=0`、`allowed_actions` 推导），`progress` 为 `{stage, observed_at}`（Q31、D49）
- [x] 前端提交页：默认 complete/standard，complete 下可填 focus；每份表单草稿一个幂等键存 sessionStorage，得到明确 `202`/`4xx` 后清除；`422 details` 逐字段显示（D56）
- [x] 前端详情页：2s 轮询，终态停止；按 `(epoch, state_revision)` 单调合并的纯函数有 Vitest 单测；M12 说明面板显示“S0 骨架：不会生成文章”
- [x] 集成测试：`asyncio.gather` 并发同键只产生一行 task 与一行 Outbox；E 个执行槽 + Q 个等待位占满后两个新请求恰好一个 `202` 一个 `503`；满额时重发已受理操作返回原 ID
- [x] Playwright 经 gateway 完成登录 → 提交 → 详情页显示 queued，截图

## Answer

- **实现**：`0c03ded`；同键受理、容量事务、URL 规范化、快照 API、提交与详情页面及 gateway DNS 恢复。`c01f901` 已同步集成分支。
- **检查**：后端 `pytest -q --tb=no -p no:cacheprovider` 为 258 passed，前端 `vitest run --maxWorkers=1` 为 35 passed；Ruff、format、strict mypy、锁文件、TypeScript、production build 通过，OpenAPI/TS 重生成逐字节一致。
- **实际运行**：真实 PG/Redis 与 Compose gateway 下验证提交 202、重放 202、冲突 409、查询 200；Playwright 10 项真实交互通过，5 张桌面/移动截图已查看。API 地址切换后 2.516 秒恢复，gateway 未重启。
- **审查与边界**：最终完整实现差异连续两轮审查未发现新问题，含新增文件及测试断言；见 [验证记录](../../../docs/validation/s0-ticket03/03-video-admission.md)。Worker 领取、取消与列表属于后续 Ticket；远端 CI 与 Linux 宿主未验证，未 push。
