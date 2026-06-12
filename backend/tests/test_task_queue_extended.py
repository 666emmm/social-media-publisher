"""PublishTask 扩展字段测试。"""
import sys
import json
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from ext_api.task_queue import PublishTask


def test_publish_task_default_new_fields():
    """新字段默认值。"""
    t = PublishTask()
    assert t.source == ''
    assert t.draft_id == 0
    assert t.account_id == 0
    assert t.payload == {}
    assert t.detail_id == ''


def test_publish_task_to_dict_includes_payload():
    """to_dict 把 payload 转 JSON 字符串。"""
    t = PublishTask(
        platform='bilibili', platform_type=5,
        source='draft', draft_id=42, account_id=3,
        payload={'title': 'T', 'files': ['/a.mp4']},
        detail_id='d-1',
    )
    d = t.to_dict()
    assert d['source'] == 'draft'
    assert d['draft_id'] == 42
    assert d['account_id'] == 3
    assert d['detail_id'] == 'd-1'
    # payload 是 JSON 字符串（DB 存储）
    assert isinstance(d['payload'], str)
    parsed = json.loads(d['payload'])
    assert parsed == {'title': 'T', 'files': ['/a.mp4']}


def test_publish_task_from_row_round_trip():
    """to_dict → from_row 往返保留所有新字段。"""
    t = PublishTask(
        platform='douyin', platform_type=3,
        source='draft', draft_id=99, account_id=5,
        payload={'title': 'X', 'ai_content': '内容由AI生成'},
        detail_id='d-2',
    )
    d = t.to_dict()
    t2 = PublishTask.from_row(d)
    assert t2.source == 'draft'
    assert t2.draft_id == 99
    assert t2.account_id == 5
    assert t2.payload == {'title': 'X', 'ai_content': '内容由AI生成'}
    assert t2.detail_id == 'd-2'