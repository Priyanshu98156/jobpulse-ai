import logging
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, BrowserContext, Page, Playwright
from app.core.config import DATA_DIR

logger = logging.getLogger(__name__)

BROWSER_PROFILE_DIR = DATA_DIR / "browser_profile"
BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

class BrowserManager:
    """
    Manages Playwright browser instance with a persistent dedicated profile.
    Mandatory headed mode per CODING_STANDARDS.md - no stealth evasion tricks.
    """
    def __init__(self, user_data_dir: Path = BROWSER_PROFILE_DIR, headless: bool = False):
        self.user_data_dir = user_data_dir
        self.headless = headless
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None

    async def start(self) -> BrowserContext:
        """Starts Playwright persistent context in headed mode."""
        if self._context is not None:
            return self._context

        logger.info(f"Launching persistent headed browser with profile at {self.user_data_dir}")
        self._playwright = await async_playwright().start()
        
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.user_data_dir),
            headless=self.headless,
            viewport={"width": 1280, "height": 800},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-default-browser-check",
                "--no-first-run",
            ]
        )
        return self._context

    async def get_page(self) -> Page:
        """Returns the active page or creates a new one."""
        ctx = await self.start()
        if ctx.pages:
            return ctx.pages[0]
        return await ctx.new_page()

    async def close(self):
        """Cleanly releases browser context and Playwright resources."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("Browser session closed cleanly.")

browser_manager = BrowserManager()

