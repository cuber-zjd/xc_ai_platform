"""飞书卡片候选：本工具只生成内容，不发送消息。"""
from urllib.parse import urlparse, quote
from html import escape


def card_for(event,base_url):
    u=urlparse(base_url)
    if u.scheme not in {'http','https'} or not u.netloc or u.username or u.password or u.query or u.fragment:
        raise ValueError('需要不含凭据、参数和片段的HTTP(S)应用地址')
    code=quote(event['code'],safe='')
    color='green' if event['tone']=='opportunity' else 'orange'
    facts=[escape(x) for x in event['facts']]
    focus={'tag':'column_set','flex_mode':'none','columns':[
        {'tag':'column','width':'weighted','weight':1,'background_style':color+'-50',
         'padding':'12px','vertical_spacing':'8px','elements':[
             {'tag':'markdown','content':'**'+facts[0]+'**'},
             *[{'tag':'markdown','content':f,'text_size':'notation'} for f in facts[1:]]]}]}
    return {'schema':'2.0','config':{'update_multi':True,'width_mode':'default','enable_forward':False},
            'header':{'template':'green' if event['tone']=='opportunity' else 'orange',
                      'subtitle':{'tag':'plain_text','content':f"数据截至 {event['as_of']} · 待人工核实"},
                      'icon':{'tag':'standard_icon','token':'notice_colorful'},
                      'title':{'tag':'plain_text','content':f"{event['title']}｜{event['customer']}"}},
            'body':{'direction':'vertical','padding':'12px','vertical_spacing':'12px','elements':[focus,
                    {'tag':'markdown','content':'**建议下一步**\n'+escape(event['action'])},
                    {'tag':'markdown','text_size':'notation','content':f"<font color='grey'>仅为待核实线索，非已确认损失或订单。规则：{event['rule_version']}</font>"},
                    {'tag':'button','text':{'tag':'plain_text','content':'查看证据并跟进'},
                     'type':'primary_filled','width':'fill','behaviors':[{'type':'open_url','default_url':f'{base_url.rstrip("/")}/?customer={code}'}]}]}}
