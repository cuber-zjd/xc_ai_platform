"""业务计算不交给语言模型：每个结果带范围、期间、证据与待核实项。"""
from __future__ import annotations

import os
import hashlib
import json
import math
import re
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DEFAULT_SNAPSHOT = Path(os.environ['INSIGHTS_DATA_DIR']) / 'snapshot.json'
RULE_VERSION = 'JY-RADAR-1.0'


def num(value):
    return float(value or 0)


def ratio(current, previous):
    return (current-previous)/previous if previous > 0 else None


def iso(value):
    return date.fromisoformat(str(value)[:10])


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class Insights:
    def __init__(self, snapshot=None):
        self.s = snapshot if snapshot is not None else json.loads(DEFAULT_SNAPSHOT.read_text(encoding='utf-8'))
        self.as_of = iso(self.s['as_of'])
        self.current_start = self.as_of-timedelta(days=27)
        self.previous_start = self.current_start-timedelta(days=28)
        self.previous_end = self.current_start-timedelta(days=1)
        self.rows = defaultdict(list)
        for r in self.s['deliveries']:
            if iso(r['day']) <= self.as_of:
                self.rows[str(r['code'])].append(r)
        self.customers = {str(c['code']): c for c in self.s['customers']}

    def meta(self):
        return {k: self.s[k] for k in ['as_of','collected_at','company','mode','scope','freshness','caveats']}

    def total(self, rows, start, end, key='qty'):
        return round(sum(num(r.get(key)) for r in rows if start <= iso(r['day']) <= end), 3)

    def customer(self, code):
        c = dict(self.customers[code])
        rows = self.rows[code]
        current = self.total(rows,self.current_start,self.as_of)
        previous = self.total(rows,self.previous_start,self.previous_end)
        yoy_end = self.as_of.replace(year=self.as_of.year-1,day=min(self.as_of.day,28)) if self.as_of.month==2 else self.as_of.replace(year=self.as_of.year-1)
        yoy_start = yoy_end-timedelta(days=27)
        yoy_rows = [r for r in rows if yoy_start <= iso(r['day']) <= yoy_end]
        yoy = self.total(rows,yoy_start,yoy_end)
        positive_days = sorted({iso(r['day']) for r in rows if num(r['qty'])>0})
        recent_days = [d for d in positive_days if d >= self.as_of-timedelta(days=365)]
        gaps = [(b-a).days for a,b in zip(recent_days,recent_days[1:])]
        median_gap = statistics.median(gaps) if len(gaps)>=4 else None
        latest = positive_days[-1] if positive_days else None
        months = defaultdict(lambda: {'qty':0,'revenue':0})
        products = defaultdict(lambda: {'qty':0,'previous_qty':0,'revenue':0})
        for r in rows:
            key = r['day'][:7]
            months[key]['qty'] += num(r['qty'])
            months[key]['revenue'] += num(r.get('revenue'))
            product = r.get('product') or r.get('product_code') or '未分类'
            if self.current_start <= iso(r['day']) <= self.as_of:
                products[product]['qty'] += num(r['qty'])
                products[product]['revenue'] += num(r.get('revenue'))
            if self.previous_start <= iso(r['day']) <= self.previous_end:
                products[product]['previous_qty'] += num(r['qty'])
        profits = defaultdict(lambda: {'qty':0,'profit':0,'gross_profit':0,'marginal_profit':0})
        for r in self.s.get('profits',[]):
            period = f"{r['year']:04d}-{r['month']:02d}"
            if str(r['code'])==code and period < self.as_of.strftime('%Y-%m'):
                for k in ['qty','profit','gross_profit','marginal_profit']:
                    profits[period][k] += num(r[k])
        profit_series = []
        for period,p in sorted(profits.items()):
            profit_series.append({'period':period,**{k:round(v,2) for k,v in p.items()},
                                  'unit_profit':round(p['profit']/p['qty'],2) if p['qty']>0 else None})
        start_month = (self.as_of.replace(day=1)-timedelta(days=365)).replace(day=1)
        series = []
        d = start_month
        while d <= self.as_of:
            key = d.strftime('%Y-%m')
            series.append({'period':key,'qty':round(months[key]['qty'],3),
                           'partial':key==self.as_of.strftime('%Y-%m')})
            d = (d.replace(day=28)+timedelta(days=4)).replace(day=1)
        c.update(current_qty=current,previous_qty=previous,change=ratio(current,previous),
                 yoy_qty=yoy if yoy_rows else None,yoy_change=ratio(current,yoy) if yoy_rows else None,
                 current_revenue=self.total(rows,self.current_start,self.as_of,'revenue'),
                 latest_delivery=latest.isoformat() if latest else None,
                 days_since_delivery=(self.as_of-latest).days if latest else None,
                 median_gap=median_gap,gap_samples=len(gaps),
                 monthly=series,products=[{'name':k,**{f:round(v,3) for f,v in vals.items()}}
                                          for k,vals in products.items()],
                 profit_series=profit_series,latest_profit=profit_series[-1] if profit_series else None,
                 periods={'current':[str(self.current_start),str(self.as_of)],
                          'previous':[str(self.previous_start),str(self.previous_end)],
                          'yoy':[str(yoy_start),str(yoy_end)]},
                 evidence=['dbo.jy_delivery_data_view2：关联客户×日期×产品聚合',
                           'dbo.jy_customer_base：客户主体与原业务员',
                           'dbo.jy_sale_profit：月度人工维护利润；尚未核实结账'],
                 caveats=['无上年同期交易记录时，同比不可比，不按下降100%处理。',
                          '图中当前月尚未结束；预警使用两个完整的等长28日窗口。',
                          '发货间隔为发货节奏参考，不等同客户下单周期；节假日、季节性须核实。'])
        return c

    def events(self, allowed=None):
        out = []
        for code in self.customers:
            if allowed is not None and code not in allowed:
                continue
            c = self.customer(code)
            facts, hypotheses, kind, tone, magnitude = [], [], None, 'risk', 0
            change = c['change']
            if c['previous_qty']>=20 and change is not None and change <= -.3 and c['previous_qty']-c['current_qty']>=20:
                kind='sales_drop'
                magnitude=c['previous_qty']-c['current_qty']
                facts.append(f"近28日发货{c['current_qty']:,.1f}吨，前28日{c['previous_qty']:,.1f}吨，变化{change:+.1%}。")
                hypotheses += ['采购节奏或节假日影响','客户库存消化、需求或竞争情况变化','供货安排或数据同步问题']
            if c['median_gap'] is not None and c['days_since_delivery'] is not None and c['days_since_delivery']>max(14,c['median_gap']*1.8):
                kind=kind or 'cadence'
                facts.append(f"距最近正向发货{c['days_since_delivery']}天；近一年发货间隔中位数{c['median_gap']:g}天，样本{c['gap_samples']}个。")
                hypotheses += ['先核实发货安排与真实采购周期，尚不能判定流失']
                magnitude=max(magnitude,c['previous_qty'])
            ps=c['profit_series']
            if len(ps)>=2:
                p0,p1=ps[-2:]
                period0=iso(p0['period']+'-01')
                expected=(period0.replace(day=28)+timedelta(days=4)).replace(day=1).strftime('%Y-%m')
                if p1['period']==expected and p0['unit_profit'] is not None and p1['unit_profit'] is not None:
                    u0,u1=p0['unit_profit'],p1['unit_profit']
                    if (u0>=0 and u1<0) or (u0>0 and u0-u1>=50 and (u1-u0)/u0<=-.3):
                        kind=kind or 'profit_drop'
                        facts.append(f"月度维护利润：{p1['period']}单位利润{u1:,.1f}元/吨，前月{u0:,.1f}元/吨；尚未核实结账与产品结构影响。")
                        hypotheses += ['核实月度利润口径、产品组合及成本结转，不能由此直接判断客户压价']
            if kind is None and c['previous_qty']>=20 and change is not None and change>=.3 and c['current_qty']-c['previous_qty']>=20:
                kind='sales_growth'; tone='opportunity'; magnitude=c['current_qty']-c['previous_qty']
                facts.append(f"近28日发货{c['current_qty']:,.1f}吨，前28日{c['previous_qty']:,.1f}吨，增长{change:.1%}。")
                hypotheses=['核实是否为持续增长、新项目需求或一次性集中补货']
            if kind is None:
                continue
            if c['yoy_change'] is not None:
                facts.append(f"去年等长同期{c['yoy_qty']:,.1f}吨，同比变化{c['yoy_change']:+.1%}。")
            else:
                facts.append('去年等长同期无交易记录，同比不可比。')
            # 证据日期变化不重建同一跟进事项；保留已记录的处理状态。
            eid='JY-'+hashlib.sha256(f'{code}|{kind}|{RULE_VERSION}'.encode()).hexdigest()[:14]
            out.append({'id':eid,'code':code,'customer':c['name'],'owner':c['owner'],
                        'segment':c['segment'],'kind':kind,'tone':tone,
                        'title': ('近期回升，仍需关注同比' if c['yoy_change'] is not None and c['yoy_change']<-.3 else '采购增长值得跟进') if tone=='opportunity' else ('月度利润变化值得复核' if kind=='profit_drop' else '经营变化值得核实'),
                        'facts':facts,'hypotheses':hypotheses,
                        'action':'确认新增需求及后续交付计划，准备产品协同建议。' if tone=='opportunity'
                                 else '核对订单与交付安排，联系客户确认原因并记录下次跟进日期。',
                        'magnitude_tons':round(magnitude,3),'as_of':str(self.as_of),
                        'rule_version':RULE_VERSION,'evidence':c['evidence'] if any('月度维护利润' in f for f in facts) else c['evidence'][:2],
                        'status':'待核实','business_outcome':'尚未复核',
                        'latest_profit':c['latest_profit']})
        return sorted(out,key=lambda e:(e['tone']=='opportunity',-e['magnitude_tons'],e['code']))

    def market(self):
        corn = sorted([r for r in self.s.get('corn',[]) if iso(r['day'])<=self.as_of and num(r['price'])>0],key=lambda r:r['day'])
        latest=corn[-1] if corn else None
        baseline=[r for r in corn if iso(r['day'])<=self.as_of-timedelta(days=28)]
        base=baseline[-1] if baseline else None
        series=defaultdict(list)
        for r in self.s.get('syrup',[]):
            if iso(r['day'])>self.as_of:
                continue
            try:
                price=float(str(r['price']).replace(',','').strip())
            except (ValueError,TypeError):
                continue
            if not math.isfinite(price) or price<=0:
                continue
            series[(r['province'],r['city'],r['enterprise'],r['specification'])].append({**r,'price':price})
        quotes=[]
        for key,rows in sorted(series.items(),key=lambda x:(x[0][0]!='山东',str(x[0]))):
            rows.sort(key=lambda r:r['day'])
            last=rows[-1]; earlier=[r for r in rows if iso(r['day'])<=iso(last['day'])-timedelta(days=7)]
            if earlier:
                b=earlier[-1]
                quotes.append({'label':' / '.join(str(k or '') for k in key),
                               'current':last,'baseline':b,'delta':last['price']-b['price']})
        return {'corn':corn,'latest':latest,'baseline':base,
                'delta':round(latest['price']-base['price'],2) if latest and base else None,
                'change':ratio(latest['price'],base['price']) if latest and base else None,
                'quotes':quotes[:8],
                'sources':['dbo.jy_corn_purchase_price：健源采购价','dbo.ncp_mysteel_fsy_price_summary：同地区、企业与规格现货报价'],
                'caveats':['不将玉米与糖浆现货简单相减当作加工利润。','市场报价不等同本公司成交价。',
                           '原料冲击仅做显式参数的情景估算，未涵盖锁价、库存成本和副产品。']}

    def simulate(self, quantity, factor, delta=None):
        if not finite(quantity) or not finite(factor) or not 0<quantity<=1000000 or not 0<factor<=10:
            raise ValueError('数量须为0至100万吨以内正数，原料耗用系数须为0至10以内正数')
        m=self.market()
        delta=m['delta'] if delta is None else delta
        if not finite(delta) or abs(delta)>10000:
            raise ValueError('缺少可用价差，或输入价差超出±10000元/吨')
        return {'quantity':quantity,'factor':factor,'delta':delta,
                'estimated_cost_change':round(quantity*factor*delta,2),'unit':'元',
                'formula':'产品数量（吨）×原料耗用系数（吨/吨）×原料价差（元/吨）',
                'label':'情景测算；非已发生损益',
                'assumptions':['假定该产品数量全部按输入原料价差暴露','未考虑锁价、库存计价、副产品收益、其他成本及售价变化'],
                'corn_periods':[m['baseline']['day'],m['latest']['day']] if m['baseline'] and m['latest'] else None}

    def opportunities(self, allowed=None):
        results=[]
        for n in self.s.get('news',[]):
            published=iso(n['published'])
            if published>self.as_of:
                continue
            for code,c in self.customers.items():
                if allowed is not None and code not in allowed:
                    continue
                aliases=n.get('entity_aliases',[])
                match=next((a for a in aliases if a and a in (c.get('name') or '')),None)
                if match:
                    results.append({'id':n['id']+'-'+code,'news':n,'code':code,'customer':c['name'],
                                    'owner':c['owner'],'matched_alias':match,'match_type':'品牌关键词匹配，法律主体待核实',
                                    'age_days':(self.as_of-published).days,
                                    'fresh':(self.as_of-published).days<=90,
                                    'action':n['action'],'claim':'待核实机会；未证明配方适用、采购需求或订单。'})
        return results

    def ask(self, question, allowed=None, customer_code=None):
        question=question.strip()
        supported=['今天优先跟进谁？','有哪些增长机会？','查看客户经营情况','玉米行情有什么变化？','生成客户拜访准备','本次数据口径是什么？']
        base={'question':question,'as_of':str(self.as_of),'mode':'受控场景工具；未调用语言模型',
              'supported_questions':supported,'scope':self.s['scope']}
        codes=list(self.customers) if allowed is None else [c for c in self.customers if c in allowed]
        if any(k in question for k in ['口径','数据来源','截止','更新']):
            return {**base,'tool':'data_quality','answer':f"发货分析截至{self.as_of}，对比两个完整28日窗口。利润单列月份，来自人工维护表，尚未核实结账。",'data':self.meta()}
        if any(k in question for k in ['玉米','行情','原料','价格']):
            m=self.market()
            answer='暂无可比较玉米价格。'
            if m['latest'] and m['baseline']:
                answer=f"健源玉米采购价{m['latest']['day']}为{m['latest']['price']:,.0f}元/吨；对比{m['baseline']['day']}变化{m['delta']:+,.0f}元/吨。不能据此直接推算产品实际利润。"
            return {**base,'tool':'market_brief','answer':answer,'data':m}
        if any(k in question for k in ['资讯','新闻','市场机会']):
            opp=self.opportunities(codes)
            return {**base,'tool':'market_opportunities','answer':f'找到{len(opp)}条有来源的品牌关联线索；请核实主体、时效与配方相关性。','data':opp}
        if customer_code:
            if customer_code not in codes:
                raise PermissionError('无权查询该客户')
            matches=[customer_code]
        else:
            matches=[code for code in codes if re.search(r'(?<![A-Za-z0-9])'+re.escape(code)+r'(?![A-Za-z0-9])',question) or (self.customers[code]['name'] and self.customers[code]['name'] in question)]
            if not matches:
                matches=[code for code in codes if any(a in question and a in (self.customers[code]['name'] or '')
                         for a in ['伊利','可口可乐','海天','世荣','阳春','旺旺','统一','亨氏','阿水','花仙尼'])]
        if len(matches)>1:
            return {**base,'tool':'clarify_customer','answer':'匹配多个客户，请选择具体主体。',
                    'data':[{'code':c,'name':self.customers[c]['name']} for c in matches]}
        if len(matches)==1:
            c=self.customer(matches[0]); p=c['latest_profit']
            answer=f"{c['name']}近28日发货{c['current_qty']:,.1f}吨，前28日{c['previous_qty']:,.1f}吨。"
            if p:
                answer+=f"最近可用利润为{p['period']}，{p['profit']:,.0f}元（维护数据，未核实结账）。"
            else:
                answer+='当前没有该客户可用月度利润，不能推算实时利润。'
            if any(k in question for k in ['为什么','原因']):
                answer+='已知数据只能解释变化落在哪些产品，采购意愿及竞争原因需要业务核实。'
            if any(k in question for k in ['拜访','联系','准备']):
                answer+='建议先核实下一次采购时间、现有库存和供货安排，再讨论价格政策；不自动向客户发送内容。'
            return {**base,'tool':'customer_brief','answer':answer,'data':c}
        if any(k in question for k in ['跟进','异常','关注','风险','增长','机会']):
            es=self.events(codes)
            if any(k in question for k in ['增长','机会']):
                es=[e for e in es if e['tone']=='opportunity']
            es=es[:5]
            return {**base,'tool':'customer_radar','answer':('建议先看：'+'；'.join(f"{e['customer']}（{e['title']}）" for e in es)) if es else '当前选定范围没有达到规则阈值的事件。','data':es}
        return {**base,'tool':'unsupported','answer':'当前仅支持客户经营、异常跟进、增长机会、行情、资讯和口径查询。可直接使用下面的示例问题；不生成任意SQL。','data':None}
