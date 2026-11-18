# VidLens 多模态 Agent 源码只读审计

审计对象是本地 `D:\VScodeProject\FrameRead\reference-project\VidLens`，范围为 `internal/investigator`、`internal/domain`、`internal/references` 及相关测试。本文只记录源码中已经观察到的调用关系和约束，未修改 VidLens 源码。首轮审计日期为 2026-10-24；2026-10-25 按已确认 FrameRead 需求追加定向复核；2026-11-09 再按“模型/工具如何生成文章与回答问题”核对当前工作树。各轮均未把新设计写成 VidLens 现有能力。

## 审计状态与证据边界

当前依赖版本由 [go.mod:1](D:/VScodeProject/FrameRead/reference-project/VidLens/go.mod:1) 和 [go.mod:5](D:/VScodeProject/FrameRead/reference-project/VidLens/go.mod:5) 观察到：`github.com/cloudwego/eino v0.9.21`、`eino-ext/components/model/openai v0.1.13`、`eino-contrib/jsonschema v1.0.3`，同时存在 `asynq`、`pgx/v5`、`redis/go-redis/v9`。这说明项目把 Eino 放在 Go Agent/模型调用层，把数据库、队列和缓存作为外围工程依赖；具体 Store、worker 和队列实现不在本次审计范围内。

`D:\VScodeProject\FrameRead\reference-project\VidLens` 本地没有 `.git` 目录；主代理核查的 `git status` 和 `git rev-parse` 均返回 `not a git repository`。因此当前 branch、commit SHA 和 worktree 状态未知，不能把本报告绑定到某个提交。

测试文件存在，但本次没有运行 `go test`，也没有启动模型、下载依赖或调用外部服务。按本次现场对三个目标目录直接执行 `*_test.go` 计数（不递归、不包含 `internal/jobs`、`internal/store` 等其他目录），结果是：`internal/investigator` 96 个、`internal/domain` 10 个、`internal/references` 2 个。测试环境代码明确规定：`-short` 跳过 integration；没有所需环境变量时默认跳过，只有 `VIDLENS_TEST_STRICT=1` 才失败，[environment.go:10](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/testenv/environment.go:10)。下文的“测试覆盖”表示代码中存在测试，不表示本次已通过。

## 结论：Eino 是调用编排层，业务闭环由 investigator 和 Store 约束

真正的主入口是 [engine.go:55](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/engine.go:55) 的 `Engine.Run`。它先读取冻结的 snapshot 和 transcript，再按 run 类型读取问答 Turn/已发布文章，恢复 checkpoint，校验执行契约，最后在三条文章路径或问答路径之间分流：

1. `ArticleLoopV1/V2` 进入 [article_loop.go:115](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop.go:115) 的独立文章循环。
2. `ExecutionContractV10/V11/V12` 进入 [workflow.go:50](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/workflow.go:50) 的 server-driven 分阶段 workflow。
3. 旧契约走 Eino ADK Agent：`adk.NewChatModelAgent`、`adk.NewRunner`，入口在 [engine.go:130](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/engine.go:130)。旧路径仍包含 legacy draft/authoring/review/repair。

### 新建文章的默认版本与配置入口

新建 `article.generate` run 的版本选择不由 `Engine.Run` 临时猜测，而是在 Store 的 run admission 阶段冻结。`CurrentArticleContract` 明确是 `ArticleLoopV2`，[execution.go:67](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/domain/execution.go:67)；默认 profile 的 `ArticleHarness` 为空，[config.go:52](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/config/config.go:52)。因此默认新建文章走 `vidlens-article-loop-2026-10-22-v2`，也就是 ArticleLoop V2，而不是 V12 staged workflow 或旧 ADK draft 路径。

配置入口是 profile 的 `article_harness` 字段，[config.go:14](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/config/config.go:14)。创建 run 时，`store.newRun` 先使用 `CurrentArticleContract`，然后读取该 run 的 profile；只有显式设置为 ArticleLoop V1、ArticleLoop V2 或 `vidlens-workflow-2026-10-21-v3`（ExecutionContractV12）时才覆盖默认值，[store.go:294](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/store.go:294)。配置校验也只接受这三个 article harness 值，[config.go:73](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/config/config.go:73)。因此：空值是 ArticleLoop V2；显式 V1 是 ArticleLoop V1；显式 V12 才是 staged workflow。旧 V1–V9 文章契约只能来自历史/恢复路径或测试夹具，不能作为当前新建文章默认值。

如果 checkpoint 中已有完成的 candidate，入口先走 publication；文章和问答最终分别经过 `validateArticle`/`validateAnswer` 及 publication review，[engine.go:348](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/engine.go:348)。因此模型输出不是最终事实，候选、草稿、观察、review、operation 和 checkpoint 才组成可恢复的业务状态。Eino 的 Agent state 只是消息和工具调用的运行时表示，不能替代这些持久记录。

### Eino 在真实调用链中的位置

代码中可以确认的 Eino 使用点如下：

| 能力 | 源码证据 | 实际职责 |
| --- | --- | --- |
| ADK Agent/Runner | [engine.go:140](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/engine.go:140)、[engine.go:146](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/engine.go:146) | 旧路径执行消息到工具调用的循环、最大迭代次数、直接返回工具和顺序执行工具 |
| 消息和多模态 parts | [engine.go:275](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/engine.go:275)、[context.go:387](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/context.go:387) | 用 `schema.Message` 保存文本、tool call、tool result、图片和元数据；图片在 checkpoint 中被剥离，恢复时再加载 |
| 工具节点和工具顺序 | [engine.go:142](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/engine.go:142) | `compose.ToolsNodeConfig` 设置 `ExecuteSequentially` 和未知工具处理 |
| 类型工具和 JSON Schema | [tools.go:376](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/tools.go:376)、[article_loop_wire.go:236](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop_wire.go:236) | `utils.InferEnhancedTool` 从 Go 类型生成工具参数；项目再加严格 JSON、重复键、完整闭合和语义校验 |
| ChatModel/模型传输 | [model.go:146](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/model.go:146)、[model_call.go:55](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/model_call.go:55) | 创建 Eino OpenAI ChatModel，封装 `Generate`，做预算、路由、发送登记、usage、失败映射和重放 |
| review/文章 loop 的单回合工具调用 | [article_loop.go:214](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop.go:214)、[workflow.go:204](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/workflow.go:204) | 每个逻辑回合绑定本阶段工具，由服务端解析和执行，未把业务状态交给 ADK 自动持有 |

Eino 负责模型调用与工具协议。文章草稿、审查结论、配图身份、额度、恢复和发布事务由 VidLens 的 investigator、domain 和 Store 管理。

## 文章流程与问答 loop 的边界

### 文章生成

旧路径的初始构建在 [engine.go:194](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/engine.go:194)：文章先建立全片画面概览，最多 `min(OverviewBins, 12)` 个 bin，视频少于 60 秒时最多 4 个；每个 bin 调 `Media.Inspect`，再把返回的 frame 送入 `imageInput`。旧 Agent 可通过 `find_evidence`、`read_source`、`inspect_video_window`、`record_observation` 定位文字、看帧和持久记录观察，[tools.go:412](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/tools.go:412)；draft 模式再通过 `begin_article`、`save_article_sections`、`submit_article_draft` 保存和提交，[draft.go:148](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/draft.go:148)。

V10–V12 是由服务端推进的阶段式流程，而不是让一个 Agent 自由决定全部阶段。`workflow.go` 定义 `plan/evidence/write/review/revision/recheck/format/answer` 的调用上限，默认总模型发送不超过 20；[workflow_article.go:94](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/workflow_article.go:94) 先做 plan，再按 plan 调查，分批写章节，组装文章，独立 review，必要时一次 revision 后重新组装、校验和 recheck，[workflow_article.go:178](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/workflow_article.go:178)。计划要求章节有有序开始时间、最多 40 章，单章最多两个 investigation，具体约束在 [workflow_article.go:49](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/workflow_article.go:49)。

新的 ArticleLoopV1/V2 在 [article_loop.go:154](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop.go:154) 由服务端控制动态回合：模型每回合只能发一个命名工具调用，工具动作可以读取证据、看图、保存局部章节、patch、finish、停止或请求 review。`finish` 只冻结 candidate，不代表批准或发布；随后按 review scope 做独立核验，候选通过后再由 [article_loop.go:729](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop.go:729) 发布。V2 的 wire 工具和严格单调用协议位于 [article_loop_wire.go:147](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop_wire.go:147)。

2026-11-09 定向补充：V2 并不是“每篇文章必须配图”。校验逻辑允许 V2 在缺少可用解释画面时无图完成；但一旦文章引用图片，该图片仍必须已实际交付、进入 `SeenFrames`、有持久 visible facts，并计入 20 MiB 配图预算，不能把无图许可反推成可以虚构或不核验图片（[validate.go:113-119](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/validate.go:113)、[article_loop.go:779-803](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop.go:779)）。V2 的作者工具描述也明确限制概览后额外新窗口，并允许缺少装饰性/无信息配图时继续正文（[article_loop_wire.go:294-303](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop_wire.go:294)）。

### 问答

`Engine.Run` 对 `qa.answer` 读取当前 Turn 和已发布文章，[engine.go:69](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/engine.go:69)。执行上下文明确把问答和文章写作分开：[execution_context.go:114](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/execution_context.go:114) 在问答中提供完整文章 reading projection、当前问题、问题上下文和历史 turn；当问题涉及原视频时，再读取必要的原文或像素，最后提交 focused answer，不建立全片概览、不生成章节、不完成文章。`QuestionContract` 也明确让 QA 使用独立 adapter，[execution.go:77](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/domain/execution.go:77)。

问答可带一个指定 frame，初始上下文在 [engine.go:199](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/engine.go:199) 交付；QA 文章引用只能作为文章导航，不是原视频证据。问答结果允许 `grounded`、`insufficient_evidence` 或 `out_of_scope`，并由 [validate.go:139](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/validate.go:139) 统一验证。外部资料工具只在当前 Turn 明确允许时启用，见 [references.go:46](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/references.go:46)。

因此不能把“文章 Agent”直接当成 QA Agent。FrameRead 也保持分析与追问的职责边界：分析负责按目标和模式生成结构化报告，追问负责当前问题的最小证据读取和独立答案，不因每个问题重新运行整条分析链。

下文的限制必须按路径理解，不能横向套用到全部实现：legacy V1–V9 使用 `engine.go` 的 ADK Agent、全片 overview、`record_observation` 和 draft tools；V10–V12 使用 `workflow_*.go` 的 server-driven 阶段和独立 stage schema；ArticleLoop V1/V2 使用 `article_loop*.go` 自己的回合、预算和 wire 协议；QA 使用 `execution_context.go`、`answer_*.go` 的 focused reading。尤其是 `engine.go:390` 的主 instructions、旧路径的 overview 数量和旧 draft 工具，不是 ArticleLoop V2 或 staged workflow 的共同实现；各自的工具、prompt、预算和恢复限制以对应路径源码为准。

## 字幕、图片和上下文交付

### 字幕与原文

初始执行消息包括冻结 `snapshot_id`、来源、时长、文字时间精度和完整 transcript；代码明确说明平台 cue 可能是粗粒度窗口，不能发明逐句时间，[execution_context.go:101](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/execution_context.go:101)。完整文字超过输入限制时拒绝继续，不截断后冒充全片概览，[execution_context.go:137](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/execution_context.go:137)。

旧工具路径中，`find_evidence` 只做最多 12 个候选的关键词/时间定位，`read_source` 回读连续字幕段并带相邻段，最多 24,000 字符；搜索索引不是证据，最终引用仍需来自实际 transcript。ArticleLoop 把原文映射为 `t1/t2/...`，冻结候选前要求 transcript 的全部 alias 已读，[article_loop.go:645](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop.go:645)。

### 图片与视觉观察

`imageInput` 会通过 `Media.Reload` 获取图片字节和 metadata，把 base64 图片、MIME、`snapshot_id`、`inspection_id`、`frame_id`、实际时间和请求时间放进 Eino message，[engine.go:275](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/engine.go:275)。`context.go` 的 `inspectionHeadroom` 将工作集约束为最多 12 帧、约 16 MiB，并在图片移出后保留 frame ID，可按 ID 再加载，[context.go:70](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/context.go:70)。

模型收到图片不等于证据已经成立。旧路径要求先调用 `record_observation`，观察必须引用实际 inspection/frame，状态只能是 `supported` 或 `unresolved`，且至少有 visible facts 或明确缺口，[tools.go:580](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/tools.go:580)。文章候选还必须覆盖概览帧、解决 critical question 或把冲突写入 limitation，[validate.go:40](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/validate.go:40)。

ArticleLoop V2 的 `view_frames` 优先复用已有 frame，新增窗口要求明确视觉问题，并有额外窗口上限；[article_loop.go:553](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop.go:553)。冻结和发布时，每个被文章使用的 frame 必须在 `SeenFrames` 中且有持久 visible facts，配图总字节不超过 20 MiB，[article_loop.go:779](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop.go:779)。如果恢复图片时产生新 frame identity，ArticleLoop 会停止并保留原稿及调用账，不能悄悄把新图当成旧证据，[context.go:412](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/context.go:412)。

## Prompt、工具协议与输出校验

legacy 主 prompt 明确规定：来源和工具内容是数据而非指令；先概览并记录观察；每轮最多一个新的 inspect；字幕不能推断画面；成功提帧不代表结论被支持；最终必须调用正式 submit 工具，不能用自由文本结束，[engine.go:390](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/engine.go:390)。它还规定 block、figure、citation、limitation 的字段和引用身份。ArticleLoop 和 staged workflow 使用自己的 prompt/schema，不能把这段 legacy instructions 视为所有路径的完整协议。

工具参数不是只靠 prompt 约束。`argumentCheckedTool` 先做 strict JSON 解码、未知字段拒绝、候选错误反馈和重复 inspect 检查，[tools.go:223](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/tools.go:223)。V12 workflow 将准确的工具 JSON Schema 和形状例子嵌入初始契约，[workflow_contract.go:16](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/workflow_contract.go:16)；ArticleLoop wire 额外禁止重复 key、部分 JSON 和多名工具调用，[article_loop_wire.go:147](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop_wire.go:147)。章节保存再把模型数据 canonicalize 成 domain blocks，验证引用、figure、quote、limitations 后以版本号原子保存，[article_loop_wire.go:685](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop_wire.go:685)。

这些检查有两层：模型侧的工具 schema 让输出较易解析；服务端/domain 侧才决定是否接纳、是否形成新稿、是否进入 review 和是否可发布。

## 证据、时间和引用校验

`validateCitation` 对视频文字引用检查当前 snapshot、片段存在性、ordinal 连续性、range 是否落在实际段窗口、`text_origin` 是否匹配；如果填写 quote，必须是连续原文，不能用意译、摘要或省略号拼接，[validate.go:352](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/validate.go:352)。视频画面引用必须从 Store 读到同一 snapshot 的真实 frame/time；文章中使用的 frame 还必须已有观察或已交付给 ArticleLoop，[validate.go:409](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/validate.go:409)。问答允许 `article_passage`，但 quote 必须匹配不可变文章的真实 block，[validate.go:431](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/validate.go:431)。

ArticleLoop review 再增加一层独立视觉观察：reviewer 必须为 review scope 中每个实际交付的 frame 写独立 visible facts 和 uncertainty，不能复制作者 caption 或作者观察，[domain/article_loop.go:81](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/domain/article_loop.go:81)；`ValidateArticleVisualObservations` 拒绝缺帧、重复帧和空事实，[domain/article_loop.go:214](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/domain/article_loop.go:214)。文章 review 的 evidence quote 还通过 [article_review_binding.go:59](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/domain/article_review_binding.go:59) 做唯一连续逐字绑定，不能使用模糊匹配或改写句子。

外部引用和视频引用也被分开。只有 QA 且当前 Turn 授权外部资料时才注册 URL；搜索片段不是证据，必须读取原始网页后才能引用，[references.go:16](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/references.go:16)。读取服务限制公共 HTML、2 MiB 页面和 12,000 字符正文，并保存 SHA-256 快照，[service.go:26](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/references/service.go:26)、[service.go:154](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/references/service.go:154)。引用校验要求 `content_sha256`、URL、title、read_at 和非空连续 quote 都来自本轮实际读取，[validate.go:354](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/validate.go:354)。

## 规划、生成、审查、修订

### 旧 draft/authoring 路径

旧 Agent 通过 `begin_article` 保存全片 outline 和 concept map，再用 `save_article_sections` 分批保存章节，最后 `submit_article_draft` 触发全量校验和 publication，[draft.go:148](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/draft.go:148)。候选校验失败时 `Engine.tryRepair` 将错误转成新的 repair 回合，并把 checkpoint 交回 `Engine.Run`；repair 受 `MaxIterations`、deadline 和 repair limit 约束，[validate.go:513](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/validate.go:513)。

### 分阶段 workflow

V10–V12 把计划和阶段状态放在服务端：`workflowProgress` 写入 `ExecutionPlan`，包括 overview、outline、write、validate、publish，[workflow.go:356](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/workflow.go:356)。文章阶段先生成 `plan_video_article`，调查 plan 指定的 evidence，再按章节批量写入；文章组装后由独立 review units 检查，只有具体问题才进入 `revise_video_chapters`，随后重新组装、校验和 recheck，[workflow_article.go:251](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/workflow_article.go:251)。

review 单元可以按 section、block、list item、table row 拆分；每个 verdict 需要明确 supported、contradicted、unverifiable 或 not_assessed，非法或不完整结果不会被当作“通过”，[workflow_review.go:45](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/workflow_review.go:45)。review key 会绑定 contract、unit、上下文、source、frame、model 和 config，因此旧 verdict 不能无条件套到新材料。

### ArticleLoop V1/V2 的独立收敛

ArticleLoop 先让作者读原文和必要图片、保存章节，`finish_article` 冻结 candidate；[article_loop.go:636](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop.go:636) 要求完整 transcript coverage、文章结构校验和 evidence fingerprint，再生成 review scopes。V2 review 使用独立像素观察、evidence quote 和 blocking findings。当前候选若与已有 blocking candidate 完全相同，会被拒绝，必须修改受影响内容；[article_loop.go:669](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop.go:669)。

局部 review 只能在 material hash、candidate/evidence identity 和 policy 一致时复用；全文批准和跨章节关系检查不继承旧结论，见 [article_loop_convergence.go:154](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop_convergence.go:154)。这是一个成熟但复杂的收敛协议，包含 review scope、delta review、challenge、修订账和 review cache，适合在核心业务闭环稳定后再逐步引入。

## 预算、错误处理和恢复

启用 model policy 的调用会记录输入字符、文本 token 估算、图片 token 估算、输出 token、安全余量、上下文容量和阶段，[budget.go:13](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/budget.go:13)。文本 token 只是保守 heuristic，不是 provider tokenizer；在该预算路径中输入超过独立限制或总 context 容量时直接返回 resource limit，不会静默截断完整视频，[budget.go:52](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/budget.go:52)。

旧 ADK 路径用 `MaxIterations - checkpoint.Calls`，见 [engine.go:140](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/engine.go:140)。模型传输层还做总时长、首包、idle deadline；普通调用 180/90/60 秒，composition/review/workflow/article loop 可到 300 秒，[model_call.go:25](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/model_call.go:25)。在 staged workflow 或 ArticleLoop 路径中，实际发送由 Store 先登记并限制为最多 20 次；这两类路径下的 QA 发送上限为最多 3 次，未知发送也计入上限，[model_call.go:336](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/model_call.go:336)。legacy QA 不应据此推断有同一个 physical-send ceiling，仍受其自身 profile/iteration 和旧恢复逻辑约束。

2026-11-09 定向补充：模型传输层不只是“封装 OpenAI 调用”。一次逻辑调用会读取当前任务的模型 routes，按冷却、各 route 已发送次数、配置优先级和本任务最近成功 route 排序；route failover 不得静默降低已接受输出预算或截断上下文。物理发送前会登记 operation/submission、记录预算与工具 hash，响应后保存 provider request/usage 信息，未知结果保留为 unknown，不因本地重试账本自动承诺 provider 只执行一次（[model_call.go:198-241](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/model_call.go:198)、[model_call.go:276-306](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/model_call.go:276)、[model_call.go:336-370](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/model_call.go:336)、[artifacts.go:411-551](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/artifacts.go:411)）。

ArticleLoop 会把 calls/sends、no-progress、sections、draft bytes、revisions、media bytes、active deadline 等冻结进预算，最大值可在 [article_loop.go:90](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop.go:90) 和 [article_loop.go:134](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop.go:134) 看到。默认约束包括最多 20 个逻辑回合、40 章、512 KiB draft、48 次 revision、20 MiB 图片和 deadline；连续没有证据或稿件推进会停止。workflow 每个阶段另有上限，定义在 [workflow.go:31](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/workflow.go:31)。

恢复不是简单地把旧消息重新发给模型：

- `checkpoint` 保存执行契约、workflow/article-loop 状态、观察、问题、草稿信息、调用次数、工具消息和 review 账；图片像素从持久消息中剥离，恢复时由 frame ID 重新 hydrate，[context.go:18](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/context.go:18)、[context.go:387](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/context.go:387)。
- 如果旧 Agent 在 assistant tool call 后 worker 失败，`resumePending` 只补执行缺失的 tool result，并逐项持久化，[engine.go:293](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/engine.go:293)。
- 启用 policy 时，模型输入会在物理发送前以 `input:<slot>` 冻结，包含去像素消息、预算和工具 schema；恢复时重新校验工具协议和输入 hash，[model_call.go:97](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/model_call.go:97)。
- 每个逻辑模型 slot 先登记 operation 和 physical submission。provider 结果未知时，ArticleLoop 保留 pending operation，不创建新的 logical slot；截断或 context 超限才缩小章节、原文、图片和 review scope，[article_loop.go:282](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop.go:282)。
- 发布成功必须由终态 run 和 immutable article 回读确认，不能只看某个 step completed，[article_loop.go:759](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop.go:759)。

因此需要明确区分：Eino/`schema.Message` 是模型回合状态；checkpoint、operation、draft version、observation、review 和 run result 才是后端可恢复状态。本文只看到 investigator 对 Store 的这些调用，底层数据库事务和 worker lease 的完整实现见后端审计。

## 测试证据：存在较多针对闭环的测试，但本次未执行

测试代码不是只有 schema 单测，至少可以看到以下可验证意图：

- [answer_once_integration_test.go:16](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/answer_once_integration_test.go:16) 使用 `testsupport.Services`、`httptest` 模型和 `engine.Run`，检查问答首轮必须使用 executable action/tool choice，并检查答案持久化。
- [workflow_integration_test.go:45](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/workflow_integration_test.go:45) 检查 review 结果持久化、只重试无效 unit；[workflow_integration_test.go:90](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/workflow_integration_test.go:90) 覆盖完整 bounded stages 的发布路径。
- [loop_recovery_integration_test.go:17](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/loop_recovery_integration_test.go:17) 用确定性 draft session 和 Eino ADK state 检查 replay、no-progress、拒绝批次后的恢复和物理预算边界。
- `article_loop_test.go`、`article_loop_recovery_test.go`、`article_loop_visual_policy_test.go` 等覆盖单工具调用、输出/图片限制、版本冲突和视觉窗口策略；这些是合成 fixture 或 mock，不等于真实模型理解能力。
- [service_test.go:21](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/references/service_test.go:21) 和 [integration_test.go:14](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/references/integration_test.go:14) 覆盖公共 URL、HTML 清理/截断、持久 read/search、quota 和 no-resend 行为。

由于本次授权明确禁止运行模型、下载依赖，且未启动测试所需的数据库/服务，本报告不宣称测试通过。后续若需要验证，应把 unit、mock HTTP integration、需要 Postgres/Redis 的 integration 分开执行，并记录环境变量和实际命令。

## 2026-10-25 定向复核补充

以下内容是对首轮审计的补充校正，不改变上文中经源码确认的路径边界：

1. **导图是 VidLens 的文章对象事实。** `domain.Article` 固定包含 `mind_map` 字段（`internal/domain/types.go:326-339`），导图结构为根节点和父子节点（`types.go:311-320`）。`validateConceptMap` 要求导图存在、节点数不超过 80、叶节点能定位到章节，并限制分支深度（`internal/investigator/concept_map.go:15-56`）。这段事实不改变 FrameRead 当前结构化报告和无独立文章发布的范围。
2. **关注点与解读深度已有明确语义。** 请求包含 `purpose` 和可选 `detail_level`（`internal/domain/generation.go:40-46`）；当前执行上下文规定 purpose 用于优先调查，不能跳过全片其余内容（`internal/investigator/execution_context.go:105-111`）。三档深度策略分别控制可选调查数和展开要求（`internal/domain/generation.go:65-80`）。FrameRead 可在此基础上显式区分“完整解读”和“关注点专题”，但不能把 VidLens 的 purpose 直接等同于专题模式。
3. **内容来源已经是结构化类型。** `ContentOrigins` 区分 `video` 与 `background_explanation`，只有外部资料开启时才增加 `external_reference`（`internal/domain/generation.go:11-17`）。这为 FrameRead 区分视频证据、报告内解释、一般知识和外部资料提供了源码参照。
4. **模型身份被冻结在业务规格中。** `GenerationSpec` 保存配置 ID、模型和模型 revision（`internal/domain/generation.go:29-39`），文章发布也保存生成模型（`internal/store/shares.go:239-245`）。这说明原项目已经把“进行中任务模型身份不能静默变化”作为业务事实，而不是前端展示字段。
5. **恢复中的图片身份有专门防线。** ArticleLoop 恢复图片时若产生新 frame identity，会停止并保留原稿和调用账（`internal/investigator/context.go:412`）。FrameRead 的源媒体恢复也应沿用“内容身份不一致就失败，不静默替换证据”的原则。

## 2026-11-09 定向核查：LLM/工具链路结论

本轮重新读取当前 `engine.go`、`context.go`、`model_call.go`、`article_loop.go`、`article_loop_wire.go`、`tools.go`、`validate.go` 后确认：用户关心的“LLM 和工具如何协同生成文章、回答问题”已经能从上文还原为以下边界，不需要再搬入更多历史 harness 才能理解原项目：

1. **Worker 只进入 Investigator，不直接理解文章 schema。** `Worker.handle` 对 `article.generate`/`qa.answer` 调 `Engine.Run`；模型、工具、prompt、预算和恢复由 investigator 管，最终仍通过 `Store.Publish`/`CompleteAnswer` 发布（[worker.go:274-278](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/jobs/worker.go:274)、[engine.go:55-193](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/engine.go:55)、[engine.go:348-388](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/engine.go:348)）。
2. **工具调用不是可信边界。** `argumentCheckedTool` 做参数登记、严格 JSON、未知字段与候选错误记录；ArticleLoop wire 更要求一个完整命名 tool call，并拒绝重复 key、部分 JSON 与伴随普通文本（[tools.go:217-315](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/tools.go:217)、[article_loop_wire.go:147-233](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/article_loop_wire.go:147)）。
3. **schema 通过不等于可发布。** 文章和 QA 最终仍分别走 `validateArticle`/`validateAnswer`、证据/引用/图片校验、独立 review/revision，再由 Store 在同一数据库边界发布；自由文本或工具名本身不构成完成（[validate.go:27-168](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/validate.go:27)、[engine.go:348-388](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/engine.go:348)、[artifacts.go:255-346](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/store/artifacts.go:255)）。
4. **文章和 QA 是两条语义不同的链。** 文章有责任完成全片结构化产出；QA 只围绕当前问题读取必要原文/文章/像素并提交 focused answer，不能把 article loop 的 overview、章节与 review 义务套到每个问题上（[execution_context.go:101-156](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/execution_context.go:101)、[answer_composition.go:9-48](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/answer_composition.go:9)）。

## 对 FrameRead 的参考边界

VidLens 的可核对参考价值是业务状态与证据契约的分层。它把媒体快照、文本、帧身份、引用、限制、过程 Checkpoint 和结果保存分开管理，模型输出经过结构校验和服务端规则后才进入业务状态。FrameRead 可按 [PRD V3](../prototype/PRD.v3.md) 和 [SPEC](../prototype/SPEC.md) 采用同类边界。

1. VideoContext 固定同源字幕/ASR、OCR、关键帧、时间区间和来源指纹。检索、四模式 Agent、报告与追问使用同一材料，不能被旧缓存或其他媒体的内容替换。
2. Agent 只输出结构化过程和结果参数。时间证据、来源、模式 Section、预算和警告由 Java 服务校验，Checkpoint 和 MySQL 保存业务事实，Redis 只做协调和短期数据。
3. 文章 loop、发布版本、全片导图和公开分享属于 VidLens 的产品对象。FrameRead 当前核心成果是按目标/模式保存的结构化视频分析报告，不把 VidLens 的文章表、分享 token 或发布事务写入 FrameRead 契约。
4. QA 使用独立的追问和证据检索路径，区分视频证据与片外补充。追问不能触发隐式重新分析或越权读取其他用户媒体。
5. 版本、租约、重试、过时写回和未知模型调用的恢复原则可作为实现参照。FrameRead 的具体消息、Checkpoint、RocketMQ 和 Redisson 合同以 SPEC 为准。

VidLens 的 Go/Eino、文章版本、兼容路径和测试数字是参考对象事实。它们不证明 FrameRead 已实现或已通过运行验收。
