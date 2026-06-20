from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logger import setup_logging, logger
from app.core.exceptions import BizException, biz_exception_handler, global_exception_handler
from app.core.middleware import RequestIdMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: specific init logic
    setup_logging()
    
    # Initialize Database Tables
    from app.db.init_db import init_db
    await init_db()

    # MCP Management
    from app.mcp.manager import mcp_manager
    mcp_manager.load_servers()
    mcp_manager.mount_to_app(app, prefix=f"{settings.API_V1_STR}/mcp")

    from app.services.agent.insight.scheduler_service import insight_scheduler_service
    await insight_scheduler_service.start_from_settings()
    
    logger.info("Startup: AI Platform Backend")
    yield
    # Shutdown: cleanup logic
    await insight_scheduler_service.stop()
    logger.info("Shutdown: AI Platform Backend")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# 开发阶段允许 ecode 从任意泛微地址嵌入调用；生产部署时再按实际域名收紧。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware
app.add_middleware(RequestIdMiddleware)

# Exception Handlers
app.add_exception_handler(BizException, biz_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    logger.debug("Root endpoint accessed")
    return {"message": "Welcome to AI Platform API", "docs": "/docs"}
