"""New engine browser factory — CloakBrowser stealth layer.

Replaces ``vendor/upstream/myUtils/browser.py`` for the new engine.
Old engine (vendor/) continues to use the original patchright-based factory.

All new engine browser creation goes through this module.
"""

from conf import LOCAL_CHROME_HEADLESS, LOGIN_HEADLESS


async def create_browser(
    headless: bool | None = None,
    login_mode: bool = False,
    proxy: dict | None = None,
    extra_args: list | None = None,
):
    """Create a stealth Chromium browser via CloakBrowser.

    Args:
        headless: Run headless.  Defaults to ``LOGIN_HEADLESS`` when
            *login_mode* is True, else ``LOCAL_CHROME_HEADLESS``.
        login_mode: If True, use login headless default (visible).
        proxy: Proxy config (dict or URL string).
        extra_args: Additional Chromium CLI arguments.
    """
    from cloakbrowser import launch_async

    if headless is None:
        headless = LOGIN_HEADLESS if login_mode else LOCAL_CHROME_HEADLESS
    return await launch_async(headless=headless, proxy=proxy, args=extra_args)


async def create_context(
    browser,
    storage_state: str | None = None,
    user_agent: str | None = None,
    viewport: dict | None = None,
):
    """Create a browser context with optional auth state."""
    return await browser.new_context(
        storage_state=storage_state,
        user_agent=user_agent,
        viewport=viewport,
    )


async def create_persistent_context(
    user_data_dir: str,
    headless: bool = False,
    proxy: dict | None = None,
    extra_args: list | None = None,
):
    """Create a persistent browser context with a local user data dir."""
    from cloakbrowser import launch_persistent_context_async

    return await launch_persistent_context_async(
        user_data_dir,
        headless=headless,
        proxy=proxy,
        args=extra_args,
    )


def create_browser_sync(
    headless: bool = False,
    extra_args: list | None = None,
):
    """Synchronous browser launch (for ``open_creator_center``).

    CloakBrowser's ``close()`` automatically handles Playwright instance cleanup.
    """
    from cloakbrowser import launch

    return launch(headless=headless, args=extra_args)
