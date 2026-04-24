from __future__ import annotations

import sys
import time
import shutil


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

    # Use in-place updates only for interactive terminals.
    # On non-interactive streams (logs, captured output), emit just a final line.
    is_tty = bool(getattr(stream, "isatty", lambda: False)())

    # Keep the rendered line within terminal width to prevent line wrapping,
    # which makes carriage-return updates look like many separate lines.
    render_width = width
    if is_tty:
        cols = shutil.get_terminal_size(fallback=(100, 20)).columns
        # Reserve room for label, framing, percent text, and a spacer.
        reserved = len(label) + len(" [] 100%")
        render_width = max(10, min(width, cols - reserved - 1))

    elapsed = 0
    last_line_len = 0
    while elapsed < total_ms:
        remaining = total_ms - elapsed
        current_step = step_ms if remaining > step_ms else remaining
        await page.wait_for_timeout(current_step)
        elapsed += current_step

        ratio = elapsed / total_ms
        if is_tty:
            filled = int(render_width * ratio)
            empty = render_width - filled
            line = f"{label} [{'#' * filled}{'-' * empty}] {int(ratio * 100):3d}%"
            pad = " " * max(0, last_line_len - len(line))
            stream.write(f"\r{line}{pad}")
            stream.flush()
            last_line_len = len(line)

    if not is_tty:
        stream.write(f"{label} [{'#' * render_width}] 100%\n")
    else:
        stream.write("\n")
    stream.flush()
