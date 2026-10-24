"""Regression coverage for the v2 packaging engine; no network or credentials."""
import io
import json
import os
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path

import py7zr
import pytest

from misong import formats, merge, pack, split
from misong.layers import LayerSpec as L, validate
from misong.mp4 import box_header, rewrite_moov, relocate_zip, zip_directory

# ffmpeg is optional: PATH first, then MISONG_FFMPEG=<path to ffmpeg executable>.
FFMPEG = shutil.which("ffmpeg") or os.environ.get("MISONG_FFMPEG", os.environ.get("NDE_FFMPEG", ""))


@pytest.fixture
def video(tmp_path):
    ffmpeg = FFMPEG
    if not ffmpeg or not Path(ffmpeg).is_file():
        pytest.skip("ffmpeg unavailable; MP4 playback requires local validation")
    path = tmp_path / "intro.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=160x120:rate=10:duration=1", "-c:v", "libx264",
                    "-movflags", "+faststart", str(path)], check=True)
    return path


@pytest.mark.parametrize("native", [True, False])
@pytest.mark.parametrize("fmt", ["7z", "zip"])
def test_backends_roundtrip(tmp_path, monkeypatch, native, fmt):
    if native and not formats.sevenzip_executable():
        pytest.skip("7za unavailable")
    if not native:
        monkeypatch.setattr(formats, "sevenzip_executable", lambda: None)
    src = tmp_path / "中文.txt"
    src.write_bytes(b"content" * 20)
    out = tmp_path / ("a." + fmt)
    formats.compress(fmt, src, out, password="test-only", header_enc=True, level=0)
    dst = formats.extract(fmt, out, tmp_path / "restore", password="test-only")
    assert dst.read_bytes() == src.read_bytes()
    with pytest.raises(Exception):
        formats.extract(fmt, out, tmp_path / "wrong", password="wrong")


def test_sevenzip_no_window_and_sanitized_error(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(formats, "sevenzip_executable", lambda: tmp_path / "7za.exe")
    def run(args, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(args, 2, b"test-only", b"")
    monkeypatch.setattr(formats.subprocess, "run", run)
    with pytest.raises(RuntimeError) as e:
        formats._sevenzip(["-ptest-only"])
    assert "test-only" not in str(e.value)
    assert seen["creationflags"] == formats.NO_WINDOW


@pytest.mark.parametrize("fmt", ["zip", "7z"])
def test_cover_decodes_and_opens(tmp_path, video, fmt):
    src = tmp_path / "original.txt"
    src.write_bytes(b"identical payload" * 400)
    arc, out = tmp_path / ("a." + fmt), tmp_path / "cover.mp4"
    formats.compress(fmt, src, arc)
    merge.embed_in_mp4(video, arc, out, fmt)
    if fmt == "zip":
        with zipfile.ZipFile(out) as z:
            assert z.read(src.name) == src.read_bytes()
    else:
        extracted = merge.extract_embedded(out, tmp_path / "embedded.7z")
        with py7zr.SevenZipFile(extracted) as z:
            z.extractall(tmp_path / "python")
        assert (tmp_path / "python" / src.name).read_bytes() == src.read_bytes()
    ffmpeg = FFMPEG
    def frames(path):
        r = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-map", "0", "-f", "framemd5", "-"],
                           capture_output=True, check=True)
        return [l for l in r.stdout.splitlines() if l and not l.startswith(b"#")]
    assert frames(out) == frames(video)
    if exe := formats.sevenzip_executable():
        r = subprocess.run([str(exe), "t", str(out)], capture_output=True)
        assert r.returncode in (0, 1), r.stdout


def test_fancy_chain_roundtrip(tmp_path, video):
    src = tmp_path / "资源"
    src.mkdir()
    (src / "中文.txt").write_bytes(bytes(range(256)) * 300)
    layers = [L("7z", "a"), L("zip", "b"), L(type="cover", video=str(video)),
              L(type="split", size="10K"), L("7z"), L("7z", "c"), L(type="cover", video=str(video))]
    out = tmp_path / "fancy.mp4"
    mf = pack.pack([src], layers, out)
    assert mf["version"] == 2
    assert "\"a\"" not in json.dumps(mf)
    restored = pack.unest(out, tmp_path / "back", [None, "c", None, None, None, "b", "a"])[0]
    assert (restored / "中文.txt").read_bytes() == (src / "中文.txt").read_bytes()
    sniffed = merge.unwrap(out, tmp_path / "sniff", chain=["c", None, "b", "a"])[-1]
    assert (sniffed / "中文.txt").read_bytes() == (src / "中文.txt").read_bytes()


def test_rename_split_and_missing_last(tmp_path):
    src = tmp_path / "source.bin"
    src.write_bytes(bytes(range(256)) * 100)
    out = tmp_path / "result.mp4"
    layers = [L("zip", level=0), L(type="rename", ext=".mp4"), L(type="split", size="10K")]
    mf = pack.pack([src], layers, out)
    first = tmp_path / mf["artifacts"][0]["name"]
    assert first.name == "result.mp4.001"
    assert not out.exists()
    assert pack.unest(first, tmp_path / "back", [None] * 3)[0].read_bytes() == src.read_bytes()
    (tmp_path / mf["artifacts"][-1]["name"]).unlink()
    with pytest.raises((ValueError, RuntimeError), match="缺少分卷"):
        pack.unest(first, tmp_path / "missing", [])


def test_no_split_at_boundary_and_mb_default(tmp_path):
    assert split.parse_size("150") == 150 * 1024**2
    assert split.parse_size("150B") == 150
    assert split.parse_size("1.5GB") == int(1.5 * 1024**3)
    src = tmp_path / "x.bin"
    src.write_bytes(b"abc")
    mf = split.split(src, 3, tmp_path / "vol")
    assert mf["parts"][0]["name"] == "x.bin"
    assert not list((tmp_path / "vol").glob("*.001"))


def test_invalid_layer_sequences(tmp_path):
    for chain in ([L(type="split"), L(type="rename", ext="mp4")],
                  [L(type="cover", video="no.mp4")],
                  [L(type="rename", ext="../bad")]):
        with pytest.raises(ValueError):
            validate(chain)


def test_stco_promotes_and_updates_ancestors():
    entries = b"\0" * 4 + struct.pack(">I2I", 2, 100, 0xFFFFFFF0)
    def box(kind, payload):
        return box_header(kind, len(payload)) + payload
    src = box(b"moov", box(b"trak", box(b"mdia", box(b"minf", box(b"stbl", box(b"stco", entries))))))
    dst = rewrite_moov(src, lambda n: n + 100)
    assert b"co64" in dst and b"stco" not in dst
    assert len(dst) == len(src) + 8
    assert struct.unpack_from(">I", dst)[0] == len(dst)
    assert struct.pack(">Q", 0x100000054) in dst


def test_zip64_offset_promotion_and_reverse():
    original = io.BytesIO()
    with zipfile.ZipFile(original, "w") as z:
        z.writestr("source.txt", b"payload")
    shifted = io.BytesIO()
    relocate_zip(io.BytesIO(original.getvalue()), shifted, 2**32 + 200)
    raw = shifted.getvalue()
    assert b"PK\x06\x06" in raw and b"PK\x06\x07" in raw
    restored = io.BytesIO()
    relocate_zip(io.BytesIO(raw), restored, -(2**32 + 200), offset_base=2**32 + 200)
    with zipfile.ZipFile(io.BytesIO(restored.getvalue())) as z:
        assert z.read("source.txt") == b"payload"


def test_existing_zip64_local_extra_preserved():
    original = io.BytesIO()
    with zipfile.ZipFile(original, "w") as z:
        with z.open("force.bin", "w", force_zip64=True) as f:
            f.write(b"force zip64")
    shifted = merge._fix_zip_offsets(original.getvalue(), 64)
    with zipfile.ZipFile(io.BytesIO(b"x" * 64 + shifted)) as z:
        assert z.read("force.bin") == b"force zip64"


def test_v1_manifest_and_keep_layers(tmp_path):
    src = tmp_path / "a.txt"
    src.write_bytes(b"old compatible")
    out = tmp_path / "a.zip"
    mf = pack.pack([src], [L("zip")], out, keep_layers=True)
    assert (tmp_path / "a.zip.layers" / "L0" / "layer0.zip").exists()
    mf["version"] = 1
    mf["layers"] = [{k: r[k] for k in ("format", "password", "header_enc", "tar_pre")} for r in mf["layers"]]
    assert pack.unest(out, tmp_path / "old", [], mf)[0].read_bytes() == src.read_bytes()


@pytest.mark.parametrize("checksum", [False, True])
def test_publish_only_final_files_and_checksums(tmp_path, checksum):
    from misong.publish import PublishOptions, prepare
    from misong import workflows
    src = tmp_path / "input.bin"
    src.write_bytes(bytes(range(256)) * 20)
    plan = prepare(PublishOptions([src], tmp_path / "job", [L("zip", level=0)],
                                  size="1K", schemes=("beast",), checksum=checksum), lambda _: None)
    data = json.loads(plan.read_text(encoding="utf-8"))
    files = [Path(x["path"]) for x in data["stages"][0]["files"]]
    assert all(not workflows.is_local_metadata(p) for p in files)
    assert any(p.suffix == ".sha256" for p in files) == checksum
    assert all(p.suffix[1:].isdigit() or p.suffix == ".sha256" for p in files)
    if checksum:
        text = next(p for p in files if p.suffix == ".sha256").read_text()
        for p in files:
            if p.suffix != ".sha256":
                assert f"{pack._sha256(p)}  {p.name}\n" in text
    assert list(plan.parent.rglob("*.misong.json"))
    assert list(plan.parent.rglob("RESTORE.txt"))


@pytest.mark.parametrize("checksum", [False, True])
def test_upload_filters_local_sidecars(tmp_path, checksum):
    from misong import workflows
    files = []
    for name in ("a.7z.001", "a.7z.002", "a.misong.json", "a.misongsplit.json", "RESTORE.txt", "a.sha256"):
        p = tmp_path / name
        p.write_bytes(b"test")
        files.append(p)
    path = workflows.prepare_upload(files, tmp_path / "upload", ["quark"], checksum=checksum)
    names = [Path(r["path"]).name for r in json.loads(path.read_text())["stages"][0]["files"]]
    assert names == ["a.7z.001", "a.7z.002"] + (["checksums.sha256"] if checksum else [])


def test_space_preflight_blocks_and_uses_largest_disk(tmp_path, monkeypatch):
    from collections import namedtuple
    from misong import preflight
    src = tmp_path / "src.bin"
    src.write_bytes(b"data")
    usage = namedtuple("Usage", "total used free")
    alternate = tmp_path / "alternate"
    alternate.mkdir()
    monkeypatch.setattr(preflight, "disk_roots", lambda target: [alternate])
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda path: usage(100, 99, 1))
    report = preflight.estimate([src], [L("zip")], tmp_path / "job")
    assert not report["ok"] and "当前最大可用盘" in report["message"] and "GB" in report["message"]
    with pytest.raises(ValueError, match="需要约"):
        preflight.require([src], [L("zip")], tmp_path / "job", lambda _: None)
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda path: usage(10**12, 0, 10**12 if Path(path) == alternate else 1))
    report = preflight.estimate([src], [L("zip")], tmp_path / "job")
    assert report["ok"] and report["relocated"]
    assert Path(report["out"]) == alternate / "misong-runs" / "job"
    assert "总读写" in report["message"] and "预计约" in report["message"]


def test_preflight_peak_does_not_multiply_by_layer_count(tmp_path):
    from misong.preflight import estimate
    src = tmp_path / "large.bin"
    with src.open("wb") as f:
        f.truncate(20 * 1024**2)
    one = estimate([src], [L("7z")], tmp_path / "one")
    many = estimate([src], [L("7z")] * 8, tmp_path / "many")
    assert many["required_bytes"] < one["required_bytes"] * 2
    assert many["io_bytes"] > one["io_bytes"] * 7


def test_api_new_templates_and_settings_strip_passwords(tmp_path, video):
    from misong.desktop.api import Api
    api = Api(tmp_path / "runs", tmp_path / "state")
    assert api._layers([{"fmt": "7z", "password": "test-only"}])[0].header_enc
    assert not api._layers([{"fmt": "7z"}])[0].header_enc
    layers = [{"type": "archive", "fmt": "zip", "password": "never-save-this", "level": 0},
              {"type": "cover", "video": str(video)}, {"type": "rename", "ext": ".mkv"},
              {"type": "split", "size": "150MB"}]
    assert api.save_template("new types", layers)["ok"]
    assert api.save_settings({"layers": layers, "layers_version": 2, "checksum": True})["ok"]
    for p in (tmp_path / "state").glob("*.json"):
        assert "never-save-this" not in p.read_text(encoding="utf-8")
    loaded = api.bootstrap()["data"]["settings"]
    assert loaded["layers"][1]["video"] == str(video)
    assert loaded["layers"][-1]["size"] == "150MB"
    assert loaded["layers_version"] == 2 and loaded["checksum"]


def test_api_preflight_blocks_before_background_job(tmp_path, monkeypatch):
    from misong.desktop.api import Api
    from misong import preflight
    api = Api(tmp_path / "runs", tmp_path / "state")
    src = tmp_path / "src.txt"
    src.write_text("payload")
    cfg = {"inputs": [str(src)], "layers": [{"type": "archive", "fmt": "7z"}], "layers_version": 2}
    monkeypatch.setattr(preflight, "estimate", lambda *a, **k: {"ok": False, "message": "需要约 10 GB"})
    assert api.preflight_pack(cfg)["data"]["ok"] is False
    assert "需要约" in api.start_pack(cfg)["error"]
    assert api.poll()["data"]["job"] is None
    assert not (tmp_path / "runs").exists()


def test_legacy_part_names_still_join(tmp_path):
    src = tmp_path / "source.bin"
    src.write_bytes(b"abcdefgh")
    folder = tmp_path / "old"
    mf = split.split(src, 3, folder)
    for r in mf["parts"]:
        p = folder / r["name"]
        new = p.with_name(p.name[:-3] + "part" + p.name[-3:])
        p.rename(new)
        r["name"] = new.name
    (folder / (src.name + split.SIDECAR_EXT)).write_text(json.dumps(mf))
    assert split.join(folder / "source.bin.part001").read_bytes() == src.read_bytes()


def test_grouping_links_released_before_next_layer(tmp_path, monkeypatch):
    src = tmp_path / "source.bin"
    src.write_bytes(bytes(range(256)) * 100)
    compress = formats.compress
    seen = []
    def checked(fmt, source, dest, **kwargs):
        if source.is_file() and source.name == "layer2.7z":
            assert not (source.parent / "bundle").exists()
            assert not (source.parent.parent / "step1").exists()
            seen.append(True)
        return compress(fmt, source, dest, **kwargs)
    monkeypatch.setattr(formats, "compress", checked)
    out = tmp_path / "release.zip"
    pack.pack([src], [L("zip", level=0), L(type="split", size="1K"), L("7z"), L("zip")], out)
    assert seen
    assert pack.unest(out, tmp_path / "back", [None] * 4)[0].read_bytes() == src.read_bytes()
