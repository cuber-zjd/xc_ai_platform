import re
from typing import Any, List, Optional
from fastapi import APIRouter, Depends
from sqlmodel import select, or_
from sqlalchemy import text
from app.api import deps
from app.db.session import async_session, get_db
from app.models.system.sys_user import SysUser
from app.schemas.result import Result
from app.schemas.inventory import MaterialQueryRequest, MaterialItem, WarehouseData
from app.core.llm_factory import LLMFactory
from app.core.logger import logger

router = APIRouter()


def parse_storage_bin(storage_bin: str) -> dict:
    """解析仓位编码，返回各部分"""
    pattern = r"(\d+)楼(\d+)排(\d+)组(\d+)层(\d+)格"
    match = re.match(pattern, storage_bin)
    if match:
        return {
            "floor": int(match.group(1)),
            "row": int(match.group(2)),
            "group": int(match.group(3)),
            "level": int(match.group(4)),
            "cell": int(match.group(5))
        }
    return None


def build_where_clause(conditions: dict) -> tuple[str, dict]:
    """构建 SQL WHERE 子句"""
    where_parts = []
    params = {}
    
    if conditions.get("material_code"):
        where_parts.append("material_code LIKE :material_code")
        params["material_code"] = f"%{conditions['material_code']}%"
    
    if conditions.get("material_desc"):
        where_parts.append("material_desc LIKE :material_desc")
        params["material_desc"] = f"%{conditions['material_desc']}%"
    
    if conditions.get("floor") is not None:
        where_parts.append("storage_bin LIKE :floor")
        params["floor"] = f"{conditions['floor']}楼%"
    
    if conditions.get("row") is not None:
        where_parts.append("storage_bin LIKE :row")
        params["row"] = f"%{conditions['row']}排%"
    
    if conditions.get("group") is not None:
        where_parts.append("storage_bin LIKE :group")
        params["group"] = f"%{conditions['group']}组%"
    
    if conditions.get("storage_bin"):
        where_parts.append("storage_bin = :storage_bin")
        params["storage_bin"] = conditions["storage_bin"]
    
    where_clause = " AND ".join(where_parts) if where_parts else "1=1"
    return where_clause, params


async def search_materials_vector(query_text: str, limit: int = 20) -> List[dict]:
    """使用 Postgres 全文检索进行分词查询"""
    sql = """
    SELECT id, material_code, material_desc, storage_loc, storage_bin, 
           unrestricted_qty, base_uom, material_group, net_amount,
           ts_rank(to_tsvector('chinese', material_desc), plainto_tsquery('chinese', :query)) as rank
    FROM material_inventory
    WHERE to_tsvector('chinese', material_desc) @@ plainto_tsquery('chinese', :query)
       OR material_code LIKE :like_query
    ORDER BY rank DESC
    LIMIT :limit
    """
    
    async with async_session() as session:
        try:
            result = await session.execute(
                text(sql), {"query": query_text, "like_query": f"%{query_text}%", "limit": limit}
            )
            return result.mappings().all()
        except Exception as e:
            logger.warning(f"Fulltext search failed, fallback to simple: {e}")
            sql_fallback = """
            SELECT id, material_code, material_desc, storage_loc, storage_bin, 
                   unrestricted_qty, base_uom, material_group, net_amount
            FROM material_inventory
            WHERE material_desc LIKE :q OR material_code LIKE :q
            LIMIT :limit
            """
            result = await session.execute(
                text(sql_fallback), {"q": f"%{query_text}%", "limit": limit}
            )
            return result.mappings().all()


async def parse_natural_language(query: str) -> dict:
    """使用 LLM 解析自然语言查询"""
    prompt = f"""你是一个库存查询助手。请将用户的自然语言查询转换为结构化的查询条件。

用户输入: {query}

请根据以下格式输出JSON（只输出JSON，不要其他内容）：
{{
    "material_code": "模糊匹配的物料编码（可选）",
    "material_desc": "模糊匹配的物料描述关键词（可选）",
    "floor": 楼层数字（可选，如1或2）,
    "row": 排数字（可选，1-6）,
    "group": 组数字（可选，1-6）,
    "level": 层数字（可选，1-4）,
    "storage_bin": 完整仓位编码（可选）
}}

如果无法确定具体条件，返回空对象 {{}}。
只返回JSON，不要其他内容。"""

    try:
        llm = LLMFactory.get_model(temperature=0.1, json_mode=True, streaming=False)
        response = await llm.ainvoke(prompt)
        content = response.content.strip()
        
        # 尝试解析 JSON
        if "{" in content and "}" in content:
            json_str = content[content.find("{"):content.rfind("}")+1]
            import json
            result = json.loads(json_str)
            
            # 转换字符串数字为整数
            for key in ["floor", "row", "group", "level"]:
                if key in result and result[key]:
                    try:
                        result[key] = int(result[key])
                    except (ValueError, TypeError):
                        result[key] = None
            
            logger.info(f"LLM 解析结果: {result}")
            return result
    except Exception as e:
        logger.error(f"LLM 解析失败: {e}")
    
    # 尝试本地解析（关键词匹配）
    result = {}
    
    # 楼层
    if "一楼" in query or "一层" in query:
        result["floor"] = 1
    elif "二楼" in query or "二层" in query:
        result["floor"] = 2
    
    # 排
    for i in range(1, 7):
        if f"{i}排" in query:
            result["row"] = i
            break
    
    # 组
    for i in range(1, 7):
        if f"{i}组" in query:
            result["group"] = i
            break
    
    # 层
    for i in range(1, 5):
        if f"{i}层" in query:
            result["level"] = i
            break
    
    # 物料编码（简单匹配）
    code_match = re.search(r'[A-Za-z0-9]{4,}', query)
    if code_match:
        result["material_code"] = code_match.group()
    
    return result


@router.get("/warehouse", response_model=Result[WarehouseData])
async def get_warehouse_data(
    db: Any = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Any:
    """获取仓库所有物料数据（用于3D建模）"""
    async with async_session() as session:
        result = await session.execute(
            text("SELECT id, material_code, material_desc, storage_loc, storage_bin, "
                 "unrestricted_qty, base_uom, material_group, net_amount "
                 "FROM material_inventory")
        )
        rows = result.mappings().all()
    
    materials = [MaterialItem(**row) for row in rows]
    return Result.success(data=WarehouseData(materials=materials, total=len(materials)))


@router.post("/query", response_model=Result[List[MaterialItem]])
async def query_materials(
    request: MaterialQueryRequest,
    db: Any = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Any:
    """查询物料"""
    # 如果是纯文本或者从输入框来的（这里后端根据 query 内容简单判断，或者前端传参，
    # 但根据用户要求：输入框输入直接搜索。
    # 逻辑：如果 query 包含特定仓位描述则走 NL 解析，否则走全文检索。
    
    is_complex = any(k in request.query for k in ["楼", "排", "组", "层", "格"])
    
    if not is_complex:
        # 直接使用全文检索/分词查询
        rows = await search_materials_vector(request.query, request.limit)
    else:
        # 解析自然语言
        conditions = await parse_natural_language(request.query)
        
        # 构建 WHERE 子句
        where_clause, params = build_where_clause(conditions)
        
        # 执行查询
        sql = f"SELECT id, material_code, material_desc, storage_loc, storage_bin, "
        sql += f"unrestricted_qty, base_uom, material_group, net_amount "
        sql += f"FROM material_inventory WHERE {where_clause} LIMIT :limit"
        params["limit"] = request.limit
        
        async with async_session() as session:
            result = await session.execute(text(sql), params)
            rows = result.mappings().all()
    
    materials = [MaterialItem(**row) for row in rows]
    return Result.success(data=materials)
