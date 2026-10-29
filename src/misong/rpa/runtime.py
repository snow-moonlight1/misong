"""One browser context per account, with private state and process-safe locking."""
from __future__ import annotations

import json
import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from ..jobs import exclusive, save_json
from ..paths import resolve_paths
from ..sharing import disk_name
from ..publish import Paused
from .drivers import BrowserDiskDriver, DriverBlocked, PROFILES, REGISTRY

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STATE = resolve_paths().state
BROWSERS = ("chromium", "chrome", "msedge")


class BrowserRuntime:
    def __init__(self, *, state_dir=None, headless=False, notify=print, cancel=None,
                 timeout=1800, login_timeout=None, diagnostics=False, browser_channel=None):
        # None 时按构造时刻的 MISONG_HOME 等解析；导入后的环境变化不锁死。
        self.state_dir = Path(state_dir) if state_dir is not None else resolve_paths().state
        self.headless = headless
        self.notify = notify
        self.cancel = cancel
        self.timeout = timeout
        self.login_timeout = (30 if headless else None) if login_timeout is None else login_timeout
        self.diagnostics = diagnostics
        if browser_channel is not None and browser_channel not in BROWSERS:
            raise ValueError("浏览器必须是 chromium、chrome 或 msedge")
        self.browser_channel = browser_channel

    def _record(self, disk, **fields):
        """Merge account health into <disk>-status.json without losing earlier facts.

        ``status`` keeps its legacy meaning for the CLI; ``verified_at`` (a full upload+share
        finished on this machine) and ``session_at`` (login confirmed online) are kept apart so a
        later probe never downgrades a verified driver and a stale session is not shown as valid.
        """
        path = self.state_dir / (disk + "-status.json")
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except ValueError:
            data = {}
        now = datetime.now().isoformat(timespec="seconds")
        if fields.get("status") == "ready":
            data["verified_at"] = now
        elif fields.get("status") == "probe" and data.get("status") == "ready":
            fields["status"] = "ready"
        if fields.pop("session_ok", False):
            data["session_at"] = now
            data.pop("session_error", None)
        error = fields.pop("error", None)
        if error is not None:
            data["last_error"] = str(error)[:300]
            data["last_error_at"] = now
        data.update(fields)
        save_json(path, data)

    def browser_for(self, disk):
        if self.browser_channel is not None:
            return self.browser_channel
        path = self.state_dir / (disk + "-browser.json")
        channel = json.loads(path.read_text(encoding="utf-8"))["channel"] if path.exists() else "chromium"
        if channel not in BROWSERS:
            raise ValueError(f"{disk} 的浏览器配置无效，请使用 --browser 重新指定")
        return channel

    def profile(self, disk):
        path = self.state_dir / "profiles" / (disk + ".json")
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        if disk not in PROFILES:
            raise DriverBlocked(f"尚未适配 {disk}；当前账号入口：{', '.join(PROFILES)}；可手动回填其他网盘链接")
        return PROFILES[disk]

    @staticmethod
    def _session_origin(profile, url):
        """Keep tab storage on its observed, approved first-party origin after redirects."""
        expected, actual = urlsplit(profile["url"]), urlsplit(url)
        hosts = {str(host).lower().removeprefix("www.")
                 for host in [expected.hostname, *profile.get("hosts", [])] if host}
        try:
            valid = (actual.scheme == expected.scheme and actual.port == expected.port
                     and not actual.username and not actual.password
                     and (actual.hostname or "").removeprefix("www.") in hosts)
        except ValueError:
            return None
        return f"{actual.scheme}://{actual.netloc}" if valid else None

    async def _save_auth(self, context, driver, disk, channel):
        """Save only a verified first-party session; never print credential values."""
        from playwright.async_api import Error as PlaywrightError
        try:
            pages = [p for p in context.pages if not p.is_closed()]
            valid = [p for p in pages if await driver.is_logged_in(p)]
            if not valid:
                return
            save_json(self.state_dir / (disk + ".json"), await context.storage_state(indexed_db=True))
            if driver.profile.get("session_storage"):
                session = {}
                for page in valid:
                    origin = self._session_origin(driver.profile, page.url)
                    if origin:
                        session[origin] = await page.evaluate("() => Object.fromEntries(Object.entries(sessionStorage))")
                save_json(self.state_dir / "session-data" / f"{disk}-{channel}.json", session)
        except PlaywrightError:
            # The owner can close the login window while its final snapshot is pending.
            return

    @asynccontextmanager
    async def open_inspection(self, disk):
        """Disposable context using the last verified snapshot and configured channel.

        Never call ensure_login/_save_auth, launch the live persistent profile, update
        browser preferences, or replace authentication snapshots during an observation.
        The caller bounds the whole operation, including startup, and navigates once.
        """
        disk = disk_name(disk)
        if disk not in REGISTRY:
            raise DriverBlocked("该网盘不支持账号检查")
        from playwright.async_api import async_playwright
        profile = self.profile(disk)
        channel = self.browser_for(disk)
        state = self.state_dir / (disk + ".json")
        with exclusive(self.state_dir / (disk + ".lock")):
            # The entry itself can be cancelled while the Node driver starts.
            # Cover __aenter__ with finally, otherwise its pipe transport leaks.
            manager = async_playwright()
            try:
                pw = await manager.__aenter__()
                browser = context = None
                try:
                    options = {"headless": self.headless}
                    if channel != "chromium":
                        options["channel"] = channel
                    browser = await pw.chromium.launch(**options)
                    context = await browser.new_context(
                        storage_state=str(state) if state.exists() else None,
                        accept_downloads=False, locale="zh-CN")
                    context.set_default_timeout(1000)
                    session_file = self.state_dir / "session-data" / f"{disk}-{channel}.json"
                    if profile.get("session_storage") and session_file.exists():
                        sessions = json.loads(session_file.read_text(encoding="utf-8"))
                        data = {origin: entries for origin, entries in sessions.items()
                                if self._session_origin(profile, origin) == origin and isinstance(entries, dict)}
                        await context.add_init_script("""(() => {
                            const entries = DATA[location.origin];
                            if (entries && sessionStorage.length === 0) {
                                for (const [key, value] of Object.entries(entries)) sessionStorage.setItem(key, value);
                            }
                        })();""".replace("DATA", json.dumps(data, ensure_ascii=True)))
                    driver = REGISTRY[disk](profile=profile, notify=self.notify, cancel=self.cancel,
                                            timeout=self.timeout, login_timeout=0, interactive=False)
                    yield driver, await context.new_page()
                finally:
                    # Cleanup has its own small bound, including after task cancellation.
                    for resource in (context, browser):
                        if resource is not None:
                            try:
                                await asyncio.wait_for(resource.close(), timeout=3)
                            except Exception:
                                pass
            finally:
                try:
                    await asyncio.wait_for(manager.__aexit__(None, None, None), timeout=5)
                    await asyncio.sleep(.05)  # let Windows pipe close callbacks drain
                except Exception:
                    pass

    async def check_login(self, disk, *, timeout=20, headed_retry=False):
        from ..account_health import AccountHealth
        return await AccountHealth(self).check_login(disk, timeout=timeout, headed_retry=headed_retry)

    async def selfcheck(self, disk, *, timeout=20, headed_retry=False):
        from ..account_health import AccountHealth
        return await AccountHealth(self).selfcheck(disk, timeout=timeout, headed_retry=headed_retry)

    async def capture_inspection_failure(self, disk, page):
        """Explicit diagnostics opt-in only; never save an authentication state."""
        if not self.diagnostics or disk not in REGISTRY:
            return
        dest = self.state_dir / "failures" / disk / ("check-" + uuid.uuid4().hex[:12])
        try:
            dest.mkdir(parents=True, exist_ok=False)
            await page.screenshot(path=str(dest / "page.png"), timeout=5000)
            content = await page.content()
            if len(content.encode("utf-8")) <= 2 * 1024 * 1024:
                (dest / "page.html").write_text(content, encoding="utf-8")
            self.notify("已保存本次自检的私密页面快照（不自动导出）")
        except Exception:
            self.notify("自检失败快照未能保存，检查结果保留")

    @asynccontextmanager
    async def open(self, disk):
        disk = disk_name(disk)
        profile = self.profile(disk)
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise RuntimeError('请安装 RPA 依赖：python -m pip install -e ".[rpa]"；python -m playwright install chromium') from e
        state = self.state_dir / (disk + ".json")
        with exclusive(self.state_dir / (disk + ".lock")):
            async with async_playwright() as pw:
                channel = self.browser_for(disk)
                self.notify(f"{disk}：浏览器 {channel}；登录态仅用于本软件")
                launch_options = {"headless": self.headless}
                if channel != "chromium":
                    launch_options["channel"] = channel
                context = browser = None
                authenticated = False
                options = dict(profile=profile, notify=self.notify, cancel=self.cancel,
                               timeout=self.timeout, login_timeout=self.login_timeout,
                               interactive=not self.headless)
                driver = REGISTRY[disk](**options) if disk in REGISTRY else BrowserDiskDriver(disk, **options)
                try:
                    if profile.get("persistent"):
                        # A dedicated normal profile retains provider device state across runs.
                        # Never open or copy the user's personal Chrome/Edge profile.
                        data_dir = self.state_dir / "browser-data" / disk / channel
                        context = await pw.chromium.launch_persistent_context(
                            str(data_dir), **launch_options, accept_downloads=False, locale="zh-CN")
                        browser = context.browser
                        # Chromium discards session cookies on a clean profile restart.
                        # Restore only missing session cookies from the verified snapshot;
                        # keep newer profile cookies, their expiry, and origin storage intact.
                        if state.exists():
                            saved = json.loads(state.read_text(encoding="utf-8"))
                            def cookie_key(cookie):
                                return (cookie["name"], cookie["domain"], cookie["path"],
                                        cookie.get("partitionKey"))
                            present = {cookie_key(c) for c in await context.cookies()}
                            missing = [c for c in saved.get("cookies", [])
                                       if c.get("expires") == -1 and cookie_key(c) not in present]
                            if missing:
                                await context.add_cookies(missing)
                    else:
                        browser = await pw.chromium.launch(**launch_options)
                        context = await browser.new_context(storage_state=str(state) if state.exists() else None,
                                                            accept_downloads=False, locale="zh-CN")
                    if self.browser_channel is not None:
                        save_json(self.state_dir / (disk + "-browser.json"), {"channel": channel})
                    session_file = self.state_dir / "session-data" / f"{disk}-{channel}.json"
                    if profile.get("session_storage") and session_file.exists():
                        sessions = json.loads(session_file.read_text(encoding="utf-8"))
                        data = {origin: entries for origin, entries in sessions.items()
                                if self._session_origin(profile, origin) == origin and isinstance(entries, dict)}
                        await context.add_init_script("""(() => {
                            const entries = DATA[location.origin];
                            if (entries && sessionStorage.length === 0) {
                                for (const [key, value] of Object.entries(entries)) sessionStorage.setItem(key, value);
                            }
                        })();""".replace("DATA", json.dumps(data, ensure_ascii=True)))
                    page = await driver.ensure_login(context)
                    authenticated = True
                    self._record(disk, session_ok=True)
                    await self._save_auth(context, driver, disk, channel)
                    yield driver, page
                    self._record(disk, status=driver.status)
                except Exception as error:
                    if context and not any(not p.is_closed() for p in context.pages):
                        self._record(disk, status="probe")
                        raise Paused("任务浏览器已关闭；已确认文件和登录会话已保留，可以继续发布") from error
                    self._record(disk, status="blocked", error=error,
                                 **({} if authenticated else {"session_error": True}))
                    if self.diagnostics and context and context.pages:
                        failed_page = context.pages[-1]
                        if not failed_page.is_closed():
                            dest = self.state_dir / "failures" / disk
                            dest.mkdir(parents=True, exist_ok=True)
                            await failed_page.screenshot(path=str(dest / "page.png"), full_page=True)
                            (dest / "page.html").write_text(await failed_page.content(), encoding="utf-8")
                            self.notify(f"诊断快照仅保存在本机：{dest}")
                    raise
                finally:
                    try:
                        if context:
                            # Never replace a valid state with an anonymous, timed-out login page.
                            if authenticated:
                                await self._save_auth(context, driver, disk, channel)
                            await context.close()
                    finally:
                        if browser:
                            await browser.close()

    async def login(self, disk):
        previous_timeout = self.login_timeout
        self.login_timeout = None  # An explicit interactive login ends when its owner closes it.
        try:
            async with self.open(disk) as (driver, page):
                self.notify(f"{disk}：会话已保存。窗口将保持打开；完成后请主动关闭浏览器窗口。")
                next_save = asyncio.get_running_loop().time() + 2
                while any(not p.is_closed() for p in page.context.pages):
                    driver.check_cancel()
                    if asyncio.get_running_loop().time() >= next_save:
                        await self._save_auth(page.context, driver, disk_name(disk), self.browser_for(disk_name(disk)))
                        next_save = asyncio.get_running_loop().time() + 2
                    await asyncio.sleep(.5)
        finally:
            self.login_timeout = previous_timeout

    async def probe(self, disk):
        disk = disk_name(disk)
        async with self.open(disk) as (driver, page):
            dest = self.state_dir / "probes" / disk
            dest.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(dest / "page.png"), full_page=True)
            (dest / "page.html").write_text(await page.content(), encoding="utf-8")
            save_json(dest / "profile.json", driver.profile)
            self.notify(f"探测快照仅存本机：{dest}")
