from __future__ import annotations

import sys
import time


async def is_selector_visible(page, selector: str, timeout_ms: int = 2_000) -> bool:
    """Return True when the selector resolves to a visible element."""
    locator = page.locator(selector).first
    try:
        await locator.wait_for(state="visible", timeout=timeout_ms)
        return True
    except Exception:
        return False


async def wait_for_login_completion(
    page,
    expected_url_fragment: str,
    login_selector: str,
    timeout_ms: int,
    poll_ms: int = 500,
) -> bool:
    """Return True when redirected back to target domain.

    Primary success is return to expected URL fragment. If login UI state is also
    available, we prefer hidden login button but do not hard-fail on visibility,
    because some flows return to search while still showing login CTA.
    """
    deadline = time.monotonic() + (timeout_ms / 1000)
    seen_returned_url_with_visible_login = 0
    while time.monotonic() < deadline:
        try:
            url_ok = expected_url_fragment in (page.url or "")
        except Exception:
            url_ok = False

        if url_ok:
            login_visible = await is_selector_visible(page, login_selector, timeout_ms=500)
            if not login_visible:
                return True

            seen_returned_url_with_visible_login += 1
            if seen_returned_url_with_visible_login >= 3:
                return True

        await page.wait_for_timeout(poll_ms)

    return False


async def wait_with_progress(
    page,
    total_ms: int,
    label: str = "Waiting",
    width: int = 30,
    step_ms: int = 1_000,
    stream=None,
) -> None:
    """Wait for total_ms while rendering a one-line terminal progress bar."""
    if total_ms <= 0:
        return

    if stream is None:
        stream = sys.stdout

    elapsed = 0
    while elapsed < total_ms:
        remaining = total_ms - elapsed
        current_step = step_ms if remaining > step_ms else remaining
        await page.wait_for_timeout(current_step)
        elapsed += current_step

        ratio = elapsed / total_ms
        filled = int(width * ratio)
        empty = width - filled
        seconds_left = max(0, int((total_ms - elapsed) / 1000))
        stream.write(
            f"\r{label} [{'#' * filled}{'-' * empty}] {int(ratio * 100):3d}% ({seconds_left:3d}s left)"
        )
        stream.flush()

    stream.write("\n")
    stream.flush()
