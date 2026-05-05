import base64
import json
from typing import Any, List
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from loguru import logger
from langchain_core.messages import SystemMessage, HumanMessage

from app.api import deps
from app.core.llm_factory import LLMFactory
from langfuse import Langfuse, observe
from app.schemas.agent.external.image_extract import ImageExtractResponse
from app.schemas.result import Result

router = APIRouter()


@router.post(
    "/extract_with_image",
    response_model=Result[ImageExtractResponse],
    dependencies=[Depends(deps.verify_external_ai_sign)],
)
@observe(name="extract_data_with_image")
async def extract_data_with_image(
    file: UploadFile = File(..., description="要识别的图片文件")
):
    """
    外部接口：通过图片提取结构化数据（二维数组）
    支持识别图片中的表格或列表数据，不包含表头及表尾。
    返回格式：[[row1_col1, row1_col2, ...], [row2_col1, row2_col2, ...]]
    """
    try:
        # 验证文件类型
        if not file.content_type.startswith("image/"):
            return Result.fail(msg="上传的文件不是有效的图片格式")

        # 读取文件并转换为 base64
        contents = await file.read()
        base64_image = base64.b64encode(contents).decode("utf-8")
        mime_type = file.content_type

        # 构建 Prompt
        system_prompt = (
            "你是一个精通OCR与表格数据解析的专家。\n"
            "用户会给你一张图片，请你识别并提取其中的主要表格数据，并以JSON格式返回一个二维数组。\n"
            "具体要求如下：\n"
            "1. 只提取表格中的正文行数据，**严禁包含表头（标题行）以及表尾（合计、备注等）**。\n"
            "2. 输出格式必须是一个严格的二维数组：[[单元格1, 单元格2, ...], [单元格1, 单元格2, ...]]。\n"
            "3. 你的输出只能包含JSON二维数组，不要输出任何Markdown标记、代码块标记或解释性文字。\n"
            "4. 如果识别到的某列数据为空，请在该位置填入 null 或空字符串。"
        )

        # 构建多模态消息
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=[
                    {"type": "text", "text": "请提取这张图片中的数据并返回二维数组："},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{base64_image}"},
                    },
                ]
            ),
        ]

        # 获取模型
        llm = await LLMFactory.get_model_by_name(
            "doubao-seed-2-0-lite",
            temperature=0.0,
            max_tokens=4096,
        )
        
        response = await llm.ainvoke(messages)
        content = response.content.strip()

        # 简单的 JSON 标记清洗逻辑
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            extracted_data = json.loads(content)
            if not isinstance(extracted_data, list):
                raise ValueError("模型返回的不是有效的数组结构")
            
            # 确保是二维数组，如果不是，尝试修复或报错
            if len(extracted_data) > 0 and not isinstance(extracted_data[0], list):
                # 如果返回的是一维数组，可能是只有一行数据或者是格式误解，视情况包装
                extracted_data = [extracted_data]

        except json.JSONDecodeError as e:
            logger.error(f"图片数据提取 JSON 解析失败: {e}\n模型返回: {content}")
            return Result.fail(msg="模型返回格式错误，无法解析为二维数组")

        Langfuse().flush()
        return Result.success(data=ImageExtractResponse(extracted_data=extracted_data))

    except Exception as e:
        logger.error(f"图片数据提取失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        Langfuse().flush()
        return Result.fail(msg=f"图片数据提取系统异常: {str(e)}")
