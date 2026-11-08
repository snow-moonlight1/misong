"""E package: step-4 delivery recipes and text-restore UI (mock bridge + real backend checks)."""
import asyncio
import importlib.util
import json
import time
from pathlib import Path

import pytest

from misong import text_delivery
from misong.desktop.api import Api
from misong.text_contracts import OperationContext
from misong.text_layers import DeliveryRecipe, TextLayer

pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[1]
SECRETS = ("inner-ui-secret", "outer-ui-secret")


def load_preview():
    spec = importlib.util.spec_from_file_location("text_ui_preview", ROOT / "scripts/ui_preview.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ui(tmp_path):
    from playwright.sync_api import sync_playwright
    preview = load_preview()
    api = Api(tmp_path / "runs", tmp_path / "state")
    fake = preview.Fake(api)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1180, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.expose_function("__py", lambda m, a: json.loads(json.dumps(fake(m, a), ensure_ascii=False)))
        page.add_init_script(preview.MOCK_JS)
        page.goto(preview.WEB.as_uri())
        page.wait_for_selector(".page.active [data-mount='run'] .run")
        yield page, fake, api, errors
        browser.close()


def to_step4(page):
    page.evaluate("""() => { const A = window.__MISONG_APP__, p = A.S.pipeline;
      p.inputs = [{path: 'D:\\\\资源\\\\S01E01.mkv', name: 'S01E01.mkv', dir: false, size: 1}];
      p.layers = [{type: 'archive', fmt: '7z', password: 'pack-pw', header_enc: true}];
      p.disks = ['quark']; p._step = 4; A.rerender('pipeline'); }""")
    page.wait_for_timeout(400)


def requests(fake, method):
    return [args for m, args in fake.requests if m == method]


def test_recipe_editor_payload_keys_off_and_no_secret_in_settings(ui):
    page, fake, api, errors = ui
    to_step4(page)
    page.click(".page.active [data-tmode='recipes']")
    page.click(".page.active [data-radd='mojibake-video']")
    page.click(".page.active [data-radd='base64']")
    exports = page.locator(".page.active [data-rexport]")
    assert exports.count() == 2 and not exports.nth(0).is_checked() and not exports.nth(1).is_checked()
    text = page.locator(".page.active [data-mount='schemes']").inner_text()
    assert "仅编码，不提供密码保护" in text and "需要联网" in text and "不是离线编解码" in text
    assert "≈" in text  # per-layer character estimate
    run = page.locator(".page.active [data-run='publish']")
    assert run.is_disabled()  # missing secrets / video
    page.fill(".page.active [data-recipe='0'] input[data-secret$='/l1']", SECRETS[0])
    page.click(".page.active [data-recipe='0'] [data-rvideo]")
    page.wait_for_timeout(300)
    page.fill(".page.active [data-recipe='0'] input[data-secret$='/video']", SECRETS[1])
    page.locator(".page.active [data-recipe='0'] input[data-secret$='/video']").dispatch_event("change")
    page.check(".page.active [data-recipe='1'] [data-rexport]")
    # reorder: add a second layer to recipe 2 and move it up
    page.click(".page.active [data-recipe='1'] [data-tladd]")
    page.select_option(".page.active [data-recipe='1'] [data-tl='1'] [data-tlscheme]", "hex")
    page.click(".page.active [data-recipe='1'] [data-tl='1'] [data-tlup]")
    page.wait_for_timeout(500)
    page.wait_for_function("() => !document.querySelector(\".page.active [data-run='publish']\").disabled")
    page.click(".page.active [data-run='publish']")
    page.wait_for_function("() => !!window.__MISONG_APP__.S.job")
    cfg = requests(fake, "start_pipeline")[-1][0]
    assert cfg["schemes"] == [] and len(cfg["recipes"]) == 2
    assert [layer["scheme"] for layer in cfg["recipes"][1]["layers"]] == ["hex", "base64"]
    assert cfg["export_text_keys"] == [cfg["recipes"][1]["id"]]
    assert set(cfg["text_secrets"].values()) == set(SECRETS)
    assert list(cfg["text_video_sources"]) == [cfg["recipes"][0]["id"]]
    # Public recipes are accepted by the real backend parser; secrets never in them.
    parsed = text_delivery.parse_recipes(cfg["recipes"])
    assert parsed[0].carrier.format_id == "framewords" and parsed[0].carrier.secret_slot
    assert not any(s in json.dumps(cfg["recipes"]) for s in SECRETS)
    for _, args in [r for r in fake.requests if r[0] == "save_settings"]:
        assert not any(s in json.dumps(args, ensure_ascii=False) for s in SECRETS)
    fake.finish("pipeline-recipes")
    page.get_by_text("全部交付完成", exact=True).wait_for(timeout=10000)
    assert not errors


def test_failed_step4_resume_passes_text_cfg_only(ui):
    page, fake, api, errors = ui
    to_step4(page)
    page.click(".page.active [data-tmode='recipes']")
    page.click(".page.active [data-radd='plain']")
    page.evaluate("""() => { const A = window.__MISONG_APP__;
      A.S.pipeline.result = {error: '分享完成、文案未完成', plan: 'D:\\\\misong\\\\runs\\\\a\\\\relay-plan.json'};
      A.rerender('pipeline'); }""")
    page.click(".page.active [data-resume]")
    page.wait_for_function("() => !!window.__MISONG_APP__.S.job")
    args = requests(fake, "resume_task")[-1]
    assert len(args) == 4 and set(args[3]) == {"secrets", "video_sources", "export_keys"}
    assert args[3]["export_keys"] == []
    assert not errors


def test_legacy_schemes_mode_unchanged(ui):
    page, fake, api, errors = ui
    to_step4(page)
    assert page.locator(".page.active [data-tmode='legacy'].on").count() == 1
    page.wait_for_function("() => !document.querySelector(\".page.active [data-run='publish']\").disabled")
    page.click(".page.active [data-run='publish']")
    page.wait_for_function("() => !!window.__MISONG_APP__.S.job")
    cfg = requests(fake, "start_pipeline")[-1][0]
    assert "recipes" not in cfg and cfg["schemes"]
    assert not errors


def wait_job(api):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        for event in api.poll()["data"]["events"]:
            if event["type"] == "job" and event["state"] != "running":
                return event
        time.sleep(.02)
    pytest.fail("job timed out")


def test_text_restore_page_drives_real_backend(ui, tmp_path):
    page, fake, api, errors = ui
    original = "https://example.invalid/s/ui-test 提取码:abcd\r\n"
    recipe = DeliveryRecipe(1, "enc", "编码", (TextLayer("a", "base64"), TextLayer("b", "hex")))
    # Playwright's sync API owns this thread's event loop; run the real backend elsewhere.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(1) as pool:
        pool.submit(asyncio.run, text_delivery.deliver_text(
            original, (recipe,), tmp_path / "delivered", OperationContext(), export_keys=["enc"])).result()
    folder = tmp_path / "delivered" / "enc"
    page.click(".nav-item[data-page='textrestore']")
    page.wait_for_timeout(300)
    run = page.locator(".page.active [data-run='go']")
    assert run.is_disabled()
    page.click(".page.active [data-trkind='video']")
    assert "需联网" in page.locator(".page.active").inner_text()
    page.click(".page.active [data-trkind='text']")
    page.fill(".page.active [data-trtext]", text_delivery.read_text_file(folder / "message.txt"))
    page.locator(".page.active [data-trtext]").dispatch_event("change")
    fake.next_pick = [str(folder / "message.tkey")]
    page.click(".page.active [data-trpick='key']")
    page.wait_for_function("() => !document.querySelector(\".page.active [data-run='go']\").disabled")
    run.click()
    page.wait_for_function("() => window.__MISONG_APP__.S.job?.kind === 'text-restore'")
    cfg = requests(fake, "start_text_restore")[-1][0]
    assert set(cfg) == {"text", "key_file", "secrets"}
    assert api.start_text_restore(cfg)["ok"]  # same payload against the real bridge
    event = wait_job(api)
    assert event["state"] == "done" and event["result"]["verified"]
    assert Path(event["result"]["out"]).read_bytes() == original.encode("utf-8")
    fake.finish("text-restore")
    page.get_by_text("文案还原完成", exact=True).wait_for(timeout=10000)
    assert not errors


def test_manual_recipe_restore_prompts_for_slots(ui):
    page, fake, api, errors = ui
    page.click(".nav-item[data-page='textrestore']")
    page.click(".page.active [data-trmanual='1']")
    recipe = DeliveryRecipe(1, "m", "魔曰", (TextLayer("x", "mojibake", secret_slot="m/x"),)).to_dict()
    page.fill(".page.active [data-trrecipe]", json.dumps(recipe))
    page.locator(".page.active [data-trrecipe]").dispatch_event("change")
    page.wait_for_selector(".page.active [data-trsecret='m/x']")
    page.fill(".page.active [data-trtext]", "曰：示例")
    page.locator(".page.active [data-trtext]").dispatch_event("change")
    page.fill(".page.active [data-trsecret='m/x']", SECRETS[0])
    page.wait_for_function("() => !document.querySelector(\".page.active [data-run='go']\").disabled")
    page.click(".page.active [data-run='go']")
    page.wait_for_function("() => !!window.__MISONG_APP__.S.job")
    cfg = requests(fake, "start_text_restore")[-1][0]
    assert cfg["recipe"] == recipe and cfg["secrets"] == {"m/x": SECRETS[0]} and "key_file" not in cfg
    assert not errors


def test_task_center_resume_collects_only_pending_recipe_secrets(ui):
    page, fake, api, errors = ui
    page.set_viewport_size({"width": 940, "height": 880})
    r = DeliveryRecipe(1, "pending", "待重试方案", (TextLayer("magic", "mojibake", secret_slot="pending/magic"),)).to_dict()
    fake.edits[r"D:\misong\runs\a"].update(
        state="blocked", delivery={"label": "分享完成、文案未完成", "recipes": []},
        resume_requirements={"recipes": [r], "legacy_key": False, "hop_password": False})
    page.click(".nav-item[data-page='tasks']")
    page.click("#tasksRefresh")
    page.wait_for_function("() => document.querySelector('#taskDetail').textContent.includes('分享完成、文案未完成')")
    title = page.locator("#taskDetail .detail-title").bounding_box()
    actions = page.locator("#taskDetail .detail-actions").bounding_box()
    assert title["width"] >= 180 and actions["y"] >= title["y"] + title["height"]
    assert page.locator("#taskDetail h2").bounding_box()["height"] < 60
    assert page.locator("#taskDetail .detail-actions [data-edit]").count() == 1
    assert page.locator("#taskDetail .detail-head [data-edit]").count() == 0
    assert page.locator("#taskDetail .path-link[data-open]").inner_text() == r"D:\misong\runs\a"
    page.click("#taskDetail [data-resume]")
    page.wait_for_selector("#modal [data-resume-secret='pending/magic']")
    assert page.locator("#modal [data-resume-export]:checked").count() == 0
    page.fill("#modal [data-resume-secret='pending/magic']", SECRETS[0])
    page.click("#modal [data-go]")
    page.wait_for_function("() => !!window.__MISONG_APP__.S.job")
    args = requests(fake, "resume_task")[-1]
    assert args[3] == {"secrets": {"pending/magic": SECRETS[0]}, "video_sources": {}, "export_keys": []}
    assert page.locator("#modal").is_hidden()
    for name, args in fake.requests:
        if name == "save_settings":
            assert SECRETS[0] not in json.dumps(args)
    assert not errors


def test_imported_template_applies_options_and_exact_public_recipe(ui):
    page, fake, api, errors = ui
    r = DeliveryRecipe(1, "imported", "文案", (TextLayer("magic", "mojibake", params={"mode": "old"}, secret_slot="custom/slot"),)).to_dict()
    page.evaluate("""r => {const A=window.__MISONG_APP__;
      A.S.meta.templates=[{name:'导入测试',layers:[{fmt:'7z',locked:true,header_enc:true}],
        options:{checksum:true,raw_merge:false},text_recipes:[r]}];
      A.S.pipeline._step=2; A.rerender('pipeline'); }""", r)
    page.click(".page.active [data-tpl='0']")
    result = page.evaluate("""() => {const A=window.__MISONG_APP__,p=A.S.pipeline;
      return {recipe:A.recipeToPublic(p.recipes[0]),checksum:p.checksum,secrets:p.textSecrets,exports:p.exportKeys};} """)
    assert result == {"recipe": r, "checksum": True, "secrets": {}, "exports": []}
    assert not errors


def test_settings_and_batch_check_controls_are_wired(ui):
    page, fake, api, errors = ui
    page.click(".nav-item[data-page='settings']")
    page.wait_for_timeout(200)
    assert page.locator(".page.active [data-settings-action]").count() == 1
    assert page.locator(".page.active h1").inner_text() == "诊断"
    page_text = page.locator(".page.active").inner_text()
    assert "不含密码、密钥、会话和截图" in page_text
    assert page.locator("#diagScreenshots").count() == 0
    pick = page.locator("#diagTaskPick")
    assert pick.input_value() == ""
    assert pick.locator("option").first.inner_text() == "不附带"
    assert "纪录片合集" in pick.inner_text()
    page.click(".page.active [data-settings-action]")
    page.wait_for_timeout(300)
    path, tasks, logs = requests(fake, "export_diagnostics")[-1]
    assert tasks == [] and isinstance(logs, list)
    assert "已导出" in page.locator("#settingsResult").inner_text()
    page.select_option("#diagTaskPick", r"D:\misong\runs\a")
    page.click(".page.active [data-settings-action]")
    page.wait_for_timeout(300)
    assert requests(fake, "export_diagnostics")[-1][1] == [r"D:\misong\runs\a"]
    page.click(".nav-item[data-page='accounts']")
    assert not page.locator("#selfcheckSnapshots").is_checked()
    page.click("#accountsCheckAll")
    page.wait_for_function("() => !!window.__MISONG_APP__.S.job")
    assert requests(fake, "check_accounts")[-1] == []
    assert not errors


def test_accounts_plain_chinese_results_and_troubleshoot_wiring(ui):
    page, fake, api, errors = ui
    page.click(".nav-item[data-page='accounts']")
    page.wait_for_timeout(300)
    card = page.locator(".acct[data-acct='quark']")
    assert card.locator("[data-op='check']").inner_text().strip() == "检查登录"
    assert card.locator("[data-op='login']").count() == 1
    assert card.locator("[data-op='selfcheck']").count() == 0
    assert "曾通过测试" in card.inner_text()
    assert page.locator("#accountsCheckAll").inner_text() == "检查全部登录"
    assert page.evaluate("() => !document.querySelector('#accountTroubleshoot').open")
    assert not page.locator("#selfcheckSnapshots").is_checked()
    assert "状态说明" not in page.locator(".page.active").inner_text()
    page.click("#accountTroubleshoot summary")
    page.select_option("#selfcheckDisk", "uc")
    page.click("#selfcheckRun")
    page.wait_for_function("() => !!window.__MISONG_APP__.S.job")
    assert requests(fake, "selfcheck")[-1] == ["uc", "chrome", False]
    page.evaluate("""() => { const A = window.__MISONG_APP__;
      A.S.accountReport = [
        {disk: 'uc', status: 'logged_in', code: 'authenticated_marker', headless: true, attempts: 1, selectors: []},
        {disk: 'quark', status: 'incomplete', code: 'selectors_incomplete', headless: true, attempts: 1,
         selectors: [{item: 'upload', status: 'passed'}, {item: 'share', status: 'not_observed'}]}];
      A.rerender('accounts'); }""")
    report = page.locator("#accountReport")
    text = report.inner_text()
    assert "UC网盘" in text and "会话有效" in text
    assert "入口基本正常，部分未检查" in text
    for raw in ("uc ·", "logged_in", "incomplete", "selectors_incomplete", "not_observed", "上传成功"):
        assert raw not in text
    page.click("#accountReport details summary")
    text = report.inner_text()
    assert "上传控件：已找到" in text and "分享入口：未检查" in text
    page.click(".nav-item[data-page='settings']")
    assert page.locator(".page.active h1").inner_text() == "诊断"
    assert not errors


def test_task_detail_exports_template_and_drag_applies_it(ui):
    page, fake, api, errors = ui
    page.click(".nav-item[data-page='tasks']")
    page.wait_for_timeout(300)
    assert page.locator("#taskDetail [data-exporttpl]").count() == 1
    page.click("#taskDetail [data-exporttpl]")
    page.wait_for_timeout(400)
    assert requests(fake, "pick_save_file")[-1] == ["task-template"]
    folder, path = requests(fake, "export_task_template")[-1]
    assert folder == r"D:\misong\runs\a"
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    assert doc["kind"] == "misong-templates" and len(doc["templates"]) == 1
    item = doc["templates"][0]
    assert item["name"] == "纪录片合集"
    assert [l["fmt"] for l in item["layers"]] == ["lz4", "7z"]
    assert item["layers"][1]["locked"] is True and "password" not in json.dumps(doc)
    # upload-only tasks have no packing layers to export
    page.locator(".task", has_text="S01E01.mkv 等 3 个文件").click()
    page.wait_for_timeout(300)
    assert page.locator("#taskDetail [data-exporttpl]").count() == 0
    # dragging the exported file into the editor applies layers without passwords
    page.click(".nav-item[data-page='pipeline']")
    page.wait_for_timeout(300)
    page.evaluate("p => window.misongDrop([p])", path)
    page.wait_for_timeout(500)
    state = page.evaluate("""() => { const p = window.__MISONG_APP__.S.pipeline;
      return {types: p.layers.map(l => l.type), step: p._step, lock: p.layers[1]._lock, pw: p.layers[1].password}; }""")
    assert state == {"types": ["archive", "archive", "rename", "split"], "step": 2, "lock": True, "pw": ""}
    assert requests(fake, "template_from_paths")[-1] == [[path]]
    assert "已套用模板" in page.locator("#toasts").inner_text()
    assert not errors


def test_dropping_several_templates_stores_quick_templates(ui, tmp_path):
    page, fake, api, errors = ui
    doc = {"schema_version": 1, "kind": "misong-templates", "templates": [
        {"name": "拖入甲", "layers": [{"fmt": "7z", "locked": True, "header_enc": True}]},
        {"name": "拖入乙", "layers": [{"fmt": "zip", "locked": False, "header_enc": True}]}]}
    path = tmp_path / "two-templates.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    page.evaluate("p => window.misongDrop([p])", str(path))
    page.wait_for_timeout(500)
    names = [t["name"] for t in api.templates()["data"]]
    assert "拖入甲" in names and "拖入乙" in names
    assert "已存入 2 个快速模板" in page.locator("#toasts").inner_text()
    assert not errors
