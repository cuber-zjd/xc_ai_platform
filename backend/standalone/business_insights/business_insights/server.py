"""独立运行时：只读接口与主平台依赖、身份和数据存储隔离。"""
import json
import os
from pathlib import Path
from .app import create_app
from .monitor import Monitor


def build_app():
    data = Path(os.environ['INSIGHTS_DATA_DIR'])
    principals = json.loads((data / 'principals.json').read_text(encoding='utf-8'))
    monitor=None
    if os.environ.get('INSIGHTS_REFRESH_ENABLED')=='1':
        monitor=Monitor(os.environ['INSIGHTS_COLLECTOR_PYTHON'],Path(__file__).resolve().parents[1]/'refresh_worker.py',
                        data,int(os.environ.get('INSIGHTS_REFRESH_INTERVAL','900')))
    return create_app(data / 'snapshot.json', data / 'demo.sqlite3', external=True,
                      principal_map=principals, feishu_process_path=data / 'feishu_process.json',refresh_monitor=monitor)


app = build_app()
