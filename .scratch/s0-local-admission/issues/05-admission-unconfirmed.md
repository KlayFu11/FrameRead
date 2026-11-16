# 05: 提交结果未确认时用同键找回

**What to build:** 当提交事务的 COMMIT 结果无法判断时，部署者看到 `503 ADMISSION_UNCONFIRMED`，页面保留原操作标识并提示用原键重发或查询，不会自动换键新建任务；如果事务实际已提交，用原键重发拿回原任务；如果事务在 COMMIT 前已回滚，得到依赖不可用错误且没有任何残留记录。

**Blocked by:** 03 提交视频任务并用原键找回

**Status:** resolved

**依据：** [M01 SPEC](../../m01-instance-platform/spec.md) 3.4 事务与 COMMIT 结果、测试决定 12；[M03 SPEC](../../m03-task-runtime/spec.md) 未确认与找回、夹具与 TD-06。REQ-03、REQ-11；AT-19 受理未确认与明确回滚、AT-02 响应丢失子场景。

- [x] 测试夹具：PG 线协议 TCP 代理，仅在 `tests/` 中，API 测试连接经由它；生产代码无开关（U1）
- [x] 模式一：丢弃 COMMIT 并断开 → 新连接按 (scope, key) 查不到 → `503 ADMISSION_UNCONFIRMED`，`action=resolve_same_key`（E8）
- [x] 模式二：转发 COMMIT 后、回包前断开 → 新连接查到 → 返回原任务 `202`（`replayed=true`）
- [x] 模式三：COMMIT 前断开 → `rolled_back` → `503 DEPENDENCY_UNAVAILABLE`，数据库中无 task、Outbox、事件
- [x] 日志记录 `commit_outcome=rolled_back/unknown`；驱动异常到两种结果的映射由以上三种模式证明（E10）
- [x] 外部制造 `40P01`/`40001` 时 `run_transaction` 整体重跑成功，幂等身份不变；COMMIT 阶段断连不重跑（Q10）
- [x] 客户端断开连接后（响应丢失）用原键重发得到原任务 ID
- [x] 前端：收到 `ADMISSION_UNCONFIRMED` 时保留幂等键并提供“用原键重试”，`GET /operations` 返回 `404` 时也不换键

## Answer

已实现并验证提交结果未确认时的同键恢复。真实 PostgreSQL wire-proxy 覆盖三种 COMMIT 故障，前端在请求发送前持久化不确定状态并锁定原始输入，支持同键重试和原操作查询；`QUEUE_FULL`、`DEPENDENCY_UNAVAILABLE` 与 `ADMISSION_UNCONFIRMED` 的文案和动作已区分。验证记录见 [`docs/validation/s0-ticket05/Ticket05.md`](../../../docs/validation/s0-ticket05/Ticket05.md)。

实现提交：`24adb23`。后端全套 `262 passed`，最终故障回归 `4 passed`，前端全套 `40 passed`，生产构建通过。实际浏览器已覆盖 COMMIT 丢弃、响应丢失、刷新保键、查询 `404`、同键重试和原操作查询恢复；隔离网关验收与 Docker/nginx 整体验收的边界见验证记录。
