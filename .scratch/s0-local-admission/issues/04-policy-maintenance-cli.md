# 04: 运行策略与维护模式 CLI

**What to build:** 部署者用 `frameread policy set` 调整执行槽、等待位、期限等资源策略，所有进程以 PostgreSQL 中的值为准，调小槽位时多余槽变为 retired 而不打断占用者；用 `frameread maintenance set normal|draining|frozen` 停写升级，非 normal 状态下新提交返回 `503 MAINTENANCE`，已受理任务仍可查询与找回。

**Blocked by:** 03 提交视频任务并用原键找回

**Status:** resolved

**依据：** [M01 SPEC](../../m01-instance-platform/spec.md) 3.1 门禁、3.7 运行策略与维护 CLI、测试决定 10、18；[M03 SPEC](../../m03-task-runtime/spec.md) 执行槽与接口中的 `sync_execution_slots`。REQ-03、REQ-11；AT-19 维护。

- [x] `policy set`：Pydantic 校验键与取值，实例行锁内更新 `policy_json` 并递增 `config_revision`，同一 UoW 调用 `sync_execution_slots`；非法值退出码 2 且不改数据（Q14、D08、D09、E7）
- [x] 调大 E 补槽行；调小 E 时多余槽置 `retired`，占用中的任务不受影响，释放后不再分配（Q22）
- [x] 启动时 `settings.toml` 与 `policy_json` 不一致只记 warning，不覆盖（Q14）
- [x] `maintenance set`：任意时刻可执行；仅 `restore_state=normal` 时可设为 normal；退出码 0/1/2，错误输出带 request_id（D07、D09）
- [x] CLI 使用应用 DML role 与 sync UoW
- [x] 测试：draining、frozen 及 fixture 写入的 review_required 下 `POST /video-tasks` 返回 `503 MAINTENANCE` 且无新增行；同键找回与 `GET /tasks/{id}` 照常；policy 调小后 retired 槽不再被分配

## Comments

- 2026-11-16：由 `feat/s0-ticket-04` 在 `e5406ab` 基础上领取，按 `implement-spec` 与 `tdd` 技能实现；父 agent 负责 integration 分支合并。

## Answer

已完成运行策略与维护模式 CLI。实现、测试与限制见 [Ticket04 验证记录](../../../docs/validation/s0-ticket04/04-policy-maintenance-cli.md)。

- `frameread policy set` 通过应用 DML 角色、实例行锁和同一 sync UoW 写入完整 Pydantic 校验后的 `policy_json`，递增 `config_revision` 并调用 `sync_execution_slots`。
- `frameread maintenance set normal|draining|frozen` 遵守 `restore_state` 切换约束，并在业务/用法错误中输出 `request_id` 与退出码。
- 实现 commit：`9ad4af6 feat: add runtime policy and maintenance CLI`。
- 实际检查：本 worktree `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp tmp/pytest-final04`，完整 270 项通过；`ruff check src tests`、`ruff format --check src tests`、`mypy --strict`、`uv lock --check --offline` 均通过。包含真实 PostgreSQL/Redis 集成测试与已安装 CLI 子进程。
- 已完成两轮全部差异审查。未完成项：本 Ticket 不操作共享 Compose；最终 gateway/浏览器验收归 Ticket10。
