"""合成验收：来源边界、日期证据、去重、失败保留和低频更新。"""
import copy
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
import httpx

from test_boundary import fixture
from business_insights.news_feed import CONFIG, collect_source, fetch, merge_news, refresh_news, validate_url
from business_insights.engine import Insights

NOW = datetime(2026, 10, 20, 10, tzinfo=ZoneInfo('Asia/Shanghai'))
SOURCES = json.loads(CONFIG.read_text(encoding='utf-8'))
ARTICLE = 'https://scs.moa.gov.cn/jcyj/202610/t20261009_123.htm'
INDEX = '<a href="./202610/t20261009_123.htm">2026年10月中国农产品供需形势分析（CASDE-No.124）</a>'
BODY = '''<meta name="ArticleTitle" content="2026年10月中国农产品供需形势分析">
<meta name="PubDate" content="2026-10-09 12:00:00"><script>伪正文</script>
<div>玉米：本期报告认为这是用于测试的合成宏观判断，不是本企业成交价。''' + '合成报告正文。' * 12 + '''玉米首席分析师
食糖 ：本期报告中的食糖供需判断仅为测试数据。''' + '合成报告正文。' * 12 + '食糖首席分析师</div>'


def rss(title='Coca-Cola Reports Third Quarter Results', stamp='Tue, 20 Oct 26 00:00:00 -0400', host='investors.coca-colacompany.com'):
    return f'''<rss><channel><item><title>{title}</title>
    <link>https://{host}/news-events/press-releases/detail/1/sample-results</link>
    <pubDate>{stamp}</pubDate></item></channel></rss>'''


class NewsTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_blocks_private_dns_redirects_and_oversized_body(self):
        source=SOURCES['sources'][0]
        with patch('business_insights.news_feed.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ValueError):
                await fetch(source['url'],source,listing=True)
        for status,body,headers in [(302,b'',{'location':'https://127.0.0.1/'}),(200,b'x'*1_000_001,{})]:
            requests=[]
            def handler(request):
                requests.append(str(request.url))
                return httpx.Response(status,content=body,headers=headers)
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler),follow_redirects=False)
            with patch('business_insights.news_feed.socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443))]), patch('business_insights.news_feed.httpx.AsyncClient',return_value=client):
                with self.assertRaises((ValueError,httpx.HTTPStatusError)):
                    await fetch(source['url'],source,listing=True)
            self.assertEqual(len(requests),1)

    async def test_dates_topics_and_only_title_candidate(self):
        calls = []
        async def get(url, source, listing=False):
            calls.append(url)
            return rss() if source['kind']=='rss' else INDEX if listing else BODY
        with tempfile.TemporaryDirectory() as folder:
            cache = await refresh_news(Path(folder), now=NOW, get=get)
            self.assertEqual(len(calls), 3)
            self.assertEqual([s['status'] for s in cache['sources']], ['success', 'success'])
            rows, state = merge_news([], cache)
            self.assertEqual({r.get('topic') for r in rows if r.get('category')=='raw_material'}, {'玉米','食糖'})
            self.assertTrue(all(r['published']=='2026-10-09' for r in rows if r.get('topic')))
            brand = next(r for r in rows if r['category']=='brand')
            self.assertEqual(brand['published'], '2026-10-20')
            self.assertEqual(brand['summary_type'], '仅标题候选')
            self.assertNotIn('items', state['sources'][0])
            calls.clear()
            await refresh_news(Path(folder), now=NOW+timedelta(minutes=15), get=get)
            self.assertEqual(calls, [])
            # 一家来源失败不影响另一家，旧内容和成功时间保留；失败后1小时内不密集重试。
            async def partial(url, source, listing=False):
                if source['kind']=='rss':
                    raise TimeoutError('合成来源失败')
                return INDEX if listing else BODY
            failed = await refresh_news(Path(folder), now=NOW+timedelta(hours=7), get=partial)
            self.assertEqual(failed['sources'][0]['status'], 'success')
            self.assertEqual(failed['sources'][1]['status'], 'failed')
            self.assertEqual(failed['sources'][1]['items'], cache['sources'][1]['items'])
            self.assertEqual(failed['sources'][1]['last_success'], cache['sources'][1]['last_success'])

    async def test_future_dates_and_missing_body_fail_without_fabrication(self):
        for body in [BODY.replace('2026-10-09 12:00:00','2026-10-21 12:00:00'), BODY.replace('食糖首席分析师','缺少正文边界')]:
            async def get(url, source, listing=False):
                return INDEX if listing else body
            with self.assertRaises(ValueError):
                await collect_source(SOURCES['sources'][0], NOW, get)
        async def future(url, source, listing=False):
            return rss(stamp='Wed, 21 Oct 26 12:00:00 -0400')
        self.assertEqual(await collect_source(SOURCES['sources'][1], NOW, future), [])

    async def test_off_topic_news_and_unsafe_links_rejected(self):
        source = SOURCES['sources'][1]
        for title in ['Board Declares Dividend','Names New President','Timing of Earnings Release']:
            async def get(url, source, listing=False):
                return rss(title=title)
            self.assertEqual(await collect_source(source, NOW, get), [])
        for url in ['http://investors.coca-colacompany.com/news-events/press-releases/detail/1/test',
                    'https://127.0.0.1/news-events/press-releases/detail/1/test',
                    'https://investors.coca-colacompany.com.evil.test/news-events/press-releases/detail/1/test',
                    'https://investors.coca-colacompany.com@127.0.0.1/test',
                    'https://investors.coca-colacompany.com:8766/news-events/press-releases/detail/1/test',
                    'https://investors.coca-colacompany.com/news-events/press-releases/detail/1/test?url=http://127.0.0.1']:
            with self.assertRaises(ValueError):
                validate_url(url, source)

    async def test_manual_evidence_wins_and_customer_scope_remains(self):
        async def get(url, source, listing=False):
            return rss() if source['kind']=='rss' else INDEX if listing else BODY
        with tempfile.TemporaryDirectory() as folder:
            cache = await refresh_news(Path(folder), now=NOW, get=get)
        brand = copy.deepcopy(cache['sources'][1]['items'][0])
        brand.pop('source_id')
        brand.update(id='manual',verification='已核验正文',summary='人工正文摘要')
        rows, status = merge_news([brand], cache)
        self.assertEqual(len([r for r in rows if r['url']==brand['url']]), 1)
        self.assertEqual(next(r for r in rows if r['id']=='manual')['verification'], '已核验正文')
        data = fixture()
        data['news'] = rows
        data['news_status'] = status
        data['customers'][0]['name'] = '可口可乐合成主体A'
        data['customers'][1]['name'] = '可口可乐合成主体B'
        engine = Insights(data)
        self.assertEqual([r['code'] for r in engine.opportunities(['A'])], ['A'])
        self.assertEqual(engine.opportunities([]), [])
        self.assertEqual(len(engine.market()['official_signals']), 2)
        self.assertEqual(data['as_of'], engine.meta()['as_of'])
        self.assertEqual(engine.meta()['news_status']['as_of'], '2026-10-20')


if __name__=='__main__':
    unittest.main()
