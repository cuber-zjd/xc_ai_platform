"""本地过程状态与幂等反馈；不回写经营数据库。"""
import os
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_DB=Path(os.environ['INSIGHTS_DATA_DIR'])/'demo.sqlite3'


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, path=DEFAULT_DB):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, payload TEXT NOT NULL,status TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS feedback (
                request_id TEXT PRIMARY KEY,event_id TEXT NOT NULL,actor TEXT NOT NULL,
                action TEXT NOT NULL,note TEXT NOT NULL,evidence TEXT NOT NULL,
                created_at TEXT NOT NULL,body_hash TEXT NOT NULL,result TEXT NOT NULL);''')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10)
        db.row_factory=sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def sync(self, events):
        with self.connect() as db:
            for e in events:
                db.execute('INSERT INTO events(id,payload,status) VALUES(?,?,?) '
                           'ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, '
                           'version=events.version+CASE WHEN events.payload<>excluded.payload THEN 1 ELSE 0 END',
                           (e['id'],json.dumps(e,ensure_ascii=False),e['status']))

    def get(self,eid):
        with self.connect() as db:
            row=db.execute('SELECT * FROM events WHERE id=?',(eid,)).fetchone()
            if row is None:
                raise KeyError(eid)
            history=[dict(r) for r in db.execute('SELECT actor,action,note,evidence,created_at FROM feedback WHERE event_id=? ORDER BY rowid',(eid,))]
        return {**json.loads(row['payload']),'status':row['status'],'version':row['version'],'history':history}

    def decorate(self,events):
        return [self.get(e['id']) for e in events]

    def feedback(self,eid,principal,action,note,evidence,request_id,version):
        if not note.strip():
            raise ValueError('请填写实际处理说明')
        if action=='verify' and not evidence.strip():
            raise ValueError('复核关闭必须填写核实依据；提交跟进不代表经营恢复')
        body=json.dumps([eid,principal['id'],action,note,evidence,version],ensure_ascii=False)
        body_hash=hashlib.sha256(body.encode()).hexdigest()
        roles={'assign':['ops'],'note':['sales','ops'],'request_leader':['sales','ops'],
               'decide':['leader'],'request_review':['sales','ops'],'verify':['ops'],'return':['ops']}
        transitions={'assign':({'待核实'},'跟进中'),'note':({'跟进中'},'跟进中'),
                     'request_leader':({'跟进中'},'待领导决策'),
                     'decide':({'待领导决策'},'跟进中'),'request_review':({'跟进中'},'待复核'),
                     'verify':({'待复核'},'已关闭'),'return':({'待复核'},'跟进中')}
        if action not in roles or principal['role'] not in roles[action]:
            raise PermissionError('当前角色无权执行此动作')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM feedback WHERE request_id=?',(request_id,)).fetchone()
            if old:
                if old['body_hash']!=body_hash:
                    raise Conflict('同一请求编号已用于不同内容')
                return json.loads(old['result'])
            row=db.execute('SELECT * FROM events WHERE id=?',(eid,)).fetchone()
            if row is None:
                raise KeyError(eid)
            payload=json.loads(row['payload'])
            if principal['role']=='sales' and payload['owner']!=principal.get('owner'):
                raise PermissionError('无权处理其他业务员的客户')
            if row['version']!=version:
                raise Conflict('事件已更新，请刷新后重新提交')
            states,target=transitions[action]
            if row['status'] not in states:
                raise Conflict('当前事件状态不允许此动作')
            now=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
            result={'ok':True,'event_id':eid,'status':target,'version':version+1,
                    'business_outcome':'仅完成过程复核；经营改善需后续数据验证' if action=='verify' else '尚未复核'}
            db.execute('UPDATE events SET status=?,version=version+1 WHERE id=?',(target,eid))
            db.execute('INSERT INTO feedback VALUES(?,?,?,?,?,?,?,?,?)',
                       (request_id,eid,principal['name'],action,note,evidence,now,body_hash,json.dumps(result,ensure_ascii=False)))
        return result
