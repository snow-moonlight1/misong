import asyncio
import json

import pytest

from nde.share_options import ShareOptions, common_options
from nde.rpa.drivers import REGISTRY


def test_intersection_follows_selected_providers():
    assert common_options(["uc"]) == (["default", "1", "7", "30", "60", "180", "forever"],
                                       ["default", "none", "code"])
    assert common_options(["uc", "xunlei"]) == (["default", "1", "7", "forever"], ["default", "code"])
    assert common_options(["quark", "uc", "123pan"]) == (["default", "1", "7", "30", "forever"],
                                                       ["default", "none", "code"])
    assert common_options(["xunlei"])[0] == ["default", "1", "2", "3", "4", "5", "6", "7", "forever"]
    assert common_options([]) == (["default"], ["default"])
    assert common_options(["feimao", "uc"]) == (["default", "forever"], ["default", "none", "code"])
    assert common_options(["quark", "feimao", "uc", "xunlei", "123pan"]) == (["default", "forever"], ["default", "code"])


def test_visible_publishing_login_does_not_close_while_waiting():
    from nde.rpa.runtime import BrowserRuntime
    assert BrowserRuntime().login_timeout is None
    assert BrowserRuntime(headless=True).login_timeout == 30


@pytest.mark.parametrize("options,disk", [
    (ShareOptions("60", "code"), "xunlei"), (ShareOptions("7", "none"), "xunlei"),
    (ShareOptions("180", "none"), "quark"),
])
def test_incompatible_policy_is_rejected(options, disk):
    with pytest.raises(ValueError, match="不支持"):
        options.validate_disk(disk)


CONTROLS = {
    "quark": '<label><input type=radio name=expiry>7天</label><label><input type=radio name=expiry checked>永久有效</label><label><input type=radio name=access>需要</label><label><input type=radio name=access checked>不需要</label>',
    "uc": """<div class=slider-tabs-wrap><div class=tabs onclick="this.classList.add('active')">7</div><div class=tabs>永久</div></div><button role=switch aria-checked=false onclick="this.setAttribute('aria-checked',this.getAttribute('aria-checked')==='true'?'false':'true')">收件密码</button>""",
    "123pan": """<div onclick="this.className='selectedTextItem_fixture'">7天</div><div onclick="this.className='selectedTextItem_fixture'">随机提取码</div><div>无提取码</div><label><input type=checkbox>免费用户提取</label>""",
    "xunlei": """<label><input type=checkbox checked disabled>有提取码</label><label><input type=checkbox checked>允许快速访问分享链接</label><div class=dialog-web-create-share__form-item-extract__item>提取期限<div class=td-select-group onclick="document.querySelector('ul').hidden=false"><span class=td-select-group__label>不限</span></div><ul hidden><li onclick="document.querySelector('.td-select-group__label').textContent='7天'"> 7天 </li></ul></div>""",
    "feimao": """<span>分享链接长期有效</span><div class=el-select><input readonly value="公开链接，不需要密码即可访问分享内容" onclick="document.querySelector('ul').hidden=false"><ul hidden><li onclick="document.querySelector('input').value=this.textContent;this.parentElement.hidden=true">私密链接，需要密码才可访问分享内容</li><li>公开链接，不需要密码即可访问分享内容</li></ul></div>""",
}


@pytest.mark.parametrize("disk", list(CONTROLS))
def test_policy_selects_observed_controls_before_share_creation(disk):
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright
    async def scenario():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content("<div role=dialog>" + CONTROLS[disk] + "</div>")
            driver = REGISTRY[disk]()
            driver.configure_share(ShareOptions("forever" if disk == "feimao" else "7", "code"))
            dialog = page.get_by_role("dialog")
            await driver._prepare_share(dialog)
            assert driver.share_expiry == ("永久有效" if disk == "feimao" else "7天")
            if disk == "quark":
                assert await dialog.get_by_role("radio", name="需要", exact=True).is_checked()
                assert await dialog.get_by_role("radio", name="7天", exact=True).is_checked()
            elif disk == "uc":
                assert await dialog.get_by_role("switch").is_checked()
            elif disk == "xunlei":
                assert not await dialog.get_by_role("checkbox", name="允许快速访问分享链接").is_checked()
            await browser.close()
    asyncio.run(scenario())


def test_quark_hidden_radio_uses_visible_label():
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright

    async def scenario():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content("""<div role=dialog>
              <label><input type=radio name=expiry style="position:absolute;width:1px;height:1px;clip:rect(0,0,0,0)">1天</label>
              <label><input type=radio name=expiry checked style="position:absolute;width:1px;height:1px;clip:rect(0,0,0,0)">永久有效</label>
              <label><input type=radio name=access style="position:absolute;width:1px;height:1px;clip:rect(0,0,0,0)">需要</label>
              <label><input type=radio name=access checked style="position:absolute;width:1px;height:1px;clip:rect(0,0,0,0)">不需要</label>
            </div>""")
            driver = REGISTRY["quark"]()
            driver.configure_share(ShareOptions("1", "code"))
            await driver._prepare_share(page.get_by_role("dialog"))
            assert driver.share_expiry == "1天"
            assert await page.get_by_role("radio", name="1天", exact=True).is_checked()
            assert await page.get_by_role("radio", name="需要", exact=True).is_checked()
            await browser.close()
    asyncio.run(scenario())


def test_quark_segmented_buttons_without_radios():
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright

    async def scenario():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content("""<div role=dialog>
              <button type=button onclick="this.classList.add('active')">1天</button>
              <button type=button class=active>永久有效</button>
              <button type=button onclick="this.classList.add('active')">需要</button>
              <button type=button class=active>不需要</button>
            </div>""")
            driver = REGISTRY["quark"]()
            driver.configure_share(ShareOptions("1", "code"))
            await driver._prepare_share(page.get_by_role("dialog"))
            assert driver.share_expiry == "1天"
            assert "active" in (await page.get_by_role("button", name="1天", exact=True).get_attribute("class") or "")
            assert "active" in (await page.get_by_role("button", name="需要", exact=True).get_attribute("class") or "")
            await browser.close()
    asyncio.run(scenario())


def test_feimao_share_menu_outside_dialog():
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright

    async def scenario():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content("""
            <div class=shareDialog role=dialog>
              <span>分享链接长期有效</span>
              <div class=el-select>
                <input readonly value="公开链接，不需要密码即可访问分享内容"
                  onclick="document.querySelector('.el-select-dropdown').hidden=false">
              </div>
            </div>
            <div class=el-select-dropdown hidden>
              <li onclick="document.querySelector('input').value=this.textContent;this.parentElement.hidden=true">私密链接，需要密码才可访问分享内容</li>
              <li>公开链接，不需要密码即可访问分享内容</li>
            </div>""")
            driver = REGISTRY["feimao"]()
            driver.configure_share(ShareOptions("forever", "code"))
            await driver._prepare_share(page.locator(".shareDialog"))
            assert await page.locator("input").input_value() == "私密链接，需要密码才可访问分享内容"
            await browser.close()
    asyncio.run(scenario())


def test_gui_choices_update_and_restore_previous_available_options():
    import tkinter as tk
    from nde.gui import App
    root = tk.Tk()
    root.withdraw()
    try:
        app = App(root)
        for disk, var in app.body_disks.items():
            var.set(disk == "uc")
        app.refresh_share_choices()
        assert "180天" in app.expiry_combo["values"] and "无提取码" in app.access_combo["values"]
        app.vars["share_expiry"].set("180天")
        app.body_disks["xunlei"].set(True)
        app.refresh_share_choices()
        assert tuple(app.expiry_combo["values"]) == ("平台默认", "1天", "7天", "永久有效")
        assert "无提取码" not in app.access_combo["values"]
        assert app.vars["share_expiry"].get() == "平台默认"
        app.body_disks["xunlei"].set(False)
        app.refresh_share_choices()
        assert "180天" in app.expiry_combo["values"] and "无提取码" in app.access_combo["values"]
    finally:
        root.destroy()
