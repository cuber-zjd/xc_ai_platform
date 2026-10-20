"""本地演示入口；外部连接采用服务端配置的 Bearer 身份，不相信模型传入的角色。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .cards import card_for
from .engine import Insights, DEFAULT_SNAPSHOT
from .store import Store, Conflict
from .feishu_process import DEFAULT_CACHE, view as process_view, decorate as process_decorate

HERE=Path(__file__).resolve().parent
DATA=DEFAULT_SNAPSHOT.parent
security=HTTPBearer(auto_error=False)


class Ask(BaseModel):
    question:str=Field(min_length=1,max_length=1000)
    customer_code:str|None=None


class Scenario(BaseModel):
    quantity:float=Field(gt=0,le=1000000,description='产品数量，吨')
    factor:float=Field(gt=0,le=10,description='显式假设：每吨产品的原料耗用吨数')
    delta:float|None=Field(default=None,ge=-10000,le=10000,description='元/吨；空值使用快照内玉米28日价差')


class Feedback(BaseModel):
    action:Literal['assign','note','request_leader','decide','request_review','verify','return']
    note:str=Field(min_length=1,max_length=3000)
    evidence:str=Field(default='',max_length=3000)
    request_id:str=Field(min_length=8,max_length=100)
    version:int=Field(ge=1)


def create_app(snapshot_path=DEFAULT_SNAPSHOT, db_path=None, external=False, principal_map=None,monitor_interval=None,feishu_process_path=None,refresh_monitor=None):
    snapshot_path=Path(snapshot_path)
    snapshot_stamp=snapshot_path.stat().st_mtime_ns
    engine=Insights(json.loads(snapshot_path.read_text(encoding='utf-8')))
    store=Store(db_path) if db_path else Store()
    store.sync(engine.events())
    process_path = feishu_process_path or (DEFAULT_CACHE if snapshot_path.resolve()==DEFAULT_SNAPSHOT.resolve() else None)
    lock=threading.Lock()
    refresh_failed=False
    if not external or monitor_interval is not None:
        raise ValueError('服务器组件只支持外部只读快照模式')
    monitor=refresh_monitor
    @asynccontextmanager
    async def lifespan(_app):
        async with mcp_transport.router.lifespan_context(mcp_transport):
            if monitor:await monitor.start()
            try:yield
            finally:
                if monitor:await monitor.stop()
    app=FastAPI(title='健源经营助手 · 场景工具接口',version='0.1.0',
                description='客户经营、行情、资讯及本地过程闭环。数据为有截止日的只读快照；问数采用受控场景路由。',
                docs_url=None, redoc_url=None,lifespan=lifespan)
    if not external:
        app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])
    principals=principal_map or {}
    for key,p in principals.items():
        if (len(key)!=64 or any(ch not in '0123456789abcdef' for ch in key)
            or p.get('role') not in {'ops','leader','sales'} or not p.get('id') or not p.get('name')
            or (p['role']=='sales' and not p.get('owner'))):
            raise ValueError('身份映射必须使用SHA256令牌键、可信角色及完整业务员范围')
    personas=[{'id':'ops','name':'运营演示','role':'ops'},
              {'id':'leader','name':'领导演示','role':'leader'}]
    owners=sorted({c.get('owner') for c in engine.customers.values() if c.get('owner')})
    personas += [{'id':'sales-'+str(i),'name':o+' · 业务员演示','owner':o,'role':'sales'} for i,o in enumerate(owners)]
    if external and not principals:
        raise ValueError('外部模式必须配置服务端身份，不允许演示身份登录')

    @app.exception_handler(Conflict)
    async def conflict_error(_request,exc):
        return JSONResponse({'detail':str(exc)},409)

    @app.exception_handler(PermissionError)
    async def permission_error(_request,exc):
        return JSONResponse({'detail':str(exc)},403)

    @app.exception_handler(ValueError)
    async def value_error(_request,exc):
        return JSONResponse({'detail':str(exc)},422)

    @app.exception_handler(KeyError)
    async def missing_error(_request,exc):
        return JSONResponse({'detail':'未找到指定客户或事件'},404)

    @app.middleware('http')
    async def origin_guard(request,call_next):
        nonlocal engine,snapshot_stamp,refresh_failed
        origin=request.headers.get('origin')
        if not external and origin and urlparse(origin).netloc!=request.headers.get('host'):
            return JSONResponse({'detail':'不允许跨站请求'},403)
        # 采集器原子替换快照；完整解析后切换，失败时保留最近成功版本。
        try:
            stamp=snapshot_path.stat().st_mtime_ns
            if stamp!=snapshot_stamp:
                with lock:
                    if stamp!=snapshot_stamp:
                        updated=Insights(json.loads(snapshot_path.read_text(encoding='utf-8')))
                        updated.meta()
                        store.sync(updated.events())
                        engine=updated
                        app.state.engine=engine
                        snapshot_stamp=stamp
            refresh_failed=False
        except (ValueError,KeyError,OSError,TypeError):
            refresh_failed=True
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    def auth(credentials:HTTPAuthorizationCredentials|None=Depends(security)):
        if not credentials:
            raise HTTPException(401,'需要有效身份凭证')
        key=hashlib.sha256(credentials.credentials.encode()).hexdigest()
        principal=principals.get(key)
        if not principal:
            raise HTTPException(401,'身份凭证无效或已过期')
        return principal

    def allowed(p):
        return {code for code,c in engine.customers.items() if p['role']!='sales' or c['owner']==p.get('owner')}

    def check_customer(code,p):
        if code not in allowed(p):
            raise HTTPException(403,'客户超出当前身份的数据范围')

    def events_for(p):
        return process_decorate(store.decorate(engine.events(allowed(p))), process_view(process_path, allowed(p)))

    def public_customer(code,p):
        check_customer(code,p)
        return {**engine.customer(code),'feishu_followup':process_view(process_path, {code})}

    @app.get('/health')
    def health():
        source_failed=monitor.status().get('last_error_type') is not None if monitor else False
        return {'ok':True,'as_of':engine.s['as_of'],'external':external,'refresh_failed':refresh_failed or source_failed,
                'monitor_running':monitor.status()['running'] if monitor else False}

    if not external:
        @app.get('/api/demo/personas')
        def list_personas():
            return {'personas':personas,'notice':'本机演示身份；未连接真实飞书身份'}

        @app.post('/api/demo/session')
        async def demo_session(request:Request):
            payload=await request.json()
            p=next((p for p in personas if p['id']==payload.get('persona')),None)
            if not p:
                raise HTTPException(422,'请选择已配置演示角色')
            token=secrets.token_urlsafe(32)
            with lock:
                principals[hashlib.sha256(token.encode()).hexdigest()]=p
            return {'token':token,'principal':p}

        @app.get('/')
        def index():
            return FileResponse(HERE/'web/index.html')

        @app.get('/docs',include_in_schema=False)
        def docs():
            return FileResponse(HERE/'web/tools.html')

        app.mount('/assets',StaticFiles(directory=HERE/'web'),name='assets')

    @app.get('/api/meta',operation_id='get_data_context')
    def meta(p=Depends(auth)):
        followup=process_view(process_path, allowed(p))
        source_failed=monitor.status().get('last_error_type') is not None if monitor else False
        return {**engine.meta(),'principal':p,'refresh_failed':refresh_failed or source_failed,
                'feishu_process':{k:v for k,v in followup.items() if k!='events'},
                'scoped_feishu_event_count':len(followup['events']),
                'monitor':monitor.status() if monitor else {'running':False,'phase':'未启用'},
                'feishu_base':os.environ.get('INSIGHTS_FEISHU_BASE_URL',''),
                'integration':{'live_readonly_data':bool(monitor and monitor.status()['cycles']>0),
                               'data_mode':'固定客户聚合快照；云端已启用只读刷新' if monitor else '已验证聚合快照；未启用刷新',
                               'feishu_base_read_verified':True,
                               'readonly_mcp_available':True,
                               'native_agent_connected':False,'scheduled_refresh':monitor.status()['running'] if monitor else False,
                               'notifications_enabled':False,'external_network_verified':False}}

    @app.get('/api/customers',operation_id='list_scoped_customers')
    def customers(p=Depends(auth)):
        out=[]
        for code in allowed(p):
            c=engine.customer(code)
            out.append({k:c[k] for k in ['code','name','owner','segment','current_qty','previous_qty','change','yoy_change','latest_profit','days_since_delivery']})
        return sorted(out,key=lambda c:-c['current_qty'])

    @app.get('/api/customers/{code}',operation_id='get_customer_brief')
    def customer(code:str,p=Depends(auth)):
        return public_customer(code,p)

    @app.get('/api/radar',operation_id='get_priority_events')
    def radar(p=Depends(auth)):
        return events_for(p)

    @app.get('/api/events/{eid}',operation_id='get_event_evidence')
    def event(eid:str,p=Depends(auth)):
        e=store.get(eid)
        check_customer(e['code'],p)
        return process_decorate([e],process_view(process_path,allowed(p)))[0]

    @app.post('/api/ask',operation_id='ask_supported_business_question')
    def ask(body:Ask,p=Depends(auth)):
        result=engine.ask(body.question,allowed(p),body.customer_code)
        if result['tool']=='customer_brief':
            code=result['data']['code']
            result['data']['feishu_followup']=process_view(process_path,{code})
        elif result['tool']=='customer_radar':
            result['data']=process_decorate(store.decorate(result['data']),process_view(process_path,allowed(p)))
        if any(word in body.question for word in ['跟进到','处理到','核实结论','跟进状态','关闭了吗','飞书状态']):
            if result['tool']=='clarify_customer':
                return result
            codes={result['data']['code']} if result['tool']=='customer_brief' else allowed(p)
            if body.customer_code:
                check_customer(body.customer_code,p)
                codes={body.customer_code}
            followup=process_view(process_path,codes)
            result.update(tool='feishu_followup',data=followup,
                answer=(f"飞书过程回读截至{followup['read_at']}，当前授权范围内有{len(followup['events'])}条事件。"
                        if followup['available'] else '尚未读取到可用的飞书跟进结果，不能判断是否已处理。'))
            if followup['events']:
                result['answer']+='；'.join(
                    f"{engine.customers[e['code']]['name']}：{e['status']}，"
                    + ('已填写人工核实结论' if e.get('human_conclusion') else '人工核实结论暂为空')
                    for e in followup['events'][:5])+'。'
            result['answer']+='过程关闭不代表销量或利润已改善。'
            if followup['stale'] and followup['available']:
                result['answer']+='该快照已过期或刷新失败，需重新回读。'
        return result

    @app.get('/api/market',operation_id='get_market_brief')
    def market(p=Depends(auth)):
        return engine.market()

    @app.post('/api/scenario',operation_id='estimate_raw_material_scenario')
    def scenario(body:Scenario,p=Depends(auth)):
        return engine.simulate(body.quantity,body.factor,body.delta)

    @app.get('/api/opportunities',operation_id='get_news_opportunities')
    def opportunities(p=Depends(auth)):
        return engine.opportunities(allowed(p))

    @app.get('/api/feishu/cards/{eid}',operation_id='preview_feishu_card')
    def preview_card(eid:str,p=Depends(auth)):
        e=store.get(eid)
        check_customer(e['code'],p)
        return {'sent':False,'card':card_for(e,os.environ.get('INSIGHTS_PUBLIC_URL','http://127.0.0.1:8766')),
                'recipient':None,'notice':'候选卡片；未发送，原业务员尚未映射至飞书身份'}

    app.state.engine=engine
    app.state.store=store
    from .mcp_gateway import create_mcp
    hosts=['127.0.0.1:*','localhost:*','testserver']
    origins=['http://127.0.0.1:*','http://localhost:*']
    public=urlparse(os.environ.get('INSIGHTS_PUBLIC_URL',''))
    if external and public.scheme=='https' and public.netloc:
        hosts.append(public.netloc)
        origins.append('https://'+public.netloc)
    mcp_server,mcp_transport,mcp_gate=create_mcp(app,principals,hosts,origins)
    app.state.mcp_server=mcp_server
    app.mount('/mcp',mcp_gate,name='readonly-mcp')
    return app
