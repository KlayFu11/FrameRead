# 10: S0 验收收口

**What to build:** 在干净本机按 `deploy/README.md` 从零启动 S0，经页面完成“登录 → 提交 → 运行 → 取消”，CI 在真实 PostgreSQL、Redis 与独立 Worker 上跑通 S0 核心链；S0 涉及的每个 AT 子场景都有可复查的验证证据，模块地图进度更新为 S0 已交付。

**Blocked by:** 05 提交结果未确认时用同键找回、07 取消、期限与等待位提升、08 Worker 失联与投递丢失的对账、09 任务列表

**Status:** ready-for-agent

**依据：** PRD §6 S0 行；[M01 SPEC](../../m01-instance-platform/spec.md) 测试决定 19、20；地图 §10.2～10.4。AT-02 新提交子场景、AT-04 全项、AT-05 受理后未发送与重复消息、基础 AT-19/21、AT-22 S0 子集（R10）、AT-20 空库迁移。

- [ ] 在新卷上严格按 `deploy/README.md` 执行，记录命令、环境与输出；不依赖已有数据
- [ ] Playwright 端到端：登录 → 提交 → 详情 running（acquire 阶段与骨架提示）→ 取消 → canceled → 列表可见；截图实际查看
- [ ] CI：锁文件、OpenAPI 与 TS 生成 diff、迁移、单测、真实 PG/Redis 集成、独立 Worker 与 control 进程核心链全部通过，无 skip
- [ ] 日志抽查：沿一条成功受理与一条失败任务，用 request_id → task_id 串起请求、受理、领取、阶段与终态；无敏感字段
- [ ] 健康抽查：分别停止 PG、Redis、Worker，ready 分项按 D13/E6 区分 unavailable 与 degraded
- [ ] `docs/validation/` 建立 S0 证据记录：每个 AT 子场景对应的测试名或命令、结果、截图与执行计划路径；注明 AT-06/08、AT-22 完整部署等不在 S0
- [ ] 更新 [map.md](../../frameread-v1/map.md) §10.2（Ticket 10/10、AT 证据路径、状态“已交付”）与 §10.4 下一步
- [ ] 向用户提出是否删除 `.scratch/frameread-v1/spec-brief-batch-a.md`（编写约定已完成使命），经用户明确同意后才删除
