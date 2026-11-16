# 02: 管理员登录与管理外壳

**What to build:** 部署者用 `frameread admin set-password` 设置密码后，经 gateway 打开 `http://127.0.0.1:8080/manage/`，未登录时跳到只有密码框的登录页；登录后进入管理外壳，可退出。伪造来源、缺少 CSRF、无会话的管理请求一律被拒绝；连续输错密码被限流。前端工程、共享请求层与 OpenAPI 生成的 TS 类型在本 Ticket 建立，供后续页面使用。

**Blocked by:** 01 平台骨架可启动

**Status:** resolved

**依据：** [M02 SPEC](../../m02-admin-access/spec.md) 全部 S0 实现决定与测试决定；[M04 SPEC](../../m04-task-sync/spec.md) 实现决定 9 前端底座。REQ-10；AT-18 管理侧子集（R11）、AT-19 的 401/403/429。

- [x] `admin set-password` 从 stdin 读取两次，Argon2id（argon2-cffi 默认参数）写 secret 文件，临时文件原子替换，已存在须 `--force`；`secrets init` 不生成该文件（Q34、D17、E15）
- [x] `admin_sessions` 迁移；`POST/GET/DELETE /session`：32 字节 token、SHA-256 存 hash、12h 绝对过期、`last_seen_at` 至多 5 分钟写一次；退出置 `deleted_at`；`credential_generation` 不符时会话失效（Q36、D17、D23）
- [x] cookie `frameread_admin` HttpOnly、SameSite=Strict、Path=/api/v1/admin，loopback HTTP 不设 Secure
- [x] `require_admin` 检查顺序 Host → Origin（写请求，缺失即拒）→ 会话 → CSRF；`ADMIN_ORIGINS` 精确列表来自启动配置；dev 配置额外允许 Vite 源（Q38、D21）
- [x] 登录与退出调用 `gate.require(session)`，frozen 下 `503 MAINTENANCE`（E5）
- [x] 登录限流：按来源与全局固定窗口，预检只读，失败路径 Lua 原子递增，只计密码错误，成功不清零；超限 `429` + `Retry-After`；Redis 不可用 `503 DEPENDENCY_UNAVAILABLE`；每进程 Argon2 并发上限 2（Q35、D18、D24、D26、E13）
- [x] control 每日物理清理过期超 1 天的会话（Q36、U2）
- [x] admin app 关闭 `/docs`、`/redoc`、`/openapi.json`（Q40、D16）
- [x] nginx gateway：`127.0.0.1:8080`，`/manage/` 静态、`/api/v1/admin/` 反代；固定子网与 IP，uvicorn 只信任 gateway；`X-Forwarded-For` 用 `$remote_addr` 覆盖（Q37、D19）
- [x] 前端：Vite + React + TS strict + React Router + TanStack Query + CSS Modules；`src/gen/` 由 OpenAPI 生成且提交；CI 重新生成后 diff 为空（Q17、Q28）
- [x] 共享请求层：写请求自动加 `X-CSRF-Token`；`401` 带原路径跳 `/manage/login`；`403 CSRF_REJECTED` 重取 session 后提示刷新，不重放；`403 ORIGIN_REJECTED` 提示从管理入口访问（Q39、D25）
- [x] 测试：无会话 `401`、无 CSRF `403`、伪造 Origin/Host `403`、限流 `429` 与有界超额、密码轮换后旧会话失效、frozen 登录 `503`；Playwright 经 gateway 登录与退出并截图
- [x] Compose 实测并记录 loopback 发布下来源地址是否退化为网桥地址（D19）

## Answer

- **实现**：`bcc592e`，增加管理员凭据 CLI、会话迁移与鉴权、限流、control 清理、gateway 静态入口和 React 管理外壳；所有管理路径启动时先检查会话，包括直接打开登录页。
- **自动化检查**：最终源码后端全量 `217 passed`，前端 `13 passed`；Ruff、format、strict mypy、两端锁文件检查、TypeScript typecheck 和 production build 均通过。OpenAPI 与 TS 类型重新生成后逐字节一致；远端 CI 未运行。
- **实际运行**：隔离 Compose 项目经 gateway 验证登录、退出、来源与 CSRF 拒绝、限流、PG/Redis 停止与恢复、密码轮换、缺失/空 hash 启动失败及 control 清理。Playwright 完成 10 项真实页面检查，保留网络顺序、DOM 快照和 7 张截图，已实际查看。
- **来源限制**：Windows Docker Desktop 下实际来源为 `172.20.0.1`；5 次失败只有一个来源键，来源与全局计数均为 5，伪造 XFF 对应键为 0。部署文档已说明合并限流的影响。
- **审查与证据**：完整实现 diff 连续两轮审查未发现问题；细项、命令、截图与限制见 [验证记录](../../../docs/validation/s0-ticket02/02-admin-login-shell.md)。
- **边界**：当前只完成 S0 管理外壳，后续业务页面、S7 public 入口和 S10 恢复流程不在本 Ticket；Windows Docker Desktop 验收不代表 Linux 宿主已验证。未 push。
