# 08: Worker 失联与投递丢失的对账

**What to build:** Worker 进程被外部 kill 后，任务不会永远停在 running：lease 到期后 reconciler 关闭旧尝试、带 `requeued` 事件重新排队，并在投递宽限满足后用新 generation 投递，由新的 Worker 接手；旧执行者的迟到写入被 fence 拒绝。投递重试预算耗尽时任务以可观察原因失败，而不是无限积压。

**Blocked by:** 06 任务被投递、领取并记录阶段

**Status:** ready-for-agent

**依据：** [M03 SPEC](../../m03-task-runtime/spec.md) Broker 丢失与换代、Claim/fence/lease、reconciler、TD-11、TD-12。REQ-03；TD-11（AT-06 整项在 S4 验收）、AT-05 的“修复不导致额外任务、无无限补投”部分。

- [ ] reconciler 按 SPEC §10.2 次序分批短事务、SKIP LOCKED；S0 实现终态以外的第 6 步：lease 已过期 → 关闭旧 attempt、使 fence 失效 → 未超期则 queued 并保留执行槽、写 `requeued` 事件，已超期则 `DEADLINE_EXCEEDED`（D31）
- [ ] 换代按 SPEC §9.3：仅当无有效 pending/claimed Outbox 且宽限满足时，旧 generation 置 superseded、`dispatch_generation` 递增并新建唯一 Outbox；宽限初始 60s，指数扩展至 5min；generation 上限取策略
- [ ] 投递重试预算耗尽 → failed `DISPATCH_EXHAUSTED`（E3）
- [ ] 旧 generation 的消息直接 ACK；旧 fence 的阶段写入与续租影响 0 行且不恢复旧状态
- [ ] 测试 TD-11：运行中任务的 Worker 进程被外部 kill，lease 到期后任务重排并被新 Worker 以更大的 fence 领取；kill 前保存的旧 fence 写入被拒绝；只有一个有效 Outbox generation
- [ ] 测试 TD-12：模拟 Broker 持续不可用（停止 Redis 仅在本测试内，用于触发投递失败），重试预算耗尽后任务 `DISPATCH_EXHAUSTED`，Outbox 不再无限补投
- [ ] 详情页显示重排后的 attempt_no 与状态，无倒退
