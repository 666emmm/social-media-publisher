"""X / Twitter platform implementation — CloakBrowser.

All browser operations go through ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` which delegate to CloakBrowser.
"""

import asyncio
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
    scrape_x_profile,
)
from ..base_platform import BasePlatform

logger = get_channel_logger("x")

X_HOME_URL = "https://x.com/home"
X_COMPOSE_URL = "https://x.com/compose/post"
X_LOGIN_URL = "https://x.com/login"

#: Post button selector on the compose page
_X_POST_BUTTON_SELECTOR = '[data-testid="tweetButton"]'
_X_POST_BUTTON_INLINE_SELECTOR = '[data-testid="tweetButtonInline"]'

#: Text input area
_X_TEXT_AREA_SELECTOR = '[data-testid="tweetTextarea_0"]'
_X_TEXT_AREA_SELECTOR_ALT = 'div[data-testid="toolBar"]'

#: File input for media
_X_FILE_INPUT_SELECTOR = 'input[data-testid="fileInput"]'

#: Audience selector button
_X_AUDIENCE_SELECTOR = '[data-testid="audienceButton"]'

#: X limits
_X_MAX_CHARS = 280


class XPlatform(BasePlatform):
    platform_id = 15
    platform_key = "x"
    platform_name = "X"

    # 支持 cookie 字符串导入账号
    supports_cookie_import = True
    # X/Twitter cookie 域
    platform_cookie_domain = ".x.com"

    def _parse_cookie_to_storage_state(self, cookie_str):
        """把 'k=v; k=v' 解析为 Playwright storage_state 的 (cookies, origins)。"""
        cookies = []
        expires = time.time() + BasePlatform._IMPORT_COOKIE_EXPIRES_SECONDS
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            name, _, value = pair.partition("=")
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": self.platform_cookie_domain,
                "path": "/",
                "expires": expires,
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            })
        logger.info(f"[x] cookie 解析: {len(cookies)} 条, domain={self.platform_cookie_domain}")
        return cookies, []

    # ------------------------------------------------------------------
    # login — QR-less login via CloakBrowser
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform X login via CloakBrowser.

        打开 X 登录页面，用户手动输入用户名密码完成登录。
        后端通过监听 URL 变化判断登录成功，随后抓取用户资料并落库。
        """
        browser = await self.create_browser(login_mode=True)
        try:
            context = await self.create_context(browser)
            page = await context.new_page()
            await page.goto(X_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            original_url = page.url

            url_changed_event = asyncio.Event()

            async def _on_url_change():
                if page.url != original_url and "login" not in page.url.lower():
                    url_changed_event.set()

            # Monitor URL change via framenavigated
            page.on(
                "framenavigated",
                lambda frame: asyncio.create_task(_on_url_change())
                if frame == page.main_frame
                else None,
            )

            logger.info("[x] 打开登录页面，等待用户完成登录...")

            # 不设超时——登录可能耗时几分钟，浏览器由用户自己关
            await url_changed_event.wait()
            logger.info("[x] 页面跳转检测——登录成功")

            # 保存登录状态
            await save_login_result(
                context, page,
                platform_id=self.platform_id,
                platform_name=self.platform_name,
                status_queue=status_queue,
                scrape_fn=scrape_x_profile,
                account_id=account_id,
            )
            logger.info("[x] 登录完成")
        finally:
            try:
                await browser.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # check_cookie — verify saved cookie is still valid
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Verify saved cookie by visiting X home page."""
        cookie_path = Path(BASE_DIR / "cookiesFile" / cookie_file)
        if not cookie_path.exists():
            return False

        def _launch():
            browser = create_browser_sync(headless=True)
            try:
                context = create_context_sync(browser, storage_state=str(cookie_path))
                page = context.new_page()
                page.goto(X_HOME_URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)
                current_url = page.url
                is_logged_in = "login" not in current_url.lower()
                logger.info(f"[x] check_cookie url={current_url}, logged_in={is_logged_in}")
                return is_logged_in
            except Exception as e:
                logger.info(f"[x] check_cookie 异常: {e}")
                return False
            finally:
                try:
                    browser.close()
                except Exception:
                    pass

        return await asyncio.to_thread(_launch)

    # ------------------------------------------------------------------
    # open_creator_center — navigate to compose page
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open X compose page."""
        cookie_path = Path(BASE_DIR / "cookiesFile" / cookie_file)

        def _launch():
            browser = create_browser_sync(headless=False)
            context = create_context_sync(browser, storage_state=str(cookie_path))
            page = context.new_page()
            page.goto(X_COMPOSE_URL, wait_until="domcontentloaded", timeout=30000)
            logger.info(f"[x] 创作者中心已打开: {page.url}")

        await asyncio.to_thread(_launch)

    # ------------------------------------------------------------------
    # sync_profile — scrape user profile info
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile information from X."""
        cookie_path = Path(BASE_DIR / "cookiesFile" / cookie_file)

        def _launch():
            browser = create_browser_sync(headless=True)
            try:
                context = create_context_sync(browser, storage_state=str(cookie_path))
                page = context.new_page()
                page.goto(X_HOME_URL, wait_until="domcontentloaded", timeout=30000)
                import asyncio as _asyncio
                return _asyncio.run(scrape_x_profile(page))
            except Exception as e:
                logger.info(f"[x] sync_profile 异常: {e}")
                return ("", "")
            finally:
                try:
                    browser.close()
                except Exception:
                    pass

        return await asyncio.to_thread(_launch)

    # ------------------------------------------------------------------
    # publish_video — post video/image + text to X
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        """Publish a post with optional media to X.

        Accepted keyword arguments:
        - ``title`` (*str*) — post text (max 280 chars)
        - ``files`` (*list[str]*) — media file absolute paths
        - ``tags`` (*list[str]*) — hashtags (appended to text)
        - ``account_file`` (*list[str]*) — cookie file names
        - ``desc`` (*str*, optional) — additional description text
        - ``schedule_time_str`` (*str*, optional) — ignored (X compose doesn't support scheduling via UI)
        """
        asyncio.run(self._publish(**kwargs))
        return True

    async def _publish(self, **kwargs):
        """Internal async orchestrator for publishing to X."""
        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", []) or []
        desc = kwargs.get("desc", "") or ""
        account_file = kwargs.get("account_file", [])

        # Build full text
        text_parts = [title]
        if desc and desc != title:
            text_parts.append(desc)
        tag_text = " ".join(f"#{t.strip().replace(' ', '')}" for t in tags if t)
        if tag_text:
            text_parts.append(tag_text)
        full_text = "\n\n".join(text_parts) if len(text_parts) > 1 else text_parts[0]

        # Truncate to X's 280 char limit
        if len(full_text) > _X_MAX_CHARS:
            full_text = full_text[:_X_MAX_CHARS - 3] + "..."

        logger.info("=" * 60)
        logger.info(f"[发布] 开始 X 发布流程")
        logger.info(f"[发布参数] text={full_text[:80]}... files={len(files)}")

        for cookie_name in account_file:
            logger.info(f"[发布] 使用账号 cookie: {cookie_name}")
            nick = get_account_name_by_cookie_file(cookie_name) or cookie_name
            bind_account_name(nick)

            cookie_path = Path(BASE_DIR / "cookiesFile" / cookie_name)
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

                # Navigate to compose page
                logger.info(f"[发布] 打开 X 撰写页面: {X_COMPOSE_URL}")
                await page.goto(X_COMPOSE_URL, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                # Upload media first (if any)
                if files:
                    await self._upload_media(page, files)

                # Fill in text
                await self._fill_text(page, full_text)

                # Click Post
                await self._click_post(page)
                logger.info(f"[发布] X 发布成功！({nick})")
            except Exception as e:
                logger.error(f"[发布] X 发布失败 ({nick}): {e}")
                raise
            finally:
                try:
                    await browser.close()
                except Exception:
                    pass

    async def _upload_media(self, page, files: list):
        """Upload image(s) or video to the compose page."""
        logger.info(f"[上传] 准备上传 {len(files)} 个媒体文件")

        for idx, file_path in enumerate(files):
            file_path = Path(file_path)
            if not file_path.exists():
                logger.warning(f"[上传] 文件不存在，跳过: {file_path}")
                continue

            logger.info(f"[上传] 上传第 {idx+1} 个文件: {file_path.name}")
            try:
                # X uses a hidden file input
                file_input = page.locator(_X_FILE_INPUT_SELECTOR).first
                if await file_input.count() == 0:
                    # Try alternative: the file input might be hidden differently
                    file_input = page.locator('input[type="file"]').first

                await file_input.set_input_files(str(file_path))
                await asyncio.sleep(3)

                # Wait for upload to complete — X shows a progress bar or the media preview
                try:
                    await page.wait_for_selector(
                        '[data-testid="attachments"]',
                        state="visible",
                        timeout=60000,
                    )
                    logger.info(f"[上传] 文件 {idx+1} 上传完成")
                except Exception:
                    # Check if media preview appeared
                    logger.info(f"[上传] 文件 {idx+1} 等待附件区域超时，检查预览...")
                    await asyncio.sleep(3)

            except Exception as e:
                logger.error(f"[上传] 文件 {idx+1} 上传失败: {e}")
                raise

    async def _fill_text(self, page, text: str):
        """Fill the tweet text into the compose textarea.

        优先使用 evaluate 直接设置 innerText + 触发 input 事件（瞬间完成），
        失败时回退到 fill()。
        """
        logger.info(f"[填写] 写入文本 ({len(text)} 字符)")

        try:
            text_area = page.locator(_X_TEXT_AREA_SELECTOR).first
            if await text_area.count() == 0:
                text_area = page.locator('[contenteditable="true"]').first

            await text_area.click()
            await asyncio.sleep(0.3)

            # 方案1: 直接用 JS 设置文本内容 + 触发 React onChange（瞬间完成）
            try:
                await text_area.evaluate("""
                    (el, text) => {
                        // 聚焦元素
                        el.focus();
                        // 清空并设置文本
                        if (el.isContentEditable || el.contentEditable === 'true') {
                            el.innerText = text;
                        } else {
                            el.value = text;
                        }
                        // 触发 input 事件让 React/Draft.js 感知变化
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        // 对于 React：通过原生 setter 触发
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
                await asyncio.sleep(0.5)
                logger.info(f"[填写] 文本写入完成 (evaluate)")
                return
            except Exception as e:
                logger.warning(f"[填写] evaluate 失败，回退 fill: {e}")

            # 方案2: 回退到 fill()（适用于标准 input/textarea）
            await text_area.fill(text)
            await asyncio.sleep(0.5)
            logger.info(f"[填写] 文本写入完成 (fill)")
        except Exception as e:
            logger.error(f"[填写] 文本写入失败: {e}")
            raise

    async def _click_post(self, page):
        """Click the Post button and wait for success."""
        logger.info("[发布] 点击 Post 按钮")

        # Try primary post button first
        post_button = page.locator(_X_POST_BUTTON_SELECTOR).first
        if await post_button.count() == 0:
            post_button = page.locator(_X_POST_BUTTON_INLINE_SELECTOR).first

        if await post_button.count() == 0:
            # Generic fallback: any button containing "Post"
            post_button = page.locator('button:has-text("Post")').first

        await post_button.wait_for(state="visible", timeout=10000)
        await asyncio.sleep(1)
        await post_button.click()
        logger.info("[发布] 已点击 Post，等待结果...")

        # Wait for the compose dialog to close or success indicator
        await asyncio.sleep(5)

        # Verify: if we're still on the compose page, something went wrong
        current_url = page.url
        if "compose/post" in current_url:
            # Check for error messages
            try:
                error_el = page.locator('[data-testid="toast"]').first
                if await error_el.count() > 0:
                    error_text = await error_el.text_content()
                    logger.warning(f"[发布] 可能出错: {error_text}")
            except Exception:
                pass
            logger.warning("[发布] Post 后仍在撰写页，可能未发出")
        else:
            logger.info(f"[发布] 页面已跳转: {current_url}")
