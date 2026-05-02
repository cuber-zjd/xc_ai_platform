from pydantic import BaseModel, Field
from typing import List, Any

class DataExtractRequest(BaseModel):
    text: str = Field(..., description="需要提取数据的自然语言文本", examples=["豆油主力合约收盘价为8605元/吨，涨32元/吨，豆粕主力合约收盘价3021元/吨，涨1元/吨。今日连盘油粕比为2.8484，现货方面，张家港现货市场油粕比为3.0205，隔夜CBOT油粕比为4.581。"])
    requirements: List[str] = Field(..., description="要提取的数据项列表，需要按顺序返回", examples=[["豆油价格", "豆油涨幅", "豆粕价格", "豆粕涨幅", "油粕比", "张家港现货市场油粕比", "隔夜油粕比"]])

class DataExtractResponse(BaseModel):
    extracted_data: List[Any] = Field(..., description="按要求顺序提取出的数据数组")
