# FrameRead 需求、验收与技术责任追踪

本文只提供正式文档之间的定位关系，不重复产品需求、技术规格或验收正文，也不表示任何实现或验收已经完成。

## 权威入口

- 产品需求与验收矩阵：[PRD.v3.md](PRD.v3.md)
- 产品需求编号：PRD.v3.md 第 4 节的 R3-01～R3-14
- 验收编号：[PRD.v3.md 第 9 节](PRD.v3.md#9-验收矩阵)的 A3-01～A3-22
- 技术模块责任与验收责任：[SPEC.md §11](SPEC.md#spec-traceability)
- 系统模块职责与逻辑依赖：[map.md](../../.scratch/frameread-v1/map.md#module-map)
- 正式 S0～S12 阶段、真实前置和进度的唯一权威：[delivery-plan.md](../../.scratch/frameread-v1/delivery-plan.md#delivery-slices)
- R3/A3 阶段归属与最终完整验收位置：[交付计划覆盖表](../../.scratch/frameread-v1/delivery-plan.md#delivery-coverage)
- 后续开发执行规则：[项目 AGENTS.md](../../AGENTS.md#ai-coding工作流) · [阶段使用流程](../../.scratch/frameread-v1/delivery-plan.md#development-rules)

## 需求与验收定位

| 需求 | PRD 正文 | 主要验收 | 技术责任 |
| --- | --- | --- | --- |
| R3-01 身份、会话与数据隔离 | [R3-01](PRD.v3.md#r3-01-身份会话与数据隔离) | A3-01、A3-19 | [SPEC §11](SPEC.md#spec-traceability) |
| R3-02 本地上传、续传与媒体管理 | [R3-02](PRD.v3.md#r3-02-本地上传续传与媒体管理) | A3-02、A3-11、A3-18 | [SPEC §11](SPEC.md#spec-traceability) |
| R3-03 单视频链接与来源识别 | [R3-03](PRD.v3.md#r3-03-单视频链接与来源识别) | A3-03、A3-04、A3-05、A3-06、A3-18 | [SPEC §11](SPEC.md#spec-traceability) |
| R3-04 平台字幕自动选择 | [R3-04](PRD.v3.md#r3-04-平台字幕自动选择) | A3-07、A3-08 | [SPEC §11](SPEC.md#spec-traceability) |
| R3-05 文本可用性、ASR 回退与时间来源 | [R3-05](PRD.v3.md#r3-05-文本可用性asr-回退与时间来源) | A3-08、A3-09、A3-10 | [SPEC §11](SPEC.md#spec-traceability) |
| R3-06 视频上下文、画面与检索 | [R3-06](PRD.v3.md#r3-06-视频上下文画面与检索) | A3-10、A3-11、A3-13、A3-14 | [SPEC §11](SPEC.md#spec-traceability) |
| R3-07 四模式、自动路由与 Agent 分析 | [R3-07](PRD.v3.md#r3-07-四模式自动路由与-agent-分析) | A3-12、A3-13、A3-15、A3-17 | [SPEC §11](SPEC.md#spec-traceability) |
| R3-08 结构化报告、阅读与结果保存 | [R3-08](PRD.v3.md#r3-08-结构化报告阅读与结果保存) | A3-13、A3-14 | [SPEC §11](SPEC.md#spec-traceability) |
| R3-09 连续追问、反馈与计划修订 | [R3-09](PRD.v3.md#r3-09-连续追问反馈与计划修订) | A3-15 | [SPEC §11](SPEC.md#spec-traceability) |
| R3-10 进度、失败与恢复 | [R3-10](PRD.v3.md#r3-10-进度失败与恢复) | A3-06、A3-10、A3-16、A3-17 | [SPEC §11](SPEC.md#spec-traceability) |
| R3-11 导出、扩展与管理 | [R3-11](PRD.v3.md#r3-11-导出扩展与管理) | A3-18、A3-20 | [SPEC §11](SPEC.md#spec-traceability) |
| R3-12 API、数据、文件与调用质量 | [R3-12](PRD.v3.md#r3-12-api数据文件与调用质量) | A3-01、A3-06、A3-17、A3-18、A3-19 | [SPEC §11](SPEC.md#spec-traceability) |
| R3-13 前端需求与待设计输入 | [R3-13](PRD.v3.md#r3-13-前端需求与待设计输入) | A3-20、A3-21 | [SPEC §11](SPEC.md#spec-traceability) |
| R3-14 可复现运行、测试与工程证据 | [R3-14](PRD.v3.md#r3-14-可复现运行测试与工程证据) | A3-19、A3-20、A3-22 | [SPEC §11](SPEC.md#spec-traceability) |

## 使用规则

1. 需求含义以 PRD.v3.md 为准，技术模块、数据责任、状态合同和验证责任以 SPEC.md 为准。
2. 本表中的验收编号仅指向 PRD.v3.md 第 9 节；验收步骤、输入、预期结果和证据要求不在此复制。
