"""指定内网源库的连接兼容配置；临时文件不含账号密码，始终要求加密。"""
from contextlib import contextmanager
import ipaddress
import os
from pathlib import Path
import tempfile


@contextmanager
def source_connection(cfg, legacy_tls_v1=False):
    import pymssql
    host=ipaddress.ip_address(cfg['host'])
    port=int(cfg['port'])
    if not host.is_private or host.is_loopback or not 1<=port<=65535 or not isinstance(legacy_tls_v1,bool):
        raise ValueError('仅允许已配置的内网源库目标与明确兼容开关')
    with tempfile.TemporaryDirectory(prefix='business-insights-tds-') as folder:
        profile=Path(folder)/'freetds.conf'
        profile.write_text('[jianyuan-source]\n'+f'host = {host}\nport = {port}\n'+
            'tds version = 7.4\nencryption = require\nread-only intent = yes\n'+
            ('enable tls v1 = yes\n' if legacy_tls_v1 else ''),encoding='utf-8')
        profile.chmod(0o600)
        previous=os.environ.get('FREETDSCONF')
        os.environ['FREETDSCONF']=str(profile)
        conn=None
        try:
            conn=pymssql.connect(server='jianyuan-source',database=cfg['database'],user=cfg['username'],
                password=cfg['password'],charset='UTF-8',timeout=45,login_timeout=15,
                autocommit=False,tds_version='7.4',encryption='require')
            cursor=conn.cursor()
            try:
                cursor.execute('SELECT encrypt_option FROM sys.dm_exec_connections WHERE session_id=@@SPID')
                if str(cursor.fetchone()[0]).upper()!='TRUE':
                    raise ValueError('源库会话未加密，拒绝采集')
            finally:cursor.close()
            yield conn
        finally:
            if conn is not None:
                try:conn.close()
                except pymssql.InterfaceError:pass
            if previous is None:os.environ.pop('FREETDSCONF',None)
            else:os.environ['FREETDSCONF']=previous
