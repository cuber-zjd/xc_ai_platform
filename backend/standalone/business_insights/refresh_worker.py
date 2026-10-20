"""使用主平台现有环境读取命名连接；仅输出聚合计数，不输出连接或异常详情。"""
import asyncio
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
BACKEND=ROOT.parents[1]
sys.path.insert(0,str(BACKEND))
os.environ.setdefault('INSIGHTS_DATA_DIR',str(ROOT/'storage'))


async def connection_config(name):
    import asyncpg
    from app.core.config import settings
    conn=await asyncpg.connect(str(settings.sqlalchemy_database_uri).replace('postgresql+asyncpg://','postgresql://'),timeout=15,command_timeout=20)
    try:
        async with conn.transaction(readonly=True):
            rows=await conn.fetch('''SELECT id,host,port,database,username,password FROM fr_report_database_connection
                WHERE lower(connection_name)=lower($1) AND is_deleted=0 AND status='active' AND db_type='sqlserver'
                ORDER BY id LIMIT 2''',name)
        if len(rows)!=1 or not rows[0]['password']:
            raise ValueError('命名连接缺失、重复或不可用')
        return dict(rows[0])
    finally:
        await conn.close()


def refresh():
    import pymssql
    from business_insights.collector import collect
    from business_insights.scanner import scan
    data=Path(os.environ['INSIGHTS_DATA_DIR'])
    scope=json.loads((data/'collection_scope.json').read_text(encoding='utf-8'))
    cfg=asyncio.run(connection_config(scope['connection_name']))
    conn=pymssql.connect(server=cfg['host'],port=int(cfg['port']),database=cfg['database'],
                         user=cfg['username'],password=cfg['password'],charset='UTF-8',
                         timeout=45,login_timeout=15,autocommit=False)
    try:
        as_of=datetime.now(ZoneInfo('Asia/Shanghai')).date()-timedelta(days=1)
        snapshot=collect(as_of,conn,scope['customer_codes'],data/'snapshot.json')
        candidates=scan(data)
        return {'as_of':snapshot['as_of'],'collected_at':snapshot['collected_at'],
                'customers':len(snapshot['customers']),'aggregate_rows':len(snapshot['deliveries']),
                'query_count':len(snapshot['provenance']),'fixed_customer_scope':True,
                'business_database_writes':0,'messages_sent':0,'feishu_writes':0,**candidates}
    finally:
        # 聚合器成功进入查询后会关闭连接；前置校验失败时由这里兜底。
        try:conn.close()
        except pymssql.InterfaceError:pass


if __name__=='__main__':
    try:
        result=refresh()
        sys.stdout.write(json.dumps({'ok':True,'result':result},ensure_ascii=False)+'\n')
    except Exception as exc:
        sys.stdout.write(json.dumps({'ok':False,'error_type':type(exc).__name__})+'\n')
        sys.exit(1)
