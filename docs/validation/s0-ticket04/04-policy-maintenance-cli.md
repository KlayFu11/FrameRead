# S0 Ticket04：运行策略与维护模式 CLI 验证

日期：2026-11-16  
分支：`feat/s0-ticket-04`，基于集成基线 `e5406ab`

## 结论

Ticket04 的策略和维护 CLI 已实现并通过本地验证。`policy set` 使用应用 DML 角色、实例行锁和同一 sync UoW 更新 `policy_json`、递增 `config_revision` 并同步 `resource_slots`；缩容将多余槽置为 `retired`，不会打断占用者，释放后也不会再次分配。`maintenance set` 可在任意维护状态执行，仅在 `restore_state=normal` 时允许切回 `normal`。非 `normal` 维护状态下，新视频任务返回 `503 MAINTENANCE`，同键 replay、任务查询保持可用。

## 实现范围

- `backend/src/frameread/cli/policy.py`：`frameread policy set`，支持 pool 容量、视频期限、租约、心跳、dispatcher、投递预算、generation 上限和事件保留策略。
- `backend/src/frameread/cli/maintenance.py`：`frameread maintenance set normal|draining|frozen`。
- `backend/src/frameread/cli/runtime.py`：读取 app DML 的 `DATABASE_DSN_FILE` 与 `MASTER_KEY_FILE`，先校验 migration head/root key，再运行 sync `UnitOfWork`。
- `backend/src/frameread/services/policy.py`、`maintenance.py`：Pydantic 合并校验、实例锁内 DML、同事务槽同步和 restore 状态约束。
- `deploy/README.md`：补充容器内 CLI 用法、退出码和维护/缩容语义。

## 自动化验证

测试使用已有真实 PostgreSQL/Redis 测试容器；每个测试通过独立数据库夹具隔离，连接信息和凭据未写入本记录。

| 检查 | 结果 |
| --- | --- |
| Ticket04 CLI 用例（完整套件内执行） | 12 passed |
| 其中实际安装 CLI 子进程 `frameread policy set`、`frameread maintenance set` | 2 个命令均退出码 0，数据库状态已核对 |
| 完整 `backend` 测试套件 | 270 passed，1 个既有 Starlette/httpx 弃用 warning，66.64s |
| `ruff check src tests` | passed |
| `ruff format --check src tests` | passed，77 files |
| `mypy --strict` | passed，50 source files |
| `uv lock --check --offline` | passed，58 packages |

最终测试命令为 `python -m pytest -q -p no:cacheprovider --basetemp tmp/pytest-final04`，使用本 worktree 的 `.venv/Scripts/python.exe`；先创建 `tmp/`，连接配置仅从既有忽略的 `.env.s0-tests` 载入进程环境。

## 关键场景证据

1. 初始 `video` 执行槽为 2；CLI 调整为 1 后，`config_revision` 从 1 递增为 2，策略期限写入 3600 秒，槽 2 为 `retired`。
2. 两个任务分别占用槽 1、2 后缩容，槽 2 保持 `assigned_task_id` 且状态为 `retired`；模拟任务释放后，新的受理只使用 active 槽 1，槽 2 保持空闲 `retired`。
3. `execution_slots=0` 的 Pydantic 校验返回退出码 2，输出 `request_id`，`policy_json` 与 `config_revision` 均未改变。
4. `restore_state=review_required` 时 `maintenance set normal` 返回退出码 1、输出 `request_id`，数据库仍保持原维护模式；`draining`、`frozen` 和 `review_required` 三种 HTTP 场景均验证了新键 `503 MAINTENANCE`、原键 replay 和任务 GET。
5. 实际安装的 CLI 子进程使用 app DML DSN 文件执行成功，证明命令入口不是仅在 `CliRunner` 内可用。
6. CLI 将 E 从 2 缩为 1 再扩为 3 后，槽 2 从 retired 恢复为 active，槽 3 新建为 active，三行均可用；两次更新后的 `config_revision=3`。
7. 非法数字、未知选项和缺失维护模式三个解析错误均退出 2，输出 UUID `request_id`。

两轮完整差异审查覆盖全部新增文件、事务回滚、门禁、用法错误与测试断言；第二轮未发现新增问题。`git diff --check` 通过。

## 未覆盖项

- 本 Ticket 未修改共享 Compose 运行栈；gateway/浏览器级整体验收由父 agent 在集成分支执行。
- `policy_differs_from_settings` 的启动 warning 逻辑沿用现有 M01 bootstrap 实现，Ticket04 未改写其判定路径；策略 CLI 不读取 `settings.toml`，运行时以 PostgreSQL 为准。
