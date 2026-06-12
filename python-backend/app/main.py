"""FastAPI 主应用入口"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import database
from app.routers import (
    user_router,
    health_router,
    article_router,
    payment_router,
    webhook_router,
    statistics_router,
)
from app.exceptions import BusinessException, ErrorCode
from app.utils.session import init_redis, close_redis
from app.services.article_task_queue import article_task_queue_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    await database.connect()
    await init_redis()
    if settings.article_task_worker_enabled:
        await article_task_queue_manager.start()
    print(f"数据库连接成功: {settings.database_url}")
    print(f"Redis 连接成功: {settings.redis_url}")
    if settings.article_task_worker_enabled:
        print(
            "文章任务队列启动成功: "
            f"maxSize={settings.article_task_queue_max_size}, "
            f"workerConcurrency={settings.article_task_worker_concurrency}"
        )
    else:
        print("文章任务队列消费已关闭，当前进程仅负责入队")
    
    yield
    
    # 关闭时执行
    if settings.article_task_worker_enabled:
        await article_task_queue_manager.stop()
    await database.disconnect()
    await close_redis()
    print("应用已关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="AI 爆款文章创作器",
    description="基于多智能体编排的 AI 文章创作平台",
    version="0.0.1",
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # 前端开发服务器地址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理
@app.exception_handler(BusinessException)
async def business_exception_handler(request: Request, exc: BusinessException):
    """业务异常处理"""
    return JSONResponse(
        status_code=200,
        content={
            "code": exc.error_code.code,
            "data": None,
            "message": exc.message
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    print(f"未处理的异常: {exc}")
    return JSONResponse(
        status_code=200,
        content={
            "code": ErrorCode.SYSTEM_ERROR.code,
            "data": None,
            "message": f"系统内部异常: {str(exc)}"
        }
    )


# 注册路由
app.include_router(health_router, prefix="/api")
app.include_router(user_router, prefix="/api")
app.include_router(article_router, prefix="/api")
app.include_router(payment_router, prefix="/api")
app.include_router(webhook_router, prefix="/api")
app.include_router(statistics_router, prefix="/api")


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "AI 爆款文章创作器 - Python 后端",
        "version": "0.0.1",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=True
    )
