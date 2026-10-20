"""固定官方来源的只读更新：独立保留日期、来源状态和少量线索，不发送消息。"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
import socket
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import httpx

CONFIG = Path(__file__).with_name('news_sources.json')
MAX_BYTES = 1_000_000
ZONE = ZoneInfo('Asia/Shanghai')


class Page(HTMLParser):
    """只读取元数据、文本和链接，不运行网页脚本。"""
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.links: list[tuple[str, str]] = []
        self.parts: list[str] = []
        self.href: str | None = None
        self.link_parts: list[str] = []
        self.ignore = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = dict(attrs)
        if tag in {'script', 'style'}:
            self.ignore += 1
        if tag == 'meta':
            self.meta[(a.get('name') or a.get('property') or '').lower()] = a.get('content', '')
        if tag == 'a':
            self.href = a.get('href')
            self.link_parts = [a.get('title', '')]

    def handle_endtag(self, tag: str) -> None:
        if tag in {'script', 'style'}:
            self.ignore = max(0, self.ignore - 1)
        if tag == 'a' and self.href:
            self.links.append((self.href, ' '.join(self.link_parts)))
            self.href = None

    def handle_data(self, data: str) -> None:
        if not self.ignore:
            self.parts.append(data)
            if self.href:
                self.link_parts.append(data)

    @property
    def text(self) -> str:
        return ' '.join(' '.join(self.parts).split())


def page(text: str) -> Page:
    result = Page()
    result.feed(text)
    return result


def validate_url(url: str, source: dict, *, listing: bool = False) -> None:
    u = urlparse(url)
    if (u.scheme != 'https' or u.hostname != source['host'] or u.username or u.password
            or u.port not in {None, 443} or u.query or u.fragment):
        raise ValueError('来源地址超出固定HTTPS边界')
    if listing:
        if url != source['url']:
            raise ValueError('不是配置的来源入口')
    elif not re.fullmatch(source['article_path'], u.path):
        raise ValueError('不是允许的官方文章路径')


async def fetch(url: str, source: dict, *, listing: bool = False) -> str:
    validate_url(url, source, listing=listing)
    addresses = await asyncio.to_thread(socket.getaddrinfo, source['host'], 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
        raise ValueError('来源域名未解析到公网地址')
    # 不继承Cookie、内部鉴权头或代理；遇重定向、拒绝和限流不重试。
    async with httpx.AsyncClient(timeout=12, follow_redirects=False, trust_env=False) as client:
        async with client.stream('GET', url, headers={'User-Agent': 'JianyuanInsights/0.1 (+readonly official feed)'}) as response:
            response.raise_for_status()
            if response.is_redirect:
                raise ValueError('不跟随来源重定向')
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise ValueError('来源响应超过1MB')
            encoding = response.charset_encoding or 'utf-8'
            return bytes(data).decode(encoding, errors='strict')


def item(source: dict, url: str, published: date, title: str, now: datetime, **extra) -> dict:
    return {
        'id': 'official-' + hashlib.sha256((url + extra.get('topic', '')).encode()).hexdigest()[:16],
        'source_id': source['id'], 'source': source['name'], 'url': url,
        'title': title[:250], 'published': published.isoformat(), 'fetched_at': now.isoformat(),
        'entity_aliases': source.get('entity_aliases', []),
        'verification': '官方来源结构化日期和正文摘录；经营含义仍需核实',
        'action': '核实采购主体、配方与需求变化；品牌披露不代表该客户已形成订单。',
        **extra,
    }


async def collect_source(source: dict, now: datetime, get=fetch) -> list[dict]:
    text = await get(source['url'], source, listing=True)
    if source['kind'] == 'casde':
        links = []
        for href, title in page(text).links:
            if '中国农产品供需形势分析' in title and 'CASDE' in title:
                url = urljoin(source['url'], href)
                validate_url(url, source)
                if url not in links:
                    links.append(url)
        if not links:
            raise ValueError('未发现CASDE文章，保留旧线索')
        # 只读最新一期，月报不做历史全量抓取。
        url = sorted(links, reverse=True)[0]
        article = page(await get(url, source))
        published = date.fromisoformat(article.meta.get('pubdate', '')[:10])
        if published > now.date():
            raise ValueError('来源发布日期在未来')
        title = article.meta.get('articletitle', '')
        if '中国农产品供需形势分析' not in title:
            raise ValueError('文章身份未匹配')
        rows = []
        for topic in ['玉米', '食糖']:
            section = re.search(topic + r'\s*[：:]\s*(.*?)' + topic + r'首席分析师', article.text)
            if not section or len(section[1]) < 50:
                raise ValueError('报告正文缺少目标品种，保留旧线索')
            rows.append(item(source, url, published, title + ' · ' + topic, now,
                topic=topic, category='raw_material', summary=section[1][:480],
                summary_type='官方正文摘录，非本系统价格预测', date_evidence='页面PubDate元数据',
                action='采购与销售共同核实原料和食糖替代价差、库存及锁价；宏观报告不等于本企业成交价或客户订单。'))
        return rows
    if source['kind'] != 'rss':
        raise ValueError('不支持的来源类型')
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('拒绝XML外部实体或DTD')
    entries = ET.fromstring(text).findall('./channel/item')
    if not entries:
        raise ValueError('官方RSS为空或格式变化')
    rows = []
    for entry in entries[:30]:
        title = (entry.findtext('title') or '').strip()
        # 财报预告、人事、分红、参会等不构成产品经营机会。
        if not re.search(r'reports? .{0,80}results|new (?:plant|factory)|invests? |production|launches? ', title, re.I):
            continue
        if re.search(r'dividend|names? |elects? |timing|conference|disruption', title, re.I):
            continue
        url = (entry.findtext('link') or '').strip()
        validate_url(url, source)
        stamp = parsedate_to_datetime(entry.findtext('pubDate') or '')
        if stamp.tzinfo is None:
            raise ValueError('RSS日期缺少时区')
        published = stamp.astimezone(ZONE).date()
        if published > now.date() or (now.date() - published).days > 180:
            continue
        # RSS仅发现标题，不伪造正文或把标题声明为已核验商机。
        rows.append(item(source, url, published, title, now,
            category='brand', summary='官方RSS标题线索，尚未读取正文；请先阅读原文核实。',
            verification='官方RSS标题、链接和发布时间；未核验正文',
            summary_type='仅标题候选', date_evidence='官方RSS pubDate（转换为北京时间）'))
        if len(rows) == 5:
            break
    return rows


async def refresh_news(data: Path, *, now: datetime | None = None, get=fetch, config: dict | None = None) -> dict:
    now = now or datetime.now(ZONE)
    config = config or json.loads(CONFIG.read_text(encoding='utf-8'))
    path = Path(data) / 'official_news.json'
    previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    previous_sources = {s['id']: s for s in previous.get('sources', [])}

    async def update(source: dict) -> dict:
        old = previous_sources.get(source['id'], {})
        if old.get('next_due') and datetime.fromisoformat(old['next_due']) > now:
            return old
        state = {**old, 'id': source['id'], 'name': source['name'], 'url': source['url'], 'last_attempt': now.isoformat()}
        try:
            rows = await collect_source(source, now, get=get)
            existing = {r['id']: r for r in old.get('items', [])}
            existing.update({r['id']: r for r in rows})
            kept = [r for r in existing.values() if 0 <= (now.date() - date.fromisoformat(r['published'])).days <= 400]
            state.update(items=sorted(kept, key=lambda r: r['published'], reverse=True)[:12],
                status='success', last_success=now.isoformat(), last_error_type=None,
                next_due=(now + timedelta(hours=config['refresh_hours'])).isoformat())
        except Exception as exc:
            # 不输出外部响应、请求头或任意异常文本；保留本来源上次成功内容。
            state.update(status='failed', last_error_type=type(exc).__name__, items=old.get('items', []),
                next_due=(now + timedelta(hours=config['failure_retry_hours'])).isoformat())
        return state

    # 两个固定站点分别串行，一轮最多3次请求；不会对所有客户逐一抓取。
    states = await asyncio.gather(*(update(s) for s in config['sources']))
    cache = {'schema_version': 1, 'checked_at': now.isoformat(), 'as_of': now.date().isoformat(),
             'refresh_hours': config['refresh_hours'], 'sources': states}
    data.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.chmod(0o600)
    temp.replace(path)
    return cache


def merge_news(manual: list[dict], cache: dict) -> tuple[list[dict], dict]:
    """手工正文核验样本优先；自动候选不可覆盖更强证据。"""
    rows = [r for r in manual if not r.get('source_id')]
    urls = {r['url'].replace('://invest.', '://investors.') for r in rows}
    for source in cache.get('sources', []):
        rows.extend(r for r in source.get('items', []) if r['url'] not in urls)
    status = {k: v for k, v in cache.items() if k != 'sources'}
    status['sources'] = [{k: v for k, v in s.items() if k != 'items'} for s in cache.get('sources', [])]
    status['notice'] = '官方来源独立更新；失败保留旧内容。RSS仅标题候选，不等同正文核验或已产生订单。'
    return rows, status
