# 07: 取消、期限与等待位提升

**What to build:** 部署者在任务详情页点击“取消”，排队任务直接变为 canceled，运行中任务先显示“取消中”再收敛为 canceled；超过总期限的任务明确失败并显示原因；任务结束释放执行槽后，最早的等待任务按原 ID 获得执行槽并被领取执行。

**Blocked by:** 06 任务被投递、领取并记录阶段

**Status:** ready-for-agent

**依据：** [M03 SPEC](../../m03-task-runtime/spec.md) 取消（T7）、期限与终态、执行槽、reconciler 中的终态清理与等待位提升；[M04 SPEC](../../m04-task-sync/spec.md) allowed_actions、取消按钮、错误展示；[M12 SPEC](../../m12-video-usecase/spec.md) 骨架超期。REQ-03；AT-04 释放后按原 ID 执行、PRD S0 行“记录阶段后取消结束”。

- [ ] `POST /tasks/{id}/cancel`：实例锁 + `gate.require(cancel_request)`（draining 允许、frozen 禁止）+ task 行锁；queued/retry_wait 直接 canceled、Outbox superseded、释放执行保留；running 写 `cancel_requested_at` 与事件并返回 `202`；终态与重复取消幂等返回 `200`（E5）
- [ ] Worker 在心跳与检查点发现取消后抛 `CancelRequested`，经 T7 收敛为 canceled 并释放槽；Worker 失联时由 lease 到期后的下一次 reconciler 扫描收敛（D43）
- [ ] 超期：骨架自行发现 → failed `PIPELINE_NOT_AVAILABLE`；排队或失联后由运行时发现 → failed `DEADLINE_EXCEEDED`（E2）
- [ ] control 循环：deadline 扫描、终态清理（Outbox superseded、lease 与槽释放）、等待位按 `(created_at, id)` 提升并激活其 blocked Outbox；draining 下不提升（D36）
- [ ] 终态不可回退：对终态任务的 running 写入条件更新失败
- [ ] 前端：取消按钮仅在 `allowed_actions` 含 `cancel` 时显示；cancel_requested 显示“取消中”；失败时显示 `error.code` 对应说明
- [ ] 测试：通过 `policy set` 设置短期限触发两种超期（D37）；占满 E 与 Q 后取消一个运行中任务，等待任务按原 ID 进入 running；draining 下仍可取消；frozen 下取消返回 `503 MAINTENANCE`
- [ ] Playwright：提交 → running → 点击取消 → canceled，截图
