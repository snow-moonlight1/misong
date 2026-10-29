"""Offline bridge and DOM integration for portable-key restoration."""
import importlib.util
from pathlib import Path

import pytest

from misong import pack, restore_key
from misong.cli import build_parser
from misong.desktop.api import Api
from misong.layers import LayerSpec as L
from test_desktop_api import ok, wait_job


def test_bridge_pack_export_then_restore_with_no_secret_events(tmp_path):
    source = tmp_path / "input.txt"
    source.write_text("offline restore proof 中文", encoding="utf-8")
    api = Api(tmp_path / "runs", tmp_path / "state")
    cfg = {"inputs": [str(source)], "layers_version": 2,
           "layers": [{"type": "archive", "fmt": "7z", "password": "key-test-only"}], "export_key": True}
    ok(api.start_pack(cfg))
    event = wait_job(api)
    assert event["state"] == "done", event
    result = event["result"]
    assert result["restore_key"] and "key-test-only" not in str(event)
    ok(api.start_restore({"source": result["artifact"], "key_file": result["restore_key"]}))
    restored = wait_job(api)
    assert restored["state"] == "done", restored
    output = Path(restored["result"]["out"])
    assert (output / source.name).read_bytes() == source.read_bytes()
    assert "key-test-only" not in str(restored)
    for path in (tmp_path / "runs").rglob("*.json"):
        assert "key-test-only" not in path.read_text(encoding="utf-8")


def test_cli_export_and_restore_roundtrip(tmp_path, capsys):
    parser = build_parser()
    source = tmp_path / "cli.txt"
    source.write_bytes(b"CLI proof" * 50)
    artifact = tmp_path / "cli.7z"
    args = parser.parse_args(["nest", str(source), "-L", "7z", "-P", "cli-test-only", "--export-key", "-o", str(artifact)])
    assert args.fn(args) == 0
    args = parser.parse_args(["restore", str(artifact), "--key-file", str(restore_key.sidecar(artifact)), "-o", str(tmp_path / "back")])
    assert args.fn(args) == 0
    assert (tmp_path / "back/cli.txt").read_bytes() == source.read_bytes()
    assert "cli-test-only" not in capsys.readouterr().out


def test_two_path_drop_and_restore_job_ui(tmp_path):
    from playwright.sync_api import sync_playwright
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("restore_preview", root / "scripts/ui_preview.py")
    preview = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preview)
    fake = preview.Fake(Api(tmp_path / "runs", tmp_path / "state"))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1090, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.expose_function("__py", fake)
        page.add_init_script(preview.MOCK_JS)
        page.goto(preview.WEB.as_uri())
        page.wait_for_selector(".page.active [data-mount='run'] .run")
        page.get_by_role("button", name="一键还原", exact=True).click()
        run = page.locator(".page.active [data-run='go']")
        assert run.is_disabled()
        page.evaluate("paths => window.misongDrop(paths)", [r"D:\example\sample.001", r"D:\example\sample.mskey"])
        page.wait_for_function("() => !document.querySelector('.page.active [data-run]').disabled")
        assert "sample.mskey" in page.locator(".page.active").inner_text()
        run.click()
        page.wait_for_function("() => !!window.__MISONG_APP__.S.job")
        fake.finish("restore")
        page.get_by_text("还原完成", exact=True).wait_for()
        assert not errors
        browser.close()
