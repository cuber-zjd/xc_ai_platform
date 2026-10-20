"""由统一发布脚本调用；仅接收结构化聚合快照，不接收代码或任意目标路径。"""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime
import time
from urllib.parse import urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'storage'
CONTAINER = 'docker-nginx-1'
CONF = '/etc/nginx/conf.d/default.conf'
TEMPLATE = Path('/home/xinxi/ai/code/dify/docker/nginx/conf.d/default.conf.template')
UNIT = 'ai-platform-business-insights.service'
BEGIN = '# BEGIN managed business-insights'
END = '# END managed business-insights'


def run(args, data=None):
    result = subprocess.run(args, input=data, capture_output=True)
    if result.returncode:
        # 不将配置、业务数据或凭据包含进异常。
        raise RuntimeError('部署子步骤失败：' + args[0])
    return result.stdout


def atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_bytes(content)
    temp.chmod(0o600)
    temp.replace(path)


def patch_nginx(original, block):
    text = original.decode('utf-8')
    if BEGIN in text:
        pattern = re.escape(BEGIN) + '.*?' + re.escape(END)
        if len(re.findall(pattern, text, flags=re.S)) != 1:
            raise ValueError('Nginx 托管片段不唯一')
        return re.sub(pattern, lambda _: block, text, flags=re.S).encode()
    if text.count('location /console/api {') != 1:
        raise ValueError('Nginx 原始锚点不唯一，拒绝修改')
    return text.replace('location /console/api {', block + '\n    location /console/api {', 1).encode()


def receive():
    os.umask(0o077)
    raw = sys.stdin.buffer.read(12_000_001)
    if len(raw) > 12_000_000:
        raise ValueError('输入过大')
    payload = json.loads(raw)
    snapshot, process = payload['snapshot'], payload['process']
    url = urlparse(payload['public_url'])
    bind = ipaddress.ip_address(payload['bind_host'])
    if url.scheme != 'https' or not re.fullmatch(r'[A-Za-z0-9.-]+(?::[0-9]{1,5})?',url.netloc) or url.username or url.password or url.path != '/business-insights' or url.query or url.fragment:
        raise ValueError('必须配置专用 HTTPS 子路径')
    if bind.is_loopback or bind.is_unspecified or not bind.is_private or bind.version != 4:
        raise ValueError('容器反代需要服务器内网 IPv4 地址')
    if not 1 <= len(snapshot['customers']) <= 100 or len(snapshot['deliveries']) > 100_000:
        raise ValueError('超出聚合试点范围')
    from business_insights.engine import Insights
    engine = Insights(snapshot)
    engine.meta()
    engine.events()
    codes = set(engine.customers)
    if len(codes) != len(snapshot['customers']) or any(str(r['code']) not in codes for r in snapshot['deliveries']):
        raise ValueError('客户范围不一致')
    if len(process['events']) > 100 or any(e['code'] not in codes for e in process['events']):
        raise ValueError('过程快照超出客户范围')
    key = payload['principal_sha256']
    if not re.fullmatch('[0-9a-f]{64}', key):
        raise ValueError('身份摘要无效')
    # 接口密钥仅用于获授权的试点接入，不声称已绑定真实飞书用户。
    principal = {key: {'id': 'pilot-connector', 'name': '经营助手试点接入', 'role': 'ops'}}
    DATA.mkdir(exist_ok=True, mode=0o700)
    DATA.chmod(0o700)
    backup = DATA / 'backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True, mode=0o700)
    for name, value in [('snapshot.json',snapshot),('feishu_process.json',process),('principals.json',principal)]:
        dest = DATA / name
        if dest.exists():
            atomic(backup / name, dest.read_bytes())
        atomic(dest, json.dumps(value, ensure_ascii=False).encode())
    env = {
        'INSIGHTS_DATA_DIR': str(DATA), 'INSIGHTS_PUBLIC_URL': payload['public_url'],
        'INSIGHTS_FEISHU_BASE_URL': payload['feishu_base_url'],
        'INSIGHTS_FEISHU_BASE_TOKEN': process['base_token'], 'INSIGHTS_FEISHU_TABLE': process['table_id'],
    }
    # 配置值不允许换行或引号，防止注入 systemd 环境文件。
    if any(any(c in str(v) for c in '\n\r"') for v in env.values()):
        raise ValueError('环境配置格式无效')
    atomic(DATA / 'service.env', ''.join(f'{k}="{v}"\n' for k,v in env.items()).encode())
    unit = f'''[Unit]
Description=经营助手限定场景只读接口
After=network-online.target

[Service]
WorkingDirectory={ROOT}
EnvironmentFile={DATA}/service.env
ExecStart={ROOT}/.venv/bin/uvicorn business_insights.server:app --host {bind} --port 8766 --log-level warning --no-access-log
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths={DATA}

[Install]
WantedBy=default.target
'''
    unit_path = Path.home() / '.config/systemd/user' / UNIT
    if unit_path.exists():
        atomic(backup / UNIT, unit_path.read_bytes())
    atomic(unit_path, unit.encode())
    run(['systemctl','--user','daemon-reload'])
    run(['systemctl','--user','enable',UNIT])
    run(['systemctl','--user','restart',UNIT])
    # 内网监听由容器反代使用；所有业务数据接口要求 Bearer，演示登录已关闭。
    for attempt in range(30):
        try:
            with urlopen(f'http://{bind}:8766/health', timeout=2) as response:
                if json.load(response).get('external') is True:
                    break
        except Exception:
            if attempt == 29:
                raise RuntimeError('经营助手健康检查失败') from None
            time.sleep(1)
    block = f'''{BEGIN}
    location = /business-insights {{ return 308 /business-insights/; }}
    location ^~ /business-insights/ {{
      proxy_pass http://{bind}:8766/;
      proxy_http_version 1.1;
      proxy_set_header Host {url.netloc};
      proxy_set_header Authorization $http_authorization;
      proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
      proxy_buffering off;
      proxy_read_timeout 120s;
      client_max_body_size 128k;
    }}
    {END}'''
    current = run(['docker','exec',CONTAINER,'cat',CONF])
    template = TEMPLATE.read_bytes()
    replacement = patch_nginx(current, block)
    updated_template = patch_nginx(template, block)
    atomic(backup / 'nginx-default.conf', current)
    atomic(backup / 'nginx-default.conf.template', template)
    try:
        # 现有容器拥有其挂载配置的写权限；不修改宿主机 Nginx 或其他服务。
        run(['docker','exec','-i',CONTAINER,'sh','-c','cat > '+CONF], replacement)
        TEMPLATE.write_bytes(updated_template)
        run(['docker','exec',CONTAINER,'nginx','-t'])
        run(['docker','exec',CONTAINER,'nginx','-s','reload'])
    except Exception:
        run(['docker','exec','-i',CONTAINER,'sh','-c','cat > '+CONF], current)
        TEMPLATE.write_bytes(template)
        run(['docker','exec',CONTAINER,'nginx','-t'])
        run(['docker','exec',CONTAINER,'nginx','-s','reload'])
        raise
    summary = {'ok': True, 'as_of': snapshot['as_of'], 'customers': len(codes),
               'process_events': len(process['events']), 'service': UNIT,
               'public_url': payload['public_url'], 'data_refresh': '显式发布快照，无云端业务库轮询',
               'messages_sent': 0, 'feishu_writes': 0, 'backup': str(backup)}
    atomic(DATA / 'deployment.json', json.dumps(summary,ensure_ascii=False,indent=2).encode())
    sys.stdout.write(json.dumps(summary,ensure_ascii=False)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='经营助手部署数据接收器')
    parser.add_argument('--receive', action='store_true', required=True)
    parser.parse_args()
    receive()
