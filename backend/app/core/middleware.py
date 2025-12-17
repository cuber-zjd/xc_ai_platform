import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from app.core.logger import logger

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Generate Request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        
        # Set Request ID in Context (using loguru's awesome context feature)
        with logger.contextualize(request_id=request_id):
            logger.debug(f"Input Request: {request.method} {request.url}")
            
            response = await call_next(request)
            
            # Add Request ID to Response Header
            response.headers["X-Request-ID"] = request_id
            
            logger.debug(f"Output Response: {response.status_code}")
            return response
