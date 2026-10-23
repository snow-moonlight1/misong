"""Clipboard path ingestion uses the same real bridge as file pickers."""
import importlib.util
from pathlib import Path

import pytest

from nde.desktop.api import Api


def test_clipboard_paths_quotes_multiple_dedup_and_upload_expansion(tmp_path):
    pw = pytest.importorskip('playwright.sync_api')
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('preview_for_clipboard', root / 'scripts/ui_preview.py')
    preview = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preview)
    api = Api(tmp_path / 'runs', tmp_path / 'state')
    fake = preview.Fake(api)
    folder = tmp_path / '中文 空格'
    folder.mkdir()
    a = folder / 'first.bin'; a.write_bytes(b'first')
    b = tmp_path / 'second.bin'; b.write_bytes(b'second')

    clipboard = {'text': '', 'denied': False}

    def bridge(method, args):
        if method == 'clipboard_paths':
            if clipboard['denied']:
                return {'ok': False, 'error': 'clipboard unavailable'}
            return {'ok': True, 'data': [s.strip().strip(chr(34)) for s in clipboard['text'].splitlines() if s.strip()]}
        if method in ('describe_paths', 'folder_files'):
            return getattr(api, method)(*args)
        return fake(method, args)

    with pw.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.expose_function('__py', bridge)
        page.add_init_script(preview.MOCK_JS)
        page.goto(preview.WEB.as_uri())
        page.wait_for_selector('.page.active [data-act="paste-paths"]')
        clipboard['text'] = f'"{a}"\r\n"{b}"\r\n{a}\r\n'
        page.locator('.page.active [data-act="paste-paths"]').click()
        page.wait_for_function('window.__NDE_APP__.S.pipeline.inputs.length===2')
        assert page.evaluate('window.__NDE_APP__.S.pipeline.inputs.map(f=>f.path)') == [str(a), str(b)]
        page.get_by_role('button', name='上传分享', exact=True).click()
        clipboard['text'] = str(folder)
        page.locator('.page.active [data-act="paste-paths"]').click()
        page.wait_for_function('window.__NDE_APP__.S.upload.files.length===1')
        assert page.evaluate('window.__NDE_APP__.S.upload.files[0].path') == str(a)
        clipboard['text'] = ''
        page.locator('.page.active [data-act="paste-paths"]').click()
        page.get_by_text('剪贴板里没有路径，请先复制文件的完整路径', exact=True).wait_for()
        clipboard['denied'] = True
        page.locator('.page.active [data-act="paste-paths"]').click()
        page.get_by_text('无法读取剪贴板，请使用选择文件或拖放', exact=True).wait_for()
        assert page.evaluate('window.__NDE_APP__.S.upload.files.length') == 1
        browser.close()


def test_clipboard_bridge_parses_paths_and_redacts_read_errors(tmp_path, monkeypatch):
    import nde.desktop.api as bridge
    api = Api(tmp_path / 'runs', tmp_path / 'state')
    monkeypatch.setattr(bridge, '_clipboard_text', lambda: '\r\n"C:\\test 空格\\a.bin"\r\nD:\\other.bin\n')
    assert api.clipboard_paths() == {'ok': True, 'data': [r'C:\test 空格\a.bin', r'D:\other.bin']}
    def fail():
        raise RuntimeError('private-clipboard-text')
    monkeypatch.setattr(bridge, '_clipboard_text', fail)
    result = api.clipboard_paths()
    assert not result['ok'] and 'private-clipboard-text' not in str(result)
    assert not list((tmp_path / 'state').rglob('*clipboard*'))


@pytest.mark.parametrize('width', [940, 1090, 1320])
def test_file_actions_do_not_squeeze_drop_instructions(tmp_path, width):
    pw = pytest.importorskip('playwright.sync_api')
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('preview_for_drop_layout', root / 'scripts/ui_preview.py')
    preview = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preview)
    fake = preview.Fake(Api(tmp_path / 'runs', tmp_path / 'state'))
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': width, 'height': 900})
        page.expose_function('__py', fake)
        page.add_init_script(preview.MOCK_JS)
        page.goto(preview.WEB.as_uri())
        page.wait_for_selector('.page.active [data-act="paste-paths"]')
        for module in ('一条龙发布', '加密打包', '上传分享'):
            page.get_by_role('button', name=module, exact=True).click()
            zone = page.locator('.page.active .drop').first
            title = zone.locator('.drop-text b').bounding_box()
            bounds = zone.bounding_box()
            assert title['width'] >= 180
            assert title['height'] < 65, (module, width, title)
            for button in zone.locator('button').all():
                button_bounds = button.bounding_box()
                assert bounds['x'] <= button_bounds['x']
                assert button_bounds['x'] + button_bounds['width'] <= bounds['x'] + bounds['width']
                assert button_bounds['y'] >= title['y'] + title['height']
        browser.close()
