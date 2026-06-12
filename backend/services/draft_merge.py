"""草稿合并/校验/payload 适配模块。

所有函数独立、纯 Python，不导入任何前端代码、不依赖任何 publish-page 内部。
字段集与 PublishCenter.vue:592-637 保持同步。
"""

# 平台声明字段映射（与 PublishCenter.vue:1329-1338 一致）
DECLARATION_PLATFORMS = {
    'xiaohongshu': 'aiContent',
    'douyin': 'aiContent',
    'kuaishou': 'aiContent',
    'bilibili': 'creationDeclaration',
    'baijiahao': 'creationDeclaration',
    'tencent_video': 'creationDeclaration',
    'iqiyi': 'creationDeclaration',
    'youtube': ['audience', 'alteredContent'],
    # channels / tiktok 不在此表（不校验声明字段）
}


def _first_truthy(*values):
    """返回第一个真值；布尔用 is None 检查除外。"""
    for v in values:
        if v is not None and v != '' and v != []:
            return v
    return values[-1] if values else None


def _first_list(*values):
    """返回第一个非空 list；都是空则返回最后一个。"""
    for v in values:
        if isinstance(v, list) and len(v) > 0:
            return v
    return values[-1] if values else []


def _first_bool(*values):
    """布尔合并：用 is None 判定 None 表示"未设置"，False/True 都是有效值。"""
    for v in values:
        if v is not None:
            return v
    return False


def merge_config(common, platform_default, platform_ov, account_ov):
    """合并 4 层。3 级字段（大多数）：accountOv > platformOv > platformDefault。
    4 级字段（cover*/video*）：accountOv > platformOv > common（跳过 platformDefault）。"""
    common = common or {}
    platform_default = platform_default or {}
    platform_ov = platform_ov or {}
    account_ov = account_ov or {}

    # 4 级字段（common 兜底）
    cover_landscape = _first_truthy(account_ov.get('coverLandscape'), platform_ov.get('coverLandscape'), common.get('coverLandscape'))
    cover_portrait = _first_truthy(account_ov.get('coverPortrait'), platform_ov.get('coverPortrait'), common.get('coverPortrait'))
    video_landscape = _first_truthy(account_ov.get('videoLandscape'), platform_ov.get('videoLandscape'), common.get('videoLandscape'))
    video_portrait = _first_truthy(account_ov.get('videoPortrait'), platform_ov.get('videoPortrait'), common.get('videoPortrait'))

    # 3 级文本字段
    title = _first_truthy(account_ov.get('title'), platform_ov.get('title'), platform_default.get('title'), '')
    description = _first_truthy(account_ov.get('description'), platform_ov.get('description'), platform_default.get('description'), '')
    tags = _first_list(account_ov.get('tags'), platform_ov.get('tags'), platform_default.get('tags', []))

    # 3 级平台常见字段
    video_format = _first_truthy(account_ov.get('videoFormat'), platform_ov.get('videoFormat'), platform_default.get('videoFormat', ''), '')
    enable_timer = _first_truthy(account_ov.get('enableTimer'), platform_ov.get('enableTimer'), platform_default.get('enableTimer', 0), 0)
    schedule_time = _first_truthy(account_ov.get('scheduleTime'), platform_ov.get('scheduleTime'), platform_default.get('scheduleTime', ''), '')
    ai_content = _first_truthy(account_ov.get('aiContent'), platform_ov.get('aiContent'), platform_default.get('aiContent', ''), '')
    is_original = _first_bool(account_ov.get('isOriginal'), platform_ov.get('isOriginal'), platform_default.get('isOriginal', False))

    # 3 级平台特定字段
    platform_specific = {}
    for field in [
        'creationDeclaration', 'riskWarning', 'enableCashActivity',
        'supplementaryDeclaration', 'audience', 'alteredContent',
        'zone', 'activityId', 'hotspotId', 'hotspotData', 'selectedTag',
        'tagType', 'tagValue', 'mixId', 'mixData', 'topic', 'isDraft',
        'location', 'collection', 'groupChat',
    ]:
        platform_specific[field] = _first_truthy(
            account_ov.get(field), platform_ov.get(field), platform_default.get(field)
        )

    return {
        'title': title,
        'description': description,
        'tags': tags,
        'coverLandscape': cover_landscape,
        'coverPortrait': cover_portrait,
        'videoLandscape': video_landscape,
        'videoPortrait': video_portrait,
        'videoFormat': video_format,
        'enableTimer': enable_timer,
        'scheduleTime': schedule_time,
        'aiContent': ai_content,
        'isOriginal': is_original,
        **platform_specific,
    }


def validate_draft_for_publish(draft):
    """dry-run 校验。返回错误消息列表（空 = 合法）。"""
    raise NotImplementedError


def validate_image_draft_for_publish(draft):
    """图文草稿 dry-run 校验。返回错误消息列表。"""
    raise NotImplementedError


def build_platform_kwargs(merged, common, account):
    """merged dict → platform.publish_video kwargs dict。"""
    raise NotImplementedError
