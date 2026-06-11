import datetime
import logging
import re
from collections.abc import Awaitable, Callable

from playwright.async_api import Locator, Page, expect
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.core.config import settings
from app.features.onetrust.auth import is_logged_in
from app.features.onetrust.browser import browser_manager
from app.features.onetrust.mapper import DEFAULT_EXPERIENCE_KIT, get_experience_kit_for_url

logger = logging.getLogger(__name__)


def _normalize_url_for_search(url: str) -> str:
    """Remove protocol and trailing slash; lowercase."""
    return re.sub(r"^https?://", "", url).rstrip("/").lower()


def _domain_variants(url: str) -> list[str]:
    """Return normalized URL and www-stripped variant."""
    n = _normalize_url_for_search(url)
    variants = [n]
    if n.startswith("www."):
        variants.append(n[4:])
    return variants


async def _build_debug(
    page: Page,
    step: str,
    exc: Exception | None = None,
    screenshot: str | None = None,
    possible_reason: str | None = None,
    next_action: str | None = None,
    visible_markers: list[str] | None = None,
) -> dict:
    try:
        page_title = await page.title()
    except Exception:  # noqa: BLE001
        page_title = None
    return {
        "step": step,
        "current_url": page.url,
        "page_title": page_title,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "screenshot": screenshot,
        "browser_headless": settings.playwright_headless,
        "user_data_dir": settings.playwright_user_data_dir,
        "possible_reason": possible_reason,
        "next_action": next_action,
        "visible_markers": visible_markers or [],
        "exception_type": type(exc).__name__ if exc else None,
        "exception_message": str(exc) if exc else None,
    }


async def _find_add_website_button(page: Page) -> Locator | None:
    candidates: list[Locator] = [
        page.get_by_role("button", name=re.compile(r"Add website", re.I)),
        page.get_by_text("Add website", exact=True),
        page.locator("button:has-text('Add website')"),
        page.locator("[data-testid*='add-website' i]"),
        page.locator("[class*='add-website' i]"),
        page.locator("a:has-text('Add website')"),
    ]
    for loc in candidates:
        try:
            if await loc.count() > 0:
                return loc
        except Exception:  # noqa: BLE001
            pass
    return None


async def collect_visible_markers(page: Page) -> list[str]:
    markers = [
        "Websites", "Add website", "Scan status", "Domain",
        "Last Updated", "spinner", "loading", "Processing", "Please wait",
    ]
    found: list[str] = []
    for marker in markers:
        try:
            if await page.locator(f"text={marker}").count() > 0:
                found.append(marker)
        except Exception:  # noqa: BLE001
            pass
    return found


async def wait_for_websites_page_ready(page: Page) -> None:
    websites_url = f"{settings.onetrust_base_url.rstrip('/')}/cookies/websites"
    if "/cookies/websites" not in page.url:
        logger.info("Navigating to Websites page: %s", websites_url)
        await page.goto(websites_url, wait_until="domcontentloaded")
    try:
        await page.wait_for_selector("text=Websites", timeout=15000)
    except PlaywrightTimeoutError:
        logger.warning("Websites heading not detected — proceeding anyway")
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except PlaywrightTimeoutError:
        pass

    poll_interval_ms = 5000
    max_wait_ms = 60000
    elapsed = 0
    while elapsed < max_wait_ms:
        btn = await _find_add_website_button(page)
        if btn is not None:
            return
        logger.info("Waiting for 'Add website' button... %ds elapsed", elapsed // 1000)
        await page.wait_for_timeout(poll_interval_ms)
        elapsed += poll_interval_ms

    logger.info("'Add website' button not found after 60s — reloading page")
    await page.reload(wait_until="domcontentloaded")
    try:
        await page.wait_for_selector("text=Websites", timeout=15000)
    except PlaywrightTimeoutError:
        pass

    retry_ms = 30000
    elapsed = 0
    while elapsed < retry_ms:
        btn = await _find_add_website_button(page)
        if btn is not None:
            return
        await page.wait_for_timeout(poll_interval_ms)
        elapsed += poll_interval_ms

    raise RuntimeError("Add website button did not appear on Websites page after 90s")


async def add_app_flow(
    url: str,
    emit: Callable[[dict], Awaitable[None]] | None = None,
) -> dict:
    """
    Orchestrate the Add Website wizard flow (11 steps).

    Steps:
      1. confirm_login
      2. open_websites_page
      3. click_add_website
      4. fill_website_url
      5. continue_to_banner_setup
      6. select_experience_kit
      7. click_next_after_kit_selection
      8. wait_review_configurations_page
      9. click_accept_all_preview
      10. click_confirm
      11. wait_return_to_websites_page
    """
    steps: list[dict] = []
    page = await browser_manager.get_page()
    kit_name = get_experience_kit_for_url(url)

    # ------------------------------------------------------------------ #
    # Step 1 — confirm_login
    # ------------------------------------------------------------------ #
    step_name = "confirm_login"
    logger.info("[%s] started | url=%s", step_name, page.url)
    if emit:
        await emit({"event": "step_started", "step": step_name})
    if not await is_logged_in(page):
        logger.warning("[%s] not logged in", step_name)
        steps.append({"step": step_name, "status": "failed", "message": "Not logged in"})
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": "Not logged in", "debug": {}})
        return {
            "status": "not logged in",
            "message": "Please call /auth/login first or complete SSO in the opened browser.",
            "input_url": url,
            "current_url": page.url,
            "steps": steps,
        }
    logger.info("[%s] completed | url=%s", step_name, page.url)
    steps.append({"step": step_name, "status": "completed"})
    if emit:
        await emit({"event": "step_completed", "step": step_name})

    # ------------------------------------------------------------------ #
    # Step 2 — open_websites_page
    # ------------------------------------------------------------------ #
    step_name = "open_websites_page"
    logger.info("[%s] started | url=%s", step_name, page.url)
    if emit:
        await emit({"event": "step_started", "step": step_name})
    try:
        await wait_for_websites_page_ready(page)
        url_lower = page.url.lower()
        if any(ind in url_lower for ind in ("auth/login", "pingidentity", "sso", "pfizeridentity", "processing")):
            logger.warning("[%s] SSO redirect detected: %s", step_name, page.url)
            steps.append({"step": step_name, "status": "failed", "message": f"Redirected to SSO: {page.url}"})
            if emit:
                await emit({"event": "step_failed", "step": step_name, "message": f"Redirected to SSO: {page.url}", "debug": {}})
            return {
                "status": "not logged in",
                "message": "Session expired — redirected to SSO. Please call /auth/login first.",
                "input_url": url,
                "current_url": page.url,
                "steps": steps,
            }
        logger.info("[%s] completed | url=%s", step_name, page.url)
        steps.append({"step": step_name, "status": "completed"})
        if emit:
            await emit({"event": "step_completed", "step": step_name})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        markers = await collect_visible_markers(page)
        debug = await _build_debug(
            page, step_name, exc=exc, screenshot=screenshot,
            possible_reason="Websites page loaded but 'Add website' button did not appear — SPA may still be loading",
            next_action="Check if a spinner or overlay is blocking the button",
            visible_markers=markers,
        )
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {
                "step": debug.get("step"), "possible_reason": debug.get("possible_reason"),
                "next_action": debug.get("next_action"), "exception_type": debug.get("exception_type"),
            }})
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "selected_kit": kit_name,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
            "debug": debug,
        }

    # ------------------------------------------------------------------ #
    # Step 3 — click_add_website
    # ------------------------------------------------------------------ #
    step_name = "click_add_website"
    logger.info("[%s] started | url=%s", step_name, page.url)
    if emit:
        await emit({"event": "step_started", "step": step_name})
    try:
        btn = await _find_add_website_button(page)
        if btn is None:
            raise RuntimeError("Could not find the 'Add website' button")
        await expect(btn.first).to_be_visible(timeout=10000)
        await expect(btn.first).to_be_enabled(timeout=10000)
        await btn.first.scroll_into_view_if_needed()
        await btn.first.click(timeout=10000)

        # Confirm wizard loaded (URL change OR visible heading)
        wizard_loaded = False
        try:
            await page.wait_for_url(re.compile(r"/cookies/new-user-wizard"), timeout=15000)
            wizard_loaded = True
        except PlaywrightTimeoutError:
            pass

        if not wizard_loaded:
            try:
                await page.wait_for_selector("text=Details", timeout=15000)
                wizard_loaded = True
            except PlaywrightTimeoutError:
                pass

        if not wizard_loaded:
            try:
                await page.wait_for_selector("text=URL", timeout=5000)
            except PlaywrightTimeoutError:
                logger.warning("[%s] wizard load confirmation timed out — proceeding", step_name)

        logger.info("[%s] completed | url=%s", step_name, page.url)
        steps.append({"step": step_name, "status": "completed"})
        if emit:
            await emit({"event": "step_completed", "step": step_name})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {}})
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "selected_kit": kit_name,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
        }

    # ------------------------------------------------------------------ #
    # Step 4 — fill_website_url
    # ------------------------------------------------------------------ #
    step_name = "fill_website_url"
    logger.info("[%s] started | url=%s", step_name, page.url)
    if emit:
        await emit({"event": "step_started", "step": step_name})
    try:
        url_input = page.get_by_label(re.compile(r"URL", re.I))
        if await url_input.count() == 0:
            url_input = page.locator("input[placeholder*='example.com' i]")
        if await url_input.count() == 0:
            url_input = page.locator("input[type='url']")

        await url_input.first.fill(url)

        continue_btn = page.get_by_role("button", name=re.compile(r"Continue to banner setup", re.I))
        await expect(continue_btn.first).to_be_enabled(timeout=15000)

        logger.info("[%s] completed | url=%s", step_name, page.url)
        steps.append({"step": step_name, "status": "completed", "value": url})
        if emit:
            await emit({"event": "step_completed", "step": step_name})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {}})
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "selected_kit": kit_name,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
        }

    # ------------------------------------------------------------------ #
    # Step 5 — continue_to_banner_setup
    # ------------------------------------------------------------------ #
    step_name = "continue_to_banner_setup"
    logger.info("[%s] started | url=%s", step_name, page.url)
    if emit:
        await emit({"event": "step_started", "step": step_name})
    try:
        continue_btn = page.get_by_role("button", name=re.compile(r"Continue to banner setup", re.I))
        if await continue_btn.count() == 0:
            continue_btn = page.locator("button:has-text('Continue to banner setup')")
        await continue_btn.first.click(timeout=10000)

        # Wait for "Assign experience kit" or "Review experience kit"
        kit_section_loaded = False
        try:
            await page.wait_for_selector("text=Assign experience kit", timeout=15000)
            kit_section_loaded = True
        except PlaywrightTimeoutError:
            pass

        if not kit_section_loaded:
            try:
                await page.wait_for_selector("text=Review experience kit", timeout=5000)
            except PlaywrightTimeoutError:
                logger.warning("[%s] kit section heading not detected — proceeding", step_name)

        logger.info("[%s] completed | url=%s", step_name, page.url)
        steps.append({"step": step_name, "status": "completed"})
        if emit:
            await emit({"event": "step_completed", "step": step_name})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {}})
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "selected_kit": kit_name,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
        }

    # ------------------------------------------------------------------ #
    # Step 6 — select_experience_kit
    # ------------------------------------------------------------------ #
    step_name = "select_experience_kit"
    logger.info("[%s] started | kit=%s | url=%s", step_name, kit_name, page.url)
    if emit:
        await emit({"event": "step_started", "step": step_name})
    try:
        kit_pattern = re.compile(r"US\s*-?\s*Geolocation Category test", re.I)
        kit_locator = page.get_by_text(kit_pattern)

        try:
            await kit_locator.first.scroll_into_view_if_needed(timeout=5000)
            await kit_locator.first.click(timeout=5000)
        except Exception:  # noqa: BLE001
            # Fallback: use search box
            search_box = page.get_by_role("searchbox")
            if await search_box.count() == 0:
                search_box = page.locator("input[type='search']")
            await search_box.fill(DEFAULT_EXPERIENCE_KIT)
            await page.wait_for_timeout(1000)
            await kit_locator.first.click(timeout=10000)

        next_btn = page.get_by_role("button", name=re.compile(r"^Next$", re.I))
        await expect(next_btn.first).to_be_enabled(timeout=10000)

        logger.info("[%s] completed | url=%s", step_name, page.url)
        steps.append({"step": step_name, "status": "completed", "selected_kit": kit_name})
        if emit:
            await emit({"event": "step_completed", "step": step_name})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {}})
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "selected_kit": kit_name,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
        }

    # ------------------------------------------------------------------ #
    # Step 7 — click_next_after_kit_selection
    # ------------------------------------------------------------------ #
    step_name = "click_next_after_kit_selection"
    logger.info("[%s] started | url=%s", step_name, page.url)
    if emit:
        await emit({"event": "step_started", "step": step_name})
    try:
        next_btn = page.get_by_role("button", name=re.compile(r"^Next$", re.I))
        if await next_btn.count() == 0:
            next_btn = page.locator("button:has-text('Next')")
        await next_btn.first.click(timeout=10000)

        logger.info("[%s] completed | url=%s", step_name, page.url)
        steps.append({"step": step_name, "status": "completed"})
        if emit:
            await emit({"event": "step_completed", "step": step_name})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {}})
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "selected_kit": kit_name,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
        }

    # ------------------------------------------------------------------ #
    # Step 8 — wait_review_configurations_page
    # ------------------------------------------------------------------ #
    step_name = "wait_review_configurations_page"
    logger.info("[%s] started | url=%s", step_name, page.url)
    if emit:
        await emit({"event": "step_started", "step": step_name})
    try:
        markers = ["Review configurations", "Review experience kit", "Geolocation rule group name", "Confirm"]
        loaded = False
        for marker in markers:
            try:
                await page.wait_for_selector(f"text={marker}", timeout=15000)
                loaded = True
                break
            except PlaywrightTimeoutError:
                continue
        if not loaded:
            raise RuntimeError("Review configurations page did not load — none of the expected markers appeared")
        logger.info("[%s] completed | url=%s", step_name, page.url)
        steps.append({"step": step_name, "status": "completed"})
        if emit:
            await emit({"event": "step_completed", "step": step_name})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(
            page, step_name, exc=exc, screenshot=screenshot,
            possible_reason="Next button may not have navigated to Review configurations page",
            next_action="Check if experience kit selection completed correctly",
        )
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {
                "possible_reason": debug.get("possible_reason"), "next_action": debug.get("next_action"),
                "exception_type": debug.get("exception_type"),
            }})
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "selected_kit": kit_name,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
            "debug": debug,
        }

    # ------------------------------------------------------------------ #
    # Step 9 — click_accept_all_preview
    # ------------------------------------------------------------------ #
    step_name = "click_accept_all_preview"
    logger.info("[%s] started | url=%s", step_name, page.url)
    if emit:
        await emit({"event": "step_started", "step": step_name})
    try:
        accept_btn = None
        # Try main page first
        candidates = [
            page.get_by_role("button", name=re.compile(r"Accept All", re.I)),
            page.get_by_text("Accept All", exact=False),
        ]
        for loc in candidates:
            if await loc.count() > 0:
                accept_btn = loc
                break
        # If not on main page, search frames
        if accept_btn is None:
            for frame in page.frames:
                try:
                    frame_loc = frame.get_by_role("button", name=re.compile(r"Accept All", re.I))
                    if await frame_loc.count() > 0:
                        accept_btn = frame_loc
                        break
                    frame_loc2 = frame.get_by_text("Accept All", exact=False)
                    if await frame_loc2.count() > 0:
                        accept_btn = frame_loc2
                        break
                except Exception:  # noqa: BLE001
                    continue

        if accept_btn is not None:
            await accept_btn.first.click(timeout=10000)
            logger.info("[%s] clicked Accept All | url=%s", step_name, page.url)
            steps.append({"step": step_name, "status": "completed"})
            if emit:
                await emit({"event": "step_completed", "step": step_name})
        else:
            # Check if Confirm is already enabled without Accept All
            confirm_check = page.get_by_role("button", name=re.compile(r"^Confirm$", re.I))
            try:
                await expect(confirm_check.first).to_be_enabled(timeout=5000)
                logger.info("[%s] skipped — Confirm already enabled | url=%s", step_name, page.url)
                steps.append({
                    "step": step_name,
                    "status": "skipped",
                    "message": "Accept All not found or not required; Confirm button already enabled",
                })
                if emit:
                    await emit({"event": "step_completed", "step": step_name})
            except Exception:  # noqa: BLE001
                raise RuntimeError("Accept All button not found and Confirm button is not enabled")
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(
            page, step_name, exc=exc, screenshot=screenshot,
            possible_reason="Accept All button not found in main page or any iframe",
            next_action="Check if the banner preview is rendered in an iframe",
        )
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {
                "possible_reason": debug.get("possible_reason"), "next_action": debug.get("next_action"),
                "exception_type": debug.get("exception_type"),
            }})
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "selected_kit": kit_name,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
            "debug": debug,
        }

    # ------------------------------------------------------------------ #
    # Step 10 — click_confirm
    # ------------------------------------------------------------------ #
    step_name = "click_confirm"
    logger.info("[%s] started | url=%s", step_name, page.url)
    if emit:
        await emit({"event": "step_started", "step": step_name})
    try:
        confirm_btn = page.get_by_role("button", name=re.compile(r"^Confirm$", re.I))
        if await confirm_btn.count() == 0:
            confirm_btn = page.locator("button:has-text('Confirm')")
        await expect(confirm_btn.first).to_be_enabled(timeout=15000)
        await confirm_btn.first.click(timeout=10000)
        logger.info("[%s] completed | url=%s", step_name, page.url)
        steps.append({"step": step_name, "status": "completed"})
        if emit:
            await emit({"event": "step_completed", "step": step_name})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(
            page, step_name, exc=exc, screenshot=screenshot,
            possible_reason="Confirm button not found or not enabled",
            next_action="Check if Accept All was clicked correctly",
        )
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {
                "possible_reason": debug.get("possible_reason"), "next_action": debug.get("next_action"),
                "exception_type": debug.get("exception_type"),
            }})
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "selected_kit": kit_name,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
            "debug": debug,
        }

    # ------------------------------------------------------------------ #
    # Step 11 — wait_return_to_websites_page
    # ------------------------------------------------------------------ #
    step_name = "wait_return_to_websites_page"
    logger.info("[%s] started | url=%s", step_name, page.url)
    if emit:
        await emit({"event": "step_started", "step": step_name})
    try:
        websites_reached = False
        try:
            await page.wait_for_url(re.compile(r"/cookies/websites"), timeout=20000)
            websites_reached = True
        except PlaywrightTimeoutError:
            pass
        if not websites_reached:
            try:
                await page.wait_for_selector("text=Scan status", timeout=10000)
                websites_reached = True
            except PlaywrightTimeoutError:
                pass
        if not websites_reached:
            raise RuntimeError("Did not return to Websites page after Confirm")
        logger.info("[%s] completed | url=%s", step_name, page.url)
        steps.append({"step": step_name, "status": "completed"})
        if emit:
            await emit({"event": "step_completed", "step": step_name})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(
            page, step_name, exc=exc, screenshot=screenshot,
            possible_reason="Confirm may not have submitted or wizard may still be open",
            next_action="Check if a validation error or modal is blocking navigation",
        )
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {
                "possible_reason": debug.get("possible_reason"), "next_action": debug.get("next_action"),
                "exception_type": debug.get("exception_type"),
            }})
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "selected_kit": kit_name,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
            "debug": debug,
        }

    # ------------------------------------------------------------------ #
    # Final return — 11 steps completed
    # ------------------------------------------------------------------ #
    debug_info = await _build_debug(
        page, "wait_return_to_websites_page",
        possible_reason=None,
        next_action="Call /filter_code to extract the data-domain-script for this website",
        visible_markers=["Websites"],
    )
    return {
        "status": "website configuration confirmed",
        "message": "Website was added and configuration confirmed. Call /filter_code to fetch the data-domain-script.",
        "input_url": url,
        "selected_kit": kit_name,
        "current_url": page.url,
        "screenshot": None,
        "steps": steps,
        "next_action": {"api": "/filter_code", "request_body": {"url": url}},
        "debug": debug_info,
    }
