import base64
import json
import re
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from loguru import logger
from langchain_core.messages import SystemMessage, HumanMessage

from app.api import deps
from app.core.llm_factory import LLMFactory
from langfuse import Langfuse, observe
from app.schemas.agent.external.image_extract import ImageExtractResponse
from app.schemas.result import Result

router = APIRouter()


def _strip_json_fence(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?", "", value, flags=re.IGNORECASE).strip()
        value = re.sub(r"```$", "", value).strip()
    return value


def _extract_json_array_text(text: str) -> str:
    value = _strip_json_fence(text)
    start = value.find("[")
    end = value.rfind("]")
    if start >= 0 and end > start:
        return value[start : end + 1].strip()
    return value


def _repair_common_json_text(text: str) -> str:
    value = _extract_json_array_text(text)
    value = value.replace("\ufeff", "").replace("\u00a0", " ")
    value = re.sub(r'\bnull"(?=\s*[,}\]])', "null", value)
    value = re.sub(r'\btrue"(?=\s*[,}\]])', "true", value, flags=re.IGNORECASE)
    value = re.sub(r'\bfalse"(?=\s*[,}\]])', "false", value, flags=re.IGNORECASE)
    value = re.sub(r",\s*([\]}])", r"\1", value)
    return value.strip()


def _parse_table_json(content: str) -> list[list[Any]]:
    errors: list[json.JSONDecodeError] = []
    candidates = [
        _extract_json_array_text(content),
        _repair_common_json_text(content),
    ]
    seen: set[str] = set()

    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            errors.append(exc)
            continue

        if not isinstance(parsed, list):
            raise ValueError("模型返回的不是有效的数组结构")
        if parsed and not isinstance(parsed[0], list):
            parsed = [parsed]
        return parsed

    raise errors[-1] if errors else ValueError("模型返回为空，无法解析为二维数组")


async def _repair_table_json_with_llm(llm: Any, content: str, error: Exception) -> str:
    repair_messages = [
        SystemMessage(
            content=(
                "你是 JSON 格式修复器。你只负责把用户给出的文本修复为合法 JSON 二维数组。\n"
                "要求：\n"
                "1. 不新增、删除或改写业务数据，只修复引号、逗号、null/true/false、括号等 JSON 语法问题。\n"
                "2. 输出必须是严格 JSON，根节点必须是二维数组。\n"
                "3. 只能输出 JSON 本身，不要输出 Markdown、代码块或解释。"
            )
        ),
        HumanMessage(
            content=(
                f"解析错误：{error}\n\n"
                "待修复文本：\n"
                f"{content[:20000]}"
            )
        ),
    ]
    response = await llm.ainvoke(repair_messages)
    repaired_content = getattr(response, "content", "")
    if isinstance(repaired_content, list):
        repaired_content = "".join(str(item) for item in repaired_content)
    return str(repaired_content).strip()


@router.post(
    "/extract_with_image",
    response_model=Result[ImageExtractResponse],
    dependencies=[Depends(deps.verify_external_ai_sign)],
)
@observe(name="extract_data_with_image")
async def extract_data_with_image(
    file: UploadFile = File(..., description="要识别的图片文件"),
    prompt: str | None = Form(None, description="用户自定义提取要求，可覆盖默认表头/表尾处理规则"),
):
    """
    外部接口：通过图片提取结构化数据（二维数组）
    支持识别图片中的表格或列表数据，默认不包含表头及表尾；如用户提示词明确要求包含，则以用户提示词为准。
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
            "1. 默认只提取表格中的正文行数据，不包含表头（标题行）以及表尾（合计、备注等）。\n"
            "2. 如果用户自定义提取要求中明确提出需要包含表头、标题行、合计、备注或其他表尾内容，必须以用户要求为准。\n"
            "3. 如果用户自定义提取要求与默认规则冲突，优先执行用户自定义提取要求。\n"
            "4. 输出格式必须是一个严格的二维数组：[[单元格1, 单元格2, ...], [单元格1, 单元格2, ...]]。\n"
            "5. 你的输出只能包含JSON二维数组，不要输出任何Markdown标记、代码块标记或解释性文字。\n"
            "6. 如果识别到的某列数据为空，请在该位置填入 null 或空字符串。"
        )
        user_text = "请提取这张图片中的数据并返回二维数组。"
        if prompt and prompt.strip():
            user_text += f"\n\n用户自定义提取要求：\n{prompt.strip()}"

        # 构建多模态消息
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=[
                    {"type": "text", "text": user_text},
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

        try:
            extracted_data = _parse_table_json(content)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(f"图片数据提取 JSON 初次解析失败，尝试修复: {exc}")
            try:
                repaired_content = await _repair_table_json_with_llm(llm, content, exc)
                extracted_data = _parse_table_json(repaired_content)
            except (json.JSONDecodeError, ValueError) as repair_exc:
                logger.error(
                    "图片数据提取 JSON 修复后仍解析失败: "
                    f"{repair_exc}; 原始返回前 1000 字符: {content[:1000]}"
                )
                return Result.fail(msg="模型返回格式错误，无法解析为二维数组")

        Langfuse().flush()
        return Result.success(data=ImageExtractResponse(extracted_data=extracted_data))

    except Exception as e:
        logger.error(f"图片数据提取失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        Langfuse().flush()
        return Result.fail(msg=f"图片数据提取系统异常: {LLMFactory.describe_invocation_error(e)}")
