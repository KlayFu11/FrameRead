# M12 视频解读用例 模块 SPEC

Status: ready-for-agent
日期：2026-11-15。依据：[Grill 批次 A](../frameread-v1/grill-batch-a.md)（M12 部分 Q41～Q46，并引用 Q19～Q21）、[待确认裁决](../frameread-v1/spec-resolutions-batch-a.md)（U1、R6、R7、R14、D42、D46、D50～D59，第二轮 E1、E2、E8、E11、E12）、[模块地图 §3 M12](../frameread-v1/map.md#3-模块清单)。

本文只定义 M12 在 V1 中的全部职责；每条实现决定标注落地切片。S0 为本轮交付范围，S1 及以后仅作接口声明，批次 B 末复核。

## 问题陈述

部署者在个人实例中提交视频解读请求，需要得到一个可查询、可追溯的任务。视频请求同时涉及四类行为（HTTP 幂等重发、历史结果匹配、主动重新解读、主动重试，见 [REQ-02](../../docs/prototype/PRD.md)），但 S0 只交付其中的“新提交”与其幂等重发。

在 S0 中，如果没有统一的规范化与身份规则，会出现以下问题：

- 同一视频的不同 URL 写法（追踪参数、`p` 分 P、`youtu.be`、`list=`）产生不同 digest，网络重发被误判为冲突，或同一视频被重复建任务。
- 响应丢失后重发同一请求可能创建第二个任务，违反 [REQ-02](../../docs/prototype/PRD.md) 与 AT-02。
- S0 没有模型、媒体与文章表。如果骨架任务表现得像真实解读，部署者会误以为文章已生成。
- 短链若在提交时联网解析，会把外部访问放进受理事务之前，并引入不可控延迟。

M12 需要在 S0 先固定请求契约、身份规则与受理映射，让后续 S1～S3 在不改变身份语义的前提下扩展真实流水线。

## 解决方案

M12 是 L4 用例入口（[模块地图 §4.1](../frameread-v1/map.md#41-分层)），在 S0 承担以下职责：

- 管理 HTTP 路由 `POST /video-tasks`，把请求规范化、计算 digest，并把结果交给 M03 的 T1 受理事务（M12 不直接写 tasks、Outbox 或事件表）。
- 提供两个纯函数：`normalize_video_input` 与 `request_digest`，附表驱动单测。URL 解析 `parse_video_url` 放在 M09 的 `media` 目录，S0 先实现，受理时由 M12 调用（R14、D52）。
- 注册 video KindHandler 的 S0 骨架：只写 `acquire` 阶段，等待取消或期限，不生成文章，S1 删除。
- 提供提交页面与任务详情的说明面板（管理前端，目录见 [模块地图 §9](../frameread-v1/map.md#9-代码目录映射)）。详情页归 M04，提交页与骨架提示由 M12 提供（D46）。

S0 不解析默认配置、不联网、不做历史匹配与重新解读；这些在对应切片中按本文的实现决定补齐。

## 用户故事

1. 作为部署者，我希望在管理页面填写视频链接、解读模式、深度和关注点后提交，以便创建一个可查询的视频任务。
2. 作为部署者，我希望提交成功后立即看到任务 ID 与快照地址，以便确认系统已受理，且明白这不代表解读已经完成。
3. 作为部署者，我希望 S0 中提交任何模型或 ASR 覆盖项都被明确拒绝，以便不误以为该配置已经生效。
4. 作为部署者，我希望同一视频的不同 URL 写法（追踪参数、`youtu.be`、`list=` 附加参数、Bilibili 的 `p` 参数）被规范为同一输入，以便同键重发不会因 URL 写法不同而冲突。
5. 作为部署者，我希望 Bilibili 缺省 `p` 时固定为单分 P1，显式 `p` 时固定为对应分段，以便同一分段的任务身份稳定。
6. 作为部署者，我希望非 HTTPS、带用户信息、非 443 端口或格式非法的链接被 `INVALID_INPUT` 拒绝，不支持站点或路径的链接被 `UNSUPPORTED_VIDEO` 拒绝，以便不会把不安全或无法处理的地址排入队列，并能区分修正方式。
7. 作为部署者，我希望拒绝链接时错误体不回显我输入的原始 URL，以便错误信息和日志不泄露原始地址。
8. 作为部署者，我希望在 `topic` 模式下未填写关注点时收到明确的 `422`，以便修正输入。
9. 作为部署者，我希望关注点首尾空白不改变任务身份，以便复制粘贴的空白不会导致同键冲突。
10. 作为部署者，我希望提交响应在网络中断后，用同一幂等键重发能得到原任务 ID，以便不产生重复任务。
11. 作为部署者，我希望同一请求的并发双击只得到一个任务，以便不因界面重复点击而重复计费或排队。
12. 作为部署者，我希望同键不同输入时收到 `409 IDEMPOTENCY_CONFLICT` 并看到原任务 ID，以便找到原任务，且原任务不被覆盖。
13. 作为部署者，我希望前端在未明确收到 `202` 或 `4xx` 前沿用同一幂等键，以便 `503` 或网络失败后重发仍然安全。
14. 作为部署者，我希望在受理结果无法确认（`ADMISSION_UNCONFIRMED`）时看到“受理结果未确认”而非“任务不存在”，并能用原键找回，以便不因误判而新建任务。
15. 作为部署者，我希望执行槽和等待位都满时收到 `503 QUEUE_FULL` 且没有任何任务或待投递记录，以便释放容量后用原键再次提交。
16. 作为部署者，我希望满额时用同键重发一个已受理的请求仍得到原任务 ID，以便已受理请求不会因容量问题丢失。
17. 作为部署者，我希望 S0 骨架任务被领取后在详情页显示“S0 骨架：不会生成文章”，以便清楚知道它不是真实解读。
18. 作为部署者，我希望在详情页取消骨架任务后任务变为已取消，以便验证取消链路。
19. 作为部署者，我希望骨架任务不写入任何文章、版本、资产或模型调用记录，以便确认 S0 不会产生费用或假成果。
20. 作为部署者，我希望骨架任务运行中到达总期限后明确失败并显示 `PIPELINE_NOT_AVAILABLE`，排队、等待安全重试或 lease 失联后已超期则失败并显示 `DEADLINE_EXCEEDED`，以便知道失败原因。
21. 作为部署者，我希望提交 `intent=reinterpret` 时收到明确的 `422`（`intent_not_available`），以便知道该功能尚未在 S0 中提供。
22. 作为部署者，我希望在维护模式或恢复后待确认（review_required）状态下提交被 `503 MAINTENANCE` 拒绝且无残留记录，以便维护期间不产生新任务。
23. 作为部署者，我希望视频提交接口只对已登录管理员开放，以便公开入口或未授权请求无法提交任务。
24. 作为部署者，我希望视频链接在提交时不被联网解析，以便提交快速完成且不产生外部访问。
25. 作为部署者，我希望 b23.tv 等短链在 S0 只校验主机是否属于支持集合，以便受理不依赖外部网络，而解析在 Worker 中进行并可追溯。
26. 作为部署者，我希望同一视频的两次不同键提交各自生成独立任务，以便后续主动重新解读（S3）不会被视频 URL 唯一性阻挡。
27. 作为部署者，我希望提交的 `Idempotency-Key` 缺失或不是合法 UUIDv4 时立即收到 `422`，以便问题在受理前暴露。
28. 作为部署者，我希望在 Worker 或 control 停止后，已受理的视频任务仍可按原 ID 查询，并在恢复后继续进入执行，以便受理结果不因投递中断而丢失。
29. 作为部署者，我希望 S0 的全部提交、重发、取消验证不需要配置任何模型服务，以便在无 API 密钥的本地环境完成验收。
30. 作为部署者，我希望页面的 URL 与表单错误在提交前给出反馈，且后端仍重复校验，以便前后端规则不一致时以后端为准。
31. 作为运维中的部署者，我希望日志能用 `request_id` 与 `task_id` 关联某次提交的结果，以便定位问题。
32. 作为运维中的部署者，我希望日志与错误体中不出现原始 URL、平台 ID、关注点原文或密钥，以便日志可以安全分享。
33. 作为后续模块开发者（Agent），我希望 `normalize_video_input` 与 `request_digest` 是纯函数，并有表驱动单测覆盖全部 URL 规则，以便 S1、S3 复用时不改变既有身份。
34. 作为后续模块开发者（Agent），我希望骨架 handler 与真实流水线之间的替换边界清楚（S1 删除骨架，不留开关），以便替换时不遗留旧路径。
35. 作为后续模块开发者（Agent），我希望 M12 对 M03、M09、M10、M11 的接口需求在本文中先声明，以便批次 B 末复核时有明确对照点。
36. 作为后续模块开发者（Agent），我希望 digest 中配置字段的 sentinel 与 `effective_input_json` 的 `config_resolution` 规则写明，以便 S1 移除 `422` 时确认已受理任务的 digest 兼容性。

## 实现决定

### 请求契约与校验

- [S0] 请求体为 `VideoTaskCreate`，保留完整字段，所有字段 `extra='forbid'`；`url` 不超过 2048，`mode` 为 `complete/topic`，`depth` 为 `brief/standard/detailed`，`focus` 不超过 2000，`topic` 模式必须有非空关注点（SPEC §5；Q41）。
- [S0] `provider_config_id` 与 `asr_config_id` 为 `null` 时，digest 中使用固定 sentinel 字符串 `"$default"`；`effective_input_json` 为规范化 DTO 加 `config_resolution: "unresolved"`；`provider_revision_id` 留空即 SQL NULL（Q41；D53；E11）。任一字段非 `null` 返回 `422 INVALID_INPUT`。S1 移除此拒绝，并在受理时解析默认项；S1 起显式填写与留空默认产生不同 digest，同键返回 `409`，属预期行为（D53）。
- [S0] `intent` 固定为 `new`；`intent=reinterpret` 返回 `422 INVALID_INPUT`，`details` 为 `intent_not_available`，S3 实现（Q45；D55）。
- [S0] `Idempotency-Key` 为必填 UUIDv4，缺失或非 UUIDv4 返回 `422 INVALID_INPUT`（Q20；R6，以 SPEC §3 为准）。`operation_scope` 由服务端固定为 `video:new`，不接受调用方传入（SPEC §3）。
- [S0] 错误体与日志不回显原始 URL 与关注点原文（SPEC §4.1）。错误类别沿用 M01 的 StrEnum 与 HTTP 映射（Q8；D11）。

### 规范化与身份（纯函数）

- [S0] `normalize_video_input` 输出规范输入：去除追踪参数，固定平台、`platform_video_id` 与 `part_id`，不展开列表参数；`focus` 只去首尾空白；`mode`、`depth` 为固定枚举（SPEC §3、§3.1；Q46）。
- [S0] `request_digest` 对规范 DTO 做键排序、UTF-8、Unicode NFC 处理后计算 SHA-256；密钥与 session 不进入 digest（SPEC §3.1；Q46）。
- [S0] 错误类别（D50）：非 HTTPS、带 userinfo、非 443 端口、格式非法返回 `INVALID_INPUT`；host 或路径不在支持范围内返回 `UNSUPPORTED_VIDEO`。两者均为 SPEC §4.1 的 `422` 类别。
- [S0] 支持范围（D51，M09 Grill 复核）：`bilibili.com`、`www.bilibili.com`、`m.bilibili.com`、`b23.tv`、`youtube.com`、`www.youtube.com`、`m.youtube.com`、`youtu.be`。YouTube 路径支持 `watch?v=`、`shorts/{id}`、`youtu.be/{id}`。
- [S0] URL 规则（表驱动覆盖，Q46）：
  - `p` 参数：Bilibili 缺省视为单分 P1，显式 `p` 固定对应分段（SPEC §3）。
  - `youtu.be` 短链：只校验 host，不联网（见下条）。
  - `list=` 参数：忽略，不展开播放列表（SPEC §3、§11.1）。
  - 追踪参数：去除，不影响身份。
- [S0] 短链只校验主机属于支持集合，不发起网络请求，按规范化短链受理，`source_id` 留空；Worker 在 acquire 阶段经 M09 解析并回填（Q42；[模块地图 §11](../frameread-v1/map.md#11-待模块-grill-解决的问题) 第 1 条）。b23.tv 短链的规范形式为 `https://b23.tv/{code}`，host 转小写，去掉 query 与 fragment（E11）。
- [S0] `parse_video_url` 放在 M09 的 `media` 目录，S0 先实现，受理时由 M12 调用；超时与失败分类由 M09 Grill 确定（R14；D52；Q46）。
- [S0] 同一视频的不同键各自产生独立任务，URL 相同不阻止提交（REQ-02）。

### 受理与 M03 的协作

- [S0] M12 通过 M03 的 T1 提交，`AdmissionRequest` 字段（D42）：`kind`、`pool`（S0 为 `video`，取值集合见 E11）、`intent`、`scope`、`key`、`request_digest`、`effective_input`、`input_hash`、`total_timeout`、`retry_of_task_id`（S0 为空）、`budget`（S0 为 `{"version":1,"limits":{}}`）。`replayed` 仅在找回已有任务时为 true。`provider_revision_id` 留空（Q41、Q20；[模块地图 §5](../frameread-v1/map.md#5-事务与关键职责归属)）。
- [S0] M12 只传入 `policy_json` 中 video 总期限作为 `total_timeout`（E1；SPEC §8.2）。`deadline_at = db_now() + total_timeout` 由 M03 在 T1 内计算。客户端以 `TaskAccepted.deadline_at` 为准。
- [S0] 结果映射：`202` 返回 `TaskAccepted`（字段见 SPEC §5），`Location` 与 `snapshot_url` 指向任务快照；同键同 digest 返回原任务，`replayed=true`，即使原任务已结束也返回 `202` 与当前状态（SPEC §4.1）。
- [S0] 同键不同 digest 返回 `409 IDEMPOTENCY_CONFLICT`，错误体携带原 `task_id`，不修改原任务（Q20；AT-02）。比较的是原始请求 digest，不按“当前默认”重新解析（SPEC §3.1）。
- [S0] `CommitOutcomeUnknown` 后由 M03 换新连接按 `(scope, key)` 查一次：一致返回 `202`，不一致返回 `409`，未找到返回 `503 ADMISSION_UNCONFIRMED`；不轮询，不提示换键（Q21）。M12 只负责把结果映射为 HTTP。显式回滚的提交失败（`rolled_back`，COMMIT 之前断开）返回 `503 DEPENDENCY_UNAVAILABLE`，不留下任何记录（E8）。
- [S0] 执行槽与等待位满额：`503 QUEUE_FULL`，无新增任务与 Outbox（SPEC §9.1）；同键已受理请求即使满额仍返回原任务（REQ-03；AT-04）。是否满额由 M03 判定，M12 保证满额判断前已完成 digest 与同键查找。
- [S0] 维护或 review_required 门禁：`503 MAINTENANCE`，拒绝新建（Q15、SPEC §9.1）。
- [S0] 路由只挂在管理 app，依赖 `require_admin`（Q33；SPEC §4）；会话与 CSRF 由 M02 处理（SPEC §4）。

### video KindHandler 骨架（S0 受控流水线）

- [S0] Claim 后写 `stage_key=acquire`、`output_json={"skeleton": true}`，然后随心跳检查取消（Q19；M03 的 `checkpoint` 与 `cancel_requested`）。
- [S0] 取消生效 → 任务 `canceled`。
- [S0] 分两种超期情况（E2）：handler 仍在运行、自己发现超期（骨架运行中到达期限）→ `failed`，错误码 `PIPELINE_NOT_AVAILABLE`（Q19）；由运行时发现超期（排队、retry_wait、lease 失联后已超期）→ `failed`，错误码 `DEADLINE_EXCEEDED`，骨架不进入（D29、R7）。
- [S0] 骨架不调用任何 Provider，不写文章表、版本表、资产表，也不声明阶段完成（Q19、Q26）。
- [S0] 骨架提示“S0 骨架：不会生成文章”由 M12 提供的 kind 说明面板显示在 M04 详情页中（Q19；D46）。
- [S0] 骨架通过 M03 的 KindHandler 注册机制接入（[模块地图 §4.1](../frameread-v1/map.md#41-分层)）。
- [S1] 删除骨架，不保留开关或配置项，由真实流水线替换（Q19）。

### 管理页面

- [S0] 路由（D46）：`/manage/videos/new` 为提交页，由 M12 提供；`/manage/tasks` 与 `/manage/tasks/:id` 由 M04 提供。
- [S0] 提交表单只有 URL、`mode`、`depth`、`focus`（Q45）；不显示模型或 ASR 选择，`intent` 固定为新提交。默认 mode=complete、depth=standard，complete 模式下也可以填写 focus（D56）。
- [S0] 前端按 SPEC §11.1 对 URL 与表单做提交前反馈，后端重复校验（SPEC §11.1）。
- [S0] 幂等键由 M04 前端底座的共享请求层生成并存入 sessionStorage，M12 调用（D46）。每份表单草稿对应一个幂等键；仅得到明确 `202` 或 `4xx` 后清除并开始新草稿，`503`、网络失败与响应未知时沿用原键（Q20；D56）。
- [S0] 收到 `202` 后跳转到任务详情（M04）；详情页的取消按钮调用 M03 的取消端点，取消按钮在 queued、running、retry_wait 状态出现（D45）。
- [S0] 页面不展示 digest、内部字段、session 或密钥。

### 数据

- [S0] M12 不拥有任何表（[模块地图 §3](../frameread-v1/map.md#3-模块清单)），不编写迁移；tasks、Outbox、事件由 M03 写入（[模块地图 §5](../frameread-v1/map.md#5-事务与关键职责归属)）。

### 日志与可观测

- [S0] 请求与任务日志只使用 M01 allowlist 中的 `request_id` 与 `task_id` 关联（Q11；D57）。`operation_scope` 不进入日志（M01 allowlist 不含该字段），日志不新增字段。AT-21 的 ID 链由 `request_id` → `task_id` 满足。
- [S0] 日志与错误体不记录原始 URL、平台 ID、video ID、关注点原文或密钥（SPEC §4.1、§20；D57）。

### 后续切片的接口声明（待批次 B 末复核）

- [S1] 受理时解析默认配置，保存 `effective_input_json`、确切 `provider_revision_id`、ASR revision、生成规则版本与资源策略快照，依赖 M05（SPEC §3.1）。
- [S1] 磁盘安全线：T1 在实例锁内读取 control 采样，超线或采样过期时返回 `503 DEPENDENCY_UNAVAILABLE`，`details` 中的 code 为 `disk_low`（Q43；SPEC §8.2；E12）。采样字段归属待 M09。
- [S1] `fingerprints` 阶段指纹纯函数随 S1 建立（D58）。
- [S1] 配置键使用 `pools.<pool>.execution_slots` 与 `pools.<pool>.waiting_slots`，`pool` 取值为 `video`、`qa`、`utility`（E11）。
- [S1] video handler 成功路径为编排方：M09 获取（acquire、短链解析、回填 `source_id`、冻结 acquisition manifest）→ 字幕或 ASR（M09 经 M08）→ 取帧（M09）→ M11 图 → M10 T6 发布（[模块地图 §6 链路 A](../frameread-v1/map.md#6-关键链路)）。
- [S2] 无字幕路径且无可用 ASR 配置：原任务 `failed`，错误码 `ASR_REQUIRED`，不自动启动 ASR；保存 ASR 配置后从原页新建关联任务（SPEC §11.2；REQ-01；D58）。
- [S3] `POST /videos/matches` 注册（D58；S0 不提供）：同步只读，零模型调用；短链未解析时返回 `match:null, reason=short_link_unresolved`；读取失败是查询失败，不转为未命中（SPEC §3.1、§4；Q42）。
- [S3] `intent=reinterpret` 的正式实现与 `video:reinterpret` 作用域（Q45；SPEC §3）。
- [S3] `POST /tasks/{id}/retries` 仅接受 video，原终态须为 `failed` 或 `canceled`；其他 kind 返回 `409 INVALID_TRANSITION`（Q44；R14；SPEC §4）。
- [S3] `result_match_hash` 实现与阶段复用判定（D58；SPEC §3.1、§3.2；[模块地图 §3 M12](../frameread-v1/map.md#m12-视频解读用例-m12-video-usecase)）。

## 测试决定

测试接缝编号沿用批次 A 约定：接缝 1 HTTP，接缝 2 进程，接缝 4 纯函数，接缝 5 浏览器。全部使用真实 PostgreSQL 与 Redis，不使用生产代码开关（Q25）。

### S0 必测场景

纯函数（接缝 4，表驱动）：

- `normalize_video_input` 与 `request_digest` 覆盖：`p` 参数（缺省与显式）、`youtu.be`、`list=`、追踪参数、userinfo、非 443 端口、非 HTTPS、不支持站点与路径（Q46；D50、D51）。
- 同一视频的不同 URL 写法、关注点首尾空白差异，产生相同规范输入与相同 digest（SPEC §3.1；AT-02 同键语义）。
- `null` 配置字段的 `"$default"` sentinel 与非 `null` 字段 digest 不同（Q41；D53）。
- 解析过程无 I/O：纯函数单测确认 `normalize_video_input` 不发起网络或文件访问（D59）。

HTTP（接缝 1）：

- 合法 `new` 提交返回 `202`；任务、Outbox 与受理事件各一份；`Location`、`snapshot_url` 与 `TaskAccepted` 字段完整（AT-02 新提交子场景）。
- 同键同输入并发（`asyncio.gather`）：仅一个任务，两个请求均返回同一 `task_id`（AT-02）。
- 客户端在提交后断开，再用同键重发：返回原 `task_id`，无第二个任务（AT-02 响应丢失）。
- 同键不同输入（URL、`mode`、`depth` 或 `focus` 任一不同）：`409 IDEMPOTENCY_CONFLICT`，错误体带原 `task_id`，原任务不变（AT-02 冲突）。
- 同键但 URL 写法不同（仅追踪参数不同）：返回原任务，不冲突（Q20、Q46）。
- 缺失或非 UUIDv4 的 `Idempotency-Key`：`422`（Q20；R6）。
- `config` 字段非 `null`、`intent=reinterpret`（`intent_not_available`）、`topic` 无关注点、未知字段：均 `422`（Q41、Q45、SPEC §5）。
- 非法 URL：格式非法（userinfo、非 443、非 HTTPS）返回 `INVALID_INPUT`，不支持站点返回 `UNSUPPORTED_VIDEO`；错误体均不回显原 URL（SPEC §4.1；D50）。
- 短链（`b23.tv`、`youtu.be`）提交返回 `202`；api-admin 仅接入 `internal: true` 网络且无出站路由，提交过程中若发起外部连接会失败，从而断言未联网（Q42；D59）。
- 满额（执行槽与等待位均满）新键：`503 QUEUE_FULL`，无新增任务、无 Outbox（AT-04，映射部分）。
- 满额时已受理键重发：返回原任务（AT-04）。
- 未登录或缺 CSRF 的提交：`401` 或 `403`，无任务（REQ-11；Q33；R11）。
- 维护或 review_required 状态提交：`503 MAINTENANCE`，无残留记录（Q15）。
- 骨架任务取消：快照变为 `canceled`，Outbox 与事件完整（Q19）。
- 骨架任务运行中到达期限：`failed`，错误码 `PIPELINE_NOT_AVAILABLE`；期限由夹具通过 `frameread policy set` 设为短期限触发，不依赖生产开关（Q19；D37；R7；E2）。
- 排队中超期的任务：`failed`，错误码 `DEADLINE_EXCEEDED`（D29；R7；E2）。
- 提交确认丢失（AT-19 受理确认子场景）：API 连接经 `tests/` 中的 PG 线协议 TCP 代理（U1），三种模式（E8）：
  - 丢弃 `COMMIT` 并断开：结果为 unknown，同键确认查不到，返回 `503 ADMISSION_UNCONFIRMED`。
  - 转发 `COMMIT` 后、回包前断开：结果为 unknown，同键确认能查到，返回 `202`（`replayed`）。
  - `COMMIT` 之前断开：结果为 rolled_back，返回 `503 DEPENDENCY_UNAVAILABLE`，断言无任务、Outbox 或事件残留。
  代理仅存在于测试，生产代码无开关（Q21；D06）。

进程（接缝 2）：

- 受理后 Worker 未启动、dispatcher 未发布时，任务仍可按 ID 查询；恢复后按同 ID 进入领取（AT-05 受理后未发送；SPEC §9.3）。
- 同一投递消息重复 `apply_async`：仅一个执行，无第二个业务任务（AT-05 重复消息）。
- 骨架领取后写入 `acquire` 阶段，`output_json` 为 `{"skeleton": true}`，无文章、版本、资产或 Provider 调用记录（Q19；AT-19/21 基础）。

浏览器（接缝 5，Playwright 经 gateway）：

- 提交表单填写 URL、模式、深度、关注点后跳转详情，显示“S0 骨架：不会生成文章”（Q45；D46）。提交表单默认 mode=complete、depth=standard（D56）。
- 详情页取消按钮生效，状态显示已取消。
- 模拟提交后响应中断，再次点击提交：页面沿用同键，返回原任务（Q20）。
- `503` 后沿用同键；`422`/`409` 后轮换为新键（Q20；D56）。

### 不在 S0 测试范围

- AT-02 的 `reinterpret`、主动重试与历史匹配（S3）。
- AT-03、AT-09、AT-11、AT-14 等真实流水线相关场景（S1 及以后）。

## 不在范围内

- 受理事务、容量、Outbox、领取与取消的实现（M03）。
- 快照与 SSE（M04）；会话与 CSRF（M02）。
- 默认配置解析与模型能力检查（M05，S1）；磁盘采样（M09 字段归属，S1）。
- 来源获取、字幕、ASR、取帧（M09，S1～S2）；生成与校验（M11、M10，S1）。
- 历史匹配、主动重新解读、主动重试与复用指纹（S3）。
- 问答、导出与分享（M13、M14、M15）。
- 真实视频流水线与文章输出（S1 起）。

## 补充说明

### 与其他模块的接口约定

- 与 M03：M12 使用 T1 受理与取消端点，实现 KindHandler 注册，并按 D42 与 E1 提供 `AdmissionRequest` 字段（含 `total_timeout`）；M03 负责 `deadline_at` 计算、`ADMISSION_UNCONFIRMED` 的确认查询与超期收敛，M12 只映射 HTTP。`PIPELINE_NOT_AVAILABLE`、`DEADLINE_EXCEEDED` 与 `DISPATCH_EXHAUSTED`（E3，M03 的投递重试预算耗尽）只出现在 `TaskSnapshot.error.code`，登记于 SPEC §4.1 的任务错误码小节（R7、E3）；`INTERNAL_ERROR` 为 HTTP 类别（SPEC §4.1）。
- 与 M04：详情页与列表由 M04 提供，M12 提供提交页与 kind 说明面板；幂等键的生成与存储由 M04 共享请求层负责（D46）。
- 与 M02：路由依赖 `require_admin`，CSRF 与 Origin 校验由 M02 统一处理。
- 与 M01：错误类别、`request_id`、日志 allowlist 沿用 M01；日志只用 `request_id` 与 `task_id`（D57）。
- 与 M09：`parse_video_url` 放在 M09 的 `media`，S0 先实现（R14、D52）；磁盘采样字段归属待 M09 Grill。
- 与 M10、M11：S1 流水线接口需求（链路 A）已在实现决定中声明，批次 B 末复核。
- 与 M05：S1 默认配置解析依赖 M05 的固定 revision。

### 待确认

无阻塞 S0 的待确认项。`youtu.be/{id}` 不是需要联网展开的短链，路径即视频 ID，与 `watch?v=`、`shorts/{id}` 一样规范为 `https://www.youtube.com/watch?v={id}`（D51）；只有 b23.tv 保留短链形式（E11）。

不阻塞 S0、归属后续模块：S1 磁盘安全线的采样字段归属待 M09 Grill。

### 文档冲突

无未解决的文档冲突。第二轮 E1、E2、E8、E11、E12 已回写本文，`disk_low` 已由 SPEC §8.2 定义。
