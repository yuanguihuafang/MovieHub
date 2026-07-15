# 后端（FastAPI）

提供电影浏览、智能推荐、片单、影评、消息中心、管理后台等 API。

## 目录结构

```
backend/
├── main.py                     # 应用入口（CORS / 静态挂载 / startup 初始化 / 路由注册）
├── db/
│   └── database.py             # MySQL 建表与数据访问（含消息中心写入）
├── api/
│   ├── deps.py                 # 认证/鉴权依赖（Bearer token / 管理员校验 / 禁言校验）
│   └── routers/                # 按模块拆分的路由
│       ├── auth.py             # 登录 / 注册
│       ├── home.py             # 首页聚合 / 首页视频列表
│       ├── movies.py           # 电影列表与详情
│       ├── recommend.py        # 智能推荐
│       ├── user.py             # 个人中心 / 片单 / 收藏 / 已看过 / 反馈 / 消息中心
│       ├── reviews.py          # 影评社区
│       ├── admin.py            # 管理后台（用户 / 收藏 / 日志 / 概览 / 浏览历史）
│       └── poster_cache.py     # 海报缓存接口
├── recommender/                # 推荐引擎
│   ├── recommend.py            # KG 链接预测 + RAG 检索 + TMDB 新鲜池三通道融合
│   └── recommend_llm.py        # LLM 定榜（偏好分解 / 去重排序 / 推荐解释）
├── services/                   # 业务服务
│   ├── tmdb_client.py          # TMDB API 客户端
│   ├── tmdb_home_cache.py      # TMDB 首页缓存
│   ├── tmdb_home_poster_cache.py
│   ├── poster_service.py       # 海报获取服务
│   └── poster_file_cache.py    # 海报落盘缓存
├── schemas/                    # Pydantic 请求/响应模型
│   ├── auth.py
│   ├── user.py
│   ├── reviews.py
│   ├── recommend.py
│   └── admin.py
├── eval/                       # 推荐系统离线评估
│   ├── metrics.py              # 评估指标（Precision / Recall / HitRate / MRR / NDCG / Coverage）
│   ├── recommend_eval.py       # 评估主程序（基于 recommend_logs + 用户反馈）
│   └── eval_report.md          # 评估报告（自动生成）
├── scripts/                    # 工具脚本
│   ├── build_kg_movie_rag.py   # 构建电影知识图谱 RAG 向量库
│   └── generate_zh_aliases.py  # 生成中文片名别名
└── data/                       # 运行时数据（均已被 .gitignore 排除）
    ├── RAG_data/               # ChromaDB 向量库 + 嵌入缓存
    ├── poster_cache/           # 海报图片缓存
    ├── eval/                   # 评估展示口径配置
    ├── vedio/                  # 首页轮播视频
    └── background/             # 背景图片
```

## 启动

在项目根目录执行：

```bash
# 方式 A：直接运行（开发推荐）
python backend/main.py

# 方式 B：uvicorn（标准/生产）
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

启动后访问 API 文档：`http://localhost:8000/docs`

## 环境变量（`.env`）

在项目根目录创建 `.env` 文件：

**必填（MySQL）：**

```bash
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=moviehub
```

**可选：**

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DASHSCOPE_API_KEY` | 通义千问 API（推荐解释 / 偏好分解） | 未配置自动降级 |
| `TMDB_API_KEY` | TMDB API（热榜 / 补海报） | 未配置自动降级 |
| `MOVIEHUB_REDIS_URL` | Redis 连接地址（缓存） | 未配置自动降级 |
| `CHROMA_PATH` | ChromaDB 向量库路径 | `backend/data/RAG_data/rag_db` |
| `CORS_ORIGINS` | 允许的前端来源（逗号分隔） | `http://localhost:5173` |
| `POSTER_FILE_CACHE` | 海报落盘缓存开关 | `1` |
| `POSTER_CACHE_DIR` | 海报缓存目录 | `backend/data/poster_cache` |

## 数据初始化

首次启动会自动建表并创建默认管理员：

- 用户名：`admin`
- 密码：`admin123`

## 推荐系统

推荐引擎采用三通道融合架构：

1. **KG 通道**：调用 Multi-MoE 模型做知识图谱链接预测
2. **RAG 通道**：ChromaDB 向量语义检索用户偏好电影
3. **TMDB 通道**：热门 / 新片补充池

三通道结果汇总后，由 LLM（通义千问）统一定榜：去重、排序、生成推荐解释。

## 离线评估

```bash
python backend/eval/recommend_eval.py
```

评估基于 `recommend_logs` 表，统计推荐曝光后 14 天内用户正反馈（收藏 / 看过 / 点赞 / 影评）的命中情况。
