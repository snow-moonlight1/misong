"""Portable keys contain synthetic secrets only; no private account data."""
import copy
import json

import pytest

from misong import pack, restore_key
from misong.layers import LayerSpec as L


@pytest.fixture
def exported(tmp_path):
    source = tmp_path / "中文😀.txt"
    source.write_bytes(b"synthetic private content" * 20)
    artifact = tmp_path / "bundle.7z"
    manifest = pack.pack([source], [L("7z", "test-only-密码-381", True)], artifact, export_key=True)
    return artifact, manifest, restore_key.sidecar(artifact)


def test_envelope_roundtrip_and_plaintext_absence(exported):
    artifact, mf, key = exported
    raw = key.read_bytes()
    payload = restore_key.read(key)
    assert payload["passwords"] == ["test-only-密码-381"]
    assert payload["manifest"]["artifacts"] == mf["artifacts"]
    assert b'"passwords"' not in raw and "test-only-密码-381".encode() not in raw
    assert "test-only-密码-381" not in artifact.with_name(artifact.name + ".misong.json").read_text(encoding="utf-8")
    assert not list(key.parent.glob("*.tmp"))


@pytest.mark.parametrize("offset", [0, len(restore_key.MAGIC), len(restore_key.MAGIC) + 32, -1])
def test_corrupted_envelope_rejected(exported, offset):
    _, _, key = exported
    raw = bytearray(key.read_bytes())
    raw[offset] ^= 1
    key.write_bytes(raw)
    with pytest.raises(ValueError, match="损坏|支持"):
        restore_key.read(key)


def test_export_is_explicit_and_never_replaces_key(exported, tmp_path):
    artifact, mf, key = exported
    raw = key.read_bytes()
    with pytest.raises((ValueError, FileExistsError)):
        pack.pack([tmp_path / "中文😀.txt"], [L("zip", "replacement")], artifact, export_key=True)
    assert key.read_bytes() == raw
    another = tmp_path / "no-key.zip"
    pack.pack([tmp_path / "中文😀.txt"], [L("zip", "not-persisted")], another)
    assert not restore_key.sidecar(another).exists()


@pytest.mark.parametrize("name", ["../escaped", "C:\\outside.txt", "/outside.txt", "a/b", "a\\b", "NUL", "file:stream", "..", "trailing."])
def test_untrusted_key_names_rejected(exported, name):
    _, _, key = exported
    payload = copy.deepcopy(restore_key.read(key))
    payload["manifest"]["layers"][0]["input_names"] = [name]
    with pytest.raises(ValueError, match="不安全"):
        restore_key.validate(payload)


def test_export_strips_host_paths(exported, tmp_path):
    _, mf, _ = exported
    mf["layers"][0]["video"] = "Z:/private-user/original-cover.mp4"
    mf["layers"][0]["private_extra"] = "local-only"
    key = tmp_path / "clean.mskey"
    restore_key.write(key, mf, ["test-only-密码-381"])
    text = json.dumps(restore_key.read(key))
    assert "private-user" not in text and "local-only" not in text


def test_oversized_and_unrecognized_keys_rejected(tmp_path):
    path = tmp_path / "bad.mskey"
    for data in (b"{}", b"", b"x" * (restore_key.MAX_SIZE + 1)):
        path.write_bytes(data)
        with pytest.raises(ValueError):
            restore_key.read(path)
