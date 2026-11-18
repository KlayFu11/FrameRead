# FrameRead

FrameRead 是基于 Java 21、Spring Boot 和 Vue 3 的长视频理解与分析平台。用户登录后可以上传或分片续传本地视频，也可以导入公开可获取的 Bilibili、YouTube 单视频链接。

系统使用平台字幕或 ASR，结合关键帧和 OCR 构建视频上下文。通用、学习、审查和创作四种 Agent 模式生成带时间证据的结构化分析报告。用户在 Web 工作区查看报告和进度、定位原片、检索证据、连续追问、反馈、修改计划或导出；浏览器扩展提供视频导入、分析进度、报告和原片定位。

## 工程结构

| 位置 | 职责 |
| --- | --- |
| `server/` | Spring Boot HTTP/SSE 服务、媒体与 Agent 编排、RocketMQ 消费、持久化与恢复 |
| `client/` | Vue 3/Vite Web 工作区 |
| `extension/` | Manifest V3 浏览器扩展 |
| `docker-compose.yml`、`rocketmq/`、`.env.example` | 中间件编排、Broker 配置和环境样例 |
| `scripts/`、`.github/workflows/` | 启动脚本和 CI |

MySQL、MyBatis-Plus 和 Flyway 管理业务数据与 Checkpoint。Redis/Redisson 提供会话、缓存和协调，RocketMQ 投递异步分析，MinIO 保存媒体资源，Qdrant 支持证据检索。应用与 FFmpeg、OCR 和下载工具运行在宿主机，中间件由 Compose 启动。运行入口为 `scripts/dev-up.sh`，链接获取的部署条件与验证依据见 [SPEC 的运行说明](docs/prototype/SPEC.md#spec-verification)。

## 项目文档

- [产品需求 PRD V3](docs/prototype/PRD.v3.md) 规定完整产品范围、业务流程与验收标准。
- [全局技术 SPEC](docs/prototype/SPEC.md) 规定模块职责、API、数据、异步恢复和运行契约。
- [模块地图](.scratch/frameread-v1/map.md) 定位模块协作、实施切片与验收入口。
- [领域术语](GLOSSARY.md) 统一业务对象和用户操作的含义。
