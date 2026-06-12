"""merge_config / validate / build_platform_kwargs 单元测试。"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services.draft_merge import (
    DECLARATION_PLATFORMS,
    merge_config,
    validate_draft_for_publish,
    validate_image_draft_for_publish,
    build_platform_kwargs,
)


# ===== DECLARATION_PLATFORMS =====

def test_declaration_platforms_keys():
    """8 个平台：xiaohongshu/douyin/kuaishou/bilibili/baijiahao/tencent_video/iqiyi + youtube。"""
    assert set(DECLARATION_PLATFORMS.keys()) == {
        'xiaohongshu', 'douyin', 'kuaishou',
        'bilibili', 'baijiahao', 'tencent_video', 'iqiyi',
        'youtube',
    }


def test_declaration_platforms_youtube_has_two_fields():
    assert DECLARATION_PLATFORMS['youtube'] == ['audience', 'alteredContent']


# ===== merge_config: 3 级 vs 4 级 =====

def test_merge_text_3_level_priority():
    """title/description/tags 是 3 级：accountOv > platformOv > platformDefault，不走 common。"""
    common = {'title': 'C', 'description': 'C', 'tags': ['c']}
    pd = {'title': 'P', 'description': 'P', 'tags': ['p']}
    po = {'title': 'O', 'description': 'O', 'tags': ['o']}
    ao = {'title': 'A', 'description': 'A', 'tags': ['a']}
    m = merge_config(common, pd, po, ao)
    assert m['title'] == 'A'
    assert m['description'] == 'A'
    assert m['tags'] == ['a']


def test_merge_text_3_level_falls_to_platform_default():
    """accountOv/platformOv 都缺时，走 platformDefault。"""
    common = {'title': 'C', 'description': 'C', 'tags': ['c']}
    pd = {'title': 'P', 'description': 'P', 'tags': ['p']}
    po = {}
    ao = {}
    m = merge_config(common, pd, po, ao)
    assert m['title'] == 'P'
    assert m['description'] == 'P'
    assert m['tags'] == ['p']


def test_merge_text_does_not_fall_to_common():
    """3 级字段不会回退到 common。"""
    common = {'title': 'C'}
    pd = {}
    po = {}
    ao = {}
    m = merge_config(common, pd, po, ao)
    assert m['title'] == ''   # 兜底空字符串


def test_merge_cover_video_4_level_falls_to_common():
    """cover*/video* 4 级：accountOv > platformOv > common，跳过 platformDefault。"""
    common = {'coverLandscape': {'id': 'c'}, 'videoLandscape': {'id': 'vc'}}
    pd = {'coverLandscape': {'id': 'p'}, 'videoLandscape': {'id': 'vp'}}   # 平台默认
    po = {}
    ao = {}
    m = merge_config(common, pd, po, ao)
    # platformDefault 不参与 cover*/video* 的兜底
    assert m['coverLandscape'] == {'id': 'c'}
    assert m['videoLandscape'] == {'id': 'vc'}


def test_merge_cover_video_4_level_platform_ov_beats_common():
    common = {'coverLandscape': {'id': 'c'}}
    pd = {}
    po = {'coverLandscape': {'id': 'o'}}
    ao = {}
    m = merge_config(common, pd, po, ao)
    assert m['coverLandscape'] == {'id': 'o'}


def test_merge_boolean_uses_is_none():
    """布尔字段：False ≠ None。accountOv.isOriginal=False 应当胜出。"""
    common = {}
    pd = {'isOriginal': True}
    po = {}
    ao = {'isOriginal': False}
    m = merge_config(common, pd, po, ao)
    assert m['isOriginal'] is False


def test_merge_list_falls_through_to_first_non_empty():
    """列表字段：第一个非空列表胜出。"""
    common = {}
    pd = {'tags': ['p']}
    po = {'tags': []}     # 空列表算 falsy
    ao = {}
    m = merge_config(common, pd, po, ao)
    assert m['tags'] == ['p']


def test_merge_ai_content_platform_specific():
    """aiContent: 3 级合并（不走 common 兜底）。"""
    common = {'aiContent': 'COMMON'}
    pd = {'aiContent': 'PD'}
    po = {'aiContent': 'OV'}
    ao = {'aiContent': 'ACC'}
    m = merge_config(common, pd, po, ao)
    assert m['aiContent'] == 'ACC'


def test_merge_creation_declaration_no_common_fallback():
    """creationDeclaration: 3 级（不参考 common）。"""
    common = {'creationDeclaration': 'COMMON'}
    pd = {}
    po = {}
    ao = {}
    m = merge_config(common, pd, po, ao)
    assert m['creationDeclaration'] is None or m['creationDeclaration'] == ''
