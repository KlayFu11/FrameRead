# M01 实例门禁与平台底座 模块 SPEC

Status: ready-for-agent
日期：2026-11-15。依据：[Grill 批次 A](../frameread-v1/grill-batch-a.md) 的 M01（Q1～Q18）及 M02/M03/M04 中与 M01 接口相关的条目（Q5、Q10、Q21、Q30、Q35）、[批次 A 待确认裁决](../frameread-v1/spec-resolutions-batch-a.md)（U1～U3、R1～R4、R7、R10、D01～D16，以及 D33/D35/D38/D41 中涉及 M01 的部分）、[模块地图](../frameread-v1/map.md) §2、§3 M01、§5、§9，[SPEC_V1](../../docs/prototype/SPEC_V1.md)、[PRD](../../docs/prototype/PRD.md) S0 行与 AT-19～AT-22。

## 问题陈述

FrameRead 的所有写入（受理、领取、阶段检查点、外部发送授权、发布、配置、分享、维护）都必须共享同一个实例身份与写入门禁。若每个模块各自实现事务重试、连接预算、密钥派生、错误体、日志字段与健康判定，就会出现：维护态下某个写入点漏检门禁而继续发起付费调用；恢复后旧 epoch 的执行者仍能提交；子密钥用途混用；错误体泄露 SQL、路径或栈；迁移与进程版本不一致时服务继续写库；空库或旧 secrets 被误覆盖。

M01 是 L0 底座。它只实现一份事务、门禁、配置、密钥、错误、日志与健康约定，使上层模块只能通过它获得这些能力。当前仓库尚无业务代码，S0 需要从空库起建立可增量启动的 Compose、迁移与最小可测试底座。

## 解决方案

M01 提供以下能力。按 Q1 逐模块对齐全部职责，各条实现决定在下文标注落地切片；S0 为主交付：

1. `instance_state` 单例与 `instance_write_gate`：在实例行锁内判定维护与恢复状态；维护 CLI 修改 `maintenance_mode`。
2. UnitOfWork / Session 约定：Repository 只构造语句，async 与 sync 两个薄执行器运行；统一的锁、门禁与提交方法；有界事务重试；提交阶段不确定的 `CommitOutcomeUnknown`。
3. Settings（非敏感配置 + `*_FILE` 凭据文件）与 `policy_json` 运行时策略。
4. KeyRing：从根密钥经 HKDF-SHA256 派生四个用途子密钥；启动时根密钥校验值比对。
5. 迁移运行器：advisory lock、单例初始化、head 校验与连接预算静态比对。
6. 统一错误体与错误码登记；`request_id` 中间件；结构化日志字段 allowlist。
7. 健康框架：live/ready、探针注册、unknown 语义。
8. `FencedTask` 值类型（供 M03/M07/M08 共用，不引入依赖环）。
9. Typer CLI `frameread` 与 X1 交付工程的 S0 部分（Compose、镜像、锁文件、OpenAPI 导出、CI 基础）。

M01 不建业务表，不实现各模块探针（Redis 探针除外，见 D41）、备份恢复流程、恢复 epoch 变更或 public app。

## 用户故事

### 部署者

1. 作为部署者，我希望首次部署时由 CLI 生成随机根密钥，以便实例从一开始就有可校验的密钥身份（installation_id 由迁移在空库初始化时生成）。
2. 作为部署者，我希望 `secrets init` 在 secrets 目录已有文件时拒绝执行，以便误操作不覆盖已有密钥。
3. 作为部署者，我希望 CLI 与服务日志都不回显密钥或连接字符串，以便密钥不进入终端历史、日志或截图。
4. 作为部署者，我希望凭据文件缺失或为空时服务启动即失败并指出是哪一项，以便配置错误不拖到运行中才暴露。
5. 作为部署者，我希望首次 `docker compose` 启动按 secrets 初始化、数据库角色创建、migrate、服务启动的顺序执行，以便每一步的前置条件都已满足。
6. 作为部署者，我希望 migrate 在空库上建立 schema、初始化实例单例并从 `settings.toml` 写入初始 `policy_json`，以便系统无需手工初始化即可运行。
7. 作为部署者，我希望已有数据而根密钥缺失时启动失败，以便系统不会生成新密钥去覆盖旧密文。
8. 作为部署者，我希望 migrate 失败时服务不写库、不自动清库、不自动降级，并保留诊断信息，以便我能按备份或兼容版本恢复。
9. 作为部署者，我希望 api-admin、worker、control 启动时比对根密钥校验值，以便误挂错误密钥的进程立即拒绝运行。
10. 作为部署者，我希望 migrate 启动时按连接预算与数据库 `max_connections` 做静态比对，以便连接超配在部署时即被发现。
11. 作为部署者，我希望普通 `restart` 不改变 installation_id 与 instance_epoch，以便重启不会误使任务或分享失效。
12. 作为部署者，我希望用 `maintenance set draining` 停止新业务副作用，以便升级前让正在进行的工作安全收敛。
13. 作为部署者，我希望 draining 下已获准的模型回执、当前阶段检查点、续租与资源释放仍能完成，以便正在进行的付费调用不会因维护而丢失结果。
14. 作为部署者，我希望用 `maintenance set frozen` 时只有维护 CLI 能写库，以便升级或恢复期间没有任何业务写入。
15. 作为部署者，我希望维护态下新受理请求返回 `503 MAINTENANCE`，而幂等找回与只读查询仍可使用，以便客户端区分"不能受理"与"已受理"。
16. 作为部署者，我希望 `policy set` 修改资源策略后 `config_revision` 递增，以便我能确认配置已经变化。
17. 作为部署者，我希望 `policy set` 拒绝非法值，以便非法资源策略不会进入运行中的系统。
18. 作为部署者，我希望运行中的 `policy_json` 与 `settings.toml` 不一致时只看到 warning，以便已运行策略不会因改文件而被意外改变。
19. 作为部署者，我希望 `/health/live` 只表示进程存活，`/health/ready` 按依赖给出 `ready/degraded/unavailable/unknown` 分项，以便区分进程故障与依赖降级。
20. 作为部署者，我希望 PostgreSQL、迁移 head 或根密钥失效时管理写被拒绝，而 Redis 或 Worker 心跳异常只显示 degraded，以便我知道何时还能接单。
21. 作为部署者，我希望采集失败的健康项显示 `null + unknown` 而不是 0，以便故障不会被误读为健康。
22. 作为部署者，我希望健康检查不产生任何付费模型调用，以便观察系统状态不花钱。
23. 作为部署者，我希望 Compose 健康检查只使用 live，以便依赖短暂不可用时容器不会被反复重启。
24. 作为部署者，我希望容器以非 root、只读根文件系统、有资源限制且不挂载 Docker socket 运行，以便降低宿主机风险。
25. 作为部署者，我希望 CI 检查生产配置中没有非 8080 的 http origin，以便误配不会暴露明文管理入口。
26. 作为部署者，我希望日志使用 Docker `json-file` 的大小与文件数上限轮转，以便日志不会占满磁盘。
27. 作为部署者，我希望任何 API 失败响应都带 `request_id`，且同一值出现在 `X-Request-ID` 响应头与日志中，以便我凭它定位问题。
28. 作为部署者，我希望错误体不包含 SQL、内部路径、栈、上游响应体或原始 URL，以便对外响应不泄露内部信息。
29. 作为部署者，我希望 `openapi export` 生成的契约与提交文件 diff 为空，并在 CI 中被检查，以便接口变化可审查。

### 运维中的部署者

30. 作为运维中的部署者，我希望迁移期间 advisory lock 阻止另一个 migrate 并发修改 schema，以便升级不会出现双重迁移。
31. 作为运维中的部署者，我希望服务只接受与代码期望完全一致的 Alembic head，以便版本不兼容时拒绝写库而不是写坏数据。
32. 作为运维中的部署者，我希望 API 在数据库短暂不可用后主动重连并重新校验 migration，以便不依赖固定 sleep。
33. 作为运维中的部署者，我希望在 `frozen` 与 `draining` 之间切换的命令有明确结果与退出码，以便脚本能判断是否生效。
34. 作为运维中的部署者，我希望采集失败或探针超时只影响对应分项而不拖垮 live，以便排障时仍能确认进程状态。

### 后续模块开发者（Agent）

35. 作为后续模块开发者（Agent），我希望 UnitOfWork 统一提供 `lock_instance`、`gate.require` 与 `commit`，以便新的写入路径不能绕过门禁与锁顺序。
36. 作为后续模块开发者（Agent），我希望门禁与锁顺序规则只实现一份，以便 async API 与 sync Worker/control/CLI 行为一致。
37. 作为后续模块开发者（Agent），我希望 `run_transaction` 只对 `40001/40P01` 整体重跑，且对已进入提交阶段不确定的事务不重跑，以便已发送的外部调用不会被二次发送。
38. 作为后续模块开发者（Agent），我希望 Repository 的条件更新 0 行时统一抛出 `VERSION_CONFLICT`，以便并发修改不会静默覆盖。
39. 作为后续模块开发者（Agent），我希望 `updated_at` 由数据库触发器维护，以便各模块不各自实现时间戳。
40. 作为后续模块开发者（Agent），我希望 KeyRing 只允许四个约定用途派生子密钥，以便加密、会话 CSRF、游标与分享 token 的密钥用途相互隔离。
41. 作为后续模块开发者（Agent），我希望错误码以 domain 枚举定义并随 OpenAPI 导出，以便前端类型与后端错误码一致。
42. 作为后续模块开发者（Agent），我希望模块通过 `register_probe(name, fn, severity)` 注册健康探针，以便各依赖的判定规则不在别处重复实现。
43. 作为后续模块开发者（Agent），我希望 `FencedTask` 作为值类型放在 M01，由 M07 只接收不调用 M03，以便依赖保持单向。
44. 作为后续模块开发者（Agent），我希望 Settings 按进程拆分子集，以便 public 进程不加载管理凭据与根密钥相关配置。
45. 作为后续模块开发者（Agent），我希望日志字段越界在代码中直接抛错，以便新增字段必须先登记到 allowlist。
46. 作为后续模块开发者（Agent），我希望 CLI 与服务共用同一 sync UnitOfWork 与门禁，以便维护命令不会绕过维护规则。
47. 作为后续模块开发者（Agent），我希望所有表都带有创建时间、更新时间、逻辑删除与版本字段，只有明确允许的两张表可以物理删除，以便数据生命周期规则一致。

## 实现决定

### 3.1 实例身份与写入门禁

1. `instance_state` 为单例表，`singleton_key` 唯一且约束为 1，同时带通用列（U2，见 24）。保存 installation_id、instance_epoch、maintenance_mode（normal/draining/frozen）、restore_state（normal/backup_image/restoring/review_required）、restore 相关字段、policy_json、config_revision、last_backup_id、root_key_check。S0 只写入并读取 installation_id、instance_epoch、maintenance_mode、policy_json、config_revision、root_key_check；restore 字段的写入路径归 M17。〔落地：S0；restore 写入 S10〕（Q6、Q14、Q15；SPEC 6.1；U2）
2. 写入门禁 `gate.require(op)` 必须在实例行锁内同时判定 `maintenance_mode='normal' AND restore_state='normal'`，不得只检查其中一项。`op` 为操作类别枚举（D07）。各状态允许的类别如下，由 M01 的门禁表统一定义：

   | 状态 | 允许的写入类别 | 说明 |
   | --- | --- | --- |
   | normal 且 restore_state=normal | 全部 | admit、retry、claim、checkpoint、send_authorize、receipt、publish、config_write、share_write、dispatch（投递与等待位提升）、session（登录与退出）、lease_release、converge、cancel_request |
   | draining | receipt、checkpoint、lease_release、converge、session、cancel_request | 对应 SPEC 7.1 与 13.1 的例外；不允许 admit、retry、claim、新阶段、send_authorize、publish、config_write、share_write、dispatch。cancel_request 只减少工作，允许（E5） |
   | frozen | 无 | 除维护 CLI 外一律拒绝，包括 T7 取消与登录退出（session、cancel_request，E5；D07、D20，登录与退出返回 `503 MAINTENANCE`） |
   | restore_state=review_required | session | 即使 maintenance_mode=normal 也拒绝其余新建与写入（SPEC 9.1）；允许登录（E13）；读取租约可用于管理核对（SPEC 17.3） |

   只读查询与幂等找回不经过写门禁，任何状态下可执行（SPEC 7.1）。〔落地：S0 覆盖 admit、claim、checkpoint、config_write、session；send_authorize、publish、share_write 在对应切片接入〕（Q15；SPEC 7.1；D07、D20）
3. 维护态的放行规则以上表为准，并满足：所有例外仍须检查 epoch、fence、期限，不能绕过恢复门禁。〔落地：S0〕（Q15；D07）
4. 维护态下，T1 与 Claim 类写请求返回 `503 MAINTENANCE`（机器类别见 §3.5）；幂等找回与只读接口不受影响。〔落地：S0；测试 T1/T2 在三种非 normal 状态下〕（Q15；SPEC 4.1）
5. `restore_state` 在 S0 仅由测试 fixture 写入；`maintenance_mode` 由维护 CLI 写入（见 §3.7）。`maintenance set` 任意时刻可执行，但仅当 `restore_state=normal` 时才能设为 normal（D07）。〔落地：S0〕（Q15；D07）
6. `instance_epoch` 在空库初始化时生成；普通重启、迁移、维护切换均不改变；只有显式恢复（M17）才更新。S0 不存在恢复写入路径。〔落地：S0 生成与不变性；恢复 S10〕（SPEC 6.1、19）
7. 门禁与 epoch 每次在事务内读取，不跨请求、跨进程缓存（SPEC 17.3 中公开读取同样要求每次重验）。〔落地：S0〕（SPEC 7.1、17.3）
8. 锁模式由调用方在事务开始时确定：受理、领取、结束、取消、槽分配/释放与恢复使用 `FOR UPDATE`；仅写阶段、心跳、资产时使用 `FOR SHARE` 检查维护与 epoch。禁止先 SHARE 后升级 UPDATE。〔落地：S0〕（Q3；SPEC 7.1）
9. 全局锁顺序写一份：instance_state 必须最先锁；其后按 provider config（UUID）→ conversation → tasks（UUID）→ resource_slots（resource_key, slot_no）→ assets（UUID）→ 子记录。可先无锁定位父 ID，入锁后必须重新验证关系。GC 只锁 instance/asset，不反向锁 task；不得在事务内持锁等待 HTTP 或文件 I/O。锁顺序作为代码约定，由并发测试覆盖，不加运行时断言（D14）。〔落地：S0 使用 instance → tasks → resource_slots 子集；其余随切片〕（SPEC 7.1；D14）

### 3.2 启动校验、Settings 与密钥

10. Settings 基于 pydantic-settings，位于 `frameread.settings` 模块（路径见 map §9）。非敏感配置来自 `settings.toml`；凭据只接受 `*_FILE` 形式的文件路径（SPEC 19 的命名为 `DATABASE_DSN_FILE`、`PUBLIC_DATABASE_DSN_FILE`、`REDIS_URL_FILE`、`MASTER_KEY_FILE`、`ADMIN_PASSWORD_HASH_FILE`）；缺失或读出为空即启动失败。`FRAMEREAD_SETTINGS` 环境变量指定 toml 路径，生产默认 `settings.toml`，开发环境显式指向 `settings.dev.toml`（D01）。〔落地：S0 框架与 S0 所需键；public 键 S7〕（Q4；SPEC 19；D01）
11. Settings 按进程拆分子集，每个进程只加载并校验自己需要的字段（D01）。S0 矩阵如下：

    | 进程 | 凭据文件（`*_FILE`） | 启动配置（settings.toml） |
    | --- | --- | --- |
    | api-admin | 管理 DML 角色 DSN、REDIS_URL、MASTER_KEY、ADMIN_PASSWORD_HASH | ADMIN_ORIGINS、SHARE_BASE_URL（R2）、连接池、SSE 参数（D48） |
    | worker | 应用 DML 角色 DSN、REDIS_URL、MASTER_KEY | Worker 并发、连接池（每 child 2+0，见 34） |
    | control | 应用 DML 角色 DSN、REDIS_URL、MASTER_KEY（R1：挂载根密钥） | 连接池（3+0）、部署规模声明 |
    | migrate | DDL 角色 DSN（`frameread_migrate`）、MASTER_KEY | 部署规模声明（D05）、初始 policy_json 来源 |
    | 维护与策略 CLI | 应用 DML 角色 DSN（D09） | 无 |
    | api-public（S7） | PUBLIC_DATABASE_DSN，不挂载根密钥（R1） | SHARE_BASE_URL（R2）；不加载任何 ADMIN_* 项 |

    〔落地：S0 除 api-public 外；api-public 在 S7〕（Q4；D01；R1、R2）
12. 敏感值与连接字符串不得出现在 CLI 输出、日志、错误体或异常文本中。〔落地：S0〕（SPEC 19、20）
13. 根密钥与子密钥派生：根密钥经 HKDF-SHA256 派生，salt 为 installation_id，info 固定为 `frameread/v1/encryption`、`frameread/v1/session-csrf`、`frameread/v1/cursor`、`frameread/v1/share` 四种之一；四种用途全部在 S0 实现，`KeyRing.derive` 只接受这四个用途。四个子密钥均为 32 字节（D03）。派生需要 installation_id，因此进程启动顺序固定为：连库 → 校验 migration head → 读 `instance_state` → 比对 `root_key_check` → 用 `installation_id` 派生子密钥（E7）。〔落地：S0 全部实现〕（Q5；SPEC 19；D03）
14. 四类子密钥的使用方：encryption 供 M05 凭据 AES-256-GCM 使用（AAD 绑定 config ID 与 key ID，SPEC 17.3）；session-csrf 供 M02 CSRF 与登录限流的来源 HMAC（Q35；D18）；cursor 供 M04 签名游标（Q30）；share 供 M15 分享 token（S7）。M01 只提供派生，不实现这些模块的逻辑。〔落地：派生 S0；使用方各自切片〕（Q5、Q30、Q35）
15. `root_key_check = HMAC(根密钥, "frameread/key-check")` 在迁移初始化时写入 `instance_state`。只有挂载根密钥的进程比对：api-admin、worker、control、migrate 与 CLI；api-public 不挂载密钥，不比对（R1）。比对不一致即拒绝启动，比对本身不生成也不修改任何数据。〔落地：S0；api-public 在 S7〕（Q6；SPEC 6.1；R1）
16. 已有数据（`instance_state` 已存在）而根密钥文件缺失或校验不一致时，启动失败；系统不生成新密钥，不覆盖 `root_key_check`。〔落地：S0〕（SPEC 19）
17. `frameread secrets init` 在 secrets 目录中生成（D02）：根密钥（32 字节，以 64 位小写十六进制存放，读取时只去掉末尾换行）、PostgreSQL 各角色密码、Redis 密码，以及由此生成的 DSN 与 Redis URL 文件。`installation_id` 不由 `secrets init` 生成，由 migrate 在空库初始化时生成。管理员密码 hash 不由 `secrets init` 生成，由 M02 的 `frameread admin set-password` 单独写入（E15）。目录内已有任一文件时拒绝执行，不覆盖。secrets 目录加入 gitignore，与 `.env*`、`*.pem`、`*.key` 一样不入库。〔落地：S0〕（Q7；SPEC 19；AGENTS.md；D02）
18. 密钥与 secrets 加载失败的错误信息只说明缺失或格式错误的配置项名，不包含文件内容。〔落地：S0〕（SPEC 19）

### 3.3 迁移与初始化

19. 迁移由 `migrate` one-shot 服务使用 DDL 专用数据库角色（`frameread_migrate`）执行。持 PostgreSQL advisory lock 后执行 Alembic upgrade；lock 的 key 为固定常量，获取最多等待 60s，超时即失败（D04）。成功后在空库初始化 `instance_state` 单例：生成 installation_id 与 instance_epoch，写入 root_key_check 与初始 `policy_json`（只在空库写入，来自 `settings.toml`）。execution 槽行由 migrate 入口在同一 UoW 中、写完策略后调用 M03 的 `sync_execution_slots` 预建；这是入口层组合，不构成 M01 依赖 M03（E7）。〔落地：S0〕（Q7、Q14；SPEC 7.2；D02、D04、D35；E7）
20. 迁移按切片增量追加 revision。S0 初始 revision 只包含 S0 表；同一 revision 内先建表、再补 FK、最后建索引与触发器。未合入 `main` 的 revision 可在切片分支修改或合并；合入后只追加；V1 定稿不 squash；AT-20 旧样本基线取 S7 head。〔落地：S0〕（Q2；SPEC 7.2）
21. 其它服务（api-admin、worker、control）启动时要求数据库 migration head 与代码期望的 head 完全相等，不接受祖先 head；不相等则拒绝写入并报告 not ready，不等待迁移完成（D04）。迁移未完成前不开放业务写入。〔落地：S0〕（Q7；SPEC 7.2、19；D04）
22. 迁移启动时执行连接预算静态比对（U3、D05）：`API 实例数×5 + Worker 并发×2 + control 实例数×3 + 保留 5 ≤ max_connections`，超出则迁移失败。部署规模（各进程实例数、Worker 并发）在 `settings.toml` 中声明；“保留 5”指留给运维的连接数；`max_connections` 用 `SHOW max_connections` 读取。〔落地：S0〕（Q18；SPEC 7；U3；D05）
23. 迁移失败：保持维护态、不自动清库、不自动 downgrade、不启动服务；诊断读取后按备份或兼容版本恢复。〔落地：S0〕（SPEC 19）
24. 所有表（含 `instance_state` 单例、执行槽、Outbox、心跳）一律带通用列：`id uuid`、`created_at`、`updated_at`、`deleted_at`（逻辑删除）、`version bigint NOT NULL DEFAULT 1 CHECK(version>0)`（U2，覆盖 SPEC 6 共同规则）。允许物理删除的只有两张表：`admin_sessions`（过期清理与恢复清空）与 `task_events`（保留期清理）；二者没有业务历史价值（U2）。其余表的“清理”一律为逻辑删除。〔落地：S0 框架；各表由所属模块应用〕（SPEC 6；AGENTS.md；U2）
25. `updated_at` 由通用 BEFORE UPDATE 触发器维护，业务代码不设置该列。〔落地：S0〕（Q9）
26. `version` 由 Repository 条件更新显式递增（`WHERE version = :expected`，SET version = version + 1）；影响行数为 0 即抛 `VERSION_CONFLICT`。tasks 的 `version` 随每次 `state_revision` 变化递增；心跳只更新 `lease_until`，不递增 `version` 与 `state_revision`（D33）。〔落地：S0〕（Q9；SPEC 6；D33）
27. 条件更新或关键写入必须检查影响行数与最终持久状态，不符即视为错误，不静默吞掉。〔落地：S0〕（SPEC 7.2）
28. CHECK、UNIQUE、FK、部分索引与状态取值 CHECK 集中在迁移中维护。`instance_state` 的 `singleton_key` 唯一且为 1。不可变保护触发器只拦截 UPDATE：`task_events` 允许 DELETE，供保留期清理使用；已完成（completed）的 `stage_results` 禁止 UPDATE，代码中不提供其 DELETE 路径（D14、E4）。〔落地：S0〕（SPEC 6、7.2；D14；E4）

### 3.4 事务、UnitOfWork 与连接

29. Repository 只构造 SQLAlchemy 语句与条件更新，不执行、不 commit；由 async 与 sync 两个薄执行器运行。与 SPEC §2“不自行 commit”兼容，SPEC 不改（R4）。〔落地：S0〕（Q3；R4）
30. `AsyncUnitOfWork` 与 `UnitOfWork` 暴露同一组方法：`lock_instance(mode)`、`gate.require(op)`、`commit()`；门禁与锁顺序规则只在这里实现一份。〔落地：S0〕（Q3；map §3 M01）
31. 事务由 Service 拥有 UoW；嵌套 Service 不得 commit 或 rollback 外层事务。〔落地：S0〕（SPEC 2）
32. API 每个请求使用独立 AsyncSession；Worker 在 prefork 子进程初始化后创建同步 Engine 与 Session，heartbeat 线程使用独立 Session；control 每次扫描使用短 Session；不跨 fork 继承连接，不跨协程共享 Session。UoW 提供 `db_now()`，取数据库 `clock_timestamp()`，供 M03 的 lease 判定使用（D14）。〔落地：S0〕（SPEC 7、10.1；D14）
33. `expire_on_commit=False`；响应 DTO 使用显式加载或 selectinload，禁止序列化时触发隐式 lazy load。〔落地：S0〕（SPEC 7）
34. 每进程连接池参数（`pool_size`、`max_overflow`、`pool_timeout`）由 Settings 配置。初始值（SPEC 7，U3 更正）：API 每实例 5+0；control 每实例 3+0；Worker 每个 child 2+0，即主任务与心跳线程各一个。连接获取超时明确失败。〔落地：S0〕（SPEC 7；U3）
35. `run_transaction(fn)`：只对 SQLSTATE `40001`、`40P01` 整体重跑整个短事务。总共最多执行 3 次（含首次）。退避取 50ms×2ⁿ，full jitter，上限 500ms（D06）。重跑时幂等身份不变；`fn` 内不得含外部副作用或外部 I/O。〔落地：S0〕（Q10；SPEC 7；D06）
36. COMMIT 阶段的结果分类（D06）：`commit()` 调用期间出现连接类异常记为 `commit_outcome=unknown`，抛 `CommitOutcomeUnknown`，不重跑；COMMIT 之前出现的异常记为 `rolled_back`。`CommitOutcomeUnknown` 之后由 M03 T1 换新连接按 (scope, key) 查一次（Q21，归 M03）；M01 只定义异常与不重跑规则。具体驱动异常与 unknown/rolled_back 的映射在实现时确定，并由 `tests/` 中的 TCP 代理（测试 12）覆盖三种模式加以证明（E10）。〔落地：S0〕（Q10、Q21；SPEC 4.1；D06）
37. 只有 SQLSTATE `40001`、`40P01` 进入重试，其它错误不重试（Q10）。〔落地：S0〕（Q10）
38. 数据库连接、rollback 与 close 在 finally 或 context manager 中完成。〔落地：S0〕（SPEC 7）

### 3.5 错误、请求标识与日志

39. 错误码以单一全局登记表（domain StrEnum）定义，每个码对应一个 HTTP 状态码与机器类别（D11）。前端类型经 OpenAPI 生成获取，不手写重复定义。S0 登记范围为 SPEC §4.1 表中的全部码，加上 R7 登记的任务错误码（见下）。〔落地：S0〕（Q8；SPEC 4.1；D11；R7）
40. 统一错误体结构固定为：`error.code`、`error.message`、`error.request_id`、`error.task_id`（可空）、`error.action`、`error.retry_after_seconds`（可空）、`error.details`（列表）（SPEC 4.1）。补充约定（D11）：
    - `action` 由 M01 全局登记表按错误码指定；取值词表固定为 `fix_input`、`resolve_same_key`、`retry_later`、`login`、`refresh`、`retry_later_or_report`、`none`（D11、E13）。
    - `retry_after_seconds` 只在 429 与 503 时给出。
    - `details` 每项为 `{field?, code, message}`；422 校验错误逐字段映射。
    - `request_id` 为 UUIDv4。

    〔落地：S0〕（SPEC 4.1；D11）
41. `500 INTERNAL_ERROR` 使用 `action=retry_later_or_report`；响应不返回异常内容、SQL、内部路径、上游 body、原始 URL 或栈。内部栈经脱敏后只进入内部日志流，不单独落盘（D12）。〔落地：S0〕（Q8；SPEC 4.1、20；D12）
42. 请求体 Schema 基类统一 `extra='forbid'`、严格枚举与整数类型；校验失败统一映射为 `422 INVALID_INPUT` 的错误体（按 40 的 details 规则），不直接暴露框架默认校验结构。〔落地：S0〕（SPEC 4.1、5）
43. `request_id` 由中间件为每个请求服务端生成 UUIDv4；写入 `X-Request-ID` 响应头与所有错误体；不采纳客户端传入的同名头。〔落地：S0〕（Q11；SPEC 20；D11）
44. structlog 以 JSON 输出，使用字段 allowlist processor；allowlist 为 SPEC 20 列出的字段（timestamp、level、event、request_id、task_id、attempt_id、fence、stage、provider_call_id、article_version_id、worker_id、epoch、error_code、duration_ms、queue_wait_ms、resource_wait_ms、usage_status）。越界字段在所有环境中都直接抛错（D12）。〔落地：S0〕（Q11；SPEC 20；D12）
45. 默认不记录请求 body、SQL 参数、上游 header/body、URL 全值；Prompt、字幕、问题原文、外部正文不进入普通日志。〔落地：S0 框架；各模块遵守〕（SPEC 17.3、20）
46. 日志轮转使用 Docker `json-file` 驱动，max-size 10m、max-file 5（D12）。〔落地：S0〕（Q11；D12）
47. Celery 消息与外部 header 只携带必要关联 ID，不携带 session 或密钥。〔落地：S0〕（SPEC 20）

**任务错误码小节（R7）**：`PIPELINE_NOT_AVAILABLE`（S0 骨架专用，S1 删除）与 `DEADLINE_EXCEEDED` 登记在同一全局表中，但只出现在 `TaskSnapshot.error.code`，不作为 HTTP 状态；SPEC §4.1 的 409 行已补 `CURSOR_RESET_REQUIRED`。

### 3.6 健康

48. 健康接口为 `/health/live` 与 `/health/ready`，仅进程内网可达，不经 gateway 暴露（R3）。live 只证明进程存活；ready 返回 `ready/degraded/unavailable/unknown` 与依赖分项。HTTP 状态：ready 与 degraded 返回 200，unavailable 与 unknown 返回 503；响应结构为 `{status, checks:[{name, status, observed_at, detail?}]}`（D13）。Worker 与 control 没有 HTTP 端口，live 由 `frameread health live` CLI 检查 tmpfs 中心跳文件的修改时间（D13、E6）。管理端 `GET /health` 为需管理员会话的只读汇总，与 `/overview` 一起在 S11 交付（R3）。〔落地：S0〕（Q12；SPEC 20；R3；D13）
49. `register_probe(name, fn, severity)`：各依赖探针由所属模块注册，M01 负责聚合。severity 取 `critical` 或 `degraded`；探针超时 2s，结果缓存 5s（D13）。采集失败或超时的分项值为 `null` 且状态为 `unknown`，不得记为 0。〔落地：S0〕（Q12；SPEC 20；D13）
50. S0 状态判定：PostgreSQL 不可用、migration head 不符、根密钥校验失败为 `unavailable`（severity critical），管理写被拒绝；Redis 不可用为 `degraded`（Redis 探针由 M01 注册，D41）；Worker 集群是否就绪由 M03 注册的 `worker_heartbeats` 探针在 api-admin ready 中报告，心跳过期为 `degraded`（E6）。〔落地：S0〕（Q12；SPEC 20；D41；E6）
51. 健康检查不调用付费模型、不发送付费探测、不访问外部服务。〔落地：S0〕（SPEC 19、20；AT-21）
52. Compose 健康检查只使用 `live`。〔落地：S0〕（Q12）
53. 服务不依赖 `depends_on` 或固定 sleep 判断可用性；启动后主动重连数据库，并校验 migration head。〔落地：S0〕（SPEC 19）

### 3.7 运行策略与维护 CLI

54. `policy_json` 是运行时资源策略的唯一来源；`settings.toml` 中的策略只在空库初始化时写入。只有资源策略进入 `policy_json`；ADMIN_ORIGINS 与 SHARE_BASE_URL 是进程启动配置，不进入（R2）。〔落地：S0〕（Q14；SPEC 6.1、19；R2）
55. `frameread policy set` 在实例行锁内修改 `policy_json`，并递增 `config_revision`；非法值拒绝写入，不改变已有值。允许在任意 maintenance 状态下执行（D07）。写入后若执行槽容量变化，入口在同一 UoW 中调用 M03 的 `sync_execution_slots`（E7）。CLI 退出码与输出见 59。〔落地：S0〕（Q14、Q16；SPEC 19；D07）
56. 运行中的 `settings.toml` 与 `policy_json` 不一致时只记 warning，不改变运行中的值。warning 比对全部策略键（D08）。〔落地：S0〕（Q14；SPEC 19；D08）
57. `frameread maintenance set normal|draining|frozen` 在实例行锁内修改 `maintenance_mode`；切换规则见 5。`frameread` Typer CLI 统一承载 `secrets init`、`maintenance set`、`policy set`、`openapi export` 与 M02 的 `admin set-password`，共用同一 sync UnitOfWork 与门禁（Q16）。〔落地：S0；admin set-password 逻辑归 M02〕（Q15、Q16）
58. S0 策略键（D08、E11）：每个池的执行槽与等待位分别为 `pools.<pool>.execution_slots` 与 `pools.<pool>.waiting_slots`，pool 取 `video`、`qa`、`utility`，video 默认 2 与 4；video 总期限 2h；lease 60s；心跳 10s；dispatcher 批量 50；投递重试预算 10；dispatch generation 上限 5；关键事件保留 7 天（SPEC §18.2，默认值入 `policy_json`，清理归 S8）。其余键采用 SPEC §8.2、§9.3 的值。策略值用 Pydantic 校验。〔落地：S0 写入；清理 S8〕（Q27；SPEC 18.2；D08）
59. CLI 约定（D09）：维护与策略 CLI 使用应用 DML 角色；退出码 0 为成功，1 为业务拒绝，2 为用法错误；输出给人读；错误信息带 `request_id`。〔落地：S0〕（Q16；D09）

### 3.8 执行栅栏值类型与依赖边界

60. `FencedTask` 值类型放在 M01（D2a）。M07 只接收调用方传入的 `FencedTask`，不调用 M03。字段为 `task_id`、`instance_epoch`、`attempt_no`、`fence`、`lease_token`（D10）。〔落地：S0 定义；S1 M07 使用〕（map §2 D2a；SPEC 10.1；D10）
61. 栅栏判定逻辑（epoch 等于当前值、fence 与 lease_token 一致、`lease_until > clock_timestamp()`）归 M03 实现；lease 判定只使用数据库时间，不使用工作进程本地时钟（SPEC 10.1）。M01 不实现该判定。〔落地：S0 由 M03 使用〕（SPEC 10.1）
62. M01 位于依赖最底层，不 import 任何业务模块；依赖只指向 M01，无循环（map §2、§4.1）。migrate 与 `policy set` 入口对 M03 `sync_execution_slots` 的调用属于入口层组合，不构成 M01 依赖 M03（E7；map §4.2）。〔落地：S0〕

### 3.9 X1 交付工程（S0 部分）

63. Compose S0 服务为 `gateway`、`api-admin`、`worker`、`control`、`migrate`、`postgres`、`redis`（Q13）。`egress-proxy` 归 M06 于 S1 加入，`api-public` 归 S7 加入（map §7；SPEC 19 完整列表）。〔落地：S0〕
64. S0 起所有运行服务：非 root 用户、只读根文件系统、精确列出的可写挂载、CPU/内存/pids 限制、不挂载 Docker socket（Q13；SPEC 19）。具体数值在首个 Ticket 中给出，并通过 Compose 实测确认（D15）。〔落地：S0〕
65. 镜像：后端镜像与前端构建镜像各一份（SPEC 2 所列 Dockerfile），基础镜像为 `python:3.12-slim` 系列（D15）。gateway 使用固定 digest 的 nginx 镜像（Q37）。首个 Ticket 锁定具体 patch 版本与镜像 digest，写入锁文件，禁止 floating latest（Q13；SPEC 19）。S0 的 Worker 镜像不安装 FFmpeg 与 yt-dlp，S1 再加入（D15）。〔落地：S0〕
66. 依赖锁定：后端使用 `uv` 与 `uv.lock`（Python 3.12，FastAPI、Pydantic v2、SQLAlchemy 2.0、Alembic、psycopg 3）；前端使用 `pnpm` 与 lockfile；Celery 5.6 在 S0 Worker 中加入；LangGraph 在 S1 加入（SPEC 2、19）。〔落地：S0〕
67. 启动顺序（S0 契约）：`secrets init` → postgres 初始化脚本创建 `frameread_migrate` 与 `frameread_app` 两个角色 → `migrate` one-shot → `frameread admin set-password` → 其余服务（E15）。postgres 初始化脚本以只读方式挂载，从 secret 文件读取角色密码（D02）。public role 归 S7/M15（Q7；SPEC 19）。〔落地：S0〕
68. Compose 命令契约：`docker compose run --rm migrate`、`up -d`、`ps`、`logs --tail=100`、`restart`，均针对 Compose 文件执行（SPEC 19；文件位置见 map §9）。〔落地：S0 可执行；S0 子集验收见测试 19 与 R10；完整部署验收 S8〕（SPEC 19、21.3；R10）
69. OpenAPI 导出：`frameread openapi export --app admin` 生成 admin 的 OpenAPI JSON，输出到前端生成目录，再由 `openapi-typescript` 生成类型文件；两者提交仓库；CI 重新生成并 diff；前端运行时只使用 `fetch`（Q17）。public 快照归 S7（SPEC 5）。运行时关闭默认 `/docs`、`/redoc` 与公开 `/openapi.json` 由 M02 在装配 admin app 时完成；导出 CLI 归 M01（D16）。〔落地：S0〕（SPEC 5；D16）
70. CI 平台为 GitHub Actions（D15）。S0 阶段（SPEC 21.3 顺序，取 S0 已有对象的子集）：锁一致性检查 → Ruff、mypy、前端 typecheck → 单元与 API 测试 → 空库 Alembic 迁移 → 集成测试（真实 PostgreSQL/Redis，独立 Worker 与 control）→ 前端 build 与镜像构建 → Playwright 受控 E2E（S0 页面随 M04/M12 交付）。`pytest` 的 `integration`、`faults` markers 在 S0 创建。〔落地：S0；E2E 随 M04 页面〕（SPEC 21.3；Q28；D15）
71. CI 检查项：OpenAPI 与前端生成类型 diff 为空（Q17）；生产配置中无非 8080 的 http origin（Q38）。〔落地：S0〕
72. 部署文档放在 `deploy/README.md`（D15）。S0 只写当前启动所需的部分（secrets、启动顺序、Compose 命令）；完整部署文档 S8。〔落地：S0 部分；S8 完整〕（map §3 X1、§7；AGENTS.md 文档规则；D15）

## 测试决定

测试接缝沿用批次 A 约定：接缝 1 HTTP（真实 api-admin，经 httpx ASGI 或 Compose 中的 gateway，后端为真实 PostgreSQL 与 Redis）；接缝 2 进程（独立运行的 api-admin、worker、control、migrate，不用进程内替身）；接缝 3 CLI（`frameread` 命令，断言退出码、输出与数据库状态）；接缝 4 纯函数（KeyRing 派生、allowlist、错误码映射、重试分类）；接缝 5 浏览器不用于 M01 的专属断言，页面中错误与 request ID 的展示由 M02/M04 负责。

AT-22 的 S0 子集（R10）：Compose 按文档启动，经页面提交、查询、取消；CI 在真实 PostgreSQL/Redis 与独立 Worker 上跑 S0 核心链。重启与完整部署在 S8 验收。

S0 必测场景（每项列出接缝与对应 AT 或 PRD 条目）：

1. 空库迁移成功：migrate 后 Alembic head 正确，`instance_state` 单例存在且 `singleton_key` 违反时插入失败，初始 `policy_json` 来自 `settings.toml`，installation_id 与 instance_epoch 存在；重复执行 migrate 结果不变（接缝 2、3；AT-20 空库迁移）。
2. 迁移失败：故障 revision 导致迁移失败后，服务不启动，数据库不被清空，已有数据与 head 保持失败前状态（接缝 2；AT-20 迁移失败）。故障注入只用外部方式（Q25、E9）：测试把迁移目录复制到临时目录，追加一个会失败的 revision，再对它运行 Alembic；生产代码与配置都不改。
3. 迁移并发：两个 migrate 同时执行，只有一个真正修改 schema，另一个等待（最多 60s）或失败，最终 schema 一致（接缝 2；AT-20 并发约束；D04）。
4. 连接预算：将 PostgreSQL `max_connections` 设置为低于公式结果时，migrate 失败且不改变 schema（接缝 2；AT-20 规模约束；U3）。
5. 版本不兼容：migrate head 与服务期望不一致（含祖先 head）时，api-admin、worker、control 拒绝写入并报告 not ready（接缝 2；AT-20；D04）。
6. 根密钥：缺失、为空、与 `root_key_check` 不符时，对已有数据的启动失败，不生成新密钥；api-public 不参与比对（接缝 2；AT-21 与 AT-23 的密钥前置；R1）。
7. `secrets init` 再次执行被拒绝，已有文件内容不变（接缝 3；D02）。
8. KeyRing 表驱动单测：同一根密钥与 installation_id 派生稳定；四种用途输出互不相同且均为 32 字节；installation_id 不同输出不同；未知用途被拒绝（接缝 4；D03）。
9. 统一错误体（AT-19）：未知字段返回 `422 INVALID_INPUT`（details 逐字段），版本冲突返回 `409 VERSION_CONFLICT`，注入未预期异常返回 `500 INTERNAL_ERROR`；三者 `request_id` 与 `X-Request-ID` 一致且为 UUIDv4，500 体不含 SQL、路径或栈，数据库状态不变（接缝 1；D11）。
10. 维护门禁（AT-19；Q15）：`draining`、`frozen`、`review_required` 下新受理与 Claim 类写入返回 `503 MAINTENANCE`；幂等找回与只读接口仍返回原结果（接缝 1、3；T1 入口在 M03 实现后执行）。frozen 下登录与退出返回 `503 MAINTENANCE`（E5、D20）；review_required 下允许登录（E13）。
11. `draining` 收敛例外：已获准调用的回执与阶段检查点在 draining 下仍可写入（接缝 1；此用例在 M03/M08 切片补充，M01 只提供门禁判定）。
12. `run_transaction` 与 COMMIT 结果（Q10、U1、D06）：外部制造 `40P01` 时整体重跑成功且总执行不超过 3 次；非重试 SQLSTATE 不重跑。COMMIT 结果由 `tests/` 中的 PG 线协议 TCP 代理夹具制造（API 连接经该代理），三种模式（E8）：(a) 丢弃 `COMMIT` 并断开：结果 unknown，按 (scope, key) 确认查不到，返回 `503 ADMISSION_UNCONFIRMED`；(b) 转发 `COMMIT` 后、回包前断开：结果 unknown，确认时能查到，返回 `202`（replayed）；(c) `COMMIT` 之前断开：结果 rolled_back，返回 `503 DEPENDENCY_UNAVAILABLE`，不留下任何记录。每种 unknown 模式下 `CommitOutcomeUnknown` 只抛出一次，不重跑。生产代码中无开关（接缝 1、4；U1；E10）。
13. `updated_at` 触发器与 `version` 条件更新：更新后 `updated_at` 前进；调用方设置的 `updated_at` 被忽略或覆盖；`version` 不匹配时返回 `VERSION_CONFLICT` 且行未变（接缝 1；D33）。
14. 日志 allowlist（AT-21；Q11；D12）：允许字段通过；越界字段抛错；请求 body、URL 全值与 SQL 参数不出现在日志中（接缝 4、接缝 2 读取日志文件）。
15. 健康（AT-21；D13、D41）：停止 PostgreSQL 后 live 仍通过，ready 为 `unavailable` 且返回 503，管理写返回 `503 DEPENDENCY_UNAVAILABLE`；停止 Redis 后 ready 为 `degraded` 且返回 200；停止 Worker 后 api-admin ready 中 `worker_heartbeats` 分项为 `degraded`（接缝 2；E6）。
16. 采集失败（AT-21；D13）：探针抛错或超过 2s 时分项为 `null` 与 `unknown`，不得为 0（接缝 1、4）。
17. 健康零收费（AT-21）：ready 与 live 调用期间没有出站网络请求（接缝 2，网络层观察）。
18. CLI（Q16；D09）：`maintenance set`、`policy set` 的成功、拒绝非法值、退出码（0/1/2）与输出符合约定，数据库状态与输出一致（接缝 3）。
19. Compose 结构检查（AT-22 S0 子集，R10）：各运行服务为非 root、只读根文件系统、无 Docker socket 挂载，资源限制存在（接缝 2，结构断言）；`up -d` 后各服务 live 为健康；按文档启动后经页面提交、查询、取消一个受控视频任务（接缝 2、5）。
20. CI 检查（AT-22 S0 子集）：锁文件一致性；OpenAPI 导出与提交文件 diff 为空；前端生成类型 diff 为空；生产配置无非 8080 的 http origin（接缝 2、3）。

测试规则：不在生产代码中加入测试开关；不 skip、不放松断言；故障手段只用外部方式（Q25）；测试夹具与 kill 或 barrier 工具只放在 `tests/` 中。测试隔离（D38）：每个测试会话从已迁移的模板库建立独立库；每个测试结束后 TRUNCATE 业务表，并把 `instance_state` 重置为 normal。期限类测试由夹具通过 `frameread policy set` 设置短期限，不依赖测试开关（D37）。

## 不在范围内

- 业务表与其迁移（分别归 M02 至 M15）。
- 各依赖探针的实现：Redis 探针由 M01 注册（D41）；Worker 心跳、存储、Provider 等由所属模块注册。
- `restore_state` 的正式写入、备份恢复流程、epoch 变更、`clear_sessions_for_restore` 等恢复钩子（M17、S10）。
- public app、public DB role、`public_instance_gate` 视图与 `acquire_share_asset_lease`（M15、S7）。
- `egress-proxy` 与出口策略（M06、S1）。
- 探测与系统内容缓存（M18、S12）。
- 关键事件与运行数据的保留清理任务（S8；S0 只写入保留天数）。
- 运行概览聚合、管理端 `GET /health` 汇总与运行手册（M16、S11）。
- 实际模型调用、可控 Provider 与调用账（M08）。
- SSE、快照与游标协议（M04）。
- 完整部署文档、备份与恢复演练（S8、S10）。

## 补充说明

### 与其他模块的接口约定

- 对 M02：提供 `KeyRing.derive("session-csrf")`；M02 的 `require_admin`、`clear_sessions_for_restore` 调用 M01 的 UoW 与门禁，登录与退出按 `gate.require(session)` 判定（D20、E5）；管理员密码 hash 文件路径由 Settings 提供；M02 在装配 admin app 时关闭 docs 与 openapi 路由（D16）。
- 对 M03：提供 `UnitOfWork`（`lock_instance`、`gate.require`、`commit`、`db_now`）、`run_transaction`、`CommitOutcomeUnknown`、`FencedTask`、`AppError` 与错误码、`register_probe`；M03 注册 `worker_heartbeats` 探针（E6），并实现 T1 中对 `CommitOutcomeUnknown` 的一次性按键查询（Q21）；M03 的 `sync_execution_slots` 由 migrate 与 `policy set` 入口调用（E7）。
- 对 M04：提供 `KeyRing.derive("cursor")`；快照与 SSE 的错误码由 M01 登记。
- 对 M05：提供 `KeyRing.derive("encryption")`；AES-GCM 的 AAD 规则归 M05（SPEC 17.3）。
- 对 M07：只接收 `FencedTask`，不调用 M03；`instance_state` 的门禁由 M01 提供。
- 对 M08：提供 `FencedTask` 与 `CommitOutcomeUnknown`（T4/T5 的事务由 M08 使用 M01 的 UoW）。
- 对 M15：提供 `KeyRing.derive("share")`；public role 与视图归 M15。
- 对 M16：提供 health 分项与版本信息的读取；概览聚合归 M16。
- 对 M17：恢复字段的写入经 M01 接口，S0 不实现。

### 第二轮裁决的跨模块约定

- 入口层组合（E7）：migrate 与 `policy set` 入口调用 M03 的 `sync_execution_slots`，M01 不依赖 M03（map §4.2）。
- 启动顺序（E7）：连库 → 校验 head → 读 `instance_state` → 比对 `root_key_check` → 派生子密钥。
- 不可变触发器只拦 UPDATE；`task_events` 允许 DELETE（E4）。
- 门禁 session 类别：只在 frozen 下禁止，review_required 下允许（E5、E13）。

### 待确认

无未解决项。原待确认 1～5 已由 E5（cancel_request）、E9（迁移失败手段）、E10（驱动异常映射在实现时确定并由 E8 代理测试覆盖）、E4（触发器只拦 UPDATE）、E7（入口组合）裁决并写入正文。
