# M02 管理访问与入口隔离 模块 SPEC

Status: ready-for-agent
日期：2026-11-15。依据：[Grill 批次 A](../frameread-v1/grill-batch-a.md) 的 Q34～Q40（并引用 Q5、Q7、Q11、Q13、Q16、Q28、Q33）、[批次 A 待确认裁决](../frameread-v1/spec-resolutions-batch-a.md)（U2、R2、R11、R12、D11、D16、D17～D26，以及 D46 中登录路由）、[模块地图 §3 M02](../frameread-v1/map.md)、[SPEC_V1](../../docs/prototype/SPEC_V1.md)、[PRD](../../docs/prototype/PRD.md)。

## 问题陈述

FrameRead 是单部署者的个人实例，管理入口只允许持有单一管理员凭据的部署者读写任务、模型配置、成果与运行状态。分享访问者、任意公网请求、跨站页面和伪造的代理转发头都不能越过这一边界（PRD REQ-10）。

若每个路由或 Service 各自判断登录、CSRF 或 Origin，很容易漏掉其中一项；密码入口又是唯一的凭据入口，需要限制暴力尝试，同时在 Redis 故障时不能无界接受密码。管理 app 与未来的分享 app 还需要在路由、凭据、进程与网关层面隔离，且公开入口不能因为代码复用而意外挂载管理 router（SPEC §1、§17.1）。

## 解决方案

- **凭据**：部署者通过 CLI 设置 Argon2id hash，写入 Docker secret；api-admin 启动时读取 hash 并计算 `credential_generation`。轮换密码后重启 api-admin，使既有会话失效。
- **会话**：`POST /session` 验证密码后在 PG 创建 `admin_sessions`，只存 token 与 CSRF 的 hash，12 小时绝对过期，无空闲超时。Cookie 为 HttpOnly、SameSite=Strict，路径限定在管理 API。
- **写防护**：所有管理路由统一经 `require_admin`，按 Host → Origin → 会话 → CSRF 的顺序校验；Host 对全部管理请求做精确校验，Origin 对写请求做精确校验。
- **登录限流**：Redis 只统计失败的密码校验，单来源与全局两级固定窗口计数；超限 `429`，Redis 不可用 `503`。
- **入口隔离**：admin app 与 public app 分别装配；gateway 按监听与路径分流，只信任固定 gateway IP 的转发信息。S0 只交付 admin app 与 `127.0.0.1:8080`，public app 与双入口负测在 S7。
- **前端外壳**：启动探测会话，`401` 跳登录页并在登录后回到原页面；CSRF token 只存内存；`403 CSRF_REJECTED` 不自动重放写请求。

## 用户故事

### 凭据

1. 作为部署者，我希望用 CLI 在 stdin 中连续输入两次密码来设置管理员凭据，以便密码不出现在命令行参数、shell 历史或日志中。
2. 作为部署者，我希望两次输入不一致或输入为空时 CLI 失败且不改动现有 secret，以便不会因误操作留下不可用的凭据。
3. 作为部署者，我希望安装后不存在默认密码、注册接口或用户记录，以便实例没有可被猜中的初始口令。
4. 作为部署者，我希望轮换密码并重启 api-admin 后，旧会话全部失效，以便丢失的设备或旧浏览器的会话不能继续使用。
5. 作为运维中的部署者，我希望 hash secret 缺失或为空时 api-admin 启动失败并给出可定位的错误，以便服务不会在无凭据状态下对外提供管理接口。
6. 作为部署者，我希望只有 api-admin 挂载管理员 hash secret，以便 worker、control 与 public 进程即使被攻破也拿不到管理员凭据。

### 登录与会话

7. 作为部署者，我希望输入正确密码后获得 HttpOnly 会话 cookie 与 CSRF token，以便页面能完成管理操作，而脚本无法读取 cookie。
8. 作为部署者，我希望密码错误时只得到统一的 `401` 错误体，以便失败响应不泄露更多信息。
9. 作为部署者，我希望会话在创建后 12 小时绝对过期且不因活动延长，以便会话生命周期可预期。
10. 作为部署者，我希望持续打开的管理页面不会让每个请求都写数据库，以便轮询不放大写入量（`last_seen_at` 至多 5 分钟写一次）。
11. 作为部署者，我希望退出后 cookie 被清除，且原会话 token 立即返回 `401`，以便在共享电脑上退出是真实生效的。
12. 作为部署者，我希望数据库不可用时管理请求返回 `503` 而不是 `401`，以便我能区分依赖故障与凭据问题。
13. 作为部署者，我希望 Redis 不可用时登录返回 `503`，而已登录的会话仍可继续使用，以便缓存或协调组件故障不打断已有操作。
14. 作为部署者，我希望同一来源连续 5 次密码错误后被 `429` 限制并看到 `Retry-After`，以便暴力尝试被限速。
15. 作为部署者，我希望全局 15 分钟内 30 次失败后所有来源都被限速，以便伪造或分散的来源不能绕过单来源限制。
16. 作为部署者，我希望一次成功登录不清除失败计数，以便攻击者不能借由一次正确密码重置限流。
17. 作为部署者，我希望超限期间即使输入正确密码也得到 `429`，以便限流不能被正确密码绕过。
18. 作为部署者，我希望登录失败、限流与依赖不可用时页面显示可理解的原因与 request ID，以便排障时能在日志中定位。
19. 作为部署者，我希望在维护模式 `frozen` 下登录与退出都返回 `503 MAINTENANCE`，以便冻结期间不产生新的管理会话状态变化。

### 写防护与入口

20. 作为部署者，我希望来自其他站点或其他端口页面的管理写请求因 Origin 或 CSRF 不符被拒绝，以便浏览器自动携带 cookie 时也不能代为执行管理操作。
21. 作为分享访问者，我希望持有分享 token 也无法访问任何 `/api/v1/admin/` 路径，以便分享权限不会扩大为管理权限。
22. 作为部署者，我希望伪造的 `X-Forwarded-For`、`X-Forwarded-Host`、`X-Forwarded-Proto` 不改变 Origin 判定、授权结果或限流来源，以便代理头只影响展示与日志。
23. 作为部署者，我希望 Host 不在精确列表中的请求被拒绝，以便 DNS rebinding 与错误域名访问无效。
24. 作为运维中的部署者，我希望 S0 只在宿主 `127.0.0.1:8080` 暴露，且 api-admin 没有宿主端口映射，以便默认不能从局域网访问管理页面。
25. 作为运维中的部署者，我希望 `/docs`、`/redoc`、`openapi.json` 与健康端点不经 gateway 暴露，以便接口面最小化。
26. 作为后续模块开发者（Agent），我希望管理路由只能通过 `require_admin` 挂载，且写请求自动执行 CSRF 与 Origin 校验，以便新增接口不会遗漏鉴权。
27. 作为后续模块开发者（Agent），我希望 OpenAPI 可直接从 admin app 对象通过 CLI 导出，而无需在服务上开放 `openapi.json`，以便 CI 生成前端类型且不扩大暴露面。
28. 作为后续模块开发者（Agent），我希望 `require_admin` 只向业务模块提供会话标识和校验结果，而不暴露 token 或 CSRF 明文，以便业务代码不接触凭据。
29. 作为分享访问者，我希望公开入口在 S7 上线时不加载管理 router、不使用管理会话依赖、并关闭 docs，以便公开入口不存在任何管理能力。

### 前端外壳

30. 作为部署者，我希望打开管理页面时自动探测会话，过期则跳到登录页，登录后回到原页面，以便不丢失当前的操作位置。
31. 作为部署者，我希望 CSRF token 只存在页面内存中，刷新页面即重新获取，以便它不会进入 localStorage 或 URL。
32. 作为部署者，我希望收到 `403 CSRF_REJECTED` 时页面重新获取会话并提示我刷新，而不是自动重放写请求，以便任务或修改不会被重复提交。
33. 作为部署者，我希望收到 `403 ORIGIN_REJECTED` 时页面提示从管理入口地址访问，而不是自动重试，以便错误入口不会被反复请求。
34. 作为部署者，我希望登录页只有一个密码输入框，以便界面不出现账号、注册或找回的概念。

### 恢复、清理与可观测

35. 作为运维中的部署者，我希望恢复之后所有管理会话被物理清空、必须重新登录，以便恢复出的实例不沿用旧会话（S10 启用）。
36. 作为运维中的部署者，我希望 control 每天清理过期超过 1 天的会话行，以便会话表不会无限增长。
37. 作为运维中的部署者，我希望日志只包含 allowlist 字段（如 request ID、事件、epoch、错误码、耗时），不包含密码、token、cookie、CSRF 或来源 IP 明文，以便日志可以安全地用于排障。
38. 作为运维中的部署者，我希望 Compose 的存活检查不依赖登录且只在内网可达，以便健康检查不需要凭据也不会暴露给公开入口。
39. 作为部署者，我希望系统中没有账号、角色、注册、找回密码或会话列表界面，以便实现与 PRD 的单凭据边界一致。

## 实现决定

### 管理员凭据（Q34、D17）

- CLI `frameread admin set-password` 从 stdin 连续读取两次，不一致或为空则失败且不改动现有 secret。[S0]
- 密码 hash 使用 `argon2-cffi` 默认参数（Argon2id），存为 Docker secret `admin_password_hash`。该 secret 不由 `secrets init` 生成，由 `admin set-password` 单独负责（E15）。[S0]
- `set-password` 写临时文件后原子替换；目标已存在时必须加 `--force`，否则失败。[S0]
- `set-password` 只写 secret，不写数据库；新 hash 在 api-admin 重启后生效。[S0]
- api-admin 启动顺序遵循 E7：连库 → 校验 head → 读 `instance_state` → 比对 `root_key_check` → 用 `installation_id` 派生子密钥 → 读取 `admin_password_hash`。
- `credential_generation` = hash secret 文件字节的 SHA-256 取前 16 个字符（十六进制小写），api-admin 启动时计算并常驻进程内存；会话的 `credential_generation` 与之不一致即无效。[S0]
- hash secret 缺失或为空时 api-admin 启动失败（M01 的 fail-fast 规则）。[S0]
- 只有 api-admin 挂载 `admin_password_hash`；worker、control 与 public 进程不挂载。[S0]
- 同一 API 进程最多同时进行 2 个 Argon2 校验，超出部分排队，排队时间计入请求超时。[S0]

### 登录与会话（Q36、D20、D22、D23、D24，SPEC §17.1）

- `POST /session` 请求体为 `{password}`，成功时返回 `201`，响应体为 `{csrf_token, expires_at}`，并设置会话 cookie。[S0]
- `POST /session` 的处理顺序：Host → Origin → JSON Content-Type → 登录限流预检 → Argon2 密码校验 → 创建会话。[S0]
- session token 为 32 字节 CSPRNG 生成；数据库只保存 `token_hash`（SHA-256），明文只出现在 cookie 与登录响应中。[S0]
- `admin_sessions` 带 M01 统一的四个通用列（`created_at`、`updated_at`、`deleted_at`、`version`）；`deleted_at` 用于退出，过期与恢复清空走物理删除（见例外说明）。[S0]
- Cookie `frameread_admin` 设置 HttpOnly、SameSite=Strict、Path=`/api/v1/admin`；HTTPS 管理 Origin 时设置 Secure，loopback HTTP 显式不设置 Secure。[S0]
- `expires_at` = 创建时间 + 12 小时，没有空闲超时。[S0]
- `last_seen_at` 仅在距上次写入超过 5 分钟时更新。[S0]
- 会话有效的条件：`token_hash` 命中、`deleted_at` 为空、未过 `expires_at`、`credential_generation` 等于当前进程值；任一不满足返回 `401 ADMIN_REQUIRED`。[S0]
- `DELETE /session` 将会话置 `deleted_at`，清除 cookie，返回 `204`；无有效会话时返回 `401`。[S0]
- 登录与退出调用 `gate.require(session)`（E5，SPEC §7.1）：`session` 类别只在 `frozen` 下禁止，此时 `POST /session` 与 `DELETE /session` 返回 `503 MAINTENANCE`；`normal`、`draining`、`review_required` 下允许登录与退出。[S0]
- 会话校验依赖 PG：数据库不可用时返回 `503 DEPENDENCY_UNAVAILABLE`，不以 cookie 存在或内存缓存放行。[S0]
- control 每日物理删除 `expires_at` 早于当前时间超过 1 天的会话行，包括已退出（已置 `deleted_at`）的行。[S0]
- `clear_sessions_for_restore(uow)` 由 M02 提供，供 M17 在恢复事务中调用；它物理清空全部 `admin_sessions`。接口在 S0 定义，恢复场景在 S10 启用。[S10]

### CSRF、Origin 与 Host（Q38、D21，SPEC §17.1）

- `require_admin` 的检查顺序固定为 Host → Origin（仅写请求）→ 会话 → CSRF。未登录的写请求若 Origin 不合法，返回 `403 ORIGIN_REJECTED`，而非 `401`。[S0]
- 所有管理请求的 Host 必须与 `ADMIN_ORIGINS` 中某一项的主机与端口精确一致，不符返回 `403 ORIGIN_REJECTED`。[S0]
- 写方法（POST、PATCH、DELETE）缺少 Origin，或 Origin 不在 `ADMIN_ORIGINS` 精确列表中，一律返回 `403 ORIGIN_REJECTED`。[S0]
- 写方法额外校验 `X-CSRF-Token`，与会话派生值比较，不符或缺失返回 `403 CSRF_REJECTED`。[S0]
- CSRF token = HMAC(session-csrf 子 key, session token)；数据库只保存其 hash，`GET /session` 返回同一 token。[S0]
- `X-Forwarded-Host` 与 `X-Forwarded-Proto` 不参与 Origin 与 Host 的推导。[S0]
- `ADMIN_ORIGINS` 为进程启动配置，是 `settings.toml` 中的非敏感项，不进入 `policy_json`（R2）。默认值为 `http://127.0.0.1:8080`、`http://localhost:8080`；`settings.dev.toml` 额外加入 `http://localhost:5173`。[S0]
- 配置校验：非 loopback 的管理 Origin 只允许 `https`（SPEC §17.1）；CI 检查生产配置中除 8080 端口外不存在 `http` Origin（Q38）。[S0]
- CORS 默认关闭，管理 app 不返回任何跨域允许头。[S0]

### 登录限流（Q35、D18，SPEC §8）

- 只统计密码校验失败；JSON、Content-Type、Origin、Host 校验失败不计入。成功不清除计数。[S0]
- 预检只读（E13），在密码校验之前执行；超限时即使密码正确也不进入校验，直接返回 `429`。[S0]
- 失败路径由 Lua 脚本原子地检查并递增计数（E13），首次失败时设置 TTL；窗口为固定窗口 15 分钟。[S0]
- 有界超额（E13）：预检与失败记录之间，在途的失败请求数最多等于每个进程的 Argon2 并发上限（2）。超额上界写入测试 22 的断言，不做预检与排队的合并原子化。[S0]
- 来源键 = HMAC(session-csrf 子 key, 带用途前缀的 gateway 转发客户端 IP)。用途前缀用于与 CSRF 派生做域分隔。Redis 键为 `fr:{epoch}:login:{source_hash}`；来源明文不写入 Redis 和日志。[S0]
- 全局键为 `fr:{epoch}:login:global`（R12）。单来源阈值为 15 分钟内 5 次失败，全局阈值为 15 分钟内 30 次失败。[S0]
- 超限返回 `429 RATE_LIMITED`，同时设置 `Retry-After` 响应头与 `retry_after_seconds`。[S0]
- Redis 不可用导致限流无法判定时返回 `503 DEPENDENCY_UNAVAILABLE`，不无界接受密码尝试（SPEC §8）。Redis 健康判定由 M01 的 Redis 探针统一负责（D24）。[S0]
- 计数键带 epoch 前缀，恢复换代后计数自然失效（SPEC §8）。[S0]

### 网关与应用装配（Q37、Q40、D16、D19、R3，SPEC §19、§20）

- gateway 使用 digest 固定的 nginx 镜像（digest 由首个 Ticket 锁定，Q13）；S0 只发布 `127.0.0.1:8080`。[S0]
- gateway 直接服务 `/manage/` 前端静态构建，把 `/api/v1/admin/` 反代到 api-admin 的内网端口；其他路径返回 `404`，不代理任何 public 路径。[S0]
- gateway 与 api-admin 位于固定子网，gateway 使用固定 IP；uvicorn 的转发信任列表只包含该 IP。[S0]
- gateway 用 `$remote_addr` 覆盖（而不是追加到）外部请求携带的 `X-Forwarded-For`；转发头只用于限流来源与日志，不用于授权。[S0]
- 默认只在 loopback 发布时，来源地址可能退化为 Docker 网桥地址，此时单来源限流实际等同于全局限流。该限制写入部署文档，并由 Compose 实测验证（测试 23）。[S0]
- api-admin 不发布宿主端口；进程内部的 `/health/live` 与 `/health/ready` 只在内网可达，不经 gateway（R3）。[S0]
- admin app 只注册管理 router；`docs`、`redoc` 与 `openapi.json` 路由由 M02 在装配 admin app 时关闭、不注册（D16）。[S0]
- OpenAPI 导出 CLI 归 M01，由 `frameread openapi export --app admin` 直接从 admin app 对象导出，不依赖服务端的 `openapi.json` 路由（Q17，D16）。[S0]
- public app 与 8081 分享监听在 S7 装配：public app 不加载 `require_admin` 与管理 router，不使用管理会话依赖，关闭 docs；分享监听不代理任何管理路径。[S7]

### 前端外壳（Q39、D23、D25、D46）

- 路由 `/manage/login` 归 M02；`/manage/tasks`、`/manage/tasks/:id`、`/manage/videos/new` 等业务路由归 M04 与 M12。[S0]
- 应用启动时调用 `GET /session`：`401` 跳转 `/manage/login`，已登录则渲染管理外壳。[S0]
- `401` 时把原路径通过路由状态或 URL 参数带到登录页，登录成功后返回原路径；不使用 localStorage 保存该路径。[S0]
- CSRF token 只存于内存。共享请求层归 M04（D46、I3），M02 提供规则：写请求统一附加 `X-CSRF-Token`；收到 `401` 时跳转 `/manage/login` 并带回原路径；收到 `403 CSRF_REJECTED` 时重新获取 `GET /session` 并提示用户刷新。M04 的轮询收到 `401` 同样按此规则跳转（与 D47 退避策略协调）。[S0]
- `403 CSRF_REJECTED` 时不自动重放写请求。[S0]
- `403 ORIGIN_REJECTED` 时提示“来源校验失败，请从管理入口地址访问”，不重试。[S0]
- 登录页只有密码输入框。[S0]
- 前端不读取 cookie，不把密码或 token 写入 localStorage、URL 或前端日志。[S0]

### 错误、日志与可观测（M01 Q8、Q11、D11，SPEC §4.1、§17.3、§20）

- M02 使用的错误码：`ADMIN_REQUIRED`（401）、`CSRF_REJECTED`（403）、`ORIGIN_REJECTED`（403）、`RATE_LIMITED`（429）、`DEPENDENCY_UNAVAILABLE`（503）、`MAINTENANCE`（503），统一在 M01 的全局错误登记表中登记。[S0]
- 错误体的 `action` 取 D11 枚举值；每个错误码的取值由 M01 的全局登记表定义（E13），M02 只列出自己使用的错误码。[S0]
- `request_id` 为 UUIDv4，同时写入 `X-Request-ID` 响应头。[S0]
- `retry_after_seconds` 只在 429 与 503 时给出；429 必给 `Retry-After` 响应头。[S0]
- 登录成功、登录失败、限流三类事件写入结构化日志，字段限于 allowlist（如 `request_id`、`event`、`epoch`、`error_code`、`duration_ms`、`queue_wait_ms`）；不写密码、token、cookie、CSRF 或来源 IP 明文。[S0]
- 请求 body 与上游信息不进入日志（SPEC §17.3）。[S0]

## 测试决定

接缝编号沿用批次约定：①HTTP 接缝（admin app，真实 PG/Redis）；②进程接缝（独立 api-admin、control，外部手段制造 Redis/PG 故障）；③CLI 接缝；④纯函数接缝；⑤浏览器接缝（Playwright 经 gateway）。

S0 必测场景（AT-18、AT-19 为管理侧子集，AT-18 整项在 S7 验收，R11）：

1. [①] 无 cookie 访问任一 S0 管理路由返回 `401 ADMIN_REQUIRED`，错误体含 `code`、`action`、`request_id`（AT-19，AT-18 管理侧子集）。
2. [①] 有效 cookie 的写请求缺少或错误的 `X-CSRF-Token` 返回 `403 CSRF_REJECTED`，数据库中无任务行与 Outbox 行新增（AT-18、AT-19）。
3. [①] 写请求的 Origin 缺失、错误或为 `https` 变体时返回 `403 ORIGIN_REJECTED`；Host 不在列表时请求被拒绝（AT-18 伪造来源）。
4. [①] 伪造 `X-Forwarded-For`、`X-Forwarded-Host`、`X-Forwarded-Proto` 不改变 401/403 结果，也不改变限流计数来源（AT-18）。
5. [①] 正确密码返回 `201`，设置 cookie 属性正确并返回 CSRF token；错误密码返回统一 `401`；数据库中只存在 token 与 CSRF 的 hash，不存在明文（AT-19）。
6. [①] 同一来源 5 次失败后，第 6 次（即使密码正确）返回 `429` 与 `Retry-After`；成功登录不清除计数（AT-19）。
7. [①] 全局阈值：通过 Compose 网关的真实链路，或使用固定 gateway 地址的测试配置，验证第 31 次失败被限流，且不同来源同样受限。
8. [②] 停止 Redis 后登录返回 `503 DEPENDENCY_UNAVAILABLE`，而已登录会话的读取仍返回 `200`（SPEC §8；AT-19）。
9. [②] 停止 PG 后，携带原 cookie 的管理请求返回 `503`，不返回 `200` 或 `401`（AT-19、AT-21）。
10. [①] 通过预置数据验证：`expires_at` 已过的会话返回 `401`；未过期但 `last_seen_at` 很旧的会话仍返回 `200`；5 分钟内多次请求只写入一次 `last_seen_at`。
11. [①] `DELETE /session` 返回 `204`，数据库中该行 `deleted_at` 非空，原 cookie 再请求返回 `401`。
12. [③] `set-password` 两次输入不一致或为空时非零退出且 secret 不变；目标已存在且无 `--force` 时失败；输入一致后写入 secret，重启 api-admin 后旧会话返回 `401`。
13. [③] `openapi export --app admin` 在服务未运行时成功导出，输出包含管理路由；HTTP 访问 `/docs`、`/redoc`、`/openapi.json` 均不返回 `200`（Q40）。
14. [②] 启动 api-admin 时 hash secret 缺失或为空则进程非零退出；存在则启动成功。
15. [②] 每日清理：预置早于当前时间超过 1 天的会话行（含已退出行）与未超过 1 天的行，执行一次清理后前者被物理删除，后者保留。
16. [④] 表驱动：`credential_generation` 派生（固定输入到 16 字符小写十六进制）；`source_hash` 同 IP 确定、不同 IP 不同、与 CSRF 派生结果不同；CSRF 派生确定；Origin 与 Host 匹配表覆盖大小写、端口、末尾斜杠、userinfo、`http`/`https`、`localhost` 与 `127.0.0.1`。
17. [⑤] 未登录访问 `/manage/` 跳转登录页，登录后回到原路径；登录页只有一个密码输入框；写请求遇到 `403 CSRF_REJECTED` 时页面提示刷新且网络请求无自动重放；`localStorage` 中不存在 token 或密码（AT-19）。
18. [⑤] 限流返回 `429` 时页面显示等待信息与 request ID（AT-19）。
19. [①] 日志抽样：登录成功、失败与限流的日志仅含 allowlist 字段，不含密码、token、cookie、CSRF 或来源 IP 明文（AT-21 的 M02 部分）。
20. [①③] 维护状态：`frozen` 下 `POST /session` 与 `DELETE /session` 返回 `503 MAINTENANCE`；`draining`、`normal` 与 `review_required` 下允许（D20、E5、E13）。
21. [①] 未登录且 Origin 伪造的写请求返回 `403 ORIGIN_REJECTED` 而非 `401`；Host 不匹配的请求返回 `403 ORIGIN_REJECTED`（D21）。
22. [①] 同一 API 进程并发 5 个正确密码登录：全部最终成功，日志中的 `queue_wait_ms` 可观察到排队，且同时进行的 Argon2 校验不超过 2（D26）。并发 N 个错误密码时，失败计数最终等于 N，且在途失败请求超过阈值的数量不超过 2（E13 有界超额）。
23. [②] Compose 实测：经 `127.0.0.1:8080` 连续发送错误密码，核对 gateway 转发的来源地址与 `source_hash` 计数键；确认 `$remote_addr` 覆盖 `X-Forwarded-For` 后的实际来源，并记录单来源退化为全局的实测结果（D19）。

S7 与 S10 补充测试（不在 S0 执行）：public app 无管理路由与 docs、公开入口对所有管理路径返回拒绝（AT-18 完整、AT-19 完整，S7）；恢复后会话全部物理清空（AT-23 的会话子场景，S10）。

## 不在范围内

- 分享 token 授权、分享数据读取、public 数据库角色与 `public_instance_gate`（M15，S7）。
- public app 装配、8081 分享监听、分享 SPA 与双入口负测（S7）。
- 出站 URL 校验与 `EgressPolicy`（M06）；渲染安全与 CSP（M10）。
- 恢复流程、binding 文件与恢复门禁（M17，S10）；本模块只提供清会话接口。
- 管理概览与运行指标（M16）；健康探针的依赖判定（M01 统一注册与判定）。
- 多管理员、角色、注册、找回密码、2FA、会话列表与远程撤销界面。
- 密码强度策略与 Argon2 参数调优（Q34 采用默认参数）。
- 非 loopback 的远程管理开放（S0 不启用；如后续开放，需按 SPEC §17.1 配置 HTTPS Origin）。
- 跨域管理访问（CORS）。
- 管理端 `GET /health` 汇总与 `/overview`（R3，S11，M16 与 M01 协同）。

## 补充说明

### 与其他模块的接口约定

- **M01**：会话的创建、清理与恢复清空经 UoW 执行；登录与退出调用 `gate.require(session)`（E5，SPEC §7.1）。错误码登记（`action` 取值以全局登记表为准）、`request_id` 中间件、secret 读取、KeyRing 的 `session-csrf` 子 key 均由 M01 提供；api-admin 只读取自身需要的 Settings 子集（`ADMIN_ORIGINS`、hash secret 路径）。
- **M03、M04、M05、M07 等管理路由**：统一依赖 `require_admin`。M04 的 SSE 在 S1 起需要每轮复核会话（SPEC §18.2），因此 `require_admin` 的会话校验逻辑需可被 SSE 循环复用，不复制一份。
- **M04**：前端共享请求层归 M04（D46、I3），M02 不另建 fetch 封装；M02 提供 CSRF header、`401`、`403 CSRF_REJECTED` 的处理规则（见实现决定的前端外壳）。
- **M17**：恢复事务中调用 `clear_sessions_for_restore(uow)`，SPEC §22.2 要求该事务由维护角色在单一 PG 事务中执行（D22、U2）。
- **M15**：分享 token 不被 `require_admin` 接受；public 入口不使用本模块的会话依赖。
- **M12**：`POST /session` 与管理写请求一样需要 CSRF；M12 的提交接口依赖 `require_admin`（Q33，任务接口只在 admin app）。
- **CLI**：`admin set-password` 与 M01 的 Typer `frameread` 入口共用（Q16），admin hash 归 `set-password` 单独负责（E15）；`openapi export` 归 M01（D16）。

### 已裁决的文档冲突

批次 A 的文档冲突 C1～C6 已由 [待确认裁决](../frameread-v1/spec-resolutions-batch-a.md) 处理并回写 SPEC_V1：`ADMIN_ORIGINS` 为列表且不进 `policy_json`（R2）、全局登录键 `fr:{epoch}:login:global`（R12）、control 每日清理过期会话（R12）、`admin_sessions` 物理删除例外与恢复清空（U2、D22）、S0 覆盖 AT-18 管理侧子集（R11）。本文不再保留冲突条目。

### 例外说明：admin_sessions 与 task_events 的物理删除

按 U2 裁决，所有表（含 `instance_state`、槽、Outbox、心跳）一律带四个通用列。允许物理删除的只有 `admin_sessions` 与 `task_events`，二者都没有业务历史价值。`admin_sessions` 的两类物理删除如下：

1. control 每日删除 `expires_at` 早于当前时间超过 1 天的行（包括已退出的行）。保留超过 1 天，是为了让近期过期或退出的会话仍可解释。
2. 恢复时 `clear_sessions_for_restore` 物理清空全部行。恢复出的旧会话不得保留任何可用于校验的 token hash。

理由：会话是凭据记录而非业务证据，过期后没有审计或引用价值；每次登录新增一行，长期保留逻辑删除行会使表无限增长；已过期或已退出的 token hash 继续保存只会扩大泄露面。该表没有外键指向它，不触发 `RESTRICT` 顾虑。

### 实施风险

- **来源退化**：默认 loopback 发布时，gateway 看到的来源可能是网桥地址，单来源计数实际等同于全局计数（D19）。已写入部署文档，并由测试 23 实测。
- **HMAC 域分隔**：来源 HMAC 与 CSRF 派生共用 `session-csrf` 子 key，已通过用途前缀分隔（D18）；KeyRing 的子 key 列表本身不需要新增。

### 待确认

无。第一、二轮裁决（E1～E15、U2、R2、R11、R12、D11、D16、D17～D26）已覆盖本模块的全部待确认项（超额上界见 E13，门禁类别见 E5，`action` 归 M01 登记表，secret 归属见 E15，共享请求层见 I3）。

### 仍未解决（不阻塞 S0）

- **restore_state 为 `backup_image` 或 `restoring` 时的登录行为**：按 M17 规则由 restore 门禁处理（E13），本模块在这两种状态下不接受登录，待 M17 Grill 确认具体的错误码与 `action`。`review_required` 状态下允许登录（E13）。

### 接口约定（已对齐，需随其他模块回写时核对）

- **M04 共享请求层**：归 M04（I3）。M02 只提供 CSRF、`401`、`403 CSRF_REJECTED` 的处理规则。
- **M01 门禁**：登录与退出使用 `session` 类别（E5）。
- **M01 secrets**：`admin_password_hash` 由 `admin set-password` 单独负责，`secrets init` 不生成（E15）。
- **M01 Settings 矩阵**：需包含 api-admin 的 `ADMIN_ORIGINS`（列表，位于 `settings.toml`，R2）与 `settings.dev.toml` 额外项（D01）。
- **M01 健康**：M02 不注册探针；Redis 对登录限流的影响由 M01 的 Redis 探针覆盖（D24）。`/health/live` 与 `/health/ready` 不经 gateway（R3）。

## 参考

- 每条决定的来源：[Grill 批次 A](../frameread-v1/grill-batch-a.md) 与 [待确认裁决](../frameread-v1/spec-resolutions-batch-a.md)。
