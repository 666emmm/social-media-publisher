"""Facebook platform implementation — CloakBrowser.

All browser operations go through ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` which delegate to CloakBrowser.
"""

import asyncio
import json
import threading
import time
from pathlib import Path
from queue import Queue

from conf import BASE_DIR
from util._logger import bind_account_name, get_channel_logger

from .._browser import create_browser_sync, create_context_sync
from .._utils import (
    get_account_name_by_cookie_file,
    save_login_result,
    scrape_user_profile,
)
from ..base_platform import BasePlatform

logger = get_channel_logger("facebook")

FACEBOOK_HOME_URL = "https://www.facebook.com/"
FACEBOOK_REELS_URL = "https://www.facebook.com/reels/create/?surface=ADDL_PROFILE_PLUS"
FACEBOOK_LOGIN_URL = "https://www.facebook.com/login"


class FacebookPlatform(BasePlatform):
    platform_id = 16
    platform_key = "facebook"
    platform_name = "Facebook"

    supports_cookie_import = True
    platform_cookie_domain = ".facebook.com"

    def _parse_cookie_to_storage_state(self, cookie_str):
        """Parse 'k=v; k=v' to Playwright storage_state (cookies, origins)."""
        cookies = []
        for item in cookie_str.split(";"):
            item = item.strip()
            if not item or "=" not in item:
                continue
            key, _, value = item.partition("=")
            key, value = key.strip(), value.strip()
            if not key:
                continue
            cookies.append({
                "name": key,
                "value": value,
                "domain": self.platform_cookie_domain,
                "path": "/",
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            })
        return {"cookies": cookies, "origins": []}

    # ------------------------------------------------------------------
    # Synchronous wrappers (called from worker threads)
    # ------------------------------------------------------------------

    async def login(self, id_str: str, status_queue: Queue, account_id: int | None = None) -> None:
        """Login via browser -- open Facebook login page, wait for user.

        使用 framenavigated 事件监听 URL 变化，只有跳转到 Facebook 首页
        （非登录/验证页面）才判定为登录成功。不设超时，等待用户完成所有验证步骤。
        """
        logger.info(f"[登录] 开始 Facebook 登录流程, id_str={id_str}")
        status_queue.put(json.dumps({"status": "status", "msg": "正在启动浏览器..."}))

        browser = await self.create_browser(headless=False, login_mode=True, humanize=False)
        try:
            context = await self.create_context(browser)
            page = await context.new_page()

            status_queue.put(json.dumps({"status": "status", "msg": "正在打开 Facebook 登录页面..."}))
            await page.goto(FACEBOOK_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            status_queue.put(json.dumps({"status": "status", "msg": "请在弹出的浏览器中登录 Facebook（包括二步验证等）"}))
            status_queue.put(json.dumps({"status": "login_url", "url": FACEBOOK_LOGIN_URL}))

            # 使用事件驱动方式等待登录，比轮询更可靠
            login_done = asyncio.Event()

            # 判断是否真正登录到 Facebook 首页
            def _is_logged_in(url: str) -> bool:
                url_lower = url.lower()
                if "facebook.com" not in url_lower:
                    return False
                for keyword in ("login", "two_step", "two_factor", "checkpoint",
                                "authentication", "verify", "recover", "identify",
                                "confirm", "challenge", "reset", "password"):
                    if keyword in url_lower:
                        return False
                return True

            async def _on_navigation(frame):
                if frame == page.main_frame and _is_logged_in(page.url):
                    # URL 通过了，但要等 3 秒再检查页面内容
                    # 防止 Facebook 在首页弹出 2FA/扫码弹窗
                    await asyncio.sleep(3)
                    if await _page_has_auth_overlay(page):
                        logger.info(f"[登录] URL 通过但检测到验证弹窗，继续等待: {page.url}")
                        return  # 有验证弹窗，不触发完成
                    logger.info(f"[登录] 检测到登录完成: {page.url}")
                    login_done.set()

            async def _page_has_auth_overlay(page_obj) -> bool:
                """检查页面上是否有 2FA / 验证 / 扫码相关的弹窗。"""
                auth_keywords = [
                    "two-factor authentication",
                    "two factor authentication",
                    "two-step verification",
                    "approve the login",
                    "enter login code",
                    "enter confirmation code",
                    "check your phone",
                    "verify your identity",
                    "scan qr code",
                    "scan the qr code",
                    "open your authenticator app",
                    "authentication app",
                    "login alert",
                    "was this you",
                    "choose a way to confirm",
                    "get a code",
                    "recover your account",
                    "confirm your identity",
                    "checkpoint",
                    "save your browser",
                    "remember this browser",
                ]
                try:
                    body_text = (await page_obj.locator("body").text_content()).lower()
                    for kw in auth_keywords:
                        if kw in body_text:
                            logger.info(f"[登录] 页面包含验证关键词: {kw}")
                            return True
                except Exception:
                    pass
                return False

            page.on("framenavigated", _on_navigation)

            if _is_logged_in(page.url):
                if not await _page_has_auth_overlay(page):
                    login_done.set()

            waited = 0
            while not login_done.is_set():
                await asyncio.sleep(1)
                waited += 1
                if waited % 5 == 0:
                    # 每 5 秒主动检查一次（framenavigated 可能不触发）
                    try:
                        if _is_logged_in(page.url) and not await _page_has_auth_overlay(page):
                            logger.info(f"[登录] 主动检测到登录完成: {page.url}")
                            login_done.set()
                    except Exception:
                        pass
                if waited % 15 == 0:
                    status_queue.put(json.dumps({"status": "status", "msg": f"等待登录完成... ({waited}s)"}))

            status_queue.put(json.dumps({"status": "status", "msg": "登录成功，正在保存 Cookie 和用户信息..."}))
            await asyncio.sleep(2)

            await save_login_result(
                context, page,
                platform_id=self.platform_id,
                platform_name=self.platform_name,
                status_queue=status_queue,
                scrape_fn=scrape_user_profile,
                account_id=account_id,
            )
            logger.info(f"[登录] Facebook 登录完成")

            # 公共主页在发布时按需获取（通过 API / Facebook 页面选择器），登录阶段不再抓取
        finally:
            try:
                await browser.close()
            except Exception:
                pass

    async def _scrape_pages(self, page):
        """Scrape managed Facebook Pages from the Pages management page.

        抓取后同时保存到 cookie 文件名对应的 _pages.json 文件，
        供发布时读取并切换身份。
        """
        pages = []
        try:
            await page.goto("https://www.facebook.com/pages/?category=your_pages", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(5)

            selectors = [
                'a[href*="/pages/"]',
                'div[role="article"] a[href*="/"]',
                'a[aria-label][href*="/"]',
            ]
            for sel in selectors:
                items = page.locator(sel)
                count = await items.count()
                if count > 0:
                    for idx in range(min(count, 20)):
                        try:
                            item = items.nth(idx)
                            name = (await item.text_content()).strip()
                            href = await item.get_attribute("href") or ""
                            if name and len(name) > 2 and name not in ["Log In", "Sign Up", "Create", "Home"]:
                                if not any(p["name"] == name for p in pages):
                                    pages.append({"name": name, "url": href})
                        except Exception:
                            continue
                    if pages:
                        break

            if not pages:
                try:
                    result = await page.evaluate("""
                        () => {
                            const links = document.querySelectorAll("a[href]");
                            const found = [];
                            for (const a of links) {
                                const text = a.textContent.trim();
                                const href = a.getAttribute("href");
                                if (text && href && href.includes("/") && text.length > 2
                                    && !found.some(f => f.name === text)) {
                                    found.push({name: text, url: href});
                                }
                            }
                            return found.slice(0, 20);
                        }
                    """)
                    for r in (result or []):
                        if r["name"] not in ["Log In", "Sign Up", "Create", "Home", "Facebook"]:
                            pages.append(r)
                except Exception:
                    pass

            logger.info(f"[主页] 抓取到 {len(pages)} 个主页: {[p['name'] for p in pages]}")

            # 保存到 _pages.json 文件
            if pages:
                # 从 page.url 或其他上下文获取当前使用的 cookie 文件名
                # 用 BASE_DIR/cookiesFile 下最近写入的文件
                cookies_dir = Path(BASE_DIR) / "cookiesFile"
                if cookies_dir.exists():
                    json_files = sorted(
                        cookies_dir.glob("facebook_*.json"),
                        key=lambda f: f.stat().st_mtime,
                        reverse=True,
                    )
                    for jf in json_files:
                        # 跳过 _pages.json 自身
                        if "_pages" in jf.stem:
                            continue
                        pages_file = cookies_dir / f"{jf.stem}_pages.json"
                        with open(pages_file, "w", encoding="utf-8") as pf:
                            json.dump(pages, pf, ensure_ascii=False)
                        logger.info(f"[主页] 已保存 {len(pages)} 个主页到: {pages_file}")
                        break
        except Exception as e:
            logger.warning(f"[主页] 抓取失败: {e}")
        return pages


    async def _switch_to_page(self, page, page_url: str, page_name: str = ""):
        """Navigate to a Facebook Page and click 'Switch' to post as that page.

        用户在前端选择了公共主页后，后端导航到该主页 URL，
        点击页面上的「切换」按钮，使后续操作都以该 Page 身份进行。
        """
        if not page_url:
            logger.info("[切换主页] 无 page_url，使用个人身份")
            return False

        logger.info(f"[切换主页] 导航到: {page_url}")
        await page.goto(page_url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(3)

        # 尝试点击 Switch / 切换 按钮
        try:
            # Facebook Page 页面上的切换按钮有多种形态
            switch_selectors = [
                'div[role="button"]:has-text("Switch")',
                'div[role="button"]:has-text("切换")',
                'span:has-text("Switch")',
                'span:has-text("切换")',
                '[aria-label*="Switch" i]',
                '[aria-label*="切换"]',
            ]
            for sel in switch_selectors:
                btn = page.locator(sel).first
                if await btn.count() > 0:
                    try:
                        await btn.click(timeout=5000)
                        await asyncio.sleep(3)
                        logger.info(f"[切换主页] 已点击切换按钮 (selector: {sel})")
                        return True
                    except Exception:
                        continue

            logger.info("[切换主页] 未找到切换按钮（可能已自动以 Page 身份登录）")
        except Exception as e:
            logger.warning(f"[切换主页] 切换异常: {e}")

        return False

    async def check_cookie(self, cookie_file: str) -> bool:
        """Verify that the stored cookie is still valid."""

        cookie_path = Path(BASE_DIR) / "cookiesFile" / cookie_file
        if not cookie_path.exists():
            return False
        try:
            browser = await self.create_browser(headless=True, humanize=False)
            try:
                context = await self.create_context(browser, storage_state=str(cookie_path))
                page = await context.new_page()
                await page.goto(FACEBOOK_HOME_URL, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                current_url = page.url
                return "facebook.com" in current_url and "login" not in current_url.lower()
            finally:
                await browser.close()
        except Exception as e:
            logger.warning(f"[Cookie检查] 失败: {e}")
            return False

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open Facebook in a visible browser for manual operations."""

        cookie_path = Path(BASE_DIR) / "cookiesFile" / cookie_file
        browser = await self.create_browser(headless=False, humanize=False)
        context = await self.create_context(browser, storage_state=str(cookie_path))
        page = await context.new_page()
        await page.goto(FACEBOOK_HOME_URL, wait_until="domcontentloaded", timeout=15000)
        logger.info(f"[创作者中心] Facebook 已打开")

    async def sync_profile(self, cookie_file: str) -> dict:
        """Sync account profile info."""

        cookie_path = Path(BASE_DIR) / "cookiesFile" / cookie_file
        try:
            browser = await self.create_browser(headless=True, humanize=False)
            try:
                context = await self.create_context(browser, storage_state=str(cookie_path))
                page = await context.new_page()
                await page.goto(FACEBOOK_HOME_URL, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(3)

                nickname = ""
                avatar_url = ""
                try:
                    name_el = page.locator('[aria-label*="profile"], [role="heading"]').first
                    if await name_el.count() > 0:
                        nickname = (await name_el.text_content()).strip()[:30]
                except Exception:
                    pass

                try:
                    avatar_el = page.locator('image[preserveAspectRatio*="slice"], svg image').first
                    if await avatar_el.count() > 0:
                        avatar_url = await avatar_el.get_attribute("xlink:href") or ""
                except Exception:
                    pass

                return {"nickname": nickname, "avatar_url": avatar_url}
            finally:
                await browser.close()
        except Exception as e:
            logger.error(f"[同步信息] 失败: {e}")
            return {"nickname": "", "avatar_url": ""}

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    async def publish_video(self, **kwargs) -> None:
        """Publish a video/reel to Facebook.

        正确流程：
        1. 打开 Reels 创建页 → 出现上传弹窗
        2. 点击上传触发按钮 → set_input_files 上传视频
        3. 等待上传完成 → 点「下一页」→ 点「下一页」（进入设置页）
        4. 填写描述（标题+内容+标签同一输入框）
        5. [可选] 分享到小组
        6. [可选] 设定时发布时间
        7. 点击发布
        """
        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", []) or []
        desc = kwargs.get("desc", "") or ""
        account_file = kwargs.get("account_file", [])
        schedule_time_str = kwargs.get("schedule_time_str", "")

        # 构建完整文本（标题+内容+标签在同一输入框）
        text_parts = []
        if title:
            text_parts.append(title)
        if desc and desc != title:
            text_parts.append(desc)
        tag_text = " ".join(f"#{t.strip().replace(' ', '')}" for t in tags if t)
        if tag_text:
            text_parts.append(tag_text)
        full_text = "\n\n".join(text_parts) if len(text_parts) > 1 else (text_parts[0] if text_parts else "")

        logger.info("=" * 60)
        logger.info(f"[发布] 开始 Facebook 发布流程")
        logger.info(f"[发布参数] text={full_text[:80]}... files={len(files)} schedule={schedule_time_str}")

        for cookie_name in account_file:
            logger.info(f"[发布] 使用账号 cookie: {cookie_name}")
            nick = get_account_name_by_cookie_file(cookie_name) or cookie_name
            bind_account_name(nick)

            cookie_path = Path(BASE_DIR) / "cookiesFile" / cookie_name
            if not cookie_path.exists():
                logger.error(f"[发布] cookie 文件不存在: {cookie_path}")
                continue

            browser = await self.create_browser(
                headless=False,
                humanize=True,
                human_preset="careful",
            )
            try:
                context = await self.create_context(
                    browser,
                    storage_state=str(cookie_path),
                )
                page = await context.new_page()

                # ── 步骤 0：切换到公共主页（如有）──
                page_name_param = kwargs.get("page_name", "")
                if page_name_param:
                    logger.info(f"[发布] 切换到公共主页: {page_name_param}")
                    await self._switch_to_page(page, page_name_param, page_name_param)

                # ── 步骤 1：打开 Reels 创建页 ──
                logger.info(f"[发布] 打开 Facebook Reels 创作页面: {FACEBOOK_REELS_URL}")
                await page.goto(FACEBOOK_REELS_URL, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(5)

                # ── 步骤 2：上传视频 ──
                if files:
                    await self._upload_media(page, files)

                # ── 步骤 3：两次「下一页」进入设置页 ──
                await self._click_next(page, step="first")
                await asyncio.sleep(3)
                await self._click_next(page, step="second")
                await asyncio.sleep(3)

                # ── 步骤 4：填写描述 ──
                if full_text:
                    await self._fill_text(page, full_text)

                # ── 步骤 5：[可选] 设定时发布 ──
                if schedule_time_str:
                    await self._set_schedule(page, schedule_time_str)

                # ── 步骤 6：点击发布 ──
                await self._click_publish(page)
                logger.info(f"[发布] Facebook 发布成功！({nick})")
            except Exception as e:
                logger.error(f"[发布] Facebook 发布失败 ({nick}): {e}")
                raise
            finally:
                try:
                    await browser.close()
                except Exception:
                    pass

    async def _upload_media(self, page, files: list):
        """上传视频到 Facebook Reels。

        步骤：
        1. 页面打开后出现上传弹窗，点击「添加视频」/「上传」按钮触发文件选择器
        2. 使用 set_input_files 上传
        3. 等待进度条消失 = 上传完成
        """
        logger.info(f"[上传] 准备上传 {len(files)} 个媒体文件")

        # 步骤 1：点击上传触发按钮
        upload_triggers = [
            'div[role="button"]:has-text("添加视频")',
            'div[role="button"]:has-text("上传")',
            'div[role="button"]:has-text("Add video")',
            'div[role="button"]:has-text("Upload")',
            'span:has-text("添加视频或拖放")',
            'span:has-text("Drag or drop")',
            'button:has-text("Upload")',
        ]
        clicked = False
        for sel in upload_triggers:
            btn = page.locator(sel).first
            if await btn.count() > 0:
                try:
                    await btn.click(timeout=5000)
                    await asyncio.sleep(2)
                    clicked = True
                    logger.info(f"[上传] 已点击上传触发按钮: {sel}")
                    break
                except Exception:
                    continue

        if not clicked:
            logger.info("[上传] 未找到上传触发按钮，尝试直接用 file input")

        # 步骤 2：通过 file input 上传
        for idx, file_path in enumerate(files):
            file_path = Path(file_path)
            if not file_path.exists():
                logger.warning(f"[上传] 文件不存在，跳过: {file_path}")
                continue

            logger.info(f"[上传] 上传第 {idx+1} 个文件: {file_path.name}")
            try:
                file_input = page.locator('input[type="file"]').first
                await file_input.set_input_files(str(file_path))
                await asyncio.sleep(5)

                # 步骤 3：等待上传进度条完成
                try:
                    await page.wait_for_selector(
                        'div[role="progressbar"]',
                        state="hidden",
                        timeout=180000,
                    )
                except Exception:
                    await asyncio.sleep(15)
                logger.info(f"[上传] 文件 {idx+1} 上传完成")
            except Exception as e:
                logger.error(f"[上传] 文件 {idx+1} 上传失败: {e}")
                raise

    async def _click_next(self, page, step: str = ""):
        """点击「下一页」按钮，从上传步骤进入设置页。

        Facebook Reels 创建流程中需要点两次 Next：
        第一次：上传完成 → 编辑裁剪页
        第二次：编辑裁剪页 → 设置页（描述/小组/定时）
        """
        logger.info(f"[下一步] 点击「下一页」({step})")

        next_selectors = [
            'div[role="button"]:has-text("下一页")',
            'div[role="button"]:has-text("继续")',
            'div[role="button"]:has-text("Next")',
            'button:has-text("下一页")',
            'button:has-text("继续")',
            'button:has-text("Next")',
            '[aria-label="下一页"]',
            '[aria-label="Next"]',
            '[aria-label="继续"]',
            '[aria-label="Continue"]',
        ]

        for sel in next_selectors:
            btn = page.locator(sel).first
            if await btn.count() > 0:
                try:
                    await btn.wait_for(state="visible", timeout=10000)
                    await btn.click(timeout=5000)
                    await asyncio.sleep(5)
                    logger.info(f"[下一步] 已点击 ({step}): {sel}")
                    return True
                except Exception as e:
                    logger.warning(f"[下一步] 点击失败 ({sel}): {e}")
                    continue

        logger.warning(f"[下一步] 未找到「下一页」按钮 ({step})，尝试继续...")
        return False

    async def _set_schedule(self, page, schedule_time_str: str):
        """设定时发布时间，或确保选中「立即发布」。

        - 有 schedule_time_str → 点击时间预设 → 填入日期时间 → 确认
        - 无 schedule_time_str → 检查是否已选「立即发布」，否则点击选择
        """

        logger.info(f"[定时] 设定发布时间: {schedule_time_str}")

        # 如果是空或已选择"立即发布"的意图，确认当前是"立即发布"
        if not schedule_time_str or schedule_time_str.strip() == "":
            try:
                body_text = await page.locator("body").text_content() or ""
                if "立即发布" in body_text:
                    logger.info("[定时] 已选择「立即发布」，无需调整")
                    # 但仍需确保没有错误选中了定时时间
                    if "今天" in body_text and ":" in body_text:
                        # 可能选中了定时，点回立即发布
                        await page.locator('text=时间预设选项').first.click(timeout=5000)
                        await asyncio.sleep(2)
                        await page.locator('text=立即发布').first.click(timeout=5000)
                        await asyncio.sleep(2)
                        logger.info("[定时] 已切换回「立即发布」")
                return
            except Exception:
                pass
            return

        # 点击「时间预设选项」触发按钮
        schedule_triggers = [
            'div[role="button"]:has-text("时间预设选项")',
            'span:has-text("时间预设选项")',
            'div[role="button"]:has-text("Schedule")',
            'span:has-text("Schedule")',
            'div[role="button"]:has-text("定时")',
        ]
        for sel in schedule_triggers:
            btn = page.locator(sel).first
            if await btn.count() > 0:
                try:
                    await btn.click(timeout=5000)
                    await asyncio.sleep(3)
                    logger.info(f"[定时] 已打开定时面板")
                    break
                except Exception:
                    continue

        # 尝试解析时间并填入日期/时间输入框
        try:
            from datetime import datetime
            dt = datetime.strptime(schedule_time_str, "%Y-%m-%d %H:%M:%S")
            date_str = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M")

            # 日期输入
            date_inputs = page.locator('input[type="date"], input[aria-label*="date" i], input[placeholder*="date" i]').first
            if await date_inputs.count() > 0:
                await date_inputs.fill(date_str)
                await asyncio.sleep(1)
                logger.info(f"[定时] 已填入日期: {date_str}")

            # 时间输入
            time_inputs = page.locator('input[type="time"], input[aria-label*="time" i], input[placeholder*="time" i]').first
            if await time_inputs.count() > 0:
                await time_inputs.fill(time_str)
                await asyncio.sleep(1)
                logger.info(f"[定时] 已填入时间: {time_str}")

            # 确认按钮
            confirm_selectors = [
                'div[role="button"]:has-text("确认")',
                'div[role="button"]:has-text("OK")',
                'div[role="button"]:has-text("Done")',
                'div[role="button"]:has-text("保存")',
            ]
            for sel in confirm_selectors:
                btn = page.locator(sel).first
                if await btn.count() > 0:
                    await btn.click(timeout=5000)
                    await asyncio.sleep(2)
                    logger.info(f"[定时] 已确认定时设置")
                    break
        except Exception as e:
            logger.warning(f"[定时] 设置失败: {e}")

    async def _fill_text(self, page, text: str):
        """Fill the description text into Facebook Reels editor."""
        logger.info(f"[填写] 写入文本 ({len(text)} 字符)")

        try:
            # Facebook uses a contenteditable div for text input
            text_area = page.locator('[contenteditable="true"], [aria-label*="description" i], [aria-label*="Describe" i]').first
            if await text_area.count() == 0:
                text_area = page.locator('[role="textbox"]').first

            await text_area.click()
            await asyncio.sleep(0.5)

            # Use JS to set text directly
            try:
                await text_area.evaluate("""
                    (el, text) => {
                        el.focus();
                        if (el.isContentEditable || el.contentEditable === 'true') {
                            el.innerText = text;
                        } else {
                            el.value = text;
                        }
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value'
                        )?.set || Object.getOwnPropertyDescriptor(
                            window.HTMLTextAreaElement.prototype, 'value'
                        )?.set;
                        if (nativeInputValueSetter) {
                            nativeInputValueSetter.call(el, text);
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                    }
                """, text)
                await asyncio.sleep(1)
                logger.info(f"[填写] 文本写入完成 (evaluate)")
                return
            except Exception as e:
                logger.warning(f"[填写] evaluate 失败，回退 fill: {e}")

            # Fallback: fill
            await text_area.fill(text)
            await asyncio.sleep(1)
            logger.info(f"[填写] 文本写入完成 (fill)")
        except Exception as e:
            logger.error(f"[填写] 文本写入失败: {e}")
            raise

        # 验证描述是否真的填入了（取前20字符检查）
        try:
            await asyncio.sleep(1)
            body_text = (await page.locator("body").text_content()) or ""
            check_keyword = text[:20].strip()
            if check_keyword and check_keyword in body_text:
                logger.info(f"[填写] 验证通过：描述已正确填入")
            else:
                logger.warning(f"[填写] 验证失败：未在页面找到描述文本，可能未填入")
        except Exception as e:
            logger.warning(f"[填写] 验证异常: {e}")

    async def _click_publish(self, page):
        """点击 Facebook 发布按钮（在设置页最后一步）。

        按优先级尝试：Share → Publish → Post → 发布
        """
        logger.info("[发布] 点击发布按钮")

        # ⚠️ 取最后一个包含「发布」的 div[role="button"]，避免误触「时间预设选项」
        # 参考：页面可能有多个含「发布」的按钮，最后一个才是真正的发布按钮
        try:
            publish_btn = page.locator('div[role="button"]').filter(hasText='发布').last()
            if await publish_btn.count() > 0:
                await publish_btn.wait_for(state="visible", timeout=10000)
                await asyncio.sleep(1)
                await publish_btn.click(force=True, timeout=5000)
                logger.info("[发布] 已点击发布按钮 (最后一个 div[role='button']:has-text('发布'))")
                await asyncio.sleep(8)
            else:
                # 兜底：尝试英文按钮
                publish_btn = page.locator('div[role="button"]').filter(hasText='Post').last()
                if await publish_btn.count() > 0:
                    await publish_btn.click(force=True, timeout=5000)
                    logger.info("[发布] 已点击发布按钮 (Post)")
                    await asyncio.sleep(8)
                else:
                    # 最终兜底
                    publish_btn = page.locator('div[role="button"]').filter(hasText='Share').last()
                    if await publish_btn.count() > 0:
                        await publish_btn.click(force=True, timeout=5000)
                        logger.info("[发布] 已点击发布按钮 (Share)")
                        await asyncio.sleep(8)
                    else:
                        logger.warning("[发布] 未找到发布按钮")
        except Exception as e:
            logger.error(f"[发布] 发布按钮点击失败: {e}")
            raise

        # 检查是否有二次确认（Done / 确认）
        try:
            confirm_selectors = [
                'div[role="button"]:has-text("Done")',
                'div[role="button"]:has-text("确认")',
                'div[role="button"]:has-text("Share")',
            ]
            for sel in confirm_selectors:
                confirm_btn = page.locator(sel).first
                if await confirm_btn.count() > 0:
                    await confirm_btn.click(timeout=5000)
                    await asyncio.sleep(3)
                    logger.info(f"[发布] 点击了二次确认按钮: {sel}")
                    break
        except Exception:
            pass

        logger.info("[发布] Facebook 发布流程完成")
