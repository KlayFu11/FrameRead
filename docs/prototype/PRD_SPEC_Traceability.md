# FrameRead V1 需求与技术设计追踪矩阵

日期：2026-11-15。唯一需求入口为[冻结PRD](PRD.md)，设计入口为[SPEC_V1.md](SPEC_V1.md)，决策依据为[ADR](../adr/)。本文是覆盖索引，不新增需求，不代表实现或运行验收通过。P0/P1/P2语义、REQ-01～REQ-18、AT-01～AT-26及S0～S12全部沿用正式PRD。

方法标记：D＝确定性自动化，M＝固定样本人工核对，S＝输入与渲染安全。一个AT可包含多种方法，各部分均须有证据。所有行当前状态为**设计已覆盖，待实现/运行验证**。

## 1. REQ → SPEC → AT → 开发切片

| 需求 | 优先级 | SPEC章节与关键设计 | AT | 开发切片 |
| --- | --- | --- | --- | --- |
| REQ-01 配置与模型选择 | P0 | [3 身份/配置版本](SPEC_V1.md#spec-03)、[4 API](SPEC_V1.md#spec-04)、[5 Schema](SPEC_V1.md#spec-05)、[6 配置表](SPEC_V1.md#spec-06)、[11 ASR](SPEC_V1.md#spec-11)、[13 Provider](SPEC_V1.md#spec-13)、[17 密钥](SPEC_V1.md#spec-17) | AT-01、AT-09 | S1、S2 |
| REQ-02 四类请求行为与身份关系 | P0 | [3 幂等/匹配/复用](SPEC_V1.md#spec-03)、[4 操作API](SPEC_V1.md#spec-04)、[6 唯一约束](SPEC_V1.md#spec-06)、[9 T1](SPEC_V1.md#spec-09)、[15 QA重问](SPEC_V1.md#spec-15) | AT-02、AT-03 | S0首建身份，S3完整行为，S5轮次 |
| REQ-03 任务受理、执行与状态 | P0 | [7 事务](SPEC_V1.md#spec-07)、[9 受理/Outbox](SPEC_V1.md#spec-09)、[10 状态/lease/fence/取消](SPEC_V1.md#spec-10)、[12 发布](SPEC_V1.md#spec-12)、[18 SSE快照](SPEC_V1.md#spec-18) | AT-02、AT-04、AT-05、AT-06、AT-07、AT-08、AT-12 | S0、S1首次发布、S4全故障 |
| REQ-04 来源、媒体和文件生命周期 | P0 | [3 来源/复用](SPEC_V1.md#spec-03)、[6 数据关系](SPEC_V1.md#spec-06)、[11 获取/字幕/真实帧/同源](SPEC_V1.md#spec-11)、[12 安装/引用/GC](SPEC_V1.md#spec-12) | AT-06、AT-09、AT-10 | S1、S2、S8 |
| REQ-05 外部调用、unknown与预算 | P0 | [8 跨进程配额](SPEC_V1.md#spec-08)、[10 恢复](SPEC_V1.md#spec-10)、[13 ledger/发送窗口](SPEC_V1.md#spec-13)、[14 有界修订](SPEC_V1.md#spec-14) | AT-06、AT-07取消交错、AT-13、AT-14 | S1模型、S2收费ASR、S4故障组合、S5共享QA |
| REQ-06 文章、证据、发布与阅读 | P0 | [5 内容Schema](SPEC_V1.md#spec-05)、[11 真实视觉输入](SPEC_V1.md#spec-11)、[12 T6](SPEC_V1.md#spec-12)、[14 graph/证据校验](SPEC_V1.md#spec-14)、[15 reader](SPEC_V1.md#spec-15)、[21 D/M核对](SPEC_V1.md#spec-21) | AT-11、AT-12 | S1、S3、S5 |
| REQ-07 私人追问 | P0 | [5 证据分类](SPEC_V1.md#spec-05)、[6 conversation/turn](SPEC_V1.md#spec-06)、[13 调用](SPEC_V1.md#spec-13)、[15 逐轮/锚点/检索读取](SPEC_V1.md#spec-15)、[17 安全](SPEC_V1.md#spec-17) | AT-15 | S5 |
| REQ-08 Markdown与图文ZIP | P0 | [5 manifest](SPEC_V1.md#spec-05)、[12 读取保护](SPEC_V1.md#spec-12)、[16 确定性离线导出](SPEC_V1.md#spec-16)、[21 离线/恶意内容测试](SPEC_V1.md#spec-21) | AT-10、AT-16 | S6，S8并发生命周期 |
| REQ-09 只读分享 | P0 | [1 双入口](SPEC_V1.md#spec-01)、[4 public API](SPEC_V1.md#spec-04)、[16 固定版本/撤销/新token](SPEC_V1.md#spec-16)、[17 权限隔离](SPEC_V1.md#spec-17)、[22 恢复禁用](SPEC_V1.md#spec-22)、[23 缓存授权](SPEC_V1.md#spec-23) | AT-17，恢复联动AT-23 | S7、S10 |
| REQ-10 管理访问与输入安全 | P0 | [1 拓扑](SPEC_V1.md#spec-01)、[4 管理路由](SPEC_V1.md#spec-04)、[16 资源allowlist](SPEC_V1.md#spec-16)、[17 管理凭据/CSRF/SSRF/渲染/脱敏](SPEC_V1.md#spec-17)、[21 安全负测](SPEC_V1.md#spec-21) | AT-18 | S0开始落实，S5资料/QA，S7完整边界 |
| REQ-11 API与数据库质量 | P0 | [4 错误/受理未确认](SPEC_V1.md#spec-04)、[5 OpenAPI](SPEC_V1.md#spec-05)、[6 字段/约束/索引](SPEC_V1.md#spec-06)、[7 SQLAlchemy/事务/迁移/分页](SPEC_V1.md#spec-07)、[18 连接有界](SPEC_V1.md#spec-18) | AT-08、AT-19、AT-20 | S0、S4、S8 |
| REQ-12 限流、资源与超时 | P0 | [8 quota/期限/磁盘](SPEC_V1.md#spec-08)、[9 有界受理/补投](SPEC_V1.md#spec-09)、[10 资源收敛](SPEC_V1.md#spec-10)、[11 子进程](SPEC_V1.md#spec-11)、[13 调用预算](SPEC_V1.md#spec-13) | AT-14、AT-19 | S1首次执行、S2/S5扩大共享、S4/S8强化 |
| REQ-13 结构化日志、状态与健康 | P0 | [18 SSE与快照](SPEC_V1.md#spec-18)、[19 就绪](SPEC_V1.md#spec-19)、[20 关联日志/健康/排障](SPEC_V1.md#spec-20) | AT-08、AT-13、AT-21 | S0持续交付、S4、S8，S11组织概览 |
| REQ-14 测试、CI与本地部署 | P0 | [7 Alembic升级](SPEC_V1.md#spec-07)、[19 Compose/密钥/重启](SPEC_V1.md#spec-19)、[21 真实依赖/独立Worker/D-M-S/页面](SPEC_V1.md#spec-21)、[24 切片门禁](SPEC_V1.md#spec-24) | AT-20、AT-22 | S0开始，S8全链 |
| REQ-15 配套备份恢复 | P1，完整V1必验 | [6 epoch/恢复状态](SPEC_V1.md#spec-06)、[16 旧token不复活](SPEC_V1.md#spec-16)、[22 一致性备份/门禁/新epoch/恢复中断](SPEC_V1.md#spec-22) | AT-23，分享联动AT-17 | S10 |
| REQ-16 内部运行概览 | P1，完整V1必验 | [4 管理API](SPEC_V1.md#spec-04)、[17 访问隔离](SPEC_V1.md#spec-17)、[20 聚合来源/时间/unknown/ID](SPEC_V1.md#spec-20) | AT-24 | S11 |
| REQ-17 Redis版本内容缓存实验 | P1，完整V1必验；启用可选 | [8 Redis生命周期](SPEC_V1.md#spec-08)、[16 逐次授权](SPEC_V1.md#spec-16)、[23 无/冷/热缓存与回源实验](SPEC_V1.md#spec-23) | AT-25 | S12，可共用S9合格证据 |
| REQ-18 实测性能与资源优化 | P0 | [7 查询测量](SPEC_V1.md#spec-07)、[20 阶段/资源指标](SPEC_V1.md#spec-20)、[23 真实瓶颈/改动/同条件复测](SPEC_V1.md#spec-23) | AT-26 | S9，真实主链具备后可提前 |

## 2. AT → 需求 → SPEC → 验证方法与切片

此反向索引确保所有26个AT均有技术机制和执行方法，不将一个AT的部分子场景通过标为整项通过。

| AT | PRD直接关联 | SPEC入口 | 方法 | 切片 / 补全位置 |
| --- | --- | --- | --- | --- |
| AT-01 | REQ-01 | [3](SPEC_V1.md#spec-03)、[13](SPEC_V1.md#spec-13)、[19](SPEC_V1.md#spec-19) | D | S1 |
| AT-02 | REQ-02、REQ-03 | [3](SPEC_V1.md#spec-03)、[9](SPEC_V1.md#spec-09)、[15](SPEC_V1.md#spec-15) | D | S0新提交、S3重解读/重试、S5问答重发 |
| AT-03 | REQ-02 | [3](SPEC_V1.md#spec-03)、[13](SPEC_V1.md#spec-13)、[16](SPEC_V1.md#spec-16) | D | S3 |
| AT-04 | REQ-03 | [7](SPEC_V1.md#spec-07)、[9](SPEC_V1.md#spec-09) | D | S0 |
| AT-05 | REQ-03 | [9](SPEC_V1.md#spec-09)、[10](SPEC_V1.md#spec-10) | D | S0局部、S4完整 |
| AT-06 | REQ-03、REQ-04、REQ-05 | [3](SPEC_V1.md#spec-03)、[10](SPEC_V1.md#spec-10)、[12](SPEC_V1.md#spec-12)、[13](SPEC_V1.md#spec-13) | D | S4，首次写入S1已具边界 |
| AT-07 | REQ-03，unknown分支联动REQ-05 | [7](SPEC_V1.md#spec-07)、[10](SPEC_V1.md#spec-10)、[12](SPEC_V1.md#spec-12)、[13](SPEC_V1.md#spec-13) | D | S4 |
| AT-08 | REQ-03、REQ-11、REQ-13 | [7](SPEC_V1.md#spec-07)、[18](SPEC_V1.md#spec-18) | D | S4 |
| AT-09 | REQ-01、REQ-04 | [11](SPEC_V1.md#spec-11)、[13](SPEC_V1.md#spec-13) | D+M | S2 |
| AT-10 | REQ-04、REQ-08 | [11](SPEC_V1.md#spec-11)、[12](SPEC_V1.md#spec-12)、[16](SPEC_V1.md#spec-16) | D+S | S8，文件写/保护从S1落实 |
| AT-11 | REQ-06 | [5](SPEC_V1.md#spec-05)、[11](SPEC_V1.md#spec-11)、[14](SPEC_V1.md#spec-14)、[21](SPEC_V1.md#spec-21) | D+M | S1默认完整/视觉，S3模式/深度/focus |
| AT-12 | REQ-03、REQ-06 | [5](SPEC_V1.md#spec-05)、[7](SPEC_V1.md#spec-07)、[12](SPEC_V1.md#spec-12)、[14](SPEC_V1.md#spec-14) | D | S1，S4扩展竞争 |
| AT-13 | REQ-05 | [10](SPEC_V1.md#spec-10)、[13](SPEC_V1.md#spec-13)、[21](SPEC_V1.md#spec-21) | D | S1模型、S2收费ASR、S4恢复组合 |
| AT-14 | REQ-05、REQ-12 | [8](SPEC_V1.md#spec-08)、[10](SPEC_V1.md#spec-10)、[13](SPEC_V1.md#spec-13) | D | S1开始，S2/S5扩大配额，S4/S8强化 |
| AT-15 | REQ-07 | [5](SPEC_V1.md#spec-05)、[15](SPEC_V1.md#spec-15)、[17](SPEC_V1.md#spec-17)、[21](SPEC_V1.md#spec-21) | D+M+S | S5 |
| AT-16 | REQ-08 | [12](SPEC_V1.md#spec-12)、[16](SPEC_V1.md#spec-16)、[21](SPEC_V1.md#spec-21) | D+S | S6 |
| AT-17 | REQ-09，恢复联动REQ-15 | [16](SPEC_V1.md#spec-16)、[17](SPEC_V1.md#spec-17)、[22](SPEC_V1.md#spec-22)、[23](SPEC_V1.md#spec-23) | D+S | S7，S10恢复/重签，S12缓存 |
| AT-18 | REQ-10 | [17](SPEC_V1.md#spec-17)、[21](SPEC_V1.md#spec-21) | D+S | S0基本鉴权、S5资料/QA、S7完整 |
| AT-19 | REQ-11，限流联动REQ-12 | [4](SPEC_V1.md#spec-04)、[7](SPEC_V1.md#spec-07)、[9](SPEC_V1.md#spec-09) | D | S0基本、S4未知提交、S7全路由 |
| AT-20 | REQ-11 | [6](SPEC_V1.md#spec-06)、[7](SPEC_V1.md#spec-07)、[21](SPEC_V1.md#spec-21) | D | S8，schema首次出现即迁移 |
| AT-21 | REQ-13 | [19](SPEC_V1.md#spec-19)、[20](SPEC_V1.md#spec-20) | D+S | S8，基础从S0持续 |
| AT-22 | REQ-14 | [19](SPEC_V1.md#spec-19)、[21](SPEC_V1.md#spec-21) | D+M+S | S8 |
| AT-23 | REQ-15，分享联动REQ-09 | [16](SPEC_V1.md#spec-16)、[22](SPEC_V1.md#spec-22) | D+S | S10 |
| AT-24 | REQ-16 | [17](SPEC_V1.md#spec-17)、[20](SPEC_V1.md#spec-20) | D+S | S11 |
| AT-25 | REQ-17 | [8](SPEC_V1.md#spec-08)、[16](SPEC_V1.md#spec-16)、[23](SPEC_V1.md#spec-23) | D+S | S12 |
| AT-26 | REQ-18 | [7](SPEC_V1.md#spec-07)、[20](SPEC_V1.md#spec-20)、[23](SPEC_V1.md#spec-23) | D | S9 |

## 3. 四项冻结决策追踪

| 最终决策 | PRD与AT | SPEC设计 | ADR与切片 |
| --- | --- | --- | --- |
| 单一管理员凭据，公开分享隔离 | REQ-10、AT-18 | [1](SPEC_V1.md#spec-01)双app、[17](SPEC_V1.md#spec-17)会话/Origin/CSRF、[19](SPEC_V1.md#spec-19)监听与挂载 | 不改账号边界；S0即鉴权、S7完整公开隔离 |
| 旧备份分享默认失效；普通重启保持；重新签发新token | REQ-09、REQ-15、AT-17、AT-23 | [16](SPEC_V1.md#spec-16)状态/资源授权、[22](SPEC_V1.md#spec-22)backup_image/epoch/确认与重签 | [ADR0001修订](../adr/0001-share-a-fixed-article-version.md)；S7、S10 |
| 确定性、固定样本人工、安全三种验收 | REQ-06、REQ-10、REQ-14；AT-11、AT-12、AT-15、AT-18、AT-22及相关安全子场景 | [14](SPEC_V1.md#spec-14)校验与语义边界、[21](SPEC_V1.md#spec-21)D/M/S矩阵和证据模板 | ADR0002内容边界不变；S1起逐项执行 |
| PG快照/关键事件权威，SSE通知与有界恢复 | REQ-03、AT-08 | [7](SPEC_V1.md#spec-07)同事务、[18](SPEC_V1.md#spec-18)游标/缺口/单调revision/临时进度 | ADR0004受理边界不变；S0基础、S4完整 |

## 4. 覆盖结论与运行状态

需求行18项，其中P0为REQ-01～REQ-14及REQ-18共15项，P1为REQ-15～REQ-17共3项，全部有SPEC/AT/切片映射。26个AT均有反向索引，S0～S12的模块/接口/依赖见[SPEC第24节](SPEC_V1.md#spec-24)。P2仍为可选扩展，不纳入默认数据库、存储或部署依赖。

本轮状态只为文档设计覆盖；所有运行、真实媒体/模型质量、故障、浏览器、恢复和性能结果均待实现后按AT留证，未标记任何功能可用或验收通过。后续编码阶段沿此矩阵拆解任务并填入实现/验证证据，不再次改变产品范围。
