"""Baidu web-driver behaviour, served entirely by local Playwright routing."""
import asyncio
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from nde.rpa.drivers import REGISTRY, DriverBlocked
from nde.share_options import ShareOptions, common_options

URL = "https://pan.baidu.com/disk/main#/index?category=all"

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"></head><body>
<div class="wp-s-aside-nav">我的文件</div>
<div class="nd-user-info">fixture-user</div>
<div class="wp-s-agile-tool-bar">
  <span id="newfolder">新建文件夹</span>
  <button class="wp-s-agile-tool-bar__h-action-button" id="shareBtn" style="display:none">分享</button>
  <textarea class="u-textarea__inner" id="newname" style="display:none"></textarea>
</div>
<div class="wp-s-pan-table"><div id="rows"></div></div>
<input type="file" name="html5uploader">
<div role="dialog" aria-label="分享文件(夹):fixture" hidden>
  <div id="pane-link">
    <div class="group" id="expiry">
      <label role="radio" aria-checked="false"><input type="radio" value="1">1天</label>
      <label role="radio" aria-checked="false"><input type="radio" value="7">7天</label>
      <label role="radio" aria-checked="false"><input type="radio" value="30">30天</label>
      <label role="radio" aria-checked="true"><input type="radio" value="365">365天</label>
      <label role="radio" aria-checked="false"><input type="radio" value="0">永久有效</label>
    </div>
    <div class="group" id="pwd">
      <label role="radio" aria-checked="true"><input type="radio" value="random">随机生成</label>
      <label role="radio" aria-checked="false"><input type="radio" value="custom">自定义</label>
    </div>
    <button type="button" class="wp-share-file__link-create-ubtn"><span>复制链接</span></button>
  </div>
</div>
<script>
const path = () => new URLSearchParams(location.hash.split('?')[1] || '').get('path') || '/';
let expiry = '365';
function selected() {
  return document.querySelector('#shareBtn').style.display !== 'none';
}
async function rows() {
  const data = await (await fetch('/api/list?dir=' + encodeURIComponent(path()))).json();
  const box = document.querySelector('#rows');
  box.innerHTML = '';
  for (const item of data.list || []) {
    const row = document.createElement('div');
    row.className = 'wp-s-pan-table__body-row';
    const block = document.createElement('div');
    block.className = 'wp-s-pan-table__body-row--checkbox-block';
    block.style.cssText = 'display:inline-block;width:18px;height:18px';
    block.onclick = () => {
      document.querySelectorAll('.selected').forEach(e => e.classList.remove('selected'));
      row.classList.add('selected');
      document.querySelector('#shareBtn').style.display = '';
    };
    const a = document.createElement('a');
    a.className = 'list-name-text';
    a.textContent = item.server_filename;
    if (item.isdir) {
      a.ondblclick = () => {
        location.hash = '#/index?category=all&path=' + encodeURIComponent('/' + item.server_filename);
      };
    }
    row.append(block, a);
    box.append(row);
  }
}
window.addEventListener('hashchange', rows);
document.querySelector('#newfolder').onclick = () => {
  const input = document.querySelector('#newname');
  input.style.display = '';
  input.value = '';
};
document.querySelector('#newname').onkeydown = async (e) => {
  if (e.key !== 'Enter') return;
  await fetch('/api/create', {method: 'POST', body: JSON.stringify({name: e.target.value})});
  e.target.style.display = 'none';
  rows();
};
document.querySelector('input[type=file]').onchange = async (e) => {
  for (const file of e.target.files) {
    await fetch('/api/upload', {method: 'POST', body: JSON.stringify({dir: path(), name: file.name, size: file.size})});
  }
  rows();
};
document.querySelector('#shareBtn').onclick = () => {
  document.querySelector('[role=dialog]').hidden = false;
};
for (const group of document.querySelectorAll('.group')) {
  for (const radio of group.querySelectorAll('[role=radio]')) {
    radio.onclick = () => {
      for (const other of group.querySelectorAll('[role=radio]')) other.setAttribute('aria-checked', 'false');
      radio.setAttribute('aria-checked', 'true');
      if (group.id === 'expiry') expiry = radio.querySelector('input').value;
    };
  }
}
document.querySelector('.wp-share-file__link-create-ubtn').onclick = () => {
  fetch('/share/pset', {method: 'POST', body: JSON.stringify({expiry})});
};
rows();
</script></body></html>"""


class FakeBaidu:
    def __init__(self):
        self.folders = {}
        self.uploads = 0
        self.force_expiry = None
        self.code = "ab12"
        self.last_share = None

    def entries(self, path):
        if path in ("", "/"):
            return [{"server_filename": name, "size": 0, "isdir": 1} for name in sorted(self.folders)]
        files = self.folders.get(path.lstrip("/"), {})
        return [{"server_filename": name, "size": size, "isdir": 0} for name, size in sorted(files.items())]

    async def route(self, route):
        request = route.request
        url = request.url
        path = urlsplit(url).path
        if path == "/api/list":
            directory = parse_qs(urlsplit(url).query).get("dir", ["/"])[0]
            await route.fulfill(status=200, content_type="application/json",
                                body=json.dumps({"errno": 0, "list": self.entries(directory)}))
        elif path == "/api/create":
            data = json.loads(request.post_data or "{}")
            self.folders.setdefault(data["name"], {})
            await route.fulfill(status=200, content_type="application/json", body='{"errno":0}')
        elif path == "/api/upload":
            data = json.loads(request.post_data or "{}")
            self.folders.setdefault(data["dir"].lstrip("/"), {})[data["name"]] = data["size"]
            self.uploads += 1
            await route.fulfill(status=200, content_type="application/json", body='{"errno":0}')
        elif path == "/share/pset":
            data = json.loads(request.post_data or "{}")
            expired = str(data.get("expiry"))
            if self.force_expiry is not None:
                expired = str(self.force_expiry)
            pwd = f"&pwd={self.code}" if self.code else ""
            body = {"errno": 0, "link": "https://pan.baidu.com/s/fixture-1", "expiredType": expired,
                    "qrcodeurl": f"https://pan.baidu.com/api/wechat/qrcode?shorturl=x{pwd}&x=1"}
            self.last_share = body
            await route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
        else:
            await route.fulfill(status=200, content_type="text/html; charset=utf-8", body=PAGE)


def make_files(tmp_path, count=2):
    files = [tmp_path / f"part{i:03}.bin" for i in range(1, count + 1)]
    for i, file in enumerate(files):
        file.write_bytes(b"baidu fixture " + bytes([i]))
    return files


def run(coro):
    asyncio.run(coro)


def test_baidu_upload_share_resume_and_login_marker(tmp_path):
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright

    files = make_files(tmp_path)

    async def scenario():
        fake = FakeBaidu()
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.route("**/*", fake.route)
            await page.goto(URL)
            driver = REGISTRY["baidu"](timeout=4, login_timeout=2, notify=lambda _: None)
            assert await driver.is_logged_in(page)
            await page.locator(".nd-user-info").evaluate("el => el.remove()")
            assert not await driver.is_logged_in(page)
            await page.reload()
            await page.locator(".nd-user-info").wait_for(state="visible")

            targets = await driver.upload(page, files, "nde-test")
            assert targets == ["nde-test"]
            assert await driver.rows(page, files[0].name).count() == 1
            assert await driver.rows(page, files[1].name).count() == 1
            await driver.upload(page, files, "nde-test")  # Same session must not reupload.
            assert fake.uploads == len(files)

            driver.configure_share(ShareOptions("7", "code"))
            info = await driver.share(page, targets)
            assert driver.status == "ready"
            assert info.disk == "baidu"
            assert info.url == "https://pan.baidu.com/s/fixture-1"
            assert info.code == "ab12"
            assert info.expire == "7天"
            assert fake.last_share["expiredType"] == "7"

            resumed = REGISTRY["baidu"](timeout=4, login_timeout=2, notify=lambda _: None)
            await resumed.upload(page, files, "nde-test")  # Fresh driver reuses listed sizes.
            assert fake.uploads == len(files)
            await browser.close()

    run(scenario())


def test_baidu_rejects_size_mismatch_in_task_folder(tmp_path):
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright

    files = make_files(tmp_path, 1)

    async def scenario():
        fake = FakeBaidu()
        fake.folders["nde-test"] = {files[0].name: files[0].stat().st_size + 1}
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.route("**/*", fake.route)
            await page.goto(URL)
            driver = REGISTRY["baidu"](timeout=4, login_timeout=2, notify=lambda _: None)
            with pytest.raises(DriverBlocked, match="大小不符"):
                await driver.upload(page, files, "nde-test")
            assert fake.uploads == 0
            await browser.close()

    run(scenario())


def test_baidu_missing_code_and_option_mismatch_are_blocked(tmp_path):
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright

    files = make_files(tmp_path, 1)

    async def scenario():
        fake = FakeBaidu()
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.route("**/*", fake.route)
            await page.goto(URL)
            driver = REGISTRY["baidu"](timeout=3, login_timeout=2, notify=lambda _: None)
            targets = await driver.upload(page, files, "nde-test")
            driver.configure_share(ShareOptions("7", "code"))
            fake.code = ""
            with pytest.raises(DriverBlocked, match="提取码"):
                await driver.share(page, targets)
            fake.code = "ab12"
            fake.force_expiry = 365
            with pytest.raises(DriverBlocked, match="实际 365"):
                await driver.share(page, targets)
            await browser.close()

    run(scenario())


def test_baidu_capabilities_and_gui_choices(tmp_path):
    from nde.desktop.api import Api
    expiry, access = common_options(["baidu"])
    assert expiry == ["default", "1", "7", "30", "365", "forever"]
    assert access == ["default", "code"]
    assert common_options(["baidu", "quark"])[1] == ["default", "code"]
    assert "365" not in common_options(["baidu", "quark"])[0]
    api = Api(runs_dir=tmp_path / "runs", state_dir=tmp_path / "state")
    meta = api.bootstrap()["data"]
    baidu = next(p for p in meta["providers"] if p["key"] == "baidu")
    assert baidu["auto"] is True
    choices = api.share_choices(["baidu"])["data"]
    assert [o["key"] for o in choices["access"]] == ["default", "code"]
    assert any(o["key"] == "365" for o in choices["expiry"])
    with pytest.raises(ValueError):
        ShareOptions("7", "none").validate_disk("baidu")
