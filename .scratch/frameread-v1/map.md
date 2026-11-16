# FrameRead V1 模块地图与实施进度

日期：2026-11-16。状态：批次 A 模块 SPEC 已确认，S0 实施中；完成情况与证据见 §10。

需求依据为 [PRD](../../docs/prototype/PRD.md) 与 [ADR](../../docs/adr/)，技术基线为 [SPEC_V1](../../docs/prototype/SPEC_V1.md)，术语见 [GLOSSARY](../../GLOSSARY.md)，REQ/AT/S 映射见[追踪矩阵](../../docs/prototype/PRD_SPEC_Traceability.md)。本文只定义模块归属、依赖和进度，不新增需求；与上述文档冲突时以上述文档为准，并记入 [§11](#11-待模块-grill-解决的问题)。下文 `SPEC §n` 指 SPEC_V1 第 n 节（锚点 `#spec-NN`）。

## 1. 使用方式

- **模块视角**（谁负责、谁持有状态、谁依赖谁）看 §2～§6；**交付视角**（S0～S12 可运行成果与验收）看 §7 和 PRD §6。两者独立：模块可跨多个切片实现，切片可涉及多个模块。
- `/grill-with-docs` 与 `/to-spec`：按 §8 顺序一次处理一个模块，覆盖该模块在 V1 中的全部行为；模块 SPEC 发布到 `.scratch/<模块目录>/spec.md`。
- `/to-tickets`：按切片触发，前提是 §10.2 中该切片所需模块 SPEC 均为“已确认”；Ticket 发布到 `.scratch/<切片目录>/issues/NN-<slug>.md`，每个 Ticket 注明所引用的模块 SPEC 章节、REQ 与 AT，按纵向切片拆分。
- 每个阶段只在用户显式调用对应命令后进入，阶段结束即停下汇报。

## 2. 划分规则与已批准决策

- 每张表只有一个写入模块，例外见 D2。
- 模块纵向拥有其路由、Service、Repository、迁移与前端页面；进程只是承载（§4.3）。
- 依赖只指向下层或同层左侧；两处反向需求用 Port 倒置，由进程入口注入。

| ID | 决策（2026-11-15 用户确认） |
| --- | --- |
| D1 | 任务运行时拆为 M03（写入侧状态机）与 M04（快照、游标、SSE）。 |
| D2 | 归属例外：a. `FencedTask` 值类型放 M01，M07 只接收调用方传入的 `FencedTask`，不调用 M03；b. M03 定义 `CallRecoveryPort`，M08 实现并注入，供 T2 Claim 与 reconciler 判定失联调用；c. `tasks.reserved_usage_json/known_usage_json` 归 M08 写，其余列归 M03，`resource_slots` 归 M03；d. 恢复终结由 M17 编排，实际改写由各表所有者的 `*_for_restore` 钩子完成；e. M16 只读聚合其他模块的表，M15 的 `acquire_share_asset_lease` 函数写 `asset_leases`（SPEC §17.3），其规则与 M07 租约语义一致；f. 能力检查由 M08 执行，M05 只受理检查任务并保存结果。 |
| D3 | QA 对话占用以 `active_turn_id` 所指 task 是否非终态判定：回答 T6 成功时清空指针；失败/取消/unknown 由 M03 通用 T7 收敛，不锁 conversation；残留指针由下一轮受理在 conversation 锁内校正。用户可见行为不变，已同步 SPEC §15.1。 |
| D4 | 代码沿用 SPEC §2 分层目录，模块是归属关系，映射见 §9。 |
| D5 | Grill 与 `/to-spec` 逐模块进行；`/to-tickets` 按切片批次，在所需模块 SPEC 确认后触发。 |

## 3. 模块清单

### M01 实例门禁与平台底座　`m01-instance-platform`

- **目的**：全部写入共用同一实例身份与写入门禁；事务、配置、密钥、错误、日志、健康的约定只实现一份。
- **负责**：`instance_state` 单例（epoch、maintenance/restore 状态、资源策略、config_revision）与 `instance_write_gate`；启动时 binding 与迁移 head 校验；UoW/Session（fork 边界、连接池预算、全局锁顺序、无副作用短事务有界重试）；Alembic 运行器与 advisory lock；Settings 与 Docker secret 文件读取；KeyRing 子密钥派生；统一错误体与错误码登记；结构化日志 allowlist 与 request ID；live/ready 框架；`FencedTask` 值类型。
- **不负责**：业务表；各依赖的健康判定（各模块注册探针）；备份恢复流程（M17）。
- **数据**：`instance_state`。
- **Interface**：`UnitOfWork`、`gate.lock/require`、`current_epoch`、`ResourcePolicy`、`KeyRing.derive`、`AppError`、`health.register_probe`、`FencedTask`。
- **依赖**：无。
- **SPEC**：§1、§2、§4.1、§6 共享字段与 6.1 `instance_state`、§7、§19、§20。
- **追踪**：REQ-03/10/11/13/14/15 底座部分；AT-19、20、21 基础；S0 主交付，S8 迁移升级与完整健康，S10 备份状态位。

### M02 管理访问与入口隔离　`m02-admin-access`

- **目的**：单一管理员凭据的管理入口，与分享入口在路由、凭据和进程上隔离。
- **负责**：CLI 设置 Argon2id 密码 hash；`/session` 与 `admin_sessions`；CSRF、精确 Origin/Host；登录限流（Redis 计数，不可用时 `503`）；admin/public 两个 ASGI app 装配（public 不加载管理 router，关闭 docs）；gateway 双监听与代理信任；管理端登录页与外壳。
- **不负责**：分享 token 授权（M15）、出站 URL 校验（M06）、渲染安全（M10）。
- **数据**：`admin_sessions`；Redis `login` 键。
- **Interface**：`require_admin` 依赖（写请求含 CSRF/Origin）、`clear_sessions_for_restore(uow)`、密码设置 CLI。
- **依赖**：M01。
- **SPEC**：§1、§4、§8 login 键、§17.1、§19。
- **追踪**：REQ-10；AT-18 管理越权、AT-19 401/403；S0 基础鉴权，S7 双入口负测完整，S10 恢复清会话。

### M03 任务运行时　`m03-task-runtime`

- **目的**：video/qa/export/probe 共用的受理、投递、执行权、阶段检查点与终态裁决；PG 权威，Celery/Redis 只唤醒。
- **负责**：T1 受理核心（scope+key 幂等、digest 比对、执行槽/等待位、task+Outbox+关键事件同事务、提交未确认判定、`GET /operations/{scope}/{key}`）；dispatcher 与 Broker 丢失对账（generation）；T2 Claim、heartbeat 续租与 `FencedTask` 锁原语；T3 `stage_results`（含跨任务 `reused_from_id`）；T7 取消/终止；reconciler 优先次序、deadline、retry_wait、等待位提升；状态机与 `state_revision`/`event_seq`、关键事件写入与保留清理；`resource_slots` 槽原语；`worker_heartbeats`；Celery app 与 KindHandler 注册。
- **不负责**：调用账与 unknown 判定（M08，经 `CallRecoveryPort`）；各 kind 的输入语义与产物；SSE 协议（M04）；文件（M07）；发布内容（M10/M13）。
- **数据**：`tasks`（预算两列除外）、`task_attempts`、`task_outbox`、`task_events`、`stage_results`、`resource_slots`、`worker_heartbeats`；Redis 队列。
- **Interface**：`admit(uow, AdmissionRequest) → TaskAccepted`、`find_operation`、`request_cancel`；Worker 侧 `KindHandler.execute(ctx)`，ctx 提供 `fenced()`、`checkpoint()`、`reuse_completed()`、`cancel_requested()`、`slots`；T6 同 UoW 调用的 `complete_success(uow, fenced, result)` 与 `fail(...)`；`interrupt_all_for_restore(uow)`；定义 Port `CallRecoveryPort`、`KindHandler`。
- **依赖**：M01（Port 由上层注入）。
- **SPEC**：§1、§3、§6.2、§7.1、§8.2、§9、§10、§12.3 T6 参与部分、§18 事件写入。
- **追踪**：REQ-02/03/11/12 任务部分；AT-02、04、05、06、07、12、19、20；S0 主交付，S1 接入真实阶段与发布，S3 跨任务复用，S4 全故障窗口，S5 QA 受理，S6 utility 池，S10 恢复钩子。

### M04 任务状态同步　`m04-task-sync`

- **目的**：刷新、断线、响应丢失后从 PG 快照恢复，关键状态不遗漏、不倒退。
- **负责**：`GET /tasks`（keyset）、`GET /tasks/{id}`（REPEATABLE READ 一致快照与 `allowed_actions`）；签名 cursor；SSE（短 Session 批读、heartbeat、`stream.reset`、`409 CURSOR_RESET_REQUIRED`）；慢客户端有界缓冲、连接数上限、会话过期检查；前端按 (epoch, revision) 单调合并、断线提示与轮询回退。
- **不负责**：状态迁移与事件写入（M03）；草稿组装（M11）。
- **数据**：无写入；读 `tasks`、`task_events`。
- **Interface**：快照、列表、SSE 三个 HTTP 入口；`TaskSnapshot`、`CriticalEvent` Schema。
- **依赖**：M01、M02、M03。
- **SPEC**：§4、§5 `TaskSnapshot`/`CriticalEvent`、§18。
- **追踪**：REQ-03/11/13；AT-08，以及 AT-02、05 按原 ID 找回部分；S0 快照，S1 最小 SSE，S4 重连与慢客户端。

### M05 模型服务配置　`m05-provider-config`

- **目的**：管理图文模型、ASR、检索配置；受理时固定语义 revision；凭据只发往授权目标。
- **负责**：配置与 revision 表（`If-Match`、语义修改新建 revision、每 kind 单默认）；AES-GCM 凭据加密、脱敏回显、同端点轮换不改语义 revision；credential_scope_hash 与 quota_group 归组；trusted-local 端点规则；`resolve_for_admission`；能力检查任务受理与结果保存；设置页。
- **不负责**：发送、调用账、配额、能力检查执行（M08）。
- **数据**：`provider_configs`、`provider_revisions`。
- **Interface**：`resolve_for_admission(uow, kind, config_id?) → FixedRevision`、`lock_config(uow, id)`、`credential_for_send(uow, revision)`（仅 M08 使用）、`record_check_result(...)`。
- **依赖**：M01、M02、M03。
- **SPEC**：§3 凭据 scope、§4、§5 `ProviderConfigWrite/View`、§6.1、§8.1 归组、§13、§17.2 本地端点、§17.3 加密。
- **追踪**：REQ-01/10；AT-01、AT-09 缺 ASR、AT-18 凭据泄露；S1 主交付，S2 ASR，S5 检索。

### M06 网络出口策略　`m06-egress`

- **目的**：所有不受信出站请求只能到达已校验的公网 HTTPS 目标。
- **负责**：`EgressPolicy`（协议/端口/userinfo、全部 A/AAAA 解析、非公网拒绝）；egress-proxy（asyncio CONNECT，media/web 两监听，连接已验证 IP）；重定向逐跳校验；media profile 平台/CDN allowlist。
- **不负责**：管理员配置的模型端点（M05）；下载与正文提取（M09/M13）。
- **数据**：无。
- **Interface**：`validate_public_url(url, profile)`、`proxy_for(profile)`、`safe_redirect_chain`。
- **依赖**：M01。
- **SPEC**：§11.1、§17.2、§19 egress-proxy、§21.2 安全语料。
- **追踪**：REQ-04/10；AT-18 SSRF、AT-09；S1 首次真实下载，S5 web profile，S8 安全语料补全。

### M07 资产存储与生命周期　`m07-assets`

- **目的**：只有完整校验并 ready 的文件可被引用；受保护资产不被清理；各崩溃窗口可识别、可收敛。
- **负责**：卷布局与 storage_key 安全；写入协议（staging 登记 → `.part` → 校验/fsync → 原子安装 → ready）；`asset_refs`（六类 owner，均带 FK）；`asset_leases`；按资产 ID 受保护读取；T8 GC 与孤儿收敛；源媒体 TTL；hash 不符置 unavailable；`GET /assets/{id}/content`。
- **不负责**：执行栅栏判定（调用方在同一 UoW 持有 `FencedTask`）；正式引用的选择（M10/M13）；分享授权（M15）。
- **数据**：`assets`、`asset_refs`、`asset_leases`；对象卷。
- **Interface**：`stage(uow, fenced, kind)`、`install(staged, stream)`（事务外）、`mark_ready(uow, fenced, staged)`、`add_refs(uow, owner, ids)`、`acquire_lease/release`、`open_read`、`gc_once`、`invalidate_leases_for_restore`。
- **依赖**：M01（不调用 M03）。
- **SPEC**：§6.3、§12、§17.3 路径。
- **追踪**：REQ-04/08；AT-06、10、12、16；S1 首次安装/引用/保护，S6 读取租约，S8 GC 与并发清理，S10 文件清单。

### M08 外部调用账与配额　`m08-call-ledger`

- **目的**：每次可能计费的发送先登记、预留、授权；结果未知时不重发、用量不记零；跨进程共享配额不可绕过。
- **负责**：`provider_calls` 五态；T4 发送授权；Redis Lua 预许可与 PG 窗口重建；Provider 处理槽；T5 回执（receipt asset、usage 结算、过期回执拒收）；同 logical_key 禁止二次发送；安全重试分类；任务预算两列；`CallRecoveryPort` 实现；chat/ASR/Brave 适配器；能力检查执行。
- **不负责**：Prompt 构造、内容校验、任务终态写入（返回结果，由 M03 收敛）。
- **数据**：`provider_calls`；`tasks.reserved_usage_json/known_usage_json`（列级归属）；Redis `rate` 键。
- **Interface**：`call(ctx, LogicalCall) → ConfirmedResponse`，异常为 `CallUnknown`、`CallFailed(retry_class)`、`BudgetExhausted`、`QuotaUnavailable`；`has_open_calls(uow, task)`；`judge_lost_calls`；`mark_sending_unknown_for_restore`。
- **依赖**：M01、M03、M05、M07。
- **SPEC**：§6.2 `provider_calls` 与预算、§8、§11.2 ASR 适配、§13、§15.3 Brave。
- **追踪**：REQ-05/12/13；AT-06、07 unknown 分支、13、14、15、23；S1 chat 完整，S2 收费 ASR 与共享配额，S4 故障组合，S5 QA 与检索。

### M09 来源与媒体获取　`m09-source-media`

- **目的**：把单条 B 站/YouTube 链接变成冻结的来源快照（媒体身份、带精度的字幕/转写、真实帧），已被引用的证据不被改写。
- **负责**：URL 规范化（平台/ID/分 P/追踪参数，短链逐跳校验）；`sources`；yt-dlp 取字幕与下载（固定参数、media proxy、字节/时长限制）；ffprobe 完整性；字幕解析与 precision；ASR 切块（每块经 M08）与 offset；acquisition manifest；snapshot/segments 冻结；取帧与 `actual_ms`；子进程守护（进程组、watchdog）；磁盘监控；源媒体清理后的同源恢复；字幕窗口与全文检索。
- **不负责**：文章/问答内容、资产登记协议（M07）、ASR 计费账（M08）、任务状态（M03）。
- **数据**：`sources`、`source_snapshots`、`transcript_segments`（含全文检索索引）。
- **Interface**：`parse_video_url`（纯函数）、`acquire_snapshot`、`extract_frames`、`restore_source_media`（不可确认时返回 `SOURCE_IDENTITY_UNVERIFIABLE`）、`transcript_window`、`search_transcript`、`media_capacity`。
- **依赖**：M01、M03、M06、M07、M08。
- **SPEC**：§3 来源/快照身份、§6.1、§8.2 磁盘、§11、§15.2 全文检索。
- **追踪**：REQ-04/01/12；AT-09、10、14、06；S0 仅 URL 规范化纯函数，S1 字幕视频与取帧，S2 双平台与 ASR，S8 补看。

### M10 正式文章版本　`m10-article-version`

- **目的**：定义正式文章版本契约；只有通过确定性规则的候选在一个事务内成为不可变版本；为管理阅读和分享提供固定投影。
- **负责**：Candidate/Map/Evidence Schema；SPEC §14.1 确定性规则与逐条校验报告；T6 发布；result_match_hash 最近匹配；版本历史；管理 `ArticleView` 与公开 allowlist 投影；前端共享受限渲染器（导图树、时间链接、原帧、区间精度）与阅读页。
- **不负责**：生成（M11）、分享授权（M15）、导出（M14）、缓存（M18）。
- **数据**：`article_versions`。
- **Interface**：`validate_candidate`（纯函数，M11 evidence_check 复用）、`publish(uow, fenced, candidate_ref)`、`find_latest_match`（失败抛错，不返回空）、`get_view`、`public_projection`、`list_versions`、`block_lookup`。
- **依赖**：M01、M03、M07、M08、M09。
- **SPEC**：§3.1 match hash、§5 文章/证据/导图 Schema、§6.3、§12.3、§14.1、§15 阅读、§16.2 公开投影、§17.3 渲染。
- **追踪**：REQ-06/02/03；AT-11 确定性部分、12、03、07、17；S1 主交付，S3 匹配，S5 选段定位，S7 公开投影。

### M11 文章生成编排　`m11-article-generation`

- **目的**：单任务内用有界 LangGraph 把冻结来源变成合格候选；节点持久化与外部发送全部经业务 Service。
- **负责**：七个节点；prompt/schema/workflow 版本；上下文预算（关键证据不静默截断）；真实图片输入 manifest；节点 `run_once` 复用完成阶段与可靠回执；recursion 与修订上限；完整/专题/深度/focus 生成规则与 no_image_reason；草稿组装与 `GET /tasks/{id}/draft`。
- **不负责**：执行权、发布、调用账、取帧。
- **数据**：无表；定义阶段输出内容。
- **Interface**：`generate_candidate(ctx, snapshot, input) → CandidateRef | GenerationFailed(draft)`、`draft_view`。
- **依赖**：M03、M07、M08、M09、M10。
- **SPEC**：§11.4 视觉输入、§14。
- **追踪**：REQ-06/05；AT-11、12、13、14；S1 完整模式，S3 专题/深度/focus，S4 重放恢复。

### M12 视频解读用例　`m12-video-usecase`

- **目的**：负责视频侧四类请求行为的语义，并把获取、转写、生成、发布组装为 video 任务。
- **负责**：`VideoTaskCreate` 规范化与 digest；`/video-tasks`、`/videos/matches`、`/tasks/{id}/retries`（QA 转专用路径）；match hash 计算；受理时解析默认配置；阶段复用指纹组合；video KindHandler 流水线；`ASR_REQUIRED` 与沿用原输入新建任务；提交/匹配/重试页面。
- **不负责**：受理事务（M03）、媒体（M09）、生成（M11）、发布（M10）。
- **数据**：无表。
- **Interface**：管理 HTTP、video KindHandler、`fingerprints` 纯函数。
- **依赖**：M01、M03、M05、M09、M10、M11。
- **SPEC**：§3、§4、§5 `VideoTaskCreate`、§9.1、§11.2 `ASR_REQUIRED`。
- **追踪**：REQ-02/01/03；AT-02、03、09、11；S0 提交契约与受控测试流水线，S1 真实流水线，S2 ASR，S3 四类行为完整。

### M13 私人问答　`m13-private-qa`

- **目的**：基于固定文章版本和来源逐轮追问；回答来源分类可信；外部资料显式开启且可追溯。
- **负责**：conversations/turns/external_reads；轮次受理（锁 conversation 后调用 M03 受理，幂等找回优先）；重问分配新序号；选段/选帧锚点校验；有界 AnswerService；Brave 检索（经 M08）与 WebReader（经 M06）；回答 T6；问答页。
- **不负责**：修改正式文章、补看实现（M09）、调用账（M08）。
- **数据**：`conversations`、`qa_turns`、`external_reads`。
- **Interface**：管理 HTTP（对话、轮次、重问）、qa KindHandler。
- **依赖**：M03、M05、M06、M07、M08、M09、M10。
- **SPEC**：§5 `TurnCreate`/`AnswerCandidate`/证据、§6.3、§15、§17.3 注入。
- **追踪**：REQ-07/02/10；AT-15、18、14、02；S5。

### M14 离线导出　`m14-export`

- **目的**：从固定正式版本确定性生成 Markdown 与图文 ZIP，零生成调用。
- **负责**：`exports`；utility 池 export 任务；图片批量校验与读取租约；纯 renderer 与 manifest；ZIP 路径安全与 CRC；受保护下载与到期重建。
- **数据**：`exports`。
- **Interface**：管理 HTTP（创建/状态/下载）、export KindHandler。
- **依赖**：M03、M07、M10。
- **SPEC**：§5 `ExportManifest`、§16.1、§17.3。
- **追踪**：REQ-08；AT-16、10；S6。

### M15 只读分享　`m15-share`

- **目的**：用独立 capability 只读分享固定版本；撤销或旧备份恢复后，新的页面、内容、图片请求全部拒绝。
- **负责**：`shares`；HMAC 派生 token、只存 hash；T9 创建/撤销/重签；public app 与分享页；public DB role、`public_instance_gate` 视图、`acquire_share_asset_lease` 函数；`no-store`；恢复钩子。
- **数据**：`shares`；public role、视图与函数。
- **Interface**：管理 HTTP、公开 HTTP、`disable_all_for_restore`。
- **依赖**：M01、M02、M07、M10（启用 M18 后经其读取内容）。
- **SPEC**：§4 public 路由、§6.3、§16.2～16.3、§17.3、§22。
- **追踪**：REQ-09/10；AT-17、18、19；S7 主交付，S10 恢复禁用与重签。

### M16 运行概览与排障（P1）　`m16-overview`

- **负责**：`/overview` 聚合；采集时间与 unknown；按 ID 排障跳转；磁盘采样；六类运行手册。
- **不负责**：基础日志与健康（M01 与各模块探针，S0 起交付）。
- **数据**：只读聚合 M03/M07/M08 的表。
- **依赖**：M01。
- **SPEC**：§20。
- **追踪**：REQ-16；AT-24；S8 运行手册，S11 主交付。

### M17 备份与恢复（P1）　`m17-backup-restore`

- **负责**：backup/restore/confirm CLI；密钥封装；恢复终结单事务编排，调用各表所有者的 `*_for_restore` 钩子。
- **数据**：无独立表；`instance_state` 恢复字段经 M01 接口写入。
- **依赖**：M01、M02、M03、M07、M08、M15。
- **SPEC**：§22。
- **追踪**：REQ-15；AT-23；S10。

### M18 版本内容缓存（P1 实验）　`m18-content-cache`

- **负责**：授权之后读缓存；public-cache ACL 与 Lua 预算；故障回源；无/冷/热对照实验与取舍记录。
- **数据**：Redis `article` 键。
- **依赖**：M01、M10。
- **SPEC**：§8、§23。
- **追踪**：REQ-17；AT-25；S12。

### 横切支撑（不单独 Grill）

| ID | 内容 | 随哪个模块对齐 |
| --- | --- | --- |
| X1 交付工程 | Compose、镜像、gateway、lockfile、CI、OpenAPI 导出与前端类型生成、部署文档（SPEC §19、§21.3） | S0 部分随 M01；S8 完整 |
| X2 测试替身与故障注入 | 可控 Provider、可控媒体源、kill/barrier、真实 PG/Redis/独立 Worker 夹具、Playwright（SPEC §21） | 夹具随 M03；可控 Provider 随 M08；可控媒体源随 M09 |
| X3 验收证据 | `docs/validation/` 模板、M 人工核对表、S 安全语料（SPEC §21.3） | 随首个产生对应证据的切片 |

S9（AT-26）是实测优化活动，改动落点由测量决定，不对应模块。

## 4. 依赖与进程

### 4.1 分层

```text
L5 运维      M16 运行概览     M17 备份恢复
L4 用例入口  M04 状态同步  M12 视频解读  M13 私人问答  M14 离线导出  M15 只读分享
L3 内容      M10 正式文章版本   M18 内容缓存   M11 文章生成
L2 能力      M06 出口策略  M07 资产  M05 模型配置  M08 调用账与配额  M09 来源与媒体
L1 执行内核  M02 管理访问   M03 任务运行时
L0 底座      M01 实例门禁与平台底座
倒置：M03 定义 CallRecoveryPort ⇐ M08 实现
      M03 定义 KindHandler ⇐ M12(video) / M13(qa) / M14(export) / M08(probe) 注册
```

### 4.2 直接依赖（全部模块使用 M01 的 UoW、错误与日志约定，管理路由均依赖 M02，下表只列需特别说明的 M01 依赖，不重复 M02）

| 模块 | 依赖 |
| --- | --- |
| M02、M06、M07 | M01 |
| M03 | M01（Port 由上层注入） |
| M04、M05 | M01、M03 |
| M08 | M01、M03、M05、M07 |
| M09 | M01、M03、M06、M07、M08 |
| M10 | M01、M03、M07、M08、M09 |
| M11 | M03、M07、M08、M09、M10 |
| M12 | M01、M03、M05、M09、M10、M11 |
| M13 | M03、M05、M06、M07、M08、M09、M10 |
| M14 | M03、M07、M10 |
| M15 | M01、M07、M10（M18） |
| M16 | M01，只读 M03/M07/M08 表 |
| M17 | M01、M02、M03、M07、M08、M15 |
| M18 | M01、M10 |

无循环依赖。新增依赖需在本表登记，出现环时先在对应模块 Grill 中解决。

进程入口组合（不构成模块依赖）：migrate 与 `frameread policy set` 的入口在同一 UoW 内先调用 M01 写入策略，再调用 M03 `sync_execution_slots` 预建或 retire 执行槽。

### 4.3 进程承载

| 进程 | 承载的模块职责 |
| --- | --- |
| api-admin | M02、M03 受理/取消/找回、M04、M05、M07 受保护读取、M10、M11 草稿、M12、M13、M14、M15 管理端、M16 |
| api-public | M15 公开读取（含 M10 投影、M18） |
| worker | M03 执行框架；video(M12)、qa(M13)、export(M14)、probe(M08) handler；M09、M11、M08 在其中运行 |
| control | M03 dispatcher/reconciler/deadline/等待位提升/事件保留；M08 失联调用判定（经 Port）；M07 GC/孤儿/TTL；M16 磁盘采样 |
| CLI / migrate | M01 迁移与初始化、M02 密码设置、M17 备份恢复 |
| egress-proxy | M06 |

## 5. 事务与关键职责归属

| 事务 | 所有者 | 同一 UoW 内参与 | 裁决内容 |
| --- | --- | --- | --- |
| T1 受理 | M03 | M12/M13/M14/M05 发起；M01 门禁；M05 固定 revision；M13 先锁 conversation | 同键先找回；满额拒绝无残留；提交未确认返回 `ADMISSION_UNCONFIRMED` |
| T2 Claim | M03 | M08（经 Port） | epoch、generation、执行槽、期限、取消；fence 递增 |
| T3 阶段检查点 | M03 | M07 pin；内容来自 M09/M11 | 栅栏校验；I/O 在事务外 |
| T4 发送授权 | M08 | M01 门禁、M05 配置锁与凭据 scope、M03 `FencedTask` 与槽 | 预留预算、PG 窗口计数；授权即视为可能已发送 |
| T5 回执 | M08 | M07 receipt asset | 过期回执拒收；用量未知不记零 |
| T6 发布/回答 | M10 文章 / M13 回答 | M03 `complete_success`、M07 `add_refs`、M08 `has_open_calls` | 唯一发布；与 T7 锁同一 task 行 |
| T7 取消/终止 | M03 | 不锁 conversation（D3） | 终态不可回退 |
| T8 清理 | M07 | — | 行锁下核查 refs/lease，gc_token 续删 |
| T9 分享 | M15 | M01 门禁与 epoch、M10 | 仅 normal 时创建/重签 |
| 恢复终结 | M17 | 各表所有者钩子 | 新 epoch、分享 disabled、未完成任务恢复中断 |

- **PG 权威状态**：各表唯一写入模块；对外快照由 M04 提供。
- **Outbox**：M03。
- **执行栅栏**：M03 产生 `FencedTask`，所有写入方持有它。
- **Provider unknown**：M08 判定与记账，M03 使任务失败。
- **正式发布**：M10。**资产保护**：M07。**分享授权**：M15；M18 永不参与授权。

## 6. 关键链路

- **A 提交到正式文章**（S0 骨架，S1 真实）：M12 规范化 → M03 T1（M01 门禁、M05 固定 revision、容量、task+Outbox+事件）→ `202` → dispatcher → Celery → M03 T2（经 Port 由 M08 判定失联调用）→ video handler：M09 获取（M06 代理、M07 安装、M03 T3、冻结 snapshot）→ 无字幕时 M09 ASR 每块经 M08 T4/T5 → M09 取帧 → M11 图（`run_once`、M08 调用、M10 校验）→ M10 T6 → M04 快照/SSE → M10 ArticleView。
- **B unknown 与主动重试**：sending 中崩溃 → M08 判定 unknown → M03 failed → M04 显示可能已计费 → M12 `/retries` → M03 T1 新任务（`retry_of`）→ 复用有效阶段（M03 `reused_from`、M07 pin）；原调用账保留。
- **C 取消与发布竞争**：M03 T7 与 M10 T6 锁同一 task 行，提交顺序裁决；已授权调用变 unknown 时按 REQ-05 失败。
- **D 问答一轮**：M13 锁 conversation → M03 admit → worker 中 M13 取证（M09、M10）→ M08 调用 → M13 T6。
- **E 分享读取**：M15 每次查 PG（status、epoch、版本）→ M18（可选）→ M10 投影；图片单独校验 allowlist，经受限函数取 M07 租约。
- **F 旧备份恢复**：M17 单事务调用 M01 换 epoch → M03 中断任务 → M08 sending 置 unknown → M07 租约失效 → M15 全部 disabled → M02 清会话 → review_required，等待 confirm。
- **G 清理与补看**：M07 T8 行锁核查 refs/lease；M09 重下载比对完整 hash 与时间线，一致才绑定旧 snapshot。

## 7. 模块 × 切片

● 主交付　◐ 扩展　○ 局部或回归；S9 落点由实测决定。

| 模块 | S0 | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 | S10 | S11 | S12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M01 | ● | ○ | | | ○ | | | | ◐ | ◐ | | |
| M02 | ● | | | | | | | ◐ | ○ | ◐ | | |
| M03 | ● | ◐ | ○ | ◐ | ◐ | ◐ | ◐ | | ○ | ◐ | | |
| M04 | ● | ◐ | | | ◐ | | | | | | | |
| M05 | | ● | ◐ | | | ◐ | | | | ○ | | |
| M06 | | ● | ○ | | | ◐ | | | ◐ | | | |
| M07 | | ● | ○ | ○ | ○ | ◐ | ◐ | ◐ | ● | ◐ | | |
| M08 | | ● | ◐ | | ◐ | ◐ | | | | ◐ | | |
| M09 | ○ | ● | ◐ | | | ○ | | | ◐ | | | |
| M10 | | ● | | ◐ | ○ | ◐ | ○ | ◐ | | | | ○ |
| M11 | | ● | | ◐ | ◐ | | | | | | | |
| M12 | ◐ | ● | ◐ | ● | ○ | | | | | | | |
| M13 | | | | | | ● | | | ○ | | | |
| M14 | | | | | | | ● | | ○ | | | |
| M15 | | | | | | | | ● | | ◐ | | ○ |
| M16 | | | | | | | | | ◐ | | ● | |
| M17 | | | | | | | | | | ● | | |
| M18 | | | | | | | | | | | | ● |
| X1/X2 | ● | ◐ | | | ◐ | | | | ● | | | |

## 8. Grill 与实施顺序

| 批次 | Grill 顺序 | 之后 |
| --- | --- | --- |
| A（S0） | ① M01（含 X1 的 S0 部分）→ ② M03 → ③ M04 → ④ M02 → ⑤ M12 | `/to-tickets` S0。M12 此时定请求/身份/复用契约，流水线对下游的接口需求先声明，批次 B 末复核；S0 所需 URL 规范化按 SPEC §11.1 实现，在 M09 Grill 中复核 |
| B（S1/S2） | ⑥ M05 → ⑦ M07 → ⑧ M08（含可控 Provider）→ ⑨ M06 → ⑩ M09（含可控媒体源）→ ⑪ M10 → ⑫ M11 | 复核 M12 流水线 → `/to-tickets` S1，再 S2 |
| C（S3/S4） | 无新模块 | 用已确认模块 SPEC 拆 Ticket；发现缺口时补对应模块 Grill |
| D（S5～S8） | ⑬ M13 → S5；⑭ M14 → S6；⑮ M15 → S7 | S8 用已有 M07/M09/M01/X1 SPEC 拆 Ticket |
| E（S9、P1） | S9 实测优化；⑯ M17 → S10；⑰ M16 → S11；⑱ M18 → S12 | — |

## 9. 代码目录映射

沿用 SPEC §2，路径相对 `backend/src/frameread/`；router 文件按资源组织，单个端点的归属以 §3 为准。每个模块编写自己所属表的迁移。

| 模块 | 后端 | 前端 |
| --- | --- | --- |
| M01 | `db/`、`domain/` 共享枚举与策略、`api/errors`、`api/dependencies`、`security/crypto`、`observability/logging`、`observability/health`、`cli/main`；Settings 位置在 M01 Grill 确定 | — |
| M02 | `security/admin_session`、`security/csrf`、`api/admin_app.py`、`api/public_app.py`、`cli/credentials`；`deploy/gateway/` 与 X1 共用 | `src/admin` 登录与外壳 |
| M03 | `services/admission`、`services/execution`、`worker/`、`control/dispatcher`、`control/reconciler`、`control/scheduler`；`api/routers/tasks` 的取消与找回端点 | — |
| M04 | `api/routers/tasks` 的列表、快照、SSE；`api/schemas/events` | `src/admin` 任务列表与状态 |
| M05 | `api/routers/settings` 及其 Service | `src/admin` 设置 |
| M06 | `security/egress` 与 egress-proxy 入口 | — |
| M07 | `storage/`、`control/gc`、`control/retention` 中资产部分 | — |
| M08 | `providers/`（chat、transcription、search、ledger、quota） | — |
| M09 | `media/` | — |
| M10 | `services/publication`、`domain/validators` 文章规则、`api/routers/articles`、`api/schemas/article`、`api/schemas/evidence` | `src/shared` 渲染器、`src/admin` 阅读 |
| M11 | `generation/`（`evidence_validation` 节点调用 M10 规则） | `src/admin` 草稿视图 |
| M12 | `api/routers/videos`、`domain/identities`、`domain/fingerprints`、video KindHandler；`api/routers/tasks` 的 retries 端点 | `src/admin` 提交、匹配、重试 |
| M13 | `services/qa`、`api/routers/qa`、`providers/web_reader` | `src/admin` 问答 |
| M14 | `services/export`、`api/routers/exports` | `src/admin` 导出 |
| M15 | `services/share`、`api/routers/shares`、public 路由；迁移中的 public role/视图/函数 | `src/public` |
| M16 | `observability/overview_queries`、`observability/metrics`、`api/routers/overview` | `src/admin` 概览 |
| M17 | `services/restore`、`cli/backup`、`cli/restore` | — |
| M18 | 位置在 M18 Grill 确定 | — |

## 10. 进度板

状态取值：Grill 为“未开始 / 进行中 / 已对齐（需用户明确确认，记日期）”；模块 SPEC 为“— / 草稿 / 已确认（记日期与路径）”。

### 10.1 模块

| 模块 | 批次 | Grill | 模块 SPEC | 备注 |
| --- | --- | --- | --- | --- |
| M01 | A | 已对齐（2026-11-15） | 已确认（2026-11-15）`.scratch/m01-instance-platform/spec.md` | 结论已回写 SPEC §4.1、§6.1、§7.2、§19 |
| M02 | A | 已对齐（2026-11-15） | 已确认（2026-11-15）`.scratch/m02-admin-access/spec.md` | 会话表物理清理为逻辑删除例外 |
| M03 | A | 已对齐（2026-11-15） | 已确认（2026-11-15）`.scratch/m03-task-runtime/spec.md` | 槽 retired 规则已回写 SPEC §6.2 |
| M04 | A | 已对齐（2026-11-15） | 已确认（2026-11-15）`.scratch/m04-task-sync/spec.md` | 含前端底座选型 |
| M05 | B | 未开始 | — | |
| M06 | B | 未开始 | — | |
| M07 | B | 未开始 | — | |
| M08 | B | 未开始 | — | |
| M09 | B | 未开始 | — | |
| M10 | B | 未开始 | — | |
| M11 | B | 未开始 | — | |
| M12 | A，B 末复核 | 已对齐（2026-11-15，S0 范围） | 已确认（2026-11-15）`.scratch/m12-video-usecase/spec.md` | 流水线下游接口待 B 末复核 |
| M13 | D | 未开始 | — | |
| M14 | D | 未开始 | — | |
| M15 | D | 未开始 | — | |
| M16 | E | 未开始 | — | |
| M17 | E | 未开始 | — | |
| M18 | E | 未开始 | — | |

### 10.2 切片

| 切片 | 新增所需模块 SPEC（另含全部前序切片所需） | Ticket 目录 | Ticket 完成/总数 | AT 证据 | 状态 |
| --- | --- | --- | --- | --- | --- |
| S0 | M01、M02、M03、M04、M12 | `.scratch/s0-local-admission/` | 4/10（01～04 resolved，05、06、09 实施中） | `docs/validation/s0/01-platform-skeleton.md`、`docs/validation/s0-ticket02/02-admin-login-shell.md`、`docs/validation/s0-ticket03/03-video-admission.md`、`docs/validation/s0-ticket04/04-policy-maintenance-cli.md` | 进行中 |
| S1 | M05、M06、M07、M08、M09、M10、M11，M12 复核 | `.scratch/s1-subtitle-article/` | 0/0 | — | 未开始 |
| S2 | — | `.scratch/s2-platforms-asr/` | 0/0 | — | 未开始 |
| S3 | — | `.scratch/s3-request-behaviors/` | 0/0 | — | 未开始 |
| S4 | — | `.scratch/s4-recovery-cancel-sse/` | 0/0 | — | 未开始 |
| S5 | M13 | `.scratch/s5-private-qa/` | 0/0 | — | 未开始 |
| S6 | M14 | `.scratch/s6-offline-export/` | 0/0 | — | 未开始 |
| S7 | M15 | `.scratch/s7-readonly-share/` | 0/0 | — | 未开始 |
| S8 | — | `.scratch/s8-lifecycle-ops/` | 0/0 | — | 未开始 |
| S9 | 按实测 | `.scratch/s9-measured-optimization/` | 0/0 | — | 未开始 |
| S10 | M17 | `.scratch/s10-backup-restore/` | 0/0 | — | 未开始 |
| S11 | M16 | `.scratch/s11-overview/` | 0/0 | — | 未开始 |
| S12 | M18 | `.scratch/s12-content-cache/` | 0/0 | — | 未开始 |

### 10.3 Ticket 状态与完成证据

- 状态流转：`ready-for-agent` → `claimed` → `resolved`；`needs-info`、`ready-for-human`、`wontfix` 按 [triage-labels](../../docs/agents/triage-labels.md)。
- 置 `resolved` 前在 Ticket 末尾 `## Answer` 写明：commit、实际运行的测试/检查命令与结果、`docs/validation/` 证据路径、未完成项。缺任一项保持 `claimed`。
- 每完成一个 Ticket，更新 §10.2 计数与 §10.4。切片“已交付”要求本片 AT 子场景证据齐全；AT 整项通过要求全部子场景完成（PRD §6）。

### 10.4 当前可执行

- 批次 A 五个模块 Grill 已对齐，逐条决定见 [grill-batch-a.md](grill-batch-a.md)。五份模块 SPEC 已确认，SPEC 待确认事项的裁决见 [spec-resolutions-batch-a.md](spec-resolutions-batch-a.md)。S0 已拆为 10 个 Ticket（`.scratch/s0-local-admission/issues/`）。01～04 已合入集成分支；05、06、09 并行实施，07、08 等待 06。执行记录见 [S0 实施计划](../s0-local-admission/task_plan.md)。
- S0 在分支 `feat/s0-local-admission` 上进行；基线文档已提交于 `b7674bb`。

## 11. 待模块 Grill 解决的问题

| # | 问题 | 归属 |
| --- | --- | --- |
| 1 | b23.tv 短链（已解决）：API 不联网，按规范化短链受理，Worker 在 acquire 经 M09/media proxy 解析并填 source_id；匹配返回 `match:null, reason=short_link_unresolved`。M09 Grill 定解析超时与失败分类 | M09、M12 |
| 2 | 磁盘安全线（部分解决）：T1 在实例锁内读 control 采样结果，超线或采样过期均 `503 DEPENDENCY_UNAVAILABLE(disk_low)`，S1 实现；采样字段归属待 M09 Grill | M12、M09、M03 |
| 3 | S0 受控流水线（已解决）：video KindHandler 骨架只写 acquire 阶段并协作等待，只能 canceled 或 deadline 时 failed（`PIPELINE_NOT_AVAILABLE`），不写文章表；S1 删除骨架，不留开关 | M03、M12 |
| 4 | 版本历史 `GET /articles` 的列表维度（按来源、匹配或全部） | M10 |
| 5 | `/tasks/{id}/retries` 对 export/probe（已解决）：仅接受 video，其他 kind 返回 `409 INVALID_TRANSITION`，S3 实现 | M12、M14、M08 |
| 6 | 迁移策略与 AT-20 基线（已解决）：按切片增量 revision，合入 `main` 后只追加，基线取 S7 head，见 SPEC §7.2 | M01 |
