"""Facebook 公共主页 API。

GET /api/facebook/pages?account_id=xxx
→ 用 CloakBrowser 打开 https://www.facebook.com/pages/?category=your_pages
→ 解析 DOM 中管理的公共主页名称和链接
→ 返回 JSON 列表
"""

import asyncio
import sqlite3
import threading
from pathlib import Path

from flask import Blueprint, request, jsonify

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger
from impl._browser import create_browser, create_context

logger = get_channel_logger("facebook")

facebook_bp = Blueprint("facebook", __name__, url_prefix="/api/facebook")

FACEBOOK_PAGES_URL = "https://www.facebook.com/pages/?category=your_pages"


def _get_cookie_path(cookie_file: str) -> str:
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


def _get_account_cookie_file(account_id: str) -> str | None:
    conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
    cursor = conn.cursor()
    cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return row[0]


def _run_in_thread(coro):
    """在独立线程中运行 asyncio coroutine 并返回结果。"""
    result = {}

    def _runner():
        loop = asyncio.new_event_loop()
        try:
            result["v"] = loop.run_until_complete(coro)
        finally:
            loop.close()

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join(timeout=120)
    return result.get("v")


async def _scrape_pages_async(cookie_file: str):
    """用浏览器打开 Pages 管理页，抓取所有公共主页名称和链接。"""
    cookie_path = _get_cookie_path(cookie_file)
    if not Path(cookie_path).exists():
        return {"code": 404, "msg": f"Cookie 文件不存在: {cookie_file}"}

    browser = await create_browser(headless=True)
    pages = []
    try:
        context = await create_context(browser, storage_state=cookie_path)
        page = await context.new_page()

        await page.goto(FACEBOOK_PAGES_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # 方法1：通过常见选择器抓取
        selectors = [
            'a[href*="/pages/"]',
            'div[role="article"] a[href*="/"]',
            'a[aria-label][href*="/"]',
        ]
        for sel in selectors:
            items = page.locator(sel)
            count = await items.count()
            if count > 0:
                for idx in range(min(count, 30)):
                    try:
                        item = items.nth(idx)
                        name = (await item.text_content()).strip()
                        href = await item.get_attribute("href") or ""
                        if name and len(name) > 2 and name not in {"Log In", "Sign Up", "Create", "Home", "Facebook", "Pages", "Messenger"}:
                            if not any(p["name"] == name for p in pages):
                                full_url = f"https://www.facebook.com{href}" if href.startswith("/") else href
                                pages.append({"name": name, "url": full_url, "href": href})
                    except Exception:
                        continue
                if pages:
                    break

        # 方法2：JS evaluate 兜底
        if not pages:
            try:
                result = await page.evaluate("""
                    () => {
                        const links = document.querySelectorAll("a[href]");
                        const found = [];
                        for (const a of links) {
                            const text = a.textContent.trim();
                            const href = a.getAttribute("href");
                            if (text && href && text.length > 2 && text.length < 100
                                && !found.some(f => f.name === text)) {
                                const fullUrl = href.startsWith("http") ? href : "https://www.facebook.com" + href;
                                found.push({name: text, url: fullUrl, href: href});
                            }
                        }
                        return found.slice(0, 30);
                    }
                """)
                skip_names = {"Log In", "Sign Up", "Create", "Home", "Facebook", "Pages", "Messenger", "Menu"}
                for r in (result or []):
                    if r["name"] not in skip_names:
                        pages.append(r)
            except Exception:
                pass

        logger.info(f"[Pages API] 抓取到 {len(pages)} 个主页")
        return {"code": 200, "data": pages}
    except Exception as e:
        logger.error(f"[Pages API] 抓取失败: {e}")
        return {"code": 500, "msg": str(e)}
    finally:
        try:
            await browser.close()
        except Exception:
            pass


@facebook_bp.route("/pages", methods=["GET"])
def list_pages():
    """获取账号管理的公共主页列表。

    Query params:
        account_id: 账号 id（用于取 cookie）

    Returns:
        {"code": 200, "data": [{"name": "主页名", "url": "完整URL", "href": "路径"}, ...]}
    """
    account_id = request.args.get("account_id", "")
    cookie_file = _get_account_cookie_file(account_id)
    if not cookie_file:
        return jsonify({"code": 404, "msg": "未找到该账号的 Cookie 文件"}), 404

    result = _run_in_thread(_scrape_pages_async(cookie_file))
    if result["code"] == 200:
        return jsonify(result)
    else:
        return jsonify(result), result.get("code", 500)
