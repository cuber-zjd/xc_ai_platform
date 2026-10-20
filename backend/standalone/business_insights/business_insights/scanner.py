"""刷新后生成去重候选；只写独立存储，不配置接收人或发送。"""
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from .engine import Insights
from .store import Store


def save(path,data):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.chmod(0o600)
    temp.replace(path)


def scan(data):
    data=Path(data)
    engine=Insights(json.loads((data/'snapshot.json').read_text(encoding='utf-8')))
    events=engine.events()
    ledger_path=data/'scan_ledger.json'
    ledger=json.loads(ledger_path.read_text(encoding='utf-8')) if ledger_path.exists() else {'seen':{}}
    clock=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
    new=[]
    for event in events:
        key=event['code']+'|'+event['kind']
        signature={'tone':event['tone'],'magnitude_bucket':int(event['magnitude_tons']//100)}
        old=ledger['seen'].get(key)
        if old is None or signature['magnitude_bucket']>=old['signature']['magnitude_bucket']+2:
            new.append({'event':event,'reason':'首次发现' if old is None else '变化量进一步扩大至少200吨',
                        'delivery_status':'待配置接收人；未发送'})
            ledger['seen'][key]={'event_id':event['id'],'signature':signature,'detected_at':clock}
    store=Store(data/'demo.sqlite3')
    store.sync(events)
    outbox_path=data/'outbox.json'
    previous=json.loads(outbox_path.read_text(encoding='utf-8')) if outbox_path.exists() else {'candidates':[]}
    queue={item['event']['id']:item for item in previous['candidates']}
    for item in new:queue[item['event']['id']]=item
    current={event['id']:event for event in events}
    for eid,item in queue.items():
        item['currently_triggered']=eid in current
        if eid in current:item['event']=current[eid]
        item['local_process_status']=store.get(eid)['status']
        item['eligible_for_review']=item['currently_triggered'] and item['local_process_status'] not in {'已关闭','已排除'}
    save(outbox_path,{'generated_at':clock,'as_of':engine.s['as_of'],'candidates':list(queue.values()),
                      'messages_sent':0,'notice':'仅为后台去重候选；接收人未配置，未发送；过程状态为独立本地状态。'})
    save(ledger_path,ledger)
    return {'new_candidates':len(new),'queued_candidates':len(queue),'messages_sent':0}
