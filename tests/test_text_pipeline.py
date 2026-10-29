"""A package: synthetic, local-only recipes, text chains and legacy outputs."""
import json
import secrets
import shutil
import subprocess
import threading
import time
import traceback
from dataclasses import FrozenInstanceError, asdict, replace

import pytest

from misong import text_pipeline as pipeline
from misong.encoders import beast, hajimi, mojibake, plain
from misong.sharing import ShareInfo, encode_copy, recipes_from_schemes, write_copy
from misong.text_contracts import (
    ErrorCode, LayerReceipt, OperationContext, RuntimeSecrets, Stage,
    TextOperationError, text_digest,
)
from misong.text_layers import (
    MAX_RECIPES, MAX_TEXT_BYTES, MAX_TEXT_LAYERS, TEXT_SCHEMES,
    CarrierSpec, DeliveryRecipe, TextLayer, validate_recipes,
)

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node unavailable")
SAMPLES = ("https://example.invalid/s/demo?pwd=1234", "中文😀𠮷", " \t文案\r\n\n ", "e\u0301 é")


def recipe(*schemes, carrier=None):
    return DeliveryRecipe(1, "demo", "合成方案",
                          tuple(TextLayer(f"layer-{i}", scheme) for i, scheme in enumerate(schemes)),
                          carrier or CarrierSpec())


def assert_code(code, operation):
    with pytest.raises(TextOperationError) as error:
        operation()
    assert error.value.code == code
    assert str(error.value) == code.value
    return error.value


def test_public_roundtrip_is_immutable_and_detached():
    params = {"dialect": "pojie", "chars": ["点", "赞", "投", "币"]}
    layer = TextLayer("inner", "beast", params=params)
    layers = [layer, TextLayer("outer", "mojibake", params={"mode": "old"}, secret_slot="demo/outer")]
    r = DeliveryRecipe(1, "demo", "视频文案", layers,
                       CarrierSpec("framewords", mode="standard", secret_slot="demo/video"))
    params["chars"][0] = "新"
    layers.clear()
    assert isinstance(r.layers, tuple) and len(r.layers) == 2
    assert r.layers[0].params["chars"] == ("点", "赞", "投", "币")
    public = r.to_dict()
    assert DeliveryRecipe.from_dict(json.loads(json.dumps(public))) == r
    public["layers"][0]["params"]["chars"][0] = "变"
    assert r.to_dict()["layers"][0]["params"]["chars"][0] == "点"
    with pytest.raises(TypeError):
        layer.params["chars"] = "其他字符"
    with pytest.raises(FrozenInstanceError):
        layer.scheme = "reverse"


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(password="forbidden"),
    lambda d: d.update(export_key=True),
    lambda d: d.update(version=True),
    lambda d: d.update(version=2),
    lambda d: d.pop("name"),
    lambda d: d.update(layers="beast"),
    lambda d: d["layers"][0].update(scheme="trunc"),
    lambda d: d["layers"][0].update(scheme="unknown"),
    lambda d: d["layers"][0].update(scheme="framewords"),
    lambda d: d["layers"][0].update(version=0),
    lambda d: d["layers"][0].update(key="forbidden"),
    lambda d: d["layers"][0]["params"].update(password="forbidden"),
    lambda d: d["carrier"].update(backend_id="framewords_web"),
    lambda d: d["carrier"].update(mode="audio"),
    lambda d: d["carrier"]["params"].update(source="C:/private/video.mp4"),
    lambda d: d["carrier"].update(secret_slot="demo/text"),
])
def test_public_recipe_rejects_unknown_fields_and_versions(mutate):
    data = recipe("beast").to_dict()
    mutate(data)
    assert_code(ErrorCode.INVALID_RECIPE, lambda: DeliveryRecipe.from_dict(data))


@pytest.mark.parametrize("params", [
    {"dialect": "invented"}, {"dialect": []}, {"chars": "aaaa"},
    {"chars": ["a", "b", "c", "de"]}, {"chars": "a bc"},
    {"chars": "a\ud800bc"}, {"mode": "old"},
])
def test_beast_params_are_reversible_and_use_existing_dialects(params):
    assert_code(ErrorCode.INVALID_RECIPE, lambda: TextLayer("a", "beast", params=params))


def test_cycle_and_invalid_layer_placement_rejected_without_recursion():
    data = recipe("beast").to_dict()
    data["layers"][0]["params"]["chars"] = data
    assert_code(ErrorCode.INVALID_RECIPE, lambda: DeliveryRecipe.from_dict(data))
    data["layers"] = [data]
    assert_code(ErrorCode.INVALID_RECIPE, lambda: DeliveryRecipe.from_dict(data))
    assert_code(ErrorCode.INVALID_RECIPE, lambda: DeliveryRecipe(1, "demo", "x", (CarrierSpec(),)))


def test_layer_recipe_and_slot_limits():
    layers = tuple(TextLayer(f"l{i}", "reverse") for i in range(MAX_TEXT_LAYERS))
    assert len(DeliveryRecipe(1, "max", "最大层数", layers).layers) == MAX_TEXT_LAYERS
    assert_code(ErrorCode.CAPACITY, lambda: DeliveryRecipe(1, "max", "x", layers + (TextLayer("extra", "reverse"),)))
    recipes = [DeliveryRecipe(1, f"r{i}", "x") for i in range(MAX_RECIPES)]
    assert len(validate_recipes(recipes)) == MAX_RECIPES
    assert_code(ErrorCode.CAPACITY, lambda: validate_recipes(recipes + [DeliveryRecipe(1, "extra", "x")]))
    assert_code(ErrorCode.INVALID_RECIPE, lambda: validate_recipes([recipe(), recipe()]))
    assert_code(ErrorCode.INVALID_RECIPE, lambda: DeliveryRecipe(1, "r", "x", (layers[0], layers[0])))
    keyed = TextLayer("m", "mojibake", secret_slot="shared")
    assert_code(ErrorCode.INVALID_RECIPE, lambda: DeliveryRecipe(1, "r", "x", (keyed,),
                CarrierSpec("framewords", mode="standard", secret_slot="shared")))
    assert_code(ErrorCode.INVALID_RECIPE, lambda: validate_recipes([
        DeliveryRecipe(1, "r1", "x", (keyed,)), DeliveryRecipe(1, "r2", "x", (keyed,))]))


def test_legacy_migration_is_parallel_stable_and_empty_stays_empty():
    migrated = recipes_from_schemes(["beast", "mojibake", "beast"])
    assert [tuple(layer.scheme for layer in r.layers) for r in migrated] == [("beast",), ("mojibake",)]
    assert migrated == recipes_from_schemes(["beast", "mojibake"])
    assert migrated[1].layers[0].secret_slot == "legacy-mojibake/text"
    assert recipes_from_schemes([]) == ()
    assert_code(ErrorCode.INVALID_RECIPE, lambda: recipes_from_schemes(["trunc"]))
    assert_code(ErrorCode.INVALID_RECIPE, lambda: recipes_from_schemes("beast"))


@pytest.mark.parametrize("text", (*SAMPLES, "", "\r\n\t "))
def test_zero_layers_preserve_exact_text_and_do_not_request_carrier_secrets(text):
    r = recipe(carrier=CarrierSpec("framewords", mode="standard", secret_slot="demo/video"))
    result = pipeline.encode_text(text, r, OperationContext())
    assert result.text == text and result.receipts == ()
    assert pipeline.decode_text(result.text, r, (), OperationContext()) == result


@pytest.mark.parametrize("scheme", [s for s in TEXT_SCHEMES if s != "mojibake"])
@pytest.mark.parametrize("text", SAMPLES)
def test_existing_encoders_roundtrip_exact_text(scheme, text):
    r = recipe(scheme)
    result = pipeline.encode_text(text, r, OperationContext())
    receipt, = result.receipts
    assert receipt.input_sha256 == text_digest(text)
    assert receipt.output_sha256 == text_digest(result.text)
    assert (receipt.characters, receipt.utf8_bytes) == (len(result.text), len(result.text.encode("utf-8")))
    restored = pipeline.decode_text(result.text, r, result.receipts, OperationContext())
    assert restored.text == text and restored.receipts is result.receipts
    assert pipeline.decode_text(result.text, r, (), OperationContext()).text == text


@pytest.mark.parametrize("dialect", ["web", "sdk", "pojie", "auto"])
@pytest.mark.parametrize("chars", ["点赞投币", "😀🧪𠮷🐈"])
def test_beast_custom_parameters(dialect, chars):
    r = DeliveryRecipe(1, "r", "x", (TextLayer("b", "beast", params={"chars": chars, "dialect": dialect}),))
    encoded = pipeline.encode_text(SAMPLES[2], r, OperationContext())
    assert pipeline.decode_text(encoded.text, r, encoded.receipts, OperationContext()).text == SAMPLES[2]


@needs_node
@pytest.mark.parametrize("mode", ["old", "wenyan"])
@pytest.mark.parametrize("schemes", [("beast", "mojibake"), ("mojibake", "base64"),
                                    ("mojibake", "base64", "mojibake"), ("mojibake", "mojibake")])
def test_serial_chains_and_separate_mojibake_keys(mode, schemes):
    secret_values = {}
    layers = []
    for index, scheme in enumerate(schemes):
        slot = f"demo/l{index}" if scheme == "mojibake" else None
        if slot:
            secret_values[slot] = secrets.token_hex(12)
        layers.append(TextLayer(f"l{index}", scheme, params={"mode": mode} if slot else {}, secret_slot=slot))
    r = DeliveryRecipe(1, "demo", "合成", tuple(layers))
    events = []
    context = OperationContext(secrets=RuntimeSecrets(secret_values), notify=events.append)
    text = " \t合成 https://example.invalid/s/demo 😀 e\u0301\r\n\n "
    if mode == "old" and schemes == ("mojibake", "mojibake"):
        # The pinned encoder itself replaces the inner old-mode markers.
        # A rejects this lossy output, rather than changing the wire format.
        assert_code(ErrorCode.INTEGRITY, lambda: pipeline.encode_text(text, r, context))
        return
    result = pipeline.encode_text(text, r, context)
    assert result.receipts[0].output_sha256 == result.receipts[1].input_sha256
    assert [v.layer_id for v in result.receipts] == [v.id for v in layers]
    assert pipeline.decode_text(result.text, r, result.receipts, context).text == text
    assert pipeline.decode_text(result.text, r, (), context).text == text
    public = json.dumps(r.to_dict())
    for value in secret_values.values():
        assert value not in public and value not in repr(context) and value not in repr(result)
        assert value not in repr(events)
    assert all(set(asdict(event)) == {"stage", "completed", "total"} for event in events)


@needs_node
@pytest.mark.parametrize("mode", ["old", "wenyan"])
def test_wrong_mojibake_password_never_returns_a_partial_result(mode):
    r = DeliveryRecipe(1, "r", "x", (TextLayer("m", "mojibake", params={"mode": mode}, secret_slot="r/m"),))
    good = OperationContext(secrets=RuntimeSecrets({"r/m": secrets.token_hex(12)}))
    result = pipeline.encode_text("synthetic text 中文😀", r, good)
    bad = OperationContext(secrets=RuntimeSecrets({"r/m": secrets.token_hex(12)}))
    assert_code(ErrorCode.INTEGRITY, lambda: pipeline.decode_text(result.text, r, result.receipts, bad))


def test_missing_later_secret_fails_before_any_encoding(monkeypatch):
    r = DeliveryRecipe(1, "r", "x", (TextLayer("b", "beast"), TextLayer("m", "mojibake", secret_slot="r/m")))
    monkeypatch.setattr(beast, "encode", lambda *a, **k: pytest.fail("partial encoding"))
    assert_code(ErrorCode.MISSING_SECRET, lambda: pipeline.encode_text("synthetic", r, OperationContext()))


def test_randomized_encoder_only_called_once_and_receipts_reused(monkeypatch):
    calls = []
    original = hajimi.encode
    def encode(text):
        calls.append(text_digest(text))
        return original(text)
    monkeypatch.setattr(hajimi, "encode", encode)
    r = recipe("hajimi", "base64")
    result = pipeline.encode_text("synthetic 😀", r, OperationContext())
    restored = pipeline.decode_text(result.text, r, result.receipts, OperationContext())
    assert restored.text == "synthetic 😀" and len(calls) == 1
    assert restored.receipts is result.receipts


@pytest.mark.parametrize("damage", ["payload", "order", "count", "input", "output", "stats", "bool", "chain", "extra"])
def test_receipt_tampering_rejected(damage):
    r = recipe("base64", "reverse")
    result = pipeline.encode_text("synthetic", r, OperationContext())
    receipts, text = result.receipts, result.text
    if damage == "payload":
        text += " "
    elif damage == "order":
        receipts = receipts[::-1]
    elif damage == "count":
        receipts = receipts[:1]
    elif damage == "input":
        receipts = (replace(receipts[0], input_sha256="0" * 64), receipts[1])
    elif damage == "output":
        receipts = (receipts[0], replace(receipts[1], output_sha256="0" * 64))
    elif damage == "stats":
        receipts = (receipts[0], replace(receipts[1], characters=1))
    elif damage == "bool":
        receipts = (receipts[0], replace(receipts[1], utf8_bytes=True))
    elif damage == "chain":
        receipts = (receipts[0], replace(receipts[1], input_sha256="0" * 64))
    else:
        receipts += (receipts[-1],)
    assert_code(ErrorCode.INTEGRITY, lambda: pipeline.decode_text(text, r, receipts, OperationContext()))


def test_outer_digest_checked_before_decoder_and_inner_digest_checked_after(monkeypatch):
    r = recipe("base64", "reverse")
    result = pipeline.encode_text("synthetic", r, OperationContext())
    def fail(*args):
        pytest.fail("unverified payload entered decoder")
    with monkeypatch.context() as patch:
        patch.setattr(plain, "decode", fail)
        assert_code(ErrorCode.INTEGRITY, lambda: pipeline.decode_text(result.text + " ", r, result.receipts, OperationContext()))
    original = plain.decode
    calls = []
    def changed(scheme, text):
        calls.append(scheme)
        return original(scheme, text) + "!"
    monkeypatch.setattr(plain, "decode", changed)
    assert_code(ErrorCode.INTEGRITY, lambda: pipeline.decode_text(result.text, r, result.receipts, OperationContext()))
    assert calls == ["reverse"]


def test_input_intermediate_and_restored_capacity_limits(monkeypatch):
    ctx = OperationContext()
    assert pipeline.encode_text("x" * MAX_TEXT_BYTES, recipe(), ctx).text == "x" * MAX_TEXT_BYTES
    for text in ("x" * (MAX_TEXT_BYTES + 1), "😀" * (MAX_TEXT_BYTES // 4 + 1)):
        assert_code(ErrorCode.CAPACITY, lambda: pipeline.encode_text(text, recipe(), ctx))
        assert_code(ErrorCode.CAPACITY, lambda: pipeline.decode_text(text, recipe(), (), ctx))
    # 3/4 MiB is exactly one MiB after base64, and may pass.
    result = pipeline.encode_text("x" * (MAX_TEXT_BYTES * 3 // 4), recipe("base64"), ctx)
    assert len(result.text) == MAX_TEXT_BYTES
    with monkeypatch.context() as patch:
        patch.setattr(plain, "encode", lambda *a: pytest.fail("known oversize expansion"))
        assert_code(ErrorCode.CAPACITY, lambda: pipeline.encode_text("x" * MAX_TEXT_BYTES, recipe("base64"), ctx))
    monkeypatch.setattr(hajimi, "encode", lambda text: "x" * (MAX_TEXT_BYTES + 1))
    assert_code(ErrorCode.CAPACITY, lambda: pipeline.encode_text("x", recipe("hajimi", "reverse"), ctx))
    monkeypatch.setattr(hajimi, "decode", lambda text: "x" * (MAX_TEXT_BYTES + 1))
    assert_code(ErrorCode.CAPACITY, lambda: pipeline.decode_text("x", recipe("hajimi"), (), ctx))


@pytest.mark.parametrize("decode", [False, True])
def test_cancel_before_between_layers_and_before_return(decode):
    signal = threading.Event()
    signal.set()
    ctx = OperationContext(cancel=signal)
    operation = (lambda r, c: pipeline.decode_text("synthetic", r, (), c)) if decode else (
        lambda r, c: pipeline.encode_text("synthetic", r, c))
    assert_code(ErrorCode.CANCELLED, lambda: operation(recipe(), ctx))
    signal.clear()
    events = []
    def notify(event):
        events.append(event)
        if event.stage in (Stage.TEXT_DECODE, Stage.TEXT_ENCODE) and event.completed == 1:
            signal.set()
    ctx = OperationContext(cancel=signal, notify=notify)
    assert_code(ErrorCode.CANCELLED, lambda: operation(recipe("reverse", "reverse"), ctx))
    assert max(event.completed for event in events) == 1
    signal.clear()
    assert_code(ErrorCode.CANCELLED, lambda: operation(recipe("reverse"), ctx))
    assert_code(ErrorCode.TIMEOUT, lambda: operation(recipe(), OperationContext(deadline=time.monotonic() - 1)))


def test_mojibake_process_cancel_kills_and_reaps_without_returning_text(monkeypatch):
    signal = threading.Event()
    class Process:
        returncode = None
        killed = False
        reaped = False
        def communicate(self, input=None, timeout=None):
            if timeout is not None:
                signal.set()
                raise subprocess.TimeoutExpired("redacted", timeout)
            self.reaped = True
            return b"", b""
        def poll(self):
            return self.returncode
        def kill(self):
            self.killed = True
            self.returncode = -1
    process = Process()
    monkeypatch.setattr(mojibake, "_ensure", lambda: None)
    monkeypatch.setattr(pipeline.subprocess, "Popen", lambda *a, **k: process)
    assert_code(ErrorCode.CANCELLED, lambda: pipeline.encode_text("synthetic", recipe("mojibake"), OperationContext(cancel=signal)))
    assert process.killed and process.reaped


def test_codec_errors_have_no_private_exception_chain(monkeypatch):
    private = secrets.token_hex(16)
    def fail(*args):
        raise RuntimeError(private)
    monkeypatch.setattr(hajimi, "decode", fail)
    error = assert_code(ErrorCode.INTEGRITY, lambda: pipeline.decode_text("synthetic", recipe("hajimi"), (), OperationContext()))
    assert error.__cause__ is None and error.__context__ is None
    assert private not in "".join(traceback.format_exception(error))
    def unavailable():
        raise mojibake.MojibakeUnavailable(private)
    monkeypatch.setattr(mojibake, "_ensure", unavailable)
    assert_code(ErrorCode.UNSUPPORTED, lambda: pipeline.encode_text("synthetic", recipe("mojibake"), OperationContext()))


@needs_node
def test_legacy_encode_copy_and_migration_keep_independent_results():
    text = SAMPLES[1]
    key = secrets.token_hex(12)
    outputs = encode_copy(text, ("beast", "mojibake", "base64"), key=key)
    assert list(outputs) == ["beast", "mojibake", "base64"]
    assert beast.decode(outputs["beast"]) == text
    assert mojibake.decode(outputs["mojibake"], key=key) == text
    assert plain.decode("base64", outputs["base64"]) == text
    for r in recipes_from_schemes(["beast", "mojibake", "base64"]):
        values = {r.layers[0].secret_slot: key} if r.layers[0].secret_slot else {}
        context = OperationContext(secrets=RuntimeSecrets(values))
        generated = pipeline.encode_text(text, r, context)
        assert pipeline.decode_text(generated.text, r, generated.receipts, context).text == text


def test_legacy_write_copy_files_override_empty_and_trunc_semantics(tmp_path):
    share = ShareInfo("quark", "https://example.invalid/s/demo", "1234")
    outputs = write_copy(tmp_path / "copy", share, ["beast", "reverse"], text="synthetic\n")
    for scheme, cipher in outputs.items():
        assert (tmp_path / "copy" / f"{scheme}.txt").read_text(encoding="utf-8") == cipher + "\n"
    assert (tmp_path / "copy" / "share-plain.txt").read_text(encoding="utf-8") == "synthetic\n\n"
    assert write_copy(tmp_path / "empty", share, []) == {}
    assert (tmp_path / "empty" / "share-plain.txt").read_text(encoding="utf-8") == share.text() + "\n"
    assert encode_copy("synthetic", []) == {}
    # The legacy lossy option remains callable; only the new recipe rejects it.
    text = "https://example.invalid/s/long-enough-link"
    assert encode_copy(text, ["trunc"]) == {"trunc": plain.encode("trunc", text)}
