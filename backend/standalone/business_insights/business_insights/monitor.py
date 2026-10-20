"""云端只读刷新任务；独立进程复用主平台连接，接口进程不持有数据库凭据。"""
import asyncio
from datetime import datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo


def now():
    return datetime.now(ZoneInfo('Asia/Shanghai'))


class Monitor:
    def __init__(self, python, worker, data, interval=900):
        if interval<300:
            raise ValueError('刷新间隔不得低于300秒')
        self.python=str(python)
        self.worker=str(Path(worker).resolve())
        self.data=Path(data)
        self.interval=interval
        self.task=None
        self.state={'phase':'未启动','last_attempt':None,'last_success':None,'next_run':None,
                    'last_error_type':None,'cycles':0,'result':None}

    def save(self):
        dest=self.data/'collection_status.json'
        temp=dest.with_suffix('.tmp')
        temp.write_text(json.dumps(self.status(),ensure_ascii=False,indent=2),encoding='utf-8')
        temp.chmod(0o600)
        temp.replace(dest)

    async def execute(self):
        process=await asyncio.create_subprocess_exec(self.python,self.worker,
            cwd=str(Path(self.worker).parents[2]),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            stdout,_=await asyncio.wait_for(process.communicate(),timeout=180)
            try:
                reply=json.loads(stdout)
            except (ValueError,TypeError):
                raise RuntimeError('刷新进程未返回有效结果') from None
            if process.returncode or reply.get('ok') is not True:
                # 只允许类型名，不采纳进程传来的任意错误内容。
                kind=reply.get('error_type','WorkerError')
                if not isinstance(kind,str) or not kind.isidentifier() or len(kind)>80:
                    kind='WorkerError'
                return {'ok':False,'error_type':kind}
            result=reply['result']
            if result.get('business_database_writes')!=0 or result.get('feishu_writes')!=0 or result.get('messages_sent')!=0:
                raise ValueError('刷新结果越过只读边界')
            return reply
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    async def run_once(self):
        self.state.update(phase='读取中',last_attempt=now().isoformat())
        self.save()
        try:
            reply=await self.execute()
            if not reply['ok']:
                self.state.update(phase='刷新失败，保留上次成功快照',last_error_type=reply['error_type'])
            else:
                self.state.update(phase='等待下次刷新',last_success=now().isoformat(),last_error_type=None,
                                  cycles=self.state['cycles']+1,result=reply['result'])
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.state.update(phase='刷新失败，保留上次成功快照',last_error_type=type(exc).__name__)
        self.state['next_run']=(now()+timedelta(seconds=self.interval)).isoformat()
        self.save()

    async def loop(self):
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # 状态文件写入失败也保留内存错误，不能把失效监测报告为成功。
                self.state.update(phase='刷新或状态持久化失败',last_error_type=type(exc).__name__)
            await asyncio.sleep(self.interval)

    async def start(self):
        if self.task and not self.task.done():return
        self.task=asyncio.create_task(self.loop(),name='business-insights-cloud-refresh')

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:await self.task
            except asyncio.CancelledError:pass
        self.state.update(phase='已停止',next_run=None)
        self.save()

    def status(self):
        return {**self.state,'running':self.task is not None and not self.task.done(),
                'interval_seconds':self.interval,'business_database_writes':0,'messages_sent':0,'feishu_writes':0}
