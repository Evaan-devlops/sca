import logging
from datetime import datetime
from pathlib import Path

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

from app.core.config import settings

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = Path("screenshots")


class BrowserManager:
    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self) -> None:
        if self._playwright is not None:
            return

        user_data_dir = Path(settings.playwright_user_data_dir).resolve()
        user_data_dir.mkdir(parents=True, exist_ok=True)
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            channel=settings.playwright_browser_channel,
            headless=settings.playwright_headless,
            slow_mo=200,
            args=["--start-maximized"],
        )
        logger.info("Chromium launched via channel=%s (headless=%s)", settings.playwright_browser_channel, settings.playwright_headless)

        pages = self._context.pages
        if pages:
            self._page = pages[0]
            logger.info("Reusing existing page from persistent context")
        else:
            self._page = await self._context.new_page()

    async def get_page(self) -> Page:
        if self._page is None:
            await self.start()
        assert self._page is not None
        return self._page

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
            self._page = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def screenshot_on_error(self, name: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = SCREENSHOTS_DIR / f"{name}_{timestamp}.png"
        try:
            if self._page is not None:
                await self._page.screenshot(path=str(filename))
                logger.info("Screenshot saved: %s", filename)
            else:
                logger.warning("screenshot_on_error: page not ready")
        except Exception:  # noqa: BLE001
            logger.warning("Failed to save screenshot: %s", filename)
        return str(filename)

    @property
    def is_ready(self) -> bool:
        return self._playwright is not None and self._page is not None


browser_manager = BrowserManager()
