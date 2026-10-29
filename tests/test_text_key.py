"""B contract-double tests, independent of A/C and of real accounts/sites."""
import copy
import json
import sys
import threading
import types
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from misong import restore_key, text_key
from misong.text_contracts import (
    ErrorCode, LayerReceipt, OperationContext, PipelineResult, RuntimeSecrets,
    TextOperationError, text_digest,
)


class ContractRecipe:
    """Minimal strict A contract double; no production encoders are exercised."""

    def __init__(self, data):
        self.data = copy.deepcopy(data)

    @classmethod
    def from_dict(cls, data):
        # B checks structural allowlists; A owns per-algorithm parameter rules.
        for layer in data["layers"]:
            params = layer["params"]
            if layer["scheme"] == "mojibake":
                if set(params) - {"mode"} or params.get("mode", "wenyan") not in ("old", "wenyan"):
                    raise TextOperationError(ErrorCode.INVALID_RECIPE)
            elif layer["scheme"] == "beast":
                if set(params) - {"dialect", "chars"}:
                    raise TextOperationError(ErrorCode.INVALID_RECIPE)
            elif params or layer["secret_slot"] is not None:
                raise TextOperationError(ErrorCode.INVALID_RECIPE)
        if data["carrier"]["format_id"] == "text" and data["carrier"]["secret_slot"] is not None:
            raise TextOperationError(ErrorCode.INVALID_RECIPE)
        return cls(data)

    def to_dict(self):
        return copy.deepcopy(self.data)


@pytest.fixture
def recipe_double(monkeypatch):
    module = types.ModuleType("misong.text_layers")
    module.DeliveryRecipe = ContractRecipe
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return ContractRecipe


def recipe_data(*, video=False, layers=2):
    return {
        "version": 1, "id": "synthetic", "name": "合成方案",
        "layers": [
            {"id": f"l{i}", "scheme": "mojibake", "version": 1,
             "params": {"mode": "old"}, "secret_slot": f"synthetic/l{i}"}
            for i in range(layers)
        ],
        "carrier": {"format_id": "framewords" if video else "text", "version": 1,
                    "mode": "standard" if video else "plain", "params": {},
                    "secret_slot": "synthetic/video" if video else None},
    }


def synthetic_result(original="  合成😀\r\ne\u0301\t", layers=2):
    text, receipts = original, []
    for i in range(layers):
        output = f"fake-{i}[{text}]"
        receipts.append(LayerReceipt(f"l{i}", text_digest(text), text_digest(output),
                                     len(output), len(output.encode("utf-8"))))
        text = output
    return PipelineResult(text, tuple(receipts))


@pytest.fixture
def case(recipe_double):
    recipe = recipe_double(recipe_data(video=True))
    result = synthetic_result()
    values = {"synthetic/l0": "test-only-inner-0-秘密", "synthetic/l1": "test-only-inner-1",
              "synthetic/video": "test-only-outer", "unrelated": "must-not-export"}
    context = OperationContext(RuntimeSecrets(values))
    return recipe, result, context


def envelope(plain):
    key, nonce = b"k" * 32, b"n" * 12
    header = text_key.MAGIC + key + nonce
    return header + AESGCM(key).encrypt(nonce, plain, header)


def test_explicit_export_roundtrip_and_snapshot(case, tmp_path):
    recipe, result, context = case
    payload = text_key.build_payload(recipe, result, context)
    assert list(tmp_path.iterdir()) == []  # building never exports
    assert payload["secrets"] == {slot: context.secrets.require(slot)
                                  for slot in ("synthetic/l0", "synthetic/l1", "synthetic/video")}
    public = json.dumps(recipe.to_dict())
    assert "test-only" not in public
    key = text_key.write(tmp_path / "synthetic.tkey", payload)
    assert text_key.read(key) == payload
    raw = key.read_bytes()
    assert raw.startswith(b"MISONGTKEY\x00\x01") and len(text_key.MAGIC) == 12
    assert b'"secrets"' not in raw and b"test-only" not in raw
    assert "合成😀" not in json.dumps(payload, ensure_ascii=False)
    assert "fake-0[" not in json.dumps(payload)
    payload["recipe"]["layers"][0]["params"]["mode"] = "wenyan"
    assert recipe.to_dict()["layers"][0]["params"]["mode"] == "old"
    assert text_key.read(key)["recipe"]["layers"][0]["params"]["mode"] == "old"


@pytest.mark.parametrize("original", ["", "\n\r\n  ", "中文😀e\u0301"])
def test_zero_layers(recipe_double, tmp_path, original):
    payload = text_key.build_payload(recipe_double(recipe_data(layers=0)),
                                     synthetic_result(original, 0), OperationContext())
    assert payload["original_sha256"] == payload["payload_sha256"] == text_digest(original)
    assert payload["receipts"] == [] and payload["secrets"] == {}
    assert text_key.read(text_key.write(tmp_path / "plain", payload)) == payload


def test_refuses_overwrite_and_destination_symlink(case, tmp_path):
    payload = text_key.build_payload(*case)
    path = text_key.write(tmp_path / "key.tkey", payload)
    before = path.read_bytes()
    with pytest.raises(TextOperationError) as error:
        text_key.write(path, payload)
    assert error.value.code == ErrorCode.IO and path.read_bytes() == before
    link = tmp_path / "link.tkey"
    try:
        link.symlink_to(path)
    except OSError:
        return  # Windows may not grant symlink creation to this process.
    with pytest.raises(TextOperationError):
        text_key.write(link, payload)
    assert link.is_symlink() and path.read_bytes() == before


@pytest.mark.parametrize("offset", [0, 11, 12, 44, -1])
def test_corruption_rejected(case, tmp_path, offset):
    path = text_key.write(tmp_path / "key", text_key.build_payload(*case))
    raw = bytearray(path.read_bytes())
    raw[offset] ^= 1
    path.write_bytes(raw)
    with pytest.raises(TextOperationError) as error:
        text_key.read(path)
    assert error.value.code == ErrorCode.INTEGRITY


@pytest.mark.parametrize("size", [0, 1, 12, 55, 71, text_key.MAX_SIZE + 1])
def test_truncated_oversized_wrong_magic(tmp_path, size):
    path = tmp_path / "bad"
    path.write_bytes(b"x" * size)
    with pytest.raises(TextOperationError):
        text_key.read(path)


def test_mskey_discrimination_both_directions(case, tmp_path):
    path = text_key.write(tmp_path / "text.mskey", text_key.build_payload(*case))
    with pytest.raises(ValueError):
        restore_key.read(path)
    # Build an actual legacy-format key, without changing its production module.
    manifest = {"version": 2, "artifact": "demo.zip", "artifacts": [
        {"name": "demo.zip", "size": 0, "sha256": "0" * 64}], "layers": [
        {"type": "archive", "format": "zip", "password": True, "input_names": ["demo"]}]}
    old = restore_key.write(tmp_path / "file.tkey", manifest, ["synthetic-password"])
    assert restore_key.read(old)["passwords"] == ["synthetic-password"]
    with pytest.raises(TextOperationError):
        text_key.read(old)


def test_legacy_mskey_v1_envelope_fixture_remains_readable(tmp_path):
    # Frozen legacy layout, constructed independently of restore_key.write.
    # This file contains synthetic metadata only and no archive extraction.
    manifest = {"version": 2, "artifact": "legacy.zip", "artifacts": [
        {"name": "legacy.zip", "size": 0, "sha256": "0" * 64}], "layers": [
        {"type": "archive", "format": "zip", "password": True, "input_names": ["legacy"]}]}
    payload = {"version": 1, "manifest": manifest, "passwords": ["synthetic-legacy-only"]}
    key, nonce = bytes(range(32)), bytes(range(12))
    header = b"MISONGKEY\x00\x01" + key + nonce
    path = tmp_path / "legacy.mskey"
    path.write_bytes(header + AESGCM(key).encrypt(nonce, json.dumps(payload).encode(), header))
    assert restore_key.read(path) == payload


def mutations():
    return [
        lambda p: p.update(extra="forbidden"),
        lambda p: p.update(type="misong-file-key"),
        lambda p: p.update(version=True),
        lambda p: p.update(version=2),
        lambda p: p.update(original_sha256="A" * 64),
        lambda p: p.update(payload_sha256="1" * 64),
        lambda p: p["secrets"].update(extra="not referenced"),
        lambda p: p["secrets"].pop("synthetic/l0"),
        lambda p: p["secrets"].update({"synthetic/l0": 1}),
        lambda p: p["recipe"].update(path="C:/private/video.mp4"),
        lambda p: p["recipe"].update(version=True),
        lambda p: p["recipe"]["layers"].extend(p["recipe"]["layers"] * 17),
        lambda p: p["recipe"]["layers"][0].update(scheme="trunc"),
        lambda p: p["recipe"]["layers"][0].update(scheme="execute"),
        lambda p: p["recipe"]["layers"][0].update(version=True),
        lambda p: p["recipe"]["layers"][1].update(id="l0"),
        lambda p: p["recipe"]["layers"][1].update(secret_slot="synthetic/l0"),
        lambda p: p["recipe"]["carrier"].update(secret_slot="synthetic/l0"),
        lambda p: p["recipe"]["layers"][0]["params"].update(password="forbidden"),
        lambda p: p["recipe"]["layers"][0]["params"].update(mode="unknown"),
        lambda p: p["recipe"]["carrier"].update(format_id="unknown"),
        lambda p: p["recipe"]["carrier"]["params"].update(selector="forbidden"),
        lambda p: p["receipts"].reverse(),
        lambda p: p["receipts"].pop(),
        lambda p: p["receipts"][0].update(extra="forbidden"),
        lambda p: p["receipts"][0].update(input_sha256="1" * 64),
        lambda p: p["receipts"][1].update(input_sha256="2" * 64),
        lambda p: p["receipts"][0].update(characters=True),
        lambda p: p["receipts"][0].update(utf8_bytes=-1),
        lambda p: p["receipts"][0].update(utf8_bytes=text_key.MAX_TEXT_BYTES + 1),
        lambda p: p["receipts"][0].update(characters=1, utf8_bytes=5),
    ]


@pytest.mark.parametrize("mutate", mutations())
def test_malicious_authenticated_structure_rejected(case, tmp_path, mutate):
    payload = text_key.build_payload(*case)
    mutate(payload)
    with pytest.raises(TextOperationError):
        text_key.write(tmp_path / "must-not-exist", payload)
    assert not (tmp_path / "must-not-exist").exists()
    path = tmp_path / "hostile"
    path.write_bytes(envelope(json.dumps(payload).encode()))
    with pytest.raises(TextOperationError):
        text_key.read(path)


@pytest.mark.parametrize("plain", [b'{"version":1,"version":1}', b'{', b'[]', b'null',
                                    b'"\xff"', b'[' * 2000 + b']' * 2000])
def test_bad_json_and_duplicate_members(tmp_path, plain):
    path = tmp_path / "bad-json"
    path.write_bytes(envelope(plain))
    with pytest.raises(TextOperationError) as error:
        text_key.read(path)
    assert error.value.__context__ is None


def test_size_boundary_and_cycle(case, tmp_path):
    payload = text_key.build_payload(*case)
    payload["secrets"]["synthetic/l0"] = "x" * text_key.MAX_SIZE
    with pytest.raises(TextOperationError) as error:
        text_key.write(tmp_path / "too-big", payload)
    assert error.value.code == ErrorCode.CAPACITY
    payload["recipe"]["carrier"]["params"]["cycle"] = payload
    with pytest.raises(TextOperationError):
        text_key.validate(payload)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(receipts=tuple(p["receipts"])),
    lambda p: p["secrets"].update({1: "bad"}),
    lambda p: p["receipts"][0].update(characters=1.0),
    lambda p: p["recipe"]["layers"][0]["params"].update(mode=float("nan")),
])
def test_in_memory_non_json_types_not_coerced(case, mutate):
    payload = text_key.build_payload(*case)
    mutate(payload)
    with pytest.raises(TextOperationError):
        text_key.validate(payload)


def test_max_layers_accepted(recipe_double, tmp_path):
    recipe = recipe_double(recipe_data(layers=text_key.MAX_LAYERS))
    context = OperationContext(RuntimeSecrets({f"synthetic/l{i}": "test-only"
                                              for i in range(text_key.MAX_LAYERS)}))
    result = synthetic_result(layers=text_key.MAX_LAYERS)
    payload = text_key.build_payload(recipe, result, context)
    assert len(text_key.read(text_key.write(tmp_path / "32.tkey", payload))["receipts"]) == 32


def test_file_size_limit_is_inclusive(recipe_double, tmp_path):
    recipe = recipe_double(recipe_data(video=True, layers=0))
    context = OperationContext(RuntimeSecrets({"synthetic/video": ""}))
    payload = text_key.build_payload(recipe, synthetic_result(layers=0), context)
    base_size = len(text_key._json_bytes(payload)) + len(text_key.MAGIC) + 32 + 12 + 16
    payload["secrets"]["synthetic/video"] = "x" * (text_key.MAX_SIZE - base_size)
    path = text_key.write(tmp_path / "limit.tkey", payload)
    assert path.stat().st_size == text_key.MAX_SIZE
    assert text_key.read(path) == payload
    payload["secrets"]["synthetic/video"] += "x"
    with pytest.raises(TextOperationError) as error:
        text_key.write(tmp_path / "too-big.tkey", payload)
    assert error.value.code == ErrorCode.CAPACITY


def test_parser_private_error_is_discarded(case, monkeypatch):
    payload = text_key.build_payload(*case)

    def fail(data):
        raise ValueError("synthetic private text/password")

    monkeypatch.setattr(ContractRecipe, "from_dict", fail)
    with pytest.raises(TextOperationError) as error:
        text_key.validate(payload)
    assert error.value.__context__ is None
    assert "private" not in str(error.value)


@pytest.mark.parametrize("path", [None, 123, "invalid\x00path"])
def test_invalid_io_paths_have_safe_errors(case, path):
    with pytest.raises(TextOperationError) as error:
        text_key.write(path, text_key.build_payload(*case))
    assert error.value.code == ErrorCode.IO and error.value.__context__ is None
    with pytest.raises(TextOperationError) as error:
        text_key.read(path)
    assert error.value.code == ErrorCode.IO and error.value.__context__ is None


def test_build_rejects_missing_secret_mismatch_and_cancel(case):
    recipe, result, context = case
    with pytest.raises(TextOperationError) as error:
        text_key.build_payload(recipe, result, OperationContext())
    assert error.value.code == ErrorCode.MISSING_SECRET
    with pytest.raises(TextOperationError):
        text_key.build_payload(recipe, PipelineResult(result.text + "!", result.receipts), context)
    bad = list(result.receipts)
    last = bad[-1]
    bad[-1] = LayerReceipt(last.layer_id, last.input_sha256, last.output_sha256,
                          last.characters - 1, last.utf8_bytes)
    with pytest.raises(TextOperationError):
        text_key.build_payload(recipe, PipelineResult(result.text, tuple(bad)), context)
    stop = threading.Event()
    stop.set()
    with pytest.raises(TextOperationError) as error:
        text_key.build_payload(recipe, result, OperationContext(context.secrets, stop))
    assert error.value.code == ErrorCode.CANCELLED


@pytest.mark.parametrize("fail_at", ["write", "short", "flush", "close"])
def test_failed_export_removes_only_new_file(case, tmp_path, monkeypatch, fail_at):
    payload = text_key.build_payload(*case)
    original_open = Path.open

    class FailingFile:
        def __init__(self, fh):
            self.fh = fh

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.fh.close()
            if fail_at == "close":
                raise OSError("synthetic failure")

        def write(self, data):
            self.fh.write(data[:10] if fail_at in ("write", "short") else data)
            if fail_at == "write":
                raise OSError("synthetic failure")
            return 10 if fail_at == "short" else len(data)

        def flush(self):
            if fail_at == "flush":
                raise OSError("synthetic failure")

    def open_double(path, mode="r", *args, **kwargs):
        fh = original_open(path, mode, *args, **kwargs)
        return FailingFile(fh) if mode == "xb" else fh

    monkeypatch.setattr(Path, "open", open_double)
    with pytest.raises(TextOperationError) as error:
        text_key.write(tmp_path / "failed.tkey", payload)
    assert error.value.code == ErrorCode.IO and error.value.__context__ is None
    assert list(tmp_path.iterdir()) == []
