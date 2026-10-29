"""数据目录解析与显式迁移的回归（全部使用 tmp_path 合成内容，不接触真实 rpa/state）。"""
import sys
from pathlib import Path

import pytest

import misong.paths as mp
from misong.paths import MigrationError, Paths, migrate_data, resolve_paths

REPO = Path(__file__).resolve().parents[1]


def use_installed_layout(monkeypatch):
    """模拟普通安装：源码根探测返回 None。"""
    monkeypatch.setattr(mp, "_source_root", lambda: None)
    monkeypatch.delenv("MISONG_HOME", raising=False)


def build_state(tmp_path):
    """合成已登录状态、设置与任务目录；不使用真实 rpa/state 内容。"""
    state = tmp_path / "old-state"
    (state / "profiles").mkdir(parents=True)
    (state / "session-data").mkdir()
    (state / "failures").mkdir()
    (state / "quark.json").write_text('{"cookies": [{"name": "sid", "value": "synthetic"}]}', encoding="utf-8")
    (state / "quark-status.json").write_text('{"status": "ready", "verified_at": "2026-10-26T10:00:00"}', encoding="utf-8")
    (state / "ui-settings.json").write_text('{"output_dir": "X:/runs/task-a"}', encoding="utf-8")
    (state / "profiles" / "quark.json").write_text('{"url": "https://pan.example.com/synthetic"}', encoding="utf-8")
    (state / "session-data" / "quark-chromium.json").write_text('{"https://pan.example.com": {"k": "v"}}', encoding="utf-8")
    return state


def build_runs(tmp_path):
    runs = tmp_path / "old-runs"
    task = runs / "task-a"
    task.mkdir(parents=True)
    (task / "misong-task.json").write_text('{"title": "示例任务"}', encoding="utf-8")
    (task / "payload.bin").write_bytes(b"\x00\x01binary")
    return runs


def assert_tree_equal(source, destination):
    for path in source.rglob("*"):
        copy = destination / path.relative_to(source)
        assert copy.is_dir() == path.is_dir()
        if path.is_file():
            assert copy.read_bytes() == path.read_bytes()


def test_misong_home_overrides_and_nests_state_runs(monkeypatch, tmp_path):
    monkeypatch.setenv("MISONG_HOME", str(tmp_path / "msdata"))
    paths = resolve_paths()
    assert isinstance(paths, Paths)
    assert all(isinstance(getattr(paths, name), Path) for name in ("home", "state", "runs"))
    assert paths.home == (tmp_path / "msdata").resolve()
    assert paths.state == paths.home / "rpa" / "state"
    assert paths.runs == paths.home / "runs"


def test_misong_home_resolves_relative_against_cwd_without_creating(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MISONG_HOME", "rel-data")
    paths = resolve_paths()
    assert paths.home == (tmp_path / "rel-data").resolve()
    assert not paths.home.exists()  # 只解析，不创建目录


def test_misong_home_expands_user(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MISONG_HOME", "~/msdata")
    assert resolve_paths().home == tmp_path / "msdata"


def test_blank_misong_home_counts_as_unset(monkeypatch):
    monkeypatch.setenv("MISONG_HOME", " ")
    paths = resolve_paths()
    assert paths.home == REPO
    assert paths.state == REPO / "rpa" / "state"
    assert paths.runs == REPO / "runs"


def test_source_checkout_without_env_keeps_repo_dirs(monkeypatch):
    monkeypatch.delenv("MISONG_HOME", raising=False)
    paths = resolve_paths()
    assert paths.home == REPO
    assert paths.state == REPO / "rpa" / "state"
    assert paths.runs == REPO / "runs"


def test_installed_default_uses_localappdata(monkeypatch, tmp_path):
    use_installed_layout(monkeypatch)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    if sys.platform != "win32":
        monkeypatch.setattr(sys, "platform", "win32")
    paths = resolve_paths()
    assert paths.home == tmp_path / "misong"
    assert paths.state == tmp_path / "misong" / "rpa" / "state"
    assert paths.runs == tmp_path / "misong" / "runs"


def test_installed_default_without_localappdata_uses_home(monkeypatch, tmp_path):
    use_installed_layout(monkeypatch)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    if sys.platform != "win32":
        monkeypatch.setattr(sys, "platform", "win32")
    assert resolve_paths().home == tmp_path / "AppData" / "Local" / "misong"


def test_installed_default_macos_application_support(monkeypatch, tmp_path):
    use_installed_layout(monkeypatch)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert resolve_paths().home == tmp_path / "Library" / "Application Support" / "misong"


def test_installed_default_linux_prefers_xdg_data_home(monkeypatch, tmp_path):
    use_installed_layout(monkeypatch)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert resolve_paths().home == tmp_path / "xdg" / "misong"


def test_installed_default_linux_without_xdg_uses_home(monkeypatch, tmp_path):
    use_installed_layout(monkeypatch)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert resolve_paths().home == tmp_path / ".local" / "share" / "misong"


def test_migration_copies_logged_in_state_settings_and_tasks_losslessly(tmp_path):
    state, runs = build_state(tmp_path), build_runs(tmp_path)
    home = tmp_path / "new-home"
    migrate_data(state, home / "rpa" / "state")
    migrate_data(runs, home / "runs")
    assert_tree_equal(state, home / "rpa" / "state")
    assert_tree_equal(runs, home / "runs")
    assert (home / "rpa" / "state" / "failures").is_dir()  # 空目录也保留
    # 原数据完整保留，不做移动或删除
    assert (state / "quark.json").read_text(encoding="utf-8").startswith('{"cookies"')
    assert (runs / "task-a" / "payload.bin").read_bytes() == b"\x00\x01binary"


def test_migration_rejects_destination_with_different_content(tmp_path):
    state = build_state(tmp_path)
    destination = tmp_path / "dest"
    (destination / "session-data").mkdir(parents=True)
    (destination / "quark.json").write_text('{"cookies": [{"name": "OTHER"}]}', encoding="utf-8")
    with pytest.raises(MigrationError):
        migrate_data(state, destination)
    # 拒绝发生在任何复制之前：目标保持原样
    assert (destination / "quark.json").read_text(encoding="utf-8") == '{"cookies": [{"name": "OTHER"}]}'
    assert not (destination / "ui-settings.json").exists()


def test_migration_treats_identical_destination_as_done(tmp_path):
    state = build_state(tmp_path)
    destination = tmp_path / "dest"
    migrate_data(state, destination)
    migrate_data(state, destination)  # 相同内容跳过，幂等重跑
    assert_tree_equal(state, destination)


def test_migration_rejects_missing_source(tmp_path):
    with pytest.raises(MigrationError):
        migrate_data(tmp_path / "nope", tmp_path / "dest")


def test_migration_rejects_file_destination(tmp_path):
    state = build_state(tmp_path)
    destination = tmp_path / "dest-file"
    destination.write_text("occupied", encoding="utf-8")
    with pytest.raises(MigrationError):
        migrate_data(state, destination)


def test_migration_rejects_destination_inside_source(tmp_path):
    state = build_state(tmp_path)
    with pytest.raises(MigrationError):
        migrate_data(state, state / "rpa" / "state")


def test_migration_rejects_symlink_entries(tmp_path):
    state = build_state(tmp_path)
    target = state / "quark-status.json"
    link = state / "linked.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("当前环境不允许创建符号链接")
    with pytest.raises(MigrationError):
        migrate_data(state, tmp_path / "dest")
    assert not (tmp_path / "dest").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="junction 仅 Windows")
def test_migration_rejects_junction_escape(tmp_path):
    import _winapi
    state = build_state(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("escape", encoding="utf-8")
    _winapi.CreateJunction(str(outside), str(state / "linked"))
    with pytest.raises(MigrationError):
        migrate_data(state, tmp_path / "dest")
    assert not (tmp_path / "dest").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="junction 仅 Windows")
def test_migration_rejects_symlinked_destination_junction(tmp_path):
    import _winapi
    state = build_state(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    _winapi.CreateJunction(str(elsewhere), str(tmp_path / "dest"))
    with pytest.raises(MigrationError):
        migrate_data(state, tmp_path / "dest")
    assert not (elsewhere / "quark.json").exists()


def test_runtime_root_and_default_state_stay_compatible():
    from misong.rpa import runtime
    assert runtime.ROOT == REPO  # 源码根兼容符号不变
    assert runtime.DEFAULT_STATE == resolve_paths().state  # 默认值改为解析结果


def test_browser_runtime_resolves_state_dir_at_construction(monkeypatch, tmp_path):
    from misong.rpa import runtime
    monkeypatch.setenv("MISONG_HOME", str(tmp_path / "late-home"))
    first = runtime.BrowserRuntime()
    assert first.state_dir == tmp_path / "late-home" / "rpa" / "state"
    monkeypatch.setenv("MISONG_HOME", str(tmp_path / "another"))
    assert runtime.BrowserRuntime().state_dir == tmp_path / "another" / "rpa" / "state"
    assert first.state_dir == tmp_path / "late-home" / "rpa" / "state"  # 已建实例不受影响


def test_browser_runtime_keeps_explicit_state_dir(monkeypatch, tmp_path):
    from misong.rpa import runtime
    monkeypatch.setenv("MISONG_HOME", str(tmp_path / "ignored"))
    assert runtime.BrowserRuntime(state_dir=tmp_path / "explicit").state_dir == tmp_path / "explicit"
