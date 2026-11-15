# S0 Ticket 01 验证记录：平台骨架可启动

日期：2026-11-16。对应 [Ticket 01](../../../.scratch/s0-local-admission/issues/01-platform-skeleton.md)。

## 环境

- 宿主：Windows，Docker Desktop（Docker 29.9.2，Compose v5.6.1，Linux 引擎 x86_64）。按 SPEC §19，Windows Docker Desktop 属于待验证宿主环境，本记录不代表已在 Linux 宿主机上验证。
- 后端：Python 3.12，依赖由 `backend/uv.lock` 锁定。
- 镜像 digest：固定在 `deploy/compose.yaml` 与 `deploy/Dockerfile.backend` 中。
- 集成测试使用独立容器 `postgres:17-alpine` 与 `redis:7.4-alpine`（与 Compose 相同的 digest）。

## 自动化测试

命令：在 `backend/` 下设置 `FRAMEREAD_TEST_PG_URL` 与 `FRAMEREAD_TEST_REDIS_URL` 后执行 `uv run pytest -q`。结果：176 passed，无 skip、无 xfail。逐条用例见 [01-pytest.txt](01-pytest.txt)。

另有 `uv lock --check`、`ruff check`、`ruff format --check` 与 `mypy --strict`，均已通过。

下面三处用变异检查确认测试能抓到真实缺陷：把实现临时改坏，确认对应测试失败，再恢复原代码：

| 被测行为 | 改坏的方式 | 结果 |
| --- | --- | --- |
| 迁移并发串行化 | 换成不互斥的 advisory lock | 并发测试失败 |
| 乐观锁条件更新 | 去掉 `version = :expected` 条件 | 过期版本用例失败 |
| 生产 origin 检查 | 在 `deploy/settings.toml` 中加入 `http://localhost:5173` | 测试失败 |

## Compose 部署（AT-22 S0 子集）

在新数据卷上按 [deploy/README.md](../../../deploy/README.md) 依次执行：`secrets init` → `build` → `run --rm migrate` → `up -d --wait`。结果：

- migrate 自动拉起 postgres，等待其健康后迁移，输出 `instance_initialized`，退出码 0。
- 六个服务全部 running；带健康检查的服务均为 healthy。
- 运行 `scripts/check_compose_s0.sh`，输出 OK。检查项：非 root、根文件系统只读、CPU/内存/pids 限制、无 privileged、未挂载 Docker socket，以及 api-admin ready 的四个分项都为 ready。用一个违规容器验证过，该脚本能报出全部 5 项问题。
- 迁移前先启动服务：api-admin ready 返回 503，`migration_head=head_mismatch`；worker 和 control 持续输出 `startup_not_ready`，不写库。迁移完成后，三个服务无需重启即转为 ready。
- 对外只发布 `127.0.0.1:8080`。通过 gateway 访问 `/health/ready` 返回 404，宿主机访问 8000 端口连接失败。

## 依赖故障（AT-21 基础）

原始输出见 [01-health-faults.txt](01-health-faults.txt)：

| 场景 | live | ready | 结论 |
| --- | --- | --- | --- |
| 基线 | 200 | 200 ready | 四个分项都为 ready |
| 停止 Redis | 200 | 200 degraded | redis 分项为 `connection_failed` |
| 停止 PostgreSQL | 200 | 503 unavailable | postgres、head、root_key 分项均为 `connection_failed` |
| 恢复依赖 | 200 | 200 ready | 进程未重启 |

## 未完成的验证

- GitHub Actions（`.github/workflows/ci.yml`）尚未在远端运行，需要推送后才能执行。
- “健康检查期间无出站请求”目前只有结构性证据：api-admin 只接入 `internal: true` 网络，健康探针只访问 PG 与 Redis。还没有在网络层直接观测。
- Worker 心跳探针 `worker_heartbeats` 归 M03（Ticket 06）；停止 Worker 后 ready 出现 degraded 分项的验证随 Ticket 06 进行。
