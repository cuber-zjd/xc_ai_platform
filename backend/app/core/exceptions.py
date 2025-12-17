from fastapi import Request
from fastapi.responses import JSONResponse
from app.schemas.result import Result

class BizException(Exception):
    """
    Business Exception
    """
    def __init__(self, code: int, msg: str, data: any = None):
        self.code = code
        self.msg = msg
        self.data = data

async def biz_exception_handler(request: Request, exc: BizException):
    """
    Handle Business Exception
    """
    return JSONResponse(
        status_code=200, # Always return 200 HTTP status for business logic errors, distinguishing via internal code
        content=Result.fail(code=exc.code, msg=exc.msg, data=exc.data).model_dump(),
    )

async def global_exception_handler(request: Request, exc: Exception):
    """
    Handle Uncaught Exception
    """
    import traceback
    from app.core.logger import logger
    
    error_msg = f"Unhandled Exception: {str(exc)}"
    logger.error(error_msg)
    logger.error(traceback.format_exc())
    
    return JSONResponse(
        status_code=500,
        content=Result.fail(code=500, msg="Internal Server Error").model_dump(),
    )
