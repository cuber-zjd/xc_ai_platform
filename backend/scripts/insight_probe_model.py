"""使用已有连接验证新模型；显式 --apply 才登记，不覆盖旧模型或计划。"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from langchain_core.messages import HumanMessage
from loguru import logger
from sqlmodel import select

from app.core.llm_factory import LLMFactory
from app.db.session import async_session
from app.models.system.sys_model import SysModel


async def main(args: argparse.Namespace) -> None:
    async with async_session() as db:
        source = await db.get(SysModel, args.source_id)
        if not source or source.is_deleted or not source.is_enabled or source.status != 1:
            raise ValueError("指定的连接模型不可用")
        llm = LLMFactory._build_llm(
            model_code=args.code, api_key=source.api_key, base_url=source.base_url,
            temperature=0, max_tokens=512, streaming=False, json_mode=True,
            enable_reasoning=False, enable_langfuse_callbacks=False,
        )
        try:
            response = await asyncio.wait_for(
                llm.ainvoke([HumanMessage(content='只返回 JSON：{"ok":true,"company":"健源"}')]),
                timeout=90,
            )
            payload = json.loads(response.content)
            if payload != {"ok": True, "company": "健源"}:
                raise ValueError("结构化响应校验失败")
        except Exception as exc:
            logger.error("模型验证失败 code={} type={}", args.code, type(exc).__name__)
            raise SystemExit(1) from None
        logger.info("模型验证通过 code={} usage={}", args.code, response.usage_metadata)
        if not args.apply:
            return
        name = args.name or args.code
        existing = (await db.exec(select(SysModel).where(SysModel.model_name == name))).first()
        if existing:
            logger.info("模型名称已存在，不覆盖：{}", name)
            return
        row = SysModel(
            model_name=name, model_code=args.code, provider=source.provider,
            api_key=source.api_key, base_url=source.base_url,
            model_level=4, priority=10000, capability="insight-report",
            max_tokens=16384, is_multimodal=False,
        )
        db.add(row)
        await db.commit()
        logger.info("已登记洞察专用模型：{}，未修改旧模型和推送计划", name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", type=int, required=True)
    parser.add_argument("--code", required=True)
    parser.add_argument("--name")
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args()))
