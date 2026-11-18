# FrameRead Web

FrameRead 的 Vue 3 工作区提供账号登录、媒体上传与导入、四模式 Agent 分析、进度、报告、证据检索、追问和导出。业务流程见 [PRD V3](../docs/prototype/PRD.v3.md)。

```bash
npm ci
npm run dev
```

开发服务器默认通过 Vite 代理访问 `http://localhost:9090`。后端地址不同时，在项目根目录 `.env` 中设置 `VITE_DEV_PROXY_TARGET`；前后端分开部署时设置 `VITE_API_BASE_URL`。
