"""飞书过程快照读取；服务器不持有飞书凭据或写入能力。"""
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from .engine import DEFAULT_SNAPSHOT
DEFAULT_CACHE = DEFAULT_SNAPSHOT.parent / 'feishu_process.json'
BASE_URL = os.environ.get('INSIGHTS_FEISHU_BASE_URL', '')
BASE = os.environ.get('INSIGHTS_FEISHU_BASE_TOKEN', '')
TABLE = os.environ.get('INSIGHTS_FEISHU_TABLE', '')
STATUSES = {'待运营核实','待分派','跟进中','待领导决策','待复核','已关闭','已排除'}

def now():
    return datetime.now(ZoneInfo('Asia/Shanghai'))

def view(path, allowed, clock=None):
    """每次请求读缓存；先按可信客户范围过滤，未读取与未知状态均不能解释成未跟进。"""
    clock = clock or now()
    unavailable = {'available': False, 'read_at': None, 'stale': True, 'refresh_failed': False,
                   'source': '飞书经营事件表只读回读', 'events': [],
                   'notice': '尚无可用飞书过程回读，不能据此判断跟进状态。'}
    if path is None:
        return unavailable
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if (data['base_token'], data['table_id']) != (BASE, TABLE):
            raise ValueError('目标不一致')
        read_at = datetime.fromisoformat(data['read_at'])
        if read_at.utcoffset() is None or read_at > clock + timedelta(minutes=5):
            raise ValueError('回读时间无效')
        seen = set()
        for event in data['events']:
            if event['event_id'] in seen or event['status'] not in STATUSES or not event.get('code'):
                raise ValueError('缓存事件不唯一或状态不明确')
            seen.add(event['event_id'])
        status_path = path.with_suffix('.status.json')
        refresh_failed = False
        if status_path.exists():
            status = json.loads(status_path.read_text(encoding='utf-8'))
            refresh_failed = status.get('ok') is False and datetime.fromisoformat(status['last_attempt']) >= read_at
        scoped = [{**event, 'source_url': BASE_URL, 'read_at': data['read_at'],
                   'business_outcome': '仅为过程状态；经营改善需后续经营数据验证'}
                  for event in data['events'] if event['code'] in allowed]
        stale = refresh_failed or clock - read_at > timedelta(minutes=30)
        return {'available': True, 'read_at': data['read_at'], 'stale': stale,
                'refresh_failed': refresh_failed, 'source': unavailable['source'], 'events': scoped,
                'notice': ('上次读取的飞书过程快照已过期或刷新失败，需重新回读。' if stale else
                           '飞书过程快照；独立于本地演示反馈及当前经营数据，不代表实时状态。无对应记录不代表未跟进。')}
    except (OSError, ValueError, KeyError, TypeError):
        return unavailable

def decorate(events, process):
    index = {(e['event_id'], e['code']): e for e in process['events']}
    return [{**event, 'local_status': event['status'],
             'feishu_process': ({**index[(event['id'], event['code'])], 'stale': process['stale']}
                               if (event['id'], event['code']) in index else None)} for event in events]
