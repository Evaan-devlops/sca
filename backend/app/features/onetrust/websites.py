import datetime
import logging
import re

from playwright.async_api import Page, expect
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


async def ensure_websites_page(page: Page) -> None:
    """Navigate to the Websites page if not already there."""
    websites_url = f"{settings.onetrust_base_url.rstrip('/')}/cookies/websites"
    if "/cookies/websites" not in page.url:
        logger.info("Navigating to Websites page: %s", websites_url)
        await page.goto(websites_url, wait_until="domcontentloaded")
    try:
        await page.wait_for_selector("text=Websites", timeout=15000)
    except PlaywrightTimeoutError:
        logger.warning("Websites heading not detected — proceeding anyway")


async def click_add_website_button(page: Page) -> bool:
    """Attempt to click the Add website button using multiple locator strategies."""
    locators = [
        page.get_by_role("button", name=re.compile(r"Add website", re.I)),
        page.get_by_text("Add website", exact=False),
        page.locator("button:has-text('Add website')"),
    ]
    for loc in locators:
        try:
            if await loc.count() > 0:
                await loc.first.click(timeout=10000)
                logger.info("Clicked 'Add website' button")
                return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("Locator attempt failed: %s", exc)
    return False


async def add_app_flow(url: str) -> dict:
    """
    Orchestrate the full Add Website wizard flow (13 steps).

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
      12. find_website_row
      13. wait_scan_status_completed
    """
    steps: list[dict] = []
    page = await browser_manager.get_page()
    kit_name = get_experience_kit_for_url(url)

    # ------------------------------------------------------------------ #
    # Step 1 — confirm_login
    # ------------------------------------------------------------------ #
    step_name = "confirm_login"
    logger.info("[%s] started | url=%s", step_name, page.url)
    if not await is_logged_in(page):
        logger.warning("[%s] not logged in", step_name)
        steps.append({"step": step_name, "status": "failed", "message": "Not logged in"})
        return {
            "status": "not logged in",
            "message": "Please call /auth/login first or complete SSO in the opened browser.",
            "input_url": url,
            "current_url": page.url,
            "steps": steps,
        }
    logger.info("[%s] completed | url=%s", step_name, page.url)
    steps.append({"step": step_name, "status": "completed"})

    # ------------------------------------------------------------------ #
    # Step 2 — open_websites_page
    # ------------------------------------------------------------------ #
    step_name = "open_websites_page"
    logger.info("[%s] started | url=%s", step_name, page.url)
    try:
        await ensure_websites_page(page)
        url_lower = page.url.lower()
        if any(ind in url_lower for ind in ("auth/login", "pingidentity", "sso", "pfizeridentity", "processing")):
            logger.warning("[%s] SSO redirect detected: %s", step_name, page.url)
            steps.append({"step": step_name, "status": "failed", "message": f"Redirected to SSO: {page.url}"})
            return {
                "status": "not logged in",
                "message": "Session expired — redirected to SSO. Please call /auth/login first.",
                "input_url": url,
                "current_url": page.url,
                "steps": steps,
            }
        logger.info("[%s] completed | url=%s", step_name, page.url)
        steps.append({"step": step_name, "status": "completed"})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
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
    # Step 3 — click_add_website
    # ------------------------------------------------------------------ #
    step_name = "click_add_website"
    logger.info("[%s] started | url=%s", step_name, page.url)
    try:
        success = await click_add_website_button(page)
        if not success:
            raise RuntimeError("Could not find or click the 'Add website' button")

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
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
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
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
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
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
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
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
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
    try:
        next_btn = page.get_by_role("button", name=re.compile(r"^Next$", re.I))
        if await next_btn.count() == 0:
            next_btn = page.locator("button:has-text('Next')")
        await next_btn.first.click(timeout=10000)

        logger.info("[%s] completed | url=%s", step_name, page.url)
        steps.append({"step": step_name, "status": "completed"})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
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
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(
            page, step_name, exc=exc, screenshot=screenshot,
            possible_reason="Next button may not have navigated to Review configurations page",
            next_action="Check if experience kit selection completed correctly",
        )
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
    try:
        confirm_btn = page.get_by_role("button", name=re.compile(r"^Confirm$", re.I))
        if await confirm_btn.count() == 0:
            confirm_btn = page.locator("button:has-text('Confirm')")
        await expect(confirm_btn.first).to_be_enabled(timeout=15000)
        await confirm_btn.first.click(timeout=10000)
        logger.info("[%s] completed | url=%s", step_name, page.url)
        steps.append({"step": step_name, "status": "completed"})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(
            page, step_name, exc=exc, screenshot=screenshot,
            possible_reason="Confirm button not found or not enabled",
            next_action="Check if Accept All was clicked correctly",
        )
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
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(
            page, step_name, exc=exc, screenshot=screenshot,
            possible_reason="Confirm may not have submitted or wizard may still be open",
            next_action="Check if a validation error or modal is blocking navigation",
        )
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
    # Step 12 — find_website_row
    # ------------------------------------------------------------------ #
    matched_display_url: str | None = None
    step_name = "find_website_row"
    logger.info("[%s] started | url=%s | input_url=%s", step_name, page.url, url)
    try:
        # Search using normalized domain
        search_term = _normalize_url_for_search(url)
        variants = _domain_variants(url)

        # Use search box on Websites page
        search_box = page.get_by_role("searchbox")
        if await search_box.count() == 0:
            search_box = page.locator("input[type='search']")
        if await search_box.count() > 0:
            await search_box.first.fill(search_term)
            await page.wait_for_timeout(1500)  # wait for table refresh

        # Find matching row — try each variant
        for variant in variants:
            row_loc = page.locator(f"text={variant}")
            if await row_loc.count() > 0:
                raw_text = await row_loc.first.inner_text()
                matched_display_url = raw_text.strip()
                break

        if matched_display_url is None:
            raise RuntimeError(f"Website row not found for URL variants: {variants}")

        logger.info("[%s] completed | matched=%s | url=%s", step_name, matched_display_url, page.url)
        steps.append({"step": step_name, "status": "completed", "matched_display_url": matched_display_url})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(
            page, step_name, exc=exc, screenshot=screenshot,
            possible_reason="Website row not found in table — may still be processing or URL normalization mismatch",
            next_action="Check the Websites table manually and verify the URL was added",
        )
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
    # Step 13 — wait_scan_status_completed
    # ------------------------------------------------------------------ #
    step_name = "wait_scan_status_completed"
    logger.info("[%s] started | url=%s", step_name, page.url)
    try:
        timeout_ms = settings.scan_timeout_ms
        poll_interval_ms = 5000
        elapsed = 0
        scan_status: str | None = None
        variants = _domain_variants(url)

        while elapsed < timeout_ms:
            # Re-find the row text
            row_text = ""
            for variant in variants:
                row_loc = page.locator(f"text={variant}")
                if await row_loc.count() > 0:
                    # Get the parent row text for scan status
                    try:
                        row_el = row_loc.first.locator("xpath=ancestor::tr")
                        if await row_el.count() > 0:
                            row_text = await row_el.first.inner_text()
                        else:
                            row_text = await row_loc.first.inner_text()
                    except Exception:  # noqa: BLE001
                        row_text = await row_loc.first.inner_text()
                    break

            if "Completed" in row_text:
                scan_status = "Completed"
                break
            if any(bad in row_text for bad in ("Failed", "Error")):
                scan_status = "Failed"
                break

            # Still pending — wait and try to refresh
            await page.wait_for_timeout(poll_interval_ms)
            try:
                refresh_btn = page.get_by_role("button", name=re.compile(r"refresh", re.I))
                if await refresh_btn.count() > 0:
                    await refresh_btn.first.click(timeout=5000)
                    await page.wait_for_timeout(1000)
            except Exception:  # noqa: BLE001
                pass
            elapsed += poll_interval_ms

        if scan_status == "Failed":
            screenshot = await browser_manager.screenshot_on_error(step_name)
            steps.append({"step": step_name, "status": "failed", "message": "Scan status is Failed"})
            debug = await _build_debug(
                page, step_name, screenshot=screenshot,
                possible_reason="OneTrust scan returned Failed status",
                next_action="Check scan logs in the OneTrust Websites page",
            )
            return {
                "status": "scan failed",
                "message": "Scan status is 'Failed' for the added website.",
                "input_url": url,
                "selected_kit": kit_name,
                "scan_status": "Failed",
                "matched_display_url": matched_display_url,
                "current_url": page.url,
                "screenshot": screenshot,
                "steps": steps,
                "debug": debug,
            }

        if scan_status is None:
            raise RuntimeError(f"Scan status did not reach Completed within {timeout_ms // 1000}s timeout")

        logger.info("[%s] completed — scan_status=Completed | url=%s", step_name, page.url)
        steps.append({"step": step_name, "status": "completed", "scan_status": "Completed"})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(
            page, step_name, exc=exc, screenshot=screenshot,
            possible_reason="Scan timed out or row could not be found during polling",
            next_action=(
                f"Increase ONETRUST_SCAN_TIMEOUT_MS (currently {settings.scan_timeout_ms}ms) "
                "or check scan status manually"
            ),
        )
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
    # Final return — all 13 steps completed
    # ------------------------------------------------------------------ #
    debug_info = await _build_debug(
        page, "wait_scan_status_completed",
        possible_reason=None,
        next_action="Ready for next automation phase",
        visible_markers=["Websites", "Scan status", "Completed"],
    )
    return {
        "status": "website url scan_status completed",
        "message": "Website was added, configuration confirmed, and scan status is Completed.",
        "input_url": url,
        "selected_kit": kit_name,
        "scan_status": "Completed",
        "matched_display_url": matched_display_url,
        "current_url": page.url,
        "screenshot": None,
        "steps": steps,
        "debug": debug_info,
    }
