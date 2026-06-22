"""支付宝内容创作平台相关 API 代理。

仿 ``douyin_image_bp.py`` 的网络拦截模式:用 CloakBrowser 打开支付宝发布页 →
上传一个空视频文件触发表单渲染 → 在合集搜索框输入关键词 → 监听
``queryCompilationsByPublicId.json`` 响应 → 把结果转发给前端。

文档 ~/zfb.md 明确要求:合集列表是会话级的(需登录态 appId + ctoken),
必须通过浏览器自动化获取,且 UI 参考"抖音图文发布的选择音乐下拉搜索组件"。

请求体(文档实测): {"pageNum":1,"pageSize":999,"publicId":"...","searchName":"一键"}
响应结构:
    {
      "stat": "ok",
      "result": {
        "total": 1, "hasMore": false,
        "list": [
          {"compilationId":"CC...","coverUrl":"...","title":"一键分发系统",
           "category":"科技数码","total": 1}
        ]
      }
    }
"""

import asyncio
import sqlite3
from pathlib import Path

from flask import Blueprint, request, jsonify

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger
from impl._browser import create_browser, create_context

logger = get_channel_logger("alipay")

alipay_bp = Blueprint('alipay', __name__, url_prefix='/api/alipay')

# 支付宝发布页(文档 ~/zfb.md)
_ALIPAY_PUBLISH_URL = (
    "https://c.alipay.com/page/content-creation/publish/short-video"
)
# 图集(图文)发布页 — 文档 ~/ZFB-tuji.md
_ALIPAY_SHORT_CONTENT_URL = (
    "https://c.alipay.com/page/content-creation/publish/short-content"
)


def _get_cookie_path(cookie_file: str) -> str:
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


def _get_account_cookie_file(account_id: str) -> str:
    """从数据库取账号 cookie 文件名。account_id 为空时取任意一个支付宝账号。"""
    conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
    cursor = conn.cursor()
    if account_id:
        cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
    else:
        cursor.execute("SELECT filePath FROM user_info WHERE type = 12 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


# ======================================================================
# /api/alipay/compilation-search
# ======================================================================

@alipay_bp.route('/compilation-search', methods=['GET'])
def search_compilation():
    """搜索支付宝合集 —— 浏览器拦截 queryCompilationsByPublicId.json。

    Query params:
        account_id: 账号 id(用于取 cookie)
        keyword:    合集名称关键词

    Returns:
        {"code": 200, "data": {"list": [...], "total": N, "hasMore": bool}}
    """
    account_id = request.args.get('account_id')
    keyword = request.args.get('keyword', '')

    logger.info(
        f"[合集搜索] 收到请求: account_id={account_id}, keyword={keyword}"
    )

    if not keyword:
        return jsonify({"code": 400, "msg": "缺少 keyword 参数"}), 400

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            logger.warning(f"[合集搜索] 账号不存在: {account_id}")
            return jsonify({"code": 404, "msg": "没有可用的支付宝账号"}), 404

        result = run_async(_search_compilation_via_browser(cookie_file, keyword))

        if result.get("success"):
            data = result.get("data", {})
            items = data.get("list", [])
            logger.info(
                f"[合集搜索] 成功,共 {len(items)} 个合集"
            )
            return jsonify({"code": 200, "data": data})
        else:
            logger.error(f"[合集搜索] 失败: {result.get('error')}")
            return jsonify({
                "code": 500, "msg": result.get("error", "请求失败"),
            }), 500
    except Exception as e:
        logger.error(f"[合集搜索] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


async def _search_compilation_via_browser(cookie_file: str, keyword: str) -> dict:
    """用 CloakBrowser 打开发布页 + 上传空视频 + 监听合集搜索响应。

    与抖音音乐搜索同构(参考 ``douyin_image_bp._search_music_via_browser``)。

    步骤:
        1. 准备一个最小空视频(首次创建,缓存复用)
        2. 开启 response 监听,匹配 queryCompilationsByPublicId.json
        3. goto 发布页 → 等 input[type=file]
        4. 上传空视频 → 等表单渲染(标题输入框出现)
        5. 定位合集搜索框 ``input[id$='_compilationInfo']`` → fill keyword
        6. 轮询等 captured_response(最长 15s)
        7. 解析响应,提取 result.list
    """
    cookie_path = _get_cookie_path(cookie_file)

    # 1. 准备空视频(支付宝要求先上传视频才会渲染完整表单)
    empty_video = Path(BASE_DIR / ".alipay_empty_video.mp4")
    if not empty_video.exists():
        try:
            _create_minimal_mp4(empty_video)
        except Exception as e:
            logger.error(f"[合集搜索] 创建空视频失败: {e}")
            return {"success": False, "error": f"创建空视频失败: {e}"}

    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            # 2. 监听合集搜索接口
            captured_response = None

            async def handle_response(response):
                nonlocal captured_response
                if (
                    "queryCompilationsByPublicId.json" in response.url
                    and captured_response is None
                ):
                    try:
                        data = await response.json()
                        captured_response = data
                        logger.info(
                            f"[浏览器拦截] 捕获到合集搜索响应: "
                            f"stat={data.get('stat')}, "
                            f"total={data.get('result', {}).get('total')}"
                        )
                    except Exception as e:
                        logger.error(f"[浏览器拦截] 解析响应失败: {e}")

            page.on("response", handle_response)

            # 3. 打开发布页
            logger.info("[合集搜索] 打开支付宝发布页...")
            await page.goto(_ALIPAY_PUBLISH_URL, timeout=60000)
            await page.wait_for_load_state("domcontentloaded", timeout=30000)

            # 4. 上传空视频
            logger.info("[合集搜索] 上传空视频触发表单渲染...")
            file_input = page.locator("input[type='file']").first
            await file_input.wait_for(state="attached", timeout=15000)
            await file_input.set_input_files(str(empty_video))

            # 5. 等表单渲染(标题输入框出现 = 上传完成 + 表单可交互)
            logger.info("[合集搜索] 等待表单渲染...")
            title_input = page.locator(
                "input[placeholder*='好的标题']"
            ).first
            try:
                await title_input.wait_for(state="visible", timeout=120000)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"等待表单渲染超时: {e}",
                }

            # 6. 定位合集搜索框 + fill 触发请求
            logger.info(f"[合集搜索] 输入关键词: {keyword}")
            compilation_input = page.locator(
                "input[id$='_compilationInfo']"
            ).first
            try:
                await compilation_input.wait_for(
                    state="visible", timeout=10000
                )
            except Exception as e:
                return {
                    "success": False,
                    "error": f"未找到合集搜索框: {e}",
                }

            await compilation_input.click()
            await compilation_input.fill(keyword)

            # 7. 轮询等响应(最长 15s)
            for i in range(150):
                if captured_response is not None:
                    break
                await asyncio.sleep(0.1)

            if captured_response is None:
                return {"success": False, "error": "未能拦截到合集搜索结果"}

            # 解析响应:文档实测 stat=ok, result.list 是合集数组
            stat = captured_response.get("stat")
            result_obj = captured_response.get("result") or {}
            if stat != "ok":
                return {
                    "success": False,
                    "error": f"接口返回 stat={stat}",
                    "data": captured_response,
                }

            # 标准化输出(只保留前端需要的字段)
            items = []
            for raw in (result_obj.get("list") or []):
                items.append({
                    "compilationId": raw.get("compilationId", ""),
                    "title": raw.get("title", ""),
                    "coverUrl": raw.get("coverUrl", ""),
                    "category": raw.get("category", ""),
                    "total": raw.get("total", 0),
                })

            return {
                "success": True,
                "data": {
                    "list": items,
                    "total": result_obj.get("total", len(items)),
                    "hasMore": bool(result_obj.get("hasMore", False)),
                },
            }

        finally:
            await context.close()
    finally:
        await browser.close()


def _create_minimal_mp4(path: Path):
    """创建一个最小的合法 mp4 文件(支付宝要求上传视频才渲染完整表单)。

    用 fmp4 atom 拼一个最小可识别的 mp4:ftyp + moov + mdat。
    支付宝只检测文件类型 + 能否解码开头,不真正播放,所以无需真实音视频数据。
    """
    import struct

    def box(box_type: bytes, payload: bytes = b"") -> bytes:
        size = 8 + len(payload)
        return struct.pack(">I", size) + box_type + payload

    # ftyp box: file type
    ftyp = box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2avc1mp41")

    # 最小 moov(空 trak,仅占位让播放器认为是合法 mp4)
    mvhd_payload = (
        b"\x00" * 100  # version + flags + 96 字段占位
    )
    moov = box(b"moov", box(b"mvhd", mvhd_payload))

    # 空 mdat
    mdat = box(b"mdat", b"\x00" * 16)

    path.write_bytes(ftyp + moov + mdat)


# ======================================================================
# run_async helper(与 douyin_image_bp 一致)
# ======================================================================

def run_async(coro):
    """在新事件循环里跑协程(避免与 Flask 线程冲突,同 douyin_image_bp)。"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 已在 loop 里(罕见),开新线程跑
            import threading
            result = {}
            def _run():
                new_loop = asyncio.new_event_loop()
                try:
                    result["v"] = new_loop.run_until_complete(coro)
                finally:
                    new_loop.close()
            t = threading.Thread(target=_run)
            t.start()
            t.join()
            return result.get("v")
    except RuntimeError:
        pass
    return asyncio.run(coro)


# ======================================================================
# /api/alipay/music-list — 图集背景音乐列表(分页)
# 文档 ~/ZFB-tuji.md:支付宝音乐组件无搜索,只有分页展示 + 试听
# ======================================================================

@alipay_bp.route('/music-list', methods=['GET'])
def music_list():
    """获取支付宝图集背景音乐列表 —— 浏览器自动化分页获取。

    Query params:
        account_id: 账号 id(用于取 cookie)
        page_num:   页码(默认 1)

    Returns:
        {"code": 200, "data": {
            "list": [{"musicId","title","coverUrl","audioUrl","duration"}],
            "pageNum": N, "hasMore": bool
        }}

    实现策略(运行时抓包探索):
        支付宝音乐列表接口 URL 文档未给出,采用宽泛拦截 —— 打开图集页 →
        点「添加音乐」→ 拦截响应里含「音乐数组」(每项同时具备 title +
        封面 URL + 音频 URL 特征)的 JSON。首次命中后,会以 DEBUG 级别打印
        命中的 URL,便于后续收敛成精确匹配。
    """
    account_id = request.args.get('account_id')
    page_num = request.args.get('page_num', '1')

    logger.info(
        f"[音乐列表] 收到请求: account_id={account_id}, page_num={page_num}"
    )

    try:
        page_num_int = int(page_num)
    except (TypeError, ValueError):
        page_num_int = 1

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            logger.warning(f"[音乐列表] 账号不存在: {account_id}")
            return jsonify({"code": 404, "msg": "没有可用的支付宝账号"}), 404

        result = run_async(
            _fetch_music_list_via_browser(cookie_file, page_num_int)
        )

        if result.get("success"):
            data = result.get("data", {})
            items = data.get("list", [])
            logger.info(
                f"[音乐列表] 成功,第 {page_num_int} 页共 {len(items)} 首音乐"
            )
            return jsonify({"code": 200, "data": data})
        else:
            logger.error(f"[音乐列表] 失败: {result.get('error')}")
            return jsonify({
                "code": 500, "msg": result.get("error", "请求失败"),
            }), 500
    except Exception as e:
        logger.error(f"[音乐列表] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


async def _fetch_music_list_via_browser(cookie_file: str, page_num: int) -> dict:
    """用 CloakBrowser 打开图集页 + 点添加音乐 + 拦截音乐列表响应 + 翻页。

    步骤:
        1. 开启 response 监听(宽泛匹配:JSON 内含「音乐数组」特征)
        2. goto 图集页 → 等表单渲染
        3. 点「添加音乐」打开「选择音乐」modal
        4. 若 page_num > 1,点 pagination-next 翻页(每次翻页触发一次请求)
        5. 轮询等 captured_response(最长 15s)
        6. 解析响应,提取音乐数组
    """
    cookie_path = _get_cookie_path(cookie_file)

    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            # 1. 监听音乐列表接口(宽泛匹配 + 特征判定)
            captured_response = None

            def _looks_like_music_list(obj) -> bool:
                """判定一个 JSON 对象是否是音乐列表响应。

                特征:对象内含数组字段,数组首元素同时有「标题」+
                「封面 URL」+「音频/时长」三类字段中的 ≥2 类。
                支付宝音乐项 DOM 对应字段:title / img(封面) /
                audio(音频)。后端响应里可能是:
                  {list: [{title, coverUrl, audioUrl, duration}]}
                或嵌在 result/data 里。这里递归找第一个满足特征的数组。
                """
                if not isinstance(obj, dict):
                    return False

                def _score_item(item):
                    if not isinstance(item, dict):
                        return 0
                    score = 0
                    keys = {k.lower() for k in item.keys()}
                    vals = {k.lower(): v for k, v in item.items()}
                    # 标题类
                    if any('title' in k or 'name' in k for k in keys):
                        score += 1
                    # 封面图类
                    if any('cover' in k or 'img' in k for k in keys):
                        score += 1
                    # 音频/时长类
                    if any('audio' in k or 'url' in k or 'duration' in k
                           or 'time' in k for k in keys):
                        score += 1
                    # 音频文件特征(afts/file 路径)
                    for v in vals.values():
                        if isinstance(v, str) and 'afts/file' in v:
                            score += 1
                            break
                    return score

                # 递归扫描所有数组,找 score >= 2 的数组
                def _scan(node):
                    if isinstance(node, list):
                        if node and _score_item(node[0]) >= 2:
                            return node
                        for x in node:
                            r = _scan(x)
                            if r is not None:
                                return r
                    elif isinstance(node, dict):
                        for v in node.values():
                            r = _scan(v)
                            if r is not None:
                                return r
                    return None

                return _scan(obj) is not None

            def _extract_music_array(obj):
                """从响应里抽出音乐数组(同 _looks_like_music_list 的递归)。"""
                def _scan(node):
                    if isinstance(node, list):
                        if node:
                            s = 0
                            for it in node[:3]:
                                if isinstance(it, dict):
                                    keys = {k.lower() for k in it.keys()}
                                    ss = 0
                                    if any('title' in k or 'name' in k for k in keys):
                                        ss += 1
                                    if any('cover' in k or 'img' in k for k in keys):
                                        ss += 1
                                    if any('audio' in k or 'url' in k
                                           or 'duration' in k or 'time' in k
                                           for k in keys):
                                        ss += 1
                                    for v in it.values():
                                        if isinstance(v, str) and 'afts/file' in v:
                                            ss += 1
                                            break
                                    s = max(s, ss)
                            if s >= 2:
                                return node
                        for x in node:
                            r = _scan(x)
                            if r is not None:
                                return r
                    elif isinstance(node, dict):
                        for v in node.values():
                            r = _scan(v)
                            if r is not None:
                                return r
                    return None
                return _scan(obj) or []

            async def handle_response(response):
                nonlocal captured_response
                if captured_response is not None:
                    return
                # 只看 JSON 响应
                ctype = (response.headers.get("content-type") or "").lower()
                if "json" not in ctype:
                    return
                try:
                    data = await response.json()
                except Exception:
                    return
                if not _looks_like_music_list(data):
                    return
                # 命中!DEBUG 打印 URL 便于后续收敛成精确匹配
                logger.debug(
                    f"[音乐列表][命中] URL={response.url} "
                    f"top_keys={list(data.keys()) if isinstance(data, dict) else type(data)}"
                )
                captured_response = data

            page.on("response", handle_response)

            # 2. 打开图集页
            logger.info("[音乐列表] 打开支付宝图集发布页...")
            await page.goto(_ALIPAY_SHORT_CONTENT_URL, timeout=60000)
            await page.wait_for_load_state("domcontentloaded", timeout=30000)

            # 3. 等「添加音乐」按钮可见
            logger.info("[音乐列表] 等待「添加音乐」按钮...")
            try:
                add_music_btn = page.locator(
                    "button.ant-btn:has-text('添加音乐')"
                ).first
                await add_music_btn.wait_for(state="visible", timeout=15000)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"未找到「添加音乐」按钮: {e}",
                }

            # 4. 点击打开 modal
            await add_music_btn.click()
            logger.info("[音乐列表] 已点击「添加音乐」,等待 modal")
            await asyncio.sleep(1.5)

            # 等 modal 打开
            try:
                await page.locator(
                    'div.antd5-modal[aria-modal="true"]:has-text("选择音乐")'
                ).first.wait_for(state="visible", timeout=10000)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"音乐 modal 未打开: {e}",
                }

            # 5. 若 page_num > 1,翻页到目标页(每翻一页触发一次请求)
            if page_num > 1:
                for _ in range(page_num - 1):
                    captured_response = None  # 清掉旧捕获,只取当前页
                    try:
                        next_btn = page.locator(
                            "li.antd5-pagination-next:not(.antd5-pagination-disabled)"
                        ).first
                        await next_btn.wait_for(
                            state="visible", timeout=5000
                        )
                        await next_btn.click()
                        await asyncio.sleep(1.0)
                    except Exception as e:
                        logger.info(
                            f"[音乐列表] 翻到第 {page_num} 页失败(可能已到末页): {e}"
                        )
                        break

            # 6. 轮询等响应(最长 15s)
            for _ in range(150):
                if captured_response is not None:
                    break
                await asyncio.sleep(0.1)

            if captured_response is None:
                return {"success": False, "error": "未能拦截到音乐列表响应"}

            # 7. 解析响应,提取音乐数组并标准化
            music_array = _extract_music_array(captured_response)
            items = []
            for raw in music_array:
                if not isinstance(raw, dict):
                    continue
                items.append({
                    "musicId": _first_value(raw, [
                        "musicId", "music_id", "id", "audioId",
                    ]) or "",
                    "title": _first_value(raw, ["title", "name"]) or "",
                    "coverUrl": _extract_url(
                        raw, ["coverUrl", "cover", "img", "pic", "imgUrl"]
                    ),
                    "audioUrl": _extract_url(
                        raw, ["audioUrl", "audio", "url", "playUrl", "fileUrl"]
                    ),
                    "duration": _first_value(raw, ["duration", "time", "len"]) or "",
                })

            # 是否有下一页:看 pagination 的 next 是否 disabled
            has_more = False
            try:
                next_disabled = await page.locator(
                    "li.antd5-pagination-next.antd5-pagination-disabled"
                ).count()
                has_more = next_disabled == 0
            except Exception:
                pass

            return {
                "success": True,
                "data": {
                    "list": items,
                    "pageNum": page_num,
                    "hasMore": has_more,
                },
            }

        finally:
            await context.close()
    finally:
        await browser.close()


def _first_value(d: dict, keys: list):
    """从 dict 里按候选 key 顺序取第一个非空值。"""
    for k in keys:
        # 大小写不敏感查找
        for dk, dv in d.items():
            if dk.lower() == k.lower() and dv not in (None, "", []):
                return dv
    return None


def _extract_url(d: dict, keys: list) -> str:
    """从 dict 里取 URL —— 兼容字段是字符串或 {url_list:[...]} 结构。"""
    v = _first_value(d, keys)
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        # antd 风格 {url_list: ["http://..."]}
        for uk in ("url_list", "urls", "list"):
            if uk in v and isinstance(v[uk], list) and v[uk]:
                return v[uk][0]
        if "url" in v and isinstance(v["url"], str):
            return v["url"]
    if isinstance(v, list) and v:
        return v[0] if isinstance(v[0], str) else ""
    return ""
