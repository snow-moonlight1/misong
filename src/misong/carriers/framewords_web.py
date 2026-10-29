"""Normal Framewords website UI, with ephemeral Playwright contexts only.

No site code, cookies, HTML, screenshots, traces or response bodies are saved.
The optional page_factory is an async context manager factory yielding a fresh
Playwright Page on *each* call, including the saved-file verification call.
It must provide equivalent isolation and must not enable diagnostics. This is
an injection seam for self-authored offline pages, not a second carrier API.
"""
from __future__ import annotations

import asyncio
import math
import os
import re
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

from .base import (
    CarrierCapabilities, DecodeRequest, DecodedText, EncodeRequest, EncodedVideo,
    verify_saved_video,
)
from ..text_contracts import ErrorCode, OperationContext, Stage, TextOperationError, text_digest

SITE_URL = "https://zy.lolcon.top/"
# Set only after the --live matrix passes; the website is still network-dependent.
# 2026-10-29: real normal UI encode + fresh-context decode, with/without password;
# Chromium 156.0.8078.4 headed. This is a tested version, not an offline guarantee.
VERIFIED_VERSIONS: tuple[str, ...] = ("2.7.8",)
MAX_INPUT_BYTES = 1024 * 1024


async def _close(resource):
    if resource is not None:
        try:
            await asyncio.wait_for(resource.close(), 5)
        except Exception:
            pass  # Never turn cleanup failures into sensitive diagnostics.


class FramewordsWebCarrier:
    def __init__(self, *, page_factory=None, browser="chromium", headless=False,
                 timeout=300.0):
        if browser not in ("chromium", "chrome", "msedge"):
            raise TextOperationError(ErrorCode.UNSUPPORTED)
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise TextOperationError(ErrorCode.INVALID_RECIPE)
        self._page_factory = page_factory
        self._browser = browser
        self._headless = headless
        self._timeout = timeout

    def capabilities(self) -> CarrierCapabilities:
        verified = bool(VERIFIED_VERSIONS) and self._page_factory is None
        return CarrierCapabilities(
            format_id="framewords", backend_id="framewords_web",
            modes=("standard",) if verified else (), can_encode=verified,
            can_decode=verified, supports_password=verified,
            verified_versions=VERIFIED_VERSIONS if verified else (),
        )

    @asynccontextmanager
    async def _page(self):
        if self._page_factory is not None:
            async with self._page_factory() as page:
                yield page
            return
        # Driver-level debug logging can print fill arguments before our error
        # boundary can redact them. Refuse it rather than mutate process-global
        # environment variables while other operations may be running.
        debug = re.split(r"[\s,]+", os.environ.get("DEBUG", ""))
        if os.environ.get("PWDEBUG") or any(
                token.startswith(("pw:", "*")) for token in debug):
            raise TextOperationError(ErrorCode.UNSUPPORTED)
        # Do not reuse BrowserRuntime: that runtime persists account diagnostics.
        from playwright.async_api import async_playwright
        startup = asyncio.create_task(async_playwright().start())
        manager = None
        browser = context = None
        try:
            # A cancellation during driver startup must not discard the handle
            # needed to stop its subprocess. Cleanup waits for the shielded start.
            manager = await asyncio.shield(startup)
            options = {"headless": self._headless}
            if self._browser != "chromium":
                options["channel"] = self._browser
            browser = await manager.chromium.launch(**options)
            context = await browser.new_context(accept_downloads=True, locale="zh-CN")
            page = await context.new_page()
            yield page
        finally:
            async def cleanup():
                local_manager = manager
                if local_manager is None:
                    try:
                        local_manager = await asyncio.wait_for(startup, 5)
                    except Exception:
                        return
                await _close(context)
                await _close(browser)
                try:
                    await asyncio.wait_for(local_manager.stop(), 5)
                except Exception:
                    pass
            closing = asyncio.create_task(cleanup())
            try:
                await asyncio.shield(closing)
            except asyncio.CancelledError:
                # Closing is independent of the cancelled operation task.
                await asyncio.shield(closing)
                raise

    async def _guard(self, work, context):
        """Bound the entire operation, including startup/downloads, and redact chains."""
        task = None
        code = None
        try:
            context.check()
            task = asyncio.create_task(work())
            deadline = time.monotonic() + self._timeout
            while not task.done():
                context.check()
                if time.monotonic() >= deadline:
                    raise TextOperationError(ErrorCode.TIMEOUT)
                await asyncio.wait({task}, timeout=.1)
            result = await task
            context.check()
        except TextOperationError as error:
            code = error.code
        except asyncio.CancelledError:
            code = ErrorCode.CANCELLED
        except (ImportError, ModuleNotFoundError):
            code = ErrorCode.UNSUPPORTED
        except (TimeoutError, asyncio.TimeoutError):
            code = ErrorCode.TIMEOUT
        except OSError:
            code = ErrorCode.IO
        except Exception:
            code = ErrorCode.PAGE_CHANGED
        finally:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        # Outside except: even __context__ must not hold a Playwright call log.
        if code is not None:
            raise TextOperationError(code)
        return result

    @staticmethod
    async def _ui(awaitable, code=ErrorCode.PAGE_CHANGED):
        failed = False
        try:
            result = await awaitable
        except TextOperationError:
            raise
        except Exception:
            failed = True
        if failed:
            raise TextOperationError(code)
        return result

    async def _open(self, page):
        if self._page_factory is None:
            response = await self._ui(
                page.goto(SITE_URL, wait_until="domcontentloaded", timeout=30000),
                ErrorCode.NETWORK,
            )
            if response is None or response.status >= 400:
                raise TextOperationError(ErrorCode.NETWORK)
        page.set_default_timeout(15000)

    async def _require(self, page, *selectors):
        for selector in selectors:
            if await page.locator(selector).count() != 1:
                raise TextOperationError(ErrorCode.PAGE_CHANGED)

    @staticmethod
    def _source(request):
        if request.mode != "standard":
            raise TextOperationError(ErrorCode.UNSUPPORTED)
        if request.password is not None and not isinstance(request.password, str):
            raise TextOperationError(ErrorCode.INVALID_RECIPE)
        source = Path(request.source).resolve(strict=True)
        if not source.is_file() or source.stat().st_size == 0:
            raise TextOperationError(ErrorCode.MEDIA)
        return source

    @staticmethod
    def _error_code(message, fallback=ErrorCode.MEDIA):
        # Only classify a dedicated status/error region. Never inspect the input
        # text/body (a hidden message may itself contain any of these words).
        if re.search(r"容量|1000|字数|过长|超出|超限|最大|至少.*秒|时长.*不足|视频.*(?:太短|过短)|too (?:large|long)|capacity", message, re.I):
            return ErrorCode.CAPACITY
        if re.search(r"组件|下载|component|download", message, re.I):
            return ErrorCode.DOWNLOAD
        if re.search(r"网络|连接|network|fetch", message, re.I):
            return ErrorCode.NETWORK
        return fallback

    async def _failure(self, page):
        for selector in ("#encode-error", "#input-error", "#failure-state"):
            loc = page.locator(selector)
            if await loc.count() == 1 and await loc.is_visible():
                message = await loc.inner_text()
                if message.strip():
                    raise TextOperationError(self._error_code(message))

    async def _wait(self, page, context, *, encoding=False, password=None):
        unlocked = False
        while True:
            context.check()
            await self._require(page, *(('#encoded-state', '#download-video') if encoding else
                                       ('#result-state', '#result-text', '#unlock-state')))
            await self._failure(page)
            if encoding:
                if await page.locator("#encoded-state").is_visible():
                    if not await page.locator("#download-video").is_visible():
                        raise TextOperationError(ErrorCode.PAGE_CHANGED)
                    return
            else:
                if await page.locator("#result-state").is_visible():
                    return
                if await page.locator("#unlock-state").is_visible():
                    if password is None or password == "":
                        raise TextOperationError(ErrorCode.MISSING_SECRET)
                    if not unlocked:
                        await self._ui(page.locator("#unlock-password").fill(password))
                        await self._ui(page.locator("#unlock-submit").click())
                        unlocked = True
                    error = page.locator("#unlock-error")
                    if await error.is_visible():
                        message = await error.inner_text()
                        if message.strip():
                            # Only an explicit website password rejection earns this code.
                            code = (ErrorCode.WRONG_PASSWORD if re.search(
                                r"密码.*(?:错误|不正确)|(?:错误|不正确).*密码|wrong password|incorrect password",
                                message, re.I) else ErrorCode.INTEGRITY)
                            raise TextOperationError(code)
            await asyncio.sleep(.1)

    async def encode(self, request: EncodeRequest, context: OperationContext) -> EncodedVideo:
        return await self._guard(lambda: self._encode(request, context), context)

    async def _encode(self, request, context):
        context.report(Stage.PREFLIGHT)
        source = self._source(request)
        if not isinstance(request.text, str) or not request.text:
            raise TextOperationError(ErrorCode.INVALID_RECIPE)
        try:
            size = len(request.text.encode("utf-8"))
        except UnicodeError:
            raise TextOperationError(ErrorCode.INVALID_RECIPE) from None
        if size > MAX_INPUT_BYTES:
            raise TextOperationError(ErrorCode.CAPACITY)
        destination = Path(request.destination).absolute()
        if os.path.lexists(destination) or destination.resolve() == source:
            raise TextOperationError(ErrorCode.IO)
        if not destination.parent.is_dir():
            raise TextOperationError(ErrorCode.IO)
        with tempfile.TemporaryDirectory(prefix=".misong-framewords-", dir=destination.parent) as folder:
            staged = Path(folder) / "download.mp4"
            context.report(Stage.CARRIER_ENCODE)
            async with self._page() as page:
                await self._open(page)
                await self._require(page, "#mode-write", "#encode-file", "#encode-text",
                                    "#encode-password", "#encode-profile", "#encode-submit",
                                    "#encoded-state", "#download-video", "#text-count")
                await self._ui(page.locator("#mode-write").click())
                # The public semantic controls map standard -> 视频加密 / 标准加密.
                await self._ui(page.get_by_role("radio", name="视频加密", exact=True).check())
                await self._ui(page.get_by_role("radio", name="标准加密", exact=True).check())
                await self._ui(page.locator("#encode-profile").select_option("balanced"))
                # Capacity is read from the current page, never guessed from Python len.
                count = await page.locator("#text-count").inner_text()
                match = re.fullmatch(r"\s*\d+\s*/\s*(\d+)\s*字\s*", count)
                if not match:
                    raise TextOperationError(ErrorCode.PAGE_CHANGED)
                limit = int(match[1])
                await self._ui(page.locator("#encode-file").set_input_files(str(source)))
                await self._ui(page.locator("#encode-text").fill(request.text))
                actual = await page.locator("#encode-text").input_value()
                if actual != request.text:
                    raise TextOperationError(ErrorCode.CAPACITY)
                count = await page.locator("#text-count").inner_text()
                match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*字\s*", count)
                if not match or int(match[2]) != limit:
                    raise TextOperationError(ErrorCode.PAGE_CHANGED)
                if int(match[1]) > limit:
                    raise TextOperationError(ErrorCode.CAPACITY)
                await self._ui(page.locator("#encode-password").fill(request.password or ""))
                await self._failure(page)
                await self._ui(page.locator("#encode-submit").click())
                await self._wait(page, context, encoding=True)
                # Observe a real completed download; don't trust a completed label.
                failure = False
                try:
                    async with page.expect_download(timeout=15000) as event:
                        await page.locator("#download-video").click()
                    download = await event.value
                    if await download.failure() is not None:
                        raise TextOperationError(ErrorCode.DOWNLOAD)
                    await download.save_as(str(staged))
                except Exception:
                    failure = True
                if failure or not staged.is_file() or staged.stat().st_size == 0:
                    raise TextOperationError(ErrorCode.DOWNLOAD)
            # The encoder page AND its context are gone before independent decode.
            await self.verify(DecodeRequest(staged, request.mode, request.password), request.text, context)
            context.check()
            # Same-directory hard link publishes atomically without overwriting a
            # destination another operation created while this one was working.
            os.link(staged, destination)
            try:
                context.check()
            except BaseException:
                if destination.samefile(staged):
                    destination.unlink()
                raise
        return EncodedVideo(destination, text_digest(request.text), verified=True)

    async def decode(self, request: DecodeRequest, context: OperationContext) -> DecodedText:
        return await self._guard(lambda: self._decode(request, context), context)

    async def _decode(self, request, context):
        context.report(Stage.CARRIER_DECODE)
        source = self._source(request)
        async with self._page() as page:
            await self._open(page)
            await self._require(page, "#mode-read", "#tab-file", "#video-file", "#submit",
                                "#result-state", "#result-text", "#unlock-state",
                                "#unlock-password", "#unlock-submit", "#unlock-error")
            await self._ui(page.locator("#mode-read").click())
            await self._ui(page.locator("#tab-file").click())
            await self._ui(page.locator("#video-file").set_input_files(str(source)))
            await self._ui(page.locator("#submit").click())
            await self._wait(page, context, password=request.password)
            text = await page.locator("#result-text").input_value()
            if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
                raise TextOperationError(ErrorCode.CAPACITY)
            context.check()
        context.check()
        return DecodedText(text)

    async def verify(self, request: DecodeRequest, expected_text: str,
                     context: OperationContext) -> DecodedText:
        return await self._guard(
            lambda: verify_saved_video(self, request, expected_text, context), context)
