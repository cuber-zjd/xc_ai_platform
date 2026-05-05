from typing import Any, List
from pydantic import BaseModel, Field

class ImageExtractResponse(BaseModel):
    extracted_data: List[List[Any]] = Field(..., description="从图片中提取出的二维数组数据")
