"""Desktop bridge tests: real workflows, fake disks, no window and no network."""
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from nde import pack, workflows
from nde.desktop.api import Api
from nde.sharing import ShareInfo


class FakeRuntime:
    def __init__(self, notify=None, cancel=None):
        self.events = []

    @asynccontextmanager
    async def open(self, disk):
        runtime = self

        class Driver:
            def require_new_folder(self, folder, on_created):
                runtime.events.append(("new-folder", disk, folder))
                on_created()

            def configure_share(self, options):
                runtime.events.append(("share-options", disk))

            async def upload(self, page, files, folder):
                runtime.events += [("upload", disk, f.name) for f in files]
                return [folder]

            async def share(self, page, targets):
                runtime.events.append(("share", disk))
                host = {"quark": "pan.quark.cn", "uc": "drive.uc.cn"}.get(disk, "www.feemoo.com")
                return ShareInfo(disk, f"https://{host}/s/{targets[0]}", "a123", "7天")
        yield Driver(), None


@pytest.fixture
def api(tmp_path):
    runtimes = []

    def factory(notify, cancel):
        runtimes.append(FakeRuntime(notify, cancel))
        return runtimes[-1]
    obj = Api(tmp_path / "runs", tmp_path / "state", runtime_factory=factory)
    obj.runtimes = runtimes
    return obj


@pytest.fixture
def src(tmp_path):
    folder = tmp_path / "input"
    folder.mkdir()
    (folder / "中文.txt").write_text("自己的资源 hello 世界 " * 40, encoding="utf-8")
    return folder


def ok(result):
    assert result["ok"], result.get("error")
    return result["data"]


def wait_job(api, timeout=60):
    deadline, logs = time.time() + timeout, []
    while time.time() < deadline:
        for event in ok(api.poll())["events"]:
            if event["type"] == "log":
                logs.append(event["text"])
            if event["type"] == "job" and event["state"] != "running":
                event["logs"] = logs
                return event
        time.sleep(0.05)
    raise AssertionError("job did not finish")


LAYERS = [{"fmt": "lz4"}, {"fmt": "zip", "password": "secret"}]


def test_bootstrap_shape(api):
    data = ok(api.bootstrap())
    assert {"formats", "providers", "expiry", "access", "forms", "browsers", "schemes", "settings"} <= set(data)
    assert any(f["key"] == "zip" and f["password"] for f in data["formats"])
    assert any(p["key"] == "quark" and p["auto"] for p in data["providers"])
    assert data["job"] is None and data["settings"] == {}


@pytest.mark.parametrize("kind", ["pack", "pipeline", "upload"])
def test_selected_output_directory_routes_new_jobs(api, src, tmp_path, kind):
    selected = tmp_path / "chosen output 中文"
    selected.mkdir()
    assert ok(api.set_output_dir(str(selected)))["runs"] == str(selected)
    config = {"inputs": [str(src)], "layers": [{"fmt": "zip"}], "size": "100B",
              "body_disks": ["quark"], "form": "direct", "schemes": ["beast"]}
    if kind == "upload":
        config["files"] = [str(src / "中文.txt")]
    ok(getattr(api, "start_" + kind)(config))
    event = wait_job(api)
    assert event["state"] == "done", event["error"]
    tasks = ok(api.list_tasks())
    assert len(tasks) == 1
    assert Path(tasks[0]["dir"]).parent == selected


def test_output_directory_persists_and_keeps_previous_tasks(api, src, tmp_path):
    ok(api.start_pack({"inputs": [str(src)], "layers": [{"fmt": "zip"}]}))
    assert wait_job(api)["state"] == "done"
    previous = ok(api.list_tasks())[0]
    selected = tmp_path / "new-output"
    selected.mkdir()
    ok(api.set_output_dir(str(selected)))
    restarted = Api(tmp_path / "runs", tmp_path / "state")
    assert ok(restarted.bootstrap())["runs"] == str(selected)
    tasks = ok(restarted.list_tasks())
    assert [t["dir"] for t in tasks] == [previous["dir"]]
    assert not tasks[0]["imported"]
    assert ok(restarted.update_task(previous["dir"], {"note": "kept"}))["note"] == "kept"
    assert Path(previous["dir"]).exists()


def test_output_directory_rejects_invalid_or_running_changes(api, tmp_path):
    selected = tmp_path / "output"
    selected.mkdir()
    file = tmp_path / "file.txt"
    file.write_bytes(b"test")
    original = ok(api.bootstrap())["runs"]
    for value in ("", str(file), str(tmp_path / "missing")):
        assert not api.set_output_dir(value)["ok"]
    api._job = {"id": "running"}
    assert "运行中" in api.set_output_dir(str(selected))["error"]
    api._job = None
    assert ok(api.bootstrap())["runs"] == original


def test_settings_never_persist_passwords(api, tmp_path):
    ok(api.save_settings({"layers": [{"fmt": "zip", "password": "secret"}], "form": "simple",
                          "hop_password": "hop-secret", "key": "KEY"}))
    raw = (tmp_path / "state" / "ui-settings.json").read_text(encoding="utf-8")
    assert "secret" not in raw and "KEY" not in raw
    settings = ok(api.bootstrap())["settings"]
    assert settings["form"] == "simple" and settings["layers"][0] == {"fmt": "zip", "header_enc": True, "locked": True}


def test_codec_roundtrip(api):
    copies = ok(api.encode("https://pan.quark.cn/s/demo 提取码:1234", ["beast", "hajimi", "base64"]))
    for scheme in ("beast", "hajimi", "base64"):
        assert ok(api.decode(copies[scheme], scheme)) == "https://pan.quark.cn/s/demo 提取码:1234"
    assert not api.encode("", ["beast"])["ok"]


@pytest.mark.parametrize("layers, message", [([], "至少"), ([{"fmt": "nope"}], "未知格式"),
                                             ([{"fmt": "lz4", "password": "x"}], "不支持密码")])
def test_layer_validation(api, src, layers, message):
    result = api.start_pack({"inputs": [str(src)], "layers": layers})
    assert not result["ok"] and message in result["error"]


def test_pack_only_job_and_task_center(api, src, tmp_path):
    ok(api.start_pack({"inputs": [str(src)], "layers": LAYERS, "split": True, "size": "100B", "disguise": "png"}))
    event = wait_job(api)
    assert event["state"] == "done", event["error"]
    result = event["result"]
    assert result["artifact"].endswith("input.png.001") and len(result["files"]) > 2
    assert workflows.read_meta(result["out"])["chain"] == "split,rename,zip,lz4"
    restored = pack.unest(result["artifact"], tmp_path / "restored", [None, None, "secret", None])
    assert any(p.name == "中文.txt" for root in restored for p in ([root] if root.is_file() else root.rglob("*")))
    tasks = ok(api.list_tasks())
    assert [t["kind"] for t in tasks] == ["pack"]
    detail = ok(api.task_detail(folder=tasks[0]["dir"]))
    assert all(f["name"] != workflows.META_NAME for f in detail["files"])
    assert "secret" not in json.dumps(detail, ensure_ascii=False)


def test_pipeline_job_uploads_and_shares(api, src):
    ok(api.start_pipeline({"inputs": [str(src)], "layers": LAYERS, "size": "100B", "body_disks": ["quark"],
                           "form": "simple", "schemes": ["beast", "hajimi"]}))
    event = wait_job(api)
    assert event["state"] == "done", event["error"]
    assert set(event["result"]["copies"]) == {"beast", "hajimi"}
    assert event["result"]["task"]["state"] == "complete"
    task = ok(api.list_tasks())[0]
    assert task["kind"] == "pipeline" and [s["role"] for s in task["stages"]] == ["body", "hop"]
    detail = ok(api.task_detail(plan=task["plan"]))
    assert set(detail["copies"]) == {"beast", "hajimi"} and detail["files"]
    assert not api.resume_task(task["plan"])["ok"]  # already complete


@pytest.mark.parametrize("kind", ["pack", "pipeline"])
@pytest.mark.parametrize("scenario", ["final_volumes", "below_threshold", "nested_volumes"])
def test_v2_split_through_gui_bridge(api, tmp_path, kind, scenario):
    src = tmp_path / "payload.bin"
    src.write_bytes(bytes(range(256)) * 9000)
    threshold = "3MB" if scenario == "below_threshold" else "1"
    layers = [{"type": "archive", "fmt": "zip", "level": 0}, {"type": "split", "size": threshold}]
    if scenario == "nested_volumes":
        layers.append({"type": "archive", "fmt": "7z", "level": 0})
    cfg = {"inputs": [str(src)], "layers": layers, "layers_version": 2,
           "body_disks": ["quark"], "schemes": ["base64"], "upload": False}
    ok(getattr(api, "start_" + kind)(cfg))
    event = wait_job(api)
    assert event["state"] == "done", event["error"]
    result = event["result"]
    folder = Path(result["out"]) if kind == "pack" else Path(result["plan"]).parent / "body"
    manifest = json.loads(next(folder.glob("*.nde.json")).read_text(encoding="utf-8"))
    sm = next(r["split_manifest"] for r in manifest["layers"] if r["type"] == "split")
    assert sm["part_size"] == (3 if scenario == "below_threshold" else 1) * 1024**2
    assert sm["part_count"] == (1 if scenario == "below_threshold" else 3)
    artifacts = [folder / r["name"] for r in manifest["artifacts"]]
    if scenario == "final_volumes":
        assert [p.suffix for p in artifacts] == [".001", ".002", ".003"]
        assert all(p.stat().st_size <= 1024**2 for p in artifacts)
    else:
        assert len(artifacts) == 1 and artifacts[0].suffix in (".zip", ".7z")
    assert pack.unest(artifacts[0], tmp_path / "restored", [None] * len(layers))[0].read_bytes() == src.read_bytes()
    logs = "\n".join(event["logs"])
    assert ("未超过阈值，保留单文件" if scenario == "below_threshold" else "生成 3 卷") in logs
    if scenario == "nested_volumes":
        assert "后续层已继续处理分卷层产物" in logs
    if kind == "pipeline":
        plan = json.loads(Path(result["plan"]).read_text(encoding="utf-8"))
        assert [Path(f["path"]) for f in plan["stages"][0]["files"]] == artifacts


def test_pipeline_validation_happens_before_job(api, src):
    base = {"inputs": [str(src)], "layers": LAYERS, "body_disks": ["quark"], "schemes": ["beast"]}
    assert "第一跳" in api.start_pipeline({**base, "form": "complex"})["error"]
    assert "本体网盘" in api.start_pipeline({**base, "body_disks": []})["error"]
    assert "文案" in api.start_pipeline({**base, "schemes": []})["error"]
    assert ok(api.poll())["job"] is None and not api._runs.exists()


def test_standalone_upload_to_multiple_disks(api, tmp_path):
    files = []
    for name in ("a.bin", "b.bin"):
        files.append(tmp_path / name)
        files[-1].write_bytes(name.encode() * 100)
    ok(api.start_upload({"files": [str(p) for p in files], "body_disks": ["quark", "uc"], "schemes": ["beast"]}))
    event = wait_job(api)
    assert event["state"] == "done", event["error"]
    uploads = [e for e in api.runtimes[0].events if e[0] == "upload"]
    assert sorted(uploads) == sorted(("upload", d, n) for d in ("quark", "uc") for n in ("a.bin", "b.bin"))
    task = ok(api.list_tasks())[0]
    assert task["kind"] == "upload" and task["state"] == "complete" and len(task["stages"]) == 2
    copy = event["result"]["copies"]["beast"]
    assert "pan.quark.cn" in ok(api.decode(copy, "beast")) and "drive.uc.cn" in ok(api.decode(copy, "beast"))


def test_upload_rejects_folders_and_duplicates(tmp_path, src):
    with pytest.raises(ValueError, match="只接受文件"):
        workflows.prepare_upload([src], tmp_path / "out", ["quark"])
    other = tmp_path / "other"
    other.mkdir()
    for folder in (src, other):
        (folder / "same.bin").write_bytes(b"x")
    with pytest.raises(ValueError, match="不能重复"):
        workflows.prepare_upload([src / "same.bin", other / "same.bin"], tmp_path / "out", ["quark"])
    assert not (tmp_path / "out").exists()


def test_single_job_lock(api, src):
    import threading
    gate = threading.Event()

    def slow(job):
        gate.wait(10)
    api._start("pack", "slow", slow)
    second = api.start_pack({"inputs": [str(src)], "layers": LAYERS})
    assert not second["ok"] and "已有任务" in second["error"]
    assert ok(api.pause()) is True
    gate.set()
    assert wait_job(api)["state"] == "done"


def test_templates_never_store_passwords_and_validate(api, tmp_path):
    from nde.desktop.api import DEFAULT_TEMPLATES
    defaults = [t["name"] for t in DEFAULT_TEMPLATES]
    assert [t["name"] for t in ok(api.templates())] == defaults  # built-ins are seeded on first run
    for name in defaults:
        ok(api.delete_template(name))
    layers = [{"fmt": "lz4"}, {"fmt": "7z", "password": "pw-secret", "header_enc": False}]
    items = ok(api.save_template("我的模板", layers, ".png", "1G"))
    assert items[0]["layers"] == [{"fmt": "lz4", "locked": False, "header_enc": True},
                                  {"fmt": "7z", "locked": True, "header_enc": False}]
    raw = (tmp_path / "state" / "ui-templates.json").read_text(encoding="utf-8")
    assert "pw-secret" not in raw
    ok(api.save_template("第二个", [{"fmt": "zip"}]))
    renamed = ok(api.save_template("改名了", layers, "", "", replace="我的模板"))
    assert [t["name"] for t in renamed] == ["改名了", "第二个"]
    assert "已有" in api.save_template("第二个", layers, replace="改名了")["error"]
    assert not api.save_template("x", [{"fmt": "nope"}])["ok"]
    assert not api.save_template("x", layers, ".exe")["ok"]
    assert not api.save_template("x", layers, "", "abc")["ok"]
    assert not api.save_template("", layers)["ok"]
    assert [t["name"] for t in ok(api.delete_template("改名了"))] == ["第二个"]
    assert [t["name"] for t in ok(api.bootstrap())["templates"]] == ["第二个"]


def test_default_templates_are_deletable_and_restorable(api, tmp_path):
    from nde.desktop.api import DEFAULT_TEMPLATES
    defaults = [t["name"] for t in DEFAULT_TEMPLATES]
    assert ok(api.bootstrap())["default_templates"] == defaults
    first = ok(api.templates())[0]
    assert first["layers"] == [{"fmt": "lz4", "locked": False, "header_enc": True},
                               {"fmt": "7z", "locked": True, "header_enc": True}]
    left = ok(api.delete_template(defaults[0]))
    assert defaults[0] not in [t["name"] for t in left]
    assert defaults[0] not in [t["name"] for t in ok(api.templates())]  # deletion is remembered
    ok(api.save_template("我的", [{"fmt": "zip"}]))
    restored = [t["name"] for t in ok(api.reset_templates())]
    assert sorted(restored) == sorted(defaults + ["我的"]) and restored[0] == defaults[0]
    # an older file written before built-ins existed keeps its own templates and gains the defaults once
    path = tmp_path / "state" / "ui-templates.json"
    path.write_text(json.dumps({"templates": [{"name": "旧模板", "layers": [{"fmt": "zip"}]}]}), encoding="utf-8")
    assert [t["name"] for t in ok(api.templates())] == defaults + ["旧模板"]


def test_disguise_whitelist(api, src, tmp_path):
    data = ok(api.bootstrap())
    assert ".mp4" in data["disguises"] and data["browser_labels"]["chromium"].startswith("Chromium")
    result = api.start_pack({"inputs": [str(src)], "layers": LAYERS, "disguise": ".exe"})
    assert not result["ok"] and "伪装后缀" in result["error"]
    with pytest.raises(ValueError, match="伪装后缀"):
        workflows.pack_only([src], [pack.LayerSpec("zip")], tmp_path / "o", disguise=".bat")


def test_error_messages_are_readable():
    from nde.desktop.api import error_text, friendly_error
    assert error_text({"type": "DriverBlocked", "stage": "body"}) == "网盘页面操作受阻（本体上传）"
    assert "[object" not in error_text({"type": "X"}) and error_text(None) == ""
    text = friendly_error("Page.goto: net::ERR_TIMED_OUT at https://drive.uc.cn/list\nCall log:")
    assert "drive.uc.cn" in text and "连接超时" in text and "网络" in text
    assert friendly_error("plain") == "plain"


def _finished_pack(api, src):
    ok(api.start_pack({"inputs": [str(src)], "layers": LAYERS, "disguise": "mp4"}))
    event = wait_job(api)
    assert event["state"] == "done", event["error"]
    return event["result"]["out"]


def test_task_edit_star_note_and_same_settings(api, src):
    folder = _finished_pack(api, src)
    task = ok(api.list_tasks())[0]
    assert task["settings"]["layers"] == [{"fmt": "lz4", "locked": False, "header_enc": True},
                                          {"fmt": "zip", "locked": True, "header_enc": True}]
    assert task["settings"]["disguise"] == ".mp4" and "secret" not in json.dumps(task, ensure_ascii=False)
    created = task["created"]
    task = ok(api.update_task(folder, {"title": "新名字", "starred": True, "note": "给朋友的"}))
    assert (task["title"], task["starred"], task["note"], task["created"]) == ("新名字", True, "给朋友的", created)
    assert not api.update_task(folder, {"title": ""})["ok"]
    assert not api.update_task(folder, {"note": "x" * 501})["ok"]
    assert "只能管理" in api.update_task(str(src), {"starred": True})["error"]


def test_plan_error_dict_becomes_text(api, src):
    ok(api.start_pipeline({"inputs": [str(src)], "layers": LAYERS, "size": "100B", "body_disks": ["quark"],
                           "schemes": ["beast"], "upload": False}))
    event = wait_job(api)
    plan_path = event["result"]["plan"]
    plan = json.loads(open(plan_path, encoding="utf-8").read())
    plan["error"] = {"type": "DriverBlocked", "stage": "body"}
    open(plan_path, "w", encoding="utf-8").write(json.dumps(plan))
    task = ok(api.task_detail(plan=plan_path))
    assert task["error"] == "网盘页面操作受阻（本体上传）"
    assert task["settings"]["body_disks"] == ["quark"] and task["settings"]["layers"][1]["locked"] is True


def test_delete_task_uses_recycle_bin(api, src, monkeypatch):
    import shutil
    trashed = []
    monkeypatch.setattr("nde.desktop.api._trash", lambda p: (trashed.append(p), shutil.rmtree(p)))
    folder = _finished_pack(api, src)
    assert "只能管理" in api.delete_task(str(src))["error"]
    assert ok(api.delete_task(folder))["trashed"] is True
    assert trashed and ok(api.list_tasks()) == [] and src.exists()


def test_import_external_task_folder(api, src, tmp_path, monkeypatch):
    out = tmp_path / "elsewhere"
    workflows.pack_only([src], [pack.LayerSpec("zip")], out)
    (out / workflows.META_NAME).unlink()  # e.g. produced by the CLI
    assert "无法识别" in api.import_task(str(src))["error"]
    task = ok(api.import_task(str(out)))
    assert task["kind"] == "pack" and task["imported"] and task["chain"] == "zip"
    assert [t["dir"] for t in ok(api.list_tasks())] == [str(out.resolve())]
    ok(api.update_task(str(out), {"starred": True}))
    monkeypatch.setattr("nde.desktop.api._trash", lambda p: pytest.fail("imported folders must not be trashed"))
    assert ok(api.delete_task(str(out)))["trashed"] is False
    assert out.exists() and ok(api.list_tasks()) == []


def test_accounts_report_single_owner_facing_state(api, tmp_path):
    from nde.rpa.runtime import BrowserRuntime
    state = tmp_path / "state"
    state.mkdir()
    runtime = BrowserRuntime(state_dir=state)
    runtime._record("quark", status="ready")
    runtime._record("quark", session_ok=True)
    runtime._record("quark", status="probe")  # a later probe must not downgrade a verified driver
    runtime._record("uc", status="blocked", error="net::ERR_TIMED_OUT at https://drive.uc.cn/", session_error=True)
    runtime._record("baidu", status="blocked", error="登录超时", session_error=True)
    runtime._record("feimao", session_ok=True)
    (state / "quark.json").write_text("{}", encoding="utf-8")
    for disk in ("uc", "baidu", "feimao"):
        (state / f"{disk}.json").write_text("{}", encoding="utf-8")
    accounts = {a["key"]: a for a in ok(api.accounts())}
    quark, uc = accounts["quark"], accounts["uc"]
    assert quark["status"] == "ready" and quark["verified"] and quark["verified_at"] and quark["session_at"]
    assert quark["session"] and quark["session_saved"] and not quark["session_error"]
    assert not uc["verified"] and uc["session_error"] and "连接超时" in uc["last_error"]
    assert {k: accounts[k]["state"] for k in ("quark", "uc", "baidu", "feimao", "xunlei")} == {
        "quark": "tested", "uc": "neterr", "baidu": "expired", "feimao": "loggedin", "xunlei": "none"}
    runtime._record("uc", session_ok=True)
    uc = {a["key"]: a for a in ok(api.accounts())}["uc"]
    assert not uc["session_error"] and uc["state"] == "loggedin"


def test_task_history_restores_tested_state(api, tmp_path):
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    (state / "quark-status.json").write_text(json.dumps({"status": "probe"}), encoding="utf-8")
    (state / "uc-status.json").write_text(json.dumps({"status": "probe"}), encoding="utf-8")
    for disk in ("quark", "uc"):
        (state / f"{disk}.json").write_text("{}", encoding="utf-8")
    run = tmp_path / "runs" / "old-task"
    run.mkdir(parents=True)
    files = [{"path": "a.7z"}]
    plan = {"version": 2, "stages": [
        {"id": "body", "disk": "quark", "state": "shared", "files": files, "uploaded": {"a.7z": ["x"]},
         "share": {"url": "https://pan.quark.cn/s/abc"}},
        {"id": "hop", "disk": "uc", "state": "shared", "files": files, "uploaded": {"a.7z": ["x"]},
         "share": {"url": "https://drive.uc.cn/s/abc"}, "manual": True}]}
    (run / "relay-plan.json").write_text(json.dumps(plan), encoding="utf-8")
    accounts = {a["key"]: a for a in ok(api.accounts())}
    assert accounts["quark"]["state"] == "tested" and accounts["quark"]["verified_at"]
    assert accounts["uc"]["state"] == "loggedin"  # a hand-filled link proves nothing about the driver


def test_mojibake_node_runs_without_console_window(monkeypatch):
    import subprocess
    from nde.encoders import mojibake
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, "密文\n".encode("utf-8"), b"")
    monkeypatch.setattr(mojibake, "_ensure", lambda: None)
    monkeypatch.setattr(mojibake.subprocess, "run", fake_run)
    assert mojibake.encode("hello").strip() == "密文"
    assert seen["creationflags"] == mojibake.NO_WINDOW
    if os.name == "nt":
        assert mojibake.NO_WINDOW == subprocess.CREATE_NO_WINDOW

@pytest.mark.parametrize("kind", ["pipeline", "upload"])
def test_publication_names_in_job_and_reopened_task(api, src, kind):
    source = src / "中文.txt"
    cfg = {"task_name": "第八期 中文 🐈", "folder_name": "nde-第八期", "body_disks": ["quark"],
           "schemes": ["beast"], "inputs": [str(source)], "files": [str(source)],
           "layers": [{"fmt": "zip", "password": "memory-only"}], "size": ""}
    job = ok(getattr(api, "start_pipeline" if kind == "pipeline" else "start_upload")(cfg))
    assert job["title"] == cfg["task_name"]
    event = wait_job(api)
    assert event["state"] == "done", event
    task = ok(api.list_tasks())[0]
    assert task["title"] == cfg["task_name"]
    data = json.loads(Path(task["plan"]).read_text(encoding="utf-8"))
    assert data["stages"][0]["folder"] == cfg["folder_name"]
    reopened = Api(api._runs, api._state)
    assert ok(reopened.list_tasks())[0]["title"] == cfg["task_name"]
    assert "memory-only" not in (Path(task["dir"]) / "nde-task.json").read_text(encoding="utf-8")


def test_invalid_names_rejected_before_background_job(api, src):
    result = api.start_pipeline({"inputs": [str(src)], "task_name": "x" * 121})
    assert not result["ok"] and "任务名称" in result["error"]
    result = api.start_upload({"files": [str(src / "中文.txt")], "folder_name": "../existing"})
    assert not result["ok"] and "目录名" in result["error"]
    assert api._job is None
