"""Passive selector checks against purpose-built pages; no real disk requests."""
import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from misong.account_health import AccountHealth
from misong.rpa.drivers import REGISTRY, DiskDriver, SelectorReport
from test_account_health import AUTH, RoutedRuntime, browser_scenario


ENTRIES = {
    "quark": '<button>新建文件夹</button><button>分享</button>',
    "feimao": '<div class=btn-add><button class=fmbtn>上传</button></div><button>新建文件夹</button>'
              '<div id=fc-content><div class=multiple-operation><button>分享</button><button>更多</button></div></div>',
    "uc": '<button>上传文件</button><button>新建文件夹</button><button>分享</button>',
    "xunlei": '<button>添加</button><button>上传文件</button><button>新建文件夹</button><button>分享</button>',
    "123pan": '<button>上传</button><button>新建</button><div class=file-operator-group>'
              '<button class=file-operator-group-button>分享</button></div>',
    "baidu": '<div class=wp-s-agile-tool-bar><button>新建文件夹</button>'
             '<button class=wp-s-agile-tool-bar__h-action-button>分享</button></div>',
}


def page_for(disk):
    return ('<!doctype html><meta charset=utf-8>' + AUTH[disk] + ENTRIES[disk]
            + '<input type=file name=html5uploader hidden>'
            + '<script>window.writes=0;document.addEventListener("click",()=>window.writes++);'
              'document.addEventListener("change",()=>window.writes++);</script>')


@pytest.mark.parametrize("disk", REGISTRY)
def test_six_drivers_passive_entries_and_exact_broken_selector(disk):
    async def scenario(browser):
        runtime = RoutedRuntime(browser, page_for(disk))
        service = AccountHealth(runtime)
        result = await service.selfcheck(disk, timeout=4)
        assert result.status == "passed", result.to_dict()
        assert {c.item for c in result.selectors} >= {"upload", "new_folder", "share"}
        async with runtime.open_inspection(disk) as (driver, page):
            await page.goto(driver.profile["url"])
            driver.profile["upload"] = "#deliberately-broken-input"
            report = await driver.selfcheck(page, timeout=2)
            assert report.status == "failed"
            assert [(c.item, c.status) for c in report.items if c.status != "passed"] == [("upload", "missing")]
            assert await page.evaluate("window.writes") == 0
            driver.profile["upload"] = "[invalid-css"
            report = await driver.selfcheck(page, timeout=2)
            assert next(c for c in report.items if c.item == "upload").status == "selector_error"
            assert "invalid-css" not in json.dumps(report.to_dict())
            driver.profile.pop("upload")
            report = await driver.selfcheck(page, timeout=2)
            assert next(c for c in report.items if c.item == "upload").status == "not_configured"
    browser_scenario(scenario)


def test_overlay_remains_and_no_input_click_create_or_share_is_triggered():
    async def scenario(browser):
        runtime = RoutedRuntime(browser, page_for("quark") +
                                '<div id=overlay style="position:fixed;inset:0;z-index:999;background:#eee">notice</div>')
        async with runtime.open_inspection("quark") as (driver, page):
            await page.goto(driver.profile["url"])
            report = await driver.selfcheck(page, timeout=2)
            assert report.status == "failed"
            assert next(c for c in report.items if c.item == "new_folder").status == "covered_overlay"
            assert next(c for c in report.items if c.item == "share").status == "covered_overlay"
            assert await page.locator("#overlay").count() == 1
            assert await page.evaluate("window.writes") == 0
            assert await page.locator("input[type=file]").evaluate("e=>e.files.length") == 0
    browser_scenario(scenario)


def test_plain_layout_overlap_is_covered_without_blaming_a_popup():
    async def scenario(browser):
        runtime = RoutedRuntime(browser, page_for("quark") +
                                '<div id=blocker style="position:absolute;left:0;top:0;width:100%;height:100%;background:#eee">notice</div>')
        async with runtime.open_inspection("quark") as (driver, page):
            await page.goto(driver.profile["url"])
            report = await driver.selfcheck(page, timeout=2)
            assert next(c for c in report.items if c.item == "new_folder").status == "covered"
            assert await page.evaluate("window.writes") == 0
    browser_scenario(scenario)


def test_label_span_inside_wrapping_button_is_not_covered():
    async def scenario(browser):
        body = (AUTH["quark"] + '<button class="btn-create-folder"><span>新建文件夹</span></button>'
                '<button>分享</button><input type=file hidden>'
                '<script>window.writes=0;document.addEventListener("click",()=>window.writes++);'
                'document.addEventListener("change",()=>window.writes++);</script>')
        runtime = RoutedRuntime(browser, body)
        async with runtime.open_inspection("quark") as (driver, page):
            await page.goto(driver.profile["url"])
            report = await driver.selfcheck(page, timeout=2)
            assert next(c for c in report.items if c.item == "new_folder").status == "passed"
            assert await page.evaluate("window.writes") == 0
    browser_scenario(scenario)


def test_lazy_share_and_menu_entries_are_incomplete_never_fake_success():
    async def scenario(browser):
        runtime = RoutedRuntime(browser, AUTH["xunlei"] + '<button>添加</button><input type=file hidden>')
        result = await AccountHealth(runtime).selfcheck("xunlei", timeout=3)
        assert result.status == "incomplete"
        states = {c.item: c.status for c in result.selectors}
        assert states["upload"] == states["upload_menu"] == "passed"
        assert states["new_folder"] == states["share"] == states["upload_button"] == "not_observed"
    browser_scenario(scenario)


def test_duplicate_or_disabled_entry_does_not_report_success():
    async def scenario(browser):
        runtime = RoutedRuntime(browser, page_for("quark") + '<button>新建文件夹</button>')
        async with runtime.open_inspection("quark") as (driver, page):
            await page.goto(driver.profile["url"])
            report = await driver.selfcheck(page, timeout=2)
            assert next(c for c in report.items if c.item == "new_folder").status == "ambiguous"
            await page.get_by_text("新建文件夹", exact=True).last.evaluate("el=>el.remove()")
            await page.get_by_text("新建文件夹", exact=True).evaluate("el=>el.disabled=true")
            report = await driver.selfcheck(page, timeout=2)
            assert next(c for c in report.items if c.item == "new_folder").status == "disabled"
            assert await page.evaluate("window.writes") == 0
    browser_scenario(scenario)


def test_selector_check_waits_for_auth_and_preserves_owner_verification():
    async def scenario(browser):
        for body, status in [('<button>登录</button>', "logged_out"), ('<div>安全验证</div>', "verification_required")]:
            runtime = RoutedRuntime(browser, body)
            report = await AccountHealth(runtime).selfcheck("quark", timeout=3)
            assert report.status == status and not report.selectors
    browser_scenario(scenario)


def test_driver_selector_timeout_and_cancellation_are_bounded():
    async def scenario(browser):
        runtime = RoutedRuntime(browser, page_for("quark"))
        async with runtime.open_inspection("quark") as (driver, page):
            await page.goto(driver.profile["url"])
            async def stuck(locator):
                await asyncio.sleep(60)
            driver._health_visible = stuck
            assert (await driver.selfcheck(page, timeout=.05)).status == "timeout"
            asyncio.get_running_loop().call_later(.03, runtime.cancel.set)
            assert (await driver.selfcheck(page, timeout=2)).status == "cancelled"
    browser_scenario(scenario)


def test_canary_is_separate_explicit_and_current_drivers_do_not_claim_support():
    runtime = SimpleNamespace(headless=True, cancel=None)
    async def run():
        service = AccountHealth(runtime)
        with pytest.raises(ValueError, match="明确启用"):
            await service.run_canary("quark")
        with pytest.raises(ValueError, match="明确启用"):
            await DiskDriver().canary_selfcheck(None)
        for disk in REGISTRY:
            result = await service.run_canary(disk, allow_remote_writes=True)
            assert result.status == "unsupported" and result.code == "canary_unsupported"
        writes = []
        class SyntheticCanary(DiskDriver):
            async def canary_selfcheck(self, page, *, allow_remote_writes=False):
                assert allow_remote_writes
                writes.extend(["upload", "share", "readback", "delete"])
                return SelectorReport("passed")
        @asynccontextmanager
        async def active(disk):
            yield SyntheticCanary(), None
        original = REGISTRY["quark"]
        try:
            REGISTRY["quark"] = SyntheticCanary
            runtime.open = active
            assert not writes
            report = await service.run_canary("quark", allow_remote_writes=True)
            assert report.status == "passed" and writes == ["upload", "share", "readback", "delete"]
        finally:
            REGISTRY["quark"] = original
    asyncio.run(run())
