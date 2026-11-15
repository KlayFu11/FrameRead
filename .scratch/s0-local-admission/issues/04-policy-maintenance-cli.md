# 04: 运行策略与维护模式 CLI

**What to build:** 部署者用 `frameread policy set` 调整执行槽、等待位、期限等资源策略，所有进程以 PostgreSQL 中的值为准，调小槽位时多余槽变为 retired 而不打断占用者；用 `frameread maintenance set normal|draining|frozen` 停写升级，非 normal 状态下新提交返回 `503 MAINTENANCE`，已受理任务仍可查询与找回。

**Blocked by:** 03 提交视频任务并用原键找回

**Status:** ready-for-agent

**依据：** [M01 SPEC](../../m01-instance-platform/spec.md) 3.1 门禁、3.7 运行策略与维护 CLI、测试决定 10、18；[M03 SPEC](../../m03-task-runtime/spec.md) 执行槽与接口中的 `sync_execution_slots`。REQ-03、REQ-11；AT-19 维护。

- [ ] `policy set`：Pydantic 校验键与取值，实例行锁内更新 `policy_json` 并递增 `config_revision`，同一 UoW 调用 `sync_execution_slots`；非法值退出码 2 且不改数据（Q14、D08、D09、E7）
- [ ] 调大 E 补槽行；调小 E 时多余槽置 `retired`，占用中的任务不受影响，释放后不再分配（Q22）
- [ ] 启动时 `settings.toml` 与 `policy_json` 不一致只记 warning，不覆盖（Q14）
- [ ] `maintenance set`：任意时刻可执行；仅 `restore_state=normal` 时可设为 normal；退出码 0/1/2，错误输出带 request_id（D07、D09）
- [ ] CLI 使用应用 DML role 与 sync UoW
- [ ] 测试：draining、frozen 及 fixture 写入的 review_required 下 `POST /video-tasks` 返回 `503 MAINTENANCE` 且无新增行；同键找回与 `GET /tasks/{id}` 照常；policy 调小后 retired 槽不再被分配
