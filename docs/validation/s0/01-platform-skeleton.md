# S0 Ticket 01 验证记录：平台骨架可启动

日期：2026-11-16。对应 [Ticket 01](../../../.scratch/s0-local-admission/issues/01-platform-skeleton.md)。

## 环境

- 宿主：Windows，Docker Desktop（Docker 29.9.2，Compose v5.6.1，Linux 引擎 x86_64）。按 SPEC §19，Windows Docker Desktop 属于待验证宿主环境，本记录不代表已在 Linux 宿主机上验证。
- 后端：Python 3.12，依赖由 `backend/uv.lock` 锁定。
- 镜像 digest：固定在 `deploy/compose.yaml` 与 `deploy/Dockerfile.backend` 中。
- 集成测试使用独立容器 `postgres:17-alpine` 与 `redis:7.4-alpine`（与 Compose 相同的 digest）。

## 自动化测试

命令：在 `backend/` 下设置 `FRAMEREAD_TEST_PG_URL` 与 `FRAMEREAD_TEST_REDIS_URL` 后执行 `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`。收尾实现 `431aa59` 的结果：177 passed，无 skip、无 xfail。[01-pytest.txt](01-pytest.txt) 保留初始实现的 176 passed 输出，不包含本次新增的 installed CLI 用例。

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

## Ticket 01 收尾验证

- 完成准确入口 `frameread health live --name worker|control`；入口在加载 Typer、FastAPI 与 SQLAlchemy 前分发至标准库检查，`frameread-live` 继续兼容，Compose 使用准确入口。
- TDD：新增 installed CLI 测试先在原实现上以 3s 超时失败；实现后，缺失、有效、过期心跳三个退出码均正确。完整测试在真实 PostgreSQL/Redis 上为 **177 passed**，命令为 `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`（工作目录 `backend/`）。现有 FastAPI/Starlette 弃用提示 1 条，不影响结果。
- 本地 CI 等价检查：`uv lock --check`、`ruff check src tests`、`ruff format --check src tests`、`mypy`（strict）全部通过；独立镜像 `docker build -f deploy/Dockerfile.backend -t frameread-ticket01:local .` 构建成功。

### 运行时网络观测

脚本：[observe_health_network.py](../../../scripts/observe_health_network.py)。使用独立验收容器，运行新构建的镜像并连接现有真实 PostgreSQL/Redis；保持生产配置与密钥只读挂载，不替换运行中的服务。验收容器额外连接 `frameread_edge` 网络，具有可用的外部默认路由，避免仅靠“没有网络”得出结论。`frameread_internal` 用于依赖连接。

在容器中执行 `python /validation/observe_health_network.py`（将仓库 `scripts/` 只读挂载到 `/validation`）。脚本从 `/proc/net/route` 定位外部默认路由接口，从 `/sys/class/net/<interface>/statistics/tx_*` 读取 Linux 接口计数。先确认 ready 成功，再调用 HTTP live/ready 各 12 次，同时调用已安装的 `frameread health live` 共 24 次；观察窗口跨越至少两个 5s 探针缓存周期。完成健康调用后，单独向 Docker 本地网关发送一个 UDP 对照包，确认计数器能检出流量。

实际结果（不含凭据）：

```json
{"method":"Linux interface TX counters (not packet capture)","interface":"eth0","requests":{"live":12,"ready":12},"installed_cli_calls":24,"installed_cli_max_seconds":0.369,"observation_seconds":20.68,"health_tx_packets":0,"health_tx_bytes":0,"positive_control_tx_packets":1}
```

这证明本次成功健康检查的观察窗口中，外部接口没有发送网络流量；PG/Redis 的内部连接仍正常。它不是抓包，不包含包内容，也不声称覆盖未来新增探针或所有故障组合。原有 internal-only 生产网络继续提供结构隔离。完成后移除本次创建的独立验收容器。

## 验证限制与后续归属

- GitHub Actions（`.github/workflows/ci.yml`）工作流已实现，本地等价检查通过；远端执行未验证，当前任务不执行 push。
- 宿主为 Windows Docker Desktop，Linux 容器内检查不等同于 Linux 宿主部署验证。
- Worker 心跳探针 `worker_heartbeats` 归 M03（Ticket 06）；停止 Worker 后 ready 出现 degraded 分项的验证随 Ticket 06 进行。
