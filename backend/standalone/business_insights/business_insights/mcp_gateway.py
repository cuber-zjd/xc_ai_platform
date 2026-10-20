"""标准只读MCP工具；复用业务HTTP接口及服务端身份，不重复实现权限。"""
from __future__ import annotations

import hashlib
from typing import Annotated, Any

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse


INSTRUCTIONS='''你是健源经营助手。先调用get_data_context确认数据期间和范围，再根据问题调用具体工具。
所有工具只读，不发送消息、不执行SQL、不修改经营或协作数据。客户权限由Bearer凭证绑定，禁止让用户输入业务员名字以获得权限。
发货下降、月度利润变化、品牌资讯只是待核实线索，不能直接断言流失、原因或订单。利润和销量分别注明期间。
缺少去年同期数据时同比不可比；成本情景是显式假设，不是实际利润。回答保留来源及截止日，并提出一个具体核实动作。'''
INSTRUCTIONS+='\n飞书过程状态在客户简报feishu_followup和事件feishu_process中，和本地status分开。注明read_at及stale；没有回读记录不能视为未跟进。飞书关闭不等于经营改善。'


class BearerGate:
    def __init__(self,app,principals):
        self.app=app
        self.principals=principals

    async def __call__(self,scope,receive,send):
        if scope['type']=='http':
            header=Request(scope).headers.get('authorization','')
            scheme,_,token=header.partition(' ')
            principal=self.principals.get(hashlib.sha256(token.encode()).hexdigest()) if scheme.lower()=='bearer' and token else None
            if principal is None:
                response=JSONResponse({'detail':'需要有效身份凭证'},401,headers={'WWW-Authenticate':'Bearer'})
                await response(scope,receive,send)
                return
        await self.app(scope,receive,send)


def create_mcp(business_app,principals,allowed_hosts,allowed_origins):
    server=MCPServer('jianyuan-business-insights',title='健源经营助手',version='0.2.0',
                     instructions=INSTRUCTIONS,log_level='ERROR')
    readonly=ToolAnnotations(read_only_hint=True,destructive_hint=False,idempotent_hint=True,open_world_hint=False)

    async def call(path,ctx,body=None):
        request=ctx.request_context.request
        if request is None:
            raise ValueError('此服务仅接受已认证HTTP工具调用')
        header=request.headers.get('authorization','')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=business_app),base_url='http://localhost') as client:
            response=await client.request('POST' if body is not None else 'GET',path,
                                          headers={'Authorization':header},json=body)
        data=response.json()
        if not response.is_success:
            detail=data.get('detail','工具调用未完成')
            raise ValueError(detail if isinstance(detail,str) else '工具参数不符合业务接口要求')
        return data

    @server.tool(annotations=readonly,structured_output=True)
    async def get_data_context(ctx:Context)->dict[str,Any]:
        """先查数据截止日、选定客户范围、口径及限制；不能把试点当作公司全量。"""
        return await call('/api/meta',ctx)

    @server.tool(annotations=readonly,structured_output=True)
    async def list_scoped_customers(ctx:Context)->dict[str,Any]:
        """列出当前凭证有权查看的客户，返回编码供后续查询；不接受业务员或角色参数。"""
        rows=await call('/api/customers',ctx)
        return {'customers':rows,'count':len(rows)}

    @server.tool(annotations=readonly,structured_output=True)
    async def get_customer_brief(customer_code:Annotated[str,Field(min_length=1,max_length=30)],ctx:Context)->dict[str,Any]:
        """按授权客户编码查发货、同比、月度利润及飞书过程回读feishu_followup。注明各自期间；过期或缺失回读不能推断实时跟进状态。"""
        from urllib.parse import quote
        return await call('/api/customers/'+quote(customer_code,safe=''),ctx)

    @server.tool(annotations=readonly,structured_output=True)
    async def get_priority_events(ctx:Context,limit:Annotated[int,Field(ge=1,le=20)]=5)->dict[str,Any]:
        """获取授权客户线索。local_status为本地演示；feishu_process为带读取时间的飞书过程快照，两者不可混同。"""
        rows=await call('/api/radar',ctx)
        return {'events':rows[:limit],'total':len(rows),'ranking':'选定客户范围，风险优先，再按发货变化量排序'}

    @server.tool(annotations=readonly,structured_output=True)
    async def get_market_brief(ctx:Context)->dict[str,Any]:
        """查询玉米采购价和同地区、企业、规格的糖浆报价；市场价不等同本公司成交价。"""
        return await call('/api/market',ctx)

    @server.tool(annotations=readonly,structured_output=True)
    async def estimate_raw_material_scenario(
        quantity:Annotated[float,Field(gt=0,le=1000000,allow_inf_nan=False)],
        factor:Annotated[float,Field(gt=0,le=10,allow_inf_nan=False)],ctx:Context,
        delta:Annotated[float|None,Field(ge=-10000,le=10000,allow_inf_nan=False)]=None)->dict[str,Any]:
        """数量吨×显式原料耗用系数×价差元/吨。系数必须由调用方明确给出；结果非实际损益。"""
        return await call('/api/scenario',ctx,{'quantity':quantity,'factor':factor,'delta':delta})

    @server.tool(annotations=readonly,structured_output=True)
    async def get_news_opportunities(ctx:Context)->dict[str,Any]:
        """查询官方资讯与有权查看客户的品牌关联；区分近期与历史，不证明采购需求或主体关系。"""
        rows=await call('/api/opportunities',ctx)
        return {'opportunities':rows,'count':len(rows),'fresh_count':sum(r['fresh'] for r in rows)}

    transport=server.streamable_http_app(streamable_http_path='/',stateless_http=True,json_response=True,
                                          max_request_body_size=65536,
                                          transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                              allowed_hosts=allowed_hosts,allowed_origins=allowed_origins))
    return server,transport,BearerGate(transport,principals)
