"""Diagnostic bundle: synthetic sensitive samples only; every member of the ZIP is opened."""
import json
import os
import zipfile
from pathlib import Path

import pytest

from misong import diagnostics
from misong.diagnostics import DiagnosticsError, export_diagnostics

SHARE_ID = "Zq9SynthShareId77"
CODE = "k7Q2"
PASSWORD = "Synth-Pass-9931x"
MOJI_KEY = "SynthMagicKeyABRA42"
COOKIE = "synthcookievalue8831"
SESSION = "synthsessionstorage5512"
COPY_TEXT = "SYNTH-COPY-TEXT-原文合成"
TKEY = "SYNTH-TKEY-CONTENT-0001"
MSKEY = "SYNTH-MSKEY-CONTENT-0002"
HTML = "SYNTH-FAILURE-HTML-0003"
USER = "synthuserqq"
SECRETS_IN_MEMORY = [PASSWORD, MOJI_KEY]
FORBIDDEN = [SHARE_ID, CODE, PASSWORD, MOJI_KEY, COOKIE, SESSION, COPY_TEXT, TKEY, MSKEY, HTML, USER]
ENV = {"ok": True, "checks": [{"id": "python", "status": "ok",
                               "message": f"C:\\Users\\{USER}\\AppData\\python.exe"}]}


def _w(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def sample(tmp_path):
    state = tmp_path / "home" / "rpa" / "state"
    share = f"https://pan.quark.cn/s/{SHARE_ID}?pwd={CODE}"
    _w(state / "quark.json", {"cookies": [{"name": "sid", "value": COOKIE}], "origins": []})
    _w(state / "session-data" / "quark-chromium.json", {"https://pan.quark.cn": {"tok": SESSION}})
    _w(state / "browser-data" / "quark" / "chromium" / "Cookies", COOKIE)
    _w(state / "profiles" / "quark.json", {"url": share})
    _w(state / "quark-status.json", {"status": "blocked", "session_at": "2026-10-29T10:00:00",
                                     "last_error": f"打开 {share} 失败 提取码：{CODE} Cookie: sid={COOKIE}",
                                     "cookies": [COOKIE], "extra": SESSION})
    _w(state / "baidu-status.json", "{broken json")
    _w(state / "failures" / "quark" / "page.html", f"<html>{HTML} {share}</html>")
    (state / "failures" / "quark" / "page.png").write_bytes(b"\x89PNG fake " + HTML.encode())
    _w(state / "failures" / "quark" / "other.txt", HTML)

    task = tmp_path / "home" / "runs" / "20261029-pipeline-abcd"
    _w(task / "misong-task.json", {
        "kind": "pipeline", "title": f"C:\\Users\\{USER}\\Videos\\clip.mp4", "created": "2026-10-29T10:00:00",
        "chain": "lz4,7z", "artifacts": [str(task / "a.7z")],
        "settings": {"layers": [{"fmt": "7z", "locked": True, "header_enc": True, "password": PASSWORD},
                                {"type": "cover", "video": f"C:\\Users\\{USER}\\cover.mp4"}],
                     "pwd_hint": f"密码 {PASSWORD}", "form": "direct", "body_disks": ["quark"],
                     "text_secrets": {"r1/text": MOJI_KEY}}})
    _w(task / "relay-plan.json", {
        "version": 2, "id": "abc", "form": "direct", "state": "blocked", "pwd_hint": PASSWORD,
        "share_options": {"expiry": "7", "access": "code", "code": CODE},
        "stages": [{"id": "body", "role": "body", "disk": "quark", "state": "complete",
                    "folder": f"misong-{SHARE_ID}",
                    "files": [{"path": str(task / "a.7z"), "size": 10, "sha256": "00"}],
                    "uploaded": {"a.7z": SHARE_ID}, "share": {"url": share, "code": CODE}},
                   "not-a-stage"],
        "text_recipes": [{"version": 1, "id": "r1", "name": "魔曰", "layers": [
            {"id": "l1", "scheme": "mojibake", "version": 1, "params": {}, "secret_slot": "r1/text"}],
            "carrier": {"format_id": "text", "version": 1, "mode": "plain", "params": {}, "secret_slot": None}}],
        "text_delivery": {"share_complete": True, "recipes": [
            {"recipe_id": "r1", "status": "blocked", "error_code": "network",
             "artifacts": [{"role": "copy", "path": str(task / "copy.txt"), "text": COPY_TEXT}]}]},
        "error": {"type": "DriverBlocked", "stage": "copy", "message": share}})
    _w(task / "share-plain.txt", COPY_TEXT + share)
    _w(task / "copy-r1.txt", COPY_TEXT)
    _w(task / "x.tkey", TKEY)
    _w(task / "a.mskey", MSKEY)
    _w(task / "RESTORE.txt", PASSWORD)

    broken = tmp_path / "home" / "runs" / "broken"
    _w(broken / "misong-task.json", "{not json")
    _w(broken / "relay-plan.json", [1, 2, 3])
    logs = [f"分享完成 {share} 提取码：{CODE}", f"password={PASSWORD}", f"Cookie: sid={COOKIE}",
            f"魔曰密钥 {MOJI_KEY}", f"输出 C:\\Users\\{USER}\\Desktop\\x", f"任务 {task}"]
    return {"root": tmp_path, "state": state, "task": task, "broken": broken, "logs": logs}


def _open(path):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        return {name: archive.read(name) for name in archive.namelist()}


def _export(sample, name="diag.zip", **kw):
    out = sample["root"] / name
    args = dict(tasks=[sample["task"], sample["broken"]], state_dir=sample["state"], log_lines=sample["logs"],
                secrets=SECRETS_IN_MEMORY, environment=ENV)
    args.update(kw)
    return out, export_diagnostics(out, **args)


def test_bundle_uses_fixed_whitelist_and_leaks_nothing(sample):
    out, result = _export(sample)
    members = _open(out)
    assert set(members) == {"manifest.json", "version.json", "environment.json", "logs.txt", "accounts.json",
                            "failures.json", "tasks/task-01.json", "tasks/task-02.json"}
    assert set(result["members"]) == set(members) and result["notice"] == ""
    root_text = str(sample["root"])
    for name, body in members.items():
        text = body.decode("utf-8")
        for secret in FORBIDDEN:
            assert secret not in text, (name, secret)
        assert root_text not in text and root_text.replace("\\", "/") not in text, name
        assert os.path.expanduser("~") not in text, name
        for marker in (".tkey", ".mskey", "share-plain", "session-data", "browser-data", "<html"):
            assert name == "manifest.json" or marker not in text, (name, marker)  # manifest states policy


def test_bundle_content_is_useful_and_redacted(sample):
    out, _ = _export(sample)
    members = _open(out)
    version = json.loads(members["version.json"])
    assert version["misong"] and version["python"] and version["system"]
    assert json.loads(members["environment.json"])["ok"] is True
    accounts = json.loads(members["accounts.json"])
    assert accounts["quark"]["status"] == "blocked" and "cookies" not in accounts["quark"]
    assert "extra" not in accounts["quark"] and "pan.quark.cn" in accounts["quark"]["last_error"]
    assert accounts["baidu"] == {"problem": "corrupt"}
    failures = json.loads(members["failures.json"])
    assert {(f["file"], f["included"]) for f in failures} == {("page.png", False), ("page.html", False)}
    task = json.loads(members["tasks/task-01.json"])
    assert task["task"]["kind"] == "pipeline" and task["task"]["settings"]["layers"][0] == \
        {"fmt": "7z", "locked": True, "header_enc": True}
    assert "pwd_hint" not in task["task"]["settings"] and "text_secrets" not in task["task"]["settings"]
    stage = task["plan"]["stages"][0]
    assert stage["shared"] is True and stage["file_count"] == 1 and stage["total_bytes"] == 10
    assert task["plan"]["stages"][1] == {"corrupt": True}
    assert task["plan"]["error"] == {"type": "DriverBlocked", "stage": "copy"}
    assert task["plan"]["share_options"] == {"expiry": "7", "access": "code"}
    assert task["plan"]["delivery"]["label"] == "分享完成、文案未完成"
    assert task["plan"]["delivery"]["recipes"][0]["artifact_roles"] == ["copy"]
    assert task["plan"]["text_recipes"][0]["secret_slots"] == 1
    broken = json.loads(members["tasks/task-02.json"])
    assert "task:corrupt" in broken["problems"] and "plan:corrupt" in broken["problems"]
    logs = members["logs.txt"].decode()
    assert "[REDACTED]" in logs and "pan.quark.cn" in logs and logs.count("\n") == 5
    manifest = json.loads(members["manifest.json"])
    assert manifest["schema_version"] == 1 and manifest["screenshots"] == {"count": 0}


def test_pattern_rules_alone_cover_links_codes_cookies_and_user_paths(sample):
    out, _ = _export(sample, secrets=())
    blob = b"".join(_open(out).values()).decode("utf-8")
    for secret in (SHARE_ID, CODE, COOKIE, SESSION, COPY_TEXT, TKEY, MSKEY, HTML, USER):
        assert secret not in blob, secret


def test_refuses_overwrite_and_bad_targets(sample):
    out, _ = _export(sample)
    before = out.read_bytes()
    with pytest.raises(DiagnosticsError):
        _export(sample)
    assert out.read_bytes() == before
    with pytest.raises(DiagnosticsError):
        _export(sample, name="diag.txt")
    with pytest.raises(DiagnosticsError):
        export_diagnostics(sample["root"] / "missing" / "d.zip", environment=ENV)


def test_screenshots_only_explicit_and_flagged(sample):
    shot = sample["root"] / "pick.png"
    shot.write_bytes(b"\x89PNG synthetic")
    out, result = _export(sample, screenshots=[shot])
    members = _open(out)
    assert members["screenshots/01.png"] == b"\x89PNG synthetic"
    assert result["notice"] == diagnostics.SCREENSHOT_NOTICE and "未经过文本脱敏" in result["notice"]
    assert json.loads(members["manifest.json"])["screenshots"] == {"count": 1, "text_redacted": False}
    for bad in (sample["task"] / "x.tkey", sample["task"] / "a.mskey",
                sample["state"] / "failures" / "quark" / "page.html", sample["root"]):
        with pytest.raises(DiagnosticsError):
            _export(sample, name=f"bad-{bad.name}.zip", screenshots=[bad])
        assert not (sample["root"] / f"bad-{bad.name}.zip").exists()
    big = sample["root"] / "big.png"
    big.write_bytes(b"0" * (diagnostics.MAX_SCREENSHOT_BYTES + 1))
    with pytest.raises(DiagnosticsError):
        _export(sample, name="big.zip", screenshots=[big])
    with pytest.raises(DiagnosticsError):
        _export(sample, name="many.zip", screenshots=[shot] * (diagnostics.MAX_SCREENSHOTS + 1))


def test_limits_on_tasks_logs_and_records(sample, monkeypatch):
    with pytest.raises(DiagnosticsError):
        _export(sample, name="t.zip", tasks=[sample["task"]] * (diagnostics.MAX_TASKS + 1))
    out, _ = _export(sample, name="logs.zip", log_lines=["x" * 1500] * 5000)
    logs = _open(out)["logs.txt"].decode()
    assert len(logs) < diagnostics.MAX_LOG_CHARS + 5000 and logs.endswith("[truncated]")
    monkeypatch.setattr(diagnostics, "MAX_RECORD_BYTES", 10)
    out, _ = _export(sample, name="rec.zip")
    assert "plan:too_large" in json.loads(_open(out)["tasks/task-01.json"])["problems"]
    monkeypatch.setattr(diagnostics, "MAX_TOTAL_BYTES", 100)
    with pytest.raises(DiagnosticsError):
        _export(sample, name="total.zip")
    assert not (sample["root"] / "total.zip").exists()


def _symlink(link: Path, target: Path, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")


def test_symlinks_and_escapes_are_not_followed(sample, tmp_path):
    outside = tmp_path / "outside"
    _w(outside / "relay-plan.json", {"state": SHARE_ID, "stages": []})
    task = sample["root"] / "linked-task"
    task.mkdir()
    _symlink(task / "relay-plan.json", outside / "relay-plan.json")
    _symlink(sample["state"] / "uc-status.json", outside / "relay-plan.json")
    linked_dir = sample["root"] / "dir-link"
    _symlink(linked_dir, outside, directory=True)
    shot = outside / "s.png"
    shot.write_bytes(b"png")
    _symlink(sample["root"] / "s-link.png", shot)
    with pytest.raises(DiagnosticsError):
        _export(sample, name="l.zip", screenshots=[sample["root"] / "s-link.png"])
    out, _ = _export(sample, name="links.zip", tasks=[task, linked_dir])
    members = _open(out)
    assert "plan:rejected_link_or_outside" in json.loads(members["tasks/task-01.json"])["problems"]
    assert json.loads(members["tasks/task-02.json"])["problem"] == "not_a_task_folder"
    assert json.loads(members["accounts.json"])["uc"] == {"problem": "rejected_link_or_outside"}
    assert SHARE_ID not in b"".join(members.values()).decode()


def test_export_never_reads_outside_whitelist(sample, monkeypatch):
    opened = []
    real_read_text = Path.read_text

    def spy(self, *a, **k):
        opened.append(self.name)
        return real_read_text(self, *a, **k)
    monkeypatch.setattr(Path, "read_text", spy)
    _export(sample, name="spy.zip")
    allowed = {"misong-task.json", "nde-task.json", "relay-plan.json"} | {
        f"{d}-status.json" for d in ("quark", "feimao", "baidu", "xunlei", "uc", "123pan")}
    assert opened and set(opened) <= allowed


def test_environment_failure_still_exports(sample, monkeypatch):
    import misong.doctor
    monkeypatch.setattr(misong.doctor, "check_environment", lambda: (_ for _ in ()).throw(RuntimeError(USER)))
    out = sample["root"] / "env.zip"
    export_diagnostics(out, environment=None)
    members = _open(out)
    assert json.loads(members["environment.json"]) == {"ok": False, "error": "RuntimeError"}
    assert "accounts.json" not in members
