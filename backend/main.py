"""
backend/main.py

应用工厂与组装入口。

- 创建 FastAPI app（CORS、静态资源挂载、startup 初始化）
- 挂载按“页面/模块”拆分的路由（auth/user/reviews/...）

推荐生产启动方式：
- `uvicorn backend.main:app --host 0.0.0.0 --port 8000`
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.requests import Request

# Ensure project root on sys.path (keep behavior consistent)
current_file = os.path.abspath(__file__)
backend_dir = os.path.dirname(current_file)
project_root = os.path.dirname(backend_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

load_dotenv(os.path.join(project_root, ".env"), override=True)

# Chroma：尽早关闭遥测，避免部分环境下 posthog/capture 版本不兼容刷「capture() takes 1 positional argument…」
# 并减少对向量查询路径的干扰（与 recommend_rag.load_rag_db 内 Settings 双保险）
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("CHROMA_TELEMETRY", "false")

from backend.api.routers.auth import router as auth_router
from backend.api.routers.home import router as home_router
from backend.api.routers.movies import router as movies_router
from backend.api.routers.poster_cache import router as poster_cache_router
from backend.api.routers.recommend import router as recommend_router
from backend.api.routers.reviews import router as reviews_router
from backend.api.routers.user import router as user_router
from backend.api.routers.admin import router as admin_router
from backend.db.database import init_db
from backend.services.poster_file_cache import ensure_poster_cache_dir, poster_file_cache_enabled
from backend.recommender import load_kg_model, load_rag_db


_DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def _parse_csv_env(name: str) -> list[str]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def create_app() -> FastAPI:
    app = FastAPI(
        title="MovieHub API",
        description="MovieHub：基于 Multi-MoE 知识图谱与 RAG 的智能电影推荐",
        version="1.0.0",
    )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(request: Request, exc: RequestValidationError):
        # 统一打印 422，便于定位“前端传参字段不一致/类型不匹配”等问题
        try:
            body = await request.body()
            body_preview = body[:800].decode("utf-8", errors="replace")
        except Exception:
            body_preview = "<unavailable>"
        print(f"❌ [422] 参数校验失败: {request.method} {request.url.path}")
        print(f"   字段错误: {exc.errors()}")
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    # 静态资源：首页视频（本地循环播放）
    vedio_dir = os.path.join(backend_dir, "data", "vedio")
    if os.path.isdir(vedio_dir):
        app.mount("/api/vedio", StaticFiles(directory=vedio_dir), name="vedio")

    # 静态资源：背景图（用于片库/推荐/片单页面两侧氛围图）
    bg_dir = os.path.join(backend_dir, "data", "background")
    if os.path.isdir(bg_dir):
        app.mount("/api/background", StaticFiles(directory=bg_dir), name="background")

    cors_origins = _parse_csv_env("CORS_ORIGINS") or list(_DEFAULT_CORS_ORIGINS)
    cors_origin_regex = (os.getenv("CORS_ORIGIN_REGEX") or "").strip() or None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup_event():
        print("\n🚀 MovieHub 启动中...\n")
        print("📦 [1/5] 初始化数据库...")
        init_db()
        print("✅ [1/5] 数据库就绪")

        print("📦 [2/5] 加载知识图谱模型...")
        load_kg_model("DB15K", True)
        print("✅ [2/5] 知识图谱就绪")

        print("📦 [3/5] 加载 RAG 向量库...")
        load_rag_db()
        print("✅ [3/5] RAG 就绪")

        print("📦 [4/5] 加载电影数据...")
        try:
            from backend.recommender import load_douban_data
            from backend.recommender.home import start_tmdb_home_updater

            load_douban_data()
            try:
                from backend.recommender.browse import load_tmdb_movies_data

                load_tmdb_movies_data()
            except Exception as e:
                print(f"⚠️  TMDB 数据加载跳过: {str(e)[:100]}")
            try:
                start_tmdb_home_updater()
            except Exception as e:
                print(f"⚠️  TMDB 首页更新器启动跳过: {str(e)[:100]}")
        except Exception as e:
            print(f"❌ 电影数据加载失败: {str(e)[:100]}")

        print("📦 [5/5] 检查海报缓存...")
        if poster_file_cache_enabled():
            ensure_poster_cache_dir()

        print("\n✅ MovieHub 启动完成！\n")

    # Routers (page/module oriented)
    app.include_router(auth_router)
    app.include_router(home_router)
    app.include_router(movies_router)
    app.include_router(poster_cache_router)
    app.include_router(recommend_router)
    app.include_router(user_router)
    app.include_router(reviews_router)
    app.include_router(admin_router)

    return app


app = create_app()


def run() -> None:
    """兼容：允许直接 `python backend/main.py` 启动。"""
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))


if __name__ == "__main__":
    run()

