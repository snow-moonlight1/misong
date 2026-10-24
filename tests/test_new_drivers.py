"""Observed provider flow variants, served entirely by Playwright routing."""
import asyncio
import json

import pytest

from misong.rpa.drivers import REGISTRY, DriverBlocked


PAGE = r"""<!doctype html><meta charset=utf-8><body>
<script>
const disk = DISK;
let folder='', names=[], selected=false;
function render(){
 document.body.innerHTML = '<div class="auth"></div><a id="root">'+(disk==='uc'?'我的文件':disk==='xunlei'?'全部':'全部文件')+'</a>'+
 '<button id="menu">添加</button><div id="menuItems" hidden><button id="mkdir">新建文件夹</button><button id="upload">上传文件</button></div>'+
 '<button id="new">新建</button><div id="naming" hidden><input id="name"><button id="confirm">确定</button></div>'+
 '<input type=file id="file" hidden><button id="upload123">上传</button>'+
 '<div class="bcrumb-filename">'+folder+'</div><div id="crumb">'+(folder?'misong-adapte...':'')+'</div>'+
 '<div id="listing"></div><div class="file-operator-group"><button class="file-operator-group-button" id="share">分享</button>'+
 (disk==='123pan'?'<div class="measuring-container" style="position:absolute;left:-9999px"><div class="file-operator-group-button">分享</div></div>':'')+'</div>'+
 '<div id="gate" hidden><span>绑定手机号码</span><button id="owner">完成绑定</button></div>'+
 '<div role="dialog" class="dialog-web-create-share create-share-modal" hidden><div id="options"></div><div id="result"></div></div>';
 document.querySelector('.auth').textContent=disk==='xunlei'?'已用1GB / 1TB':'1GB/1TB';
 if(disk==='xunlei')document.body.insertAdjacentHTML('afterbegin','<input placeholder="搜索我的文件"><span>我的分享</span>');
 document.querySelector('#menuItems').hidden=disk==='xunlei';
 document.querySelector('#root').onclick=()=>{folder=''; history.pushState({},'',location.pathname);render()};
 document.querySelector('#menu').onclick=()=>document.querySelector('#menuItems').hidden=false;
 document.querySelector('#mkdir').onclick=document.querySelector('#new').onclick=()=>document.querySelector('#naming').hidden=false;
 const create=()=>{names.push(document.querySelector('#name').value);document.querySelector('#naming').hidden=true;rows()};
 document.querySelector('#confirm').onclick=create;
 document.querySelector('#name').onkeydown=e=>{if(e.key==='Enter')create()};
 document.querySelector('#upload').onclick=document.querySelector('#upload123').onclick=()=>document.querySelector('#file').click();
 document.querySelector('#file').onchange=e=>{
  names.push(...Array.from(e.target.files).map(f=>f.name));rows();
  if(disk==='xunlei'){
   document.body.insertAdjacentHTML('beforeend','<div class="pan-task-list" style="width:0;height:0"><div class="TaskList__shadow--fixture" style="position:fixed;inset:0;z-index:100;background:#0008"></div><div class="TaskList__header--fixture" style="position:fixed;top:0;left:0;z-index:101"><a class="xlp-list-del" style="display:block;background:white;width:30px;height:30px">×</a></div></div>');
   document.querySelector('.xlp-list-del').onclick=()=>{window.closedTransfers=(window.closedTransfers||0)+1;document.querySelector('.pan-task-list').remove()};
  }
  if(disk==='123pan'){
   document.body.insertAdjacentHTML('beforeend','<div class="popoverContent_fixture" style="position:fixed;inset:0;z-index:100;background:#ddd"><div class="titleBar_fixture">进度<button class="closeIcon_fixture">×</button></div></div>');
   document.querySelector('.closeIcon_fixture').onclick=()=>{window.closedTransfers=(window.closedTransfers||0)+1;document.querySelector('.popoverContent_fixture').remove()};
  }
 };
 document.querySelector('#share').onclick=()=>{
  document.querySelector('[role=dialog]').hidden=false;
  document.querySelector('#options').innerHTML=
    (disk==='xunlei'?'<label><input type=checkbox checked>允许快速访问分享链接</label>':'')+
    (disk==='123pan'?'<div id="free">无提取码</div><div class="selectedTextItem_fixture" id="random">随机提取码</div><div id="paid">付费提取</div><label><input type=checkbox>免费用户提取</label>':'')+
    '<button id="create">'+(disk==='uc'?'创建分享链接':'创建链接')+'</button>';
  if(disk==='123pan') document.querySelector('#free').onclick=()=>{document.querySelector('#paid').className='';document.querySelector('#free').className='selectedTextItem_fixture'};
  document.querySelector('#create').onclick=()=>{
   if(disk==='xunlei'&&document.querySelector('#options input').checked)throw Error('fast mode hides required code');
   if(disk==='123pan'&&document.querySelector('#paid').className)throw Error('paid sharing');
   if(disk==='uc'&&!window.bound){document.querySelector('#gate').hidden=false;return}
   document.querySelector('#create').hidden=true;
   document.querySelector('#result').innerHTML='<input value="'+(disk==='123pan'?'https://fixture.share.123pan.cn/123pan/Abc-test':'https://'+(disk==='uc'?'drive.uc.cn':'pan.xunlei.com')+'/s/fixture')+'">'+
     (disk==='xunlei'?'<label class="code">提取码<input value="s9gg"></label>':'');
  };
 };
 document.querySelector('#owner').onclick=()=>{window.bound=true;document.querySelector('#gate').hidden=true};
 rows();
}
function rows(){
 const values=folder?names.filter(n=>n!==folder):names.filter(n=>n.startsWith('misong-'));
 document.querySelector('#listing').innerHTML=values.map(n=>'<div class="row"><input type=checkbox><span>'+n+'</span></div>').join('');
 document.querySelectorAll('.row span').forEach(e=>e.ondblclick=()=>{
  folder=e.textContent; history.pushState({},'','?'+(disk==='123pan'?'homeFilePath=12345':'path='+encodeURIComponent('/'+folder)));render();
 });
}
render();
</script>"""


@pytest.mark.parametrize("disk", ["uc", "xunlei", "123pan"])
def test_provider_upload_collection_share_and_resume(tmp_path, disk):
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright
    files = [tmp_path / f"part{i:03}.bin" for i in (1, 2)]
    for file in files:
        file.write_bytes(b"own test bytes")

    async def scenario():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            html = PAGE.replace("DISK", json.dumps(disk))
            await page.route("**/*", lambda route: route.fulfill(body=html, content_type="text/html; charset=utf-8"))
            await page.goto("http://127.0.0.1:8123/")
            driver = REGISTRY[disk](timeout=3, login_timeout=2, notify=lambda _: None)
            driver.profile.update(logged_in=".auth", rows=".row", folder_input="#name",
                                  new_folder="新建" if disk == "123pan" else "新建文件夹",
                                  upload_trigger="#upload123" if disk == "123pan" else "#upload",
                                  root_text="全部" if disk == "xunlei" else "我的文件" if disk == "uc" else "全部文件")
            if disk != "xunlei":
                driver.profile["root_role"] = "link"
                await page.locator("#root").evaluate("e=>e.setAttribute('role','link')")
            assert await driver.is_logged_in(page)
            await page.locator(".auth").evaluate("e=>e.textContent=''")
            assert not await driver.is_logged_in(page)  # File manager skeleton alone is insufficient.
            await page.locator(".auth").evaluate("e=>e.textContent='已用1GB / 1TB'" if disk == "xunlei" else "e=>e.textContent='1GB/1TB'")
            targets = await driver.upload(page, files, "misong-test-collection")
            # Root is rerendered by normal in-site navigation, including semantic link role.
            if disk != "xunlei":
                await page.locator("#root").evaluate("e=>e.setAttribute('role','link')")
            await driver.upload(page, files, "misong-test-collection")  # Resume must not upload duplicates.
            assert await driver.rows(page, files[0].name).count() == 1
            if disk == "uc":
                async def owner():
                    await page.locator("#gate").wait_for(state="visible")
                    await page.locator("#owner").click()
                owner_task = asyncio.create_task(owner())
            info = await driver.share(page, targets)
            if disk in ("xunlei", "123pan"):
                assert await page.evaluate("window.closedTransfers") == 2
                assert await page.locator(".pan-task-list").count() == 0
                assert await page.locator(".popoverContent_fixture").count() == 0
            if disk == "uc":
                await owner_task
            assert info.disk == disk and driver.status == "ready"
            assert info.code == ("s9gg" if disk == "xunlei" else "")
            assert "\\" not in info.url
            if disk == "123pan":
                assert "/123pan/Abc-test" in info.url
            await browser.close()
    asyncio.run(scenario())


def test_123_does_not_activate_download_sponsorship():
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright
    async def scenario():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content('<div role=dialog><div class=selectedTextItem_fixture>无提取码</div><label><input type=checkbox checked>免费用户提取</label></div>')
            with pytest.raises(DriverBlocked, match="分享流量包"):
                await REGISTRY["123pan"]()._prepare_share(page.get_by_role("dialog"))
            await browser.close()
    asyncio.run(scenario())


def test_123_closes_splash_with_its_own_button():
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright
    async def scenario():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content('''<div class="splashScreenModal_fixture" style="position:fixed;inset:0">
              <a href="https://example.invalid/member" id="ad">
                <button class="splashScreenModal__close_fixture">×</button></a></div>
              <button id="new">新建</button>
              <script>document.querySelector('.splashScreenModal__close_fixture').onclick=e=>{
                e.preventDefault();document.querySelector('.splashScreenModal_fixture').remove()};
                document.querySelector('#new').onclick=()=>window.created=true;</script>''')
            await REGISTRY["123pan"]()._dismiss_promotions(page)
            await page.get_by_role("button", name="新建", exact=True).click(timeout=2000)
            assert await page.evaluate("window.created")
            assert page.url == "about:blank"
            await browser.close()
    asyncio.run(scenario())


def test_xunlei_auth_uses_visible_controls_instead_of_outer_container_or_quota():
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright
    async def scenario():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            driver = REGISTRY["xunlei"]()
            await page.set_content('<section class="file-manager-layout"><input placeholder="搜索我的文件"><span>我的分享</span></section>')
            assert await page.locator(".pan-content").count() == 0
            assert await driver.is_logged_in(page)
            await page.get_by_text("我的分享", exact=True).evaluate("e=>e.remove()")
            assert not await driver.is_logged_in(page)
            await browser.close()
    asyncio.run(scenario())
