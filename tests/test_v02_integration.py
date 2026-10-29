"""Cross-module acceptance after the parallel modules have been delivered."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from misong.cli import build_parser
from misong.desktop.api import Api
from misong import paths, redact


def test_desktop_and_browser_runtime_resolve_same_home_after_import(monkeypatch, tmp_path):
    from misong.rpa.runtime import BrowserRuntime
    first, second = tmp_path / "first", tmp_path / "second"
    monkeypatch.setenv("MISONG_HOME", str(first))
    api = Api()
    assert api._state == BrowserRuntime().state_dir == first / "rpa/state"
    assert api._runs == first / "runs"
    monkeypatch.setenv("MISONG_HOME", str(second))
    assert Api()._runs == second / "runs"
    assert api._runs == first / "runs"


def test_migrated_settings_and_synthetic_session_are_loaded(monkeypatch, tmp_path):
    old = tmp_path / "old-state"
    old.mkdir()
    (old / "ui-settings.json").write_text(json.dumps({"checksum": True}), encoding="utf-8")
    (old / "quark.json").write_text('{"cookies": [{"name": "sid", "value": "synthetic-session"}]}', encoding="utf-8")
    home = tmp_path / "new-home"
    parser = build_parser()
    args = parser.parse_args(["data-migrate", str(old), str(home / "rpa/state")])
    assert args.fn(args) == 0
    monkeypatch.setenv("MISONG_HOME", str(home))
    api = Api()
    assert api._load_settings()["checksum"] is True
    assert (api._state / "quark.json").read_bytes() == (old / "quark.json").read_bytes()
    assert old.exists()


@pytest.mark.parametrize("json_output", [False, True])
def test_doctor_cli_exit_code_and_redaction(monkeypatch, capsys, json_output):
    import misong.doctor as doctor
    monkeypatch.setattr(doctor, "check_environment", lambda: {"ok": False, "checks": [
        {"id": "dependency", "status": "error", "message": "密码：中文口令-synthetic"}]})
    args = build_parser().parse_args(["doctor"] + (["--json"] if json_output else []))
    assert args.fn(args) == 1
    text = capsys.readouterr().out
    assert "中文口令-synthetic" not in text and "REDACTED" in text
    if json_output:
        assert json.loads(text)["ok"] is False


def test_log_and_job_steps_are_redacted(tmp_path):
    api = Api(tmp_path / "runs", tmp_path / "state")
    job = {"kind": "restore"}
    api._notify(job)("密码：中文测试口令😀")
    event = api.poll()["data"]["events"][0]
    assert "中文测试口令" not in str(event) and "中文测试口令" not in job["step"]
    assert "REDACTED" in event["text"]


def test_migration_directory_file_conflict_has_no_partial_writes(tmp_path):
    old, dest = tmp_path / "old", tmp_path / "dest"
    (old / "empty").mkdir(parents=True)
    (old / "blocked").mkdir()
    (old / "a.txt").write_bytes(b"synthetic")
    dest.mkdir()
    (dest / "blocked").write_bytes(b"must stay")
    with pytest.raises(paths.MigrationError):
        paths.migrate_data(old, dest)
    assert sorted(p.name for p in dest.iterdir()) == ["blocked"]
    assert (dest / "blocked").read_bytes() == b"must stay"


def test_migration_rejects_linked_destination_ancestor(monkeypatch, tmp_path):
    old = tmp_path / "old"
    old.mkdir()
    (old / "a.txt").write_bytes(b"synthetic")
    actual = paths._is_link
    link = tmp_path / "linked-parent"
    monkeypatch.setattr(paths, "_is_link", lambda path: Path(path) == link or actual(path))
    with pytest.raises(paths.MigrationError, match="符号链接"):
        paths.migrate_data(old, link / "new-state")
    assert not link.exists()


def test_migration_unreadable_subdirectory_stops_before_writing(monkeypatch, tmp_path):
    old, target = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    def unreadable(*args, **kwargs):
        kwargs["onerror"](PermissionError("synthetic unreadable directory"))
        return iter(())
    monkeypatch.setattr(paths.os, "walk", unreadable)
    with pytest.raises(paths.MigrationError, match="完整读取"):
        paths.migrate_data(old, target)
    assert not target.exists() and old.exists()


@pytest.mark.parametrize("value", ["中文口令😀", "a", "very-long-synthetic-password-0123456789"])
def test_free_text_unicode_passwords_are_redacted_and_idempotent(value):
    text = "解压密码：" + value
    result = redact.redact_text(text)
    assert value not in result and redact.redact_text(result) == result


@pytest.mark.parametrize("text,value", [("password='space secret 中文'", "space secret 中文"),
                                        ('密码="secret words"', "secret words"), ("key=短码", "短码")])
def test_quoted_and_short_custom_secrets_are_redacted(text, value):
    result = redact.redact_text(text)
    assert value not in result and redact.redact_text(result) == result


def test_doctor_starts_when_core_dependencies_cannot_be_imported():
    root = Path(__file__).resolve().parents[1]
    code = r'''
import sys, importlib.abc
sys.path.insert(0, 'src')
class BlockCore(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'py7zr','pyzipper','lz4','zstandard','brotli','cryptography'}:
            raise ModuleNotFoundError('simulated missing dependency')
sys.meta_path.insert(0, BlockCore())
from misong.cli import main
raise SystemExit(main(['doctor','--json']))
'''
    result = subprocess.run([sys.executable, "-X", "utf8", "-c", code], cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=25)
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is False
    assert next(item for item in report["checks"] if item["id"] == "dependencies")["status"] == "error"
    assert "Traceback" not in result.stderr
