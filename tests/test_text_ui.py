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
