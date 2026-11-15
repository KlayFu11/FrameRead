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
