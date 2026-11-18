# DoVideoAI 多模态 Agent 源码只读审计

审计对象是本地 `D:\VScodeProject\FrameRead\reference-project\DOVideo`，范围为 `server/src/main/java/com/example/server/service`（AgentLoopService、AiService、LongVideoContextService、VideoEvidenceRetrievalService、mode/）、`utils/DeepSeekUtils` 及相关测试。本文只记录源码中已观察到的调用关系和约束，未修改 DOVideo 源码，也未运行任何测试、启动模型或调用外部服务。审计日期为 2026-11-16。

## 审计状态与证据边界

DOVideo 的 Agent 能力建立在 LangChain4j 之上。依赖由 [pom.xml:106](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/pom.xml:106) 观察到：`dev.langchain4j:langchain4j-open-ai:1.16.3`，底层模型为硅基流动的 DeepSeek V3.2（[application.properties:30](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/resources/application.properties:30)），Embedding 为 BAAI/bge-m3，ASR 为 TeleAI/TeleSpeechASR。与 VidLens 用 Eino 不同，DOVideo 把 LangChain4j 只当作「OpenAI 兼容模型的 HTTP 客户端 + 轻量 Function Calling 封装」，Agent 的规划、执行、校验、预算和恢复全部由服务端 Java 代码自行编排，不交给 LangChain4j 的 Agent 运行时。

测试文件存在（`AgentLoopService` 相关 `*Test.java` 共 16 个，覆盖 `AgentCheckpointService`、`AgentExecutionBudget`、`EvidenceVerificationService`、`AnalysisDispatchService`、`TaskEventService` 等），但本次未执行。下文「测试覆盖」表示代码中存在测试，不代表本次已通过。

## 结论：受控三轮 AgentLoop，证据校验是服务端代码而非 prompt

真正的主入口是 [AgentLoopService.java:63](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/AgentLoopService.java:63) 的 `AgentLoopService.run`。它与 VidLens 的 ArticleLoop 是同一类设计：模型在每一轮只被要求返回「一份结构化 JSON」，服务端把 JSON 解析成领域对象后，用独立的 Java 校验逻辑（而非再让模型自评）决定是否通过、是否定向补证据、是否终止。差异在于 DOVideo 的收敛远更简单：

1. **Planner → Executor → Critic** 是固定三步，最多 `maxRounds`（默认 2）轮，[AgentLoopService.java:44](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/AgentLoopService.java:44)、[AgentLoopService.java:146](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/AgentLoopService.java:146)。
2. 没有 VidLens 的 review scope、delta review、challenge、review cache 等复杂收敛协议。
3. 证据校验不是靠 Critic 模型自评通过就算数，而是 `EvidenceVerificationService` 在服务端对每条结论做「时间戳落在原始片段内 + source 合法 + claim 逐字绑定」的确定性检查，[AgentLoopService.java:290](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/AgentLoopService.java:290)。

### 新建分析的默认路径与配置入口

`AiService.asyncAnalyze` 是应用层入口，[AiService.java:97](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/AiService.java:97)。它先读 Checkpoint，命中已完成的 `result` 直接复用落库；否则 `resolveContext` 构建/复用 VideoContext，再进入 `agentLoopService.run(mediaId, videoContext, modeRegistry.of(mode))`。

分析模式由 `ModeProfile` 描述。`ModeRegistry` 注册四种模式（GENERAL/LEARNING/REVIEW/CREATION），每种模式携带 plan/execute/critic 三段附加指令和 `requiredSectionKeys`（学习模式要求大纲、自测题、易错点等结构化段落）。`profile == null` 等价于 GENERAL，此时三段指令均为空串，拼接出的 prompt 与引入模式体系前逐字节一致，[AgentLoopService.java:511](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/AgentLoopService.java:511)。这是一个明确的向后兼容约定。

### LangChain4j 在真实调用链中的位置

代码中可以确认的 LangChain4j 使用点如下：

| 能力 | 源码证据 | 实际职责 |
| --- | --- | --- |
| ChatModel 传输 | [DeepSeekUtils.java:84](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/utils/DeepSeekUtils.java:84) | `OpenAiChatModel` 封装硅基流动接口，`maxRetries(0)` 关闭 SDK 内建重试，重试策略由 `chat()` 自行实现，避免嵌套重试 |
| 结构化 JSON 解析 | [DeepSeekUtils.java:375](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/utils/DeepSeekUtils.java:375) | 模型返回文本后剥 ``` 围栏、截取首个 JSON 对象，用 Jackson 反序列化成领域类型；解析失败重发一次「严格返回 JSON」的修正请求 |
| 轻量 Function Calling | [DeepSeekUtils.java:471](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/utils/DeepSeekUtils.java:471) | 仅在追问检索增强时使用：模型声明调用 `searchEvidence` 工具，服务端校验工具名在授权列表内后执行，回填结果，最多 3 轮 |

LangChain4j 负责模型调用和工具协议。服务层执行结构校验、证据检查、计划与结果持久化、预算管理和失败恢复。

## Agent 循环的边界

### 规划（Planner）

`resolvePlan` 先读 Checkpoint 中的 plan，无则调 `deepSeekUtils.plan` 生成 1~5 个可执行任务。`validatePlan` 的规则是确定性的：`understoodGoal` 非空、任务非空、任务数 ≤ 5、每个任务非空且 ≤ 500 字，[AgentLoopService.java:259](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/AgentLoopService.java:259)。结构不合法会先 `repairPlan` 补一次，仍不合法则抛异常终止。Planner prompt 明确要求「任务必须能够仅依靠 VideoContext 中的 ASR、OCR 和时间戳证据完成」，[DeepSeekUtils.java:108](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/utils/DeepSeekUtils.java:108)。

### 执行（Executor）

`executeRound` 调 `deepSeekUtils.execute` 生成 `AnalysisResult`。产物结构固定为 `title + conclusions + evidence + suggestions`（模式化时额外带 `sections`）。Executor prompt 的硬约束是：每条 conclusion 必须绑定至少一条 evidence；`evidence.claim` 必须逐字复制它支持的 conclusion；`timestampMs` 必须落在原始片段内；`source` 只能是 ASR/OCR/ASR+OCR；不得使用视频上下文之外的事实，[DeepSeekUtils.java:270](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/utils/DeepSeekUtils.java:270)。

草稿生成后先 `saveExecutionState` 落盘再进 Critic。这个顺序是断点恢复的关键：如果 Executor 草稿已落盘、Critic 尚未跑就因 MQ 重投而重启，`runWithinBudget` 会识别「result 非空且 critique 为空且 round > 0」直接从 Critic 继续，而不是重新生成整份产物，[AgentLoopService.java:134](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/AgentLoopService.java:134)。

### 校验（Critic）

Critic 分两层：

1. **模型自评**：`deepSeekUtils.critique` 检查目标覆盖、结论-证据绑定、时间戳可核验性、结构完整性，返回 `passed` 与 `feedback/missingRequirements/unsupportedClaims/requiredTimestamps` 四类反馈，[DeepSeekUtils.java:310](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/utils/DeepSeekUtils.java:310)。
2. **服务端确定性复核**：`enforceStructureBounds` 补结构缺陷，`enforceEvidenceBounds` 用 `EvidenceVerificationService` 逐条核验证据能否在原始 ASR/OCR 中定位，把所有无法核验的证据和没有证据支撑的结论强制翻转为 `passed=false` 并追加到反馈，[AgentLoopService.java:290](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/AgentLoopService.java:290)。

这个「模型说通过不算数，服务端再复核一遍」的设计是 DOVideo 与 VidLens 共同的核心价值：schema 通过不等于可发布。

### 定向补充证据与修订

Critic 未通过时，`contextForRetry` 判断是否需要补充证据（有 `requiredTimestamps`/`unsupportedClaims` 时走 `refineForCritique` 定向加载原始片段），`revisePlanForRetry` 仅在 `missingRequirements` 非空时调 `replan` 修订计划，[AgentLoopService.java:375](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/AgentLoopService.java:375)。纯改写（无证据缺口）不重新检索，只重写；证据缺口才追加检索。达到 `maxRounds` 仍未通过时保留警告直接产出结果，不无限循环。

## 长视频检索与上下文选择

对超过 5 分钟的视频，`LongVideoContextService.selectRelevant` 走分段检索，而不是把全片塞给模型，[LongVideoContextService.java:40](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/LongVideoContextService.java:40)：

1. `VideoChunkingService` 把 60 秒片段聚成 5 分钟 chunk，每个 chunk 用模型生成摘要与关键词（`summarizeChunk`），并生成 Embedding。
2. `VideoEvidenceRetrievalService.rank` 做混合打分：语义相似度 0.6 + 关键词匹配 0.25 + 画面文字关键词 0.15，选出 TopK chunk 后细粒度排序到 segment，[VideoEvidenceRetrievalService.java:100](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/VideoEvidenceRetrievalService.java:100)。
3. `withinBudget` 把选中片段裁剪到 24,000 字符以内，[LongVideoContextService.java:90](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/LongVideoContextService.java:90)。

检索的语义召回优先走 Qdrant，Qdrant 或 Embedding 服务不可用时退化为本地余弦相似度 + 关键词，不阻断主分析链路，[VideoEvidenceRetrievalService.java:98](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/VideoEvidenceRetrievalService.java:98)。检索意图（`retrievalIntent`）本身也由模型生成：把目标改写成 semanticQuery + keywords + visualKeywords，模型不可用时用分词兜底。

## 模式路由

`ModeRouter.route` 把用户目标交给模型分类成四种模式之一。设计约束明确写入类注释：路由是增强能力，绝不阻断主流程，任何异常、超时、无法识别的返回值都安全回退 GENERAL；产物一定是四个具体模式之一，绝不会有 AUTO 中间态，[ModeRouter.java:49](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/mode/ModeRouter.java:49)。自动路由本身消耗一次模型调用，因此用独立的用户级（10/min）与全局级（60/min）令牌桶配额，配额不足直接按 GENERAL 继续。

这个「AUTO 只在前端存在、提交前先落定成具体模式」的约定，是为了保证提交、状态查询、重跑三端共用同一套任务身份 key，避免读写端 key 不对称，[AnalysisController.java:85](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/controller/AnalysisController.java:85)。

## 预算、错误处理和恢复

`AgentExecutionBudget` 提供三类终止预算：最大轮次（默认 2）、最大时长（默认 120s）、最大估算 Token（默认 50,000），以及可选的最大估算成本（默认关闭），[AgentLoopService.java:44](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/AgentLoopService.java:44)。`checkBudget` 在每个阶段边界检查，超限抛 `BudgetExceededException` 并计入 `budgetTerminations` 遥测。模型调用超时会区分「超过 Agent 剩余时间预算」（抛 DeadlineExceeded，不可重试）和「普通超时」（可重试），[DeepSeekUtils.java:438](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/utils/DeepSeekUtils.java:438)。

模型调用的重试策略是：最多 3 次，指数退避（1s、2s），仅对 408/429/5xx 可重试，参数错误等 NonRetriableException 直接抛 `IllegalArgumentException`（标记为永久失败），[DeepSeekUtils.java:546](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/utils/DeepSeekUtils.java:546)。

恢复不是简单重发旧消息。Checkpoint 由 `AgentCheckpointService` 管理，键的粒度分两类：

- **内容级**（`mediaId` 为键）：`context`、`chunks`、`feedback`，与用户目标和模式无关，同一视频换目标/模式复用。
- **目标级**（`mediaId + goalDigest(goal, mode)` 为键）：`plan`、`result`、`criticState`、`stage`、`revision`，不同模式的同一目标互不串键。

Checkpoint 以 MySQL 为恢复真源（`agent_checkpoints` 表，[V1__create_core_tables.sql:29](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/resources/db/migration/V1__create_core_tables.sql:29)），Redis 为热缓存（`AgentCheckpointRepository` 先查 Redis 再回源 MySQL）。`VideoContext` 的构建结果（含证据帧地址）也持久化，避免重复 ASR/OCR。

`AiService.resolveContext` 的复用顺序体现了内容级复用的完整语义：本 mediaId 检查点 → 内容级归属索引（contentHash）→ 加内容锁后真正构建。同一视频被多个目标/用户并发提交时，只有一个消费者真正跑 ASR/OCR，其余等待后复用；等待超时（5 分钟）则交由 RocketMQ 重投，等对方落盘后命中复用检查，[AiService.java:161](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/AiService.java:161)。

## 追问与证据检索

`AiService.followUp` 是独立于主分析的第二条链，[AiService.java:289](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/AiService.java:289)。它复用已构建的 VideoContext，用「原始目标 + 已有分析结果（截断 4000 字）+ 追问历史（Redis List，最多 10 轮）+ Function Calling 检索到的证据摘要」拼成上下文，再走一次 `agentLoopService.run` 生成答案。追问历史只存 Redis（7 天 TTL），不是正式业务数据。Function Calling 检索任何异常都不阻断追问主流程，降级为不带增强证据直接回答。

`searchEvidence` 是独立的证据检索接口，返回带时间戳、来源（ASR/OCR/ASR+OCR）和片段摘要的 `VideoEvidenceHit` 列表，[VideoEvidenceRetrievalService.java:47](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/VideoEvidenceRetrievalService.java:47)。

## 测试证据：存在针对闭环的测试，但本次未执行

- [AgentLoopService 相关测试](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/test/java/com/example/server/service/AgentCheckpointServiceTest.java) 覆盖 Checkpoint 读写与模式隔离。
- [AgentExecutionBudgetTest](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/test/java/com/example/server/service/AgentExecutionBudgetTest.java) 覆盖时长/Token/成本三类预算的终止边界。
- [EvidenceVerificationServiceTest](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/test/java/com/example/server/service/EvidenceVerificationServiceTest.java) 覆盖证据时间戳、来源、claim 绑定的确定性校验。
- [AnalysisDispatchServiceTest](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/test/java/com/example/server/service/AnalysisDispatchServiceTest.java) 覆盖提交幂等、限流与投递失败回滚。

由于本次未运行任何测试、未启动模型或中间件，不宣称测试通过。

## 对 FrameRead 的参考边界

DOVideo 的 Agent 层提供可核对的 Java/Spring 实现参照。它坚持模型输出结构化参数、服务端确定性校验、Checkpoint 持久化和预算封顶。FrameRead 的正式实现以 [PRD V3](../prototype/PRD.v3.md) 与 [SPEC](../prototype/SPEC.md) 为准，可采用以下通用原则。

1. `EvidenceVerificationService` 的时间戳、来源和 claim 校验应继续由服务端完成。模型的 Critic 结果是过程信号，不能替代业务校验。
2. 内容级材料与目标/模式级结果分开保存。字幕、ASR、OCR 和帧按媒体来源与内容指纹复用，计划、结果和追问按 `(mediaId, goal, actualMode)` 隔离。
3. AUTO 在提交前确定具体模式，路由失败沿现行错误或约定路径处理。路由能力不能改变媒体归属、分析作用域和恢复身份。
4. 混合检索可以按 Qdrant、本地向量和关键词的现有降级顺序运行。检索故障的降级不能绕过权限、容量和供应商配额边界。
5. DOVideo 的固定轮次、DTO 和测试不能直接作为 FrameRead 合同。FrameRead 保留自己的四模式、报告警告完成、来源固定、异步恢复和追问语义。
