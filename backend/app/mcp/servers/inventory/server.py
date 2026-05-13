from typing import List, Any
from sqlalchemy import text
from app.mcp.base import BaseMCPServer
from app.mcp.servers.inventory.schema import MaterialQuerySchema, MaterialSearchSchema
from app.db.session import async_session
from mcp.types import Tool, TextContent
from app.core.logger import logger


class InventoryServer(BaseMCPServer):
    def __init__(self):
        super().__init__(name="inventory-server")

    def _setup_handlers(self):
        @self.server.list_tools()
        async def handle_list_tools() -> List[Tool]:
            return [
                Tool(
                    name="query_inventory",
                    description="根据物料编码或库位查询库存信息",
                    inputSchema=MaterialQuerySchema.model_json_schema(),
                ),
                Tool(
                    name="search_materials",
                    description="通过描述信息全文检索物料库存 (支持中文分词)",
                    inputSchema=MaterialSearchSchema.model_json_schema(),
                ),
            ]

        @self.server.call_tool()
        async def handle_call_tool(
            name: str, arguments: dict | None
        ) -> List[TextContent]:
            arguments = arguments or {}
            try:
                if name == "query_inventory":
                    return await self.query_inventory(MaterialQuerySchema(**arguments))
                elif name == "search_materials":
                    return await self.search_materials(
                        MaterialSearchSchema(**arguments)
                    )
                else:
                    raise ValueError(f"Unknown tool: {name}")
            except Exception as e:
                logger.error(f"Error executing tool {name}: {str(e)}")
                return [TextContent(type="text", text=f"错误: {str(e)}")]

    async def query_inventory(self, params: MaterialQuerySchema) -> List[TextContent]:
        query_parts = []
        sql_params = {}

        if params.material_code:
            query_parts.append("material_code LIKE :mcode")
            sql_params["mcode"] = f"%{params.material_code}%"

        if params.storage_bin:
            query_parts.append("storage_bin = :sbin")
            sql_params["sbin"] = params.storage_bin

        if not query_parts:
            return [TextContent(type="text", text="未提供查询条件")]

        where_clause = " AND ".join(query_parts)
        sql = f"SELECT * FROM material_inventory WHERE {where_clause} LIMIT 20"

        async with async_session() as session:
            result = await session.execute(text(sql), sql_params)
            rows = result.mappings().all()

        if not rows:
            return [TextContent(type="text", text="未找到相关库存记录")]

        return [TextContent(type="text", text=self._format_results(rows))]

    async def search_materials(self, params: MaterialSearchSchema) -> List[TextContent]:
        # 使用 Postgres 全文检索 (zhparser/jieba 需要环境支持，这里使用通用的 tsvector)
        # 根据用户提供的 SQL 模板进行适配
        sql = """
        SELECT *, ts_rank(to_tsvector('chinese', material_desc), plainto_tsquery('chinese', :query)) as rank
        FROM material_inventory
        WHERE to_tsvector('chinese', material_desc) @@ plainto_tsquery('chinese', :query)
        ORDER BY rank DESC
        LIMIT :limit
        """

        async with async_session() as session:
            try:
                result = await session.execute(
                    text(sql), {"query": params.query_text, "limit": params.limit}
                )
                rows = result.mappings().all()
            except Exception as e:
                # 如果 'chinese' 字典不存在，回退到 simple
                logger.warning(
                    f"Fulltext search with 'chinese' failed, falling back to 'simple': {e}"
                )
                sql_fallback = sql.replace("'chinese'", "'simple'")
                result = await session.execute(
                    text(sql_fallback),
                    {"query": params.query_text, "limit": params.limit},
                )
                rows = result.mappings().all()

        if not rows:
            return [
                TextContent(
                    type="text",
                    text=f"搜索关键词 '{params.query_text}' 未匹配到任何结果",
                )
            ]

        return [TextContent(type="text", text=self._format_results(rows))]

    def _format_results(self, rows: List[Any]) -> str:
        lines = []
        for row in rows:
            line = (
                f"物料: {row['material_code']} | 描述: {row['material_desc']} | "
                f"数量: {row['unrestricted_qty']} {row['base_uom']} | "
                f"库位: {row['storage_bin']}"
            )
            lines.append(line)
        return "\n".join(lines)


server = InventoryServer()
