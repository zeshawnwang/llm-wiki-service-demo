"""
LLM Wiki Service - FastAPI应用入口
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings, ensure_directories
from app.api import api_router

logger = logging.getLogger(__name__)

# 确保数据目录存在
ensure_directories()

# 创建FastAPI应用
settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description="LLM Wiki 简化版服务层 - 企业知识库后端",
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册API路由
app.include_router(api_router)


# ========== Git同步定时器 ==========

async def _git_sync_loop():
    """后台定时Git同步循环"""
    from app.services.git_sync_service import GitSyncService

    interval = settings.git_sync_interval_minutes * 60  # 转为秒

    # 首次启动时等待一小段时间，避免和启动流程冲突
    await asyncio.sleep(10)

    while True:
        try:
            sync_service = GitSyncService()
            result = sync_service.sync()
            if result["success"]:
                logger.info(f"[Git同步] {result['message']}")
            else:
                logger.warning(f"[Git同步] {result['message']}")
        except Exception as e:
            logger.error(f"[Git同步] 异常: {e}")

        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时开启Git同步定时器"""
    if settings.git_sync_enabled:
        logger.info(
            f"[Git同步] 已启用，每 {settings.git_sync_interval_minutes} 分钟同步一次 "
            f"→ {settings.git_remote_url} ({settings.git_branch})"
        )
        task = asyncio.create_task(_git_sync_loop())
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    else:
        logger.info("[Git同步] 未启用（GIT_SYNC_ENABLED=false）")
        yield


# ========== 路由 ==========

@app.get("/")
async def root():
    """根路径"""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs",
        "api": "/api"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "service": settings.app_name
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
