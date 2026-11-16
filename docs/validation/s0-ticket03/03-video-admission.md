# S0 Ticket 03 验证记录

日期：2026-11-16。对应 [Ticket 03](../../../.scratch/s0-local-admission/issues/03-submit-video-task.md)。

## 环境与实现

- Windows Docker Desktop；真实 PostgreSQL 17、Redis 7.4。后端依赖沿用已提交的 `backend/uv.lock`。
- 最终测试使用 Ticket03 自身的 `.venv/Scripts/python.exe`；实际打印的 `frameread.__file__` 位于 Ticket03 worktree。通过现有 uv 缓存离线恢复环境，没有更改依赖版本。
- API、worker、control 使用本任务开发项目 `frameread-s0-t02`；保留既有密钥与数据卷。
- 受理与槽同步位于 [admission.py](../../../backend/src/frameread/services/admission.py)，快照位于 [task_snapshot.py](../../../backend/src/frameread/services/task_snapshot.py)。
- 已应用的 `0003` 保持不变；`0004` 追加四个可空 UUID 引用列。实际迁移测试检查列类型、可空性及 SQL `NULL`；S1 创建目标表后再增加相应外键，本轮未创建未来业务表。

## 后端检查

工作目录为 `backend/`，`FRAMEREAD_TEST_PG_URL` 与 `FRAMEREAD_TEST_REDIS_URL` 从本地测试环境注入，不在此记录凭据。

| 检查 | 实际结果 |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest -q --tb=no -p no:cacheprovider` | 258 passed，53.16s，无 skip；1 条既有 Starlette/httpx 弃用提示 |
| `ruff check src tests` | 通过 |
| `ruff format --check src tests` | 71 files already formatted |
| `mypy`（项目 strict 配置） | 46 source files，无问题 |
| `uv sync --frozen --offline` | 从现有缓存恢复本 worktree，未升级版本 |
| `uv lock --check --offline` | 通过 |
| 前端 `vitest run --maxWorkers=1 --reporter=dot` | 35 passed，5 files，29.58s |
| 前端 `tsc --noEmit`、`vite build` | 通过，最终脚本 `index-UNUv61Vj.js` |
| `frameread openapi export --app admin --out openapi/admin.json` | 重生成前后 hash 相同 |
| `openapi-typescript ../backend/openapi/admin.json -o src/gen/admin-api.d.ts` | 重生成前后 hash 相同 |
| `ruff check scripts/verify_gateway_dns.py --config backend/pyproject.toml` | 通过 |

主要行为由 [test_video_admission.py](../../../backend/tests/integration/test_video_admission.py)、[test_migrate.py](../../../backend/tests/integration/test_migrate.py) 和 [test_video_input.py](../../../backend/tests/unit/test_video_input.py) 覆盖：

- 同键并发只产生一份 task、Outbox 与 accepted 事件；同键异输入返回原任务 ID 的冲突。
- E=2、Q=4 容量边界下，最后一个名额的两个并发请求恰好一个成功、一个 `QUEUE_FULL`；满额仍可找回原操作。
- 真实约束失败时 task、Outbox、事件与槽绑定全部回滚；实例初始化与槽同步失败也在同一事务回滚。
- 维护状态下，新受理被拒绝，已受理操作仍可重放或查询；快照从同一 REPEATABLE READ 数据库快照读取任务、当前 epoch 与门禁。
- `allowed_actions` 新增四组真实数据库回归：修复前 frozen/review_required 两组失败，修复后全量通过；正常与 draining 仍提供 cancel，禁止取消的状态不提供该动作。
- URL 规范化不联网，覆盖支持主机、路径、分 P、追踪参数与输入错误；S0 配置与 intent 边界执行后端重复校验。
- 新增回归覆盖必填 `Idempotency-Key` 的 OpenAPI 契约、非十进制分 P 输入、持久草稿损坏时禁止换键提交、旧 revision 终态响应不能停止新状态轮询，以及 404 错误仍显示 request ID。

## 容器与 gateway 回归

- 最终 backend 与 gateway 镜像构建成功，实际容器 image ID 与最终构建镜像一致，增量迁移完成，api-admin、worker、control、gateway 均 healthy。
- 实测发现：后端容器重建后，gateway 会话请求返回 502，而 gateway 内按 `api-admin` DNS 访问 live 返回 200。这是旧地址缓存问题，不能只靠重启 gateway 交付。
- 修复使用固定 nginx 1.28 镜像支持的 upstream shared zone、`server resolve` 与 Docker DNS，配置已在同一固定镜像中执行 `nginx -t` 通过。依据：[nginx 官方 upstream 文档](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#server)。
- 真实地址切换回归入口：[verify_gateway_dns.py](../../../scripts/verify_gateway_dns.py)。它只操作明确指定的独立 S0 验收项目，结束时恢复 API 原网络地址。[gateway-dns.json](gateway-dns.json) 记录从 `172.28.0.4` 切换为 `172.28.0.253` 后 2.516 秒恢复，gateway 未重启，随后恢复原地址。
- 每次 curl 独立请求并写入独立临时响应文件，由 Python 解析断言。结果见 [http.json](http.json)：登录 201、提交 202、同键重放 202、快照 200、操作找回 200、异输入冲突 409；任务保持 queued、attempt_no=0、unknown_call_count=0。

## 浏览器验收

本地 Playwright 使用独立 Chromium 上下文，经 gateway 执行真实操作；上下文与浏览器均已关闭。密码从忽略文件读取，没有写入截图、日志或提交。

[browser-result.json](browser-result.json) 记录 10 项检查：登录返回提交页、complete/standard 默认值、非法 host 的 422 字段提示与旧键清除、刷新保留草稿、真实 202 跳转 queued 详情、新键生成与成功后清除、轮询及刷新保留任务 ID、新表单为空、桌面/移动端无水平溢出、无页面异常和外部浏览器请求。

已实际查看全部五张截图：

- [桌面表单](form-desktop.png)、[422 错误](form-invalid-desktop.png)、[桌面详情](detail-desktop.png)。
- [移动端详情](detail-mobile.png)、[移动端表单](form-mobile.png)。

视口为 1280×900 与 390×844，布局、错误提示和 S0 边界说明可读，无遮挡。DOM 证据见 [表单](form-snapshot.txt) 与 [详情](detail-snapshot.txt)。

## 限制

当前 Ticket 只完成受理与快照，Worker 领取、取消及列表由后续 Ticket 实现。远端 GitHub Actions 与 Linux 宿主部署尚未运行；本地验证不代表这些环境已通过。未 push。
