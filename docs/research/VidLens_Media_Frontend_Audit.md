# VidLens 媒体、前端与本地快照核查

核查日期：2026-10-24；2026-10-25 补充导图、导出、分享、配置和恢复；2026-11-09 按前端任务流、媒体处理与进度展示再次定向核对当前工作树。对象为 `D:/VScodeProject/FrameRead/reference-project/VidLens` 本地文件，不以远端最新版本替换本地事实。本文是静态审计；没有启动服务、执行原项目测试、下载视频、调用模型或安装依赖。

## 1. 快照和可复现边界

2026-10-24 核查时 VidLens 没有 `.git`，当时 Git 命令返回 `not a git repository`；2026-10-30 路径检查仍未发现该目录。因此 VidLens 的 Commit SHA、分支、相对 Git 修改状态不能确定，也不能写成 `main` 或“工作区干净”。

2026-10-24 静态枚举记录为 578 个文件，本次未重做全量计数。按扩展名统计，包含空行与注释，不包含依赖目录：

| 类别 | 文件 | 行数 |
| --- | ---: | ---: |
| Go 实现，排除 `_test.go` | 162 | 35,475 |
| Go 测试文件 | 184 | 24,512 |
| TypeScript/TSX 实现，排除 `.test.` | 92 | 15,115 |
| TypeScript/TSX 测试 | 38 | 2,221 |
| SQL 迁移 | 28 | 269 |

这些数字只证明当前源码规模，不证明执行覆盖率、质量或 4～6 周能复刻。没有逐行审阅全部 60,000 多行 Go，而是对入口、主要链路、持久化边界和相关测试定向核查。

依赖声明：[go.mod](D:/VScodeProject/FrameRead/reference-project/VidLens/go.mod:3) 为 Go 1.26.0、Eino 0.9.21、Eino OpenAI component 0.1.13、Asynq 0.26.0、pgx/v5 5.11.0、go-redis/v9 9.23.0。前端 [package.json](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/package.json:1) 声明 React `^18.3.1`、TypeScript `^5.7.3`、Vite `^5.4.14`、Vitest `^2.1.9`；解析 lockfile 得到实际锁定 React 18.3.1、TypeScript 5.9.3、Vite 5.4.21、Vitest 2.1.9，不能把声明下界当成安装版本。

[Dockerfile.backend](D:/VScodeProject/FrameRead/reference-project/VidLens/Dockerfile.backend:1) 使用 Go 1.26.5 构建，运行基础为 Python 3.12 slim，并带 FFmpeg、yt-dlp 2026.8.19、Deno 2.9.6。[Compose](D:/VScodeProject/FrameRead/reference-project/VidLens/compose.backend.yaml:1) 声明 PostgreSQL 17、Redis 7；Redis 配置 AOF 和 `noeviction`。这表明媒体能力已依赖成熟外部程序，并非所有计算都在 Go 内执行。

## 2. 媒体入口、真实能力与成本

| 能力 | 核实位置与执行方式 | 测试证据，仅已阅读或定位 | FrameRead 参考边界 |
| --- | --- | --- | --- |
| URL 标准化 | [domain/source.go:16](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/domain/source.go:16) `ParseSource`，HTTPS、Bilibili BV+分P、YouTube watch/shorts/youtu.be；标准化为 source identity | [source_test.go](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/domain/source_test.go:1) | 中；FrameRead 只接受经安全校验的公网 HTTP(S) 单视频输入，平台与分 P 身份保持独立，列表/合集明确拒绝 |
| Bilibili 接入 | [bilibili.go:130](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/bilibili.go:130) 公开 API，解析 track、字幕，下载含受限重试；[source.go:158](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:158) 使用该分支 | [bilibili_test.go:34](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/bilibili_test.go:34)、[bilibili_integration_test.go:21](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/bilibili_integration_test.go:21) | 中高，主要难点是平台访问和完整性；参考该适配数据流。B 站是最终成品必须支持的平台，验证无 Cookie 的实际可达范围 |
| YouTube 接入 | [source.go:35](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:35) 限制视频格式；[download.go:62](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/download.go:62) 调用 yt-dlp；禁用浏览器 Cookie 获取 | [download_test.go:49](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/download_test.go:49)、[integration_test.go:112](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/integration_test.go:112) | 中；采用 yt-dlp 进程能力，YouTube 与 B 站均纳入最终验收；网络可达与受限链接分别验证 |
| 视频、音频获取 | [source.go:265](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:265) 可提前获取音频；[source.go:393](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:393) 视频无音轨时获取独立音频，并检查合计字节 | [source_parallel_integration_test.go:20](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source_parallel_integration_test.go:20) | 中；串行基线后按网络/磁盘瓶颈采用有界并发，保留大小、超时、截断验证与取消清理，不以协程数作为吞吐证据 |
| 字幕采用决策 | [subtitle_selection.go:44](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/subtitle_selection.go:44) 候选排序和尝试；[subtitles.go:19](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/subtitles.go:19) VTT/SRT/JSON；[source.go:334](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:334) 检查覆盖率 | [subtitle_selection_integration_test.go:16](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/subtitle_selection_integration_test.go:16) | 低中；正式文本主链。50% 可用/85% 完整是原实现的 cue 时间并集阈值，不等于语义准确率或语音覆盖率 |
| ASR 降级 | [asr.go:25](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/asr.go:25) 缺配置明确报错；60秒窗口、最多2个并发，按原顺序提交进度；[asr.go:120](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/asr.go:120) 操作级结果复用 | [asr_parallel_integration_test.go:18](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/asr_parallel_integration_test.go:18) | 中；缺字幕时的 ASR 是最终成品链路，服务独立配置。若仅返回整段文字，按窗口标时间与精度，不能伪造逐词对齐 |
| ASR 缓存复用 | [source.go:360](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:360) 检查实际含音频媒体的完整 hash 和 pipeline/provider 配置 | [integration_test.go:154](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/integration_test.go:154) | 中；失败重试的有效阶段复用属于可靠性要求；跨任务内容缓存另按收益论证。均不能只按 URL 复用，需核对源内容、处理参数和配置版本 |
| 按需取帧 | [frames.go:39](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/frames.go:39) `Inspect`，单次1～6帧，普通窗口最长60秒，支持裁剪/重新加载 | [integration_test.go:21](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/integration_test.go:21) | 中；参考有界窗口、实际解码时间和父帧关系，FrameRead 的取帧边界按 VideoContext、Agent 和资源预算合同验证 |
| 实际画面时间 | [frames.go:156](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/frames.go:156) FFmpeg `showinfo`，解析 `pts_time`，保存实际解码时间而非只用请求时间 | 同上，测试生成独立样本并校验真实帧时间 | 主链；Java 服务调用媒体工具时仍需保存实际解码时间和精度 |
| 媒体缓存 | [frames.go:133](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/frames.go:133) key 含 snapshot、时间、模式、crop、version；命中后仍检查 DB asset、文件存在、Pin | 同上及 resource 测试 | 保留 DB 唯一键、文件校验和引用保护；Redis 加速按热点与对照测量决定，不能取代资产有效性检查 |
| 全片导图 | `domain.Article` 固定包含 `mind_map`（[types.go:311-320](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/domain/types.go:311)、[types.go:326-339](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/domain/types.go:326)）；发布前校验导图层级、叶节点章节定位和深度（[concept_map.go:15-56](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/concept_map.go:15)）；阅读页渲染导图（[ReadView.tsx:15](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/ui/ReadView.tsx:15)、[MindMap.tsx:1](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/ui/MindMap.tsx:1)） | [concept_map_test.go:1](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/exporting/concept_map_test.go:1)、[mindLayout.test.ts:1](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/ui/mindLayout.test.ts:1) | 导图是 VidLens 现有文章结构的一部分。FrameRead 不将该文章对象或导图发布流程写入当前产品合同 |
| 进程边界 | [process.go:75](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/process.go:75) Unix 进程组、取消时杀子进程组、输出/工作区限制；RSS 只观察主子进程 | [transport_test.go:14](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/transport_test.go:14) 不完整下载不能成为可发布文件 | FrameRead 按 Compose 加宿主机应用/媒体工具的运行边界执行进程组、取消、输出、工作区和资源限制；调用封装不能代替进程治理 |
| 文件归属与清理 | [files.go:68](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/files.go:68) hash、归属、rename；视频/音频不自动过期。[cleanup.go:12](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/cleanup.go:12) DB 删除租约、Pin、待删资源、失败标记、有限孤儿清理 | [manage_test.go:14](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/manage_test.go:14) 删除原视频保留已发布帧 | 中；正式资产长期保留、原媒体清理/同源恢复、临时文件和失败清理均为成品要求；高级配额后台不是必需。删 Redis key 不等于删除媒体 |
| Markdown / ZIP | [exporting/service.go:51](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/exporting/service.go:51) 读取已发布文章、确定性渲染、临时文件、hash、路径和体积限制，不再调用模型；ZIP 含 `article.md`、本地图片、`sources.json` 与 `manifest.json`，缺图/hash 不符会失败（`service.go:99-195`） | [service_test.go:85](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/exporting/service.go:85)、[citation_timing_test.go:26](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/exporting/citation_timing_test.go:26)、[concept_map_test.go:1](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/exporting/concept_map_test.go:1) | VidLens 的导出实现属于参考对象。FrameRead 当前合同提供 Markdown、转写文本和 MP3 导出，不把文章 ZIP 作为当前必需对象 |

### 2026-11-09 媒体链路定向补充

上表已经覆盖主能力；本轮再补几条对 FrameRead Java/Spring 实现有直接影响的当前源码事实：

1. **下载边界比“调用 yt-dlp”更具体。** YouTube 视频格式被限制为 1080p 内的 HTTPS/mp4 候选，下载参数显式 `--ignore-config`、`--no-cache-dir`、`--no-playlist`、`--no-cookies`、`--no-cookies-from-browser`；YouTube 还指定 Node JS runtime 并禁止借用浏览器/共享 Cookie。下载完成后再用 ffprobe 校验真实视频轨、音频轨、时长和分辨率，不完整下载不能进入后续生成（[source.go:35-59](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:35)、[source.go:314-329](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:314)、[source.go:573-612](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:573)）。
2. **字幕采用是有限尝试，不是“找到一种就停”。** 当前决策版本为 `subtitle-adoption-v2`，语言按 zh-Hans/zh-CN/zh/en 等优先级排序、手工字幕优先于自动字幕、格式优先级为 json3/vtt/srt/json；最多尝试 3 个候选，并且复用最初 `--dump-single-json` 得到的 `source-info.json`，避免二次抓取改变轨道或签名地址。每次尝试、解析结果、coverage 和 fallback reason 都写入 source diagnostic（[subtitle_selection.go:44-80](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/subtitle_selection.go:44)、[subtitle_selection.go:82-155](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/subtitle_selection.go:82)、[source.go:250-260](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:250)）。
3. **ASR 只在字幕不可用且确有音频时进入。** YouTube 会在字幕 coverage 不足时预取音轨；若视频本身无音轨，则另行下载 audio，且视频与独立音频的合计字节不能超过下载上限。ASR 将音频切成 60 秒窗口，最多两个上传 worker，但按原顺序提交进度和拼接结果；窗口级 operation 支持失败后有限复用，provider request ID 与结果持久化（[source.go:262-296](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:262)、[source.go:389-455](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:389)、[asr.go:25-118](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/asr.go:25)、[asr.go:120-208](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/asr.go:120)）。
4. **截图是持久 operation，不是临时函数返回值。** 同一 `inspect` key 完成后可直接恢复；缓存命中仍校验 asset 状态、文件存在与 pin。普通窗口一次最多 6 帧、窗口最长 60 秒，必须解析 FFmpeg `pts_time` 得到实际解码时间；单帧最大 2 MiB，单次 inspection 总载荷 8 MiB，文章和 QA 的预留预算分别为 20 MiB/8 MiB。裁剪必须来自已交付的 parent frame，并继承父帧实际时间（[frames.go:39-86](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/frames.go:39)、[frames.go:127-225](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/frames.go:127)）。
5. **媒体子进程有独立资源治理。** FFmpeg/yt-dlp 通过进程组启动，取消时 kill 整个进程组；stdout/stderr、工作区字节、停滞时间、主进程 RSS 都有上限。仅以异步调用封装而不保留这些治理，会丢掉原实现的重要后端价值（[process.go:46-147](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/process.go:46)）。

原实现的 `local://` 是显式开启 `dev_media_dir` 后的开发样本通道，不是浏览器用户上传视频功能，见 [source.go:116](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:116) 和 [startup.md:39](D:/VScodeProject/FrameRead/reference-project/VidLens/docs/backend/startup.md:39)。固定本地样本可作为 FrameRead 测试输入，但不等同于浏览器用户上传产品功能。

## 3. 前端可参考范围与耦合

页面链路在 [App.tsx:45](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/app/App.tsx:45)：输入、运行、阅读、历史；`/r/:id` 恢复某次请求。它已有阅读和选段逻辑，适合参考业务交互。

| 范围 | 证据 | 迁移判断 |
| --- | --- | --- |
| 阅读、块内容、引用、帧查看 | [ReadView.tsx:15](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/ui/ReadView.tsx:15)、[Blocks.tsx:81](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/ui/Blocks.tsx:81) | 作为参考对象按 props、状态依赖和新 API 契约评估交互复用，不直接沿用组件实现 |
| API 封装 | [http.ts:50](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/api/http.ts:50) | 强耦合原 `/api/v1/requests`、契约版本头、CSRF、cookie、错误结构、幂等返回头，不能只换 base URL |
| 请求重放 | [writes.ts:58](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/api/writes.ts:58)、[useVisitor.ts:310](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/app/useVisitor.ts:310) | 保留“网络失败沿用同一幂等键”的语义，配合后端唯一约束；按钮禁用不足以去重 |
| 实时同步 | [runtime.ts:45](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/api/runtime.ts:45)、[live.ts:70](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/api/live.ts:70) | 实际是 EventSource/SSE，`LiveSocket` 名称不表示 WebSocket；事件类型含 snapshot/upsert/reset/auth_required |
| 断线恢复 | [live.ts:174](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/api/live.ts:174) | 退避重连，先 HTTP 获取快照和 cursor，再订阅；schema/scope不符触发恢复，不靠内存状态撑刷新 |
| 状态与结果契约 | [types.ts:1](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/contract/types.ts:1) | 原 Request/Turn/Run/Phase 是不同层次；FrameRead 的状态以当前 HTTP/SSE 合同中的 TaskStatus、TaskStage 和作用域字段为准，不能直接沿用参考对象的适配层 |
| 执行过程、计划和管理后台 | [RunView.tsx:15](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/ui/RunView.tsx:15)、`frontend/src/site` | 绑定大量原 article loop、budget/model、site capacity 数据。FrameRead 只做阶段、失败、重试和耗时等必要任务状态，不复刻站点运营后台；这不删除最终成品的任务可靠性要求 |

2026-11-09 定向补充：任务页把“数据消费”和“视觉呈现”分得很清楚。前端先用 HTTP snapshot 安装 request/turn 权威状态，再通过 EventSource 更新；`RunView` 从 view 中拆出阶段、当前动作、最近步骤、计划、画面、模型调用和可用操作，而不是自行计算后端是否完成。提交入口在跳转前保存 pending idempotency key，QA 发送也校验上一 turn 是否终态，取消/重试以后端返回的新 view 为准（[useVisitor.ts:269-328](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/app/useVisitor.ts:269)、[useVisitor.ts:509-544](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/app/useVisitor.ts:509)、[useVisitorConversation.ts:297-424](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/app/useVisitorConversation.ts:297)、[RunView.tsx:69-104](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/app/RunView.tsx:69)）。FrameRead 的 Vue 工作区也需要同步这种 view/动作契约，不能只复用视觉样式。

前端已有 38 个 `.test.` 文件，不代表全部组件有行为覆盖，更不表示本轮测试通过。可借鉴 `api/live.test.ts`、`api/writes.test.ts`、`contract/stream.test.ts` 的断线与重复写场景，适配后需重新验收。

## 4. 文档与代码差异

[startup.md:52](D:/VScodeProject/FrameRead/reference-project/VidLens/docs/backend/startup.md:52) 仍写公开分享未实现，但 [http.ts:139](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/api/http.ts:139)、后端 shares 路由与存储、README均显示已有分享功能。判断以本地实际实现为准，不能逐段复制旧文档。

[scripts/verify.py:1](D:/VScodeProject/FrameRead/reference-project/VidLens/scripts/verify.py:1) 提供 `unit/full` 验证模式，full 依赖独立测试 PostgreSQL/Redis、FFmpeg和私有能力样本；跳过测试会被分类，不等于通过。[startup.md:43](D:/VScodeProject/FrameRead/reference-project/VidLens/docs/backend/startup.md:43) 的 smoke 可能调用真实模型/ASR，本轮不运行。

## 5. 2026-11-18 定向复核：媒体、前端与 FrameRead 边界

以下事实只描述 VidLens 的实现，FrameRead 的产品边界以 [PRD V3](../prototype/PRD.v3.md) 和 [SPEC](../prototype/SPEC.md) 为准。

1. VidLens 的 Markdown/ZIP 导出、公开分享、图片 allowlist 和文章导图属于参考项目能力。FrameRead 当前契约提供 Markdown、转写文本和 MP3 导出，不把 VidLens 的文章发布或公开分享对象写入产品契约。
2. VidLens 的模型配置分为访问者选择和运营后台。FrameRead 使用用户账户、管理员失败任务权限和项目规定的模型配置入口，不复制 VidLens 的管理站路由。
3. VidLens 恢复媒体时核对 snapshot 内容身份。FrameRead 采用同源媒体、来源指纹、时间和对象引用校验，重新导入不能用 URL 相同替代内容相同。
4. VidLens 的前端状态快照、SSE 重连、断线恢复、当前页解析和资源生命周期是实现参照。FrameRead 的 Web 使用 Vue 3，扩展使用 MV3，需按当前 HTTP/SSE 合同重新验证。
5. 媒体与数据库的一致性、删除保护、资源引用和错误诊断属于 FrameRead 完整交付要求。参考项目的实现事实不代表 FrameRead 已通过运行验收。

## 7. 本次文件指纹与只读验证

2026-10-24 首轮审计记录：对当时578个文件保存SHA-256基线并在当轮收尾比较，新增/改动0、删除0。该结果仅属于当轮检查，不表示2026-10-30再次完成同样的全量验证，也不替代Git历史。以下关键文件hash用于定位原审计版本；后续文件变化时须重新核查对应结论。

2026-10-30 与 2026-11-09 收尾均重新计算了下表12个关键文件的SHA-256，12/12与记录一致。2026-11-09 本轮同时定向读取了 HTTP/SSE、Worker、媒体处理、持久化、Agent 与运行页实现；这个定向检查不覆盖其余文件，也不表示已重新逐行审完所有源码或运行通过。

| 文件（相对 `D:/VScodeProject/FrameRead/reference-project/VidLens`） | SHA-256 |
| --- | --- |
| `go.mod` | `8c08196b8bde0437bcf74b4c722697c29ef7e75bcc6a9666ab3ee6633766d55b` |
| `go.sum` | `4b15d26be3a95a29f9593d720a6c27febc70cdf720fceef66f55f453236278a8` |
| `frontend/package-lock.json` | `007e825f837b281a5bd72587e89ee27432a3586763cc94b31b6ef12e04db3186` |
| `internal/domain/execution.go` | `299be13e9baef1fea318c4d2bbf86ec9003ee52ee81454ebbbda1151c3dd787c` |
| `internal/investigator/engine.go` | `11f1be905b2e65eed0b6fb9b151a8e3754eac8de10e8d96b19890e281c20e7f0` |
| `internal/investigator/article_loop.go` | `0664885e375ee31c03add0d675458d881ff172637ec905117a53faa71521129f` |
| `internal/store/execution.go` | `e2af0a94188fac07b8b86800ac1fd42588f6bf786bb83fd018f230b3bc9990e1` |
| `internal/store/migrations/001_init.sql` | `fab209e114fbcb95da77a65f629e670f4366e7416977d2f13c28651300eb47ce` |
| `internal/jobs/worker.go` | `52c79c37ed503051dcabe4f08b902544c52117fa353e1311cb24e14a1ddef6d7` |
| `internal/media/source.go` | `678a03e9f399b13c220e18b4113202ab7c80c1b2fdf1e729970972f988573c4c` |
| `frontend/src/api/http.ts` | `9383333dbcc6a78fb5a78d330fe27a269f1ef249c82a09319838d26df7ca6672` |
| `compose.backend.yaml` | `f74a4aee854bc7f94d4b042db5a06f6d67f20aa4349eb996a7a6d6cf6736b7ab` |
