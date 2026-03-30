import asyncio
import io
from unittest.mock import AsyncMock

from core.login_utils import is_selector_visible
from core.login_utils import wait_with_progress


class _DummyLocator:
    def __init__(self, should_be_visible: bool) -> None:
        self.wait_for = AsyncMock()
        if not should_be_visible:
            self.wait_for.side_effect = RuntimeError("not visible")


class _DummyPage:
    def __init__(self, should_be_visible: bool) -> None:
        self._locator = _DummyLocator(should_be_visible)
        self._locator.first = self._locator
        self.url = "https://example.com/login"
        self._ticks = 0

    def locator(self, _selector: str):
        return self._locator

    async def wait_for_timeout(self, _ms: int):
        self._ticks += 1


class _DummyPageCompletes(_DummyPage):
    async def wait_for_timeout(self, _ms: int):
        self._ticks += 1
        if self._ticks >= 1:
            self.url = "https://www.mycareersfuture.gov.sg/search?page=0"
            self._locator.wait_for.side_effect = RuntimeError("not visible")


class _DummyPageReturnsWithLoginVisible(_DummyPage):
    async def wait_for_timeout(self, _ms: int):
        self._ticks += 1
        if self._ticks >= 1:
            self.url = "https://www.mycareersfuture.gov.sg/search?page=0"


def test_is_login_button_visible_true() -> None:
    page = _DummyPage(should_be_visible=True)
    assert asyncio.run(is_selector_visible(page, "button[data-testid='navbar-login']")) is True


def test_is_login_button_visible_false() -> None:
    page = _DummyPage(should_be_visible=False)
    assert asyncio.run(is_selector_visible(page, "button[data-testid='navbar-login']")) is False


def test_wait_with_progress_renders_and_completes() -> None:
    page = _DummyPage(should_be_visible=True)
    out = io.StringIO()
    asyncio.run(
        wait_with_progress(
            page=page,
            total_ms=250,
            label="Login",
            width=10,
            step_ms=100,
            stream=out,
        )
    )
    rendered = out.getvalue()
    assert "Login" in rendered
    assert "100%" in rendered
    assert page._ticks == 3
