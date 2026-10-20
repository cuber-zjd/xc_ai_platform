"""合成数据验收：服务端权限、写入边界和反代配置幂等。"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('INSIGHTS_DATA_DIR', str(Path(tempfile.gettempdir())/'insights-test-only'))
os.environ.setdefault('INSIGHTS_PUBLIC_URL','https://pilot.example/business-insights')
from fastapi.testclient import TestClient
from business_insights.app import create_app
from deploy import patch_nginx, BEGIN, END


def fixture():
    return {'as_of':'2026-10-18','collected_at':'2026-10-19T10:00:00+08:00',
            'company':'测试','mode':'synthetic_test','scope':'合成两客户','freshness':{},'caveats':[],
            'customers':[{'code':'A','name':'合成甲','owner':'甲','segment':'饮料'},
                         {'code':'B','name':'合成乙','owner':'乙','segment':'乳品'}],
            'deliveries':[{'code':'A','day':'2026-09-20','qty':100,'product':'糖浆'},
                          {'code':'A','day':'2026-10-18','qty':10,'product':'糖浆'},
                          {'code':'B','day':'2026-10-18','qty':200,'product':'糖浆'}],
            'profits':[],'corn':[{'day':'2026-09-20','price':2240},{'day':'2026-10-18','price':2180}],
            'syrup':[],'news':[]}


class Boundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.snapshot = self.root/'snapshot.json'
        self.snapshot.write_text(json.dumps(fixture()),encoding='utf-8')
        self.token = 'synthetic-private-token'
        principals = {hashlib.sha256(self.token.encode()).hexdigest():
                      {'id':'test','name':'合成业务员','role':'sales','owner':'甲'}}
        self.app = create_app(self.snapshot,self.root/'state.sqlite3',external=True,principal_map=principals)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.headers = {'Authorization':'Bearer '+self.token}

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.temp.cleanup()

    def test_no_anonymous_business_or_demo_identity(self):
        self.assertEqual(self.client.get('/api/meta').status_code,401)
        self.assertEqual(self.client.post('/mcp/',json={}).status_code,401)
        self.assertEqual(self.client.post('/api/demo/session',json={'persona':'ops'}).status_code,404)
        with self.assertRaises(ValueError):create_app(self.snapshot,self.root/'other.sqlite3',external=False)

    def test_scope_and_no_feedback_endpoint(self):
        rows = self.client.get('/api/customers',headers=self.headers).json()
        self.assertEqual([r['code'] for r in rows],['A'])
        self.assertEqual(self.client.get('/api/customers/B',headers=self.headers).status_code,403)
        event = self.client.get('/api/radar',headers=self.headers).json()[0]
        self.assertEqual(self.client.post('/api/events/'+event['id']+'/feedback',headers=self.headers,json={}).status_code,404)
        meta = self.client.get('/api/meta',headers=self.headers).json()
        self.assertFalse(meta['integration']['live_readonly_data'])
        self.assertFalse(meta['integration']['notifications_enabled'])

    def test_scenario_and_mcp_origin_boundary(self):
        result = self.client.post('/api/scenario',headers=self.headers,json={'quantity':1000,'factor':1,'delta':-60})
        self.assertEqual(result.json()['estimated_cost_change'],-60000)
        self.assertEqual(self.client.post('/api/scenario',headers=self.headers,json={'quantity':1000,'factor':0}).status_code,422)
        self.assertEqual(self.client.post('/mcp/',headers={**self.headers,'Origin':'https://untrusted.example'},json={}).status_code,403)

    def test_nginx_idempotency_preserves_original_routes(self):
        original = b'server {\n location /console/api { proxy_pass http://api:5001; }\n}'
        block = BEGIN+'\n location /business-insights/ { proxy_pass http://pilot; }\n'+END
        once = patch_nginx(original,block)
        self.assertEqual(patch_nginx(once,block),once)
        self.assertIn(b'location /console/api { proxy_pass http://api:5001; }',once)
        self.assertEqual(once.count(BEGIN.encode()),1)
        with self.assertRaises(ValueError):patch_nginx(b'server {}',block)
        with self.assertRaises(ValueError):patch_nginx(original+original,block)

    def test_mcp_scenario_requires_three_plain_numeric_assumptions(self):
        headers={**self.headers,'Accept':'application/json, text/event-stream'}
        response=self.client.post('/mcp/',headers=headers,
                                  json={'jsonrpc':'2.0','id':1,'method':'tools/list'})
        self.assertEqual(response.status_code,200)
        tools=response.json()['result']['tools']
        self.assertEqual(len(tools),7)
        scenario=next(t for t in tools if t['name']=='estimate_raw_material_scenario')
        schema=scenario['inputSchema']
        self.assertEqual(set(schema['required']),{'quantity','factor','delta'})
        for value in schema['properties'].values():
            self.assertEqual(value['type'],'number')
            self.assertNotIn('anyOf',value)
            self.assertNotIn('exclusiveMinimum',value)
        def call(arguments):
            return self.client.post('/mcp/',headers=headers,json={
                'jsonrpc':'2.0','id':2,'method':'tools/call',
                'params':{'name':'estimate_raw_material_scenario','arguments':arguments}}).json()['result']
        result=call({'quantity':1000,'factor':1,'delta':-60})
        self.assertFalse(result.get('isError',False))
        self.assertEqual(result['structuredContent']['estimated_cost_change'],-60000)
        self.assertTrue(call({'quantity':1000,'factor':1})['isError'])
        self.assertTrue(call({'quantity':1000,'factor':1,'delta':None})['isError'])
        self.assertTrue(call({'quantity':0,'factor':1,'delta':-60})['isError'])
        self.assertTrue(call({'quantity':1000,'factor':0,'delta':-60})['isError'])


if __name__ == '__main__':
    unittest.main()
