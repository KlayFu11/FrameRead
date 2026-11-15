FrameRead **一个面向长视频内容理解的视频解读 Agent**；将视频转化为带时间出处、真实配图和全片导图的图文文章，并支持追问、导出与分享。

> 当前仅有产品与技术设计文档，没有可运行代码、启动脚本或已验证部署。本文中的目录和运行方式是目标契约，不代表功能已经实现。

## 项目定位

FrameRead 面向个人 Docker 自托管场景，用于学习和展示 Python 后端、AI 应用服务化以及适量的 React/TypeScript 全栈能力。项目免注册，但管理入口使用单一管理员凭据；公开分享入口使用独立 token，只能读取绑定版本的内容。

## 目录结构

```text
FrameRead/
├── docs/                   # 已有：产品、技术、ADR 与研究文档
├── .scratch/frameread-v1/  # 已有：模块地图与实施进度
├── backend/                # 规划：Python 后端
├── frontend/               # 规划：React/TypeScript 前端
├── deploy/                 # 规划：Docker Compose 与镜像配置
└── scripts/                # 规划：验收与实验入口
```

后端、前端、部署和脚本目录目前尚未建立，目录骨架以 [SPEC_V1 第 2 节](docs/prototype/SPEC_V1.md#spec-02) 为准。

## 技术栈

以下是 [SPEC_V1 第 19 节](docs/prototype/SPEC_V1.md#spec-19) 的设计选择，具体 patch 版本、lockfile、镜像 digest 和兼容性尚未安装验证：

- Python 3.12、FastAPI、Pydantic v2、SQLAlchemy 2.0、Alembic、psycopg3
- PostgreSQL 17 作为任务、文章和关键状态的权威存储
- Redis 7.4、Celery 5.6，配合独立 Worker 和 control 进程
- LangGraph 1，仅用于文章任务内部的有界编排，不裁决业务终态
- React/TypeScript、FFmpeg、yt-dlp、Docker Compose
- `uv` 管理 Python 依赖，`pnpm` 管理前端依赖

MinIO、Qdrant、Kubernetes 等不属于 V1 默认依赖；Redis 内容缓存是否启用要以实测实验为准。

## 业务流程

1. 部署者使用 Compose 启动实例，配置图文模型和可选的独立 ASR 服务。
2. 粘贴 Bilibili 或 YouTube 单条视频链接，选择完整解读或关注点专题、深度和关注点。
3. 系统先匹配已有正式文章；首次处理或主动重新解读时才创建任务。
4. 通过历史、状态快照和 SSE 查看排队、阶段、草稿、错误与结果。
5. 阅读带章节目录、时间出处、真实配图和全片导图的正式文章，并可回看原帧。
6. 对视频、选段或选帧进行私人追问；外部资料只有显式开启后才会读取。
7. 导出 Markdown 或图文 ZIP，创建、读取或撤销固定版本的只读分享。
8. 查看运行概览并执行清理、备份和恢复；旧备份恢复后分享默认禁用，核对后重新签发。

## 本地运行环境

目标运行环境是 Linux amd64 容器，宿主机使用 Docker Compose；Windows Docker Desktop 仍待验证。部署者需要自行提供模型服务配置和相应凭据，凭据不得提交到仓库。当前没有可执行的启动命令、Compose 文件或服务入口；实现并验证前不把设计文档中的命令当作可用 Quick Start。

## 文档导航

- [PRD：V1 产品与验收基线](docs/prototype/PRD.md)
- [SPEC_V1：技术设计基线](docs/prototype/SPEC_V1.md)
- [模块地图与实施进度](.scratch/frameread-v1/map.md)
- [ADR 0001：固定文章版本分享](docs/adr/0001-share-a-fixed-article-version.md)
- [ADR 0002：问答中的背景知识边界](docs/adr/0002-keep-background-knowledge-in-qa.md)
- [ADR 0003：未确认模型调用的重试](docs/adr/0003-retry-an-unconfirmed-model-call.md)
- [ADR 0004：视频任务受理边界](docs/adr/0004-bound-video-task-admission.md)
