"""Account checks use synthetic snapshots and routed HTML, never real accounts."""
import asyncio
import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from misong.account_health import AccountHealth, AccountPreflightBlocked, HealthReport, required_disks
from misong.jobs import save_json
from misong.rpa.drivers import PROFILES, REGISTRY, DiskDriver
from misong.rpa.runtime import BrowserRuntime

AUTH = {
    "quark": '<div class=file-list>files</div>',
    "feimao": '<div class=user_info><span class=name>synthetic owner</span></div>',
    "uc": '<div class=AsideFooter--tit-left--fixture>1GB / 1TB</div>',
    "xunlei": '<input placeholder="搜索我的文件"><span>我的分享</span>',
    "123pan": '<div class=totalUsageText_fixture>1GB / 1TB</div>',
    "baidu": '<div class=wp-s-aside-nav>files</div><div class=nd-user-info>synthetic owner</div>',
}


class RoutedRuntime:
    """Same service boundary with a real engine and no persistent account files."""
    def __init__(self, browser, body, *, http_status=200, abort=False):
        self.browser = browser
        self.body = body
        self.http_status = http_status
        self.abort = abort
        self.headless = True
        self.cancel = threading.Event()
        self.opened = []

    @asynccontextmanager
    async def open_inspection(self, disk):
        self.opened.append((disk, self.headless))
        context = await self.browser.new_context()
        try:
            page = await context.new_page()
            async def route(request):
                if self.abort:
                    await request.abort("internetdisconnected")
                else:
                    await request.fulfill(status=self.http_status, content_type="text/html; charset=utf-8",
                                          body=self.body)
            await page.route("**/*", route)
            yield REGISTRY[disk](cancel=self.cancel, notify=lambda _: None), page
        finally:
            await context.close()


def browser_scenario(callback):
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright
    async def run():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                await callback(browser)
            finally:
                await browser.close()
    asyncio.run(run())


@pytest.mark.parametrize("disk", REGISTRY)
def test_six_provider_login_expiry_network_and_owner_verification(disk):
    async def scenario(browser):
        runtime = RoutedRuntime(browser, AUTH[disk])
        service = AccountHealth(runtime)
        assert (await service.check_login(disk, timeout=4)).status == "logged_in"
        runtime.body = '<button>扫码登录</button>'
        assert (await service.check_login(disk, timeout=4)).status == "logged_out"
        runtime.abort = True
        result = await service.check_login(disk, timeout=4)
        assert result.status == "network_error" and result.code == "navigation_failed"
        runtime.abort = False
        runtime.body = AUTH[disk] + '<div role=dialog>安全验证</div>'
        assert (await service.check_login(disk, timeout=4)).status == "verification_required"
        runtime.body = AUTH[disk] + '<span>请绑定手机号后再继续操作</span>'
        assert (await service.check_login(disk, timeout=4)).status == "verification_required"
        runtime.body = AUTH[disk] + '<span style="position:fixed;top:-52px;height:20px">账号涉嫌违规已被封禁</span>'
        assert (await service.check_login(disk, timeout=4)).status == "logged_in"
        runtime.http_status = 503
        runtime.body = '<button>扫码登录</button>'
        assert (await service.check_login(disk, timeout=4)).status == "network_error"
        runtime.http_status = 403
        runtime.body = '<div>安全验证</div>'
        assert (await service.check_login(disk, timeout=4)).status == "verification_required"
    browser_scenario(scenario)


@pytest.mark.parametrize("disk", REGISTRY)
def test_six_provider_timeout_cancel_and_no_login_wait(disk, monkeypatch):
    runtime = SimpleNamespace(headless=True, cancel=threading.Event())
    service = AccountHealth(runtime)
    entered, cleaned = [], []
    async def stuck(*args):
        entered.append(True)
        try:
            await asyncio.sleep(60)
        finally:
            cleaned.append(True)
    monkeypatch.setattr(service, "_attempt", stuck)
    async def run():
        result = await service.check_login(disk, timeout=.08)
        assert result.status == "timeout" and cleaned == [True]
        asyncio.get_running_loop().call_later(.04, runtime.cancel.set)
        result = await service.check_login(disk, timeout=1)
        assert result.status == "cancelled" and len(cleaned) == 2
        result = await service.check_login(disk, timeout=1)
        assert result.status == "cancelled" and len(entered) == 2
    asyncio.run(run())


def test_unknown_dom_is_not_expired_and_unexpected_origin_is_not_authenticated():
    async def scenario(browser):
        runtime = RoutedRuntime(browser, '<p>loading</p>')
        result = await AccountHealth(runtime).check_login("quark", timeout=.5)
        assert result.status in ("unknown", "timeout")
        page = await browser.new_page()
        await page.set_content(AUTH["quark"])
        result = await REGISTRY["quark"]().check_login(page, timeout=.5)
        assert result.status == "unknown" and result.code == "unexpected_origin"
    browser_scenario(scenario)


def test_session_invalid_beats_visible_file_scaffold():
    async def scenario(browser):
        runtime = RoutedRuntime(browser, AUTH["feimao"] + '<p>' + PROFILES["feimao"]["session_invalid"] + '</p>')
        result = await AccountHealth(runtime).check_login("feimao", timeout=3)
        assert result.status == "logged_out" and result.code == "session_expired"
    browser_scenario(scenario)


def test_baidu_login_redirect_is_observed_without_waiting_for_owner():
    async def scenario(browser):
        page = await browser.new_page()
        await page.route("**/*", lambda route: route.fulfill(body='<button>去登录</button>', content_type="text/html; charset=utf-8"))
        await page.goto("https://passport.baidu.com/login")
        assert (await REGISTRY["baidu"]().check_login(page, timeout=.5)).status == "logged_out"
    browser_scenario(scenario)


def test_quark_mobile_and_wechat_login_prompts_are_logged_out():
    async def scenario(browser):
        runtime = RoutedRuntime(browser, '<button>手机登录</button><button>微信登录</button>')
        result = await AccountHealth(runtime).check_login("quark", timeout=2)
        assert result.status == "logged_out" and result.code == "login_required"
    browser_scenario(scenario)


def test_123pan_login_redirect_host_is_logged_out():
    async def scenario(browser):
        page = await browser.new_page()
        await page.route("**/*", lambda route: route.fulfill(body='<button>扫码登录</button>', content_type="text/html; charset=utf-8"))
        await page.goto("https://user.123pan.cn/centerlogin")
        result = await REGISTRY["123pan"]().check_login(page, timeout=.5)
        assert result.status == "logged_out" and result.code == "login_required"
    browser_scenario(scenario)


def test_baidu_anonymous_scaffold_with_login_gate_is_logged_out():
    async def scenario(browser):
        runtime = RoutedRuntime(browser, AUTH["baidu"] + '<button>去登录</button>')
        result = await AccountHealth(runtime).check_login("baidu", timeout=2)
        assert result.status == "logged_out" and result.code == "login_required"
    browser_scenario(scenario)


def test_batch_all_and_single_headed_retry_are_bounded_and_do_not_change_runtime(monkeypatch):
    runtime = SimpleNamespace(headless=True, cancel=None)
    service = AccountHealth(runtime)
    calls = []
    async def observed(disk, mode, headless, timeout):
        calls.append((disk, headless))
        return HealthReport(disk, "network_error" if headless else "logged_in", "synthetic", headless)
    monkeypatch.setattr(service, "_attempt", observed)
    async def run():
        results = await service.check_all(headed_retry=True)
        assert len(results) == 6 and all(r.attempts == 2 and r.status == "logged_in" for r in results)
        assert calls == [(d, h) for d in REGISTRY for h in (True, False)]
        assert runtime.headless is True
        calls.clear()
        results = await service.check_all(["夸克", "quark", "UC"], headed_retry=False)
        assert [r.disk for r in results] == ["quark", "uc"] and len(calls) == 2
    asyncio.run(run())


def test_retry_exhaustion_and_external_async_cancel(monkeypatch):
    runtime = SimpleNamespace(headless=True, cancel=None)
    service = AccountHealth(runtime)
    calls = []
    async def failure(disk, mode, headless, timeout):
        calls.append(headless)
        return HealthReport(disk, "verification_required", "owner_action_required", headless)
    monkeypatch.setattr(service, "_attempt", failure)
    async def run():
        result = await service.check_login("quark", headed_retry=True)
        assert result.status == "verification_required" and calls == [True, False]
        async def stuck(*args):
            await asyncio.sleep(60)
        monkeypatch.setattr(service, "_attempt", stuck)
        task = asyncio.create_task(service.check_login("quark"))
        await asyncio.sleep(.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())


def test_preflight_only_pending_remote_stages_including_hop(monkeypatch):
    service = AccountHealth(SimpleNamespace(headless=True, cancel=None))
    calls = []
    async def check(disk, **kw):
        calls.append(disk)
        return HealthReport(disk, "logged_out" if disk == "uc" else "network_error", "synthetic", True)
    monkeypatch.setattr(service, "check_login", check)
    plan = {"version": 2, "stages": [
        {"id": "body", "disk": "quark", "share": {"url": "synthetic"}},
        {"id": "body-uc", "disk": "uc", "uploaded": {"all": ["done"]}},
        {"id": "hop", "disk": "baidu", "files": []},
        {"id": "body-again", "disk": "uc"}], "text_delivery": {"share_complete": True}}
    async def run():
        result = await service.preflight(plan)
        assert result.disks == ("uc", "baidu") and calls == ["uc", "baidu"]
        assert not result.allowed
        with pytest.raises(AccountPreflightBlocked) as exc:
            result.require_ready()
        assert "uc=logged_out" in str(exc.value) and "baidu=network_error" in str(exc.value)
        for stage in plan["stages"]:
            stage["share"] = {"url": "synthetic"}
        calls.clear()
        result = await service.preflight(plan)
        assert result.allowed and not result.results and not calls
        assert result.require_ready() is result
    asyncio.run(run())
    with pytest.raises(ValueError):
        required_disks({"version": 1})


def test_inspection_uses_synthetic_snapshot_and_never_rewrites_it(tmp_path, monkeypatch):
    pytest.importorskip("playwright")
    disk = "feimao"
    rt = BrowserRuntime(state_dir=tmp_path, headless=True, browser_channel="chromium", notify=lambda _: None)
    profile = dict(PROFILES[disk], url="http://127.0.0.1:23456/", hosts=["127.0.0.1"])
    save_json(tmp_path / "profiles" / (disk + ".json"), profile)
    snapshot = {"cookies": [{"name": "synthetic_cookie", "value": "synthetic-value", "domain": "127.0.0.1",
                            "path": "/", "expires": -1, "httpOnly": False, "secure": False, "sameSite": "Lax"}],
                "origins": [{"origin": "http://127.0.0.1:23456", "localStorage": [{"name": "synthetic_local", "value": "kept"}]}]}
    save_json(tmp_path / (disk + ".json"), snapshot)
    save_json(tmp_path / "session-data" / f"{disk}-chromium.json", {
        "http://127.0.0.1:23456": {"synthetic_tab": "kept"}, "https://untrusted.invalid": {"unexpected": "discard"}})
    save_json(tmp_path / (disk + "-status.json"), {"status": "ready", "verified_at": "past"})
    save_json(tmp_path / (disk + "-browser.json"), {"channel": "msedge"})
    sentinel = tmp_path / "browser-data" / disk / "chromium" / "untouched"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("synthetic profile; must not open")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    async def forbidden(*args, **kw):
        pytest.fail("An inspection must never enter interactive login or save authentication")
    monkeypatch.setattr(REGISTRY[disk], "ensure_login", forbidden)
    monkeypatch.setattr(rt, "_save_auth", forbidden)
    async def run():
        for body in (AUTH[disk], '<button>扫码登录</button>', '<div>安全验证</div>'):
            async with rt.open_inspection(disk) as (driver, page):
                await page.route("**/*", lambda route: route.fulfill(body=body, content_type="text/html; charset=utf-8"))
                await page.goto(profile["url"])
                assert await page.evaluate("localStorage.getItem('synthetic_local')") == "kept"
                assert await page.evaluate("sessionStorage.getItem('synthetic_tab')") == "kept"
                assert await page.evaluate("sessionStorage.getItem('unexpected')") is None
                assert any(c["name"] == "synthetic_cookie" for c in await page.context.cookies())
                await driver.check_login(page, timeout=.3)
                await page.evaluate("document.cookie='synthetic_cookie=changed';localStorage.clear()")
        for p, content in before.items():
            assert p.read_bytes() == content
        assert not (tmp_path / "failures").exists()
    asyncio.run(run())


def test_conflicting_scaffold_and_login_prompt_does_not_claim_authenticated():
    async def scenario(browser):
        runtime = RoutedRuntime(browser, AUTH["quark"] + '<button>扫码登录</button>')
        result = await AccountHealth(runtime).check_login("quark", timeout=5)
        assert result.status == "unknown" and result.code == "conflicting_login_signals"
    browser_scenario(scenario)


def test_transient_login_prompt_over_authenticated_shell_resolves_logged_in():
    async def scenario(browser):
        runtime = RoutedRuntime(browser, AUTH["quark"] + '<button id=gate>扫码登录</button>'
                                '<script>setTimeout(()=>document.getElementById("gate").remove(),300)</script>')
        result = await AccountHealth(runtime).check_login("quark", timeout=3)
        assert result.status == "logged_in" and result.code == "authenticated_marker"
    browser_scenario(scenario)


def test_navigation_timeout_is_network_failure_not_session_expiry():
    pytest.importorskip("playwright")
    from playwright.async_api import TimeoutError as PlaywrightTimeout
    @asynccontextmanager
    async def opened(disk):
        async def goto(*args, **kw):
            raise PlaywrightTimeout("synthetic private URL must not appear in report")
        yield SimpleNamespace(profile=PROFILES[disk]), SimpleNamespace(goto=goto)
    runtime = SimpleNamespace(headless=True, cancel=None, open_inspection=opened)
    result = asyncio.run(AccountHealth(runtime).check_login("quark"))
    assert result.status == "network_error" and result.code == "navigation_timeout"
    assert "private URL" not in json.dumps(result.to_dict())


def test_healthy_preflight_allows_only_after_every_pending_disk_is_confirmed(monkeypatch):
    service = AccountHealth(SimpleNamespace(headless=True, cancel=None))
    async def ready(disk, **kw):
        return HealthReport(disk, "logged_in", "authenticated_marker", True)
    monkeypatch.setattr(service, "check_login", ready)
    result = asyncio.run(service.preflight({"version": 2, "stages": [{"disk": d} for d in REGISTRY]}))
    assert result.allowed and len(result.results) == 6
    assert result.to_dict()["allowed"] is True


def test_reports_hide_arbitrary_exceptions_and_unsupported_input(monkeypatch):
    service = AccountHealth(SimpleNamespace(headless=True, cancel=None))
    secret = "Cookie=synthetic-secret https://example.invalid/s/synthetic-secret"
    async def broken(*args):
        raise RuntimeError(secret)
    monkeypatch.setattr(service, "_attempt", broken)
    async def run():
        result = await service.check_login("quark")
        assert result.status == "error" and secret not in json.dumps(result.to_dict())
        unsupported = await service.check_login(secret)
        assert unsupported.status == "unsupported" and secret not in json.dumps(unsupported.to_dict())
        base = DiskDriver()
        assert (await base.check_login(None)).status == "unsupported"
        assert (await base.selfcheck(None)).status == "unsupported"
    asyncio.run(run())


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_budget_is_rejected(timeout):
    with pytest.raises(ValueError):
        asyncio.run(AccountHealth(SimpleNamespace(headless=True)).check_login("quark", timeout=timeout))
