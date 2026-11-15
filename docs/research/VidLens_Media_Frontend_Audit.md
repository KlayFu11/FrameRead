# VidLens 媒体、前端与本地快照核查

核查日期：2026-10-24；2026-10-25 补充导图、导出、分享、配置和恢复；2026-10-30 按用户确认的项目归属与后端学习目标校正文档范围；2026-11-09 按前端任务流、媒体处理与进度展示再次定向核对当前工作树。对象为 `D:/VScodeProject/FrameRead/reference-project/VidLens` 本地文件，不以远端最新版本替换本地事实。本文是静态审计；没有启动服务、执行原项目测试、下载视频、调用模型或安装依赖。

## 1. 快照和可复现边界

2026-10-24 核查时 VidLens 没有 `.git`，当时 Git 命令返回 `not a git repository`；2026-10-30 路径检查仍未发现该目录。因此 VidLens 的 Commit SHA、分支、相对 Git 修改状态不能确定，也不能写成 `main` 或“工作区干净”。FrameRead 则已于 2026-10-30 初始化独立 Git 仓库，分支 `main`，尚无提交；两者版本状态不能混写。

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

| 能力 | 核实位置与执行方式 | 测试证据，仅已阅读或定位 | Python 成本与保留建议 |
| --- | --- | --- | --- |
| URL 标准化 | [domain/source.go:16](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/domain/source.go:16) `ParseSource`，HTTPS、Bilibili BV+分P、YouTube watch/shorts/youtu.be；标准化为 source identity | [source_test.go](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/domain/source_test.go:1) | 低；主链保留白名单、分P独立身份，不把不同视频合并 |
| Bilibili 接入 | [bilibili.go:130](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/bilibili.go:130) 公开 API，解析 track、字幕，下载含受限重试；[source.go:158](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:158) 使用该分支 | [bilibili_test.go:34](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/bilibili_test.go:34)、[bilibili_integration_test.go:21](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/bilibili_integration_test.go:21) | 中高，主要难点是平台访问和完整性；直接参考既有适配数据流。B 站是最终成品必须支持的平台，验证无 Cookie 的实际可达范围 |
| YouTube 接入 | [source.go:35](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:35) 限制视频格式；[download.go:62](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/download.go:62) 调用 yt-dlp；禁用浏览器 Cookie 获取 | [download_test.go:49](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/download_test.go:49)、[integration_test.go:112](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/integration_test.go:112) | 中；复用 yt-dlp 进程能力，YouTube 与 B 站均纳入最终验收；网络可达与受限链接分别验证 |
| 视频、音频获取 | [source.go:265](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:265) 可提前获取音频；[source.go:393](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:393) 视频无音轨时获取独立音频，并检查合计字节 | [source_parallel_integration_test.go:20](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source_parallel_integration_test.go:20) | 中；串行基线后按网络/磁盘瓶颈采用有界并发，保留大小、超时、截断验证与取消清理，不以协程数作为吞吐证据 |
| 字幕采用决策 | [subtitle_selection.go:44](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/subtitle_selection.go:44) 候选排序和尝试；[subtitles.go:19](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/subtitles.go:19) VTT/SRT/JSON；[source.go:334](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:334) 检查覆盖率 | [subtitle_selection_integration_test.go:16](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/subtitle_selection_integration_test.go:16) | 低中；正式文本主链。50% 可用/85% 完整是原实现的 cue 时间并集阈值，不等于语义准确率或语音覆盖率 |
| ASR 降级 | [asr.go:25](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/asr.go:25) 缺配置明确报错；60秒窗口、最多2个并发，按原顺序提交进度；[asr.go:120](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/asr.go:120) 操作级结果复用 | [asr_parallel_integration_test.go:18](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/asr_parallel_integration_test.go:18) | 中；缺字幕时的 ASR 是最终成品链路，服务独立配置。若仅返回整段文字，按窗口标时间与精度，不能伪造逐词对齐 |
| ASR 缓存复用 | [source.go:360](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:360) 检查实际含音频媒体的完整 hash 和 pipeline/provider 配置 | [integration_test.go:154](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/integration_test.go:154) | 中；失败重试的有效阶段复用属于可靠性要求；跨任务内容缓存另按收益论证。均不能只按 URL 复用，需核对源内容、处理参数和配置版本 |
| 按需取帧 | [frames.go:39](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/frames.go:39) `Inspect`，单次1～6帧，普通窗口最长60秒，支持裁剪/重新加载 | [integration_test.go:21](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/integration_test.go:21) | 中；主链保留有界取帧和按需补看，裁剪仅在阅读细节确有需要时增加 |
| 实际画面时间 | [frames.go:156](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/frames.go:156) FFmpeg `showinfo`，解析 `pts_time`，保存实际解码时间而非只用请求时间 | 同上，测试生成独立样本并校验真实帧时间 | 主链；Python 可调用同一媒体工具，本机制本身不足以构成保留 Go 的理由 |
| 媒体缓存 | [frames.go:133](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/frames.go:133) key 含 snapshot、时间、模式、crop、version；命中后仍检查 DB asset、文件存在、Pin | 同上及 resource 测试 | 保留 DB 唯一键、文件校验和引用保护；Redis 加速按热点与对照测量决定，不能取代资产有效性检查 |
| 全片导图 | `domain.Article` 固定包含 `mind_map`（[types.go:311-320](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/domain/types.go:311)、[types.go:326-339](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/domain/types.go:326)）；发布前校验导图层级、叶节点章节定位和深度（[concept_map.go:15-56](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/investigator/concept_map.go:15)）；阅读页渲染导图（[ReadView.tsx:15](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/ui/ReadView.tsx:15)、[MindMap.tsx:1](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/ui/MindMap.tsx:1)） | [concept_map_test.go:1](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/exporting/concept_map_test.go:1)、[mindLayout.test.ts:1](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/ui/mindLayout.test.ts:1) | 导图是 VidLens 现有文章结构的一部分。FrameRead 将全片导图列为最终产物，专题文章也不能把导图降级为专题范围 |
| 进程边界 | [process.go:75](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/process.go:75) Unix 进程组、取消时杀子进程组、输出/工作区限制；RSS 只观察主子进程 | [transport_test.go:14](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/transport_test.go:14) 不完整下载不能成为可发布文件 | 主链保留，运行统一 Linux Docker；`async def` 不能代替子进程退出和资源治理 |
| 文件归属与清理 | [files.go:68](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/files.go:68) hash、归属、rename；视频/音频不自动过期。[cleanup.go:12](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/cleanup.go:12) DB 删除租约、Pin、待删资源、失败标记、有限孤儿清理 | [manage_test.go:14](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/manage_test.go:14) 删除原视频保留已发布帧 | 中；正式资产长期保留、原媒体清理/同源恢复、临时文件和失败清理均为成品要求；高级配额后台不是必需。删 Redis key 不等于删除媒体 |
| Markdown / ZIP | [exporting/service.go:51](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/exporting/service.go:51) 读取已发布文章、确定性渲染、临时文件、hash、路径和体积限制，不再调用模型；ZIP 含 `article.md`、本地图片、`sources.json` 与 `manifest.json`，缺图/hash 不符会失败（`service.go:99-195`） | [service_test.go:85](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/exporting/service_test.go:85)、[citation_timing_test.go:26](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/exporting/citation_timing_test.go:26)、[concept_map_test.go:1](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/exporting/concept_map_test.go:1) | VidLens 已具备两种导出实现。FrameRead 按已确认需求把二者列为最终验收；这不是自动视频剪辑或视频片段导出 |

### 2026-11-09 媒体链路定向补充

上表已经覆盖主能力；本轮再补几条对 Python 重实现有直接影响的当前源码事实：

1. **下载边界比“调用 yt-dlp”更具体。** YouTube 视频格式被限制为 1080p 内的 HTTPS/mp4 候选，下载参数显式 `--ignore-config`、`--no-cache-dir`、`--no-playlist`、`--no-cookies`、`--no-cookies-from-browser`；YouTube 还指定 Node JS runtime 并禁止借用浏览器/共享 Cookie。下载完成后再用 ffprobe 校验真实视频轨、音频轨、时长和分辨率，不完整下载不能进入后续生成（[source.go:35-59](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:35)、[source.go:314-329](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:314)、[source.go:573-612](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:573)）。
2. **字幕采用是有限尝试，不是“找到一种就停”。** 当前决策版本为 `subtitle-adoption-v2`，语言按 zh-Hans/zh-CN/zh/en 等优先级排序、手工字幕优先于自动字幕、格式优先级为 json3/vtt/srt/json；最多尝试 3 个候选，并且复用最初 `--dump-single-json` 得到的 `source-info.json`，避免二次抓取改变轨道或签名地址。每次尝试、解析结果、coverage 和 fallback reason 都写入 source diagnostic（[subtitle_selection.go:44-80](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/subtitle_selection.go:44)、[subtitle_selection.go:82-155](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/subtitle_selection.go:82)、[source.go:250-260](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:250)）。
3. **ASR 只在字幕不可用且确有音频时进入。** YouTube 会在字幕 coverage 不足时预取音轨；若视频本身无音轨，则另行下载 audio，且视频与独立音频的合计字节不能超过下载上限。ASR 将音频切成 60 秒窗口，最多两个上传 worker，但按原顺序提交进度和拼接结果；窗口级 operation 支持失败后有限复用，provider request ID 与结果持久化（[source.go:262-296](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:262)、[source.go:389-455](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:389)、[asr.go:25-118](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/asr.go:25)、[asr.go:120-208](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/asr.go:120)）。
4. **截图是持久 operation，不是临时函数返回值。** 同一 `inspect` key 完成后可直接恢复；缓存命中仍校验 asset 状态、文件存在与 pin。普通窗口一次最多 6 帧、窗口最长 60 秒，必须解析 FFmpeg `pts_time` 得到实际解码时间；单帧最大 2 MiB，单次 inspection 总载荷 8 MiB，文章和 QA 的预留预算分别为 20 MiB/8 MiB。裁剪必须来自已交付的 parent frame，并继承父帧实际时间（[frames.go:39-86](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/frames.go:39)、[frames.go:127-225](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/frames.go:127)）。
5. **媒体子进程有独立资源治理。** FFmpeg/yt-dlp 通过进程组启动，取消时 kill 整个进程组；stdout/stderr、工作区字节、停滞时间、主进程 RSS 都有上限。仅把调用包成 `async subprocess` 而不保留这些治理，会丢掉原实现的重要后端价值（[process.go:46-147](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/process.go:46)）。

原实现的 `local://` 是显式开启 `dev_media_dir` 后的开发样本通道，不是浏览器用户上传视频功能，见 [source.go:116](D:/VScodeProject/FrameRead/reference-project/VidLens/internal/media/source.go:116) 和 [startup.md:39](D:/VScodeProject/FrameRead/reference-project/VidLens/docs/backend/startup.md:39)。FrameRead 可以把固定本地样本作为测试输入，但不能把它冒称原项目已有上传产品功能。

## 3. 前端可参考范围与耦合

页面链路在 [App.tsx:45](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/app/App.tsx:45)：输入、运行、阅读、历史；`/r/:id` 恢复某次请求。它已有阅读和选段逻辑，适合参考业务交互。

| 范围 | 证据 | 迁移判断 |
| --- | --- | --- |
| 阅读、块内容、引用、帧查看 | [ReadView.tsx:15](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/ui/ReadView.tsx:15)、[Blocks.tsx:81](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/ui/Blocks.tsx:81) | 用户自有源码可直接参考与适配；按 props、状态依赖和新 API 契约评估组件复用，无需为项目归属问题重写 UI |
| API 封装 | [http.ts:50](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/api/http.ts:50) | 强耦合原 `/api/v1/requests`、契约版本头、CSRF、cookie、错误结构、幂等返回头，不能只换 base URL |
| 请求重放 | [writes.ts:58](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/api/writes.ts:58)、[useVisitor.ts:310](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/app/useVisitor.ts:310) | 保留“网络失败沿用同一幂等键”的语义，配合后端唯一约束；按钮禁用不足以去重 |
| 实时同步 | [runtime.ts:45](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/api/runtime.ts:45)、[live.ts:70](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/api/live.ts:70) | 实际是 EventSource/SSE，`LiveSocket` 名称不表示 WebSocket；事件类型含 snapshot/upsert/reset/auth_required |
| 断线恢复 | [live.ts:174](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/api/live.ts:174) | 退避重连，先 HTTP 获取快照和 cursor，再订阅；schema/scope不符触发恢复，不靠内存状态撑刷新 |
| 状态与结果契约 | [types.ts:1](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/contract/types.ts:1) | 原 Request/Turn/Run/Phase 是不同层次；FrameRead 若简化成 task.status + task.stage，必须同步重写适配层 |
| 执行过程、计划和管理后台 | [RunView.tsx:15](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/ui/RunView.tsx:15)、`frontend/src/site` | 绑定大量原 article loop、budget/model、site capacity 数据。FrameRead 只做阶段、失败、重试和耗时等必要任务状态，不复刻站点运营后台；这不删除最终成品的任务可靠性要求 |

2026-11-09 定向补充：任务页把“数据消费”和“视觉呈现”分得很清楚。前端先用 HTTP snapshot 安装 request/turn 权威状态，再通过 EventSource 更新；`RunView` 从 view 中拆出阶段、当前动作、最近步骤、计划、画面、模型调用和可用操作，而不是自行计算后端是否完成。提交入口在跳转前保存 pending idempotency key，QA 发送也校验上一 turn 是否终态，取消/重试以后端返回的新 view 为准（[useVisitor.ts:269-328](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/app/useVisitor.ts:269)、[useVisitor.ts:509-544](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/app/useVisitor.ts:509)、[useVisitorConversation.ts:297-424](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/app/useVisitorConversation.ts:297)、[RunView.tsx:69-104](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/ui/RunView.tsx:69)）。FrameRead 复用 React 组件时也必须同步这套 view/动作契约，不能只复用视觉样式。

前端已有 38 个 `.test.` 文件，不代表全部组件有行为覆盖，更不表示本轮测试通过。可借鉴 `api/live.test.ts`、`api/writes.test.ts`、`contract/stream.test.ts` 的断线与重复写场景，适配后需重新验收。

## 4. 文档与代码差异

[startup.md:52](D:/VScodeProject/FrameRead/reference-project/VidLens/docs/backend/startup.md:52) 仍写公开分享未实现，但 [http.ts:139](D:/VScodeProject/FrameRead/reference-project/VidLens/frontend/src/api/http.ts:139)、后端 shares 路由与存储、README均显示已有分享功能。判断以本地实际实现为准，不能逐段复制旧文档。

[scripts/verify.py:1](D:/VScodeProject/FrameRead/reference-project/VidLens/scripts/verify.py:1) 提供 `unit/full` 验证模式，full 依赖独立测试 PostgreSQL/Redis、FFmpeg和私有能力样本；跳过测试会被分类，不等于通过。[startup.md:43](D:/VScodeProject/FrameRead/reference-project/VidLens/docs/backend/startup.md:43) 的 smoke 可能调用真实模型/ASR，本轮不运行。

## 5. 2026-10-25 复审补充：成品功能与 FrameRead 边界

以下事实来自本轮定向读取，用于替换旧工期导致的“导图/导出/分享后置”建议：

1. **图文 ZIP 已是实际实现，不只是路线设想。** 导出服务支持 `markdown` 与 `markdown_zip`（`internal/exporting/service.go:99-124`），ZIP 写入正文、相对路径图片、来源元数据和 manifest，并校验 asset 状态、大小与 SHA-256；失败会返回明确错误，不输出半成品（`service.go:153-195`）。
2. **网页只读分享已有前端入口。** 管理页面可创建/撤销分享（`frontend/src/ui/ShareControl.tsx:77-90`），公开页从 `/api/v1/shares/{token}` 读取（`frontend/src/api/shares.ts:4-17`）并渲染文章与导图（`frontend/src/site/SharedRecord.tsx:18-80`）。前端文案明确私人追问不公开（`ShareControl.tsx:81`）。FrameRead 应把公开对象从“处理记录”收敛为“正式文章版本”，并保留图片 allowlist 与撤销语义。
3. **配置管理在 VidLens 中分成 visitor 选择和管理站运营。** visitor 从 `/api/v1/models` 选择已启用模型（`frontend/src/app/useVisitor.ts:269-360`）；完整 provider/model/probe/路由后台在 `frontend/src/site/Manage*.tsx` 与 `/api/v1/admin/*`。FrameRead 不复制站点运营后台，只保留个人设置页：多模型配置、能力检查、ASR 独立配置、密钥脱敏、默认模型和配置 revision。
4. **源媒体恢复存在内容身份校验。** QA 需要恢复媒体时，原项目会创建 `source.restore` 并在完成时比较新旧 snapshot 的 `VideoHash`（`internal/store/artifacts.go:102-110`）。FrameRead 应保留该原则；对下载格式不同导致字节不同的情况，采用可验证的内容指纹，而不是假设重新下载的字节必然相同。
5. **旧报告中的“Markdown P1、ZIP P2、分享延后、导图复杂交互后置”只是旧工期建议。** 当前已确认需求要求 Markdown/ZIP/分享成为最终验收；允许简化的只是复杂导图交互和站点运营 UI，不能删除全片导图、离线图片、分享撤销和权限隔离。

## 6. 项目归属与直接参考规则

用户于 2026-10-30 明确 VidLens 是自己的 GitHub 项目，源码位于 `D:/VScodeProject/FrameRead/reference-project/VidLens`。按根目录 `AGENTS.md`，直接参考其功能、源码架构和数据流，不再把 VidLens 许可证、归属或使用授权作为风险、审批或阻塞项。

前端复用和后端重设计只按技术收益判断：展示组件能复用就适配，耦合原管理后台或事件协议的部分需重新对齐；媒体流程保留来源身份、字幕/ASR 时间、真实帧及资源生命周期。后端学习重点包括阻塞子进程隔离、有界并发、SSE 恢复、持久任务与文件/数据库一致性，不以增加组件数量代替工程深度。

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
