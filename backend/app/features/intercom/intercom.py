import asyncio
import logging
import re
from typing import Any, Callable

from playwright.async_api import Page

from app.core.config import settings
from app.features.onetrust.browser import browser_manager
from app.features.onetrust.websites import add_app_flow

logger = logging.getLogger(__name__)


async def process_ticket_flow(ticket_number: str, emit: Callable[[dict], Any] | None = None) -> dict:
    """Automate Intercom: open inbox, click SSO, open search, input ticket, wait for results."""
    page: Page = await browser_manager.get_page()
    steps: list[dict] = []

    async def _emit(event: dict) -> None:
        steps.append(event if event.get("step") else {"step": event.get("event", "event")})
        if emit:
            await emit({"event": "step_event", **event})

    # Bring browser to front
    await page.bring_to_front()

    # Step: open intercom URL
    step = "open_intercom_url"
    try:
        await _emit({"step": step, "status": "started", "message": f"Navigating to {settings.intercom_login_url}"})
        await page.goto(settings.intercom_login_url, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
        await _emit({"step": step, "status": "completed", "current_url": page.url})
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s failed: %s", step, exc)
        screenshot = await browser_manager.screenshot_on_error(step)
        await _emit({"step": step, "status": "failed", "message": str(exc), "screenshot": screenshot})
        return {"status": "error", "failed_step": step, "steps": steps, "current_url": page.url}

    # Step: click Sign in with SAML SSO on Intercom login page
    step = "click_sso_button"
    try:
        await _emit({"step": step, "status": "started", "message": "Clicking Intercom SAML SSO link"})
        sso_locators = [
            page.get_by_role("link", name=re.compile(r"Sign in with SAML SSO", re.I)),
            page.get_by_role("button", name=re.compile(r"Sign in with SAML SSO", re.I)),
            page.get_by_text("Sign in with SAML SSO", exact=True),
            page.locator("a:has-text('Sign in with SAML SSO')"),
            page.locator("button:has-text('Sign in with SAML SSO')"),
        ]
        clicked = False
        for loc in sso_locators:
            try:
                if await loc.count() > 0:
                    await loc.first.click()
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            # fallback: try any text link/button containing 'SAML'
            try:
                loc = page.locator("text=Sign in with SAML")
                if await loc.count() > 0:
                    await loc.first.click()
                    clicked = True
            except Exception:
                pass

        if not clicked:
            raise RuntimeError("Could not locate Intercom SAML SSO link/button")

        try:
            await page.wait_for_load_state("networkidle", timeout=settings.intercom_timeout_ms)
        except Exception:
            pass

        await _emit({"step": step, "status": "completed", "current_url": page.url})
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s failed: %s", step, exc)
        screenshot = await browser_manager.screenshot_on_error(step)
        await _emit({"step": step, "status": "failed", "message": str(exc), "screenshot": screenshot})
        return {"status": "error", "failed_step": step, "steps": steps, "current_url": page.url}

    # Step: fill work email on SAML page
    step = "fill_saml_email"
    try:
        await _emit({"step": step, "status": "started", "message": "Filling work email on Intercom SAML page"})
        email = settings.onetrust_email
        if not email:
            raise RuntimeError("ONETRUST_EMAIL is required for Intercom SAML login")

        email_input = None
        email_candidates = [
            page.get_by_label(re.compile(r"Work email", re.I)),
            page.get_by_placeholder(re.compile(r"email", re.I)),
            page.locator("input[type='email']"),
            page.locator("input[name*='email' i]"),
        ]
        for candidate in email_candidates:
            try:
                if await candidate.count() > 0:
                    email_input = candidate.first
                    break
            except Exception:
                continue

        if email_input is None:
            raise RuntimeError("Could not locate work email input on SAML page")

        await email_input.fill(email)

        submit_locators = [
            page.get_by_role("button", name=re.compile(r"Sign in with SAML SSO", re.I)),
            page.get_by_text("Sign in with SAML SSO", exact=True),
            page.locator("button:has-text('Sign in with SAML SSO')"),
        ]
        submitted = False
        for loc in submit_locators:
            try:
                if await loc.count() > 0:
                    await loc.first.click()
                    submitted = True
                    break
            except Exception:
                continue

        if not submitted:
            raise RuntimeError("Could not locate SAML SSO submit button")

        try:
            await page.wait_for_load_state("networkidle", timeout=settings.intercom_timeout_ms)
        except Exception:
            pass

        await _emit({"step": step, "status": "completed", "current_url": page.url})
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s failed: %s", step, exc)
        screenshot = await browser_manager.screenshot_on_error(step)
        await _emit({"step": step, "status": "failed", "message": str(exc), "screenshot": screenshot})
        return {"status": "error", "failed_step": step, "steps": steps, "current_url": page.url}

    # Step: wait for inbox/search UI to appear
    step = "wait_for_inbox_ui"
    try:
        await _emit({"step": step, "status": "started", "message": "Waiting for Intercom inbox UI"})
        # wait for either the left "Inbox" label or a search input to appear
        try:
            await page.wait_for_selector("text=Inbox", timeout=settings.intercom_timeout_ms)
        except Exception:
            # tolerate if label not present; wait for search input instead
            pass

        # Wait for any of the search input selectors
        search_input = None
        search_selectors = [
            "input[placeholder*='Search' i]",
            "input[type='search']",
            "input[placeholder*='search']",
        ]
        for sel in search_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    await loc.wait_for(state="visible", timeout=2000)
                    search_input = loc
                    break
            except Exception:
                continue

        if search_input is None:
            # try role-based searchbox
            try:
                sb = page.get_by_role("searchbox")
                if await sb.count() > 0:
                    search_input = sb.first
            except Exception:
                pass

        if search_input is None:
            raise RuntimeError("Search input not found")

        await _emit({"step": step, "status": "completed", "message": "Inbox UI available"})
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s failed: %s", step, exc)
        screenshot = await browser_manager.screenshot_on_error(step)
        await _emit({"step": step, "status": "failed", "message": str(exc), "screenshot": screenshot})
        return {"status": "error", "failed_step": step, "steps": steps, "current_url": page.url}

    # Step: focus search (click search area) — attempt to click 'Search' label if present
    step = "activate_search"
    try:
        await _emit({"step": step, "status": "started", "message": "Activating search box"})
        try:
            search_label = page.get_by_text("Search", exact=False)
            if await search_label.count() > 0:
                await search_label.first.click()
        except Exception:
            # ignore
            pass

        # ensure search_input is focused
        try:
            await search_input.click()
        except Exception:
            pass

        await _emit({"step": step, "status": "completed"})
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s failed: %s", step, exc)
        screenshot = await browser_manager.screenshot_on_error(step)
        await _emit({"step": step, "status": "failed", "message": str(exc), "screenshot": screenshot})
        return {"status": "error", "failed_step": step, "steps": steps, "current_url": page.url}

    # Step: fill ticket number and press Enter
    step = "fill_ticket_and_search"
    try:
        await _emit({"step": step, "status": "started", "message": f"Searching for ticket {ticket_number}"})
        # fill
        await search_input.fill(ticket_number)
        # small pause
        await asyncio.sleep(0.2)
        await search_input.press("Enter")
        await _emit({"step": step, "status": "completed"})
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s failed: %s", step, exc)
        screenshot = await browser_manager.screenshot_on_error(step)
        await _emit({"step": step, "status": "failed", "message": str(exc), "screenshot": screenshot})
        return {"status": "error", "failed_step": step, "steps": steps, "current_url": page.url}

    # Step: wait for search results
    step = "wait_for_search_results"
    try:
        await _emit({"step": step, "status": "started", "message": "Waiting for search results"})
        try:
            await page.wait_for_selector(f"text={ticket_number}", timeout=settings.intercom_timeout_ms)
        except Exception:
            # fallback: wait for 'result found' text or list items
            try:
                await page.wait_for_selector("text=result found", timeout=settings.intercom_timeout_ms)
            except Exception:
                # final fallback: short sleep then continue
                await asyncio.sleep(2)

        await _emit({"step": step, "status": "completed", "current_url": page.url})
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s failed: %s", step, exc)
        screenshot = await browser_manager.screenshot_on_error(step)
        await _emit({"step": step, "status": "failed", "message": str(exc), "screenshot": screenshot})
        return {"status": "error", "failed_step": step, "steps": steps, "current_url": page.url}

    # ------------------------------------------------------------------ #
    # Step: click the search result preview to open conversation details
    # ------------------------------------------------------------------ #
    step = "click_search_result"
    try:
        await _emit({"step": step, "status": "started", "message": "Clicking search result preview"})

        # Try to click the preview cell or the row containing ticket_number
        clicked = False
        try:
            # Prefer clicking the preview text cell
            preview_loc = page.locator(f"text={ticket_number}").first
            if await preview_loc.count() > 0:
                await preview_loc.click()
                clicked = True
        except Exception:
            clicked = False

        if not clicked:
            # Fallback: click a row that contains the ticket id
            try:
                row = page.locator(f"xpath=//div[contains(., '{ticket_number}')]")
                if await row.count() > 0:
                    await row.first.click()
                    clicked = True
            except Exception:
                clicked = False

        if not clicked:
            raise RuntimeError("Could not click the search result")

        # Wait for details panel to load — look for a 'Details' heading or conversation body
        try:
            await page.wait_for_selector("text=Details", timeout=settings.intercom_timeout_ms)
        except Exception:
            # fallback: wait for some conversation attributes or the conversation text to appear
            try:
                await page.wait_for_selector("text=Conversation attributes", timeout=5000)
            except Exception:
                await page.wait_for_timeout(1500)

        await _emit({"step": step, "status": "completed", "current_url": page.url})
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s failed: %s", step, exc)
        screenshot = await browser_manager.screenshot_on_error(step)
        await _emit({"step": step, "status": "failed", "message": str(exc), "screenshot": screenshot})
        return {"status": "error", "failed_step": step, "steps": steps, "current_url": page.url}

    # ------------------------------------------------------------------ #
    # Step: extract URL/domain from the conversation text
    # ------------------------------------------------------------------ #
    step = "extract_url_from_ticket"
    try:
        await _emit({"step": step, "status": "started", "message": "Extracting URL from ticket text"})

        # Collect visible text from page and frames
        texts = []
        try:
            texts.append(await page.inner_text("body"))
        except Exception:
            pass
        for f in page.frames:
            try:
                texts.append(await f.inner_text("body"))
            except Exception:
                pass

        combined = "\n".join(t for t in texts if t)

        # Regex to capture common domain/url forms
        url_candidates = re.findall(r"https?://[^\s,)+]+|www\.[^\s,)+]+|[A-Za-z0-9.-]+\.[A-Za-z]{2,}", combined)
        chosen = None
        if url_candidates:
            # Prefer one containing a dot and not starting with ticket id
            for c in url_candidates:
                s = c.strip().strip('.,)')
                # skip obvious false positives
                if ticket_number in s:
                    continue
                # ignore short TLD-like tokens
                if len(s) < 4:
                    continue
                chosen = s
                break

        if not chosen:
            raise RuntimeError("No URL/domain found in ticket text")

        await _emit({"step": step, "status": "completed", "value": chosen})
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s failed: %s", step, exc)
        screenshot = await browser_manager.screenshot_on_error(step)
        await _emit({"step": step, "status": "failed", "message": str(exc), "screenshot": screenshot})
        return {"status": "error", "failed_step": step, "steps": steps, "current_url": page.url}

    # ------------------------------------------------------------------ #
    # Step: start OneTrust add_app_flow using extracted URL
    # ------------------------------------------------------------------ #
    step = "start_onetrust_add_app"
    try:
        await _emit({"step": step, "status": "started", "message": f"Calling OneTrust add_app_flow for {chosen}"})
        # Reuse existing add_app_flow which handles login checks and SSO waits
        onetrust_result = await add_app_flow(chosen, emit=emit)
        await _emit({"step": step, "status": "completed", "result": onetrust_result})
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s failed: %s", step, exc)
        screenshot = await browser_manager.screenshot_on_error(step)
        await _emit({"step": step, "status": "failed", "message": str(exc), "screenshot": screenshot})
        return {"status": "error", "failed_step": step, "steps": steps, "current_url": page.url}

    return {"status": "ok", "message": "Intercom search completed and OneTrust flow started", "input_ticket": ticket_number, "extracted_url": chosen, "onetrust": onetrust_result, "current_url": page.url, "steps": steps}
