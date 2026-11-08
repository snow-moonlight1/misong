"""F/G/H and release seams: synthetic state only, never real account access."""
import asyncio
import json
import time
from pathlib import Path

import pytest

from misong import diagnostics, eventlog, publish as publisher, templates
from misong.account_health import AccountHealth, AccountPreflightBlocked, HealthReport, PublishPreflight
from misong.cli import main
from misong.desktop import api as api_module
from misong.desktop.api import Api
from misong.jobs import fingerprint, save_json
from misong.text_layers import DeliveryRecipe, TextLayer


def wait(api):
    deadline = time.monotonic() + 10
    events = []
    while time.monotonic() < deadline:
        events.extend(api.poll()["data"]["events"])
        done = [e for e in events if e["type"] == "job" and e["state"] != "running"]
        if done:
            return done[-1], events
        time.sleep(.01)
    pytest.fail("job timed out")


def make_plan(tmp_path):
    source = tmp_path / "synthetic.bin"
    source.write_bytes(b"synthetic")
    recipe = DeliveryRecipe(1, "r1", "合成文案", (TextLayer("magic", "mojibake", secret_slot="r1/magic"),))
    plan = {"version": 2, "id": "synthetic", "form": "direct", "schemes": [], "pwd_hint": "synthetic",
            "state": "blocked", "text_recipes": [recipe.to_dict()], "stages": [
                {"id": "body", "disk": "quark", "folder": "synthetic", "uploaded": {},
                 "files": [fingerprint(source)], "state": "pending"}]}
    path = tmp_path / "relay-plan.json"
    save_json(path, plan)
    return path, plan


def test_task_delivery_summary_and_runtime_resume_keys(tmp_path, monkeypatch):
    path, plan = make_plan(tmp_path)
    plan["stages"][0].update(share={"disk": "quark", "url": "https://pan.quark.cn/s/synthetic"}, state="shared")
    save_json(path, plan)
    api = Api(tmp_path / "runs", tmp_path / "state")
    detail = api.task_detail(str(path))["data"]
    assert detail["delivery"]["label"] == "分享完成、文案未完成"
    assert detail["resume_requirements"]["recipes"][0]["layers"][0]["secret_slot"] == "r1/magic"
    captured = []
    async def fake_publish(path, **kwargs):
        captured.append(kwargs["text_context"].secrets.require("r1/magic"))
        return {"copies": {}}
    monkeypatch.setattr(api_module, "publish", fake_publish)
    assert api.resume_task(str(path), text_cfg={"secrets": {"r1/magic": "synthetic-runtime-password"}})["ok"]
    done, events = wait(api)
    assert done["state"] == "done" and captured == ["synthetic-runtime-password"]
    assert "synthetic-runtime-password" not in json.dumps(events)
    for state_file in (tmp_path / "state").rglob("*"):
        if state_file.is_file():
            assert b"synthetic-runtime-password" not in state_file.read_bytes()


def test_template_import_rename_export_preserves_options_and_recipes(tmp_path):
    api = Api(tmp_path / "runs", tmp_path / "state")
    _, plan = make_plan(tmp_path)
    source = tmp_path / "input.json"
    source.write_text(json.dumps({"schema_version": 1, "kind": "misong-templates", "templates": [{
        "name": "合成模板", "layers": [{"fmt": "7z", "locked": True, "header_enc": True},
                                  {"type": "cover", "video": ""}],
        "options": {"checksum": True}, "text_recipes": plan["text_recipes"]}]}), encoding="utf-8")
    imported = api.import_templates(str(source))
    assert imported["ok"], imported
    item = next(t for t in imported["data"]["templates"] if t["name"] == "合成模板")
    renamed = api.save_template("改名模板", item["layers"], replace=item["name"])
    assert renamed["ok"], renamed
    result = next(t for t in renamed["data"] if t["name"] == "改名模板")
    assert result["options"] == item["options"] and result["text_recipes"] == item["text_recipes"]
    assert result["layers"][1]["video"] == ""
    destination = tmp_path / "export.json"
    assert api.export_templates(str(destination))["ok"]
    restored = templates.read_file(destination)
    assert next(t for t in restored if t["name"] == "改名模板")["text_recipes"] == item["text_recipes"]


def test_task_template_export_and_drop_roundtrip(tmp_path):
    from misong import workflows
    runs = tmp_path / "runs"
    api = Api(runs, tmp_path / "state")
    folder = runs / "task"
    folder.mkdir(parents=True)
    path, plan = make_plan(folder)
    # A hand-edited legacy settings block may still carry a password; export must drop it.
    layers = [{"type": "archive", "fmt": "7z", "locked": True, "header_enc": True, "password": "never-exported"},
              {"type": "split", "size": "1900MB"}]
    workflows.write_meta(folder, "pipeline", "任务标题", settings={
        "layers": layers, "disguise": ".mp4", "size": "", "raw_merge": True, "checksum": True, "layers_version": 2})
    dest = tmp_path / "task-template.json"
    result = api.export_task_template(str(folder), str(dest))
    assert result["ok"], result
    item = json.loads(dest.read_text(encoding="utf-8"))["templates"][0]
    assert item["name"] == "任务标题" and item["disguise"] == ".mp4"
    assert item["options"] == {"raw_merge": True, "checksum": True}
    assert item["text_recipes"] == plan["text_recipes"]
    assert "never-exported" not in dest.read_text(encoding="utf-8")
    assert [l.get("type", "archive") for l in item["layers"]] == ["archive", "split"]
    # one dropped template is returned for direct apply and stores nothing
    before = api.templates()["data"]
    dropped = api.template_from_paths([str(dest)])
    assert dropped["ok"], dropped
    assert dropped["data"]["saved"] is None
    assert dropped["data"]["templates"] == [item]
    assert api.templates()["data"] == before
    # several dropped templates become quick templates, renaming conflicts
    second = tmp_path / "second.json"
    assert templates.export_file([{"name": "任务标题", "layers": [{"fmt": "zip", "locked": False, "header_enc": True}]}], second)["count"] == 1
    multi = api.template_from_paths([str(dest), str(second)])
    assert multi["ok"], multi
    assert multi["data"]["saved"]["renamed"] == [{"from": "任务标题", "to": "任务标题 (2)"}]
    names = [t["name"] for t in api.templates()["data"]]
    assert "任务标题" in names and "任务标题 (2)" in names
    # never overwrites an existing file; refuses tasks without packing layers
    assert not api.export_task_template(str(folder), str(dest))["ok"]
    upload = runs / "upload-only"
    upload.mkdir()
    make_plan(upload)
    workflows.write_meta(upload, "upload", "仅上传")
    assert not api.export_task_template(str(upload), str(tmp_path / "nope.json"))["ok"]


def test_cli_diagnostic_and_template_routes(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MISONG_HOME", str(tmp_path / "home"))
    assert main(["template", "export", str(tmp_path / "templates.json")]) == 0
    assert main(["template", "import", str(tmp_path / "templates.json")]) == 0
    assert main(["diag", "export", "-o", str(tmp_path / "diagnostics.zip")]) == 0
    import zipfile
    with zipfile.ZipFile(tmp_path / "diagnostics.zip") as archive:
        assert "environment.json" in archive.namelist()
        assert not any(n.endswith((".tkey", ".mskey", ".png")) for n in archive.namelist())
    assert "Traceback" not in capsys.readouterr().out


def test_account_cli_batch_and_selfcheck(tmp_path, monkeypatch, capsys):
    observed = []
    async def checks(self, disks=None, **kwargs):
        observed.append(disks)
        self.runtime.notify("账号检查：synthetic")
        return (HealthReport("quark", "logged_in", "observed", True),)
    async def selfcheck(self, disk, **kwargs):
        return HealthReport(disk, "passed", "selectors_passed", True)
    monkeypatch.setattr(AccountHealth, "check_all", checks)
    monkeypatch.setattr(AccountHealth, "selfcheck", selfcheck)
    assert main(["account", "check", "--all", "--headless"]) == 0
    assert observed == [None]
    output = capsys.readouterr()
    assert json.loads(output.out)[0]["status"] == "logged_in"
    assert "synthetic" in output.err
    assert main(["selfcheck", "--disk", "quark", "--headless"]) == 0
    assert "selectors_passed" in capsys.readouterr().out


def test_account_api_records_health_without_replacing_auth(tmp_path, monkeypatch):
    api = Api(tmp_path / "runs", tmp_path / "state")
    auth = api._state / "quark.json"
    auth.parent.mkdir(parents=True)
    auth.write_bytes(b"synthetic-auth-snapshot")
    async def checks(self, disks=None, **kwargs):
        return (HealthReport("quark", "network_error", "navigation_failed", True),)
    monkeypatch.setattr(AccountHealth, "check_all", checks)
    assert api.check_accounts()["ok"]
    done, _ = wait(api)
    assert done["result"]["checks"][0]["status"] == "network_error"
    account = next(a for a in api.accounts()["data"] if a["key"] == "quark")
    assert account["state"] == "neterr" and auth.read_bytes() == b"synthetic-auth-snapshot"
    assert diagnostics.account_status(api._state)["quark"]["check"]["status"] == "network_error"


def test_publish_preflight_blocks_before_any_remote_operation(tmp_path):
    path, plan = make_plan(tmp_path)
    class Health:
        async def preflight(self, data, **kwargs):
            assert data["stages"][0]["state"] == "pending"
            return PublishPreflight(("quark",), (HealthReport("quark", "logged_out", "login_required", True),))
    class NeverRemote:
        def open(self, disk):
            pytest.fail("must not open upload flow")
    with pytest.raises(AccountPreflightBlocked):
        asyncio.run(publisher.publish(path, runtime=NeverRemote(), health=Health(), notify=lambda _: None))
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["account_preflight"]["allowed"] is False
    assert saved["state"] == "blocked" and not saved["stages"][0]["uploaded"]


def test_structural_log_rotation_never_records_arbitrary_values(tmp_path):
    folder = tmp_path / "logs"
    folder.mkdir()
    (folder / "events.jsonl").write_bytes(b" " * (512 * 1024))
    eventlog.record_job(tmp_path, kind="pipeline", state="running")
    eventlog.record_job(tmp_path, kind="synthetic-secret", state="running")
    assert (folder / "events.jsonl.1").exists()
    report = json.loads(eventlog.recent(tmp_path)[0])
    assert report["kind"] == "pipeline"
    assert "synthetic-secret" not in (folder / "events.jsonl").read_text(encoding="utf-8")


def test_inspection_closes_manager_when_cancelled_during_start(tmp_path, monkeypatch):
    api = pytest.importorskip("playwright.async_api")
    from misong.rpa.runtime import BrowserRuntime
    closed = []
    class Manager:
        async def __aenter__(self):
            await asyncio.sleep(60)
        async def __aexit__(self, *args):
            closed.append(True)
    monkeypatch.setattr(api, "async_playwright", Manager)
    health = AccountHealth(BrowserRuntime(state_dir=tmp_path, headless=True))
    result = asyncio.run(health.check_login("quark", timeout=.02))
    assert result.status == "timeout" and closed == [True]
    assert not (tmp_path / "quark.json").exists()


@pytest.mark.parametrize("enabled", [False, True])
def test_failure_snapshots_require_explicit_opt_in_and_are_not_bundled(tmp_path, enabled):
    from misong.rpa.runtime import BrowserRuntime
    class Page:
        async def screenshot(self, *, path, **kwargs):
            Path(path).write_bytes(b"synthetic-private-image")
        async def content(self):
            return "<p>synthetic-private-account-detail</p>"
    runtime = BrowserRuntime(state_dir=tmp_path / "state", diagnostics=enabled, notify=lambda _: None)
    asyncio.run(runtime.capture_inspection_failure("quark", Page()))
    listing = diagnostics.failure_listing(runtime.state_dir)
    assert bool(listing) == enabled
    if enabled:
        assert {r["file"].split("/")[-1] for r in listing} == {"page.png", "page.html"}
        assert all(not r["included"] for r in listing)
    members = diagnostics.build_members(state_dir=runtime.state_dir, environment={"ok": True, "checks": []})
    assert not any(b"synthetic-private" in body for body in members.values())
