"""Self-authored simulated UI, not a copy of the site or its codec.

The fixture deliberately stores JSON in a fake video. These tests prove UI,
isolation and failure handling only; live format compatibility needs --live.
All browser requests are blocked, including localhost: pytest never visits the site.
"""
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from misong.carriers import DecodeRequest, EncodeRequest
from misong.carriers.framewords_web import FramewordsWebCarrier
from misong.text_contracts import ErrorCode, OperationContext, TextOperationError, text_digest


PAGE = """<!doctype html><meta charset=utf-8>
<button id=mode-write>加密模式</button><button id=mode-read>解密模式</button>
<label><input type=radio name=carrier checked>视频加密</label>
<label><input type=radio name=placement checked>标准加密</label>
<input id=encode-file type=file><textarea id=encode-text></textarea>
<span id=text-count>0 / 1000 字</span><input id=encode-password type=password>
<select id=encode-profile><option value=balanced>均衡</option></select>
<button id=encode-submit>写入并校验视频</button><p id=encode-error hidden></p>
<div id=encoded-state hidden><a id=download-video download=fixture.mp4>保存视频</a></div>
<button id=tab-file>本地视频</button><input id=video-file type=file>
<button id=submit>读取隐藏文字</button><p id=input-error hidden></p>
<div id=result-state hidden><textarea id=result-text></textarea></div>
<div id=unlock-state hidden><input id=unlock-password type=password>
<button id=unlock-submit>解锁</button><p id=unlock-error hidden></p></div>
<div id=failure-state hidden><p id=failure-message></p></div>
<script>
const el=id=>document.getElementById(id);
const show=(id,text)=>{el(id).hidden=false;if(text)el(id).textContent=text};
const cfg=CONFIG;
el('text-count').textContent='0 / '+(cfg.limit||1000)+' 字';
let imported;
el('encode-text').oninput=()=>{
 el('text-count').textContent=Array.from(el('encode-text').value).length+' / '+(cfg.limit||1000)+' 字';
 if(cfg.truncate)el('encode-text').value=el('encode-text').value.slice(0,3);
};
el('encode-submit').onclick=()=>{
 if(cfg.hang)return;
 if(cfg.failure){show('failure-state');show('failure-message',cfg.failure);return;}
 if(cfg.disappear){el('encoded-state').remove();return;}
 const blob=new Blob([JSON.stringify({text:el('encode-text').value,password:el('encode-password').value})]);
 el('download-video').href=URL.createObjectURL(blob);
 if(cfg.noDownload)el('download-video').removeAttribute('download');
 show('encoded-state');
};
el('submit').onclick=async()=>{
 if(cfg.readHang)return;
 try { imported=JSON.parse(await el('video-file').files[0].text()); }
 catch {show('failure-state');show('failure-message','媒体损坏');return;}
 // No encoder state is consulted: every context imports only the saved bytes.
 if(imported.password)show('unlock-state');else finish();
};
function finish(){
 el('unlock-state').hidden=true;
 el('result-text').value=cfg.mismatch?'tampered':imported.text;
 show('result-state');
}
el('unlock-submit').onclick=()=>{
 if(el('unlock-password').value!==imported.password)show('unlock-error',cfg.ambiguous?'认证校验失败':'密码错误');
 else finish();
};
</script>"""


class Pages:
    def __init__(self, **config):
        self.config = config
        self.opened = self.closed = self.active = 0
        self.network = []

    @asynccontextmanager
    async def __call__(self):
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(accept_downloads=True)
            assert not context.pages
            await context.route('**/*', lambda route: route.abort())
            context.on('request', lambda request: self.network.append(request.url))
            page = await context.new_page()
            assert self.active == 0, 'encoder must close before independent reader opens'
            self.opened += 1
            self.active += 1
            config = self.config.copy()
            if self.opened > 1:
                config.pop('hang', None)
            await page.set_content(PAGE.replace('CONFIG', json.dumps(config)))
            if config.get('changed'):
                await page.locator('#encode-profile').evaluate('(e)=>e.remove()')
            try:
                yield page
            finally:
                await context.close()
                await browser.close()
                self.active -= 1
                self.closed += 1


@pytest.fixture(autouse=True)
def playwright_available():
    pytest.importorskip('playwright.async_api')


def run(coro):
    return asyncio.run(coro)


def video(tmp_path, text='independent 中文🙂', password=''):
    source = tmp_path / 'input.mp4'
    source.write_text(json.dumps({'text': text, 'password': password}), encoding='utf-8')
    return source


def assert_code(code, call):
    with pytest.raises(TextOperationError) as caught:
        run(call)
    assert caught.value.code == code
    assert str(caught.value) == code.value
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


@pytest.mark.parametrize('password', [None, '', 'fixture-password-中文'])
def test_saved_file_and_new_carrier_independent_decode(tmp_path, password):
    pages = Pages()
    carrier = FramewordsWebCarrier(page_factory=pages)
    source = video(tmp_path)
    original = source.read_bytes()
    output = tmp_path / 'output.mp4'
    text = '  中文🙂 e\u0301\nhttps://example.invalid/s/fixture\t尾\n'
    stages = []
    result = run(carrier.encode(EncodeRequest(source, output, text, password=password),
                                OperationContext(notify=stages.append)))
    assert result.verified and result.path == output
    assert result.payload_sha256 == text_digest(text)
    assert source.read_bytes() == original
    assert pages.opened == pages.closed == 2
    # New Python object and browser contexts get no input text or encoder cache.
    fresh = FramewordsWebCarrier(page_factory=pages)
    assert run(fresh.decode(DecodeRequest(output, password=password), OperationContext())).text == text
    assert pages.opened == pages.closed == 3
    assert not pages.network
    assert set(tmp_path.iterdir()) == {source, output}
    assert all(not hasattr(event, 'text') and not hasattr(event, 'password') for event in stages)


def test_decode_without_ever_encoding(tmp_path):
    pages = Pages()
    source = video(tmp_path, text='file-owned result')
    result = run(FramewordsWebCarrier(page_factory=pages).decode(DecodeRequest(source), OperationContext()))
    assert result.text == 'file-owned result'
    assert pages.opened == pages.closed == 1


@pytest.mark.parametrize('config,code', [
    ({'mismatch': True}, ErrorCode.INTEGRITY),
    ({'changed': True}, ErrorCode.PAGE_CHANGED),
    ({'disappear': True}, ErrorCode.PAGE_CHANGED),
    ({'failure': '组件下载失败'}, ErrorCode.DOWNLOAD),
    ({'failure': '超过当前容量'}, ErrorCode.CAPACITY),
    ({'failure': '承载这些文字至少需要 10 秒视频'}, ErrorCode.CAPACITY),
    ({'failure': '网络连接失败'}, ErrorCode.NETWORK),
    ({'failure': '媒体格式无效'}, ErrorCode.MEDIA),
    ({'truncate': True}, ErrorCode.CAPACITY),
])
def test_failed_encode_never_delivers_or_changes_source(tmp_path, config, code):
    pages = Pages(**config)
    source = video(tmp_path)
    old = source.read_bytes()
    output = tmp_path / 'out.mp4'
    assert_code(code, FramewordsWebCarrier(page_factory=pages).encode(
        EncodeRequest(source, output, 'sensitive-fixture'), OperationContext()))
    assert source.read_bytes() == old
    assert not output.exists()
    assert list(tmp_path.iterdir()) == [source]
    assert pages.opened == pages.closed


@pytest.mark.parametrize('password,code,config', [
    (None, ErrorCode.MISSING_SECRET, {}),
    ('', ErrorCode.MISSING_SECRET, {}),
    ('wrong', ErrorCode.WRONG_PASSWORD, {}),
    ('wrong', ErrorCode.INTEGRITY, {'ambiguous': True}),
])
def test_password_classification(tmp_path, password, code, config):
    pages = Pages(**config)
    source = video(tmp_path, password='correct')
    assert_code(code, FramewordsWebCarrier(page_factory=pages).decode(
        DecodeRequest(source, password=password), OperationContext()))
    assert pages.opened == pages.closed


def test_live_page_capacity_uses_its_counter(tmp_path):
    pages = Pages(limit=2)
    source = video(tmp_path)
    assert_code(ErrorCode.CAPACITY, FramewordsWebCarrier(page_factory=pages).encode(
        EncodeRequest(source, tmp_path / 'out.mp4', '中🙂三'), OperationContext()))
    assert pages.opened == pages.closed == 1


def test_no_download_is_not_success(tmp_path):
    pages = Pages(noDownload=True)
    source = video(tmp_path)
    output = tmp_path / 'out.mp4'
    assert_code(ErrorCode.DOWNLOAD, FramewordsWebCarrier(page_factory=pages).encode(
        EncodeRequest(source, output, 'synthetic'), OperationContext()))
    assert pages.opened == pages.closed == 1
    assert list(tmp_path.iterdir()) == [source]


def test_target_created_during_verification_is_not_overwritten(tmp_path, monkeypatch):
    from misong.carriers import framewords_web
    pages = Pages()
    source = video(tmp_path)
    output = tmp_path / 'out.mp4'
    real_link = os.link
    def competing_writer(staged, destination):
        output.write_bytes(b'competing-writer')
        real_link(staged, destination)
    monkeypatch.setattr(framewords_web.os, 'link', competing_writer)
    assert_code(ErrorCode.IO, FramewordsWebCarrier(page_factory=pages).encode(
        EncodeRequest(source, output, 'synthetic'), OperationContext()))
    assert pages.opened == pages.closed == 2
    assert output.read_bytes() == b'competing-writer'
    assert set(tmp_path.iterdir()) == {source, output}


def test_cancel_at_saved_file_verification_discards_download(tmp_path):
    from misong.text_contracts import Stage
    pages = Pages()
    event = threading.Event()
    def notify(progress):
        if progress.stage == Stage.VERIFY:
            event.set()
    source = video(tmp_path)
    output = tmp_path / 'out.mp4'
    assert_code(ErrorCode.CANCELLED, FramewordsWebCarrier(page_factory=pages).encode(
        EncodeRequest(source, output, 'synthetic'), OperationContext(cancel=event, notify=notify)))
    assert pages.opened == pages.closed == 1
    assert list(tmp_path.iterdir()) == [source]


def test_invalid_media_decode_does_not_return_partial_text(tmp_path):
    pages = Pages()
    source = tmp_path / 'broken.mp4'
    source.write_bytes(b'not a fixture video')
    assert_code(ErrorCode.MEDIA, FramewordsWebCarrier(page_factory=pages).decode(
        DecodeRequest(source), OperationContext()))
    assert pages.opened == pages.closed == 1


@pytest.mark.parametrize('text,mode,code', [
    ('x' * (1024 * 1024 + 1), 'standard', ErrorCode.CAPACITY),
    ('', 'standard', ErrorCode.INVALID_RECIPE),
    ('synthetic', 'audio', ErrorCode.UNSUPPORTED),
], ids=['oversize', 'empty', 'unsupported-mode'])
def test_preflight_before_browser(tmp_path, text, mode, code):
    source = video(tmp_path)
    pages = Pages()
    assert_code(code, FramewordsWebCarrier(page_factory=pages).encode(
        EncodeRequest(source, tmp_path / 'out.mp4', text, mode=mode), OperationContext()))
    assert pages.opened == 0


@pytest.mark.parametrize('same_source', [True, False])
def test_no_overwrite_even_source_alias(tmp_path, same_source):
    source = video(tmp_path)
    destination = source if same_source else tmp_path / 'existing.mp4'
    if not same_source:
        destination.write_bytes(b'keep')
    before = destination.read_bytes()
    pages = Pages()
    assert_code(ErrorCode.IO, FramewordsWebCarrier(page_factory=pages).encode(
        EncodeRequest(source, destination, 'fixture'), OperationContext()))
    assert destination.read_bytes() == before
    assert pages.opened == 0


@pytest.mark.parametrize('operation', ['encode', 'decode'])
def test_deadline_and_cancel_before_browser(tmp_path, operation):
    pages = Pages()
    carrier = FramewordsWebCarrier(page_factory=pages)
    source = video(tmp_path)
    request = (EncodeRequest(source, tmp_path / 'out.mp4', 'secret') if operation == 'encode'
               else DecodeRequest(source))
    context = OperationContext(deadline=time.monotonic() - 1)
    assert_code(ErrorCode.TIMEOUT, getattr(carrier, operation)(request, context))
    event = threading.Event()
    event.set()
    assert_code(ErrorCode.CANCELLED, getattr(carrier, operation)(request, OperationContext(cancel=event)))
    assert pages.opened == 0


@pytest.mark.parametrize('kind', ['timeout', 'signal', 'task'])
def test_interrupt_wait_cleans_up(tmp_path, kind):
    pages = Pages(hang=True)
    source = video(tmp_path)
    output = tmp_path / 'out.mp4'
    event = threading.Event()
    async def operation():
        carrier = FramewordsWebCarrier(page_factory=pages, timeout=15)
        context = OperationContext(cancel=event)
        task = asyncio.create_task(carrier.encode(EncodeRequest(source, output, 'private'), context))
        while pages.opened == 0:
            await asyncio.sleep(.02)
        await asyncio.sleep(.4)
        if kind == 'signal':
            event.set()
        elif kind == 'task':
            task.cancel()
        else:
            # A monotonic absolute deadline includes browser waits and startup.
            object.__setattr__(context, 'deadline', time.monotonic())
        return await task
    assert_code(ErrorCode.TIMEOUT if kind == 'timeout' else ErrorCode.CANCELLED, operation())
    assert pages.opened == pages.closed == 1
    assert not output.exists()
    assert list(tmp_path.iterdir()) == [source]


def test_sensitive_exception_redacted_even_exception_context(tmp_path, capsys, caplog):
    @asynccontextmanager
    async def bad_factory():
        raise RuntimeError('secret-text secret-password sensitive-url')
        yield
    source = video(tmp_path)
    assert_code(ErrorCode.PAGE_CHANGED, FramewordsWebCarrier(page_factory=bad_factory).decode(
        DecodeRequest(source), OperationContext()))
    output = capsys.readouterr()
    assert output.out == output.err == caplog.text == ''


@pytest.mark.parametrize('phase', ['startup', 'launch', 'body', 'cleanup'])
def test_production_runtime_cleanup_at_cancellation_boundaries(monkeypatch, phase):
    import playwright.async_api
    async def exercise():
        entered = asyncio.Event()
        release = asyncio.Event()
        closed = []
        async def pause(at):
            if phase == at:
                entered.set()
                await release.wait()
        class Context:
            async def new_page(self):
                return object()
            async def close(self):
                await pause('cleanup')
                closed.append('context')
        class Browser:
            async def new_context(self, **kwargs):
                assert kwargs == {'accept_downloads': True, 'locale': 'zh-CN'}
                return Context()
            async def close(self):
                closed.append('browser')
        class Chromium:
            async def launch(self, **kwargs):
                await pause('launch')
                return Browser()
        class Manager:
            chromium = Chromium()
            async def stop(self):
                closed.append('driver')
        class Start:
            async def start(self):
                await pause('startup')
                return Manager()
        monkeypatch.setattr(playwright.async_api, 'async_playwright', Start)
        async def operation():
            async with FramewordsWebCarrier()._page():
                await pause('body')
        task = asyncio.create_task(operation())
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert 'driver' in closed
        if phase in ('body', 'cleanup'):
            assert closed == ['context', 'browser', 'driver']
    run(exercise())


def test_unverified_factory_cannot_advertise_live_support():
    caps = FramewordsWebCarrier(page_factory=Pages()).capabilities()
    assert not caps.can_encode and not caps.can_decode
    assert caps.modes == caps.verified_versions == ()
    assert caps.max_characters is None and caps.max_utf8_bytes is None


@pytest.mark.parametrize('name,value', [('PWDEBUG', '1'), ('DEBUG', 'pw:api'), ('DEBUG', '*')])
def test_refuse_driver_debug_that_can_log_fill_values(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    async def operation():
        async with FramewordsWebCarrier()._page():
            pytest.fail('unsafe debug environment must be rejected before browser startup')
    assert_code(ErrorCode.UNSUPPORTED, operation())


def test_import_does_not_load_playwright_and_script_requires_live():
    command = 'import sys; import misong.carriers.framewords_web; assert "playwright" not in sys.modules'
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(root / 'src'))
    subprocess.run([sys.executable, '-c', command], check=True, cwd=root / 'tests', env=env)
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'verify_framewords_web.py'
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert result.returncode == 2
    assert '--live' in result.stderr
