# 09: 任务列表

**What to build:** 部署者打开 `/manage/tasks`，看到按新到旧排列的任务列表，可按 kind 与 status 过滤并翻页，列表每 5s 刷新，从列表进入任务详情。篡改游标或改变过滤条件后沿用旧游标得到明确错误，而不是错乱的数据。

**Blocked by:** 03 提交视频任务并用原键找回

**Status:** ready-for-agent

**依据：** [M04 SPEC](../../m04-task-sync/spec.md) 任务列表、签名游标、轮询、状态合并；SPEC_V1 §5 `TaskListItem`、§7.2 分页。REQ-03、REQ-11；AT-20 分页有界与无 N+1 的 S0 部分。

- [ ] `GET /tasks`：keyset `(created_at, id)` 新到旧，默认 20、上限 100；返回 `TaskListItem` 摘要；过滤 `kind`、`status` 为小写枚举，非法值 `422`（D44）
- [ ] 游标用 cursor 子密钥 HMAC 签名，含 `scope=admin-task-list` 与过滤摘要；篡改或过滤变化返回 `422 INVALID_INPUT`，`details` code `cursor_invalid`（Q30、R8）
- [ ] 每页固定数量 SQL，无按行查询；保存代表样本的 `EXPLAIN (ANALYZE, BUFFERS)` 与查询次数到验证证据
- [ ] 前端列表页：5s 轮询，页面隐藏暂停，失败指数退避至 30s 并提示“连接中断”；每行按 `(epoch, state_revision)` 合并；超过 10s 未同步显示同步时间；本地时区（D47）
- [ ] 测试：分页边界与稳定排序、过滤、游标篡改与过滤变化、上限 100；Playwright 打开列表并进入详情，截图
