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
    logger.info("Startup: AI Platform Backend")
    yield
    # Shutdown: cleanup logic
    logger.info("Shutdown: AI Platform Backend")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Middleware
app.add_middleware(RequestIdMiddleware)

# Exception Handlers
app.add_exception_handler(BizException, biz_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# Set all CORS enabled origins
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    logger.debug("Root endpoint accessed")
    return {"message": "Welcome to AI Platform API", "docs": "/docs"}
