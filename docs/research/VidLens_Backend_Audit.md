# VidLens 后端只读审计

审计对象：`D:\VScodeProject\FrameRead\reference-project\VidLens` 当前工作树。

审计范围：`cmd/vidlens`、`internal/httpapi`、`internal/jobs`、`internal/store`、`internal/resource`、`internal/outbound`，以及迁移、配置、Docker、后端测试和前端 SSE 对接。重点追踪提交任务、入队、领取、租约、并发、失败、恢复、取消、结果一致性、PostgreSQL 与 Redis 的真实职责、Schema/去重/重试语义。

证据状态：本文的路径和行号来自 2026-10-24 首轮读取的源码与测试文件，并在 2026-10-25 对配置、分享、导出和恢复做了定向复核；2026-11-09 又按“前端任务流、API/Worker 调度、媒体链路、Agent 链路、持久化、前端进度展示”六问定向核对关键实现。测试文件已阅读但未执行；没有启动 PostgreSQL、Redis、Asynq worker、FFmpeg、模型或前端服务；没有联网。VidLens 当前目录没有可用的 `.git` 元数据，因此行号对应当前工作树，不能映射到提交版本。报告只读分析，没有修改 VidLens 业务代码。

## 结论

VidLens 的真正业务状态在 PostgreSQL。`job_runs`、`job_attempts`、`generation_requests`、`qa_turns`、`run_events`、`task_outbox`、`idempotency`、`resource_leases`、`media_assets` 和 `storage_reservations` 共同构成可恢复的控制平面。Redis 主要承担三类职责：Asynq 的任务投递媒介、资源槽位的短期协调键、短 TTL 缓存/限流键。Redis 中没有可单独解释任务最终状态的业务真相；资源申请还要由 PostgreSQL 租约作最后裁决。

核心链路是“数据库事务写入任务和 Outbox，worker 从队列领取后再次向数据库 Claim，数据库以 `execution_epoch`、`lease_owner` 和期限 fencing，结果在同一数据库控制事务中发布，SSE 再从数据库视图读取”。[internal/store/store.go:58-73](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/store.go:58) 的事务包装会取得 advisory lock `867914031`；[internal/store/execution.go:13-103](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/execution.go:13) 的 Claim、[internal/store/execution.go:109-122](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/execution.go:109) 的 Heartbeat、[internal/store/execution.go:187-239](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/execution.go:187) 的 Fail 和 [internal/store/execution.go:294-327](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/execution.go:294) 的 Step 都把执行状态变化落到 PostgreSQL。这个设计比“Redis status + worker 直接写结果”更容易解释恢复和并发边界，是 FrameRead 重构时最值得保留的部分。

当前实现的主要边界如下：

- Asynq delivery retry 与数据库业务 retry 是两套机制。前者处理 broker/task delivery，后者由 `Store.Fail` 根据 transient、失败次数、active budget 和 deadline 决定；不能只看队列重试次数判断业务是否会重跑。
- 取消是协作式的。API 先把 run 标为 `cancel_requested`；worker 下一次 Claim、Fail、Suspend 或 Repair 才会将它终止。共享 source run 仍被其他 request 使用时，取消一个 request 不会取消共享 run。
- 结果发布有数据库原子边界。`FinishSource`、`Publish` 和 `CompleteAnswer` 在 fencing、快照/帧校验、pin、状态更新和事件记录之间保持同一控制事务；文件物理删除仍是事务外的后续清理，因此文件系统异常会表现为 `unavailable`/清理重试，而不会让数据库凭空回到未完成状态。
- Redis 资源键不是最终锁。[internal/resource/manager.go:43-158](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/resource/manager.go:43) 先 `SetNX` Redis 键，再调用 `Store.AcquireResource`，后者在 [internal/store/resources.go:10-36](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/resources.go:10) 中以数据库主键槽位作最终判断。Redis 不可用时资源申请直接失败，不会自动降级到内存或仅数据库模式。
- SSE 不是 token 流。[internal/httpapi/stream.go:146-313](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/httpapi/stream.go:146) 发送 snapshot、activity upsert、reset 和 keepalive；模型流在 worker 内部组装，前端最终通过数据库视图同步状态。

## 模块映射

| 层 | 主要路径与函数 | 真实职责 |
|---|---|---|
| 进程启动 | [cmd/vidlens/main.go:50-110](D:/VScodeProject/FrameRead/reference-project/VidLens/cmd/vidlens/main.go:50) | 加载配置、打开 PostgreSQL、迁移/Bootstrap、创建 resource/media/investigator/jobs、启动 HTTP 和 worker、优雅关闭 |
| HTTP/API | [internal/httpapi/server.go:42-125](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/httpapi/server.go:42)、[internal/httpapi/server.go:275-377](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/httpapi/server.go:275) | 路由、session/CSRF、幂等键、请求提交/取消/重试、view 查询 |
| SSE | [internal/httpapi/stream.go:28-145](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/httpapi/stream.go:28)、[internal/httpapi/stream.go:146-313](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/httpapi/stream.go:146) | 按 session/type/id 订阅，HMAC cursor，数据库轮询和 snapshot/upsert/reset |
| 任务状态 | [internal/store/store.go:58-108](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/store.go:58)、[internal/store/store.go:274-328](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/store.go:274) | advisory lock、迁移、事件序号、创建 run 与 durable Outbox |
| 执行控制 | [internal/store/execution.go:13-103](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/execution.go:13)、[internal/store/execution.go:109-173](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/execution.go:109)、[internal/store/execution.go:187-357](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/execution.go:187) | Claim、fence、heartbeat、lease 过期接管、失败/重试、checkpoint、暂停、Outbox claim/result |
| 恢复 | [internal/store/execution.go:359-468](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/execution.go:359)、[internal/jobs/worker.go:365-389](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/worker.go:365) | 查询非终态 run，结合 broker 状态处理缺失投递、依赖唤醒、期限/队列/资源等待 |
| 业务请求 | [internal/store/requests.go:22-240](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/requests.go:22)、[internal/store/requests.go:242-280](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/requests.go:242)、[internal/store/requests.go:311-512](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/requests.go:311) | request/turn 去重、共享 source、重试、取消、conversation/QA turn |
| 结果/媒体 | [internal/store/artifacts.go:96-162](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/artifacts.go:96)、[internal/store/artifacts.go:164-345](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/artifacts.go:164) | source snapshot、article 发布、QA answer 完成、frame/pin/reservation 一致性 |
| Worker | [internal/jobs/worker.go:47-87](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/worker.go:47)、[internal/jobs/worker.go:89-172](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/worker.go:89)、[internal/jobs/worker.go:175-329](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/worker.go:175) | Asynq 队列、Outbox 投递、Claim 后执行 Media/Agent、heartbeat、错误分类和 shutdown suspend |
| 资源 | [internal/resource/manager.go:43-158](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/resource/manager.go:43)、[internal/store/resources.go:10-71](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/resources.go:10) | Redis 短租约 + PostgreSQL 槽位租约、续租、释放、磁盘 reservation、内存闸门 |
| 外连 | [internal/outbound/client.go:17-104](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/outbound/client.go:17)、[internal/outbound/credentials.go:18-71](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/outbound/credentials.go:18) | URL/redirect/DNS/dial 的 SSRF 边界、代理、凭证客户端的目标校验 |
| Schema/迁移 | [internal/store/migrations/001_init.sql:10-44](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/migrations/001_init.sql:10)、[internal/store/migrations.go:8-41](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/migrations.go:8) | durable 状态、唯一约束、资源/事件表；迁移版本以注册表身份为准，不按文件名重排 |

## 链路 C：数据库真相、队列投递与可恢复执行

```mermaid
sequenceDiagram
    participant UI as Frontend
    participant API as HTTP API
    participant PG as PostgreSQL
    participant OB as task_outbox
    participant R as Redis/Asynq
    participant W as Worker
    participant RES as Resource Manager
    participant SSE as SSE

    UI->>API: POST /api/v1/requests + Idempotency-Key
    API->>PG: CreateRequestWithInput(Tx)
    PG->>PG: idempotency/hash + request/source/run
    PG->>OB: task_outbox(run,generation)
    API-->>UI: 201/200 + request view
    loop 每 1 秒
        W->>PG: Outbox() claim 10 rows, lease 30s
        W->>R: Enqueue vidlens.run, task id vl:run:generation
        W->>PG: OutboxResult(delivered)
    end
    R-->>W: Asynq task
    W->>PG: Claim(run,generation,owner)
    PG->>PG: epoch/attempt/60s lease/admission
    W->>RES: Acquire resource
    RES->>R: SetNX resource key, TTL 60s
    RES->>PG: AcquireResource(slot, lease 60s)
    W->>PG: Heartbeat/Checkpoint/Step
    W->>PG: Publish or CompleteAnswer
    PG->>PG: fence + pins + result + terminal event
    loop SSE poll
        SSE->>PG: RequestView/TurnView + event cursor
        PG-->>SSE: snapshot/activity/upsert
        SSE-->>UI: SSE event
    end
    Note over PG,W: reconcile 30s; missing delivery increments dispatch_generation and creates new Outbox
```

### C1. 提交和去重

`POST /api/v1/requests` 在 [internal/httpapi/server.go:275-298](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/httpapi/server.go:275) 做 session 认证、body 解码、`Idempotency-Key` 校验后调用 `Store.CreateRequestWithInput`。成功响应由 `accepted` 统一生成，首次为 201，命中 replay 为 200 并带 `Idempotency-Replayed: true`，同时返回 `Location` 和过期时间（[internal/httpapi/server.go:240-273](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/httpapi/server.go:240)）。

[internal/store/requests.go:22-40](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/requests.go:22) 的 `replay` 以 `(scope,key)` 查询 `idempotency`：同 hash 返回同一资源；hash 不同返回冲突；过期键返回 410。request 的 scope 是当前 session，retry 会将旧 request 纳入 scope 变化。Schema 的主键是 `(scope,key)`（[internal/store/migrations/001_init.sql:26](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/migrations/001_init.sql:26)）。这意味着幂等性是“同一用户/作用域、同一键、同一规范化输入”的语义，不是全局 URL 去重。

`CreateRequestWithInput`（[internal/store/requests.go:49-240](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/requests.go:49)）会规范 URL/purpose，冻结配置和输入 hash，按 source identity 和 article spec 处理以下几种情况：

1. 复用已有 `video_sources`/`source_snapshots`，或者创建 `source.prepare`/`source.restore` run。
2. 对相同 source 的 active/completed source 任务做 coalesce；不同 article spec 作为不同 subscriber 计入 admission。
3. 发现可复用 article 时直接绑定，否则创建/复用 `article.generate`。
4. 每个新 run 通过 `newRun`（[internal/store/store.go:294-328](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/store.go:294)）在同一事务写入 `job_runs`、初始 `run_events` 和 `task_outbox`，而不是先返回 API 再异步补一条队列记录。

这套语义的安全边界是：去重只保护 API 写入和数据库 run 创建；它不保证外部下载、模型调用、文件写入天然 exactly-once。模型和外部操作另有 `run_operations` 的操作键/提交次数记录（[internal/store/artifacts.go:411-551](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/artifacts.go:411)），用来避免已完成结果被重复消费，但 provider 本身仍可能在超时后已经执行。

### C2. Outbox、入队与领取

`Store.Outbox`（[internal/store/execution.go:338-345](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/execution.go:338)）在短事务中最多 claim 10 条未 delivered 记录，并设置 30 秒 `claimed_until`。`Worker.dispatch`（[internal/jobs/worker.go:175-216](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/worker.go:175)）读取冻结的 config/profile，生成 Asynq task type `vidlens.run`、任务 ID `vl:<run_id>:<dispatch_generation>`，设置最大 broker retry 25、timeout 和 deadline；只有 enqueue 成功或对同 ID 冲突任务核对 type/payload 后才调用 `OutboxResult(..., delivered=true)`。broker 错误按 1/5/15/30/60 秒回退（[internal/store/execution.go:347-357](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/execution.go:347)）。

因此，API 事务提交成功但进程在投递前崩溃时，数据库仍有 Outbox，下一次 dispatch 会补投。重复 dispatch 不会依赖随机 task id，而是通过确定性 task id 和 payload 校验去重。`Worker.reconcile`（[internal/jobs/worker.go:365-389](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/worker.go:365)）每 30 秒检查非终态 run；队列状态为 `missing` 且没有 pending Outbox 时由 `Store.Repair` 增加 `dispatch_generation`、重新排队并生成 Outbox（[internal/store/execution.go:362-468](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/execution.go:362)）。broker 状态为 `unknown` 时不自动判定丢失，避免把 inspector 暂时不可用误判成业务丢任务；代价是恢复可能延迟。

2026-11-09 定向核对补充：Worker 进程不是只监听一个 run 队列。`jobs.New` 为 `generation`、`interactive`、`maintenance`、`probes` 分别创建 Asynq server；generation 的最大 goroutine 数为 `MaxVideoConcurrency=64`，但真正开始执行仍由 PostgreSQL admission 裁决；interactive 为 1；maintenance 为 1 且映射 `maintenance:1`、`cleanup:2` 并启用 strict priority；probes 使用 `store.MaxConcurrentProbes`（[internal/jobs/worker.go:47-87](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/worker.go:47)）。同一进程的 dispatch loop 每秒运行，除 durable Outbox 外还会读取数据库中的待导出和模型探测记录；cleanup 任务每 5 分钟以确定性 task ID 投递一次，重复 enqueue 自动去重（[internal/jobs/worker.go:136-160](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/worker.go:136)、[internal/jobs/worker.go:175-215](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/worker.go:175)、[internal/jobs/worker.go:391-394](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/worker.go:391)）。这些队列承担不同工作类型，但 run 业务状态仍在 PostgreSQL。

### C3. Claim、租约和并发

`Store.Claim`（[internal/store/execution.go:13-103](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/execution.go:13)）在数据库事务中完成这些检查和变更：

- generation 必须匹配，终态和 `waiting_dependency` 不领取。
- `cancel_requested` 立即进入 canceled 终止路径；超过 deadline 或 queue wait limit 进入 failed。
- 仍有有效的 running lease 时不重复领取；过期的 running lease 会关闭来源步骤、计 active time、结束旧 attempt、增加 failure count，再决定是否重启。
- 通过 `admitExecution` 检查 live execution setting 和全局 pending admission；容量等待不启动 attempt，也不消耗 active/retry budget。
- 成功领取时递增 `execution_epoch`/`attempt_no`，写入 `lease_owner`、60 秒 `lease_expires_at`、`job_attempts`，并把 QA turn 置为 running。

后续写操作必须通过 `fence`（[internal/store/store.go:330-341](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/store.go:330)）核对 run 仍为 running、epoch 与 owner 相同、lease 未过期且 deadline 未到。旧 worker 即使在网络分区后恢复，也不能用旧 epoch 写 checkpoint、step 或结果。`Heartbeat`（[internal/store/execution.go:109-122](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/execution.go:109)）刷新数据库 lease 并计 active time；[internal/jobs/worker.go:217-329](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/worker.go:217) 中的执行循环大约每 10 秒 heartbeat。

并发上有两层限制：

- `jobs.New` 为 generation Asynq worker 配置最多 `config.MaxVideoConcurrency`（当前源码为 64），但真正是否开始执行由数据库 live setting/admission 再裁决（[internal/jobs/worker.go:47-87](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/worker.go:47)）。[internal/jobs/concurrency_test.go:17-140](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/concurrency_test.go:17) 覆盖运行中把 live limit 从 2 调到 10、再降回 2；降低不会中断已有任务，新任务会 busy 且不消耗 attempt/failure。
- `Store.Tx` 每次控制事务取得同一个 PostgreSQL advisory lock `867914031`（[internal/store/store.go:58-73](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/store.go:58)），使 request/run 状态变更容易串行化，但也给高并发写入带来全局锁竞争和 2 秒事务超时边界。这个锁不是媒体下载/模型调用锁，长耗时工作仍在事务外执行。

资源并发是另一套槽位控制。`Manager.Acquire`（[internal/resource/manager.go:43-158](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/resource/manager.go:43)）根据 `ai:interactive`、`ai:generation`、`asr`、`ffmpeg`、download 等名称申请 Redis TTL 键，再以 `Store.AcquireResource` 把同一 slot 写入 `resource_leases`；每 10 秒左右续租 Redis 和数据库，释放时使用 owner compare，避免删除别人的键。DB 端会清理已过期 lease，并以 `(resource,slot)` 主键防止双占用（[internal/store/resources.go:10-55](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/resources.go:10)）。[internal/store/resource_wait.go:26-167](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/resource_wait.go:26) 只记录有实时 holder 证据的等待区间，并合并重叠等待，避免把 stale wait 当成业务进度。

### C4. 失败、重试和恢复

`Store.Fail`（[internal/store/execution.go:187-239](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/execution.go:187)）先再次 fencing，再根据 worker 传入的 `transient`、`MaxRetries(kind)`、active budget 和 deadline 决定：

- 不满足条件：调用 `terminate(..., "failed", failure)`，写终态、结束 attempt、释放 pin/reservation 并写事件。
- 满足条件：关闭来源步骤、写 retry notice、结束 attempt，把 run 置为 `retry_wait`，递增 `failure_count`，保存 `retry_not_before` 和 failure，并清除 lease。

`Worker.handle`（[internal/jobs/worker.go:217-329](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/worker.go:217)）负责将 Media/Agent 错误分类；Asynq 的 delivery retry 和 `Store.Fail` 的业务 retry 分开。[internal/jobs/worker.go:330-364](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/worker.go:330) 对网络/预算等 transient 代码允许自动重试；若是文章审阅、结构或语义问题，虽然错误对象可能带 `CanRetry`，分类仍可能令 `automatic=false`，不会因为队列重试而盲目重复业务生成。服务关闭时 `Suspend`（[internal/store/execution.go:254-293](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/execution.go:254)）把可恢复 run 置为约 5 秒后的 retry_wait，并清除 lease。

`Store.Repair`（[internal/store/execution.go:362-468](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/execution.go:362)）覆盖以下恢复分支：取消或 deadline 终止；队列等待超时；资源等待 stall；Outbox 长时间未投递；依赖完成后的 wake；broker `archived/completed` 但数据库没有结果时失败；broker `missing` 且没有 pending Outbox 时新建 generation/Outbox。它会保留原 deadline 和 failure_count，所以“补投”不是无上限重置预算。`waiting_dependency` 主要用于 QA 等待 source restore；依赖成功时复制依赖事件后的步骤并重新排队，依赖失败/取消时终止 dependent run（[internal/store/artifacts.go:348-395](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/artifacts.go:348)、[internal/store/execution.go:430-468](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/execution.go:430)）。

### C5. 取消语义

`CancelRequest`（[internal/store/requests.go:242-280](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/requests.go:242)）在事务内锁住 request，冻结当前 segment 的 `through_seq`，将 request 标记 canceled、清空 active run，并调用 `cancelUnused`。只有当该 source/article run 没有其他 active request 或 waiting dependency 时，run 才会标成 `cancel_requested`；共享 run 仍被其他 request 使用时继续运行。已取消 request 的历史步骤因 watermark 被冻结，后续共享 run 的事件不会污染它的历史视图。

`CancelTurn`（[internal/store/requests.go:492-512](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/requests.go:492)）把 QA turn 和 run 标成 `cancel_requested`；worker 通过 Claim/Fail/Suspend/Repair 终止。也就是说，HTTP 取消成功返回不等于执行线程已经立即停止，前端应等待 SSE/GET view 变成 canceled。测试 [internal/store/store_test.go:70-134](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/store_test.go:70) 专门覆盖共享取消、冻结历史和幂等 replay，但本次未执行。

### C6. 结果一致性

source 完成路径在 [internal/store/artifacts.go:96-162](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/artifacts.go:96)：`FinishSource` fencing 后核对视频 hash、快照唯一性、transcript 和 media asset，再 `finishRun`；之后 `bindPrepared`（[internal/store/artifacts.go:164-241](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/artifacts.go:164)）在同一控制逻辑中把 waiting_source request 绑定到 snapshot，复用/创建 article run，并 pin 视频。

article 发布路径在 [internal/store/artifacts.go:255-316](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/artifacts.go:255)：`Publish` fencing 后核对 snapshot、所有 cited frame 为 ready、frame 属于当前 snapshot、总大小上限，再写 article、pin article 资源、把匹配 requests 置 completed，并完成 generation run。QA 完成路径 `CompleteAnswer`（[internal/store/artifacts.go:318-345](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/artifacts.go:318)）同样核对 frame ready/snapshot、写 answer、清 active turn 后完成 run。

`media_assets` 的 state 约束是 ready/deleting/deleted/unavailable，`storage_key` 唯一；Schema 见 [internal/store/migrations/001_init.sql:27](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/migrations/001_init.sql:27)。数据库 pin/reservation 防止正在引用的 asset 被清理；[internal/store/cleanup.go:10-50](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/cleanup.go:10) 说明物理清理在事务外进行并可重试。数据库结果和文件 bytes 因而不是同一原子系统：数据库先记录可验证的 asset/result，文件删除失败会留下清理状态；读取层会再次检查文件/媒体状态并在过期或不可用时返回对应状态。

## API、SSE 与前端同步

HTTP 路由在 [internal/httpapi/server.go:42-125](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/httpapi/server.go:42)。request 的创建、查询、取消、重试、article、activity、events、frame 和 conversation/turn 路由都由同一 server 提供；`healthz` 只检查 PostgreSQL（[internal/httpapi/server.go:44-51](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/httpapi/server.go:44)），不能作为 Redis/Asynq/模型健康的完整证明。写请求还通过 Origin/CSRF/session 校验（[internal/httpapi/server.go:151-224](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/httpapi/server.go:151)）。

`RequestView`/`TurnView`（[internal/store/views.go:547-600](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/views.go:547)）从 PostgreSQL repeatable-read 视图组装 status、execution、retry、actions、activity 和 stream position。cursor 使用 secret key HMAC，并绑定 session、资源类型和资源 ID（[internal/store/views.go:21-60](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/views.go:21)），不能在不同用户/资源之间复用。

`events`（[internal/httpapi/stream.go:146-313](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/httpapi/stream.go:146)）流程为：认证并读取当前 snapshot，解析 `Last-Event-ID` 或 `after` cursor，检查 cursor watermark 是否仍可用，按 `session:type:id` 订阅 Hub，发送初始 snapshot；如果数据库事件正好连续到 `seq+1` 且 step 的 last sequence 匹配，发送 `activity.upsert`，否则发送完整 `view.snapshot`。旧 cursor 已被清理时发送 `stream.reset`，并要求前端重新 GET；15 秒 keepalive，session 过期发送 auth 事件，终态后关闭。

Hub 由 [internal/httpapi/stream.go:28-145](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/httpapi/stream.go:28) 管理，全局上限 100、单 session 上限 4、每通道 buffer 32、每通道约 1 MiB；慢订阅者会被关闭，避免一个客户端拖住所有请求。Hub 每约 2 秒读取数据库视图，而不是把 Redis pub/sub 当事件真相。[internal/httpapi/stream_test.go:8-37](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/httpapi/stream_test.go:8) 覆盖慢订阅者、计数释放、替换订阅和重复 unsubscribe，未运行。

前端 [frontend/src/api/http.ts:50-83](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/api/http.ts:50) 默认带 credentials、contract 2、CSRF 和 idempotency key。[frontend/src/api/runtime.ts:44-58](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/api/runtime.ts:44) 使用带 credentials 的 EventSource；[frontend/src/api/live.ts:46-233](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/api/live.ts:46) 以 `after` cursor 建立 ResourceStream，使用 socket generation 防止旧连接覆盖新状态，校验 scope/schema，遇到 gap/reset 时用 HTTP snapshot 重同步，并采用指数退避。[frontend/src/contract/stream.ts:3-55](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/contract/stream.ts:3) 要求 upsert 必须是严格的 `seq+1`，否则安装 snapshot 或 resync；[frontend/src/app/useVisitor.ts:269-360](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/app/useVisitor.ts:269)、[frontend/src/app/useVisitor.ts:509-543](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/app/useVisitor.ts:509) 保存 pending idempotency key 并负责 submit/cancel/retry。[frontend/src/app/useVisitorConversation.ts:297-424](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/app/useVisitorConversation.ts:297) 对 QA turn 采用同一套 pending key、HTTP snapshot 和 cancel/retry 同步。该前端闭环与后端 cursor 设计相符，但本次没有运行浏览器或前端测试。

2026-11-09 定向核对补充：运行页的进度不是只显示一个百分比，而是把后端 view 的多个层次组合展示。`RunView` 同时读取 request 终态、execution phase/status/retry reason、`activity.current_step_id`、`recent_steps`、模型调用/发送计数、execution plan、已展示 frame 及 frame availability；再经 `ExecutionPlan`、`ActivityList`、`FrameTimeline` 展示阶段、动作日志、画面时间线，并根据 `actions.can_cancel/can_retry/can_read_article` 渲染操作（[frontend/src/ui/RunView.tsx:69-104](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/ui/RunView.tsx:69)、[frontend/src/ui/RunView.tsx:243-280](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/ui/RunView.tsx:243)）。因此 FrameRead 不宜把后端状态简化成单一 `progress: 0..100`；至少应保留 `status + stage + current_action + retained_result + actions`，否则前端无法恢复和解释失败。

## PostgreSQL 与 Redis 的职责边界

| 数据/能力 | PostgreSQL | Redis/Asynq | 断点行为 |
|---|---|---|---|
| run 最终状态、attempt、epoch、failure、deadline | 真相，带事务和 fence | 不保存最终业务状态 | Redis 丢失后可由 DB Recoverable/Outbox 重建；DB 不可用则 API/worker 控制面不可用 |
| 任务投递 | `task_outbox` 持久记录 generation、queue、失败次数 | Asynq task 和 delivery state | enqueue 失败留在 Outbox；inspector unknown 不误判，missing 可由 Repair 补投 |
| 资源槽位 | `resource_leases` 是最后裁决 | `vidlens:resource:*` TTL 协调键 | Redis 不可用时 Acquire 503；过期键可重建，DB lease 仍需核对 |
| 事件与 SSE cursor | `run_events` seq、revision、HMAC cursor 输入 | 无事件真相 | Redis 不参与 SSE 增量判断；事件保留不足时 reset + HTTP snapshot |
| frame/metadata cache | 读取前仍查 DB/文件状态 | `vidlens:cache:*` 固定 512 bucket、10 分钟 TTL，碰撞校验 key | Redis error/stale 视为 cache miss，回源 DB/文件；写缓存错误被忽略 |
| 频率限制 | 不作为持久计数 | `INCR` + 60 秒 TTL | `resource.Limit` 在 Redis 出错时按允许处理，属于 fail-open |

部署配置也体现了这个边界：[compose.backend.yaml:17-24](D:/VScodeProject/FrameRead/reference-project/VidLens/compose.backend.yaml:17) 使用 Redis 7、AOF、`noeviction` 和持久卷，[compose.backend.yaml:2-16](D:/VScodeProject/FrameRead/reference-project/VidLens/compose.backend.yaml:2) 使用 PostgreSQL 17 独立卷；但 AOF/volume 只能提高队列和协调恢复能力，不能替代 PostgreSQL 业务状态备份。[internal/resource/manager.go:251-275](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/resource/manager.go:251) 的 cache 是 best effort，不能将它升级为结果存储。

## Schema、迁移、配置和 Docker

### Schema 与迁移

[internal/store/migrations/001_init.sql:10-44](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/migrations/001_init.sql:10) 的关键约束包括：

- `job_runs` 包含 `kind/status/dispatch_generation/execution_epoch/attempt_no/failure_count/active_ms/deadline/queued_at/lease_owner/lease_expires_at/checkpoint/failure/dependency`；active status 上的 `(kind,work_key)` partial unique index 防止同一工作项重复活跃。
- `job_attempts` 对 `(run_id,attempt_no)` 和 `(run_id,execution_epoch)` 唯一，保留每次领取的 worker/heartbeat/outcome。
- `task_outbox` 对 `(run_id,dispatch_generation)` 唯一，保存 `not_before/delivered_at/claimed_until/failures`。
- `generation_requests` 保存 source、snapshot、active run、article、冻结 config、revision、segments、deadline 和 failure；状态为 waiting_source/generating/completed/failed/canceled。
- `idempotency` 以 `(scope,key)` 为主键，保存 input hash、resource ID 和 expiry。
- `run_events` 以 `(run_id,seq)` 为主键；`resource_leases` 以 `(resource,slot)` 为主键；`storage_reservations` 以 run 为主键。

迁移在 [internal/store/store.go:74-108](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/store.go:74) 取得 advisory lock `867914030`，逐个应用尚未记录的版本。注册表 [internal/store/migrations.go:8-41](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/migrations.go:8) 明确规定版本身份不依赖文件名排序：例如 version 18 对应 `019_model_recommendation.sql`、version 19 对应 `020_site_announcement.sql`、version 20 对应 `018_execution_settings.sql`。重构时不能简单按 SQL 文件前缀重排或重编号。

### 启动和配置

[cmd/vidlens/main.go:50-110](D:/VScodeProject/FrameRead/reference-project/VidLens/cmd/vidlens/main.go:50) 的生产启动顺序是 load config → `store.Open` → `Migrate` → `Bootstrap` → resource/media/investigator/jobs → worker → HTTP。启动还设置 `GOMAXPROCS=2`、约 768 MiB memory limit、HTTP header/read/idle timeout；收到信号后先关 HTTP，再让 worker 在约 30 秒内结束。

[internal/store/store.go:32-54](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/store.go:32)、[internal/store/store.go:146-257](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/store.go:146) 中，数据库 pool 的 max conns 为 10，control transaction 约 2 秒；secret key 派生 AES-GCM key 加密 provider/ASR credentials，并用于 cursor/CSRF 签名。[config.example.yaml:1-31](D:/VScodeProject/FrameRead/reference-project/VidLens/config.example.yaml:1) 给出新数据库的连接、`data_dir`、secret、model/ASR 和 optional reference/search 配置。YAML 只在新数据库 Bootstrap 时初始化内容配置/凭证，后续配置以数据库 revision 为准；`SaveConfig` 为配置 revision 和 credential ref 提供持久历史。

[Dockerfile.backend:1-23](D:/VScodeProject/FrameRead/reference-project/VidLens/Dockerfile.backend:1) 使用 Go 构建镜像，并包含 Deno、Python 3.12、`ffmpeg`、固定版本 `yt-dlp[default]`；以 uid 10001 运行。[compose.backend.yaml:28-50](D:/VScodeProject/FrameRead/reference-project/VidLens/compose.backend.yaml:28) 暴露 PostgreSQL 5544、Redis 6391、backend 8086，backend profile 默认不直接启动；数据目录、数据库、Redis 都使用独立卷或挂载。[docs/backend/startup.md:25](D:/VScodeProject/FrameRead/reference-project/VidLens/docs/backend/startup.md:25) 明确依赖 Linux/Docker 的 Unix system calls，Windows 本机不作为当前后端运行环境。

### 外连与 SSRF 边界

[internal/outbound/client.go:17-104](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/outbound/client.go:17) 对 DNS 结果、redirect 和实际 dial 地址重复检查，拒绝 localhost、单标签主机、私有/链路本地/保留地址、userinfo/fragment 和非允许端口；默认关闭环境 proxy，并在 redirect 时清除 Authorization/Cookie。[internal/outbound/credentials.go:18-71](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/outbound/credentials.go:18) 对模型 endpoint、proxy 和 TLS SNI/Host 做独立校验。`CreateTurn`（[internal/store/requests.go:311-477](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/requests.go:311)）还要求外部 source 使用 contract v2、网络开关开启，并限制 URL 数量。这个防护属于输入/传输边界，不能代替业务任务状态的幂等和 lease。

## 文档与源码不一致项

[docs/backend/startup.md:52](D:/VScodeProject/FrameRead/reference-project/VidLens/docs/backend/startup.md:52) 写着“public sharing is not implemented”。当前源码已实现分享：

- [internal/httpapi/server.go:102-106](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/httpapi/server.go:102) 注册 request share 的 GET/PUT/DELETE，以及 `/api/v1/shares/{token}` 和共享 frame content 路由。
- [internal/httpapi/shares.go:8-48](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/httpapi/shares.go:8) 实现启用/撤销分享、公开 shared record 和 frame；公开内容设置 `no-referrer`、`noindex`，共享图片保持 no-store。
- [internal/store/migrations.go:29](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/migrations.go:29) 注册 `017_request_shares.sql`，说明分享 schema 已被纳入迁移序列。

因此本审计以当前源码和迁移为准：分享已存在，`startup.md` 的该句是过时文档。是否有前端分享入口、分享 token 的产品范围仍需另查前端页面；这不改变后端路由已存在的事实。

## 已有测试与验证边界

以下是源码中找到的关键测试。它们证明项目作者为这些语义提供了回归入口，但本次没有运行，所以不能把测试断言当成本次环境的实测结果。

| 测试 | 路径与覆盖 | 本次状态 |
|---|---|---|
| `TestSharedCancelFreezesHistoryAndIdempotency` | [internal/store/store_test.go:70-134](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/store_test.go:70)：共享 source、replay、hash conflict、取消冻结历史 | 已读，未运行 |
| `TestClaimFencingAndConcurrentAdmission` | [internal/store/store_test.go:182-223](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/store_test.go:182)：过期 lease takeover、旧 worker fencing、并发 admission | 已读，未运行 |
| `TestSlowSubscribers...` | [internal/httpapi/stream_test.go:8-37](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/httpapi/stream_test.go:8)：慢订阅者、Hub 计数、替换/重复取消订阅 | 已读，未运行 |
| resource wait tests | [internal/store/resource_wait_test.go:39-223](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/resource_wait_test.go:39)：holder 证据、union interval、stale verification、冻结 queue limit | 已读，未运行 |
| `TestRealBrokerOutboxReplayAndLostDeliveryRepair` | [internal/jobs/worker_test.go:16-70](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/worker_test.go:16)：真实 broker、task retry/deadline/timeout、Outbox replay、generation repair | 已读，未运行 |
| worker failure tests | [internal/jobs/worker_test.go:71-195](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/worker_test.go:71)：durable terminal failure、semantic failure、终态不重复提交 | 已读，未运行 |
| live video limit | [internal/jobs/concurrency_test.go:17-140](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/concurrency_test.go:17)：动态并发上限、interactive admission、busy 不消耗 attempt | 已读，未运行 |
| outbound SSRF tests | [internal/outbound/client_test.go:1-29](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/outbound/client_test.go:1)、[internal/outbound/credentials_test.go:1-99](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/outbound/credentials_test.go:1)：私网编码、redirect、proxy、timeout | 已读，未运行 |
| frontend API/stream tests | [frontend/src/api/live.test.ts:1-127](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/api/live.test.ts:1)、[frontend/src/api/history.test.ts:1-24](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/api/history.test.ts:1)、[frontend/src/api/writes.test.ts:1-27](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/api/writes.test.ts:1)、[frontend/src/contract/stream.test.ts:1-69](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/contract/stream.test.ts:1) | 已读/索引，未运行 |

集成测试由 [internal/testsupport/services.go:16-64](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/testsupport/services.go:16) 读取 `VIDLENS_TEST_DATABASE_URL` 和 `VIDLENS_TEST_REDIS_URL`；环境变量的 skip/strict 逻辑在 [internal/testenv/environment.go:10-25](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/testenv/environment.go:10)。由于本次约束是“不启动服务、不修改环境”，没有设置或验证这些服务，也没有执行 Go、frontend、Docker 或 smoke script。因而本文只能确认“测试存在及其意图”，不能声称当前 checkout 测试通过。

## 2026-10-25 定向复核补充

1. **配置是版本化业务事实，但当前只有一个活动 runtime profile。** `SaveConfig` 在同一事务写入 `runtime_config_revisions`、更新当前指针，并给替换的模型/ASR 密钥生成新的 credential ref（`internal/store/store.go:224-256`）。这证明“任务冻结配置 revision、密钥轮换不追溯改写已接受任务”的机制存在。FrameRead 需要把该机制扩展为多个用户可命名、可选择的模型配置；不能把 VidLens 的单活动 profile 误写成多配置产品。
2. **模型运营目录与管理后台不是 FrameRead 要继承的能力。** `/api/v1/admin/providers`、`models`、`probes`、路由与执行设置在 `internal/httpapi/server.go:65-98` 注册，前端有完整管理站。它们是原项目站点运营功能；FrameRead 只保留设置页所需的最小配置、能力检查和密钥保护。
3. **分享撤销与图片 allowlist 已是后端事实。** 启用分享时按 request 创建 token，撤销时删除 token（`internal/store/shares.go:86-104`）；公开文章会清理内部身份并标记 `qa_available:false`（`shares.go:186-257`）。共享 frame 必须属于文章引用或已公开执行步骤，且 asset 为 ready（`shares.go:260-307`）。这满足“撤销后图片也不能继续访问”的关键边界，但 FrameRead 仍需把公开对象从 request 处理历史改成明确的 `article_version`。
4. **媒体恢复已经校验内容身份。** `FinishSource` 对 `source.restore` 比较旧 snapshot 与新 snapshot 的 `VideoHash`，不一致即返回 `MEDIA_UNAVAILABLE`（`internal/store/artifacts.go:96-110`）。这证明原系统不是仅凭 URL 恢复；FrameRead 应保留该原则，并进一步处理不同下载封装/格式导致的字节差异。
5. **导出和文章版本是不同生命周期。** 导出从 `PublishedArticle` 读取正式内容并按格式生成 Markdown/ZIP，导出文件可过期清理（`internal/exporting/service.go:70-84,220-250,258-313`）。FrameRead 应把“正式文章版本不可变”和“导出文件可重建”分开，分享绑定前者，导出不触发重新生成。

## 2026-11-09 六问覆盖矩阵

按用户要求的六个问题重新核对后，本文与另外两份审计的分工如下；结论是主链路已经理清，本轮主要补充“多队列”和“运行页如何消费 view”两个此前不够直接的细节。

| 用户问题 | 本文对应章节 | 协同文档 | 核查结论 |
| --- | --- | --- | --- |
| 前端如何提交任务、查询结果 | “API、SSE 与前端同步”；C1 | [VidLens_Media_Frontend_Audit.md](VidLens_Media_Frontend_Audit.md) 第3节 | `POST /api/v1/requests` 带幂等键，GET 权威 view；前端另保存 pending write，网络失败后沿用同一幂等键重放 |
| 长任务如何调度，API 和 Worker 如何协作 | 链路 C；C2/C3/C4 | [VidLens_Media_Frontend_Audit.md](VidLens_Media_Frontend_Audit.md) 第2节 | API 只在 PostgreSQL 事务中创建任务/Outbox；dispatch 投递，Worker 再 Claim；worker pool 与业务 admission 分层 |
| 视频、字幕、音频、截图如何处理 | PostgreSQL/Redis 职责边界及结果一致性 | [VidLens_Media_Frontend_Audit.md](VidLens_Media_Frontend_Audit.md) 第2节 | 媒体字节与元数据由 media service 处理，snapshot/transcript/asset 登记入库；截图受 operation、pin、hash 与预算约束 |
| LLM 和工具如何协同生成文章、回答问题 | 结果一致性与持久化边界 | [VidLens_Agent_Audit.md](VidLens_Agent_Audit.md) 全文 | Worker 调 investigator；模型与工具由 Agent 审计说明，业务状态仍回到 Store/PG |
| 哪些数据持久化、如何管理任务执行状态 | Schema 与迁移；链路 C | [VidLens_Agent_Audit.md](VidLens_Agent_Audit.md) “预算、错误处理和恢复” | PG 保存 run/attempt/outbox/event/operation/checkpoint/result 等事实；Redis 只做投递、短期协调和可选缓存 |
| 页面交互、数据请求和任务进度如何展示 | API/SSE；本轮 RunView 补充 | [VidLens_Media_Frontend_Audit.md](VidLens_Media_Frontend_Audit.md) 第3节 | SSE 推 view/upsert/reset，运行页组合 phase、动作、计划、画面和可用操作；断线从 GET 快照恢复 |

## 对 FrameRead 重构的保留边界

FrameRead 以合理设计和完整业务为前提展示后端工程能力。以下为 Python 重设计建议，不是 VidLens 新增能力；用户已确认 VidLens 为自有项目，可直接参考源码架构和数据流。应保留以下契约：

1. FastAPI 内部写接口在一个 PostgreSQL transaction 中完成规范化输入、`Idempotency-Key` hash、task 创建和 durable outbox；返回 `task_id` 后由 GET 快照或 SSE 读取数据库 view。个人设置接口同样要有配置 revision，密钥只在服务端凭据存储解密。
2. 用 PostgreSQL 的 `tasks`、`task_attempts`、`outbox`、`stage_results` 和 `task_events` 表达业务状态；幂等 scope/key/hash 优先由 tasks 的唯一约束承载，无独立生命周期需求不另建 idempotency 表。保留 generation、attempt、deadline、lease/fence、retry budget 和 unknown 调用账。运行取消先进入 `cancel_requested`，与发布在同一任务行上裁决；普通线程锁不能保护多进程执行权。
3. 推荐 Celery+Redis 或等价 broker 只做投递，不让 Redis status 成为业务真相；Worker 领取前后都回数据库 Claim/fence，broker 丢任务由 outbox/reconciler 补投。Worker 方案不是用户硬约束，PG SKIP LOCKED 是可行的减项备选。
4. 实现 `source.prepare → article.generate → publish` 与独立 `qa.answer`；文章发布必须在同一业务事务中校验 snapshot/frame、固定不可变文章版本和导图、写终态。草稿、attempt 和正式版本分开保存。
5. 分享 token 绑定正式文章版本，公开路由只返回文章、导图和 allowlist 图片；撤销 token 后页面、图片和缓存均失效。导出读取同一正式版本，缺图或 hash 校验失败就是导出失败，不重新调用模型。
6. 资源槽位优先复用任务/资源租约；若加入 Redis，区分短期协调与 PG 业务执行权。读取缓存故障可回源，保护供应商配额或机器容量的限流/准入失败则应暂停新受限工作，不能统一称为 best effort。媒体清理用持久引用和必要读取租约保护成果，在 PG 短事务内标记 deleting 后再删文件，防止检查引用与实际删除之间的竞态。

7. 管理端推荐 REST+GET 快照+SSE，`task_events` 关键事件与状态同事务写入，缺口重新取快照，慢消费者有界断开。个人实例数据按实例归属；独立公开路由集合只允许 token 绑定的正式版本和图片，不需要增加多租户或强制登录。
8. 超时、指数退避、错误分类和结构化请求/任务/调用关联日志纳入主链；缓存、provider 令牌桶及持续故障熔断需有对应场景和实验，不为关键词同时加入多种锁、队列或限流算法。单机 broker/Worker 故障恢复属于容错证据，不能直接表述为多机高可用。

这样得到的个人自托管项目仍能展示后端岗位关心的状态机、幂等、队列、租约、失败恢复、事件同步和结果一致性，同时避免把 VidLens 的完整媒体处理、模型运营路由、外连策略和全部迁移一次性搬进 Python。更细的 Python 模块拆分属于重构设计，不是本次源码审计的已实现事实。
