"""已验证的健源固定聚合查询；仅允许 SELECT，不接受工具端 SQL。"""
from __future__ import annotations
import calendar
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo


def validate_sql(sql):
    if not re.match(r'^\s*(SELECT|WITH)\b',sql,re.I):
        return ['只允许固定只读查询']
    if ';' in sql or re.search(r'\b(insert|update|delete|merge|drop|truncate|alter|create|exec|execute|grant|revoke|backup|restore|into)\b',sql,re.I):
        return ['禁止写入、多语句或过程调用']
    return []


def month_shift(value: date, months: int) -> date:
    n = value.year * 12 + value.month - 1 + months
    y, m = divmod(n, 12)
    return date(y, m + 1, min(value.day, calendar.monthrange(y, m + 1)[1]))


def dump(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(type(value).__name__)


def collect(as_of: date, connection, approved_codes, output: Path) -> dict:
    if as_of >= datetime.now(ZoneInfo('Asia/Shanghai')).date():
        raise ValueError('只读取已结束日期')
    codes=sorted(set(str(c) for c in approved_codes))
    if len(codes)!=len(approved_codes) or not 1<=len(codes)<=100 or any(not re.fullmatch(r'[0-9]{1,20}',c) for c in codes):
        raise ValueError('客户白名单无效')
    old=json.loads(output.read_text(encoding='utf-8'))
    if as_of<date.fromisoformat(old['as_of']):
        raise ValueError('不允许刷新回退数据截止日')
    if codes!=sorted(str(c['code']) for c in old['customers']):
        raise ValueError('当前快照客户范围与固定白名单不符')
    conn=connection
    odbc=False
    provenance = []

    def query(key, sql, params=()):
        errors = validate_sql(sql)
        if errors:
            raise ValueError('; '.join(errors))
        cursor = conn.cursor()
        try:
            bound = tuple(p.strftime('%Y%m%d') if isinstance(p, date) else p for p in params)
            cursor.execute(sql.replace('%s', '?') if odbc else sql, bound)
            rows = [dict(zip([c[0] for c in cursor.description],row)) for row in cursor.fetchmany(20001)]
        finally:
            cursor.close()
        if len(rows) > 20000:
            raise RuntimeError(f'{key}超出聚合快照上限，未保存不完整结果')
        provenance.append({'id': key, 'sql': sql, 'parameters': [str(p) for p in params],
                           'rows': len(rows), 'sha256': hashlib.sha256(sql.encode()).hexdigest()})
        return rows

    try:
        duplicates = query('customer_key_check', '''SELECT customer_no,COUNT(*) n
            FROM dbo.jy_customer_base GROUP BY customer_no HAVING COUNT(*)>1''')
        if duplicates:
            raise RuntimeError('客户主数据编码重复，需要先复核关联粒度')
        end = as_of + timedelta(days=1)
        start = month_shift(as_of.replace(day=1), -24)
        fixed_marks=','.join(['%s']*len(codes))
        cohort=query('cohort', f'''SELECT CAST(customer_no AS varchar(50)) code,
          customer_name name,salesman owner,sub_market segment,customer_value_type value_type,market,dept
          FROM dbo.jy_customer_base WHERE customer_no IN ({fixed_marks}) ORDER BY customer_no''',tuple(codes))
        if sorted(str(c['code']) for c in cohort)!=codes:
            raise ValueError('客户主数据缺失或重复，保留原快照')
        marks = ','.join(['%s'] * len(codes))
        deliveries = query('daily_customer_product', f'''SELECT
          CAST(relation_customer_no AS varchar(50)) code, posting_date day,
          mara_group_no product_code,MAX(mara_group_desc) product,
          SUM(shipment_quantity) qty,SUM(net_income) revenue
          FROM dbo.jy_delivery_data_view2
          WHERE relation_customer_no IN ({marks}) AND posting_date >= %s AND posting_date < %s
          AND mara_group_desc IN (N'果葡糖浆',N'麦芽糖浆',N'差异化糖浆')
          GROUP BY relation_customer_no,posting_date,mara_group_no
          ORDER BY relation_customer_no,posting_date,mara_group_no''', (*codes, start, end))
        profit = query('monthly_customer_profit', f'''SELECT
          COALESCE(NULLIF(cb.relation_customer,''),p.customer_no) code,
          TRY_CONVERT(int,p.year_val) year,TRY_CONVERT(int,p.month_val) month,
          p.mara_group_desc product,SUM(p.quantity) qty,
          SUM(p.gross_profit)*10000 gross_profit,SUM(p.profit)*10000 profit,
          SUM(p.marginal_profit)*10000 marginal_profit
          FROM dbo.jy_sale_profit p LEFT JOIN dbo.jy_customer_base cb ON p.customer_no=cb.customer_no
          WHERE COALESCE(NULLIF(cb.relation_customer,''),p.customer_no) IN ({marks})
          AND p.mara_group_desc IN (N'果葡糖浆',N'麦芽糖浆',N'差异化糖浆')
          AND TRY_CONVERT(int,p.year_val) BETWEEN %s AND %s
          GROUP BY COALESCE(NULLIF(cb.relation_customer,''),p.customer_no),
          p.year_val,p.month_val,p.mara_group_desc
          ORDER BY code,year,month''', (*codes, start.year, as_of.year))
        profit = [r for r in profit if r['year'] and r['month'] and 1 <= r['month'] <= 12
                  and date(r['year'], r['month'], 1) < as_of.replace(day=1)]
        corn = query('corn', '''SELECT date_val day,jianyuan_price price
          FROM dbo.jy_corn_purchase_price WHERE date_val >= %s AND date_val <= %s
          AND jianyuan_price IS NOT NULL AND jianyuan_price>0 ORDER BY date_val''',
                     (as_of-timedelta(days=100), as_of))
        syrup = query('syrup', '''SELECT record_date day,province,city,enterprise,specification,price
          FROM dbo.ncp_mysteel_fsy_price_summary WHERE record_date >= %s AND record_date <= %s
          ORDER BY record_date,enterprise,specification''', (as_of-timedelta(days=35), as_of))
        freshness = query('source_freshness', '''SELECT
          (SELECT MAX(posting_date) FROM dbo.jy_delivery_data_view2 WHERE posting_date<=%s) delivery,
          (SELECT COUNT(*) FROM dbo.jy_delivery_data_view2 WHERE posting_date>%s) future_delivery_rows,
          (SELECT COUNT(*) FROM dbo.jy_corn_purchase_price WHERE date_val>%s) future_corn_rows,
          (SELECT COUNT(*) FROM dbo.jy_sale_profit WHERE TRY_CONVERT(int,year_val) IS NULL
           OR TRY_CONVERT(int,month_val) NOT BETWEEN 1 AND 12) invalid_profit_period_rows''',
                          (as_of, as_of, as_of))[0]
        news=old.get('news',[])
        news_status=old.get('news_status',{})
        news_path=output.parent/'official_news.json'
        if news_path.exists():
            try:
                from .news_feed import merge_news
                news,news_status=merge_news(news,json.loads(news_path.read_text(encoding='utf-8')))
            except (ValueError,KeyError,TypeError,OSError):
                news_status={**news_status,'cache_error':True,'notice':'资讯缓存读取失败，保留上次内容'}
        snapshot = {'schema_version': 1, 'as_of': as_of.isoformat(),
                    'collected_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                    'mode': 'live_readonly_snapshot', 'company': '健源',
                    'scope': f'发布时固定{len(codes)}家客户；近24个月；仅三类糖浆；不是全公司排名',
                    'customers': cohort, 'deliveries': deliveries, 'profits': profit,
                    'corn': corn, 'syrup': syrup, 'news': news, 'news_status':news_status,'freshness': freshness,
                    'provenance': provenance,
                    'caveats': ['销量为已入库发货记录，日历28日等长比较；不代表已核准需求或流失。',
                                '未验收源系统同步完整性；缺失利润保留为空。',
                                '利润来自按月维护表，单位由万元转换为元，未确认已结账。',
                                '客户关联主体采用源视图；利润按客户主数据关联主体汇总。',
                                '云端仅按固定客户白名单只读刷新；飞书真实身份映射仍待验收。']}
        safe = json.loads(json.dumps(snapshot, ensure_ascii=False, default=dump))
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_suffix('.tmp')
        from .engine import Insights
        Insights(safe).events()
        temp.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.chmod(0o600)
        temp.replace(output)
        return safe
    finally:
        conn.close()
