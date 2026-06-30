from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
from contextlib import asynccontextmanager

from encoding_utils import configure_stdio_encoding

configure_stdio_encoding()

import api as api_module
from agent import init_agent_async

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

# 1. 在这里定义 lifespan 上下文管理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行：初始化全局 Agent 和 MCP 工具
    print("正在初始化 Agent 和 MCP 工具...")
    await init_agent_async()
    print("Agent 初始化完成，应用启动！")
    
    yield
    
    # 关闭时清理（目前不需要清理，留空即可）
    print("应用正在关闭...")


def create_app() -> FastAPI:
    # 2. 将 lifespan 传入原有的 FastAPI 初始化逻辑中
    app = FastAPI(title="Cute Cat Bot API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # No-cache middleware for development
    @app.middleware("http")
    async def _no_cache(request, call_next):
        response = await call_next(request)
        path = request.url.path or ""
        if path == "/" or path.endswith((".html", ".js", ".css")):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    app.include_router(api_module.router)

    # serve frontend static files at root
    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")

    return app


# 3. 创建带有完整路由和中间件的 app
app = create_app()

if __name__ == "__main__":
    import uvicorn
    # 4. 直接运行这个 app 即可，不要再重新实例化 FastAPI
    uvicorn.run("app:app", host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", 8080)), reload=False) 
    # 注意：建议使用字符串形式 "app:app" 启动 uvicorn，这是生产环境和正确触发 lifespan 的推荐方式
