"""合成验证：固定客户聚合、失败保留、生命周期与取数子进程回收。"""
import asyncio
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from test_boundary import fixture
from business_insights.collector import collect, validate_sql
from business_insights.monitor import Monitor
from business_insights.scanner import scan


class Cursor:
    def __init__(self,conn):
        self.conn=conn

    def execute(self,sql,params):
        self.conn.queries.append((sql,params))
        response=self.conn.responses.pop(0)
        if isinstance(response,Exception):raise response
        self.rows=response
        self.keys=list(response[0]) if response else []
        self.description=[(key,) for key in self.keys]

    def fetchmany(self,limit):
        return [tuple(row[k] for k in self.keys) for row in self.rows[:limit]]

    def close(self):pass


class Connection:
    def __init__(self,responses):
        self.responses=responses
        self.queries=[]
        self.closed=False

    def cursor(self):return Cursor(self)
    def close(self):self.closed=True


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'snapshot.json'
        self.data=fixture()
        for row in self.data['customers']+self.data['deliveries']:
            row['code']={'A':'101','B':'202'}[row['code']]
        self.data['news']=[{'id':'synthetic-source','title':'合成来源保留'}]
        self.path.write_text(json.dumps(self.data),encoding='utf-8')
        self.original=self.path.read_bytes()

    def tearDown(self):self.temp.cleanup()

    def connection(self):
        return Connection([[],self.data['customers'],self.data['deliveries'],[],self.data['corn'],[],
                           [{'delivery':'2026-10-18','future_delivery_rows':0,'future_corn_rows':0,'invalid_profit_period_rows':0}]])

    def test_fixed_scope_queries_dates_and_news_preserved(self):
        conn=self.connection()
        result=collect(date(2026,10,18),conn,['101','202'],self.path)
        self.assertTrue(conn.closed)
        self.assertEqual(len(result['provenance']),7)
        self.assertEqual(result['news'],self.data['news'])
        self.assertIn('固定2家',result['scope'])
        cohort_sql,cohort_params=conn.queries[1]
        self.assertNotIn('TOP',cohort_sql)
        self.assertEqual(cohort_params,('101','202'))
        delivery_sql,delivery_params=conn.queries[2]
        self.assertIn('posting_date < %s',delivery_sql)
        self.assertEqual(delivery_params[-1],'20261019')
        self.assertTrue(all(not validate_sql(sql) for sql,_ in conn.queries))

    def test_query_failure_and_missing_customer_preserve_snapshot(self):
        for change in ['query_error','missing_customer']:
            conn=self.connection()
            if change=='query_error':conn.responses[2]=RuntimeError('合成数据库失败')
            else:conn.responses[1]=self.data['customers'][:1]
            with self.assertRaises((ValueError,RuntimeError)):
                collect(date(2026,10,18),conn,['101','202'],self.path)
            self.assertTrue(conn.closed)
            self.assertEqual(self.path.read_bytes(),self.original)

    def test_oversized_result_rejected_without_partial_save(self):
        conn=self.connection()
        conn.responses[2]=[self.data['deliveries'][0]]*20001
        with self.assertRaises(RuntimeError):collect(date(2026,10,18),conn,['101','202'],self.path)
        self.assertEqual(self.path.read_bytes(),self.original)

    def test_scope_and_time_cannot_expand_or_regress(self):
        for codes,day in [(['101','303'],date(2026,10,18)),(['101','101'],date(2026,10,18)),
                          (["101'; DROP TABLE x",'202'],date(2026,10,18)),(['101','202'],date(2026,10,17))]:
            conn=self.connection()
            with self.assertRaises(ValueError):collect(day,conn,codes,self.path)
            self.assertEqual(conn.queries,[])
            self.assertEqual(self.path.read_bytes(),self.original)
        for sql in ['DELETE FROM x','SELECT * INTO y FROM x','SELECT 1; DROP TABLE x','EXEC p']:
            self.assertTrue(validate_sql(sql))

    def test_scan_repeated_run_preserves_unsent_queue(self):
        first=scan(self.path.parent)
        second=scan(self.path.parent)
        self.assertGreater(first['new_candidates'],0)
        self.assertEqual(second['new_candidates'],0)
        self.assertEqual(first['queued_candidates'],second['queued_candidates'])
        queue=json.loads((self.path.parent/'outbox.json').read_text(encoding='utf-8'))
        self.assertEqual(queue['messages_sent'],0)
        self.assertTrue(all(item['delivery_status']=='待配置接收人；未发送' for item in queue['candidates']))


class MonitorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.monitor=Monitor('python','worker.py',self.temp.name)

    async def asyncTearDown(self):
        if self.monitor.task:await self.monitor.stop()
        self.temp.cleanup()

    async def test_live_lifecycle_and_failure_preserve_last_success(self):
        done=asyncio.Event()
        async def success():
            done.set()
            return {'ok':True,'result':{'as_of':'2026-10-18','business_database_writes':0,'feishu_writes':0,'messages_sent':0}}
        self.monitor.execute=success
        await self.monitor.start()
        await asyncio.wait_for(done.wait(),2)
        status=self.monitor.status()
        self.assertTrue(status['running'])
        self.assertEqual(status['cycles'],1)
        self.assertIsNotNone(status['last_success'])
        self.monitor.execute=AsyncMock(return_value={'ok':False,'error_type':'OperationalError'})
        await self.monitor.run_once()
        failed=self.monitor.status()
        self.assertEqual(failed['last_success'],status['last_success'])
        self.assertEqual(failed['cycles'],1)
        self.assertEqual(failed['last_error_type'],'OperationalError')
        self.assertEqual(failed['result'],status['result'])
        saved=json.loads((Path(self.temp.name)/'collection_status.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['last_error_type'],'OperationalError')
        await self.monitor.stop()
        self.assertFalse(self.monitor.status()['running'])

    async def test_cancelled_collection_kills_and_reaps_child(self):
        started=asyncio.Event()
        class Process:
            returncode=None
            killed=False
            reaped=False
            async def communicate(self):
                started.set()
                await asyncio.Event().wait()
            def kill(self):self.killed=True
            async def wait(self):
                self.returncode=-9
                self.reaped=True
        child=Process()
        with patch('asyncio.create_subprocess_exec',AsyncMock(return_value=child)):
            task=asyncio.create_task(self.monitor.execute())
            await asyncio.wait_for(started.wait(),2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(child.killed and child.reaped)


if __name__=='__main__':unittest.main()
