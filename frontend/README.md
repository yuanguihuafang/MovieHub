# 前端（Vue 3）

基于 **Vue 3 + TypeScript + Vite + Element Plus + Pinia** 的电影推荐系统前端。

## 目录结构

```
frontend/movie-app/
├── src/
│   ├── views/                   # 页面组件
│   │   ├── HomeView.vue         # 首页（轮播 / 热门 / 推荐）
│   │   ├── BrowseView.vue       # 电影浏览（类型筛选 / 搜索 / 分页）
│   │   ├── RecommendView.vue    # 智能推荐（KG + RAG 融合推荐）
│   │   ├── LibraryView.vue      # 片单管理
│   │   ├── ReviewsView.vue      # 影评社区
│   │   ├── ProfileView.vue      # 个人中心（收藏 / 已看过 / 反馈历史）
│   │   ├── NotificationsView.vue # 消息中心
│   │   ├── AuthView.vue         # 登录 / 注册
│   │   ├── ChangePasswordView.vue # 修改密码
│   │   └── AdminView.vue        # 管理后台
│   ├── components/              # 通用组件（弹窗 / 布局 / 卡片等）
│   ├── stores/                  # Pinia 状态管理
│   │   └── (auth / recommend 等)
│   ├── services/
│   │   └── api.ts               # Axios 客户端（自动注入 token）
│   ├── composables/             # 组合式函数
│   ├── app/
│   │   ├── router/index.ts      # 路由与权限守卫
│   │   └── shell/               # 布局（用户端 / 管理端）
│   ├── styles/                  # 全局样式
│   ├── types/                   # TypeScript 类型定义
│   └── utils/                   # 工具函数
├── package.json
├── vite.config.ts
└── tsconfig.json
```

## 启动

```bash
cd frontend/movie-app
npm install
npm run dev
```

默认访问：`http://localhost:5173`

## 后端代理

开发环境已在 `vite.config.ts` 配置代理：`/api` → `http://localhost:8000`，前端无需写死后端域名。

## 页面说明

| 页面 | 路由 | 功能 |
|------|------|------|
| 首页 | `/` | 轮播视频、热门电影、个性化推荐 |
| 浏览 | `/browse` | 按类型筛选、关键词搜索、分页浏览 |
| 推荐 | `/recommend` | 输入偏好描述，获取 KG + RAG 融合推荐结果 |
| 片单 | `/library` | 创建 / 编辑片单，添加 / 移除电影 |
| 影评 | `/reviews` | 发影评、评论 / 回复、点赞 |
| 个人中心 | `/profile` | 收藏、已看过、点赞/踩历史 |
| 消息 | `/notifications` | 操作记录与互动通知 |
| 管理后台 | `/admin` | 用户管理、影评审核、禁言、推荐日志、系统概览 |

## 构建（生产）

```bash
npm run build
npm run preview
```

> 构建时如果看到 "chunk > 500KB" 的提示，是打包优化建议，不影响运行。

## 相关文档

- 后端启动与环境变量：`backend/README.md`
- 项目总览：根目录 `README.md`
