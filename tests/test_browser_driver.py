"""Real Playwright engine against a loopback fake disk, never external accounts."""
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from nde.jobs import save_json
from nde.rpa.runtime import BrowserRuntime


PAGE = """<!doctype html><meta charset=utf-8><style>.file-list {min-height: 80px}</style><body>
<button id=new>新建文件夹</button><div id=naming hidden><input placeholder=文件夹名称><button id=ok>确定</button></div>
<input type=file multiple><button id=share>分享</button><button id=refresh>刷新</button><div id=breadcrumb></div><div class=file-list><table><tbody></tbody></table></div>
<div id=toolbar><button id=more>更多</button><div id=more-panel hidden><button id=overflow-share>分享</button></div></div>
<button id=upload-go>选择上传文件</button><div id=account-gate hidden><span>请绑定手机号后再继续操作</span><button id=finish-bind>完成绑定</button></div>
<div role=dialog hidden><button id=create>创建链接</button><div id=result></div></div>
<div class=el-dialog id=share-notice hidden><span>为了共同维护良好的网络环境，每次分享的文件将会经过机器检测，请勿分享非法文件。</span><button id=accept-notice>确 认</button></div>
<div style="position:fixed;top:-52px;height:20px">账号涉嫌违规已被封禁，暂时无法使用该功能</div>
<div id=invalid-session hidden>当前设备已被下线，如非本人操作请及时修改密码，避免所存储的数据丢失。</div>
<script>
const folder=new URL(location.href).searchParams.get('folder')||'';
const needsGate=new URL(location.href).searchParams.has('gate');
document.querySelector('#invalid-session').hidden=!new URL(location.href).searchParams.has('invalid');
let accountReady=!needsGate;
document.querySelector('#breadcrumb').textContent=folder;
const esc=s=>s.replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
async function render(){
 const response=await (await fetch('/list?folder='+encodeURIComponent(folder))).json();
 const data=response.data.list.map(x=>x.file_name);
 await new Promise(r=>setTimeout(r,120));
 document.querySelector('tbody').innerHTML=data.map(n=>'<tr><td><input type=checkbox></td><td><span>'+esc(n)+'</span></td></tr>').join('');
 document.querySelectorAll('tr span').forEach(s=>s.ondblclick=()=>location.href='/?'+(needsGate?'gate=1&':'')+'folder='+encodeURIComponent(s.textContent));
}
document.querySelector('#new').onclick=()=>document.querySelector('#naming').hidden=false;
document.querySelector('#refresh').onclick=render;
document.querySelector('#upload-go').onclick=()=>{if(!accountReady){document.querySelector('#account-gate').hidden=false}else{document.querySelector('input[type=file]').click()}};
document.querySelector('#finish-bind').onclick=()=>{accountReady=true;document.querySelector('#account-gate').hidden=true};
document.querySelector('#ok').onclick=async()=>{await fetch('/mkdir?name='+encodeURIComponent(document.querySelector('#naming input').value));document.querySelector('#naming').hidden=true;await render()};
document.querySelector('input[type=file]').onchange=async e=>{for(const f of e.target.files){await fetch('/upload?folder='+encodeURIComponent(folder)+'&name='+encodeURIComponent(f.name),{method:'POST',body:await f.arrayBuffer()})};await render()};
document.querySelector('#share').onclick=()=>document.querySelector('#share-notice').hidden=false;
document.querySelector('#more').onclick=()=>document.querySelector('#more-panel').hidden=false;
document.querySelector('#overflow-share').onclick=()=>document.querySelector('#share-notice').hidden=false;
document.querySelector('#accept-notice').onclick=()=>{document.querySelector('#share-notice').hidden=true;document.querySelector('[role=dialog]').hidden=false};
document.querySelector('#create').onclick=()=>{document.querySelector('#result').innerHTML='<input value=\"'+location.origin+'/s/fixture\"><span>提取码：a123</span>';document.querySelector('#create').hidden=true};
render();
</script></body>"""


@pytest.fixture
def local_disk():
    files = {}
    uploads = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            q = parse_qs(url.query)
            if url.path == "/list":
                body = json.dumps({"code": 0, "data": {"list": [
                    {"file_name": name, "size": len(data) if data is not None else 0}
                    for name, data in files.get(q.get("folder", [""])[0], {}).items()]}}).encode()
                content = "application/json"
            elif url.path == "/mkdir":
                name = q["name"][0]
                files.setdefault("", {})[name] = None
                files.setdefault(name, {})
                body, content = b"ok", "text/plain"
            else:
                body, content = PAGE.encode(), "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content)
            self.send_header("Set-Cookie", "fixture_session=test; Path=/; SameSite=Lax")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            q = parse_qs(urlsplit(self.path).query)
            data = self.rfile.read(int(self.headers["Content-Length"]))
            name, folder = q["name"][0], q["folder"][0]
            files[folder][name] = data
            uploads.append((folder, name))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    # Windows may allocate 10080 from its dynamic range; Chromium blocks that port.
    while server.server_port == 10080:
        server.server_close()
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/", files, uploads
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def runtime_for(tmp_path, url):
    pytest.importorskip("playwright")
    profile = {"url": url, "hosts": ["127.0.0.1"], "logged_in": ".file-list", "rows": "tr", "folder_ready": "#breadcrumb", "folder_departed": True,
               "upload": "input[type=file]", "new_folder": "新建文件夹", "folder_input": "input[placeholder]",
               "confirm": "确定", "share": "分享", "create_share": "创建链接", "dialog": "[role=dialog]:visible",
               "refresh": "#refresh", "listing_url": "/list",
               "share_notice": "为了共同维护良好的网络环境，每次分享的文件将会经过机器检测，请勿分享非法文件。",
               "expire": "7天"}
    state_dir = tmp_path / "state"
    save_json(state_dir / "profiles" / "fixture.json", profile)
    return BrowserRuntime(state_dir=state_dir, headless=True, notify=lambda _: None, login_timeout=5, timeout=5)


def test_real_browser_upload_share_and_session_reuse(tmp_path, local_disk):
    url, stored, uploads = local_disk
    rt = runtime_for(tmp_path, url)
    file = tmp_path / "中文.txt"
    file.write_text("hello 世界", encoding="utf-8")
    async def scenario():
        async with rt.open("fixture") as (driver, page):
            assert driver.status == "probe"
            # This offscreen, pre-rendered message is present on real Quark pages too.
            restriction = page.get_by_text("账号涉嫌违规已被封禁，暂时无法使用该功能", exact=True)
            assert await restriction.is_visible()
            await driver.check_restriction(page)  # Must not treat it as an account ban.
            targets = await driver.upload(page, [file], "nde-test-body")
            info = await driver.share(page, targets)
            assert info.url == url + "s/fixture" and info.code == "a123"
            assert driver.status == "ready"
        state = json.loads((rt.state_dir / "fixture.json").read_text(encoding="utf-8"))
        assert any(c["name"] == "fixture_session" for c in state["cookies"])
        async with rt.open("fixture") as (driver, page):
            assert any(c["name"] == "fixture_session" for c in await page.context.cookies())
            await driver.upload(page, [file], "nde-test-body")
        assert uploads == [("nde-test-body", file.name)]
        assert stored["nde-test-body"][file.name] == file.read_bytes()
    asyncio.run(scenario())


def test_login_window_remains_until_closed(tmp_path, local_disk, monkeypatch):
    from nde.rpa.drivers import BrowserDiskDriver
    url, _, _ = local_disk
    rt = runtime_for(tmp_path, url)
    original = BrowserDiskDriver.ensure_login
    flags = []
    async def observed(self, context):
        assert self.login_timeout is None
        page = await original(self, context)
        async def user_closes():
            await asyncio.sleep(.7)
            flags.append("user closed")
            await page.close()
        asyncio.create_task(user_closes())
        return page
    monkeypatch.setattr(BrowserDiskDriver, "ensure_login", observed)
    asyncio.run(rt.login("fixture"))
    assert flags == ["user closed"]
    assert rt.login_timeout == 5
    assert (rt.state_dir / "fixture.json").exists()


def test_explicit_login_waits_without_auth_timeout_and_can_close(tmp_path, local_disk, monkeypatch):
    from nde.publish import Paused
    from nde.rpa.drivers import BrowserDiskDriver
    url, _, _ = local_disk
    rt = runtime_for(tmp_path, url)
    rt.login_timeout = .01
    config = rt.profile("fixture")
    config["logged_in"] = "#never-authenticated"
    save_json(rt.state_dir / "profiles" / "fixture.json", config)
    original = BrowserDiskDriver.ensure_login
    async def observed(self, context):
        assert self.login_timeout is None
        async def user_closes():
            await asyncio.sleep(1)
            await context.close()
        asyncio.create_task(user_closes())
        return await original(self, context)
    monkeypatch.setattr(BrowserDiskDriver, "ensure_login", observed)
    with pytest.raises(Paused):
        asyncio.run(rt.login("fixture"))
    assert rt.login_timeout == .01
    assert not (rt.state_dir / "fixture.json").exists()


def test_logged_out_scaffold_does_not_overwrite_last_session(tmp_path, local_disk):
    from nde.rpa.drivers import DriverBlocked
    url, _, _ = local_disk
    rt = runtime_for(tmp_path, url)
    config = rt.profile("fixture")
    config.update(url=url + "?invalid=1", session_invalid="当前设备已被下线，如非本人操作请及时修改密码，避免所存储的数据丢失。")
    save_json(rt.state_dir / "profiles" / "fixture.json", config)
    original = {"cookies": [], "origins": []}
    state = rt.state_dir / "fixture.json"
    save_json(state, original)
    rt.login_timeout = .6
    async def scenario():
        async with rt.open("fixture"):
            pytest.fail("Anonymous file-list scaffold must not authenticate")
    with pytest.raises(DriverBlocked, match="登录未完成"):
        asyncio.run(scenario())
    assert json.loads(state.read_text(encoding="utf-8")) == original


def test_dedicated_persistent_browser_retains_site_state(tmp_path, local_disk):
    url, _, _ = local_disk
    rt = runtime_for(tmp_path, url)
    config = rt.profile("fixture")
    config["persistent"] = True
    config["session_storage"] = True
    save_json(rt.state_dir / "profiles" / "fixture.json", config)
    async def scenario():
        async with rt.open("fixture") as (_, page):
            await page.evaluate("localStorage.setItem('fixture-device', 'same-device')")
            await page.evaluate("sessionStorage.setItem('fixture-session', 'tab-session')")
        assert (rt.state_dir / "browser-data" / "fixture" / "chromium").is_dir()
        async with rt.open("fixture") as (driver, page):
            assert await page.evaluate("localStorage.getItem('fixture-device')") == "same-device"
            assert await page.evaluate("sessionStorage.getItem('fixture-session')") == "tab-session"
            driver.profile["logged_in_nonempty"] = True
            driver.profile["logged_in"] = "#breadcrumb"
            assert not await driver.is_logged_in(page)  # A visible empty shell is insufficient.
    asyncio.run(scenario())


def test_covered_promotion_template_is_not_clicked(tmp_path, local_disk):
    url, _, _ = local_disk
    rt = runtime_for(tmp_path, url)
    async def scenario():
        async with rt.open("fixture") as (driver, page):
            await page.evaluate("""() => {
                const promotion=document.createElement('div');
                promotion.className='couponReceive';
                promotion.innerHTML='<button class="closeIcon" style="position:fixed;left:10px;top:10px;width:60px;height:30px">Close</button>';
                document.body.append(promotion);
                const cover=document.createElement('div');
                cover.style='position:fixed;left:0;top:0;width:100px;height:100px;z-index:99999;background:white';
                document.body.append(cover);
            }""")
            driver.profile["promotion_close"] = ".couponReceive .closeIcon"
            assert await page.locator(driver.profile["promotion_close"]).is_visible()
            await asyncio.wait_for(driver._dismiss_promotions(page), timeout=1)
    asyncio.run(scenario())


def test_share_in_responsive_more_menu(tmp_path, local_disk):
    url, _, _ = local_disk
    rt = runtime_for(tmp_path, url)
    config = rt.profile("fixture")
    config.update(share_scope="#toolbar", share_more="更多")
    save_json(rt.state_dir / "profiles" / "fixture.json", config)
    file = tmp_path / "guide.txt"
    file.write_text("synthetic guide")
    async def scenario():
        async with rt.open("fixture") as (driver, page):
            targets = await driver.upload(page, [file], "nde-more")
            info = await driver.share(page, targets)
            assert info.url == url + "s/fixture"
    asyncio.run(scenario())


def gated_runtime(tmp_path, url):
    runtime = runtime_for(tmp_path, url)
    config = runtime.profile("fixture")
    config.update(url=url + "?gate=1", upload_trigger="#upload-go",
                  account_prompt="请绑定手机号后再继续操作")
    save_json(runtime.state_dir / "profiles" / "fixture.json", config)
    return runtime


def test_account_prerequisite_is_not_bypassed_by_hidden_file_input(tmp_path, local_disk):
    from nde.rpa.drivers import AccountActionRequired
    url, stored, uploads = local_disk
    runtime = gated_runtime(tmp_path, url)
    file = tmp_path / "guide.txt"
    file.write_text("synthetic guide")
    async def scenario():
        async with runtime.open("fixture") as (driver, page):
            with pytest.raises(AccountActionRequired, match="无头模式"):
                await driver.upload(page, [file], "nde-gated")
            assert await page.locator("#account-gate").is_visible()
    asyncio.run(scenario())
    assert uploads == [] and stored["nde-gated"] == {}


def test_upload_resumes_after_owner_completes_account_setup(tmp_path, local_disk):
    url, stored, uploads = local_disk
    runtime = gated_runtime(tmp_path, url)
    file = tmp_path / "guide.txt"
    file.write_text("synthetic guide")
    async def scenario():
        async with runtime.open("fixture") as (driver, page):
            # CI browser is headless; this test's button stands in for a real owner.
            driver.interactive = True
            async def owner():
                await page.locator("#account-gate").wait_for(state="visible")
                await page.locator("#finish-bind").click()
            owner_task = asyncio.create_task(owner())
            await driver.upload(page, [file], "nde-gated")
            await owner_task
    asyncio.run(scenario())
    assert uploads == [("nde-gated", "guide.txt")]
    assert stored["nde-gated"]["guide.txt"] == file.read_bytes()


def test_closed_task_window_pauses_with_saved_authentication(tmp_path, local_disk):
    from nde.publish import Paused
    url, _, _ = local_disk
    runtime = runtime_for(tmp_path, url)
    async def scenario():
        with pytest.raises(Paused, match="任务浏览器已关闭"):
            async with runtime.open("fixture") as (_, page):
                await page.close()  # Owner closes an active publishing browser.
                await page.locator("button").click()
    asyncio.run(scenario())
    assert (runtime.state_dir / "fixture.json").exists()
