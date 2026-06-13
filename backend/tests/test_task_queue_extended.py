"""PublishTask 扩展字段测试。"""
import sys
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock

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
    """to_dict 不再序列化 payload（payload 是 in-memory，不持久化）。"""
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
    # payload 不持久化（in-memory only），不再被 JSON 编码到 to_dict
    assert d['payload'] == {'title': 'T', 'files': ['/a.mp4']}
    assert not isinstance(d['payload'], str)


def test_publish_task_from_row_round_trip():
    """to_dict → from_row 往返保留新字段（payload in-memory，不进 DB）。"""
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
    assert t2.detail_id == 'd-2'
    # payload 是 in-memory 字段，from_row 后回到默认 {}
    assert t2.payload == {}


def test_execute_splats_payload_to_platform_publish_video():
    """_execute 当 task.payload 非空时调 platform.publish_video(**payload)。"""
    from ext_api import task_queue as tq
    from ext_api.task_queue import TaskStatus

    # 构造一个最小 task
    t = PublishTask(
        platform='xiaohongshu', platform_type=1,
        payload={'title': 'T', 'files': ['/a.mp4'], 'tags': ['x'],
                 'desc': 'D', 'ai_content': '内容由AI生成'},
        account_id=1, source='draft', draft_id=42,
    )

    # Mock platform
    fake_platform = MagicMock()
    fake_platform.publish_video = MagicMock(return_value=True)

    with patch.object(tq, 'get_platform', return_value=fake_platform):
        queue = tq.get_task_queue()
        asyncio.run(queue._execute(t))

    # 验证 publish_video 被以 payload kwargs 调用
    fake_platform.publish_video.assert_called_once()
    call_kwargs = fake_platform.publish_video.call_args.kwargs
    assert call_kwargs['title'] == 'T'
    assert call_kwargs['files'] == ['/a.mp4']
    assert call_kwargs['tags'] == ['x']
    assert call_kwargs['desc'] == 'D'
    assert call_kwargs['ai_content'] == '内容由AI生成'


def test_execute_async_publish_video():
    """platform.publish_video 是 async 时也走 splat。"""
    from ext_api import task_queue as tq

    async def fake_async_publish(**kwargs):
        return True

    fake_platform = MagicMock()
    fake_platform.publish_video = fake_async_publish

    t = PublishTask(
        platform='douyin', platform_type=3,
        payload={'title': 'X', 'files': ['/a.mp4']},
    )

    with patch.object(tq, 'get_platform', return_value=fake_platform):
        queue = tq.get_task_queue()
        result = asyncio.run(queue._execute(t))

    assert result is True