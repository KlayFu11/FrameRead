# M03 任务运行时 模块 SPEC

Status: ready-for-agent
日期：2026-11-15。依据：[Grill 批次 A](../frameread-v1/grill-batch-a.md)（M03 的 Q19～Q27，并取其中引用的 M01、M12 条目）、[模块地图 §3 M03](../frameread-v1/map.md)、[批次 A 待确认裁决](../frameread-v1/spec-resolutions-batch-a.md)（第一轮 U1、U2、R5、R6、R7、D08、D10、D14、D27～D43、D54；第二轮 E1～E8、E11、E14）。

## 问题陈述

视频解读任务从提交到结束，要经过受理、排队、投递、领取、执行、取消或终态。每一步都可能因进程退出、消息重复或丢失、客户端响应丢失、数据库提交结果不明而中断。如果没有统一的运行时内核，会出现以下问题：

- 网络重发同一次提交时建出多个任务；或响应丢失后无法找回已受理的任务（REQ-03，AT-02、AT-05）。
- 满额时若无界接单，待投递工作和执行积压会无限增长；若接单与投递记录不在同一事务内，会出现"有任务无投递"或"有投递无任务"（REQ-03，ADR 0004）。
- 已失联的旧 Worker 在新执行者接管后仍可能写入阶段或结果，覆盖新结果（AT-06）。
- 取消与完成竞争时没有唯一裁决，或者把 Celery revoke 当作取消的事实（REQ-03，AT-07）。
- 如果 S0 不把执行权、期限、取消检查和恢复契约定下来，S1 接入真实下载、ASR 与模型调用后，就要回头补救已经存在的写入路径，违背 PRD §6 "首次引入写操作即落实不变量" 的切片原则。

本模块的目标是：在 S0 落地运行时内核，使后续切片只替换 KindHandler 内的阶段内容，而不改变受理、栅栏、取消、恢复的契约。S0 的 video handler 只是受控骨架，只写 acquire 阶段，不生成文章（Q19）。

## 解决方案

以 PostgreSQL 为唯一权威状态，Redis 与 Celery 只负责唤醒（[SPEC §9](../../docs/prototype/SPEC_V1.md#spec-09)、[§10](../../docs/prototype/SPEC_V1.md#spec-10)）。

- **受理（T1）**：在实例锁内先按 `(operation_scope, idempotency_key)` 查重并比对 digest，再判定执行槽与等待位；成功时 task、初始 Outbox 与 accepted 事件同事务写入，满额或失败则不留下任何记录。`deadline_at` 在 T1 内由数据库时间计算。
- **投递**：control 进程以同步 tick 扫描 Outbox 并投递到 Celery。消息可能重复或丢失，以 generation、claim_token 与 PG 领取（T2）去重。
- **执行权（T2 与栅栏）**：Worker 在数据库内领取，递增 fence 与 attempt、签发 lease；之后每次写入都校验 fence、lease_token 与数据库时钟下的 lease_until。独立心跳线程每 10s 续租，续租失败或看到取消请求即停止本地工作，不再写结果。
- **取消（T7）**：排队任务同事务转 canceled；运行中任务先持久写 cancel_requested，再由 Worker 的检查点收敛。取消不等于外部调用已停止。
- **恢复与期限（reconciler）**：control 负责 deadline、等待位提升、lease 失联重排、Broker 丢失换代与取消收敛，三者同一套代码在 S0 实现。
- **可观测**：每次关键状态变化在同一事务内推进 `state_revision` 与 `event_seq` 并写入关键事件，供 M04 快照与 SSE 使用。
- **外部调用边界**：调用账与 unknown 判定由 M08 经 `CallRecoveryPort` 注入；S0 注入 `NoProviderCallsRecovery`，始终报告无在途调用（Q26）。

## 用户故事

### 受理与幂等

- US-01：作为部署者，我希望提交视频任务后立即收到 `202`、任务 ID 与快照地址，以便之后按 ID 查询，而不必等待解读完成。
- US-02：作为部署者，我希望 `202` 返回时任务与待投递记录已一起持久化，以便接单之后任务一定会被投递，不会只留下一个无法执行的记录。
- US-03：作为部署者，我希望同一 `Idempotency-Key` 与相同请求重发时拿回原任务，以便网络重试或刷新页面不会重复创建任务。
- US-04：作为部署者，我希望同一 `Idempotency-Key` 配不同请求时得到 `409 IDEMPOTENCY_CONFLICT` 并看到原任务 ID，以便发现误用而不覆盖已受理任务。
- US-05：作为部署者，我希望缺失或格式非法（非 UUIDv4）的 `Idempotency-Key` 被立即拒绝为 `422`，以便不会产生无法找回的任务。
- US-06：作为部署者，我希望任务已经结束后再用同一键重发仍返回原 ID 与当前状态，以便重发永远只回到同一个身份。
- US-07：作为部署者，我希望提交结果无法确认（提交响应丢失或数据库在提交时断连）时，用同一键找回，以便我不必猜测任务是否存在，也不必换键重来。
- US-08：作为部署者，我希望找回时若找不到原操作，系统返回 `503 ADMISSION_UNCONFIRMED` 而不是 `404`，以便我知道"无法证明没有任务"，应继续用同一键查询。
- US-09：作为部署者，我希望数据库已明确回滚的受理失败只留下"未受理"的结果，以便失败后不会出现半个任务。

### 容量与排队

- US-10：作为部署者，我希望执行槽空闲时新任务直接占用一个执行保留位，以便它马上可被领取。
- US-11：作为部署者，我希望执行槽占满、等待名额还有空位时，新任务进入等待位，以便临时高峰不会直接失败。
- US-12：作为部署者，我希望执行槽和等待名额都占满时收到明确的 `503 QUEUE_FULL` 且系统不留下任何任务或待投递记录，以便满额不会造成无界积压。
- US-13：作为部署者，我希望满额时对已受理请求的同键重发仍返回原任务，以便满额不影响找回已受理的工作。
- US-14：作为部署者，我希望执行槽释放后等待任务按 `(created_at, id)` 顺序提升并进入执行，以便排队顺序可预测且同一任务不会重复排队。
- US-15：作为运维中的部署者，我希望调小执行容量时多出的槽被标记为 retired，占用它的任务正常跑完，以便缩容不会打断正在执行的工作。
- US-16：作为运维中的部署者，我希望容量判定与受理同在一个实例锁下，以便两个并发请求在一个执行槽、一个等待名额的条件下只会有一个成功。

### 投递与重复消息

- US-17：作为部署者，我希望 control 不在线时，已受理任务仍能被找到并保持排队，以便接单与投递可以解耦。
- US-18：作为部署者，我希望 control 恢复后，已受理但未投递的任务会被投递并执行，以便投递中断不会让任务丢失。
- US-19：作为部署者，我希望 Broker 中同一任务的消息被重复投递时，只有一次领取成功，以便重复消息不产生第二次执行或第二个 attempt。
- US-20：作为部署者，我希望过期 generation 的旧消息被直接确认丢弃，以便旧消息不能接管新投递。
- US-21：作为运维中的部署者，我希望 Redis 或 Broker 数据丢失后，control 能依据 PG 中的状态产生新的投递代次，且不创建第二个业务任务，以便消息层故障不会改变任务身份。
- US-22：作为运维中的部署者，我希望投递失败按指数退避（最长 60s）重试，且超过投递预算后任务以 `DISPATCH_EXHAUSTED` 失败，以便投递故障不会无限补投。
- US-23：作为运维中的部署者，我希望"发布消息的次数"与"业务执行的次数"分开计数，以便排障时能区分投递重复与执行重复。

### 执行权、心跳与取消

- US-24：作为部署者，我希望 Worker 领取任务时只有一个执行者获得 fence 与 lease，以便多个 Worker 不会同时执行同一任务。
- US-25：作为部署者，我希望 Worker 在心跳中断或被 kill 后，lease 过期的任务能被 control 重新排队或明确失败，以便任务不会永远停在运行中。
- US-26：作为部署者，我希望旧 Worker 在失去 lease 后的任何写入都被拒绝，以便它不能覆盖新执行者的阶段或结果。
- US-27：作为部署者，我希望在任务运行中点击取消后，系统先持久记录"已请求取消"，Worker 在下一次心跳或检查点内停止并收敛为 canceled，以便取消结果可追踪且不依赖消息撤销。
- US-28：作为部署者，我希望排队或等待中的任务取消后立即进入 canceled，并释放其执行保留位，以便被取消的任务不会占用容量。
- US-29：作为部署者，我希望重复取消同一任务得到相同结果，以便重复点击不产生副作用。
- US-30：作为部署者，我希望取消已经结束的任务时返回其当前终态快照而不改变状态，以便终态不可回退。
- US-31：作为部署者，我希望运行中的骨架任务超过总期限后被明确标记为 failed 并带原因码，以便任务不会无限等待。
- US-32：作为部署者，我希望排队中的任务超过总期限后被标记为 failed 且原因码为 `DEADLINE_EXCEEDED`，以便等待也受期限约束。
- US-33：作为运维中的部署者，我希望 Worker 遇到未预期异常时任务转为 failed `INTERNAL_ERROR`，以便异常不会让任务卡在 running。
- US-34：作为运维中的部署者，我希望 Worker 在无法 Claim、数据库不可用或收到过期消息时不执行任何副作用，并让 PG 调度继续恢复，以便失败的消息不会造成隐性执行。

### 维护与恢复

- US-35：作为运维中的部署者，我希望维护状态为 draining 或 frozen 时不再开始新的领取、投递与受理，以便升级或维护期间不产生新的业务副作用；draining 时仍可取消任务，因为取消只会减少工作。
- US-36：作为运维中的部署者，我希望重启 Worker 或 control 后，已有任务的状态与 epoch 不倒退、不被重置，以便普通重启不改变已有的任务事实。

### 可观测与安全

- US-37：作为运维中的部署者，我希望每条关键事件都带有 `seq`、`state_revision` 与 `instance_epoch`，以便按顺序还原一个任务的生命周期并识别恢复事件。
- US-38：作为运维中的部署者，我希望一次请求、任务、尝试、阶段与 fence 之间的关系能在日志中关联，以便从一条失败任务反查到具体的执行尝试。
- US-39：作为运维中的部署者，我希望 Worker 心跳过期时健康检查显示为 degraded 而不是 healthy，以便"未知"不会被误认为正常。
- US-40：作为部署者，我希望任务接口只在管理入口可用，公开入口没有任何任务能力，以便分享访问者无法提交或取消任务。
- US-41：作为部署者，我希望任务错误体与日志中不出现 SQL、栈、内部路径或密钥，以便错误信息可以安全地展示与分享。
- US-42：作为后续模块开发者（Agent），我希望通过 `KindHandler` 与 `ctx` 注册新的任务类型，而不修改运行时内核，以便问答、导出、检查等后续功能复用同一套受理与执行契约。
- US-43：作为后续模块开发者（Agent），我希望 T6 与 T7 的同事务约定、`FencedTask` 的校验规则和 `CallRecoveryPort` 的注入方式在 S0 就明确，以便 S1 之后的写入模块不会绕过栅栏。

## 实现决定

标签说明：`[S0]` 本切片交付；`[S1]`、`[S3]` 等表示在该切片交付的接口或行为，S0 不实现也不得留开关（Q19）。括号内为依据，`D*`、`U*`、`R*`、`E*` 指[批次 A 待确认裁决](../frameread-v1/spec-resolutions-batch-a.md)。

### 受理（T1）

- [S0] 受理在一个 UoW 内顺序执行：获取实例锁并 `gate.require(admit)` 要求 `maintenance_mode=normal` 且 `restore_state=normal`（Q14、Q15、SPEC §7.1）→ 按 `(operation_scope, idempotency_key)` 查重 → 比对 digest → 判定执行槽与等待位 → 写 task、初始 Outbox 与 accepted 事件。幂等查重先于容量判定与默认配置解析（SPEC §9.1）。
- [S0] `Idempotency-Key` 头必填，严格校验为 UUIDv4（R6，以 SPEC §3 为准）。缺失或非法返回 `422 INVALID_INPUT`，不写任何记录（Q20）。
- [S0] `operation_scope` 由服务端固定生成，S0 仅使用 `video:new`；调用方不能指定 scope（SPEC §3，Q20）。
- [S0] 同键同 digest 返回原 `TaskAccepted`，即使原任务已结束也返回当前状态（SPEC §4.1）。`replayed` 仅在找回已有任务时为 true（D42）。
- [S0] 同键不同 digest 返回 `409 IDEMPOTENCY_CONFLICT`，错误体携带原 `task_id`，不修改原任务（Q20，AT-02）。digest 由 M12 按 SPEC §3.1 计算，M03 只比较不计算（Q20、Q46）。
- [S0] 满额（执行槽已满且等待位已满）返回 `503 QUEUE_FULL`，不写 task、Outbox 或事件（ADR 0004，SPEC §9.1）。满额时同键重发仍返回原任务（ADR 0004，Q20）。
- [S0] 成功返回 `202`，带 `Location` 与 `snapshot_url`，不声称任务已运行（SPEC §4.1）。
- [S0] `AdmissionRequest` 字段为 `kind`、`pool`、`intent`、`scope`、`key`、`request_digest`、`effective_input`、`input_hash`、`total_timeout`、`retry_of_task_id?`、`budget`（D42，E1）。S0 的 `budget_json` 为 `{"version":1,"limits":{}}`（D42）。
- [S0] S0 不解析默认配置、不做 provider 配置固定、不做磁盘阈值检查（Q41、Q43 的 S1 部分）。S0 的 `provider_config_id`、`asr_config_id` 非 null 时由 M12 返回 `422`（Q41）。S0 不调用 M05、M09、M10、M11（R14）。
- [S0] M12 只传入 `total_timeout`（取自 `policy_json` 的 video 总期限，S0 为 2h）。M03 在 T1 内计算 `deadline_at = db_now() + total_timeout`，并在 `TaskAccepted.deadline_at` 中返回持久化值（E1，替代 D54 的应用侧计算）。`deadline_at` 永不因重投或恢复而重置（SPEC §8.2）。
- [S0] `admission_class` 取 `execution` 或 `waiting`，等待数由 `admission_class=waiting` 的活动任务查询得出，不维护计数列（SPEC §9.1）。

### 未确认与找回

- [S0] COMMIT 阶段断连抛出 `CommitOutcomeUnknown`，不交给 `run_transaction` 重跑（Q10，SPEC §4.1）。COMMIT 已发出后连接断开即为 `commit_outcome=unknown`；断开发生在 COMMIT 发出之前为 `commit_outcome=rolled_back`（D06，E8）。两者在日志中区分。
- [S0] `commit_outcome=unknown` 时，受理路径换新连接后按 `(operation_scope, idempotency_key)` 查询一次：找到且 digest 一致返回 `202`（`replayed=true`），digest 不一致返回 `409`，未找到返回 `503 ADMISSION_UNCONFIRMED`（Q21，E8）。不轮询，不提示换键。
- [S0] `commit_outcome=rolled_back` 时不做找回，返回 `503 DEPENDENCY_UNAVAILABLE`，且不留下任何记录（E8，SPEC §4.1）。
- [S0] `GET /operations/{scope}/{key}` 找到原操作时返回 `200`，body 为 `TaskAccepted`（`replayed=true`）（D27）；未找到返回 `404`；数据库不可用返回 `503`（SPEC §4）。该端点的 `404` 与受理路径的 `503 ADMISSION_UNCONFIRMED` 语义不同，不得混用。`404` 能否证明未受理的问题见补充说明的文档冲突。
- [S0] 同键找回时不重新解析当前默认配置，也不因缓存失效而丢失绑定（PRD REQ-02）。

### 状态机与版本

- [S0] 对外状态取 `queued`、`running`、`cancel_requested`、`retry_wait`、`succeeded`、`failed`、`canceled`。S0 不产生 `retry_wait`，其状态枚举和迁移检查在 S0 定义（SPEC §10 状态图）。`stage` 与状态分开保存，S0 只使用 `acquire`（SPEC §10）。
- [S0] S0 允许的迁移：`queued→running`（T2）；`queued→canceled`（T7）；`queued→failed`（由运行时发现超期，`DEADLINE_EXCEEDED`，E2）；`queued→failed`（投递预算耗尽，`DISPATCH_EXHAUSTED`，E3）；`running→cancel_requested→canceled`（T7）；`running→failed`（handler 自己发现超期，S0 骨架为 `PIPELINE_NOT_AVAILABLE`，Q19、E2；或未预期异常，`INTERNAL_ERROR`，Q23）；`running→queued`（lease 失联且未超期，D31）；`running→failed`（lease 失联且已超期，`DEADLINE_EXCEEDED`，D31、E2）；`cancel_requested→canceled`（lease 失效后 reconciler 收敛，D43）。其余迁移不被允许（SPEC §10）。
- [S0] 终态不可回退。任何以非终态为前提的条件更新返回 0 行时，调用方视为迁移失败，不重试业务动作（SPEC §10.2）。
- [S0] 每次关键状态变化在同一 task 行锁事务内递增 `state_revision` 与 `event_seq` 并写入关键事件。心跳不递增 `state_revision`（SPEC §18）。
- [S0] `tasks.version` 随每次 `state_revision` 变化递增；心跳只更新 `lease_until`，不递增 `version` 与 `state_revision`（D33）。条件更新 0 行即 `VERSION_CONFLICT` 或迁移失败（Q9）。`updated_at` 由数据库触发器维护（Q9）。

### 执行槽（resource_slots）

- [S0] 执行槽 `resource_key = execution:{pool}`。`pool` 取值为 `video`、`qa`、`utility`（E11）；S0 只启用 `video`。策略键为 `pools.<pool>.execution_slots` 与 `pools.<pool>.waiting_slots`（E11）；S0 的 video 取值为 E=2、Q=4（D08）。槽行与等待位按 E 个执行槽加 Q 个等待位预建（Q22，SPEC §6.2、§9.1）。
- [S0] 槽行预建与容量同步由入口组合调用 M03 的 `sync_execution_slots`：migrate 空库初始化与 `policy set` 在同一 UoW 中，先由 M01 写入策略，再调用它（D35、E7）。`policy set` 调小容量时，多余槽由该函数置为 `retired`（Q22，SPEC §6.2）。M01 不依赖 M03（E7，map §4.2）。
- [S0] T1 在实例锁下以 `FOR UPDATE SKIP LOCKED` 选取空闲槽并绑定 `assigned_task_id` 与 `assigned_fence`。执行保留位一直持有到任务终态，并在同一 T7 事务内释放（SPEC §6.2、§9.1）。
- [S0] 调小容量时多余槽置为 `retired`；占用者运行至结束、释放后不再被分配（Q22，SPEC §6.2）。
- [S0] 等待位提升：control 每个 tick 按 `(created_at, id)` 将最早等待任务绑定空闲槽，并激活其 Outbox（SPEC §9.1、§9.3，Q24）。等待位提升属于 `dispatch` 门禁类别，draining 与 frozen 下禁止（E5、D36）。
- [S0] 执行槽 E 与 Worker 并发分开配置；E 大于总并发时，启动只记 warning（D40）。
- [S0] 槽原语只覆盖 execution 槽。处理/Provider 槽的短租约属于 S1（SPEC §8.1）。

### 投递（Outbox 与 dispatcher）

- [S0] Outbox 每个任务的每个 `generation` 唯一。`delivery_status` 取值为 `pending`（待投递）、`blocked`（等待位，不投递）、`claimed`（已领取）、`published`（已投递）、`superseded`（已被取代或取消），由迁移 CHECK 固定（SPEC §9.1、§9.2、§9.3；见下方"枚举"决定）。
- [S0] control 每 1s 使用 `FOR UPDATE SKIP LOCKED LIMIT batch` 领取到期的 `pending` 记录，batch 为 50（D08），写入 `claim_token`、`claim_until`、`publish_attempts` 后提交，然后在事务外调用投递（SPEC §9.2，Q24）。
- [S0] `gate.require(dispatch)` 在 draining 与 frozen 下禁止，因此 draining 时 dispatcher 暂停投递（D36、E5）。
- [S0] 回写只在 `delivery_status=claimed` 且 `claim_token`、`generation`、`instance_epoch` 与 `claim_until` 均匹配时成功；影响行数为 0 时只记录 stale callback，不恢复旧状态（SPEC §9.2）。
- [S0] Celery 投递名 `fr:{epoch}:{task_id}:{generation}` 只作观测标识，不假定 Broker 按 ID 去重（SPEC §9.2）。投递 `retry=False`，重试由 dispatcher 控制（SPEC §9.2、§9.4）。
- [S0] 投递失败记录错误类别与下次 `available_at`，指数退避加抖动，间隔上限 60s；投递重试预算为 10 次（D08）。预算耗尽时任务以 `DISPATCH_EXHAUSTED` 失败（E3，登记于 SPEC §4.1 任务错误码）。超过总期限时按运行时发现超期处理，用 `DEADLINE_EXCEEDED`（E2）。
- [S0] 发送成功但回写前退出时允许重复消息，由 Claim 去重（SPEC §9.2）。数据库不可用时不假定投递记录已经保存（SPEC §9.2）。
- [S0] 任务进入终态、取消或换代时，将相关 Outbox 标为 `superseded` 并清空 `claim_token` 与 `claim_until`（SPEC §9.2）。

### Broker 丢失与换代（reconciler）

- [S0] reconciler 查找满足以下全部条件的任务：非终态、持有执行保留位、没有有效执行 lease、没有 `pending` 或有效 `claimed` 的 Outbox，且最近一次投递尝试已超过宽限（Q24，SPEC §9.3）。
- [S0] 处理时按全局锁顺序锁实例、task 与当前 generation 的 Outbox；仅当 `claim_until` 已过期且条件仍成立时，把旧 generation 标为 `superseded`、递增 `dispatch_generation` 并新建唯一 Outbox。原 task ID、预算与期限不变（SPEC §9.3）。
- [S0] 宽限初始 60s，对重复未领取的任务指数扩展，最长 5min（SPEC §9.3）。每个任务同一时刻最多一个有效待投递 generation；generation 总数上限为 5（D08）。
- [S0] 等待位任务不因扫描而补投（SPEC §9.3）。过期的旧 generation 消息直接 ACK（SPEC §9.3）。

### Claim、fence 与 lease

- [S0] T2 Claim 在锁 task 后检查：`instance_epoch` 为当前值、generation 为当前值、执行槽绑定正确、未超期限、无取消请求、非终态（SPEC §10.1）。
- [S0] 若已有有效 lease，拒绝并 ACK 消息，不执行。若没有有效 lease，先调用 `CallRecoveryPort`（S0 为 `NoProviderCallsRecovery`），再递增 `fence` 与 `attempt_no`，生成随机 `lease_token`，设置 `lease_until`，创建 attempt 行并写入 running 事件（SPEC §10.1）。
- [S0] `FencedTask` 字段为 `task_id`、`instance_epoch`、`attempt_no`、`fence`、`lease_token`（D10），值类型由 M01 定义，M03 负责构造。
- [S0] lease 时长 60s，心跳间隔 10s（D08）。lease 判断全部使用数据库时间（`clock_timestamp()` 或 UoW 的 `db_now()`，D14），Worker 本地时钟不参与接管决定（SPEC §10.1）。续租只更新 `lease_until`（D33）。
- [S0] lease 失联后的恢复判定：S0 没有外部调用，因此失联一律视为可恢复。未超期则重新排队并保留执行槽，事件为 `requeued`（E14）；已超期则以 `DEADLINE_EXCEEDED` 失败（D31、E2）。
- [S0] 每次写阶段、产物登记、续租或结果，都锁 task 并在同一事务内校验 `epoch = current AND fence = claimed_fence AND lease_token = claimed_token AND lease_until > clock_timestamp()`，并检查允许的状态（SPEC §10.1）。
- [S0] 每个 Celery child 同步执行一个任务（SPEC §9.4，Q23）。心跳由 child 内的独立线程使用独立 Session，每 10s 续租（Q23，D08）。
- [S0] 续租失败或取消请求出现时设置 `threading.Event`。`ctx.checkpoint()`、`ctx.fenced()`、`ctx.cancel_requested()` 在检查后抛出 `LeaseLost`（不写结果）或 `CancelRequested`（转 T7）（Q23）。
- [S0] 未预期异常转为 `failed` 且 `error` 码为 `INTERNAL_ERROR`，前提是 fence 仍有效；否则不写（Q23，SPEC §10.1）。
- [S0] S0 骨架阶段不设单独的阶段上限，只受总期限约束（D30）。

### 取消（T7）

- [S0] `POST /tasks/{id}/cancel` 锁实例与 task（Q24，SPEC §10.3）。取消经 `gate.require(cancel_request)` 门禁：draining 下允许（只会减少工作），frozen 下禁止（E5）。
- [S0] queued 或 waiting 任务同事务转 `canceled`、把 Outbox 标为 `superseded`、释放执行保留位并写事件，返回 `200` 快照（SPEC §4、§10.3）。
- [S0] running 任务写入 `cancel_requested_at`、状态 `cancel_requested` 与事件，返回 `202` 快照（SPEC §4、§10.3）。不得使用 Celery revoke 或 terminate 作为数据库取消（SPEC §10.3）。
- [S0] Worker 在心跳中看到取消请求后设置 Event，下一次检查点抛出 `CancelRequested`，转 T7 写入 `canceled` 并释放执行保留位（Q23、SPEC §10.3）。
- [S0] Worker 失联时，`cancel_requested` 在 lease 到期后的下一次 reconciler 扫描中转为 `canceled`（D43）。
- [S0] 重复取消幂等：终态与已结束的取消请求返回当前快照（SPEC §4）。

### 期限与终态

- [S0] `deadline_at = db_now() + total_timeout`，在 T1 内计算（E1）；永不因重投或自动恢复重置（SPEC §8.2、REQ-03）。S0 的 `total_timeout` 为 video 总期限 2h，来自 `policy_json`（D08）。
- [S0] 期限原因码按发现方区分（E2）：由运行时（control reconciler）发现超期，包括排队、retry_wait 与 lease 失联后已超期，一律用 `DEADLINE_EXCEEDED`；handler 仍在运行、自己发现超期时，用 handler 的错误码，S0 骨架为 `PIPELINE_NOT_AVAILABLE`（Q19）。
- [S0] 排队中超期：failed，`DEADLINE_EXCEEDED`，由 control 的 reconciler 收敛（D29、E2）。
- [S0] 运行中超期：由 Worker 在心跳中发现后停止，骨架任务转 failed，`PIPELINE_NOT_AVAILABLE`（Q19、E2）。Worker 失联时由 reconciler 收敛，使用 `DEADLINE_EXCEEDED`（D31、E2）。
- [S0] `visibility_timeout` 取最大总期限加 10 分钟，即 130 分钟（D30）。
- [S0] 终态写入、Outbox 的 `superseded`、执行保留位释放与事件在同一事务中完成（SPEC §10.3、§12.3 的 T6 模式）。

### 骨架阶段（S0 video handler）

- [S0] 领取成功后，在 T3 中写入 `stage_results`，`stage_key=acquire`，`input_hash` 取 `tasks.input_hash`（D32），`output_json={"skeleton": true}`，并推进 `tasks.stage` 与 `progress_json`（Q19）。`progress` 为 `{stage, observed_at}`（D49）。
- [S0] 写入阶段后，handler 继续心跳，直到取消请求或期限到达。骨架不产生 `succeeded`（Q19）。
- [S0] 页面标注"S0 骨架：不会生成文章"由 M04、M12 负责；M03 不生成面向用户的文案（Q19）。
- [S0] S1 删除骨架 handler，不留开关（Q19）。
- [S0] kill 与 barrier 夹具只放在 `tests/` 目录，生产代码不包含任何测试开关（Q19、Q25）。

### 事件写入与保留

- [S0] 关键事件类型由 M03 定义，Schema 由 M04 定义（D34）。S0 词表为 `accepted`、`claimed`、`stage_completed`、`cancel_requested`、`requeued`、`retry_wait`、`succeeded`、`failed`、`canceled`（D34）。`requeued` 为失联重排，已登记于 SPEC §18（E14）。S0 不产生 `succeeded` 与 `retry_wait`。`claimed` 即进入 running。临时进度、心跳不写关键事件（SPEC §18）。
- [S0] `projection` 包含 `status`、`stage`、`error_code`（D34），不含 Prompt、原文或密钥（SPEC §5）。
- [S0] 事件与所属状态变化在同一事务中写入，`seq` 与 `state_revision` 同步递增（SPEC §18）。
- [S0] 关键事件保留默认 7 天，天数入 `policy_json`（Q27、D08，SPEC §18.2）。S0 只写入不清理；清理作业在 S8 实现（Q27）。`task_events` 是允许物理删除的表之一（U2）。
- [S0] 不可变触发器只拦截 UPDATE（E4）。`task_events` 允许 DELETE，供 S8 保留期清理使用；`stage_results` 完成后禁止 UPDATE，代码中不提供其 DELETE 路径（E4）。

### 数据表与迁移

- [S0] M03 自己的表由 M03 编写迁移：`tasks`（预算两列除外）、`task_attempts`、`task_outbox`、`task_events`、`stage_results`、`resource_slots`、`worker_heartbeats`（map §3、§9）。
- [S0] 所有表带 SPEC §6 共同规则的通用列（`id`、`created_at`、`updated_at`、`deleted_at`、`version`）。允许物理删除的只有 `admin_sessions` 与 `task_events`（U2），因此 `task_outbox`、`resource_slots`、`worker_heartbeats` 一律逻辑删除，不做物理删除。
- [S0] 唯一性与检查约束按 SPEC §6.2 建立：`(operation_scope, idempotency_key)`、`(task_id, attempt_no)`、`(task_id, fence)`、`(task_id, generation)`、`(task_id, seq)`、`(resource_key, slot_no)`、`(task_id, stage_key, input_hash)`、`worker_id`，以及状态取值 CHECK。
- [S0] 枚举以迁移 CHECK 为准（正式决定）：`tasks.admission_class` 取 `execution`、`waiting`；`task_outbox.delivery_status` 取 `pending`、`blocked`、`claimed`、`published`、`superseded`；`tasks.status` 取本节"状态机与版本"列出的七个值。取值变更只能通过新增迁移完成。
- [S0] 索引包括 `(pool, status, not_before_at, created_at, id)`、活动 `lease_until`、`deadline_at` 的部分索引、`(created_at DESC, id DESC)`（SPEC §6.2）。
- [S0] 已完成的 `stage_results` 与 `task_events` 禁止 UPDATE，由触发器保护（E4，D14，SPEC §6、§7.2）。
- [S0] 前向外键按 SPEC §7.2 的规则，在被引用表首次出现的切片补上。S0 的 `tasks` 不含指向 source、snapshot、provider revision 的外键；这些列在 S1 增加（派生，依据 SPEC §7.2）。`stage_results.reused_from_id` 及其外键在 S3 增加（派生）。
- [S0] `budget_json` 为 `{"version":1,"limits":{}}`（D42）。`reserved_usage_json` 与 `known_usage_json` 列在 S0 迁移中创建，写入归 M08（D2c）。

### 进程与 Celery 配置

- [S0] Celery 5.6 prefork，`task_acks_late=True`、`worker_prefetch_multiplier=1`、`task_ignore_result=True`、JSON 序列化、禁用自动重试与 `self.retry`、`task_reject_on_worker_lost=False`（SPEC §9.4）。不配置 result backend（SPEC §8）。
- [S0] `visibility_timeout` 与 `app.conf.visibility_timeout` 取同一值 130 分钟（D30）。
- [S0] S0 只声明 `fr.video` 队列（派生，map §3 M03 与 SPEC §8 队列表；`fr.qa`、`fr.utility` 随 S5、S6 增加）。
- [S0] Worker 无法 Claim、数据库不可用或收到过期消息时，不执行副作用，记录后结束消息（SPEC §9.4）。
- [S0] 心跳写入 `worker_heartbeats`，字段含 `worker_id`、`instance_epoch`、`process_generation`、`last_seen_at`、`capacity_json`、`active_count`（SPEC §6.2）。
- [S0] control 在 S0 只启动 1 个实例，tick 调度为单进程同步循环；多实例的正确性由 `SKIP LOCKED` 与行锁保证，不以单实例为前提（R5，Q24）。每循环短事务、批量、SKIP LOCKED（Q24）。

### 接口与 Port

- [S0] Service 接口：`admit(uow, AdmissionRequest) → TaskAccepted`、`find_operation(scope, key)`、`request_cancel(uow, task_id)`、`sync_execution_slots(uow, pool)`（map §3 M03，E7）。`AdmissionRequest` 字段见受理一节（D42、E1）。
- [S0] Worker 侧 `KindHandler.execute(ctx)`，ctx 在 S0 提供 `fenced()`、`checkpoint()`、`cancel_requested()`、`slots`（execution 槽）（map §3 M03）。
- [S0] `reuse_completed()` 随 S3 的跨任务复用与同任务恢复引入，S0 不提供（map §3 M03，SPEC §3.2）。
- [S0] `CallRecoveryPort` 由 M03 定义，包含 `judge_lost_calls(uow, task)` 的判定入口（map §3 M03、M08）。S0 注入 `NoProviderCallsRecovery`，始终返回无在途调用（Q26）。S1 由 M08 替换并删除 S0 实现（Q26）。
- [S1] `complete_success(uow, fenced, result)` 与 T6 同 UoW 调用，与 M10 的发布对接，S0 不实现（map §3 M03、SPEC §12.3）。
- [S10] `interrupt_all_for_restore(uow)` 随 M17 恢复钩子引入，S0 不实现（map §3 M03、§5）。
- [S0] `KindHandler` 的注册入口由 Worker 进程入口注入，S0 只注册 video 骨架（SPEC §2、map §4.3）。

### 健康、日志与可观测

- [S0] M03 注册 Worker 心跳探针：心跳过期为 `degraded`，从未出现心跳为 `degraded`，不显示为 healthy（Q12、SPEC §20，AT-21，D41）。
- [S0] Worker 与 control 的 live 检查使用 tmpfs 心跳文件，由 `frameread health live` CLI 判定（M01，D13）。Worker 集群是否就绪由 M03 注册的 `worker_heartbeats` 探针在 api-admin 的 ready 中报告（E6）。两者分工，不互相替代。
- [S0] Redis 探针由 M01 注册（D41）。探针的超时与缓存规则见 M01（D13）。
- [S0] 运行时写入的日志字段至少包括 `request_id`、`task_id`、`attempt_no`、`fence`、`stage`、`status`、`event_type`、`dispatch_generation`、错误码。这些字段加入 M01 的日志 allowlist（Q11）。
- [S0] 健康检查与运行时的探针不得发起任何 Provider 调用（SPEC §20，AT-21）。
- [S0] 错误体按 SPEC §4.1 输出 `code`、`message`、`request_id`、`task_id`、`action`，不包含 SQL、栈、内部路径或原始 URL（SPEC §4.1）。任务错误码登记见 SPEC §4.1 的任务错误码小节（R7、E2、E3）。

## 测试决定

接缝编号沿用批次 A 约定：1 HTTP、2 进程、3 CLI、4 纯函数、5 浏览器。M03 的测试以外部可见行为为准，不断言内部调用次数或私有函数。

### 夹具（X2 中随 M03 的部分）

- 真实 PostgreSQL 与 Redis，启动时迁移到 head。
- 独立 Worker 进程与独立 control 进程，使用真实入口启动，不在测试进程内替身（接缝 2）。
- 故障手段在 S0 只用外部方式：不启动 control、直接对同一 task 重复调用投递、客户端在响应前断开、`asyncio.gather` 并发（Q25）。
- 提交结果未确认的故障制造：`tests/` 中的 PG 线协议 TCP 代理夹具（U1）。API 连接经此代理，提供三种模式（E8）：
  - 丢弃 `COMMIT` 并断开：结果为 unknown，确认时查不到，返回 `503 ADMISSION_UNCONFIRMED`；
  - 转发 `COMMIT` 后、回包前断开：结果为 unknown，确认时能查到，返回 `202 replayed`；
  - 在 `COMMIT` 之前断开：结果为 rolled_back，返回 `503 DEPENDENCY_UNAVAILABLE`，不留下任何记录。
  生产代码无开关。驱动异常与 unknown/rolled_back 的具体映射在实现时确定，由上述三种模式证明（E10）。
- kill 与 barrier 夹具只放在 `tests/` 目录，不进入生产代码（Q19、Q25）。
- 测试隔离：每个测试会话由迁移后的模板库新建独立库；每个测试结束后 TRUNCATE 业务表，并把 `instance_state` 重置为 normal（D38）。
- 期限类测试由夹具通过 `frameread policy set` 设置短期限，不依赖测试开关（D37）。

### S0 必测场景

- TD-01（AT-02 新提交子场景，接缝 1）：
  - a) 同键同输入并发两次提交，只产生一个任务，两个响应的 `task_id` 相同，task、Outbox 与 accepted 事件各一份。
  - b) 提交成功后客户端断开，同键重发得到原 `task_id`，不新增记录。
  - c) 同键不同输入得到 `409 IDEMPOTENCY_CONFLICT`，错误体含原 `task_id`，原任务不变。
  - d) 缺失或非 UUIDv4 的 `Idempotency-Key` 得到 `422`，无新增记录。
  - 改变默认模型的子场景在 S1 验收（Q41）；主动重新解读与重试属 S3。
- TD-02（AT-04 全项，接缝 1 与 2）：占满执行槽与等待位，两个不同新请求并发提交，恰好一个 `202` 与一个 `503 QUEUE_FULL`；`503` 不留下任何 task、Outbox 或事件；满额时同键重发仍得到原 ID；通过取消释放执行槽后，等待任务按同 ID 进入执行。
- TD-03（AT-05 受理后未发送与重复消息，接缝 2）：
  - a) 不启动 control 受理后，快照可查询为 `queued`；启动 control 后投递并领取。
  - b) 对同一 task 重复投递两次，只有一次领取成功，另一条消息被确认丢弃，无第二个 attempt，无第二份 accepted 事件。
  - c) 构造过期 generation 的消息，旧消息不能接管。
- TD-04（PRD S0 主链，接缝 1 与 2）：提交 → Worker 领取 → 写入 `acquire` 阶段 → 取消 → `canceled`，验证事件序列 `seq` 连续、`state_revision` 递增。排队任务取消直接 `canceled` 并释放槽。重复取消返回相同快照。
- TD-05（期限，接缝 1 与 2）：骨架任务与排队任务各自超过期限后转 `failed`，排队者为 `DEADLINE_EXCEEDED`，运行者为 `PIPELINE_NOT_AVAILABLE`。期限通过 `policy set` 设置短期限触发（D37）。
- TD-06（AT-19 基础，接缝 1）：`422`、`409`、`503 QUEUE_FULL`（无新增记录）、`503 ADMISSION_UNCONFIRMED` 的错误体均含机器类别、`action`、`request_id`。`ADMISSION_UNCONFIRMED` 经 TCP 代理的丢弃 `COMMIT` 模式注入，`202 replayed` 经转发 `COMMIT` 后断开模式注入，`503 DEPENDENCY_UNAVAILABLE` 经 `COMMIT` 前断开模式注入（E8）。后台失败可凭 `task_id` 与日志定位。`429` 不属于 M03。
- TD-07（AT-21 基础，接缝 1 与 2）：成功与失败任务的日志可关联 `request_id`、`task_id`、`attempt_no`、`stage`；停止 Worker 后心跳健康显示为 `degraded`；停止 control 不影响 live；健康检查期间没有外部 HTTP 请求。
- TD-08（空库迁移，接缝 1 与 3）：空库迁移到 head 后 M03 表存在；CHECK、UNIQUE、部分索引与不可变触发器存在；迁移失败时业务写入被阻止（AT-20 的 S0 子集，M01 门禁）。迁移失败用 E9 的方式注入。
- TD-09（执行槽缩容，接缝 3，Q22）：通过 CLI 调小 E 后，多余槽为 `retired`，占用任务正常完成，新受理按新容量判定。该场景无直接 AT，依据 Q22 自测。
- TD-10（维护门禁，接缝 3，Q15、E5）：`frozen` 下受理、领取、投递、取消均被拒绝；`draining` 下受理、领取、投递、等待位提升被拒绝，但取消允许；既有任务查询在两种状态下均不受影响。
- TD-11（lease 失联与旧执行者拒写，接缝 2，S0 必测，D39）：kill 正在运行的骨架 Worker，lease 未超期时任务重新排队（事件 `requeued`）并保留执行槽；超期时以 `DEADLINE_EXCEEDED` 失败；旧 fence 的写入影响 0 行。AT-06 整项仍在 S4 验收（D39）。
- TD-12（投递预算耗尽，接缝 2，E3）：让投递持续失败直至预算耗尽，任务以 `DISPATCH_EXHAUSTED` 失败，不再有新 generation 的有效投递。

## 不在范围内

- 调用账、预留与 unknown 判定的实现（M08，S1 起）；S0 只使用 `NoProviderCallsRecovery`（Q26）。
- 真实阶段、媒体获取、ASR、取帧与 LangGraph（M09、M11，S1）。
- 正式发布 T6 与 `complete_success` 的调用（M10，S1）。
- 处理/Provider 槽的短租约（M07/M08，S1）。
- 磁盘阈值检查与 `disk_low` 判定（M12 与 M09，S1，Q43、E12）。
- 同任务内的阶段复用与 `reuse_completed()`（S4）；跨任务复用与 `reused_from_id`（S3）。
- `POST /tasks/{id}/retries` 与 `retry_of` 的新任务创建（M12，S3，Q44）。
- reconciler 全窗口、旧 fence 拒绝、取消与发布 barrier（S4，SPEC §10.2、§10.3）。
- Redis 停止与恢复故障（D28，S4）。
- AT-06 整项验收（S4）；S0 仅有 TD-11。
- SSE、快照与 `allowed_actions`（M04，S1 起，Q31、Q32）。
- `qa`、`export`、`probe` 三类 kind 的 handler 与 `fr.qa`、`fr.utility` 队列（S5、S6、S8）。
- 关键事件的物理清理作业（S8，Q27）。
- 恢复终结钩子 `interrupt_all_for_restore`（S10，M17）。
- 运行概览、指标与 `/overview`（M16，S11）。
- AT-20 的规模查询、执行计划与 I/O 证据（S7、S8）。
- 任何 AT-02 的"改变默认模型"与 AT-03 的主动重新解读子场景（S1、S3）。
- 性能测量与优化（S9）。

## 补充说明

### 与其他模块的接口约定

- **M01**：提供 `UnitOfWork`（API 用 async，Worker 与 control 用 sync）、`gate.require(op)`（D07、E5）。`op` 类别包括 `admit`（受理）、`claim`、`dispatch`（投递与等待位提升，draining 与 frozen 下禁止）、`cancel_request`（draining 允许，frozen 禁止）、`session`（登录与退出，仅 frozen 下禁止）等，完整表见 SPEC §7.1。另提供 `run_transaction` 的 40001/40P01 重跑、`CommitOutcomeUnknown`、`FencedTask` 值类型（D10）、`db_now()`（D14）、错误码登记（`QUEUE_FULL`、`ADMISSION_UNCONFIRMED`、`IDEMPOTENCY_CONFLICT`、`INVALID_INPUT`、`INTERNAL_ERROR`、`PIPELINE_NOT_AVAILABLE`、`DEADLINE_EXCEEDED`、`DISPATCH_EXHAUSTED`，R7、E2、E3、D11）、策略读取（D08 各键，含 `pools.<pool>.execution_slots` 与 `pools.<pool>.waiting_slots`，E11）、日志 allowlist、Redis 健康探针（D41）。M01 不依赖 M03；槽行预建与容量同步由入口组合调用 M03 的 `sync_execution_slots`（E7）。
- **M02**：所有任务路由依赖 `require_admin`；M03 不实现会话逻辑（Q33）。
- **M04**：读取 `tasks`、`task_events`；快照与 SSE 协议由 M04 实现；M03 保证 `state_revision` 与 `event_seq` 的递增规则。事件 Schema 由 M04 定义（D34）；列表摘要 `TaskListItem` 由 M04 定义，并登记到 SPEC §5（D44、E14）。`unknown_call_count` 在 S0 为事实计数 0，S1 起查询 `provider_calls`（R9）。
- **M05**：`resolve_for_admission` 在 S1 才被 T1 调用。S0 不调用 M05（Q41，R14）。
- **M07**：M07 不调用 M03；写入时由调用方在同一 UoW 持有 `FencedTask`（map D2a）。
- **M08**：实现 `CallRecoveryPort`，写 `reserved_usage_json`、`known_usage_json`；T6 的 `has_open_calls` 在 S1 才参与（map §5）。
- **M09、M10、M11**：S0 不调用（R14）。
- **M12**：计算 `request_digest`、规范化输入、只传入 `total_timeout`（E1，由 M03 计算 `deadline_at`）、注册 video KindHandler；S0 对非 null 配置返回 `422`（Q41）；`intent=reinterpret` 返回 `422`（D55）；`/retries` 在 S3（Q44），仅接受 video（R14）。
- **M13、M14**：M13 在调用 M03 受理前先锁 conversation（map D3）；M14 使用 utility 池，S6 起。
- **M15、M17**：M17 的恢复钩子 `interrupt_all_for_restore` 与 M15 的分享禁用不属于 S0。

### 待后续模块 Grill 的事项

- M08：`CallRecoveryPort` 对已授权调用的判定，以及 S1 的 unknown 与用量结算语义。
- M08：`budget_json` 的 `version` 字段在 S1 起由 M08 与 M12 写入真实上限，版本号演进规则待 M08 确认（D42）。
- M09：`acquire` 阶段解析短链并填写 `source_id`（Q42）；磁盘采样的字段归属（Q43）。
- M12：`/tasks/{id}/retries` 的完整语义（S3，Q44）。
- M13：conversation 锁与 `active_turn_id` 的校正（map D3）。

### 文档冲突

无未解决项。`GET /operations` 的 `404` 只表示查询时没有该受理，客户端仍以原键重发、不换新键，已写入 SPEC §4。以下也已解决：control 实例数（R5）、逻辑删除例外（U2）、UUID 版本（R6）、错误码登记（R7）、`admission_class` 与 `delivery_status` 枚举（本 SPEC 正式决定，见数据表一节）。

### 待确认

无。第一轮 24 条待确认与第二轮 E1～E8、E11、E14 涉及 M03 的部分已全部写入正式决定。

### 与其他模块接口不一致之处

无未解决项。以下原不一致已由第二轮裁决消除：migrate 对 M03 的反向依赖（E7）、draining 与 SPEC §7.1 的差异（E5）、运行超期错误码（E2）、投递预算耗尽错误码（E3）、deadline 计算位置（E1）。
