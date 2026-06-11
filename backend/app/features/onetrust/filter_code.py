import datetime
import logging
import re
from collections.abc import Awaitable, Callable

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.core.config import settings
from app.features.onetrust.auth import is_logged_in, is_sso_or_manual_page
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


async def _find_row_for_variants(page: Page, variants: list[str]) -> str:
    """Re-locate the specific matched row and return its text. Returns '' if not found."""
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
    return row_text


async def wait_website_details_ready(page: Page, domain: str) -> None:
    """
    Poll up to 60s until the Website details page is fully loaded.

    Required markers:
      1. URL matches /cookies/scan-results/
      2. "Website details" text visible
      3. Domain text visible
      4. "Completed" chip/text visible
      5. "Publish" or "Publish test" button visible
      6. Top-right actions menu button visible (near Publish)
      7. No spinner / loading overlay
    """
    # Fast-path: wait for URL to settle first
    try:
        await page.wait_for_url(re.compile(r"/cookies/scan-results/"), timeout=15000)
    except PlaywrightTimeoutError:
        logger.warning("[wait_website_details_ready] URL did not match /cookies/scan-results/ within 15s")

    poll_ms = 3000
    elapsed = 0
    max_ms = 60000

    while elapsed < max_ms:
        all_present = True

        # 1. URL check
        if "/cookies/scan-results/" not in page.url:
            all_present = False

        # 2. "Website details" heading
        if all_present:
            try:
                if await page.locator("text=Website details").count() == 0:
                    all_present = False
            except Exception:  # noqa: BLE001
                all_present = False

        # 3. Domain text visible
        if all_present and domain:
            try:
                if await page.locator(f"text={domain}").count() == 0:
                    all_present = False
            except Exception:  # noqa: BLE001
                all_present = False

        # 4. "Completed" chip
        if all_present:
            try:
                if await page.locator("text=Completed").count() == 0:
                    all_present = False
            except Exception:  # noqa: BLE001
                all_present = False

        # 5. Publish or Publish test button
        if all_present:
            try:
                publish_loc = page.locator("button:has-text('Publish')")
                if await publish_loc.count() == 0:
                    all_present = False
            except Exception:  # noqa: BLE001
                all_present = False

        # 6. Top-right actions menu button (More / Options / Actions near Publish)
        if all_present:
            try:
                found_menu = False
                for selector in [
                    "button[aria-label*='More' i]",
                    "button[aria-label*='Options' i]",
                    "button[aria-label*='Actions' i]",
                ]:
                    if await page.locator(selector).count() > 0:
                        found_menu = True
                        break
                if not found_menu:
                    # Also check by role
                    for name_re in [re.compile(r"^More$", re.I), re.compile(r"More options", re.I)]:
                        if await page.get_by_role("button", name=name_re).count() > 0:
                            found_menu = True
                            break
                if not found_menu:
                    all_present = False
            except Exception:  # noqa: BLE001
                all_present = False

        # 7. No spinner overlay
        if all_present:
            try:
                spinner_selectors = [
                    "[class*='spinner' i]",
                    "[class*='loading' i]",
                    "[aria-label*='loading' i]",
                ]
                for selector in spinner_selectors:
                    if await page.locator(selector).count() > 0:
                        all_present = False
                        break
            except Exception:  # noqa: BLE001
                pass

        if all_present:
            logger.info("[wait_website_details_ready] All markers present — page ready")
            return

        logger.info(
            "[wait_website_details_ready] Waiting for details page markers... elapsed=%dms url=%s",
            elapsed, page.url,
        )
        await page.wait_for_timeout(poll_ms)
        elapsed += poll_ms

    raise RuntimeError(
        f"Website details page did not become fully ready within {max_ms // 1000}s. "
        f"Current URL: {page.url}"
    )


async def click_top_right_actions_menu(page: Page) -> None:
    """
    Click the three-dot/More button near Publish/Publish test (top-right area).
    Uses bounding box Y-coordinate to pick the topmost candidate if multiple found.
    """
    candidates = [
        page.get_by_role("button", name=re.compile(r"^More$", re.I)),
        page.get_by_role("button", name=re.compile(r"More options", re.I)),
        page.locator("button[aria-label*='More' i]"),
        page.locator("button[aria-label*='Options' i]"),
        page.locator("button[aria-label*='Actions' i]"),
    ]

    best_btn = None
    best_y = float("inf")

    for loc in candidates:
        try:
            cnt = await loc.count()
            if cnt == 0:
                continue
            for i in range(cnt):
                try:
                    btn = loc.nth(i)
                    # Only consider visible buttons
                    if not await btn.is_visible():
                        continue
                    box = await btn.bounding_box()
                    if box and box["y"] < best_y:
                        best_y = box["y"]
                        best_btn = btn
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass

    if best_btn is None:
        raise RuntimeError(
            "Could not find top-right three-dot actions menu button near Publish. "
            "Tried: More, More options, aria-label*=More/Options/Actions"
        )

    await best_btn.click(timeout=10000)

    # Verify menu opened by checking for "Copy production scripts" option
    try:
        await page.wait_for_selector("text=Copy production scripts", timeout=10000)
    except PlaywrightTimeoutError:
        screenshot = await browser_manager.screenshot_on_error("click_top_right_actions_menu")
        raise RuntimeError(
            f"Actions menu opened but 'Copy production scripts' option not found within 10s. "
            f"Screenshot: {screenshot}"
        )


async def get_production_modal_text(page: Page) -> str:
    """
    Collect all text content from within the Production scripts modal dialog.

    Gathers text from the dialog role, plus textarea, pre, code elements,
    and elements containing 'otSDKStub.js'. Returns combined, whitespace-normalised text.
    """
    collected: list[str] = []

    # Locate modal by role first; fall back to nearest container of "Production scripts" text
    modal_loc = page.get_by_role("dialog")
    if await modal_loc.count() == 0:
        # Try: find "Production scripts" heading and walk up
        heading = page.locator(":text('Production scripts')")
        if await heading.count() > 0:
            modal_loc = heading.locator("..").locator("..")
        else:
            modal_loc = page.locator("[class*='modal' i], [class*='dialog' i]")
    if await modal_loc.count() == 0:
        modal_loc = page.locator("body")

    modal = modal_loc.first

    # 1. inner_text of the whole modal
    try:
        text = await modal.inner_text()
        if text:
            collected.append(text)
    except Exception:  # noqa: BLE001
        pass

    # 2. textarea elements
    try:
        textareas = modal.locator("textarea")
        cnt = await textareas.count()
        for i in range(cnt):
            try:
                val = await textareas.nth(i).input_value()
                if val:
                    collected.append(val)
            except Exception:  # noqa: BLE001
                try:
                    val = await textareas.nth(i).inner_text()
                    if val:
                        collected.append(val)
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass

    # 3. pre elements
    try:
        pres = modal.locator("pre")
        cnt = await pres.count()
        for i in range(cnt):
            try:
                val = await pres.nth(i).inner_text()
                if val:
                    collected.append(val)
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass

    # 4. code elements
    try:
        codes = modal.locator("code")
        cnt = await codes.count()
        for i in range(cnt):
            try:
                val = await codes.nth(i).inner_text()
                if val:
                    collected.append(val)
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass

    # 5. elements containing 'otSDKStub.js'
    try:
        sdk_els = modal.locator(":text('otSDKStub.js')")
        cnt = await sdk_els.count()
        for i in range(cnt):
            try:
                # Walk up two levels to capture the script tag text
                parent = sdk_els.nth(i).locator("..").locator("..")
                val = await parent.first.inner_text()
                if val:
                    collected.append(val)
            except Exception:  # noqa: BLE001
                try:
                    val = await sdk_els.nth(i).inner_text()
                    if val:
                        collected.append(val)
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass

    combined = "\n".join(collected)
    # Normalize whitespace: collapse multiple spaces/tabs to single space,
    # but preserve newlines for regex matching
    combined = re.sub(r"[ \t]+", " ", combined)
    combined = re.sub(r"\n{3,}", "\n\n", combined)
    return combined.strip()


async def filter_code_flow(
    url: str,
    emit: Callable[[dict], Awaitable[None]] | None = None,
) -> dict:
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
    scan_timeout_ms = settings.onetrust_scan_timeout_ms
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
    if emit:
        await emit({"event": "step_started", "step": step_name})
    if not await is_logged_in(page):
        logger.warning("[%s] not logged in", step_name)
        if await is_sso_or_manual_page(page):
            steps.append({
                "step": step_name,
                "status": "failed",
                "message": "Login is incomplete — SSO/PingID/manual login page detected",
            })
            if emit:
                await emit({
                    "event": "step_failed",
                    "step": step_name,
                    "message": "Login is incomplete. Complete SSO first.",
                })
                await emit({
                    "event": "finished",
                    "status": "login required",
                    "next_action": "Call /auth/login and complete SSO manually.",
                })
            return {
                "status": "login required",
                "message": (
                    "OneTrust login is not complete. "
                    "Complete SSO/manual login first, then retry this API."
                ),
                "failed_step": step_name,
                "input_url": url,
                "current_url": page.url,
                "steps": steps,
                "debug": {
                    "possible_reason": "Browser is still on SSO/PingID/manual login page",
                    "next_action": (
                        "Call /auth/login, complete SSO manually in opened browser, "
                        "then call /auth/status until it returns logged in."
                    ),
                },
            }
        steps.append({"step": step_name, "status": "failed", "message": "Not logged in"})
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": "Not logged in", "debug": {}})
            await emit({"event": "finished", "status": "not logged in"})
        return {
            "status": "not logged in",
            "message": "Please call /auth/login first.",
            "input_url": url,
            "current_url": page.url,
            "steps": steps,
        }
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
            if emit:
                await emit({"event": "step_failed", "step": step_name, "message": f"Redirected to SSO: {page.url}", "debug": {}})
            return {
                "status": "not logged in",
                "message": "Session expired — redirected to SSO. Please call /auth/login first.",
                "input_url": url,
                "current_url": page.url,
                "steps": steps,
            }
        steps.append({"step": step_name, "status": "completed"})
        if emit:
            await emit({"event": "step_completed", "step": step_name})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot,
                                   possible_reason="Navigation to Websites page failed")
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {
                "possible_reason": debug.get("possible_reason"), "exception_type": debug.get("exception_type"),
            }})
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
    if emit:
        await emit({"event": "step_started", "step": step_name})
    try:
        await wait_websites_table_loaded(page, table_timeout_ms)
        steps.append({"step": step_name, "status": "completed"})
        if emit:
            await emit({"event": "step_completed", "step": step_name})
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
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {
                "possible_reason": debug.get("possible_reason"), "next_action": debug.get("next_action"),
                "exception_type": debug.get("exception_type"),
            }})
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
    if emit:
        await emit({"event": "step_started", "step": step_name})
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
        if emit:
            await emit({"event": "step_completed", "step": step_name})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot,
                                   possible_reason="Search box not found or search failed")
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {
                "possible_reason": debug.get("possible_reason"), "exception_type": debug.get("exception_type"),
            }})
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
    if emit:
        await emit({"event": "step_started", "step": step_name})
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
            if emit:
                await emit({"event": "step_failed", "step": step_name,
                            "message": f"Row not found for variants: {variants}", "debug": {
                                "possible_reason": debug.get("possible_reason"),
                                "next_action": debug.get("next_action"),
                            }})
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
        if emit:
            await emit({"event": "step_completed", "step": step_name})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot)
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {
                "exception_type": debug.get("exception_type"),
            }})
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
    # Polls the SPECIFIC matched row only. Uses scan_timeout_ms (not table timeout).
    # ------------------------------------------------------------------ #
    step_name = "verify_scan_completed"
    logger.info("[%s] started | url=%s", step_name, page.url)
    if emit:
        await emit({"event": "step_started", "step": step_name})
    try:
        poll_ms = 5000
        elapsed = 0
        last_status = ""

        logger.info("[%s] verify_scan_completed started | domain=%s", step_name, matched_display_url)

        while elapsed < scan_timeout_ms:
            row_text = await _find_row_for_variants(page, variants)

            # Determine current status from row text
            if "Completed" in row_text:
                current_status = "Completed"
            elif any(bad in row_text for bad in ("Failed", "Error")):
                current_status = "Failed"
            elif row_text:
                # Extract meaningful status word from row text if possible
                status_match = re.search(
                    r"\b(Pending|Scanning|In[- ]?[Pp]rogress|Queued|Running)\b",
                    row_text,
                )
                current_status = status_match.group(1) if status_match else "Pending"
            else:
                current_status = "Unknown"

            if current_status != last_status:
                logger.info("[%s] current scan status: %s", step_name, current_status)
                last_status = current_status

            if current_status == "Completed":
                scan_status = "Completed"
                break

            if current_status == "Failed":
                scan_status = "Failed"
                break

            # Not final — wait and retry
            logger.info("[%s] waiting 5 seconds (elapsed=%dms)", step_name, elapsed)
            await page.wait_for_timeout(poll_ms)

            # Try refresh button
            try:
                refresh_btn = page.get_by_role("button", name=re.compile(r"refresh", re.I))
                if await refresh_btn.count() > 0:
                    await refresh_btn.first.click(timeout=5000)
                    await page.wait_for_timeout(1000)
            except Exception:  # noqa: BLE001
                pass

            # Re-apply search filter to ensure we're still on Websites page
            try:
                url_lower = page.url.lower()
                if "/cookies/websites" in url_lower:
                    sb = page.get_by_role("searchbox")
                    if await sb.count() == 0:
                        sb = page.locator("input[type='search']")
                    if await sb.count() > 0:
                        await sb.first.fill(normalized_domain)
                        await page.wait_for_timeout(500)
            except Exception:  # noqa: BLE001
                pass

            elapsed += poll_ms

        if scan_status == "Failed":
            screenshot = await browser_manager.screenshot_on_error(step_name)
            steps.append({"step": step_name, "status": "failed", "message": "Scan status is Failed",
                          "scan_status": "Failed"})
            debug = await _build_debug(page, step_name, screenshot=screenshot,
                                       possible_reason="OneTrust scan returned Failed status")
            if emit:
                await emit({"event": "step_failed", "step": step_name,
                            "message": "Scan status is Failed", "debug": {
                                "possible_reason": debug.get("possible_reason"),
                            }})
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
                "message": "Scan status did not become Completed within timeout",
                "scan_status": last_status,
            })
            debug = await _build_debug(
                page, step_name,
                possible_reason="Scan still pending after timeout",
                next_action=f"Increase ONETRUST_SCAN_TIMEOUT_MS (currently {scan_timeout_ms}ms) or wait and retry",
            )
            if emit:
                await emit({"event": "step_failed", "step": step_name,
                            "message": "Scan did not reach Completed within timeout", "debug": {
                                "possible_reason": debug.get("possible_reason"),
                                "next_action": debug.get("next_action"),
                            }})
            return {
                "status": "scan pending",
                "message": "Scan did not reach Completed status within timeout.",
                "input_url": url,
                "normalized_domain": normalized_domain,
                "matched_display_url": matched_display_url,
                "scan_status": last_status or "Pending",
                "current_url": page.url,
                "steps": steps,
                "debug": debug,
            }

        logger.info("[%s] current scan status: Completed", step_name)
        steps.append({"step": step_name, "status": "completed", "scan_status": "Completed"})
        if emit:
            await emit({"event": "step_completed", "step": step_name})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot)
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {
                "exception_type": debug.get("exception_type"),
            }})
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
    if emit:
        await emit({"event": "step_started", "step": step_name})
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

        steps.append({"step": step_name, "status": "completed"})
        if emit:
            await emit({"event": "step_completed", "step": step_name})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot,
                                   possible_reason="Could not click website row link to open details page")
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {
                "possible_reason": debug.get("possible_reason"), "exception_type": debug.get("exception_type"),
            }})
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
    # Calls wait_website_details_ready to ensure ALL markers are present.
    # ------------------------------------------------------------------ #
    step_name = "wait_website_details_page"
    logger.info("[%s] started | url=%s", step_name, page.url)
    if emit:
        await emit({"event": "step_started", "step": step_name})
    try:
        await wait_website_details_ready(page, normalized_domain)
        steps.append({"step": step_name, "status": "completed"})
        if emit:
            await emit({"event": "step_completed", "step": step_name})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot,
                                   possible_reason="Website details page did not fully load within 60s",
                                   next_action="Check if the row click navigated correctly and all markers are present")
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {
                "possible_reason": debug.get("possible_reason"), "next_action": debug.get("next_action"),
                "exception_type": debug.get("exception_type"),
            }})
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
    # Uses click_top_right_actions_menu to pick the topmost More button.
    # ------------------------------------------------------------------ #
    step_name = "open_actions_menu"
    logger.info("[%s] started | url=%s", step_name, page.url)
    if emit:
        await emit({"event": "step_started", "step": step_name})
    try:
        await click_top_right_actions_menu(page)
        steps.append({"step": step_name, "status": "completed"})
        if emit:
            await emit({"event": "step_completed", "step": step_name})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot,
                                   possible_reason="Three-dot actions menu near Publish/Publish test not found",
                                   next_action="Check if the Website details page has a More/... button near Publish")
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {
                "possible_reason": debug.get("possible_reason"), "next_action": debug.get("next_action"),
                "exception_type": debug.get("exception_type"),
            }})
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
    if emit:
        await emit({"event": "step_started", "step": step_name})
    try:
        copy_btn = page.get_by_text("Copy production scripts", exact=True)
        if await copy_btn.count() == 0:
            copy_btn = page.get_by_role("menuitem", name=re.compile(r"Copy production scripts", re.I))
        if await copy_btn.count() == 0:
            copy_btn = page.locator("text=Copy production scripts")
        await copy_btn.first.click(timeout=10000)
        steps.append({"step": step_name, "status": "completed"})
        if emit:
            await emit({"event": "step_completed", "step": step_name})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot,
                                   possible_reason="'Copy production scripts' menu item not found or not clickable")
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {
                "possible_reason": debug.get("possible_reason"), "exception_type": debug.get("exception_type"),
            }})
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
    # Polls until modal text contains BOTH otSDKStub.js AND data-domain-script.
    # ------------------------------------------------------------------ #
    step_name = "wait_production_scripts_modal"
    logger.info("[%s] started | url=%s", step_name, page.url)
    if emit:
        await emit({"event": "step_started", "step": step_name})
    try:
        poll_ms = 5000
        max_iterations = 6  # 30s total
        modal_ready = False

        for iteration in range(max_iterations):
            logger.info("[%s] checking modal readiness iteration=%d", step_name, iteration + 1)

            # Check structural markers first (fast)
            has_heading = False
            has_use_on_prod = False
            has_copy_scripts = False
            has_close = False

            try:
                has_heading = await page.locator("text=Production scripts").count() > 0
            except Exception:  # noqa: BLE001
                pass
            try:
                has_use_on_prod = await page.locator("text=Use on your production website").count() > 0
            except Exception:  # noqa: BLE001
                pass
            try:
                has_copy_scripts = await page.get_by_role("button", name=re.compile(r"Copy scripts", re.I)).count() > 0
            except Exception:  # noqa: BLE001
                pass
            try:
                has_close = await page.get_by_role("button", name=re.compile(r"^Close$", re.I)).count() > 0
            except Exception:  # noqa: BLE001
                pass

            # Check modal text for script content
            modal_text = await get_production_modal_text(page)
            has_sdk_stub = "otSDKStub.js" in modal_text
            has_data_domain = "data-domain-script" in modal_text

            logger.info(
                "[%s] markers: heading=%s use_on_prod=%s copy_scripts=%s close=%s sdk_stub=%s data_domain=%s",
                step_name, has_heading, has_use_on_prod, has_copy_scripts, has_close, has_sdk_stub, has_data_domain,
            )

            if has_heading and has_use_on_prod and has_copy_scripts and has_close and has_sdk_stub and has_data_domain:
                modal_ready = True
                break

            if iteration < max_iterations - 1:
                await page.wait_for_timeout(poll_ms)

        if not modal_ready:
            raise RuntimeError(
                "Production scripts modal did not contain all required content "
                "(otSDKStub.js + data-domain-script) within 30s"
            )

        steps.append({"step": step_name, "status": "completed"})
        if emit:
            await emit({"event": "step_completed", "step": step_name})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot,
                                   possible_reason="Production scripts modal did not open or script text not loaded")
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {
                "possible_reason": debug.get("possible_reason"), "exception_type": debug.get("exception_type"),
            }})
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
    if emit:
        await emit({"event": "step_started", "step": step_name})
    try:
        modal_text = await get_production_modal_text(page)
        script_snippet = modal_text[:2000] if modal_text else None

        # Primary extraction attempt
        match = re.search(r'data-domain-script=["\']([^"\']+)["\']', modal_text)

        # Fallback: normalize whitespace and try again (handles broken line-wraps)
        if not match:
            normalized_text = re.sub(r"\s+", " ", modal_text)
            match = re.search(r'data-domain-script=["\']([^"\']+)["\']', normalized_text)

        if match:
            data_domain_script = match.group(1)
            # Extract script_snippet: line containing otSDKStub.js
            for line in modal_text.splitlines():
                if "otSDKStub.js" in line:
                    script_snippet = line.strip()
                    break

            steps.append({"step": step_name, "status": "completed", "value": data_domain_script})
            if emit:
                await emit({"event": "step_completed", "step": step_name})
        else:
            # Rich failure response
            screenshot = await browser_manager.screenshot_on_error(step_name)
            markers = await _collect_visible_markers(page)
            try:
                page_title = await page.title()
            except Exception:  # noqa: BLE001
                page_title = None

            steps.append({"step": step_name, "status": "failed",
                          "message": "data-domain-script attribute not found in modal text"})
            if emit:
                await emit({"event": "step_failed", "step": step_name,
                            "message": "data-domain-script attribute not found in modal text", "debug": {
                                "possible_reason": "Production scripts modal opened but script text not readable",
                            }})
            return {
                "status": "failed",
                "message": "data-domain-script attribute not found in modal text",
                "input_url": url,
                "normalized_domain": normalized_domain,
                "matched_display_url": matched_display_url,
                "scan_status": scan_status,
                "current_url": page.url,
                "screenshot": screenshot,
                "steps": steps,
                "debug": {
                    "step": step_name,
                    "current_url": page.url,
                    "page_title": page_title,
                    "visible_markers": markers,
                    "modal_text_preview": modal_text[:1000] if modal_text else "",
                    "possible_reason": (
                        "Production scripts modal opened but script text was not available/readable to Playwright"
                    ),
                    "next_action": (
                        "Check screenshot — verify Production scripts modal is open and contains the script block"
                    ),
                    "screenshot": screenshot,
                    "failed_step": step_name,
                },
            }
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(page, step_name, exc=exc, screenshot=screenshot,
                                   possible_reason="data-domain-script not found in Production scripts modal",
                                   next_action="Check modal content manually")
        if emit:
            await emit({"event": "step_failed", "step": step_name, "message": str(exc), "debug": {
                "possible_reason": debug.get("possible_reason"), "exception_type": debug.get("exception_type"),
            }})
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
