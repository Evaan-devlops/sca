import asyncio
import datetime
import re
from collections.abc import Awaitable, Callable

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import logging

from app.core.config import settings
from app.features.onetrust.browser import browser_manager

logger = logging.getLogger(__name__)


class _IamLoginTimeoutError(RuntimeError):
    """Raised when the Digital On Demand IAM manual login times out."""

    def __init__(
        self,
        message: str,
        screenshot: str | None = None,
        failed_step: str | None = None,
        next_action: str | None = None,
        visible_markers: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.screenshot = screenshot
        self.failed_step = failed_step
        self.next_action = next_action
        self.visible_markers = visible_markers or []


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


_ONETRUST_AUTH_MARKERS = (
    "/cookies/websites",
    "/welcome",
)
_ONETRUST_AUTH_TEXT_MARKERS = ("Sandbox Environment", "Cookie Consent", "Websites")


async def detect_digital_on_demand_login(page: Page) -> bool:
    """Return True if the Digital On Demand IAM login page is currently visible."""
    iam_markers = [
        "DIGITAL ON DEMAND",
        "IAM: Sign In",
        "ACCEPT & CONNECT",
    ]
    try:
        body_text = await page.inner_text("body")
        return any(marker in body_text for marker in iam_markers)
    except Exception:  # noqa: BLE001
        return False


async def is_sso_or_manual_page(page: Page) -> bool:
    """Return True if page is any SSO/PingID/IAM intermediate login page (keep-waiting state)."""
    url_lower = page.url.lower()
    sso_url_markers = (
        "devfederate", "pingidentity", "/idp/", "sso.ping",
        "processing", "pfizeridentity", "auth/login",
    )
    if any(m in url_lower for m in sso_url_markers):
        return True
    try:
        body = await page.inner_text("body")
        sso_body_markers = (
            "Digital On Demand", "IAM: Sign In", "ACCEPT & CONNECT",
            "PingID", "Sign On",
        )
        return any(m in body for m in sso_body_markers)
    except Exception:  # noqa: BLE001
        return False


async def handle_digital_on_demand_manual_login(
    page: Page,
    steps: list[dict],
    emit: Callable[[dict], Awaitable[None]] | None = None,
) -> None:
    """
    Handle the Digital On Demand / IAM login page by:
    1. Detecting its presence (logged by caller before this is called).
    2. Optionally prefilling the username from settings.
    3. Waiting up to onetrust_manual_login_timeout_ms for the user to
       manually enter their password and click ACCEPT & CONNECT.

    Raises RuntimeError on timeout.
    NEVER fills or touches the password field.
    """
    steps.append({
        "step": "detect_digital_on_demand_login",
        "status": "completed",
        "message": "Digital On Demand IAM login page detected",
    })

    # Optionally prefill username
    if settings.onetrust_iam_username:
        input_loc = None
        username_candidates = [
            page.get_by_label(re.compile(r"username", re.I)),
            page.locator("input[name*='user' i]"),
            page.locator("input[type='text']").first,
        ]
        for candidate in username_candidates:
            try:
                if await candidate.count() > 0:
                    input_loc = candidate
                    break
            except Exception:  # noqa: BLE001
                pass

        if input_loc is not None:
            try:
                current_val = await input_loc.first.input_value()
                if not current_val:
                    await input_loc.first.fill(settings.onetrust_iam_username)
                    logger.info("Prefilled IAM username field")
                steps.append({"step": "prefill_iam_username", "status": "completed"})
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not prefill IAM username: %s", exc)
                steps.append({"step": "prefill_iam_username", "status": "skipped", "message": str(exc)})

    # Notify caller that we are waiting
    steps.append({
        "step": "wait_for_manual_iam_login",
        "status": "started",
        "message": "Waiting for user to manually enter IAM password and click ACCEPT & CONNECT",
    })
    if emit:
        await emit({
            "event": "step_started",
            "step": "wait_for_manual_iam_login",
            "message": "Enter IAM password manually and click ACCEPT & CONNECT in the opened browser",
        })

    timeout_ms = settings.onetrust_manual_login_timeout_ms
    poll_interval_s = 5
    elapsed_ms = 0

    while elapsed_ms < timeout_ms:
        url_lower = page.url.lower()

        # Check if we've reached the OneTrust dashboard
        try:
            body_text = await page.inner_text("body")
        except Exception:  # noqa: BLE001
            body_text = ""

        is_authenticated = (
            any(m in url_lower for m in _ONETRUST_AUTH_MARKERS)
            or any(m in body_text for m in _ONETRUST_AUTH_TEXT_MARKERS)
        )

        if is_authenticated:
            logger.info("IAM login completed — OneTrust dashboard detected: %s", page.url)
            # Update the step status
            for step in reversed(steps):
                if step.get("step") == "wait_for_manual_iam_login":
                    step["status"] = "completed"
                    step["message"] = "IAM login completed"
                    break
            return

        logger.debug(
            "IAM manual login wait: %dms elapsed, url=%s",
            elapsed_ms, page.url,
        )
        await asyncio.sleep(poll_interval_s)
        elapsed_ms += poll_interval_s * 1000

    # Timeout — save screenshot and raise
    _screenshot = await browser_manager.screenshot_on_error("manual_iam_login_timeout")
    raise _IamLoginTimeoutError(
        "Digital On Demand IAM login did not complete within timeout. "
        "Complete login manually in the opened browser, then call /auth/login again.",
        screenshot=_screenshot,
    )


async def wait_for_auth_completion(
    page: Page,
    steps: list[dict],
    emit: Callable[[dict], Awaitable[None]] | None = None,
) -> None:
    """
    Poll until OneTrust authenticated page is reached or timeout.
    Treats all SSO/PingID/IAM intermediate pages as keep-waiting states.
    Raises _IamLoginTimeoutError on timeout.
    """
    SUCCESS_URL_MARKERS = ("/welcome", "/cookies/websites")
    SUCCESS_BODY_MARKERS = ("Sandbox Environment", "Cookie Consent", "Websites")

    timeout_ms = settings.onetrust_manual_login_timeout_ms
    poll_interval_s = 5
    log_every_n = 3  # log url+markers every 15s (every 3rd poll)
    elapsed_ms = 0
    poll_count = 0

    if emit:
        await emit({
            "event": "step_started",
            "step": "wait_for_sso_completion",
            "message": (
                "Waiting for SSO/login to complete. "
                "Complete any manual steps in the opened browser."
            ),
        })

    # One-time username prefill on first poll if on SSO/IAM page
    if settings.onetrust_iam_username and await is_sso_or_manual_page(page):
        try:
            input_loc = page.get_by_label(re.compile(r"username", re.I))
            if await input_loc.count() == 0:
                input_loc = page.locator("input[name*='user' i]")
            if await input_loc.count() > 0:
                val = await input_loc.first.input_value()
                if not val:
                    await input_loc.first.fill(settings.onetrust_iam_username)
                    steps.append({"step": "prefill_iam_username", "status": "completed"})
                    logger.info("Prefilled IAM username field")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not prefill IAM username: %s", exc)

    while elapsed_ms < timeout_ms:
        url_lower = page.url.lower()

        # Check success
        try:
            body = await page.inner_text("body")
        except Exception:  # noqa: BLE001
            body = ""

        if any(m in url_lower for m in SUCCESS_URL_MARKERS) or \
                any(m in body for m in SUCCESS_BODY_MARKERS):
            steps.append({"step": "wait_for_sso_completion", "status": "completed"})
            if emit:
                await emit({"event": "step_completed", "step": "wait_for_sso_completion"})
            return  # success

        # Log every 15s
        if poll_count % log_every_n == 0:
            visible = [
                m for m in list(SUCCESS_BODY_MARKERS) + [
                    "PingID", "Sign On", "Digital On Demand"
                ]
                if m in body
            ]
            logger.info(
                "wait_for_auth_completion: elapsed=%dms url=%s visible=%s",
                elapsed_ms, page.url, visible,
            )

        await page.wait_for_timeout(poll_interval_s * 1000)
        elapsed_ms += poll_interval_s * 1000
        poll_count += 1

    # Timeout
    screenshot = await browser_manager.screenshot_on_error("wait_for_auth_completion_timeout")
    try:
        body = await page.inner_text("body")
        visible_markers = [
            m for m in (
                "PingID", "Sign On", "Digital On Demand", "IAM: Sign In",
                "ACCEPT & CONNECT", "devfederate", "SSO",
            )
            if m in body or m.lower() in page.url.lower()
        ]
    except Exception:  # noqa: BLE001
        visible_markers = []

    steps.append({
        "step": "wait_for_sso_completion",
        "status": "failed",
        "message": "SSO/login did not complete within timeout",
    })
    if emit:
        await emit({
            "event": "step_failed",
            "step": "wait_for_sso_completion",
            "message": "SSO/login did not complete. Complete manually in the opened browser.",
        })

    raise _IamLoginTimeoutError(
        "SSO/PingID login did not complete within timeout. Complete login manually in the opened browser, "
        "then call /auth/login or /auth/status again.",
        screenshot=screenshot,
        failed_step="wait_for_sso_completion",
        next_action=(
            "Complete SSO manually in the opened browser, then call /auth/status. "
            "Only continue when status is logged in."
        ),
        visible_markers=visible_markers,
    )


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


async def login_onetrust(
    emit: Callable[[dict], Awaitable[None]] | None = None,
) -> dict:
    """Orchestrate the full OneTrust login flow. Returns a status dict."""
    page = await browser_manager.get_page()
    email = settings.onetrust_email
    steps: list[dict] = []

    if not email:
        step_name = "load_email_from_config"
        steps.append({
            "step": step_name,
            "status": "failed",
            "message": "ONETRUST_EMAIL is missing",
        })
        return {
            "status": "configuration error",
            "message": "ONETRUST_EMAIL is missing. Add it to backend/.env.",
            "current_url": page.url,
            "failed_step": step_name,
            "steps": steps,
            "debug": {
                "possible_reason": (
                    "backend/.env is missing ONETRUST_EMAIL or .env was not copied from .env.example"
                ),
                "next_action": "Create backend/.env and set ONETRUST_EMAIL",
            },
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

    # Short pause to allow page to respond after email + Next click
    await asyncio.sleep(2.5)

    # Unified SSO/IAM/PingID wait — treats all intermediate pages as keep-waiting states
    try:
        await wait_for_auth_completion(page, steps, emit=emit)
        # Fall through to post-login handling below
    except _IamLoginTimeoutError as e:
        return {
            "status": "manual login required",
            "message": str(e),
            "failed_step": e.failed_step,
            "current_url": page.url,
            "screenshot": e.screenshot,
            "steps": steps,
            "debug": {
                "possible_reason": "SSO/PingID did not finish or needs manual approval",
                "next_action": e.next_action,
                "visible_markers": e.visible_markers,
            },
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
