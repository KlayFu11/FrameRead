# DoVideoAI 媒体、前端与本地快照核查

核查日期：2026-11-16。对象为 `D:/VScodeProject/FrameRead/reference-project/DOVideo` 本地文件。本文是静态审计；没有启动服务、执行原项目测试、下载视频、调用模型或安装依赖。

## 1. 快照与可复现边界

DOVideo 是 `Xiaoc7r/DOVideo-AI` 的开源项目（MIT License），本地目录为 `reference-project/DOVideo`。技术栈与版本由 [README.md](D:/VScodeProject/FrameRead/reference-project/DOVideo/README.md:8) 和 [pom.xml](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/pom.xml:8) 观察：Java 21、Spring Boot 3.5.9、Vue 3、MySQL 8、Redis 7、RocketMQ 5.3.4、LangChain4j 1.16.3、FFmpeg、Tesseract、yt-dlp、DeepSeek V3.2、TeleSpeechASR、BGE-M3。

目录结构分三层：`client/`（Vue 3 工作台）、`server/`（Spring Boot API 与 Video Agent）、`extension/`（Chrome 浏览器扩展，含 sidepanel、SSE 解析、Markdown 渲染、URL 解析）。`extension/` 是本项目的一个独特组成部分，VidLens 没有对应物。

依赖声明：[package.json](D:/VScodeProject/FrameRead/reference-project/DOVideo/client/package.json) 使用 Vite、Vue 3、Marked；前端测试用 Vitest（`api.test.js`、`chunkUpload.test.js`、`taskEvents.test.js`、`useAnalysisWorkspace.test.js`、`videoTimestamps.test.js`）。

## 2. 媒体入口、真实能力与成本

| 能力 | 核实位置与执行方式 | 测试证据 | FrameRead 参考判断 |
| --- | --- | --- | --- |
| 分片上传 + 断点续传 | [ChunkUploadService.java:57](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/ChunkUploadService.java:57) 5MB/片，Redis 记元数据与分片索引，MinIO 存分片对象，合并时流式拷贝并算 MD5 | [ChunkUploadServiceTest.java](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/test/java/com/example/server/service/ChunkUploadServiceTest.java) | 中高。分片上传是 FrameRead PRD V3 的正式能力；注册用户归属、普通上传、断点续传与合并幂等（completedKey 防重复插媒体记录）均应按当前产品契约实现 |
| 在线链接导入 | [MediaIngestService.java:39](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/MediaIngestService.java:39) yt-dlp 下载到临时文件，算 MD5 后转存 MinIO，删临时文件 | [MediaServiceTest.java](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/test/java/com/example/server/service/MediaServiceTest.java) | 中。yt-dlp 依赖外部命令，与 VidLens 同构；FrameRead 需自行校验无 Cookie 可达范围 |
| 文件类型校验 | [MediaService.java:46](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/MediaService.java:46) 白名单 mp4/mov/mkv/avi/webm/m4v，文件名规范化 | 同上 | 低，直接保留 |
| 音频切片 | [SegmentedTranscriptionService.java:86](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/SegmentedTranscriptionService.java:86) FFmpeg `-f segment -segment_time 60` 切 60 秒音频 | 无专门测试 | 低中。60 秒窗口与 VidLens 一致 |
| ASR | [SegmentedTranscriptionService.java:31](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/SegmentedTranscriptionService.java:31) 逐片调 AliyunAsrUtils，单片失败不中断，全失败才抛错 | 无专门测试 | 中。ASR 是正式文本主链，需保留单路容错 |
| 关键帧抽取 | [VideoContextService.java:213](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/VideoContextService.java:213) FFmpeg `select=eq(n,0)+gt(scene,0.35)+gte(t-prev_selected_t,30)` 场景变化 + 30 秒保底采样 | 无专门测试 | 中。场景检测 + 保底采样的双保险值得参考 |
| 感知哈希去重 | [VideoContextService.java:229](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/VideoContextService.java:229) dHash（9×8 灰度）汉明距离 ≤5 判重 | 无专门测试 | 低。相邻帧去重避免 OCR 重复烧算力 |
| OCR | [VideoContextService.java:237](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/VideoContextService.java:237) Tesseract 逐帧识别，单帧失败跳过 | 无专门测试 | 中。画面文字是 DOVideo 区分于纯 ASR 方案的关键 |
| 双分支并行 + 容错 | [VideoContextService.java:78](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/VideoContextService.java:78) ASR/OCR 独立线程池并行，单路失败保留另一路，双路都失败才报错 | 无专门测试 | 高。这是 DOVideo 的核心工程亮点，FrameRead 应保留「单路失败降级」的边界 |
| 时序多模态融合 | [VideoContextService.java:267](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/VideoContextService.java:267) 60 秒窗口把 transcript + ocrTexts + evidenceFrames 合并成 VideoSegment | 无专门测试 | 高。统一 VideoSegment 结构是检索与校验的基础 |
| 实际画面时间 | [VideoContextService.java:336](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/VideoContextService.java:336) 解析 FFmpeg `showinfo` 的 `pts_time`，取实际解码时间 | 无专门测试 | 主链。与 VidLens 同构，保留实际时间而非请求时间 |
| 证据帧上传 | [VideoContextService.java:248](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/VideoContextService.java:248) 关键帧 OCR 后上传 MinIO `evidence-frames/` 前缀 | 无专门测试 | 中。证据帧持久化供前端回看 |
| 5 分钟分块摘要 | [DeepSeekUtils.java:241](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/utils/DeepSeekUtils.java:241) `summarizeChunk` 生成 200 字摘要 + 关键词 | 无专门测试 | 中。分块摘要 + Embedding 是长视频检索的前提 |
| 混合检索 | [VideoEvidenceRetrievalService.java:92](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/VideoEvidenceRetrievalService.java:92) 语义 0.6 + 关键词 0.25 + 画面词 0.15，Qdrant 降级本地向量 | 无专门测试 | 高。降级链是容错关键 |
| 向量存储 | [QdrantVectorStore.java:53](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/QdrantVectorStore.java:53) 手动 HTTP 调 Qdrant upsert/search/delete，collection 自动创建 | 无专门测试 | 中。直接 HTTP 而非 SDK，逻辑清晰可参考 |
| 进程边界 | [VideoContextService.java:309](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/VideoContextService.java:309) ProcessBuilder 15 分钟超时 + destroyForcibly | 无专门测试 | 主链。与 VidLens 同构，保留超时与强制终止 |

### 媒体链路的关键差异点

DOVideo 的媒体处理与 VidLens 有三点显著差异，对 FrameRead 的参考判断不同：

1. **OCR 是核心而非辅助**。VidLens 以 ASR/字幕为主，按需抽帧；DOVideo 把关键帧 OCR 提到与 ASR 对等的双分支，画面文字（板书、PPT、代码）是证据的一等来源。这对「视觉设计背景 + 语文教学」的用户场景未必必要，但对需要画面文字证据的场景是更强的能力。
2. **双分支并行 + 单路容错**是明确的设计意图，`finishContext` 里「双路都失败才报错、单路失败保留另一路并记 telemetry」体现了比 VidLens 更强的降级策略，[VideoContextService.java:145](D:/VScodeProject/FrameRead/reference-project/DOVideo/server/src/main/java/com/example/server/service/VideoContextService.java:145)。
3. **分块摘要 + 向量检索**是针对「数小时长视频」的专项能力，VidLens 的 ArticleLoop 不显式做分块向量检索。DOVideo 的 24,000 字符上下文裁剪是一个硬约束，意味着超长视频必然有信息损失，靠混合检索尽量保留相关片段。

## 3. 前端可参考范围与耦合

前端是 Vue 3 + Vite 的单页应用，[App.vue](D:/VScodeProject/FrameRead/reference-project/DOVideo/client/src/App.vue) 是入口。核心状态在 [useAnalysisWorkspace.js](D:/VScodeProject/FrameRead/reference-project/DOVideo/client/src/useAnalysisWorkspace.js) 一个组合式函数中，管理工作台侧边栏的全部状态。

| 范围 | 证据 | 迁移判断 |
| --- | --- | --- |
| API 封装 | [api.js:73](D:/VScodeProject/FrameRead/reference-project/DOVideo/client/src/api.js:73) | 统一解包 `{ code, message, data }` 信封，只对 JSON 解包、SSE/音频原样透传；401 触发 `auth-expired`。强耦合后端信封格式，FrameRead 若用不同契约需重写适配层 |
| SSE 流读取 | [taskEvents.js](D:/VScodeProject/FrameRead/reference-project/DOVideo/client/src/taskEvents.js) | 用 fetch 读 `response.body` 流式解析，非 EventSource；据 `task-status` 事件名分发 |
| 终态判定 | [taskEventsPolicy.js:4](D:/VScodeProject/FrameRead/reference-project/DOVideo/client/src/taskEventsPolicy.js:4) | 4xx 除 408/429 外不重连，网络错误和 5xx 退避重连 |
| 工作台状态 | [useAnalysisWorkspace.js:78](D:/VScodeProject/FrameRead/reference-project/DOVideo/client/src/useAnalysisWorkspace.js:78) | 用 workspaceVersion + captureAuthSession 双重守卫防异步回调串台；goal 与 mode 成对持久化到 localStorage |
| 分片上传 | [chunkUpload.js](D:/VScodeProject/FrameRead/reference-project/DOVideo/client/src/chunkUpload.js) | 5MB 分片，先 init-upload 再逐片传，complete-upload 合并 |
| Markdown 渲染 | [markdown.js](D:/VScodeProject/FrameRead/reference-project/DOVideo/client/src/markdown.js) | Marked 渲染，安全处理 |
| 时间戳跳转 | [videoTimestamps.js](D:/VScodeProject/FrameRead/reference-project/DOVideo/client/src/videoTimestamps.js) | 点击时间戳定位视频画面，与证据帧联动 |
| Demo 模式 | [demoData.js](D:/VScodeProject/FrameRead/reference-project/DOVideo/client/src/demoData.js) | 内置示例数据，`?demo` 参数离线预览工作台，不依赖后端 |

前端的关键工程点是「异步回调串台防护」：`workspaceVersion` 在每次切换视频/目标/重开面板时自增，所有异步回调先校验版本与会话，旧任务的响应不会写到新页面上。这与 VidLens 的 `useVisitor` 的 pending key 语义同构，FrameRead 的 Vue 工作区也需要等价机制。

浏览器扩展 `extension/` 是独立组件，[sidepanel.js](D:/VScodeProject/FrameRead/reference-project/DOVideo/extension/sidepanel.js) 提供侧边栏，[urlParser.js](D:/VScodeProject/FrameRead/reference-project/DOVideo/extension/lib/urlParser.js) 解析当前页面视频链接，[sseParser.js](D:/VScodeProject/FrameRead/reference-project/DOVideo/extension/lib/sseParser.js) 解析后端 SSE。这是 DOVideo 独有的「浏览器内直接解析当前视频」入口。FrameRead 的扩展同样承接登录、当前页或手动链接、导入后分析、SSE 和时间定位，但不直接复制 DOVideo 的解析器与协议。

## 4. 文档与代码差异

[README.md](D:/VScodeProject/FrameRead/reference-project/DOVideo/README.md) 的 mermaid 时序图与源码实现一致，无发现文档声称已实现但代码缺失的能力。README 中「历史示例模型 DeepSeek-R1-Distill-Qwen-32B 已被硅基流动禁用」的说明表明配置层面有过迭代。

## 5. 对 FrameRead 的参考边界

DOVideo 的媒体与检索实现是 Java/Spring 参照，FrameRead 的产品契约以 [PRD V3](../prototype/PRD.v3.md) 和 [SPEC](../prototype/SPEC.md) 为准。

1. ASR、OCR 和关键帧可以并行处理。单一路径失败时保留另一支的真实材料，两支均不可用时按现行上下文错误路径处理，不把失败占位值当作证据。
2. 语音、OCR、帧和时间信息应在 VideoContext 中统一表达，供检索、Agent、报告和追问复用。保留原始区间和来源，不把合并窗口写成逐句精度。
3. Qdrant、本地向量和关键词的降级必须在媒体归属和来源指纹约束下执行。检索基础设施故障可按 SPEC 降级，不能绕过权限或容量护栏。
4. 分块摘要和 Embedding 由长视频需求和真实资源条件驱动，不能因技术名词提前承诺无限时长或固定性能。
5. FrameRead 当前 Web 使用 Vue 3，扩展是独立 MV3 客户端。DOVideo 的异步回调版本、SSE 终态判断和当前页解析方式可作为行为参考，组件和协议需要按 FrameRead 代码适配。

媒体与检索的实现细节属于 FrameRead 当前工程和 SPEC 的职责，不把 DOVideo 的目录、DTO、模型配置或测试数字写成 FrameRead 已实现事实。
