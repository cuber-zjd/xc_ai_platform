"""独立运行时：只读接口与主平台依赖、身份和数据存储隔离。"""
import json
import os
from pathlib import Path
from .app import create_app


def build_app():
    data = Path(os.environ['INSIGHTS_DATA_DIR'])
    principals = json.loads((data / 'principals.json').read_text(encoding='utf-8'))
    return create_app(data / 'snapshot.json', data / 'demo.sqlite3', external=True,
                      principal_map=principals, feishu_process_path=data / 'feishu_process.json')


app = build_app()
