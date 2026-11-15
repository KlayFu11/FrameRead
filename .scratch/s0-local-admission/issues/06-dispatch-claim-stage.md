# 06: 任务被投递、领取并记录阶段

**What to build:** 提交后的任务由 control 投递到 Celery，独立 Worker 领取后写入 `acquire` 骨架阶段，详情页显示 running、当前阶段和“S0 骨架：不会生成文章”。受理时 control 未运行，之后启动会补投；同一条消息重复到达不会产生第二次执行；draining 下停止新投递和新领取。

**Blocked by:** 04 运行策略与维护模式 CLI

**Status:** ready-for-agent

**依据：** [M03 SPEC](../../m03-task-runtime/spec.md) 投递、Claim/fence/lease、骨架阶段、事件写入、进程与 Celery 配置、健康；[M12 SPEC](../../m12-video-usecase/spec.md) video KindHandler 骨架。REQ-03；AT-05 受理后未发送与重复消息子场景。

- [ ] `task_attempts`、`stage_results`、`worker_heartbeats` 迁移；`task_events` 与已完成 `stage_results` 的不可变触发器只拦 UPDATE（E4）
- [ ] control 单进程 tick 调度：dispatcher 每 1s `FOR UPDATE SKIP LOCKED` 领取 pending Outbox，记录 claim_token 后事务外 `apply_async`，回写须匹配 claim_token/generation/epoch；调用 `gate.require(dispatch)`，draining 与 frozen 下暂停（Q24、D36、E5）
- [ ] Celery 配置按 SPEC §9.4（acks_late、prefetch 1、无 result backend、禁自动重试、visibility_timeout = 最大总期限 + 10 分钟）（D30）
- [ ] T2 Claim：实例锁 → `gate.require(claim)` → epoch、generation、执行槽、期限、取消检查 → fence 与 attempt 递增、lease、`claimed` 事件；已有有效 lease 或旧 generation 的消息直接 ACK 不执行；S0 注入 `NoProviderCallsRecovery`（Q26）
- [ ] 心跳线程独立 Session，每 10s 续租；续租失败设置事件，handler 在 `checkpoint()`/`fenced()` 处抛 `LeaseLost` 后不再写任何结果；心跳不递增 `state_revision` 与 `version`（Q23、D33）
- [ ] video KindHandler 骨架：写 `stage_key=acquire`、`input_hash=tasks.input_hash`、`output_json={"skeleton": true}`、`stage_completed` 事件，然后协作等待（Q19、D32）
- [ ] Worker 写 tmpfs live 文件；M03 注册 `worker_heartbeats` 探针，过期在 api-admin ready 中为 degraded（E6）
- [ ] 测试（真实 PG、Redis、独立 Worker 与 control 进程）：受理时 control 未启动，任务保持 queued 且 Outbox pending，启动 control 后被领取；测试直接重复 `apply_async` 同一消息，只有一个 attempt；draining 下不投递、不领取
- [ ] Playwright：提交后详情页从 queued 变为 running 并显示 `acquire` 阶段，截图
