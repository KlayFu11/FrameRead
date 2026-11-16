# 管理前端

此切片只提供管理员登录、会话恢复和退出外壳。启动时所有管理路径均先探测会话，包括直接打开登录页；有效会话直接进入外壳，401 才显示密码框。业务页面由后续 Ticket 接入。

使用 Node 24 和 `package.json` 指定的 pnpm 版本：

```sh
pnpm install --frozen-lockfile
pnpm test
pnpm typecheck
pnpm build
```

构建产物位于 `dist/`，静态资源基路径为 `/manage/`，由 gateway 服务。前端所有 HTTP 调用经 `src/shared/api.ts`，会话 cookie 由浏览器自动携带，CSRF 只保存在请求层内存。`src/admin/` 放管理页面，`src/shared/` 放共享请求与错误展示，`src/gen/` 只放生成类型。

本地开发先启动 gateway，再运行 `pnpm dev`，访问 `http://localhost:5173/manage/`。Vite 将 `/api` 代理到 `http://127.0.0.1:8080`，保留开发入口 Host；后端开发配置须允许 `http://localhost:5173`。

后端修改契约后，先在 `backend/` 使用已安装的 CLI：

```sh
frameread openapi export --app admin --out openapi/admin.json
```

再在 `frontend/` 运行 `pnpm generate:api`。提交 `backend/openapi/admin.json` 与 `src/gen/admin-api.d.ts`，不手工编辑生成文件。CI 重新导出、生成后应检查这两个文件无 diff。

Vitest 在 HTTP 边界替换 `fetch`，覆盖 cookie 请求选项、CSRF 头、401、CSRF 拒绝不重放、登录原路径恢复、退出、Origin 错误和限流反馈。真实 cookie 属性、gateway 和浏览器布局另由 Ticket 的端到端验收验证。
