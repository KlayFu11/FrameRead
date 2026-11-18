# Issue tracker：本地 Markdown

Issue 和 spec 保存在项目的 `.scratch/` 目录下。

## 文件约定

- 每个功能使用一个目录：`.scratch/<feature>/`。
- 规格文件：`.scratch/<feature>/spec.md`。
- 每个实施任务单独保存为
  `.scratch/<feature>/issues/<NN>-<slug>.md`，从 `01` 开始编号。
- 在任务文件顶部附近使用 `Status:` 记录分流状态，具体取值见
  [triage-labels.md](triage-labels.md)。
- 评论和讨论追加到文件末尾的 `## Comments` 下。

当 Skill 要求发布到 issue tracker 时，在相应功能目录下创建文件；
当 Skill 要求读取任务时，读取用户提供的路径或对应编号的文件。

## Wayfinder 约定

- 地图文件：`.scratch/<effort>/map.md`。
- 子任务：`.scratch/<effort>/issues/<NN>-<slug>.md`。
- 使用 `Type:` 记录 `research`、`prototype`、`grilling` 或 `task`。
- 使用 `Blocked by: NN, NN` 记录依赖；所有依赖已解决后才能开始。
- 使用 `Status: claimed` 表示已领取，`Status: resolved` 表示已解决。
- 按编号查找未领取且未被阻塞的任务；领取时先保存状态。
- 解决时在任务中追加 `## Answer`，更新状态，并在地图中记录结论及链接。

## FrameRead V1 交付入口

正式阶段、依赖和进度的唯一权威是[交付计划 S0～S12](../../.scratch/frameread-v1/delivery-plan.md#delivery-slices)。通用工作流见[项目 AGENTS.md](../../AGENTS.md#ai-coding工作流)，具体阶段使用见[交付计划执行流程](../../.scratch/frameread-v1/delivery-plan.md#development-rules)。本 tracker 不复制阶段表，也不以 Ticket 已解决代表切片运行验收通过。

后续 Implementation Ticket 记录 `Slice: Sx`、实际模块契约版本/章节、相关 R3/A3、可重复且可失败的验收条件和测试入口。`Blocked by: NN` 保持表示本地 Ticket 依赖，阶段和必要公共能力依赖链接到正式交付计划，不与本地编号混用。模块 SPEC、切片记录和证据沿用上述 `.scratch/<feature>/` 目录约定，建立时登记实际路径并回链交付计划。

已有 Decision Ticket 无 `Status:` 或 `Answer` 时不能推定已解决；先按实际决策记录核对。当前[派发待确认投影](../../.scratch/frameread-v1/issues/01-analysis-dispatch-pending-projection.md)仍需在 S6 对应公共状态契约冻结前处理。
