"""End-to-end verification for netdisk-encrypt toolbox.

Run: .venv/Scripts/python -m pytest tests -v
Heavy JS interop tests are skipped automatically when node/deps missing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nde import formats, merge, pack, split as splitmod  # noqa: E402
from nde.encoders import beast, hajimi, mojibake, plain  # noqa: E402

# ---------------------------------------------------------------- fixtures

@pytest.fixture()
def sample_dir(tmp_path):
    d = tmp_path / "my_resource"
    d.mkdir()
    (d / "note.txt").write_text("资源说明书 hello 世界 " * 50, encoding="utf-8")
    (d / "data.bin").write_bytes(bytes(range(256)) * 3000)
    return d


@pytest.fixture()
def small_mp4(tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("no ffmpeg")
    p = tmp_path / "intro.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10:duration=1",
         "-c:v", "libx264", "-preset", "ultrafast", "-movflags", "+faststart",
         str(p)],
        check=True)
    assert p.stat().st_size > 1000
    return p


def cli(*args, expect_ok=True):
    r = subprocess.run(
        [sys.executable, str(ROOT / "nde.py"), *map(str, args)],
        capture_output=True, cwd=str(ROOT))
    if expect_ok and r.returncode != 0:
        raise AssertionError(f"CLI failed: {r.stderr.decode('utf-8', 'replace')}")
    return r


# ---------------------------------------------------------------- beast vectors

def test_beast_official_vectors():
    assert beast.encode("你好", dialect="sdk") == "呜嗷嗷嗷啊嗷嗷~啊呜~啊~呜呜嗷"
    assert beast.decode("呜嗷嗷嗷啊嗷嗷~啊呜~啊~呜呜嗷", dialect="sdk") == "你好"


@pytest.mark.parametrize("dialect", ["sdk", "web", "pojie"])
def test_beast_dialects_roundtrip(dialect):
    t = "https://pan.xunlei.com/s/ExampleLink 提取码:ab3d 密码:123"
    d = ("嗷", "呜", "喵", "~") if dialect == "pojie" else beast.DEFAULT_DICT
    c = beast.encode(t, chars=d, dialect=dialect)
    assert beast.decode(c, chars=d, dialect=dialect) == t
    assert beast.decode(c, chars=d, dialect="auto") == t


def test_beast_custom_dict():
    t = "链接 https://a.b/c 密码 d"
    c = beast.encode(t, chars="点赞投币")
    assert beast.decode(c, chars="点赞投币") == t


# ---------------------------------------------------------------- plain schemes

@pytest.mark.parametrize("scheme", list(plain.SCHEMES))
def test_plain_roundtrip(scheme):
    t = "https://pan.baidu.com/s/1abc?pwd=1234 提取码:1234"
    if scheme == "trunc":
        c = plain.encode(scheme, t)
        assert t[:8] in c and t[-10:] in c
        return
    assert plain.decode(scheme, plain.encode(scheme, t)) == t


def test_chain_encode_decode():
    t = "https://example.com/s/xyz 密码:q7"
    c = beast.encode(t)
    c2 = plain.encode("base64", c)
    back = beast.decode(plain.decode("base64", c2))
    assert back == t


# ---------------------------------------------------------------- hajimi

def test_hajimi_roundtrip_stress():
    rng_samples = [
        "https://pan.quark.cn/s/abc123 提取码:K9mZ",
        "链接在评论区，密码见简介 123456",
        "a" * 300,
        "混合 mixed 文本😀 emoji",
    ]
    enc = hajimi.Encoder()
    for t in rng_samples:
        assert enc.decode(enc.encode(t)) == t


def test_hajimi_cross_lang_js():
    node = shutil.which("node")
    harness = ROOT / "tests" / "harness" / "hajimi_node.mjs"
    if not node or not harness.exists():
        pytest.skip("node/harness unavailable")
    t = "https://drive.uc.cn/s/sample 提取码:hx77 密码:1234"
    r = subprocess.run([node, str(harness), "enc"], input=(t + "\n").encode(),
                       capture_output=True, cwd=str(harness.parent))
    assert r.returncode == 0, r.stderr
    assert hajimi.decode(r.stdout.decode().strip()) == t
    c = hajimi.encode(t)
    r2 = subprocess.run([node, str(harness), "dec"], input=c.encode(),
                        capture_output=True, cwd=str(harness.parent))
    assert r2.returncode == 0, r2.stderr
    assert r2.stdout.decode() == t


# ---------------------------------------------------------------- mojibake

def test_mojibake_wenyan_roundtrip():
    t = "https://www.alipan.com/s/FmExample 访问码:8h2k 压缩包密码:哈基米"
    c = mojibake.encode(t, key="我的魔咒")
    assert "。" in c  # 文言文形态
    assert mojibake.decode(c, key="我的魔咒") == t


def test_mojibake_old_roundtrip():
    t = "链接: https://example.org 密码: old123"
    c = mojibake.encode(t, key="K", mode="old")
    assert mojibake.decode(c, key="K", mode="old") == t


# ---------------------------------------------------------------- nest / unest

def test_nest_two_layers(sample_dir, tmp_path):
    out = tmp_path / "pkg.7z"
    layers = [pack.LayerSpec("zip", password="innerPW"),
              pack.LayerSpec("7z", password="outerPW", header_enc=True)]
    mf = pack.pack([sample_dir], layers, out)
    assert out.exists() and out.stat().st_size > 0
    side = json.loads((out.parent / (out.name + ".nde.json")).read_text(encoding="utf-8"))
    assert [l["format"] for l in side["layers"]] == ["7z", "zip"]  # outer first
    res = pack.unest(out, tmp_path / "back", ["outerPW", "innerPW"])
    assert res[0].name == "my_resource"
    assert (res[0] / "data.bin").read_bytes() == (sample_dir / "data.bin").read_bytes()


def test_nest_raw_uncommon_formats(sample_dir, tmp_path):
    # inner lz4 (no pwd) -> outer 7z with password; disguise as .lz4
    src = sample_dir / "note.txt"
    layers = [pack.LayerSpec("lz4"), pack.LayerSpec("7z", password="pw1")]
    out = tmp_path / "video.lz4"
    pack.pack([src], layers, out, )
    mf = json.loads((out.parent / (out.name + ".nde.json")).read_text(encoding="utf-8"))
    res = pack.unest(out, tmp_path / "b2", ["pw1", None])
    assert res[0].read_text(encoding="utf-8") == src.read_text(encoding="utf-8")
    # sniff must NOT claim lz4 (it is really 7z) — that's the point of disguise
    assert formats.sniff(out) == "7z"


def test_nest_three_layer_tar_chain(sample_dir, tmp_path):
    layers = [pack.LayerSpec("tar.xz"), pack.LayerSpec("zip", password="z"),
              pack.LayerSpec("7z", password="s")]
    out = tmp_path / "tri.7z"
    pack.pack([sample_dir], layers, out)
    pack.unest(out, tmp_path / "b3", ["s", "z", None])
    got = tmp_path / "b3" / "my_resource" / "note.txt"
    assert got.read_text(encoding="utf-8").startswith("资源说明书")


def test_nest_wrong_password_fails(sample_dir, tmp_path):
    layers = [pack.LayerSpec("7z", password="right")]
    out = tmp_path / "x.7z"
    pack.pack([sample_dir], layers, out)
    with pytest.raises(Exception):
        pack.unest(out, tmp_path / "b4", ["wrong"])


# ---------------------------------------------------------------- split / join

def test_split_join_roundtrip(tmp_path):
    big = tmp_path / "big.bin"
    big.write_bytes(bytes((i * 37) % 256 for i in range(700_000)))
    man = splitmod.split(big, 250_000, tmp_path / "vol")
    assert man["part_count"] == 3
    parts = sorted((tmp_path / "vol").glob("*.[0-9][0-9][0-9]"))
    assert len(parts) == 3
    joined = splitmod.join(parts[0], tmp_path / "re.bin")
    assert joined.read_bytes() == big.read_bytes()


def test_split_corrupt_detected(tmp_path):
    f = tmp_path / "f.bin"
    f.write_bytes(b"payload" * 100_000)
    splitmod.split(f, 300_000, tmp_path / "v2")
    p2 = tmp_path / "v2" / "f.bin.002"
    p2.write_bytes(b"X" * p2.stat().st_size)
    with pytest.raises(RuntimeError, match="校验失败"):
        splitmod.join(tmp_path / "v2" / "f.bin.001", tmp_path / "out.bin")


# ---------------------------------------------------------------- merge / unwrap

def test_merge_fixed_zip_extractable(sample_dir, tmp_path, small_mp4):
    art = tmp_path / "payload.zip"
    pack.pack([sample_dir], [pack.LayerSpec("zip", password="mPW")], art)
    merged = tmp_path / "cover.mp4"
    rep = merge.concat_merge([small_mp4, art], merged)
    assert rep["mode"] == "concat-fixed-zip"
    # any zip tool can open the merged file directly
    res = merge.unwrap(merged, tmp_path / "uw", password="mPW")
    assert any(r.name == "my_resource" for r in res)
    # head video bytes intact => still playable
    head = merged.read_bytes()[:small_mp4.stat().st_size]
    assert head == small_mp4.read_bytes()


def test_merge_raw_and_unwrap_nested(sample_dir, tmp_path, small_mp4):
    art = tmp_path / "p2.7z"
    pack.pack([sample_dir], [pack.LayerSpec("7z", password="q")], art)
    merged = tmp_path / "cover2.mp4"
    rep = merge.concat_merge([small_mp4, art], merged, fix_zip=False)
    assert rep["mode"] == "concat-raw"
    res = merge.unwrap(merged, tmp_path / "uw2", password="q")
    assert any(r.name == "my_resource" for r in res)


def test_concat_zip_fix_makes_strict_valid(sample_dir, tmp_path, small_mp4):
    """修偏移后的 视频+zip 合并体是标准合法 zip(SFX 同款布局)：严格 zipfile 也能
    直接打开；未修的纯 copy/b 拼接则只能靠扫描容忍(实测 zipfile 会报错)。"""
    art = tmp_path / "raw.zip"
    pack.pack([sample_dir], [pack.LayerSpec("zip", password="rPW")], art)
    import struct, pyzipper
    fixed = tmp_path / "fixed.mp4"
    merge.concat_merge([small_mp4, art], fixed, fix_zip=True)
    data = fixed.read_bytes()
    eocd = data.rfind(b"PK\x05\x06")
    cd_off = struct.unpack_from("<I", data, eocd + 16)[0]
    first_lho = struct.unpack_from("<I", data, cd_off + 42)[0]
    assert first_lho == small_mp4.stat().st_size  # 偏移确实被补丁到视频之后
    with pyzipper.AESZipFile(fixed) as zf:
        assert "my_resource/note.txt" in zf.namelist()
        assert zf.read("my_resource/note.txt", pwd=b"rPW").startswith("资源说明书".encode())
    raw = tmp_path / "raw.mp4"
    merge.concat_merge([small_mp4, art], raw, fix_zip=False)
    # 纯拼接体：靠扫描容忍类工具/我们的 unwrap 恢复
    res = merge.unwrap(raw, tmp_path / "uw4", password="rPW")
    assert any(r.name == "my_resource" for r in res)


def test_unwrap_disguised_zip(tmp_path, sample_dir):
    art = tmp_path / "dis.mp4"  # pure zip named as mp4 (改后缀套路的还原)
    layers = [pack.LayerSpec("zip", password="dPW")]
    pack.pack([sample_dir], layers, art)
    res = merge.unwrap(art, tmp_path / "uw3", password="dPW")
    assert any(r.name == "my_resource" for r in res)


def test_unwrap_chain_peel_full_depth(sample_dir, tmp_path, small_mp4):
    """接收方视角极限用例：伪装mp4 + 视频合并 + lz4/zip/7z 三层，
    仅凭魔数嗅探+密码链一路剥到原始文件（tar 自动垫层也在链上）。"""
    layers = [pack.LayerSpec("lz4"), pack.LayerSpec("zip", password="cZ"),
              pack.LayerSpec("7z", password="c7", header_enc=True)]
    art = tmp_path / "pkg.mp4"
    pack.pack([sample_dir], layers, art)
    merged = tmp_path / "cover.mp4"
    merge.concat_merge([small_mp4, art], merged)
    res = merge.unwrap(merged, tmp_path / "chain", chain=["c7", "cZ", None])
    names = [r.name for r in res]
    assert "my_resource" in names
    got = next(r for r in res if r.name == "my_resource")
    assert (got / "data.bin").read_bytes() == (sample_dir / "data.bin").read_bytes()


# ---------------------------------------------------------------- cli smoke

def test_cli_full_chain(tmp_path, sample_dir):
    out = tmp_path / "cli.7z"
    cli("nest", sample_dir, "-L", "zip,lzma,7z", "-P=-,-,cliPW",
        "-o", out, "--disguise", ".mp4")
    assert out.with_suffix(".mp4").exists() or out.exists()
    artifact = out if out.exists() else out.with_suffix(".mp4")
    cli("split", artifact, "-s", "100B", "-o", tmp_path / "cv")
    part = next((tmp_path / "cv").glob("*.001"))
    cli("join", part, "-o", tmp_path / "re.mp4")
    r = cli("code", "encode", "-S", "beast,hajimi", "-T", "https://x.y/z 密码:1", "-o", tmp_path / "c.txt")
    txt = (tmp_path / "c.txt").read_text(encoding="utf-8").strip()
    r2 = cli("code", "decode", "-S", "beast,hajimi", "-F", tmp_path / "c.txt")
    assert "https://x.y/z 密码:1" in r2.stdout.decode("utf-8")


@pytest.mark.parametrize("damage", ["none", "corrupt", "missing", "swapped"])
def test_recipient_join_with_public_checksums(tmp_path, damage):
    """Recipients receive the published .sha256, not the private JSON sidecar."""
    from nde.workflows import write_checksums
    src = tmp_path / "中文 空格.bin"
    src.write_bytes(__import__('os').urandom(300))
    volumes = tmp_path / "download"
    splitmod.split(src, 100, volumes)
    parts = sorted(volumes.glob("*.00?"))
    write_checksums(parts, volumes / "checksums.sha256")
    (volumes / (src.name + splitmod.SIDECAR_EXT)).unlink()
    if damage == "corrupt":
        parts[1].write_bytes(b"X" * 100)
    elif damage == "missing":
        parts[-1].unlink()
    elif damage == "swapped":
        a, b = parts[0].read_bytes(), parts[1].read_bytes()
        parts[0].write_bytes(b)
        parts[1].write_bytes(a)
    out = tmp_path / "restored.bin"
    result = cli("join", parts[0], "-o", out, expect_ok=False)
    if damage == "none":
        assert result.returncode == 0
        assert out.read_bytes() == src.read_bytes()
        assert "通过校验" in result.stdout.decode("utf-8")
    else:
        assert result.returncode != 0
        assert ("缺少分卷" if damage == "missing" else "校验失败") in result.stderr.decode("utf-8")
        assert not out.exists()


@pytest.mark.parametrize("no_verify", [False, True])
def test_join_does_not_claim_unperformed_verification(tmp_path, no_verify):
    src = tmp_path / "source.bin"
    src.write_bytes(b"abc" * 100)
    splitmod.split(src, 100, tmp_path / "vol")
    (tmp_path / "vol" / (src.name + splitmod.SIDECAR_EXT)).unlink()
    r = cli("join", tmp_path / "vol" / "source.bin.001", "-o", tmp_path / "out.bin",
            *(["--no-verify"] if no_verify else []))
    assert "未校验" in r.stdout.decode("utf-8")
    assert "通过校验" not in r.stdout.decode("utf-8")
