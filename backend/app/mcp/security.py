from fastapi import Request, HTTPException, Security
from fastapi.security import APIKeyHeader
from app.core.config import settings
from starlette import status

mcp_api_key_header = APIKeyHeader(name="X-MCP-API-Key", auto_error=False)

async def verify_mcp_auth(api_key: str = Security(mcp_api_key_header)):
    """
    验证 MCP 请求的安全性。
    支持从请求头或查询参数中获取 API Key。
    """
    if not settings.MCP_API_KEY:
        # 如果未配置 API Key，则默认放行（开发环境）
        return
        
    if api_key != settings.MCP_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate MCP credentials",
        )
