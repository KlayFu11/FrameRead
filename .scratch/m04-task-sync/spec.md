# M04 任务状态同步 模块 SPEC

Status: ready-for-agent
日期：2026-11-15。依据：Grill 批次 A（[grill-batch-a.md](../frameread-v1/grill-batch-a.md) 的 M04 部分 Q28～Q33，并引用其中的 M01 Q5、Q8、Q11、Q17，M03 Q19、Q31）、模块地图 §3 M04（[map.md](../frameread-v1/map.md#3-模块清单)）。

## 问题陈述

- 管理员提交视频任务后，如果提交响应丢失、页面刷新、网络断开或关闭浏览器，就无法从权威状态重新找到该任务。操作者只能凭记忆重新提交，产生重复任务或误判为未受理。
- 任务状态在 PostgreSQL 中持续推进（排队、运行、等待重试、取消请求、终态）。如果前端各自缓存、不按版本合并，旧响应晚到会把新状态覆盖回去，终态可能被回退成运行中，恢复后 epoch 变化的旧游标也可能被当成新进展。
- 快照中的 `state_revision`、`event_seq`、`instance_epoch` 若来自不同时间点，客户端无法判断自己拿到的是不是最新状态，也无法安全地从快照切换到事件流。
- 任务列表若无界或按偏移分页，历史增多后会一次拉取过多行，或翻页时重复、漏项；过滤条件改变后，旧游标会指向错误位置。
- 读取路径（列表、快照、事件流）若写库、触发 Worker、调用付费模型，或暴露 Prompt、字幕、外部正文、密钥、SQL、异常栈，会破坏“重连不创建任务或付费调用”和安全要求。
- 前端底座（工程、路由、数据请求、错误与会话处理、类型生成）若由 M02 登录外壳与 M12 页面各自实现，行为会分叉。

## 解决方案

- 在管理 app 下提供三个入口：任务列表（keyset 分页、签名游标、`kind`/`status` 过滤）、任务快照（REPEATABLE READ 一致读取，返回 `TaskSnapshot` 与签名游标）、任务事件流（S1 起最小 SSE，S4 补全重连与慢客户端）。三者全部只读，并依赖 `require_admin`。
- S0 只实现列表与快照，前端用轮询（详情 2 秒、终态后停止；列表 5 秒）。PostgreSQL 是唯一权威，前端按 `(instance_epoch, state_revision)` 单调合并。
- 合并规则写成纯函数，用表驱动 Vitest 单测覆盖；epoch 变化时清空旧状态并提示恢复。
- 签名游标使用 M01 派生的 cursor 子密钥；列表游标与快照/事件流游标的作用域互不通用。
- 前端底座：Vite、React、TypeScript strict、React Router、TanStack Query、CSS Modules 加少量 token，不引入组件库；管理端与分享端同一工程两个入口（分享入口 S7 起）；后端导出管理端 OpenAPI，前端生成类型并提交，运行时只用 `fetch` 封装。
- 统一 `fetch` 封装处理 CSRF、401 跳转登录、403 提示刷新；错误展示机器类别、用户说明、可复制的 request ID 与动作。

## 用户故事

### 任务找回与查看（正常路径）

- US-01 作为部署者，我希望提交视频任务收到 `202` 后直接进入该任务的详情页，以便立刻看到它处于排队还是运行中。（S0）
- US-02 作为部署者，我希望提交响应丢失后，凭原任务 ID 或原受理身份打开详情，以便确认任务已存在，而不是重新提交。（S0）
- US-03 作为部署者，我希望刷新浏览器后仍能打开同一任务详情并看到服务端当前快照，以便刷新不丢失进度。（S0）
- US-04 作为部署者，我希望任务未终态时详情每 2 秒刷新一次，进入终态后停止刷新，以便观察进展又不持续请求。（S0）
- US-05 作为部署者，我希望任务列表每 5 秒刷新第一页，并能按任务类型和状态过滤，以便找到需要处理的任务。（S0）
- US-06 作为部署者，我希望按每页 20 条翻页，翻页时已存在的任务不重复、不漏掉，以便完整浏览历史。（S0）
- US-07 作为部署者，我希望修改过滤条件后列表从第一页重新开始，而不是沿用旧游标，以便不看到错位结果。（S0）
- US-08 作为部署者，我希望快照中 `status`、`stage`、`attempt_no` 与“排队、运行、等待安全重试、取消已请求、终态”分开展示，以便不把阶段或尝试误认为任务结果。（S0）
- US-09 作为部署者，我希望只有快照 `allowed_actions` 包含某动作时才看到对应按钮，以便不尝试无效操作。（S0）
- US-10 作为部署者，我希望 S0 骨架任务的详情页明确标注“S0 骨架：不会生成文章”，以便不把骨架结束误认为成文。（S0，提示由 M12 的 video 说明面板提供，D46）
- US-11 作为部署者，我希望任务 `result` 只在成功终态出现，`unknown_call_count` 大于 0 时突出展示，以便区分成功结果与未知调用。（S0 恒为 0 且不显示，D49；S1 起由调用账提供真实计数，R9）

### 断线、失败与会话

- US-12 作为部署者，我希望网络断开或轮询失败时继续看到最后一次成功的快照，并被告知数据可能已过期，以便不误以为任务已停止或已取消。（S0）
- US-13 作为部署者，我希望慢的旧响应晚于新响应到达时，页面不回退到旧 `state_revision`，以便状态不倒退。（S0）
- US-14 作为部署者，我希望任务进入终态后，即使再次轮询，页面仍保持终态，以便结果不因并发读取而变化。（S0）
- US-15 作为部署者，我希望访问不存在的任务 ID 得到统一 `404 NOT_FOUND`，以便错误不泄露其他信息。（S0）
- US-16 作为部署者，我希望使用被篡改或作用域不符的游标时得到明确拒绝，以便伪造游标不能看到不该看的范围。（S0）
- US-17 作为部署者，我希望服务端实例 epoch 改变（恢复事件）时，页面清空旧状态并提示“实例已恢复”，以便不把新旧 epoch 的 revision 混在一起比较。（S0 前端规则；S10 真实恢复）
- US-18 作为部署者，我希望无会话访问任务接口得到 `401` 并被带到登录页，登录后回到原页面，以便不丢失正在查看的任务。（S0）
- US-19 作为部署者，我希望在无管理员会话时任务数据不被读取，以便未授权访问得不到任何任务内容。（S0）
- US-20 作为部署者，我希望 `503 DEPENDENCY_UNAVAILABLE` 或 `MAINTENANCE` 时页面显示依赖或维护原因并保留已有快照，以便区分系统问题与任务问题。（S0）
- US-21 作为部署者，我希望 `QUEUE_FULL` 与 `ADMISSION_UNCONFIRMED` 两类 `503` 显示不同说明和动作，以便知道前者可稍后再申请，后者必须用原键找回。（S0，适用于所有提交与读取页面；动作词表见 D11，第 9 节）
- US-22 作为部署者，我希望每个错误都显示 request ID 并可复制，以便把页面现象与日志对应起来排障。（S0）
- US-23 作为部署者，我希望 `403 CSRF_REJECTED` 时页面提示我刷新会话，而不是自动重放写请求，以便不重复执行操作。（S0，写请求由 M02 与 M03 定义）
- US-24 作为部署者，我希望在多个浏览器标签页中查看同一任务，各页面独立合并、互不覆盖，以便多窗口查看不冲突。（S0）

### 一致性与性能

- US-25 作为部署者，我希望快照中的 `event_seq`、`state_revision`、`instance_epoch` 与游标来自同一个时间点，以便“同一快照”的含义可信。（S0）
- US-26 作为部署者，我希望任务推进时快照读取不会读到部分提交的状态（例如 stage 已变而结果未写），以便不看到半提交的结果。（S0）
- US-27 作为部署者，我希望列表每页最多 100 条，且查询次数不随行数增长，以便历史很多时页面仍然响应。（S0）
- US-28 作为部署者，我希望快照与列表读取完成后立即释放数据库连接，以便轮询不占用连接池。（S0）
- US-29 作为部署者，我希望服务端不为慢速浏览器无限缓存事件，超限时关闭连接并要求重新同步，以便服务资源有界。（S4 完整；S1 起连接上限生效）
- US-30 作为部署者，我希望 SSE 长连接在会话过期或撤销后，于下一轮检查时结束，以便长连接不会永久保有权限。（S1）

### 事件流与恢复

- US-31 作为部署者，我希望 SSE 断线后页面显示“连接中断”并以快照轮询恢复，而不是把任务标为已取消，以便不误判业务状态。（S1）
- US-32 作为部署者，我希望事件游标超出保留窗、序号不连续或签名无效时，服务端发送 `stream.reset` 并要求重新获取快照，以便不因缺口遗漏终态。（S1 最小实现；S4 补全矩阵）
- US-33 作为部署者，我希望重连时优先使用 `Last-Event-ID`，且游标不能跨任务使用，以便旧游标不会把进度接到错误的任务上。（S1）
- US-34 作为部署者，我希望普通容器重启后，快照与列表仍显示原 epoch 下的同一任务与状态，以便重启不丢失进度。（S0）
- US-35 作为部署者，我希望重复刷新、重连事件流或读取快照不会新建任务、不会触发 Worker 或付费调用，以便查看状态没有副作用。（S0 与 S1）

### 后续模块开发者（Agent）

- US-36 作为后续模块开发者（Agent），我希望 `TaskSnapshot` 与 `CriticalEvent` 的字段只有一份 Schema 来源并由 OpenAPI 导出，以便新增字段时不会在读取或展示环节遗漏。（S0 快照；CriticalEvent 随 S1 SSE 接入）
- US-37 作为后续模块开发者（Agent），我希望 `allowed_actions` 与 `unknown_call_count` 由服务端推导，前端不自行判断能否取消或是否存在未知调用，以便规则只实现一份。（S0）
- US-38 作为后续模块开发者（Agent），我希望 M04 不维护任务状态副本，只读取 `tasks` 与 `task_events`，以便不出现第二个真相来源。（S0）
- US-39 作为后续模块开发者（Agent），我希望统一的 `fetch` 封装、错误展示和会话跳转由 M02 与 M12 共用，以便登录页与任务页面行为一致。（S0）
- US-40 作为后续模块开发者（Agent），我希望 OpenAPI 与生成的前端类型提交进仓库，CI 重新生成并比对差异，以便接口漂移在合并前被发现。（S0）

## 实现决定

### 1. 接口与权限

- 三个入口都在管理 app 下：`GET /tasks`（列表）、`GET /tasks/{id}`（快照），以及 `GET /tasks/{id}/events`（SSE，S1 起加入）。路径省略 `/api/v1/admin` 的约定见 [SPEC §4](../../docs/prototype/SPEC_V1.md#spec-04)。（S0；SSE 在 S1）
- 三个入口全部依赖 `require_admin`，公开 app 不注册这些路由（Q33；[Q40](../frameread-v1/grill-batch-a.md)）。（S0）
- 三个入口全部只读，不写任何表，不触发 Worker，不调用 Provider，不创建任务。（S0）
- 请求参数按 [SPEC §5](../../docs/prototype/SPEC_V1.md#spec-05) 使用严格校验，未知字段或非法 ID 返回 `422 INVALID_INPUT`；未知任务 ID 返回 `404 NOT_FOUND`。（S0）
- DB 不可用返回 `503 DEPENDENCY_UNAVAILABLE`，不返回空列表。（S0）
- 错误体使用 M01 统一格式，包含 request ID（Q8、Q11）。（S0）
- 响应使用独立 allowlist Schema，不直接序列化 ORM 模型（SPEC §5）。（S0）

### 2. TaskSnapshot 字段与推导

- `TaskSnapshot` 按 [SPEC §5](../../docs/prototype/SPEC_V1.md#spec-05) 完整输出：`id, kind, intent, status, stage, state_revision, event_seq, cursor, instance_epoch, attempt_no, progress, deadline_at, cancel_requested_at, result, error, draft_summary, allowed_actions, unknown_call_count`（Q31）。（S0）
- `draft_summary` 在 S0 恒为 `null`（Q31）。草稿摘要在 S3 草稿链路接入后再返回实际内容。（S0 为 null；S3 起有值）
- `result` 仅在成功终态有值。S0 骨架不会成功，因此 S0 恒为 `null`（Q19、Q31）。（S0）
- `unknown_call_count` 在 S0 返回 `0`，这是事实计数：S0 尚无外部调用（Q31、R9）。S1 起改为查询 `provider_calls` 的未知调用数，由 M08 的调用账提供；查询失败时快照返回错误，不回落为 `0`（R9）。（S0 为 0；S1 起为真实计数）
- `allowed_actions` 由服务端按状态推导，前端不自行推导。S0 中唯一可能的取值为 `cancel`，出现在 `queued`、`running`、`retry_wait` 状态；`cancel_requested` 状态不出现该动作，页面显示“取消中”（Q31、D45）。（S0）
- `error` 只输出已脱敏的错误类别、说明与关联标识，不输出异常栈、SQL、上游响应体（SPEC §4.1）。任务错误码只出现在 `TaskSnapshot.error.code`，不作为 HTTP 状态（R7）。（S0）
- 任务错误码分两类归因（E2）：handler 仍在运行且自己发现超期时，使用 handler 的错误码，S0 骨架为 `PIPELINE_NOT_AVAILABLE`（S1 删除）；由运行时发现超期时（包括排队、`retry_wait`、lease 失联后已超期），一律为 `DEADLINE_EXCEEDED`。投递重试预算耗尽时为 `DISPATCH_EXHAUSTED`（E3）。以上码登记于 SPEC §4.1 任务错误码小节，由 M03 产生。（S0）
- 客户端以快照中的 `deadline_at` 为准显示期限，不在本地按提交时间自行推算；期限由 M03 在 T1 中用 `db_now()` 计算（E1）。（S0）
- `progress` 按存储值原样输出，临时进度不作为关键事件持久化（SPEC §18）。S0 骨架的 `progress` 为 `{stage, observed_at}`（D49）。（S0）
- `stage` 与 `status` 分开输出，前端不由 `stage` 枚举推断进展（SPEC §10）。（S0）

### 3. 快照读取

- 快照读取是单个 Session 的短事务，隔离级别为 REPEATABLE READ。在同一快照内读取任务行、`result`、`draft_summary`、当前 `event_seq` 与 `instance_epoch`，然后生成签名游标（[SPEC §18.1](../../docs/prototype/SPEC_V1.md#spec-18)、[SPEC §7](../../docs/prototype/SPEC_V1.md#spec-07)）。（S0）
- 快照读取只做查询，不加 `FOR UPDATE`，不等待业务锁，结束时在 `finally` 中释放连接（SPEC §7）。（S0）
- `state_revision`、`event_seq`、`instance_epoch` 与 `cursor` 来自同一快照（US-25）。（S0）
- 快照接口不接受游标输入，游标只在列表翻页与 S1 起的事件流中作为输入。（S0）
- 快照的 SQL 次数固定，S0 为一次任务行读取；S1 起增加固定次数的 `provider_calls` 聚合（SPEC §7.2）。（S0）

### 4. 任务列表

- 列表采用 keyset 分页，排序键为 `(created_at, id)`，方向为新到旧，翻页条件为严格小于游标位置（[SPEC §6.2](../../docs/prototype/SPEC_V1.md#spec-06)、[SPEC §7.2](../../docs/prototype/SPEC_V1.md#spec-07)）。（S0）
- 列表行使用摘要 DTO `TaskListItem`，字段为：`id`、`kind`、`intent`、`status`、`stage`、`state_revision`、`instance_epoch`、`created_at`、`deadline_at`、`cancel_requested_at`、`error_code`；不含 `progress`、`event_seq`、`result`、`allowed_actions`，需要时进入快照（D44）。（S0）
- 默认每页 20 条，上限 100，不提供无界或 `all` 形式（SPEC §4；Q30 无变化）。（S0）
- S0 只支持 `kind` 与 `status` 过滤（Q30）。过滤值为小写枚举：`kind` 取 `video/qa/export/probe`，`status` 取 SPEC §10 状态图中的状态；非法值或其他过滤参数返回 `422 INVALID_INPUT`，`details` 指明字段（D44）。（S0）
- 列表游标是签名值，载荷包含 `schema_version`、`scope=admin-task-list`、末行的 `(created_at, id)` 与过滤条件摘要（Q30）。游标被篡改或过滤条件已变时，返回 `422 INVALID_INPUT`，`details` 为 `cursor_invalid`，属于客户端错误（R8）；`cursor_invalid` 登记于 M01 全局错误登记表（接口约定，见补充说明）。（S0）
- 列表的 SQL 次数固定，不逐行查询任务或关联数据（SPEC §7.2；US-27）。（S0）
- 列表是单条语句，按默认隔离级别读取。翻页一致性依赖 keyset 排序，不跨页保证快照一致（D44；SPEC §7 中“多查询一致快照”不适用于单条语句，此为本条推导）。（S0）

### 5. 签名游标

- 游标使用 HMAC-SHA256 签名，子密钥由 M01 通过 HKDF 派生，info 为 cursor 子密钥（Q5）。（S0）
- 作用域分离：快照与事件流的游标 `scope=admin`，列表游标 `scope=admin-task-list`。两类游标互不接受，且事件流游标不能跨 `task_id` 使用（SPEC §18.1）。（S0 列表；S1 事件流）
- 签名不匹配、`schema_version` 不识别、作用域不符或字段被篡改，均拒绝（列表返回 `422`；事件流见第 6 条）。（S0 列表）
- 游标载荷不含 Prompt、原文、session 或凭据（SPEC §18.1）。游标不是权限凭据，接口仍需管理员会话。（S0）
- 根密钥失配时 M01 启动即失败，因此不会误接受其他实例签发的游标（SPEC §19，M01 §6）。（S0）

### 6. 事件流（SSE）

- 使用 `sse-starlette` 的 `EventSourceResponse`，15 秒发送一次 ping（Q32、SPEC §18.1）。（S1）
- 每轮检查管理员会话未过期、未撤销（Q32；SPEC §18.2）。（S1）
- 单连接最多 64 个待发送事件（Q32）；单事件不超过 32 KiB，写超时 5 秒（SPEC §18.2）。（S1 设上限；S4 验证慢客户端）
- 每批读取 `seq > 游标 seq`，每批最多 100 条，默认每秒一批，每批使用短 Session，不保持长事务（SPEC §18.1）。（S1）
- 事件帧使用 `id` 携带签名游标、`event: task.changed`、`data` 为 `CriticalEvent`（SPEC §18.1）。断线重连优先使用 `Last-Event-ID`（SPEC §18.1）。（S1）
- 游标超出保留窗时，握手阶段直接返回 `409 CURSOR_RESET_REQUIRED`，表示需要重新取快照（R8）。其余情况（`seq` 超前、签名或 epoch 无效、序号不连续）在建连后发送 `stream.reset` 并关闭；握手阶段能识别时同样可直接返回 `409 CURSOR_RESET_REQUIRED`（SPEC §18.1）。（S1 最小；S4 完整）
- `CriticalEvent` 随 S1 SSE 进入 OpenAPI 快照，S0 的快照不含事件流 Schema（R13）。（S1）
- `CriticalEvent.type` 由 M03 定义词表，`CriticalEvent` Schema 由 M04 定义。S0 词表为 `accepted`、`claimed`、`stage_completed`、`cancel_requested`、`requeued`、`retry_wait`、`succeeded`、`failed`、`canceled`；`projection` 包含 `status`、`stage`、`error_code`（D34）。（S1 起对外；M03 在 S0 已写入 `task_events`）
- heartbeat 注释帧不更新游标，也不占用关键事件序号（SPEC §18.1）。（S1）
- 事件流在 S1 只实现正常订阅与终态关闭；断线回退、重同步与慢客户端矩阵在 S4 补全（Q32、map §7）。S1 不得声称 AT-08 已通过，AT-08 整项在 S4 验收（R13）。（S1、S4）
- 事件流不增加写路径，不调用模型，重连不创建任务（US-35）。（S1）
- 网关关闭 SSE 缓冲，`proxy_read_timeout` 设为 1 小时；SSE 参数（15 秒 ping、每批 100、64 事件上限、32 KiB、5 秒写超时）属于 API 进程的 `settings.toml`，不进 `policy_json`（D48；SPEC §18.2、X1）。（S1）

### 7. 状态合并与终态

- 客户端保存 `(instance_epoch, state_revision)`。同一 epoch 下，低于当前 revision 的快照丢弃；revision 相同且内容相同的重复快照忽略；epoch 改变时清空旧状态并显示恢复标识（SPEC §18.2；Q29）。（S0）
- 快照合并与列表合并使用同一规则；列表每一行单独按 `(instance_epoch, state_revision)` 合并，不整页替换（D44；Q29）。（S0）
- S1 起事件流的 `seq` 规则并入同一合并函数：`seq <= last_seq` 忽略，`seq > last_seq + 1` 不猜测中间状态，改为重新获取快照（SPEC §18.2）。（S1）
- 终态只采信服务端持久状态；客户端不因本地推断把任务置为终态（SPEC §18.2）。（S0）
- 合并是纯函数，使用表驱动 Vitest 测试（Q29）。（S0）
- 新任务使用新 ID，页面不复用旧任务的界面状态（SPEC §18.2）。（S0）

### 8. 轮询

- 详情页在任务非终态时每 2 秒请求一次快照，观察到终态后停止（Q29）。（S0）
- 列表页每 5 秒请求一次第一页（Q29）。（S0）
- S1 起事件流正常时停止轮询，事件流断开时轮询作为回退（Q29；SPEC §18.1）。（S1）
- 页面隐藏时暂停轮询（D47）。（S0）
- 轮询失败后指数退避，最长间隔 30 秒，并提示“连接中断”（D47）。（S0）
- 最后一次成功同步距今超过 10 秒时，页面显示同步时间（D47）。（S0）
- 轮询失败时保留最后一次成功快照，显示过期标记，不清空界面，也不把失败解释为业务取消或失败（US-12；SPEC §18.1）。（S0）

### 9. 前端底座（供 M02、M12 共用，Q28）

- 工程与依赖：Vite、React、TypeScript strict、React Router、TanStack Query 管理服务端状态，使用 pnpm 与 lockfile（Q28；SPEC §2）。（S0）
- 样式：CSS Modules 加少量设计 token，不引入组件库（Q28）。（S0）
- 测试：Vitest 做单元测试，Playwright 通过网关做端到端测试；typecheck 与 build 进入 CI（Q28；SPEC §21.3）。（S0）
- 入口：管理端与分享端同一工程的两个入口，分享入口 S7 起才加入（Q28；[SPEC §2](../../docs/prototype/SPEC_V1.md#spec-02)）。（S0 管理端；S7 分享端）
- 类型生成：后端从 CLI 导出管理端 OpenAPI 快照并提交；前端用 `openapi-typescript` 生成类型并提交；CI 重新生成并比对差异。生成产物不手工修改（Q17；SPEC §5）。（S0）
- 运行时只用 `fetch` 封装，不引入额外请求运行时（Q17）。（S0）
- 所有 HTTP 调用经同一个 `fetch` 封装。读请求依赖同源会话 cookie；写请求附加 `X-CSRF-Token`（Q39；SPEC §17.1）。（S0）
- CSRF token 只存在内存中，不写入浏览器持久存储（Q39；SPEC §17.1）。（S0）
- 启动时调用会话查询：`401` 时跳转登录页并记住原路径，登录后返回原路径（Q39）。（S0）
- `403 CSRF_REJECTED` 时重新获取会话并提示刷新，不自动重放写请求（Q39）。（S0）
- 登录页只有密码输入框（Q39）。（S0，页面归属 M02）
- 错误展示：显示 `message`、可复制的 `request_id` 与 `action`。`action` 取值固定为 `fix_input`、`resolve_same_key`、`retry_later`、`login`、`refresh`、`retry_later_or_report`、`none`，前端按取值映射固定文案，不解析 `message`（D11）。（S0）
- `retry_after_seconds` 只在 `429` 与 `503` 出现，页面据此显示等待时间；其他状态不显示倒计时（D11）。（S0）
- `details` 每项为 `{field?, code, message}`；`422` 校验错误按字段映射到表单对应位置，无字段的项在表单顶部显示（D11）。（S0）
- `DEPENDENCY_UNAVAILABLE` 与 `MAINTENANCE` 显示原因；`QUEUE_FULL` 与 `ADMISSION_UNCONFIRMED` 使用不同文案与动作，前者可在容量释放后重新申请，后者只允许用原键找回（SPEC §4.1；REQ-11；US-21）。（S0）
- 路由（D46）：`/manage/login`（M02 登录页）、`/manage/tasks`（任务列表）、`/manage/tasks/:id`（任务详情）、`/manage/videos/new`（提交页，M12）。（S0）
- 共享请求层（本模块前端底座）负责生成 `Idempotency-Key` 并存入 sessionStorage，M12 的提交页调用该层；得到明确 `202` 或 `4xx` 后清除（D46、D56）。（S0）
- 时间按浏览器本地时区显示，API 仍为 UTC RFC3339（D47；SPEC §4）。（S0）

### 10. 任务视图

- 列表视图展示状态、类型、阶段、受理时间、截止时间，支持过滤与下一页，并覆盖加载、空列表、失败、过期状态（US-05、US-06；SPEC §21.3）。（S0）
- 详情视图分开展示 `status`、`stage`、`attempt_no`、排队、运行、等待安全重试、取消已请求、结果、错误；`error.code` 为 `PIPELINE_NOT_AVAILABLE`、`DEADLINE_EXCEEDED` 或 `DISPATCH_EXHAUSTED` 时按错误码展示说明（US-08；SPEC §10；R7；E3）。`unknown_call_count` 为 0 时不显示，大于 0 时突出展示（D49）。（S0）
- 取消按钮位于 M04 详情页（D46），只在 `allowed_actions` 包含 `cancel` 时显示。点击后调用 M03 的取消接口，返回的 `TaskSnapshot` 经第 7 条的合并规则写入（SPEC §4；Q31）。（S0）
- S0 骨架提示“S0 骨架：不会生成文章”，以及按 kind 的说明面板，由 M12 提供并嵌入详情页（Q19、Q45、D46）。（S0）
- 任务 ID 与 request ID 可复制（Q8、Q11）。（S0）

### 11. 读写边界

- M04 不写任何表，只读取 `tasks` 与 `task_events`（map §3 M04）。（S0）
- 状态迁移、事件写入、阶段写入、取消请求由 M03 负责；M04 不重算 `state_revision` 与 `event_seq`（map §3 M03）。（S0）
- `draft_summary` 与草稿接口由 M11 与 M12 负责，S0 不接入（map §3 M11）。（S0 不接入；S3 起接入）

## 测试决定

测试接缝编号沿用 [批次 A 约定](../frameread-v1/spec-brief-batch-a.md)：接缝 1 为 HTTP，接缝 2 为进程，接缝 4 为纯函数，接缝 5 为浏览器。

S0 必测（只声明 S0 覆盖的 AT 子场景，AT-08 整项留到 S4）：

- T-01（接缝 1）快照返回 SPEC §5 全部字段；S0 中 `draft_summary` 与 `result` 为 `null`，`unknown_call_count` 为 `0`，`allowed_actions` 只可能包含 `cancel`（Q31）。
- T-02（接缝 1 与接缝 2，AT-05 找回子场景）：受理后尚未投递（Outbox 未投递或 Worker 未启动）时，列表与快照返回同一 `task_id` 与排队状态；随后恢复投递，同一 ID 继续推进，`state_revision` 单调不降。
- T-03（接缝 1，AT-02 找回子场景）：同键重发不创建新任务，快照与原受理响应的 `task_id` 一致；同键重发的断言以 M03 为主，M04 只断言读取结果一致。
- T-04（接缝 1，AT-19 子场景）：非法任务 ID、未知查询参数返回 `422`；未知 ID 返回 `404 NOT_FOUND`；无会话返回 `401`；错误体包含机器类别、说明、request ID 与动作，不含 SQL、路径或异常栈（Q8、Q11）。
- T-05（接缝 1）列表默认 20 条，超过 100 的 `limit` 被拒绝；在推进状态与插入新任务的同时逐页翻完，已存在的行不重复、不漏；`kind` 与 `status` 过滤正确（Q30）。
- T-06（接缝 1）篡改游标、过滤条件变化后使用旧游标、列表游标作用域不符，均返回 `422 INVALID_INPUT`，`details` 为 `cursor_invalid`（Q30；R8）。
- T-07（接缝 1，AT-21 子场景）：每个读取接口调用前后，`tasks`、`task_events`、`task_outbox` 的行数与内容不变，且没有新的 Provider 调用记录（SPEC §4；REQ-13）。
- T-08（接缝 1 与接缝 2）：独立 Worker 推进任务期间并发读取快照，每次返回的 `state_revision`、`event_seq`、`instance_epoch` 相互配套，`state_revision` 不下降（AT-08 的 S0 子集；完整 AT-08 留 S4）。
- T-09（接缝 4）合并纯函数表驱动测试：高 revision 接受；低 revision 丢弃；相同 revision 重复忽略；epoch 改变清空并标记恢复；终态不被较旧快照回退；乱序到达时以 revision 最大者为准（Q29；SPEC §18.2）。
- T-10（接缝 4，Vitest 与 fake timers）轮询调度：详情 2 秒、列表 5 秒，终态后停止详情轮询；页面隐藏时暂停；失败后退避、上限 30 秒（Q29；D47）。
- T-11（接缝 5，Playwright 经网关）：提交后进入详情、刷新恢复、列表翻页与过滤、运行中取消（进入 `cancel_requested` 后收敛）、排队中取消；轮询期间停止后端，页面保留快照并标记过期，恢复后更新；无会话跳转登录并回到原页面（US-03、US-12、US-18）。每个关键状态截图、查看浏览器控制台与网络请求（AGENTS 应用验证要求）。
- T-12（接缝 5）加载、空列表、依赖不可用（503）与过期状态的页面截图，并核对文案区分 `QUEUE_FULL` 与 `ADMISSION_UNCONFIRMED`（US-21）。
- T-13（CI 契约检查）重新导出 OpenAPI 与生成类型后，与提交版本无差异（Q17；US-40）。

S1 起新增的测试（本 SPEC 只列入口，不在 S0 运行）：

- 事件流正常订阅、终态关闭、断线后轮询回退（S1）。
- 游标超保留窗、序号不连续、签名错误、跨任务使用的 `stream.reset` 与 `409 CURSOR_RESET_REQUIRED`（S4 完整，S1 至少覆盖正常路径）。
- 慢客户端、连接上限、会话过期后的连接结束（S4）。

测试约束：不为测试在生产代码中加入开关；失败不通过 `skip` 或放宽断言处理（brief 与 AGENTS）。

## 不在范围内

- 状态迁移、关键事件写入、取消请求写入、`GET /operations/{scope}/{key}` 找回接口（M03）。
- 提交表单、`Idempotency-Key` 的生成与保存、匹配与重试页面（M12）。草稿内容与 `GET /tasks/{id}/draft`（M11/M12，S3 起）。
- `allowed_actions` 中 `retry`、`reinterpret` 等动作（S3 起）。
- S4 完整 SSE 矩阵：慢客户端、重连缺口、AT-08 整项验收（S4）。
- 分享端入口、分享页面、公开 API（M15，S7）。
- 事件保留清理（S8；S0 只写入）与运行概览 `/overview`（M16，S11）。
- 备份恢复后的 epoch 更新与会话清理（M17，S10）。
- 组件库、主题切换、国际化与浏览器持久化的任务缓存（Q28 与批次约定未决定，不做）。

## 补充说明

### 与其他模块的接口约定

- M03：M04 只读 `tasks` 与 `task_events`。`state_revision`、`event_seq`、`attempt_no`、`result`、`error` 的写入规则由 M03 定义，M04 原样输出（map §5、§3）。
- M01：cursor 子密钥由 M01 派生（Q5）；统一错误体、request ID、UoW 与 REPEATABLE READ 事务由 M01 提供（Q8、Q11、Q3）；读取路径的日志仅使用 allowlist 字段（SPEC §20）。
- M02：`require_admin`、会话 cookie、CSRF token 的管理与 `401`/`403` 语义由 M02 定义（Q34–Q39）。M04 的任务接口与前端 `fetch` 封装按这些语义消费。
- M08（S1）：`unknown_call_count` 在 S1 起由 `provider_calls` 聚合，S0 返回 0（Q31）。
- M12：提交页、`Idempotency-Key` 的生成与 sessionStorage 保存（Q20）、骨架提示与取消按钮所在页面（Q45）由 M12 定义，M04 提供快照与合并规则。
- X1：网关的 SSE 缓冲与超时设置（S1）。

### 裁决回写

本轮依据 [spec-resolutions-batch-a.md](../frameread-v1/spec-resolutions-batch-a.md) 回写：第一轮待确认与文档冲突中与 M04 相关的条目已成为正式决定（D11、D34、D44～D49、R7、R8、R9、R13）；第二轮 E1、E2、E3、E14 与取消按钮归属（D46）已成为正式决定（见实现决定 2、4、9、10）。SPEC_V1 已登记 `TaskListItem`（§5）、`requeued`（§18）与任务错误码（§4.1），原“与其他模块可能不一致之处”已解决，不再保留。

### 待确认

1. R9 的“查询失败返回错误”需要 M08 提供失败类型，M04 再按 D11 归类为 `503` 或 `500`。归类待 M08 确认。

### 接口约定

- M01：`cursor_invalid` 作为 `422 INVALID_INPUT` 的 details code，登记于 M01 全局错误登记表（D11；本 SPEC 第 4 条使用）。
- M03：`PIPELINE_NOT_AVAILABLE`、`DEADLINE_EXCEEDED`、`DISPATCH_EXHAUSTED` 由 M03 产生并写入 `TaskSnapshot.error.code`；M04 只读取，不改写（E2、E3）。
- M03：快照中的 `deadline_at` 为唯一期限来源，客户端以此为准（E1）。
- M02、M01：S0 OpenAPI 导出依赖 M01 的导出 CLI（D16），登录路由依赖 M02（D46），需在 S0 Ticket 中对齐。
