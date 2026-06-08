import datetime
import re

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import logging

from app.core.config import settings
from app.features.onetrust.browser import browser_manager

logger = logging.getLogger(__name__)

_SUCCESS_URL_PATTERNS = (
    "onetrust.com/home",
    "onetrust.com/welcome",
    "onetrust.com/cookies",
    "onetrust.com/privacy",
    "onetrust.com/assessments",
)

_SUCCESS_TEXTS = ("Sandbox Environment", "My apps", "Cookie Consent")


def _mask_email(email: str) -> str:
    """Mask email for safe debug output: first char + *** + @domain."""
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    masked = local[0] + "*" * max(1, len(local) - 1) if local else "***"
    return f"{masked}@{domain}"


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


async def is_logged_in(page: Page) -> bool:
    """Return True if the current page indicates an active OneTrust session."""
    url_lower = page.url.lower()
    if any(pattern in url_lower for pattern in _SUCCESS_URL_PATTERNS):
        return True
    try:
        body_text = await page.inner_text("body")
        if any(text in body_text for text in _SUCCESS_TEXTS):
            return True
    except Exception:  # noqa: BLE001
        return False
    return False


async def fill_email_or_confirm_prefilled_email(page: Page, email: str) -> dict:
    """Navigate to the login URL, check/fill the email field, and click Next."""
    await page.goto(settings.onetrust_login_url, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")

    email_input = None
    candidates = [
        page.get_by_label("Email address"),
        page.locator("input[type='email']"),
        page.locator("input[placeholder*='email' i]"),
    ]
    for candidate in candidates:
        if await candidate.count() > 0:
            email_input = candidate
            break

    if email_input is None:
        raise RuntimeError("Could not locate the email input field on the login page")

    current_val = await email_input.first.input_value()

    if not current_val:
        await email_input.first.fill(email)
        email_action = "filled_from_env"
        email_prefilled = False
        logger.info("Filled email field for %s", _mask_email(email))
    elif current_val.lower() == email.lower():
        email_action = "kept_existing"
        email_prefilled = True
        logger.info("Email field already contains matching value for %s — keeping", _mask_email(email))
    else:
        await email_input.first.clear()
        await email_input.first.fill(email)
        email_action = "replaced_existing"
        email_prefilled = True
        logger.info("Replaced existing email with %s", _mask_email(email))

    next_locator = None
    next_candidates = [
        page.get_by_role("button", name=re.compile(r"Next", re.I)),
        page.get_by_text("Next", exact=True),
    ]
    for candidate in next_candidates:
        if await candidate.count() > 0:
            next_locator = candidate
            break

    if next_locator is None:
        raise RuntimeError("Could not locate the Next button on the login page")

    await next_locator.click()
    logger.info("Clicked Next button")

    return {"email_prefilled": email_prefilled, "email_action": email_action}


async def wait_for_sso_completion(page: Page) -> bool:
    """Poll until the page lands on a known success URL/text or the timeout elapses."""
    timeout_ms = settings.playwright_timeout_ms
    poll_interval_ms = 2000
    elapsed = 0

    while elapsed < timeout_ms:
        logger.debug("SSO wait: %dms elapsed, url=%s", elapsed, page.url)

        url_lower = page.url.lower()
        if any(pattern in url_lower for pattern in _SUCCESS_URL_PATTERNS):
            logger.info("SSO completed — success URL detected: %s", page.url)
            return True

        try:
            body_text = await page.inner_text("body")
            if any(text in body_text for text in _SUCCESS_TEXTS):
                logger.info("SSO completed — success text detected on %s", page.url)
                return True
        except Exception:  # noqa: BLE001
            pass

        try:
            await page.wait_for_url(
                re.compile("|".join(re.escape(p) for p in _SUCCESS_URL_PATTERNS)),
                timeout=poll_interval_ms,
            )
            logger.info("SSO completed — wait_for_url matched: %s", page.url)
            return True
        except PlaywrightTimeoutError:
            elapsed += poll_interval_ms
            logger.debug("SSO poll interval elapsed, total elapsed: %dms", elapsed)

    return False


async def handle_post_login_modals(page: Page) -> list[str]:
    """Dismiss known post-login modals. Return list of handled modal names."""
    handled: list[str] = []

    for _ in range(3):
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except PlaywrightTimeoutError:
            pass

        body_text = await page.inner_text("body")

        if "Product tutorials and improvements" in body_text:
            logger.info("Handling Product tutorials modal")
            modal_candidates = [
                page.get_by_role("button", name=re.compile(r"No thanks", re.I)),
                page.get_by_text("No thanks, remove", exact=False),
                page.get_by_role("button", name=re.compile(r"Continue", re.I)),
                page.locator("button[aria-label*='close' i]"),
            ]
            clicked = False
            for locator in modal_candidates:
                try:
                    await locator.click(timeout=3000)
                    clicked = True
                    break
                except Exception:  # noqa: BLE001
                    continue
            if clicked:
                handled.append("product tutorials and improvements")
                continue

        elif "Scheduled maintenance" in body_text:
            logger.info("Handling Scheduled maintenance modal")
            modal_candidates = [
                page.get_by_role("button", name=re.compile(r"Continue", re.I)),
                page.locator("button[aria-label*='close' i]"),
            ]
            clicked = False
            for locator in modal_candidates:
                try:
                    await locator.click(timeout=3000)
                    clicked = True
                    break
                except Exception:  # noqa: BLE001
                    continue
            if clicked:
                handled.append("scheduled maintenance")
                continue

        else:
            break

    return handled


async def login_onetrust() -> dict:
    """Orchestrate the full OneTrust login flow. Returns a status dict."""
    page = await browser_manager.get_page()
    email = settings.onetrust_email
    steps: list[dict] = []

    if not email:
        return {
            "status": "error",
            "message": "ONETRUST_EMAIL is not set in environment",
            "current_url": page.url,
        }

    if await is_logged_in(page):
        logger.info("Already logged in: %s", page.url)
        steps.append({"step": "open_login_page", "status": "skipped", "message": "Already logged in"})
        return {
            "status": "logged in",
            "message": "Already logged in to OneTrust sandbox",
            "current_url": page.url,
            "handled_modals": [],
            "steps": steps,
        }

    # Step: open_login_page
    step_name = "open_login_page"
    try:
        await page.goto(settings.onetrust_login_url, wait_until="domcontentloaded")
        logger.info("[%s] completed | url=%s", step_name, page.url)
        steps.append({"step": step_name, "status": "completed"})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(
            page, step_name, exc=exc, screenshot=screenshot,
            possible_reason="Could not navigate to login URL",
            next_action="Check ONETRUST_LOGIN_URL in .env and network connectivity",
        )
        return {
            "status": "error",
            "message": str(exc),
            "current_url": page.url,
            "screenshot": screenshot,
            "failed_step": step_name,
            "steps": steps,
            "debug": debug,
        }

    # Step: fill_email_or_confirm_prefilled_email
    step_name = "fill_email_or_confirm_prefilled_email"
    try:
        await fill_email_or_confirm_prefilled_email(page, email)
        logger.info("[%s] completed | url=%s", step_name, page.url)
        steps.append({"step": step_name, "status": "completed"})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(
            page, step_name, exc=exc, screenshot=screenshot,
            possible_reason="Email input or Next button not found on login page",
            next_action="Check login page loaded correctly and selectors are valid",
        )
        return {
            "status": "error",
            "message": str(exc),
            "current_url": page.url,
            "screenshot": screenshot,
            "failed_step": step_name,
            "steps": steps,
            "debug": debug,
        }

    # Step: wait_for_sso_completion
    step_name = "wait_for_sso_completion"
    try:
        sso_ok = await wait_for_sso_completion(page)

        if not sso_ok:
            screenshot = await browser_manager.screenshot_on_error("sso_timeout")
            steps.append({"step": step_name, "status": "failed", "message": "SSO timed out"})
            sso_exc = TimeoutError("SSO did not complete within timeout")
            debug = await _build_debug(
                page, step_name, exc=sso_exc, screenshot=screenshot,
                possible_reason="SSO/PingID did not finish or needs manual approval",
                next_action="Complete SSO manually in the opened browser, then call /auth/login again",
            )
            return {
                "status": "SSO issue",
                "message": (
                    "SSO did not complete within timeout. "
                    "Please complete SSO manually in the opened browser, then retry."
                ),
                "current_url": page.url,
                "screenshot": screenshot,
                "failed_step": step_name,
                "steps": steps,
                "debug": debug,
            }

        logger.info("[%s] completed | url=%s", step_name, page.url)
        steps.append({"step": step_name, "status": "completed"})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(
            page, step_name, exc=exc, screenshot=screenshot,
            possible_reason="Unexpected error during SSO wait",
            next_action="Check browser state and retry /auth/login",
        )
        return {
            "status": "error",
            "message": str(exc),
            "current_url": page.url,
            "screenshot": screenshot,
            "failed_step": step_name,
            "steps": steps,
            "debug": debug,
        }

    # Step: handle_post_login_modals
    step_name = "handle_post_login_modals"
    try:
        handled_modals = await handle_post_login_modals(page)
        logger.info("[%s] completed. Handled modals: %s | url=%s", step_name, handled_modals, page.url)
        steps.append({"step": step_name, "status": "completed"})
    except Exception as exc:
        logger.exception("[%s] failed: %s", step_name, exc)
        screenshot = await browser_manager.screenshot_on_error(step_name)
        steps.append({"step": step_name, "status": "failed", "message": str(exc)})
        debug = await _build_debug(
            page, step_name, exc=exc, screenshot=screenshot,
            possible_reason="Unexpected error while handling post-login modals",
            next_action="Check browser state and retry /auth/login",
        )
        return {
            "status": "error",
            "message": str(exc),
            "current_url": page.url,
            "screenshot": screenshot,
            "failed_step": step_name,
            "steps": steps,
            "debug": debug,
        }

    logger.info("Login successful.")
    return {
        "status": "logged in",
        "message": "OneTrust login completed and sandbox page reached",
        "current_url": page.url,
        "handled_modals": handled_modals,
        "steps": steps,
    }
