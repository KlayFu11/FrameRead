# 批次 A 模块 SPEC 编写约定

供编写 M01、M02、M03、M04、M12 模块 SPEC 共用。模块 SPEC 确认后本文可删除。

## 依据（按优先级）

1. [grill-batch-a.md](grill-batch-a.md)：用户逐条确认的 Q1～Q46 决定，必须全部体现在对应模块 SPEC 中，不得改变或新增决策。
2. [map.md](map.md) §2 决策 D1～D5、§3 模块条目、§5 事务归属、§9 目录映射。
3. [SPEC_V1](../../docs/prototype/SPEC_V1.md) 对应章节（模块条目中的 "SPEC" 行），[PRD](../../docs/prototype/PRD.md) §6 S0 行及相关 AT，[GLOSSARY](../../GLOSSARY.md)，[ADR](../../docs/adr/)。

冲突时以 PRD/ADR/SPEC_V1 为准，并在 SPEC 的“补充说明”中列出冲突，不自行裁决。

## 范围

覆盖模块在 V1 中的全部职责，但每条实现决定标注落地切片（如 “S0”“S1 接入 M08 后”“S8”）。S0 的范围以 PRD §6 S0 行为准：Compose 增量启动、页面提交/查询受控视频任务、Worker 领取、记录阶段后取消结束；AT-02 新提交子场景、AT-04 全项、AT-05 受理后未发送/重复消息；基础 AT-19/21；空库迁移。

## 统一测试接缝（所有模块共用，不另造）

1. **HTTP 接缝**：真实运行的 admin app（经 httpx ASGI 客户端或 Compose 中的 gateway），后端为真实 PostgreSQL 与 Redis。外部行为通过状态码、错误体、`TaskSnapshot` 与数据库最终状态断言。
2. **进程接缝**：独立运行的 Worker 与 control 进程（不在测试进程内替身），用于投递、Claim、取消、重复消息、受理后未投递等场景。
3. **CLI 接缝**：`frameread` 命令（secrets/maintenance/policy/openapi/admin），断言退出码、输出与数据库状态。
4. **纯函数接缝**：`normalize_video_input`、`request_digest`、`parse_video_url`、KeyRing 派生、前端快照合并函数，表驱动单测。
5. **浏览器接缝**：Playwright 通过 gateway 操作管理页面。

原则：只测外部可见行为，不断言内部调用次数或私有函数；不允许为测试在生产代码中加开关；故障手段在 S0 只用外部方式（Grill Q25）。仓库尚无代码，测试先例为空，按上述接缝新建。

## 文件与格式

- 路径：`.scratch/<模块目录>/spec.md`，模块目录取 map.md §3 的英文目录名。
- 中文撰写，技术术语与标识符保留原文；使用 GLOSSARY 术语。
- 不写具体文件路径或代码片段（目录映射已在 map.md §9，链接即可）；接口名、表名、错误码、字段名可以写。
- 已有说明用相对路径链接到 SPEC_V1 具体章节锚点（如 `../../docs/prototype/SPEC_V1.md#spec-07`），不复制正文。
- 文件头：

```
# <Mxx 模块名> 模块 SPEC

Status: ready-for-agent
日期：2026-11-15。依据：Grill 批次 A（链接）、模块地图 §3 Mxx（链接）。
```

- 章节固定为：`## 问题陈述`、`## 解决方案`、`## 用户故事`（编号，格式“作为<角色>，我希望<功能>，以便<收益>”；角色可用 部署者、运维中的部署者、后续模块开发者（Agent）等；要非常完整，覆盖正常、失败、并发、恢复、安全与可观测）、`## 实现决定`（按子主题分组，每条标落地切片）、`## 测试决定`（引用上面的接缝编号，列出 S0 必测场景与对应 AT）、`## 不在范围内`、`## 补充说明`（含与其他模块的接口约定、待后续模块 Grill 的事项）。
