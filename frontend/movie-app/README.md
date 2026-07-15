# 电影推荐系统前端（Vue 3）

这是本项目的前端应用，位于 `frontend/movie-app/`，技术栈为 **Vue 3 + TypeScript + Vite + Element Plus + Pinia**。

## 开发启动

```bash
npm install
npm run dev
```

默认访问：`http://localhost:5173`

## 生产构建

```bash
npm run build
npm run preview
```

## 重要说明

- **API 地址**：开发环境通过 Vite 代理把 `/api` 转发到 `http://localhost:8000`，配置见 `vite.config.ts`
- **鉴权**：登录后会在 `localStorage` 保存 token（形如 `user_<id>`），请求会自动带 `Authorization: Bearer <token>`（见 `src/services/api.ts`）
- **页面路由**：见 `src/app/router/index.ts`（含登录/管理员守卫）

更多说明请查看：`frontend/FRONTEND_README.md`
