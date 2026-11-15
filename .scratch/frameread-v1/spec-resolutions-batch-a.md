# 批次 A 模块 SPEC 待确认事项裁决

日期：2026-11-15。汇总五份模块 SPEC“待确认”与“文档冲突”，去重后由主 Agent 提出裁决，经用户确认后回写各模块 SPEC 与 SPEC_V1，模块 SPEC 中对应条目改为正式决定。来源列：M01#n 指该模块 SPEC 待确认第 n 条，C 开头指文档冲突。U1～U3 为需用户取舍的事项，其余为默认裁决。

## 需用户取舍

| ID | 来源 | 推荐 |
| --- | --- | --- |
| U1 | M01#13、M03#2、M12#8 | 提交结果未确认的故障制造：`tests/` 中的 PG 线协议 TCP 代理夹具。转发 `COMMIT` 后、回传结果前切断连接，得到真实的 commit 未知；在转发 `COMMIT` 前切断得到 `rolled_back`。API 连接经此代理，生产代码无开关 |
| U2 | M03#12、M01#29、M02 C3/C5 | 逻辑删除例外：所有表（含 `instance_state`、槽、Outbox、心跳）一律带四个通用列；允许物理删除的只有 `admin_sessions`（过期与恢复清空）和 `task_events`（保留期清理），两者都没有业务历史价值。写入 SPEC §6 共同规则 |
| U3 | M01 C-1 | 更正 Q18：每个 Worker child 的连接池为 2（主任务与心跳各一，与 SPEC §7 一致），公式改为 Worker 并发 ×2，原来的 ×3 多算了 |

## 文档冲突裁决（回写 SPEC_V1）

| ID | 来源 | 裁决 |
| --- | --- | --- |
| R1 | M01 C-3 | `root_key_check` 只由挂载根密钥的进程比对（api-admin、worker、control、migrate、CLI）；api-public 不挂密钥、不比对。改 SPEC §6.1 措辞 |
| R2 | M01 C-4、M02 C1 | `ADMIN_ORIGINS`（列表）与 `SHARE_BASE_URL` 是进程启动配置，不进 `policy_json`；只有资源策略进 `policy_json`。修正 SPEC §19 本轮措辞，§17.1 同步为列表 |
| R3 | M01 C-5 | 进程内部 `/health/live`、`/health/ready` 不经 gateway；管理端 `GET /health` 为需管理员会话的只读汇总，与 `/overview` 一起在 S11 交付 |
| R4 | M01 C-2 | Repository“构造语句、由执行器运行”与 SPEC §2“不自行 commit”兼容，SPEC 不改 |
| R5 | M03 C1、M03#14 | Q24 的单进程指一个 control 进程内用 tick 调度；S0 只启动 1 个 control 实例，多实例的正确性由 SKIP LOCKED 保证，与 SPEC §19 不冲突 |
| R6 | M12#1、M03 C3 | `Idempotency-Key` 严格校验 UUIDv4（以 SPEC §3 为准） |
| R7 | M03 C4、M12#9、M04 C1 | 错误码统一登记：SPEC §4.1 的 409 行补 `CURSOR_RESET_REQUIRED`；新增“任务错误码”小节，登记 `PIPELINE_NOT_AVAILABLE`（S0 专用，S1 删除）和 `DEADLINE_EXCEEDED`，它们只出现在 `TaskSnapshot.error.code`，不作为 HTTP 状态 |
| R8 | M04 C2 | 两种游标失效有意区分：列表游标被篡改或过滤条件已变，返回 `422 INVALID_INPUT`（`details: cursor_invalid`），属于客户端错误；SSE 游标超出保留窗返回 `409 CURSOR_RESET_REQUIRED`，表示需要重新取快照 |
| R9 | M04 C3 | S0 的 `unknown_call_count=0` 是事实计数（尚无外部调用）；S1 改为查询 `provider_calls`，查询失败时返回错误，不回落为 0 |
| R10 | M01 C-6 | S0 的 AT-22 子集：Compose 按文档启动，经页面提交、查询、取消；CI 在真实 PG/Redis 与独立 Worker 上跑 S0 核心链。重启与完整部署在 S8 验收 |
| R11 | M02 C6 | S0 测试覆盖 AT-18 的管理侧子集（无会话 `401`、无 CSRF `403`、Origin 伪造），作为部分证据，AT-18 在 S7 整项验收 |
| R12 | M02 C2、C4 | SPEC §8 键表补 `fr:{epoch}:login:global`；SPEC §19 的 control 职责补“过期会话清理” |
| R13 | M04 C4、C5 | S1 只交付最小 SSE，不得声称 AT-08 已通过（整项在 S4）；`CriticalEvent` 随 SSE 在 S1 进入 OpenAPI |
| R14 | M12 冲突 3～6 | 按切片差异处理，不改文档：S0 不调用 M05/M09/M10/M11；`/tasks/{id}/retries` 只用于 video；`parse_video_url` 放在 M09 的 `media` 目录，S0 先实现 |

## 默认裁决：M01

| ID | 来源 | 裁决 |
| --- | --- | --- |
| D01 | M01#1、#2 | 各进程只加载自己所需的配置，由 Settings 子集定义，矩阵写进模块 SPEC。`FRAMEREAD_SETTINGS` 指定 toml 路径，生产默认 `settings.toml`，开发环境显式指向 `settings.dev.toml` |
| D02 | M01#3、#4、#38 | `secrets init` 生成：根密钥（32 字节，64 位十六进制，只去掉末尾换行）、PG 各 role 密码、Redis 密码，以及 DSN 和 Redis URL 文件。`installation_id` 由 migrate 在空库初始化时生成。initdb 脚本以只读方式挂载，从 secret 文件读取 role 密码 |
| D03 | M01#5 | 四个子密钥都是 32 字节 |
| D04 | M01#8、#9 | advisory lock 的 key 用固定常量；migrate 等锁最多 60s，超时失败。其他服务要求数据库 head 与代码期望的 head 完全相等，不接受祖先 head，否则拒绝写入并报告 not ready，不等待迁移完成 |
| D05 | M01#10 | S0 的部署规模（各进程实例数、Worker 并发）在 `settings.toml` 中声明；“保留 5”指留给运维的连接数；用 `SHOW max_connections` 读取上限 |
| D06 | M01#11、#12 | 总共最多执行 3 次（含首次）；退避取 50ms×2ⁿ，full jitter，上限 500ms。`commit()` 调用期间出现连接类异常记为 `unknown`，COMMIT 之前出现的异常记为 `rolled_back` |
| D07 | M01#14、#15、#16 | 门禁接口为 `gate.require(op)`，`op` 是操作类别枚举，每种状态允许哪些类别用一张表定义（照 SPEC §7.1）。frozen 状态下除维护 CLI 外一律拒绝，T7 也不例外。`maintenance set` 任意时刻可执行；仅当 `restore_state=normal` 时才能设为 normal。`policy set` 允许在任意 maintenance 状态下执行 |
| D08 | M01#17 | S0 的 `policy_json` 键：每个池的 E/Q（video 默认 E=2、Q=4）、video 总期限 2h、lease 60s、心跳 10s、dispatcher 批量 50、投递重试预算 10、generation 上限 5、事件保留 7 天；其余采用 SPEC §8.2、§9.3 的值。用 Pydantic 校验，warning 比对全部键 |
| D09 | M01#18、#19 | 维护 CLI 使用应用 DML role；退出码 0 成功、1 业务拒绝、2 用法错误，输出给人读，错误信息带 `request_id` |
| D10 | M01#20 | `FencedTask` 字段：`task_id`、`instance_epoch`、`attempt_no`、`fence`、`lease_token` |
| D11 | M01#21、#22 | 错误码放在一张全局登记表中。`action` 的取值固定为：`fix_input`、`resolve_same_key`、`retry_later`、`login`、`refresh`、`retry_later_or_report`、`none`。`retry_after_seconds` 只在 429 和 503 时给出。`details` 每项为 `{field?, code, message}`，422 校验错误逐字段映射。`request_id` 用 UUIDv4 |
| D12 | M01#23、#24 | allowlist 越界在所有环境都抛错（照 Q11）；Docker 日志 max-size 10m、max-file 5；脱敏后的栈信息只进内部日志流，不单独落盘 |
| D13 | M01#25～#27 | ready/degraded 返回 200，unavailable/unknown 返回 503，响应结构为 `{status, checks:[{name,status,observed_at,detail?}]}`。Worker 和 control 没有 HTTP 端口，用 tmpfs 中心跳文件的修改时间做 live 检查，由 `frameread health live` CLI 判定。探针超时 2s、结果缓存 5s，severity 取 `critical` 或 `degraded` |
| D14 | M01#30～#32 | S0 的不可变保护触发器作用于 `task_events` 和已完成的 `stage_results`；锁顺序作为代码约定，由并发测试覆盖，不加运行时断言；UoW 提供 `db_now()`，取 `clock_timestamp()` |
| D15 | M01#33～#35、#37 | 资源限制的具体数值在 Ticket 中给出，并通过 Compose 实测；基础镜像用 `python:3.12-slim` 系列，S0 的 Worker 镜像不装 FFmpeg 和 yt-dlp（S1 再加）；CI 用 GitHub Actions；部署文档放在 `deploy/README.md` |
| D16 | M01#36 | 关闭 docs 和 openapi 路由由 M02 在装配 admin app 时完成，OpenAPI 导出 CLI 归 M01 |

## 默认裁决：M02

| ID | 来源 | 裁决 |
| --- | --- | --- |
| D17 | M02#1、#2、#16 | `credential_generation` 取十六进制小写；`set-password` 写临时文件后原子替换，已存在时必须加 `--force`；session token 的 hash 用 SHA-256 |
| D18 | M02#3～#6、#8、#9 | 限流用固定窗口，由 Lua 原子完成检查加递增，首次失败时设置 TTL；只有密码错误计入失败次数；预检在密码校验之前，超限时即使密码正确也返回 `429`。`source_hash` 用 session-csrf 子密钥，并加用途前缀做域分隔 |
| D19 | M02#7 | gateway 用 `$remote_addr` 覆盖 `X-Forwarded-For`，不在原值后追加。默认只在 loopback 发布时，来源地址可能退化成网桥地址，这时按来源限流等同于全局限流；这一点写进文档并在 Compose 实测 |
| D20 | M02#10 | 登录和退出不经过业务写门禁；frozen 状态下返回 `503 MAINTENANCE`，其余状态都允许 |
| D21 | M02#11～#13 | 检查顺序为 Host → Origin（仅写请求）→ 会话 → CSRF；写请求缺少 Origin 一律拒绝；Host 不匹配返回 `403 ORIGIN_REJECTED` |
| D22 | M02#14 | 恢复时物理清空 `admin_sessions`（见 U2） |
| D23 | M02#15 | 登录请求体为 `{password}`，响应为 `{csrf_token, expires_at}` |
| D24 | M02#17 | Redis 不可用时登录返回 `503 DEPENDENCY_UNAVAILABLE`，健康状态由 M01 的 Redis 探针覆盖 |
| D25 | M02#18 | 收到 `403 ORIGIN_REJECTED` 时提示“来源校验失败，请从管理入口地址访问”，不重试 |
| D26 | M02#20 | 每个 API 进程最多同时进行 2 个 Argon2 校验，超出部分排队，排队时间计入请求超时 |

## 默认裁决：M03

| ID | 来源 | 裁决 |
| --- | --- | --- |
| D27 | M03#1 | `GET /operations/{scope}/{key}` 找到原操作时返回 `200`，body 为 `TaskAccepted`（`replayed=true`） |
| D28 | M03#3 | S0 不覆盖 Redis 停止与恢复（PRD S0 未列），留到 S4 |
| D29 | M03#4、#5 | 排队中的任务超期 failed 并带 `DEADLINE_EXCEEDED`；运行中的任务超期由 Worker 在心跳中发现后停止，Worker 失联时由 reconciler 收敛 |
| D30 | M03#6、#7、#20 | 默认值见 D08；骨架阶段的上限只有总期限；`visibility_timeout` 取最大总期限加 10 分钟 |
| D31 | M03#8 | S0 中 lease 失联一律视为可恢复（S0 没有外部调用）：没有超期就重新排队并保留执行槽，已超期则 `DEADLINE_EXCEEDED` |
| D32 | M03#9 | 骨架阶段的 `input_hash` 取 `tasks.input_hash` |
| D33 | M03#10 | `tasks.version` 随每次 `state_revision` 变化递增；心跳只更新 `lease_until`，不递增 `version` 和 `state_revision` |
| D34 | M03#11、M04#16 | 事件类型由 M03 定义，Schema 由 M04 定义。S0 词表：`accepted`、`claimed`、`stage_completed`、`cancel_requested`、`requeued`、`retry_wait`、`succeeded`、`failed`、`canceled`；`projection` 包含 `status`、`stage`、`error_code` |
| D35 | M03#13 | migrate 在空库初始化写入 `policy_json` 后，调用 M03 的槽原语预建槽行 |
| D36 | M03#15 | draining 状态下 dispatcher 暂停投递，等待位不提升；已在运行的任务按 SPEC §7.1 的例外继续收敛 |
| D37 | M03#16 | 期限类测试由夹具通过 `frameread policy set` 设置短期限，不依赖测试开关 |
| D38 | M03#17 | 测试隔离：每个测试会话由迁移后的模板库建一个独立库，每个测试结束后 TRUNCATE 业务表，并把 `instance_state` 重置为 normal |
| D39 | M03#18 | lease 失联接管（外部 kill Worker 进程）纳入 S0 必测，对应 SPEC 测试编号 TD-11；AT-06 整项仍在 S4 验收 |
| D40 | M03#19 | 执行槽 E 与 Worker 并发分开配置；E 大于总并发时，启动只记 warning |
| D41 | M03#21 | Redis 探针由 M01 注册，Worker 心跳探针由 M03 注册 |
| D42 | M03#22、#23 | `AdmissionRequest` 包含：`kind`、`pool`、`intent`、`scope`、`key`、`request_digest`、`effective_input`、`input_hash`、`deadline`、`retry_of_task_id?`、`budget`。`replayed` 仅在找回已有任务时为 true。S0 的 `budget_json` 为 `{"version":1,"limits":{}}` |
| D43 | M03#24 | Worker 失联后，`cancel_requested` 在 lease 到期后的下一次 reconciler 扫描中转为 canceled |

## 默认裁决：M04

| ID | 来源 | 裁决 |
| --- | --- | --- |
| D44 | M04#1、#4～#7 | 列表行使用摘要 DTO `TaskListItem`：`id`、`kind`、`intent`、`status`、`stage`、`state_revision`、`instance_epoch`、`created_at`、`deadline_at`、`cancel_requested_at`、`error_code`。按新到旧排序；过滤值为小写枚举，非法值返回 `422`；不保证跨页快照一致；每行按 (epoch, revision) 单独合并 |
| D45 | M04#2 | `cancel` 出现在 queued、running、retry_wait 状态；cancel_requested 状态不出现，页面显示“取消中” |
| D46 | M04#8～#10 | 路由：`/manage/login`、`/manage/tasks`、`/manage/tasks/:id`、`/manage/videos/new`。详情页归 M04，按 kind 的说明面板由 M12 提供，骨架提示也在其中。共享请求层（M04 的前端底座）负责生成幂等键并存入 sessionStorage，M12 调用 |
| D47 | M04#11～#13 | 页面隐藏时暂停轮询；失败后指数退避，最长 30s，并提示“连接中断”。最后一次成功同步超过 10s 时显示同步时间。时间按浏览器本地时区显示 |
| D48 | M04#14、#15 | SSE 参数属于 API 进程配置，放在 `settings.toml`，不进 `policy_json`；gateway 的 SSE location 关闭缓冲，`proxy_read_timeout` 设为 1h |
| D49 | M04#17、#18 | S0 的 `progress` 为 `{stage, observed_at}`；`unknown_call_count` 为 0 时不显示 |

## 默认裁决：M12

| ID | 来源 | 裁决 |
| --- | --- | --- |
| D50 | M12#2 | 非 HTTPS、带 userinfo、非 443 端口、格式非法返回 `INVALID_INPUT`；host 或路径不在支持范围内返回 `UNSUPPORTED_VIDEO` |
| D51 | M12#3 | S0 支持的 host：`bilibili.com`、`www.bilibili.com`、`m.bilibili.com`、`b23.tv`、`youtube.com`、`www.youtube.com`、`m.youtube.com`、`youtu.be`；YouTube 路径支持 `watch?v=`、`shorts/{id}`、`youtu.be/{id}`。在 M09 Grill 中复核 |
| D52 | M12#4 | `parse_video_url` 放在 M09 的 media 目录（R14） |
| D53 | M12#5、#6 | 配置字段为空时，sentinel 取字符串 `"$default"`；`effective_input_json` 为规范化后的 DTO 加上 `config_resolution: "unresolved"`。S1 起，显式填写的配置与留空默认按 SPEC §3.1 产生不同的 digest，同一个键时返回 `409`，这是预期行为 |
| D54 | M12#7 | 骨架任务的期限由 M12 在受理时按 `policy_json` 中的 video 总期限计算，写入 `AdmissionRequest.deadline` |
| D55 | M12#10 | 提交 `intent=reinterpret` 时返回 `422 INVALID_INPUT`，`details` 为 `intent_not_available` |
| D56 | M12#11、#12 | 页面默认 mode=complete、depth=standard，complete 模式下也可以填写 focus。每份表单草稿对应一个幂等键，得到明确的 `202` 或 `4xx` 后清除 |
| D57 | M12#13 | 日志不新增字段，按 `task_id` 关联；平台 ID 与 URL 不写入日志 |
| D58 | M12#14～#16 | `/videos/matches` 在 S3 注册，S0 不提供；`ASR_REQUIRED` 在 S2 实现；`fingerprints`（阶段指纹）在 S1 建立，`result_match_hash` 在 S3 实现 |
| D59 | M12#17 | 验证"提交时不联网"：api-admin 只接入 `internal: true` 网络，没有出站路由；纯函数单测确认解析过程不发生 I/O |

## 第二轮：回写后发现的跨模块不一致

| ID | 来源 | 推荐裁决 |
| --- | --- | --- |
| E1 | M12、M03 回写报告（D54 与 SPEC §8.2 冲突） | 替换 D54：M12 只传 `total_timeout`（取自 `policy_json` 的 video 总期限），由 M03 在 T1 内计算 `deadline_at = db_now() + total_timeout`。`AdmissionRequest.deadline` 改为 `total_timeout`，客户端以 `TaskAccepted.deadline_at` 为准 |
| E2 | M03、M12（超期错误码） | 两种情况分开：handler 仍在运行、自己发现超期时，用 handler 的错误码（S0 骨架为 `PIPELINE_NOT_AVAILABLE`，维持 Q19）；由运行时发现超期时，包括排队、retry_wait、lease 失联后已超期，一律用 `DEADLINE_EXCEEDED` |
| E3 | M03 | 投递重试预算耗尽时，任务以 `DISPATCH_EXHAUSTED` 失败，登记到 SPEC §4.1 的任务错误码 |
| E4 | M01、M03（D14 与 U2 冲突） | 不可变触发器只拦 UPDATE：`task_events` 允许 DELETE，供保留期清理；`stage_results` 完成后内容禁止 UPDATE，代码中不提供 DELETE 路径 |
| E5 | M01、M02、M03（门禁类别缺口） | `gate.require(op)` 增加三类操作：`dispatch` 指投递与等待位提升，draining 和 frozen 下禁止；`session` 指登录与退出，只在 frozen 下禁止，M02 调用它；`cancel_request` 指用户取消，draining 下允许（只会减少工作），frozen 下禁止。写入 SPEC §7.1 |
| E6 | M03 | Worker 与 control 的 live 检查用 tmpfs 文件，由 CLI 判定（M01）；Worker 集群是否就绪由 M03 注册的 `worker_heartbeats` 探针在 api-admin ready 中报告；Redis 探针归 M01 |
| E7 | M01、M03（D35 依赖方向；KeyRing 依赖数据库） | 槽行预建在进程入口层组合：migrate 和 `policy set` 的入口在同一个 UoW 里先调 M01 写策略，再调 M03 的 `sync_execution_slots`，这属于入口注入，不是 M01 模块依赖 M03，登记到地图 §4.2。进程启动顺序固定为：连库 → 校验 head → 读 `instance_state` → 比对 `root_key_check` → 用 `installation_id` 派生子密钥 |
| E8 | M12（U1 缺"未找到"分支） | TCP 代理提供三种模式：丢弃 `COMMIT` 并断开，结果为 unknown，确认时查不到，返回 `503 ADMISSION_UNCONFIRMED`；转发 `COMMIT` 后、回包前断开，结果为 unknown，确认时能查到，返回 `202 replayed`；在 `COMMIT` 之前断开，结果为 rolled_back，返回 `503 DEPENDENCY_UNAVAILABLE`，不留下任何记录 |
| E9 | M01（迁移失败的测试手段） | 测试把迁移目录复制到临时目录，追加一个会失败的 revision，再对它运行 Alembic；生产代码与配置都不改 |
| E10 | M01 | 驱动异常和 unknown/rolled_back 的具体映射在实现时确定，用 E8 的代理测试覆盖三种模式来证明 |
| E11 | M12 | `provider_revision_id` 留空即 SQL NULL；短链规范形式为 `https://b23.tv/{code}`，host 转小写，去掉 query 和 fragment；`pool` 取值为 `video`、`qa`、`utility`；策略键为 `pools.<pool>.execution_slots` 和 `pools.<pool>.waiting_slots` |
| E12 | M12（`disk_low` 没有登记） | SPEC §8.2 增加一句：超过安全线或采样过期时，T1 返回 `503 DEPENDENCY_UNAVAILABLE`，`details` 中的 code 为 `disk_low` |
| E13 | M02 | 登录限流允许有界超额：在途的失败请求最多等于每个进程的 Argon2 并发上限（2）。预检只读，失败路径做原子递增。每个错误码的 `action` 由 M01 的全局登记表定义。`review_required` 状态下允许登录 |
| E14 | M04、M03 | SPEC §5 登记 `TaskListItem`；SPEC §18 的关键事件中加入"失联重排（`requeued`）" |
| E15 | M02、M01 | `secrets init` 不生成管理员 hash，它由 `admin set-password` 单独负责 |
