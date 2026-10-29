"""Offline tests for the read-only environment doctor; no network or browser launches."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from misong import doctor


def _completed(command, code=0, stdout=b"", stderr=b""):
    return subprocess.CompletedProcess(command, code, stdout, stderr)


@pytest.fixture
def healthy(tmp_path, monkeypatch):
    """A fully healthy fake environment; probes never touch the real machine."""
    root = tmp_path / "browsers"
    (root / "chromium-9999").mkdir(parents=True)
    (root / "chromium-9999" / "INSTALLATION_COMPLETE").touch()
    exe_dir = tmp_path / "bin"
    exe_dir.mkdir()

    monkeypatch.setattr(doctor, "_module_available", lambda name: True)
    monkeypatch.setattr(doctor, "_package_version", lambda name: "1.64.0")
    monkeypatch.setattr(doctor, "_sevenzip_executable", lambda: exe_dir / "7za.exe")
    monkeypatch.setattr(doctor, "_which", lambda name: str(exe_dir / "node.exe"))
    monkeypatch.setattr(doctor, "_playwright_browsers_root", lambda: root)
    monkeypatch.setattr(doctor, "_system_browsers", lambda: {"chrome": False, "msedge": False})

    def run(command, **kwargs):
        if Path(str(command[0])).name.startswith("node"):
            return _completed(command, 0, b"v24.1.0\r\n")
        return _completed(command, 0, b"\r\n7-Zip (a) 26.04 (x64) : Copyright (c) 1999-2026\r\n")

    monkeypatch.setattr(doctor.subprocess, "run", run)
    return SimpleNamespace(tmp_path=tmp_path, root=root, exe_dir=exe_dir,
                           run=run, monkeypatch=monkeypatch)


def _check(report, check_id):
    return next(check for check in report["checks"] if check["id"] == check_id)


def test_healthy_environment_is_ok(healthy):
    report = doctor.check_environment()
    assert report["ok"] is True
    assert [check["id"] for check in report["checks"]] == [
        "python", "dependencies", "7zip", "node", "playwright", "browsers", "desktop"]
    assert all(check["status"] == "ok" for check in report["checks"])
    assert all(check["message"] for check in report["checks"])
    assert {check["id"] for check in report["checks"] if check["required"]} == {
        "python", "dependencies", "7zip"}


def test_missing_core_dependency_is_error_and_report_completes(healthy):
    healthy.monkeypatch.setattr(doctor, "_module_available",
                                lambda name: name != "lz4")
    healthy.monkeypatch.setattr(doctor, "_sevenzip_executable",
                                lambda: (_ for _ in ()).throw(ImportError(str(healthy.tmp_path))))
    report = doctor.check_environment()
    dependencies = _check(report, "dependencies")
    assert dependencies["status"] == "error"
    assert "lz4" in dependencies["message"]
    assert _check(report, "7zip")["status"] == "error"
    assert "无法读取 7-Zip 探测入口" in _check(report, "7zip")["message"]
    assert str(healthy.tmp_path) not in _check(report, "7zip")["message"]
    assert report["ok"] is False
    assert len(report["checks"]) == 7


def test_missing_optional_tools_only_warns(healthy):
    healthy.monkeypatch.setattr(doctor, "_which", lambda name: None)
    healthy.monkeypatch.setattr(doctor, "_module_available",
                                lambda name: name not in {"playwright", "webview"})
    report = doctor.check_environment()
    for check_id in ("node", "playwright", "browsers", "desktop"):
        assert _check(report, check_id)["status"] == "warn"
    assert report["ok"] is True


def test_missing_7zip_is_a_required_error(healthy):
    healthy.monkeypatch.setattr(doctor, "_sevenzip_executable", lambda: None)
    report = doctor.check_environment()
    assert _check(report, "7zip")["status"] == "error"
    assert "7-Zip" in _check(report, "7zip")["message"]
    assert report["ok"] is False


def test_python_below_minimum_is_error(healthy):
    healthy.monkeypatch.setattr(doctor.sys, "version_info",
                                SimpleNamespace(major=3, minor=10, micro=9))
    report = doctor.check_environment()
    check = _check(report, "python")
    assert check["status"] == "error"
    assert "3.10.9" in check["message"] and "3.11" in check["message"]
    assert report["ok"] is False


@pytest.mark.parametrize("tool", ["node", "7zip"])
def test_probe_timeout_forms_a_result(healthy, tool):
    def run(command, **kwargs):
        name = Path(str(command[0])).name
        if tool == "node" and name.startswith("node"):
            raise subprocess.TimeoutExpired(command, kwargs.get("timeout"))
        if tool == "7zip" and name.startswith("7za"):
            raise subprocess.TimeoutExpired(command, kwargs.get("timeout"))
        if name.startswith("node"):
            return _completed(command, 0, b"v24.1.0\r\n")
        return _completed(command, 0, b"7-Zip (a) 26.04 (x64)")

    healthy.monkeypatch.setattr(doctor.subprocess, "run", run)
    report = doctor.check_environment()
    check = _check(report, tool)
    assert "超时" in check["message"]
    assert check["status"] == ("warn" if tool == "node" else "error")
    assert report["ok"] is (tool == "node")


@pytest.mark.parametrize("stdout", [b"\xff\xfe\x80\x81", b"\x00\x00", None])
def test_undecodable_or_empty_probe_output_is_tolerated(healthy, stdout):
    def run(command, **kwargs):
        return _completed(command, 0, stdout)

    healthy.monkeypatch.setattr(doctor.subprocess, "run", run)
    report = doctor.check_environment()
    assert _check(report, "node")["status"] == "warn"
    assert _check(report, "7zip")["status"] == "ok"
    assert report["ok"] is True


def test_unexpected_probe_exception_does_not_break_the_report(healthy):
    healthy.monkeypatch.setattr(doctor, "_run",
                                lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(str(healthy.tmp_path))))
    report = doctor.check_environment()
    assert len(report["checks"]) == 7
    assert _check(report, "7zip")["status"] == "error"
    assert _check(report, "node")["status"] == "warn"
    text = json.dumps(report, ensure_ascii=False)
    assert str(healthy.tmp_path) not in text
    assert "检查未能完成" in _check(report, "7zip")["message"]


def test_playwright_chromium_executable_without_marker_is_detected(healthy, tmp_path):
    root = tmp_path / "alternate-browsers"
    executable = root / "chromium-1234" / "chrome-win64" / "chrome.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    healthy.monkeypatch.setattr(doctor, "_playwright_browsers_root", lambda: root)
    report = doctor.check_environment()
    assert _check(report, "browsers")["status"] == "ok"
    assert report["ok"] is True


def test_system_browser_keeps_web_upload_usable_without_playwright_chromium(healthy):
    healthy.monkeypatch.setattr(doctor, "_playwright_browsers_root",
                                lambda: healthy.tmp_path / "no-browsers")
    healthy.monkeypatch.setattr(doctor, "_system_browsers",
                                lambda: {"chrome": True, "msedge": False})
    report = doctor.check_environment()
    check = _check(report, "browsers")
    assert check["status"] == "ok"
    assert "Chrome" in check["message"]
    assert report["ok"] is True


def test_system_browser_without_playwright_still_warns(healthy):
    healthy.monkeypatch.setattr(doctor, "_module_available",
                                lambda name: name != "playwright")
    healthy.monkeypatch.setattr(doctor, "_system_browsers",
                                lambda: {"chrome": False, "msedge": True})
    report = doctor.check_environment()
    check = _check(report, "browsers")
    assert check["status"] == "warn"
    assert "Playwright" in check["message"] and "Edge" in check["message"]


def test_no_paths_or_environment_values_are_reported(healthy):
    secret = "doctor-secret-value"
    secret_dir = healthy.tmp_path / secret
    secret_dir.mkdir()
    healthy.monkeypatch.setenv("LOCALAPPDATA", str(secret_dir))
    healthy.monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(secret_dir))
    healthy.monkeypatch.setattr(doctor, "_sevenzip_executable",
                                lambda: secret_dir / "7za.exe")
    healthy.monkeypatch.setattr(doctor, "_which",
                                lambda name: str(secret_dir / "node.exe"))

    def run(command, **kwargs):
        name = Path(str(command[0])).name
        if name.startswith("node"):
            return _completed(command, 0, f"{secret_dir}\\node.exe v24.1.0".encode())
        return _completed(command, 0, f"{secret_dir}\\7za.exe 7-Zip 26.04 (x64)".encode())

    healthy.monkeypatch.setattr(doctor.subprocess, "run", run)
    text = json.dumps(doctor.check_environment(), ensure_ascii=False)
    assert secret not in text
    assert str(healthy.tmp_path) not in text
    assert str(healthy.root) not in text


def test_nonzero_7zip_exit_code_reports_only_the_code(healthy):
    def run(command, **kwargs):
        return _completed(command, 2, b"failed with C:\\private\\7za.exe")

    healthy.monkeypatch.setattr(doctor.subprocess, "run", run)
    report = doctor.check_environment()
    check = _check(report, "7zip")
    assert check["status"] == "error"
    assert "代码 2" in check["message"]
    assert "private" not in check["message"]
