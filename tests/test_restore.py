"""Real archive/volume restoration and fake-drive key delivery."""
import asyncio
import json
import shutil

import pytest

from misong import pack, restore_key, workflows
from misong.layers import LayerSpec as L
from misong.publish import Paused, import_share
from misong.restore import restore
from test_packaging_redesign import video
from test_publish import FakeRuntime, load, make_job, run


def bundle(tmp_path, layers=None, *, name="bundle.zip"):
    source = tmp_path / "original"
    source.mkdir(exist_ok=True)
    (source / "中文😀.txt").write_bytes(bytes(range(256)) * 12)
    artifact = tmp_path / name
    mf = pack.pack([source], layers or [L("zip", "test-secret-inner"), L("7z", "test-secret-outer", True)],
                   artifact, export_key=True)
    return source, artifact, mf, restore_key.sidecar(artifact)


def test_two_files_restore_without_sidecars(tmp_path):
    source, artifact, mf, key = bundle(tmp_path)
    download = tmp_path / "download"
    download.mkdir()
    shutil.copy2(artifact, download / artifact.name)
    shutil.copy2(key, download / key.name)
    result = restore(download, tmp_path / "back", notify=lambda _: None)
    assert result["verified"] and result["layers"] == 2
    assert (tmp_path / "back/original/中文😀.txt").read_bytes() == (source / "中文😀.txt").read_bytes()
    assert len(list(download.iterdir())) == 2


def test_complex_layers_cover_split_and_rewrap(tmp_path, video):
    layers = [L("lz4"), L("zip", "inner-a"), L(type="cover", video=str(video)),
              L(type="split", size="1K"), L("7z", "outer-b", True), L(type="rename", ext="mkv")]
    source, artifact, mf, key = bundle(tmp_path, layers, name="complex.mkv")
    progress = []
    restore(artifact, tmp_path / "back", key, notify=progress.append)
    assert (tmp_path / "back/original/中文😀.txt").read_bytes() == (source / "中文😀.txt").read_bytes()
    assert len([p for p in progress if p.startswith("还原：")]) == 6
    assert "inner-a" not in " ".join(progress) and "outer-b" not in " ".join(progress)


def test_outer_split_from_any_volume_and_missing_volume(tmp_path):
    source, _, mf, key = bundle(tmp_path, [L("zip", "pw"), L(type="split", size="100B")])
    assert len(mf["artifacts"]) > 1
    selected = tmp_path / mf["artifacts"][-1]["name"]
    restore(selected, tmp_path / "back", key, notify=lambda _: None)
    assert (tmp_path / "back/original/中文😀.txt").read_bytes() == (source / "中文😀.txt").read_bytes()
    (tmp_path / mf["artifacts"][0]["name"]).unlink()
    with pytest.raises(ValueError, match="缺少分卷"):
        restore(selected, tmp_path / "missing", key)
    assert not (tmp_path / "missing").exists()


def test_wrong_key_or_corruption_leaves_output_untouched(tmp_path):
    _, artifact, _, key = bundle(tmp_path)
    original = artifact.read_bytes()
    artifact.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    out = tmp_path / "back"
    with pytest.raises(ValueError, match="校验不符"):
        restore(artifact, out, key)
    assert not out.exists() and key.exists()


def test_mismatched_layer_password_is_sanitized(tmp_path):
    _, artifact, mf, _ = bundle(tmp_path, [L("zip", "right-secret")])
    key = tmp_path / "wrong.mskey"
    restore_key.write(key, mf, ["bad-secret-not-in-errors"])
    with pytest.raises(ValueError, match="第 1 层") as exc:
        restore(artifact, tmp_path / "back", key)
    assert "bad-secret" not in str(exc.value) and not (tmp_path / "back").exists()


def test_renamed_single_artifact_and_existing_output(tmp_path):
    _, artifact, _, key = bundle(tmp_path)
    renamed = artifact.rename(tmp_path / "renamed.bin")
    out = tmp_path / "back"
    out.mkdir()
    (out / "keep").write_text("keep")
    with pytest.raises(ValueError, match="必须为空"):
        restore(renamed, out, key)
    assert (out / "keep").read_text() == "keep"
    restore(renamed, tmp_path / "fresh", key, notify=lambda _: None)
    assert (tmp_path / "fresh/original/中文😀.txt").is_file()


def test_ambiguous_key_requires_explicit_selection(tmp_path):
    _, artifact, _, key = bundle(tmp_path)
    shutil.copy2(key, tmp_path / "another.mskey")
    with pytest.raises(ValueError, match="多把"):
        restore(artifact, tmp_path / "back")
    restore(artifact, tmp_path / "back", key, notify=lambda _: None)


@pytest.mark.parametrize("location,form,disk", [("local", "direct", None), ("body", "direct", "quark"),
                                                ("hop", "simple", "feimao"), ("hop", "complex", "feimao")])
def test_key_delivery_and_cleanup_retains_key(tmp_path, location, form, disk):
    plan_path = make_job(tmp_path, form, restore_key_location=location, cleanup_after_upload=True)
    plan = load(plan_path)
    from pathlib import Path
    key = Path(plan["restore_key"]["file"]["path"])
    runtime = FakeRuntime()
    run(plan_path, runtime, hop_password="hop-test-only" if form == "complex" else None)
    sent = [(event[1], event[2]) for event in runtime.events if event[0] == "upload" and event[2].endswith(".mskey")]
    assert sent == ([(disk, key.name)] if disk else [])
    assert key.is_file()
    assert restore_key.read(key)["passwords"] == [None, "secret", None]
    for path in plan_path.parent.rglob("*.json"):
        assert '"secret"' not in path.read_text(encoding="utf-8")
    assert load(plan_path)["state"] == "complete"


def test_replaced_first_hop_reuses_same_key(tmp_path):
    path = make_job(tmp_path, "simple", restore_key_location="hop")
    run(path, FakeRuntime())
    before = load(path)["restore_key"]["file"]
    import_share(path, "body", "https://pan.quark.cn/s/replacement 提取码:z123")
    runtime = FakeRuntime()
    run(path, runtime)
    assert load(path)["restore_key"]["file"] == before
    from pathlib import Path
    assert ("upload", "feimao", Path(before["path"]).name) in runtime.events


def test_hop_key_with_direct_mode_rejected_before_writing(tmp_path):
    with pytest.raises(ValueError, match="中转"):
        make_job(tmp_path, "direct", restore_key_location="hop")
    assert not (tmp_path / "output").exists()


def test_cancel_before_unpack_preserves_inputs(tmp_path):
    _, artifact, _, key = bundle(tmp_path)
    def cancel():
        raise Paused("已暂停")
    with pytest.raises(Paused):
        restore(artifact, tmp_path / "back", key, check_cancel=cancel)
    assert artifact.exists() and key.exists() and not (tmp_path / "back").exists()


@pytest.mark.parametrize("fmt", ["lz4", "zst", "br", "gz", "bz2", "xz", "lzma", "tar"])
def test_raw_and_tar_layers_restore_directory(tmp_path, fmt):
    source, artifact, _, key = bundle(tmp_path, [L(fmt), L("7z", "raw-test-only", True)])
    restore(artifact, tmp_path / "back", key, notify=lambda _: None)
    assert (tmp_path / "back/original/中文😀.txt").read_bytes() == (source / "中文😀.txt").read_bytes()


def test_pause_between_layers_has_no_partial_result(tmp_path):
    _, artifact, _, key = bundle(tmp_path)
    halted = False
    def notify(message):
        nonlocal halted
        if message.startswith("还原：第 1/"):
            halted = True
    def cancel():
        if halted:
            raise Paused("已暂停")
    with pytest.raises(Paused):
        restore(artifact, tmp_path / "back", key, notify=notify, check_cancel=cancel)
    assert not (tmp_path / "back").exists()
    assert artifact.exists() and key.exists() and not list(tmp_path.glob(".misong-restore-*"))


def test_unicode_zip_password_and_key_restore(tmp_path, monkeypatch):
    from misong import formats
    # Prove the Unicode password works through the actual Python ZIP backend,
    # rather than treating the native 7za limitation as an invalid password.
    def no_native(*args, **kwargs):
        raise AssertionError("Unicode ZIP passwords must use the UTF-8 backend")
    monkeypatch.setattr(formats, "_sevenzip", no_native)
    source, artifact, _, key = bundle(tmp_path, [L("zip", "中文密码😀-test-only")])
    restore(artifact, tmp_path / "back", key, notify=lambda _: None)
    assert (tmp_path / "back/original/中文😀.txt").read_bytes() == (source / "中文😀.txt").read_bytes()
