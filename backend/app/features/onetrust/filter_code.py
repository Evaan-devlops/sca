import datetime
import logging
import re

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.core.config import settings
from app.features.onetrust.auth import is_logged_in
from app.features.onetrust.browser import browser_manager

logger = logging.getLogger(__name__)


def _normalize_domain(url: str) -> str:
    n = re.sub(r"^https?://(www\.)?", "", url).split("/")[0].lower()
    return n


def _url_variants(url: str) -> list[str]:
    n = re.sub(r"^https?://", "", url).rstrip("/").lower()
    variants = [n]
    if n.startswith("www."):
        variants.append(n[4:])
    variants.append("http://" + n)
    variants.append("https://" + n)
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


async def _collect_visible_markers(page: Page) -> list[str]:
    markers = [
        "Websites", "Website URL", "Scan status", "Add website",
        "No records found", "Loading", "Website details",
    ]
    found: list[str] = []
    for marker in markers:
        try:
            if await page.locator(f"text={marker}").count() > 0:
                found.append(marker)
        except Exception:  # noqa: BLE001
            pass
    return found


async def wait_websites_table_loaded(page: Page, timeout_ms: int) -> None:
    table_ready_selectors = [
        "text=Website URL",
        "text=Scan status",
        "input[type='search']",
        "button:has-text('Add website')",
        "[role='row']",
        "text=No records found",
    ]
    poll_ms = 3000
    elapsed = 0
    while elapsed < timeout_ms:
        for selector in table_ready_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    return
            except Exception:  # noqa: BLE001
                pass
        logger.info("Waiting for Websites table to load... elapsed=%dms", elapsed)
        await page.wait_for_timeout(poll_ms)
        elapsed += poll_ms
    raise RuntimeError(f"Websites table did not load within {timeout_ms // 1000}s")


async def filter_code_flow(url: str) -> dict:
    """
    Extract data-domain-script from OneTrust Production scripts modal (12 steps).

    Steps:
      1. confirm_login
      2. open_websites_page
      3. wait_websites_table_loaded
      4. filter_website
      5. find_website_row
      6. verify_scan_completed
      7. open_website_details
      8. wait_website_details_page
      9. open_actions_menu
      10. click_copy_production_scripts
      11. wait_production_scripts_modal
      12. extract_data_domain_script
    """
    steps: list[dict] = []
    page = await browser_manager.get_page()
    table_timeout_ms = settings.onetrust_website_table_timeout_ms
    normalized_domain = _normalize_domain(url)
    variants = _url_variants(url)
    matched_display_url: str | None = None
    scan_status: str | None = None
    data_domain_script: str | None = None
    script_snippet: str | None = None

    # ------------------------------------------------------------------ #
    # Step 1 — confirm_login
    # ------------------------------------------------------------------ #
    step_name = "confirm_login"
    logger.info("[%s] started | url=%s", step_name, page.url)
    if not await is_logged_in(page):
        steps.append({"step": step_name, "status": "failed", "message": "Not logged in"})
        return {
            "status": "not logged in",
            "message": "Please call /auth/login first or complete SSO in the opened browser.",
            "input_url": url,
            "current_url": page.url,
            "steps": steps,
        }
    steps.append({"step": step_name, "status": "completed"})

    # ------------------------------------------------------------------ #
    # Step 2 — open_websites_page
    # ------------------------------------------------------------------ #
    step_name = "open_websites_page"
    logger.info("[%s] started | url=%s", step_name, page.url)
    try:
        websites_url = f"{settings.onetrust_base_url.rstrip('/')}/cookies/websites"
        if "/cookies/websites" not in page.url:
            await page.goto(websites_url, wait_until="domcontentloaded")
        try:
            await page.wait_for_selector("text=Websites", timeout=15000)
        except PlaywrightTimeoutError:
            logger.warning("[%s] Websites heading not detected — proceeding", step_name)
        url_lower = page.url.lower()
        if any(ind in url_lower for ind in ("auth/login", "pingidentity", "sso", "pfizeridentity")):
            steps.append({"step": step_name, "status": "failed", "message": f"Redirected to SSO: {page.url}"})
            return {
                "status": "not logged in",
                "message": "Session expired — redirected to SSO. Please call /auth/login first.",
                "input_url": url,
                "current_url": page.url,
                "steps": steps,
            }
        steps.append({"step": step_name, "status": "completed"})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot,
                                   possible_reason="Navigation to Websites page failed")
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
            "debug": debug,
        }

    # ------------------------------------------------------------------ #
    # Step 3 — wait_websites_table_loaded
    # ------------------------------------------------------------------ #
    step_name = "wait_websites_table_loaded"
    logger.info("[%s] started | url=%s", step_name, page.url)
    try:
        await wait_websites_table_loaded(page, table_timeout_ms)
        steps.append({"step": step_name, "status": "completed"})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        markers = await _collect_visible_markers(page)
        debug = await _build_debug(
            page, step_name, exc=exc, screenshot=screenshot,
            possible_reason="Websites table controls did not appear — SPA may still be loading",
            next_action="Check if OneTrust Websites page loaded correctly",
            visible_markers=markers,
        )
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
            "debug": debug,
        }

    # ------------------------------------------------------------------ #
    # Step 4 — filter_website
    # ------------------------------------------------------------------ #
    step_name = "filter_website"
    logger.info("[%s] started | url=%s | query=%s", step_name, page.url, normalized_domain)
    try:
        search_box = None
        search_candidates = [
            page.get_by_placeholder(re.compile(r"Search", re.I)),
            page.get_by_role("searchbox"),
            page.locator("input[type='search']"),
            page.locator("input[placeholder*='Search' i]"),
        ]
        for loc in search_candidates:
            try:
                if await loc.count() > 0:
                    search_box = loc
                    break
            except Exception:  # noqa: BLE001
                pass

        if search_box is not None:
            await search_box.first.fill(normalized_domain)
            try:
                await search_box.first.press("Enter")
            except Exception:  # noqa: BLE001
                pass
            await page.wait_for_timeout(2000)

        steps.append({"step": step_name, "status": "completed", "value": normalized_domain})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot,
                                   possible_reason="Search box not found or search failed")
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
            "debug": debug,
        }

    # ------------------------------------------------------------------ #
    # Step 5 — find_website_row
    # ------------------------------------------------------------------ #
    step_name = "find_website_row"
    logger.info("[%s] started | url=%s | variants=%s", step_name, page.url, variants)
    try:
        poll_ms = 3000
        elapsed = 0
        while elapsed < table_timeout_ms:
            for variant in variants:
                row_loc = page.locator("tr").filter(
                    has_text=re.compile(re.escape(variant), re.I)
                )
                if await row_loc.count() > 0:
                    matched_display_url = variant
                    break
                row_loc2 = page.get_by_role("row").filter(
                    has_text=re.compile(re.escape(variant), re.I)
                )
                if await row_loc2.count() > 0:
                    matched_display_url = variant
                    break
                text_loc = page.locator(f"text={variant}")
                if await text_loc.count() > 0:
                    matched_display_url = variant
                    break
            if matched_display_url is not None:
                break
            logger.info("[%s] row not found — waiting... elapsed=%dms", step_name, elapsed)
            # Re-run search
            try:
                sb = page.get_by_role("searchbox")
                if await sb.count() == 0:
                    sb = page.locator("input[type='search']")
                if await sb.count() > 0:
                    await sb.first.fill(normalized_domain)
                    await page.wait_for_timeout(500)
            except Exception:  # noqa: BLE001
                pass
            # Try refresh button
            try:
                refresh_btn = page.get_by_role("button", name=re.compile(r"refresh", re.I))
                if await refresh_btn.count() > 0:
                    await refresh_btn.first.click(timeout=5000)
            except Exception:  # noqa: BLE001
                pass
            await page.wait_for_timeout(poll_ms)
            elapsed += poll_ms

        if matched_display_url is None:
            steps.append({
                "step": step_name,
                "status": "failed",
                "message": f"Row not found for variants: {variants}",
            })
            markers = await _collect_visible_markers(page)
            debug = await _build_debug(
                page, step_name,
                possible_reason="Website row not in table — /add_app may not have completed or table is still loading",
                next_action="Run /add_app first, then retry /filter_code",
                visible_markers=markers,
            )
            return {
                "status": "website not found",
                "message": "Website row not found. Run /add_app first or wait for OneTrust table refresh.",
                "input_url": url,
                "normalized_domain": normalized_domain,
                "current_url": page.url,
                "steps": steps,
                "debug": debug,
            }

        steps.append({"step": step_name, "status": "completed", "matched_display_url": matched_display_url})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot)
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
            "debug": debug,
        }

    # ------------------------------------------------------------------ #
    # Step 6 — verify_scan_completed
    # ------------------------------------------------------------------ #
    step_name = "verify_scan_completed"
    logger.info("[%s] started | url=%s", step_name, page.url)
    try:
        poll_ms = 5000
        elapsed = 0
        while elapsed < table_timeout_ms:
            row_text = ""
            for variant in variants:
                row_loc = page.locator("tr").filter(
                    has_text=re.compile(re.escape(variant), re.I)
                )
                if await row_loc.count() > 0:
                    try:
                        row_text = await row_loc.first.inner_text()
                    except Exception:  # noqa: BLE001
                        pass
                    break
                row_loc2 = page.get_by_role("row").filter(
                    has_text=re.compile(re.escape(variant), re.I)
                )
                if await row_loc2.count() > 0:
                    try:
                        row_text = await row_loc2.first.inner_text()
                    except Exception:  # noqa: BLE001
                        pass
                    break

            if "Completed" in row_text:
                scan_status = "Completed"
                break
            if any(bad in row_text for bad in ("Failed", "Error")):
                scan_status = "Failed"
                break

            if row_text:
                logger.info("[%s] scan still pending — waiting... elapsed=%dms", step_name, elapsed)
            await page.wait_for_timeout(poll_ms)
            try:
                refresh_btn = page.get_by_role("button", name=re.compile(r"refresh", re.I))
                if await refresh_btn.count() > 0:
                    await refresh_btn.first.click(timeout=5000)
                    await page.wait_for_timeout(1000)
            except Exception:  # noqa: BLE001
                pass
            elapsed += poll_ms

        if scan_status == "Failed":
            screenshot = await browser_manager.screenshot_on_error(step_name)
            steps.append({"step": step_name, "status": "failed", "message": "Scan status is Failed"})
            debug = await _build_debug(page, step_name, screenshot=screenshot,
                                       possible_reason="OneTrust scan returned Failed status")
            return {
                "status": "scan failed",
                "message": "Scan status is 'Failed' for the requested website.",
                "input_url": url,
                "normalized_domain": normalized_domain,
                "matched_display_url": matched_display_url,
                "scan_status": "Failed",
                "current_url": page.url,
                "screenshot": screenshot,
                "steps": steps,
                "debug": debug,
            }

        if scan_status is None:
            steps.append({
                "step": step_name,
                "status": "failed",
                "message": "Scan did not complete within timeout",
            })
            debug = await _build_debug(
                page, step_name,
                possible_reason="Scan still pending after timeout",
                next_action=f"Increase ONETRUST_WEBSITE_TABLE_TIMEOUT_MS (currently {table_timeout_ms}ms) or wait and retry",
            )
            return {
                "status": "scan pending",
                "message": "Scan did not reach Completed status within timeout.",
                "input_url": url,
                "normalized_domain": normalized_domain,
                "matched_display_url": matched_display_url,
                "scan_status": "Pending",
                "current_url": page.url,
                "steps": steps,
                "debug": debug,
            }

        steps.append({"step": step_name, "status": "completed", "scan_status": "Completed"})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot)
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
            "debug": debug,
        }

    # ------------------------------------------------------------------ #
    # Step 7 — open_website_details
    # ------------------------------------------------------------------ #
    step_name = "open_website_details"
    logger.info("[%s] started | url=%s", step_name, page.url)
    try:
        clicked = False
        for variant in variants:
            row_loc = page.locator("tr").filter(
                has_text=re.compile(re.escape(variant), re.I)
            )
            if await row_loc.count() == 0:
                row_loc = page.get_by_role("row").filter(
                    has_text=re.compile(re.escape(variant), re.I)
                )
            if await row_loc.count() > 0:
                link_in_row = row_loc.first.locator("a")
                if await link_in_row.count() > 0:
                    await link_in_row.first.click(timeout=10000)
                    clicked = True
                    break
                text_cell = row_loc.first.locator(f"text={variant}")
                if await text_cell.count() > 0:
                    await text_cell.first.click(timeout=10000)
                    clicked = True
                    break

        if not clicked:
            raise RuntimeError(f"Could not find clickable link in website row for variants: {variants}")

        details_loaded = False
        try:
            await page.wait_for_url(re.compile(r"/cookies/scan-results/"), timeout=15000)
            details_loaded = True
        except PlaywrightTimeoutError:
            pass
        if not details_loaded:
            try:
                await page.wait_for_selector("text=Website details", timeout=15000)
                details_loaded = True
            except PlaywrightTimeoutError:
                pass
        if not details_loaded:
            logger.warning("[%s] website details navigation not confirmed — proceeding", step_name)

        steps.append({"step": step_name, "status": "completed"})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot,
                                   possible_reason="Could not click website row link to open details page")
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "normalized_domain": normalized_domain,
            "matched_display_url": matched_display_url,
            "scan_status": scan_status,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
            "debug": debug,
        }

    # ------------------------------------------------------------------ #
    # Step 8 — wait_website_details_page
    # ------------------------------------------------------------------ #
    step_name = "wait_website_details_page"
    logger.info("[%s] started | url=%s", step_name, page.url)
    try:
        await page.wait_for_selector("text=Website details", timeout=20000)
        try:
            await page.wait_for_selector("button:has-text('Publish')", timeout=10000)
        except PlaywrightTimeoutError:
            logger.warning("[%s] Publish button not detected — proceeding", step_name)
        steps.append({"step": step_name, "status": "completed"})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot,
                                   possible_reason="Website details page did not load",
                                   next_action="Check if the row click navigated correctly")
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "normalized_domain": normalized_domain,
            "matched_display_url": matched_display_url,
            "scan_status": scan_status,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
            "debug": debug,
        }

    # ------------------------------------------------------------------ #
    # Step 9 — open_actions_menu
    # ------------------------------------------------------------------ #
    step_name = "open_actions_menu"
    logger.info("[%s] started | url=%s", step_name, page.url)
    try:
        more_btn = None
        more_candidates = [
            page.get_by_role("button", name=re.compile(r"^More$", re.I)),
            page.get_by_role("button", name=re.compile(r"More options", re.I)),
            page.locator("button[aria-label*='More' i]"),
            page.locator("button:has-text('...')"),
            page.locator("[aria-label*='more' i]"),
        ]
        for loc in more_candidates:
            try:
                cnt = await loc.count()
                if cnt == 1:
                    more_btn = loc.first
                    break
                elif cnt > 1:
                    best_btn = None
                    best_y = float("inf")
                    for i in range(cnt):
                        try:
                            box = await loc.nth(i).bounding_box()
                            if box and box["y"] < best_y:
                                best_y = box["y"]
                                best_btn = loc.nth(i)
                        except Exception:  # noqa: BLE001
                            pass
                    if best_btn is not None:
                        more_btn = best_btn
                        break
            except Exception:  # noqa: BLE001
                pass

        if more_btn is None:
            raise RuntimeError("Could not find three-dot actions menu button near Publish")

        await more_btn.click(timeout=10000)

        try:
            await page.wait_for_selector("text=Copy production scripts", timeout=10000)
        except PlaywrightTimeoutError:
            raise RuntimeError("Actions menu opened but 'Copy production scripts' option not found")

        steps.append({"step": step_name, "status": "completed"})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot,
                                   possible_reason="Three-dot actions menu near Publish/Publish test not found",
                                   next_action="Check if the Website details page has a More/... button near Publish")
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "normalized_domain": normalized_domain,
            "matched_display_url": matched_display_url,
            "scan_status": scan_status,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
            "debug": debug,
        }

    # ------------------------------------------------------------------ #
    # Step 10 — click_copy_production_scripts
    # ------------------------------------------------------------------ #
    step_name = "click_copy_production_scripts"
    logger.info("[%s] started | url=%s", step_name, page.url)
    try:
        copy_btn = page.get_by_text("Copy production scripts", exact=True)
        if await copy_btn.count() == 0:
            copy_btn = page.get_by_role("menuitem", name=re.compile(r"Copy production scripts", re.I))
        if await copy_btn.count() == 0:
            copy_btn = page.locator("text=Copy production scripts")
        await copy_btn.first.click(timeout=10000)
        steps.append({"step": step_name, "status": "completed"})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot,
                                   possible_reason="'Copy production scripts' menu item not found or not clickable")
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "normalized_domain": normalized_domain,
            "matched_display_url": matched_display_url,
            "scan_status": scan_status,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
            "debug": debug,
        }

    # ------------------------------------------------------------------ #
    # Step 11 — wait_production_scripts_modal
    # ------------------------------------------------------------------ #
    step_name = "wait_production_scripts_modal"
    logger.info("[%s] started | url=%s", step_name, page.url)
    try:
        modal_loaded = False
        for marker in ("text=Production scripts", "text=data-domain-script", "text=otSDKStub.js"):
            try:
                await page.wait_for_selector(marker, timeout=15000)
                modal_loaded = True
                break
            except PlaywrightTimeoutError:
                continue
        if not modal_loaded:
            raise RuntimeError("Production scripts modal did not appear")
        steps.append({"step": step_name, "status": "completed"})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot,
                                   possible_reason="Production scripts modal did not open after clicking 'Copy production scripts'")
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "normalized_domain": normalized_domain,
            "matched_display_url": matched_display_url,
            "scan_status": scan_status,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
            "debug": debug,
        }

    # ------------------------------------------------------------------ #
    # Step 12 — extract_data_domain_script
    # ------------------------------------------------------------------ #
    step_name = "extract_data_domain_script"
    logger.info("[%s] started | url=%s", step_name, page.url)
    try:
        modal_loc = page.locator("[role='dialog']")
        if await modal_loc.count() == 0:
            modal_loc = page.locator("[class*='modal' i], [class*='dialog' i]")
        if await modal_loc.count() == 0:
            modal_loc = page.locator("body")

        modal_text = await modal_loc.first.inner_text()
        script_snippet = modal_text[:2000] if modal_text else None

        match = re.search(r'data-domain-script=["\']([^"\']+)["\']', modal_text)
        if match:
            data_domain_script = match.group(1)
        else:
            raise RuntimeError("data-domain-script attribute not found in modal text")

        steps.append({"step": step_name, "status": "completed", "value": data_domain_script})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot,
                                   possible_reason="data-domain-script not found in Production scripts modal",
                                   next_action="Check modal content manually")
        return {
            "status": "failed",
            "message": f"Step '{step_name}' failed: {exc}",
            "input_url": url,
            "normalized_domain": normalized_domain,
            "matched_display_url": matched_display_url,
            "scan_status": scan_status,
            "current_url": page.url,
            "screenshot": screenshot,
            "steps": steps,
            "debug": debug,
        }

    # ------------------------------------------------------------------ #
    # Final return — all 12 steps completed
    # ------------------------------------------------------------------ #
    debug_info = await _build_debug(
        page, "extract_data_domain_script",
        possible_reason=None,
        next_action="data-domain-script extracted successfully",
        visible_markers=["Production scripts", "data-domain-script"],
    )
    return {
        "status": "data_domain_script extracted",
        "message": "Production script data-domain-script was extracted successfully.",
        "input_url": url,
        "normalized_domain": normalized_domain,
        "matched_display_url": matched_display_url,
        "scan_status": scan_status,
        "data_domain_script": data_domain_script,
        "script_snippet": script_snippet,
        "current_url": page.url,
        "screenshot": None,
        "steps": steps,
        "debug": debug_info,
    }
