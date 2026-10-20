"""统一发布入口的附属数据传输步骤；代码仍只由 Git 发布。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    for name in ['server','user','remote-path','ssh-key','data-dir','credential-file','public-url']:
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    data = Path(args.data_dir)
    credential = Path(args.credential_file)
    if credential.exists():
        config = json.loads(credential.read_text(encoding='utf-8'))
        if config['public_url'] != args.public_url:
            raise ValueError('已有凭据目标不一致')
        token = config['token']
    else:
        token = secrets.token_urlsafe(48)
        credential.parent.mkdir(parents=True,exist_ok=True)
        credential.write_text(json.dumps({'public_url': args.public_url, 'token': token,
                                         'scope': '限定客户只读试点；不是飞书用户身份'},ensure_ascii=False,indent=2),encoding='utf-8')
        if os.name == 'nt':
            # 用当前用户 SID 避免中文账号名和域账号的转义问题。
            result = subprocess.run(['whoami','/user','/fo','csv','/nh'],capture_output=True,text=True,check=True)
            import csv
            sid = next(csv.reader([result.stdout.strip()]))[1]
            subprocess.run(['icacls',str(credential),'/inheritance:r','/grant:r',f'*{sid}:(F)'],capture_output=True,check=True)
        else:
            credential.chmod(0o600)
    snapshot = json.loads((data/'snapshot.json').read_text(encoding='utf-8'))
    process = json.loads((data/'feishu_process.json').read_text(encoding='utf-8'))
    payload = {'snapshot':snapshot,'process':process,'principal_sha256':hashlib.sha256(token.encode()).hexdigest(),
               'public_url':args.public_url,'bind_host':args.server,
               'feishu_base_url': 'https://xiangchi.feishu.cn/base/'+process['base_token']}
    remote = str(Path(args.remote_path).as_posix()).replace('\\','/')+'/backend/standalone/business_insights'
    command = 'cd '+shlex.quote(remote)+' && INSIGHTS_DATA_DIR='+shlex.quote(remote+'/storage')+' .venv/bin/python deploy.py --receive'
    result = subprocess.run(['ssh','-i',args.ssh_key,'-o','BatchMode=yes','-o','ConnectTimeout=15',
                             args.user+'@'+args.server,command],input=json.dumps(payload,ensure_ascii=False).encode(),
                            capture_output=True)
    if result.returncode:
        # 部署脚本不将 SSH 数据输入或 token 输出到日志。
        sys.stderr.buffer.write(result.stderr[-3000:])
        raise RuntimeError('经营助手部署失败，保留数据和配置备份')
    sys.stdout.buffer.write(result.stdout)


if __name__ == '__main__':
    main()
