import json
from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from langchain_core.messages import SystemMessage, HumanMessage

from app.api import deps
from app.core.llm_factory import LLMFactory
from app.schemas.agent.data_extract import DataExtractRequest, DataExtractResponse
from app.schemas.result import Result

router = APIRouter()


@router.post(
    "/extract_with_text",
    response_model=Result[DataExtractResponse],
    dependencies=[Depends(deps.verify_external_ai_sign)],
)
async def extract_data_with_text(request: DataExtractRequest):
    """
    外部接口：通过自然语言提取结构化数据
    传入需要提取数据的文本和要求（要提取的字段列表），返回提取到的数据数组。
    此接口通过请求头 ai-sign 进行认证。
    """
    try:
        # 构建 Prompt
        system_prompt = (
            "你是一个强大的数据提取专家。\n"
            "用户会给你一段自然语言文本，以及一个需要提取的字段列表（以JSON数组形式表示）。\n"
            "请你从文本中提取对应字段的数据，并严格按照用户要求的字段顺序，返回一个包含提取结果的JSON数组。\n"
            "要求：\n"
            "1. 你的输出必须是一个合法的JSON格式，且仅包含一个数组。\n"
            "2. 数组中的元素顺序必须与用户要求的字段顺序完全一致。\n"
            "3. 如果某个字段在文本中找不到对应的数据，请在该位置返回 null 或空字符串。\n"
            "4. 除了JSON数组外，不要输出任何其他文本（不要有markdown标记等）。"
        )

        user_prompt = f"文本：\n{request.text}\n\n要求提取的字段：\n{json.dumps(request.requirements, ensure_ascii=False)}"

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        # 获取指定模型
        llm = await LLMFactory.get_model_by_name(
            "doubao-seed-2-0-lite", temperature=0.0, max_tokens=4096
        )
        response = await llm.ainvoke(messages)

        content = response.content.strip()

        # 尝试解析 JSON
        # 处理可能包含的 markdown json 标记
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
                # 兼容某些模型依然返回了对象的情况
                if isinstance(extracted_data, dict) and len(extracted_data) > 0:
                    # 尝试从字典值中提取
                    extracted_data = list(extracted_data.values())
                    # 如果长度不一致，说明提取可能有问题，但不做严格截断，也可以只取要求长度
                    if len(extracted_data) != len(request.requirements):
                        logger.warning(
                            f"提取返回字典且长度不一致: req={len(request.requirements)}, res={len(extracted_data)}"
                        )
                else:
                    raise ValueError("返回的数据不是有效的数组或字典结构")
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}\n模型返回: {content}")
            raise HTTPException(
                status_code=500, detail="模型返回格式错误，无法解析为JSON数组"
            )

        # 确保返回长度与请求一致，多余的截断，少补null
        if len(extracted_data) > len(request.requirements):
            extracted_data = extracted_data[: len(request.requirements)]
        elif len(extracted_data) < len(request.requirements):
            extracted_data.extend(
                [None] * (len(request.requirements) - len(extracted_data))
            )

        return Result.success(data=DataExtractResponse(extracted_data=extracted_data))

    except Exception as e:
        logger.error(f"数据提取失败: {str(e)}")
        import traceback

        logger.error(traceback.format_exc())
        return Result.fail(msg=f"数据提取失败: {str(e)}")
