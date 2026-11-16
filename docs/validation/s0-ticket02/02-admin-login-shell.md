# S0 Ticket 02 验证记录：管理员登录与管理外壳

日期：2026-11-16。实现提交：`bcc592e`。对应 [Ticket 02](../../../.scratch/s0-local-admission/issues/02-admin-login-shell.md)、[M02 SPEC](../../../.scratch/m02-admin-access/spec.md) 与 M04 前端底座。

## 环境与范围

宿主为 Windows Docker Desktop，运行 Linux 容器；隔离 Compose 项目为 `frameread-s0-t02`，入口为 `http://127.0.0.1:8080/manage/`。已应用迁移 `0002`，api-admin、worker、control、postgres、redis 与 gateway 正常运行。凭据、cookie 和测试连接配置仅留在被忽略的本地文件，不属于提交产物。

后端使用项目 `.venv` 中的 Python 3.12，依赖由 `backend/uv.lock` 固定。前端本地检查使用 Node `24.19.0`、pnpm `10.20.0`；gateway 构建使用 Dockerfile 中固定 digest 的 Node 镜像。最终 production bundle 为 `index-Cf9MuIhH.js`，与浏览器验收使用的运行实例一致。

## 自动化与静态检查

| 检查 | 命令与结果 |
| --- | --- |
| 后端完整测试 | 在 `backend/` 设置本地测试环境变量后，`.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`，**217 passed**，40.48s，无 skip、无 xfail；1 条现有 Starlette TestClient 弃用提示 |
| 后端依赖 | `uv lock --check`，58 packages，成功 |
| 后端静态检查 | `ruff check src tests`、`ruff format --check src tests`、`mypy` 全部成功；59 files already formatted，36 source files 无类型错误 |
| 前端锁与安装 | `pnpm install --frozen-lockfile --offline`，锁文件匹配且已安装依赖无需变动 |
| 前端测试 | `pnpm test`，**13 passed**，2 个测试文件 |
| 前端类型与构建 | `pnpm typecheck`、`pnpm build` 成功，87 个模块完成 production build |
| 生成产物 | `frameread openapi export --app admin --out backend/openapi/admin.json`（从仓库根目录调用 CLI）后，在 `frontend/` 执行 `pnpm generate:api`；分别比对生成前后 SHA-256，两份产物均逐字节一致 |
| 差异与审查 | `git diff --check` 成功；完整实现含新增文件连续两轮审查未发现问题，检查了接口顺序、事务与门禁、cookie、凭据写入、限流、前端恢复与错误反馈、部署和生成产物 |

HTTP 集成测试使用真实 PostgreSQL 与 Redis。覆盖登录与退出、cookie 属性、只存 hash、12h 绝对过期、无空闲超时、`last_seen_at` 节流、密码轮换、Host/Origin 与 malformed JSON 的校验顺序、来源和全局限流、成功不清零、并发排队与有界超额、日志 allowlist，以及维护门禁和清理。并发错误登录检查失败计数等于实际 `401` 数量，且 10 个请求的失败数在 5～7 范围内；未通过放松断言或跳过用例处理失败。

CLI 测试包含已安装命令的重定向 stdin，确认不会回显密码；空值、不一致输入和未经 `--force` 的覆盖均失败，原文件保留。前端测试在 `fetch` 边界覆盖 CSRF 自动附加、403 后重取会话且不重放、401 原路径恢复、直接访问登录页的有效会话恢复、退出、429、Origin 拒绝、字段错误和 request ID 复制。

## 实际 HTTP 与进程检查

复现入口为 [try_s0_admin_acceptance.py](../../../scripts/try_s0_admin_acceptance.py)。该脚本仅用于隔离验收实例，会设置临时密码、停止和恢复依赖、轮换验收密码；不得对已有用户实例执行。`prepare`、`http` 与 `process` 是独立阶段，`reset-limits` 仅清理该验收实例当前 epoch 的登录计数。

| 操作 | 实际结果 |
| --- | --- |
| 无 cookie 读取管理会话 | `401 ADMIN_REQUIRED` |
| 写请求缺失/伪造 Origin，或 Host 不匹配 | `403 ORIGIN_REJECTED` |
| 正确密码登录，读取会话，缺少 CSRF 退出 | 依次 `201`、`200`、`403 CSRF_REJECTED` |
| 正确 CSRF 退出，再使用旧 cookie | `204`，随后 `401` |
| 经 gateway 访问 docs、OpenAPI、健康或 public 路径 | `404` |
| 停止 Redis | 登录 `503 DEPENDENCY_UNAVAILABLE`，已有会话读取 `200` |
| 停止 PostgreSQL | 原 cookie 读取 `503 DEPENDENCY_UNAVAILABLE`；恢复后读取 `200` |
| CLI 轮换密码并重新创建 api-admin | 旧 cookie `401`，新密码登录 `201`；gateway 重启以刷新 API 地址 |
| hash secret 缺失或为空 | 独立 api-admin 进程非零退出 |
| control 清理预置过期会话 | 超过 1 天的 2 行删除（含退出行），近期或未到期的 2 行保留 |
| frozen 状态 | 登录拒绝；会话只读不刷新 `last_seen_at`，清理不删除；HTTP 集成测试同时验证登录和退出均为 `503 MAINTENANCE` |
| 5 次错误密码，轮换伪造 XFF，第 6 次使用正确密码 | 前 5 次 `401`，第 6 次 `429`，包含 `Retry-After` 与等待秒数 |

## 来源与日志

执行只读观察器：

```sh
backend/.venv/Scripts/python.exe scripts/observe_admin_source.py
```

观察器读取 Docker 网络候选地址，在容器中用派生子 key 计算来源 HMAC，与真实 Redis 来源键比对；不输出子 key、hash secret、会话 token 或 cookie。最终观察结果见 [source-observation.json](source-observation.json)：

- 实际来源为 Docker 网桥地址 `172.20.0.1`，仅 1 个来源键，来源与全局失败计数均为 5。
- 伪造 `192.0.2.*` 的 XFF 没有创建对应来源键。nginx 使用实际 TCP 对端覆盖 XFF，uvicorn 只信任固定 gateway 地址。
- 最终运行实例抽样检查 api-admin 的 9 条和 gateway 的 23 条 JSON 日志，字段均在各自 allowlist 内，登录成功、失败、限流事件齐全，未出现来源 IP 明文。检查范围是此次抽样记录。

因此本平台经 loopback 发布的多个客户端会共享单来源限流，5 次失败即可使这些客户端一起受到限制。`172.20.0.1` 是本次观测结果，其他宿主和网络不得直接沿用。详见 [部署说明](../../../deploy/README.md#网关来源与本地调试)。

## 浏览器交互与截图

使用本地 Playwright 与独立 Chromium context，浏览器版本 `156.0.8078.4`。实际打开 gateway 页面，以 DOM 定位输入框和按钮，使用 `1280×900` 与 `390×844` 视口。驱动默认缓存版本未安装，显式指定了本机已有 Chromium 可执行文件；浏览器已在验收结束后关闭。

[browser-result.json](browser-result.json) 保留 10 项检查和实际响应顺序：未登录深链接 `/manage/tasks` 跳登录、仅一个密码框、错误密码反馈、登录 `201` 后回原路径、有效会话直接打开登录页后进入管理外壳、移动端溢出、CSRF `403` 不重放、退出 `204` 与刷新后仍未登录、限流 `429` 的等待信息与 request ID、无 JavaScript page error。

CSRF 场景仅在浏览器网络层移除一次真实 `DELETE` 请求的 `X-CSRF-Token`，后端实际返回 `403`；请求层随后发出 `GET` 并获得 `200`，页面提示刷新。在第二次人工点击之前只有一条 `DELETE`，没有自动重放；再次点击后正常 `204`。浏览器存储未保存 token 或密码。

全部 7 张截图已实际查看，两个视口下未观察到遮挡、裁切、横向溢出或不可读错误反馈：

| 状态 | 截图 |
| --- | --- |
| 桌面登录与错误密码 | [login-desktop.png](login-desktop.png)、[login-error.png](login-error.png) |
| 桌面与移动端管理外壳 | [shell-desktop.png](shell-desktop.png)、[shell-mobile.png](shell-mobile.png) |
| 移动端 CSRF 拒绝 | [csrf-rejected-mobile.png](csrf-rejected-mobile.png) |
| 移动端退出后登录页 | [logout-mobile.png](logout-mobile.png) |
| 移动端限流反馈 | [rate-limited-mobile.png](rate-limited-mobile.png) |

DOM 证据为 [login-snapshot.txt](login-snapshot.txt) 与 [shell-snapshot.txt](shell-snapshot.txt)。

## 限制

GitHub Actions 已更新，本地对应检查通过；没有 push，远端工作流尚未运行。此次为 Windows Docker Desktop 上的 Linux 容器验收，不代表 Linux 宿主兼容性已验证。仅验收 S0 管理入口，S7 public app 与 S10 恢复调用链不在本 Ticket。当前业务页面由后续 Ticket 实现，前端不展示尚不存在的业务功能。
