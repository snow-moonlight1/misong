"""B restore tests with A/C doubles; these are not real integration evidence."""
import asyncio
import shutil
import sys
import threading
import time
import types
from dataclasses import replace

import pytest

from misong import text_key, text_restore
from misong.carriers import CarrierCapabilities, DecodedText
from misong.text_contracts import (
    ErrorCode, OperationContext, PipelineResult, RuntimeSecrets, Stage,
    TextOperationError, text_digest,
)
from test_text_key import (  # shared synthetic fixtures, no dependency on A/C files
    case, recipe_double, recipe_data, synthetic_result,
)


@pytest.fixture
def pipeline_double(monkeypatch):
    seen = []

    def decode(text, recipe, receipts, context):
        seen.append((text, recipe, receipts, context))
        for index in reversed(range(len(recipe.data["layers"]))):
            context.check()
            layer = recipe.data["layers"][index]
            if layer["secret_slot"]:
                context.secrets.require(layer["secret_slot"])
            if receipts and text_digest(text) != receipts[index].output_sha256:
                raise TextOperationError(ErrorCode.INTEGRITY)
            prefix = f"fake-{index}["
            if not text.startswith(prefix) or not text.endswith("]"):
                raise TextOperationError(ErrorCode.INTEGRITY)
            text = text[len(prefix):-1]
            if receipts and text_digest(text) != receipts[index].input_sha256:
                raise TextOperationError(ErrorCode.INTEGRITY)
        return PipelineResult(text, receipts)

    module = types.ModuleType("misong.text_pipeline")
    module.decode_text = decode
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return module, seen


@pytest.fixture
def exported(case, tmp_path):
    recipe, result, context = case
    payload = text_key.build_payload(recipe, result, context)
    path = text_key.write(tmp_path / "synthetic.tkey", payload)
    return recipe, result, payload, path


def run_restore(**kwargs):
    defaults = dict(text=None, video=None, key_file=None, recipe=None,
                    context=OperationContext())
    defaults.update(kwargs)
    return asyncio.run(text_restore.restore_text(**defaults))


class FakeCarrier:
    """No network; independently reads this synthetic on-disk payload each time."""
    def __init__(self, expected_password="test-only-outer", *, failure=None, caps=None, after=None):
        self.expected_password = expected_password
        self.failure = failure
        self.caps = caps or CarrierCapabilities(
            "framewords", "fake", ("standard",), can_decode=True, supports_password=True,
        )
        self.after = after
        self.calls = []

    def capabilities(self):
        return self.caps

    async def decode(self, request, context):
        self.calls.append((request, context))
        assert "inner" not in repr(request) + repr(context)
        for slot in ("synthetic/l0", "synthetic/l1", "synthetic/video", "caller-only"):
            with pytest.raises(TextOperationError):
                context.secrets.require(slot)
        if self.failure is not None:
            raise self.failure
        if request.password != self.expected_password:
            raise TextOperationError(ErrorCode.WRONG_PASSWORD)
        text = request.source.read_bytes().decode("utf-8").split("\x00", 1)[1]
        if self.after:
            self.after()
        return DecodedText(text)


def test_key_text_restore_preserves_exact_text_and_caller_secrets(exported, pipeline_double):
    _, result, _, path = exported
    caller = OperationContext(RuntimeSecrets({"caller-only": "keep"}))
    events = []
    caller = replace(caller, notify=events.append)
    restored = run_restore(text=result.text, key_file=path, context=caller)
    original = "  合成😀\r\ne\u0301\t"
    assert restored.text == original and restored.verified is True
    assert restored.original_sha256 == text_digest(original)
    assert original not in repr(restored)
    assert caller.secrets.require("caller-only") == "keep"
    with pytest.raises(TextOperationError):
        caller.secrets.require("synthetic/l0")
    private = pipeline_double[1][0][3].secrets
    with pytest.raises(TextOperationError):
        private.require("synthetic/l0")
    assert [e.stage for e in events] == [Stage.PREFLIGHT, Stage.TEXT_DECODE, Stage.VERIFY]


@pytest.mark.parametrize("prefix", ["original synthetic video", "transcoded bytes changed"])
def test_video_bytes_need_not_match_and_only_outer_password_reaches_c(
        exported, pipeline_double, tmp_path, prefix):
    _, result, _, path = exported
    video = tmp_path / "synthetic.mp4"
    video.write_bytes((prefix + "\x00" + result.text).encode())
    stop = threading.Event()
    events = []
    caller = OperationContext(RuntimeSecrets({"caller-only": "keep"}), stop,
                              time.monotonic() + 60, events.append)
    carrier = FakeCarrier()
    restored = run_restore(video=video, key_file=path, context=caller, carrier=carrier)
    assert restored.text == "  合成😀\r\ne\u0301\t" and restored.verified
    request, outer = carrier.calls[0]
    assert request.password == "test-only-outer"
    assert outer.cancel is caller.cancel and outer.deadline == caller.deadline
    assert outer.notify is caller.notify and outer.secrets is not caller.secrets
    assert Stage.CARRIER_DECODE in [e.stage for e in events]
    assert pipeline_double[1][0][3].secrets is not outer.secrets
    assert video.read_bytes().startswith(prefix.encode())


@pytest.mark.parametrize("video_input", [False, True])
def test_manual_path_never_claims_digest_verification(recipe_double, pipeline_double,
                                                     tmp_path, video_input):
    recipe = recipe_double(recipe_data(video=video_input))
    result = synthetic_result()
    secrets = RuntimeSecrets({"synthetic/l0": "test-only-0", "synthetic/l1": "test-only-1",
                              **({"synthetic/video": "test-only-outer"} if video_input else {})})
    context = OperationContext(secrets)
    kwargs = {"text": result.text}
    if video_input:
        video = tmp_path / "manual.mp4"
        video.write_bytes(("video\x00" + result.text).encode())
        kwargs = {"video": video, "carrier": FakeCarrier()}
    restored = run_restore(recipe=recipe, context=context, **kwargs)
    assert restored.verified is False and restored.original_sha256 == text_digest(restored.text)
    assert pipeline_double[1][0][2] == ()
    assert secrets.require("synthetic/l0") == "test-only-0"


def test_passwordless_manual_video(recipe_double, pipeline_double, tmp_path):
    data = recipe_data(video=True, layers=0)
    data["carrier"]["secret_slot"] = None
    recipe = recipe_double(data)
    video = tmp_path / "plain.mp4"
    video.write_bytes("video\x00任意文字😀".encode())
    restored = run_restore(video=video, recipe=recipe, carrier=FakeCarrier(None))
    assert restored.text == "任意文字😀" and not restored.verified


@pytest.mark.parametrize("selection", [
    {}, {"text": "x", "video": "x"}, {"text": "x"},
    {"text": "x", "key_file": "x", "recipe": "x"},
    {"video": "x"},
])
def test_ambiguous_or_missing_inputs_rejected(selection, pipeline_double):
    with pytest.raises(TextOperationError) as error:
        run_restore(**selection)
    assert error.value.code == ErrorCode.INVALID_RECIPE
    assert pipeline_double[1] == []


@pytest.mark.parametrize("change", [lambda t: " " + t, lambda t: t + "\n",
                                    lambda t: t.replace("\r\n", "\n"), lambda t: t.replace("e\u0301", "é")])
def test_payload_mismatch_rejected_before_a(exported, pipeline_double, change):
    _, result, _, path = exported
    with pytest.raises(TextOperationError) as error:
        run_restore(text=change(result.text), key_file=path)
    assert error.value.code == ErrorCode.INTEGRITY and pipeline_double[1] == []


def test_extracted_video_text_mismatch(exported, pipeline_double, tmp_path):
    video = tmp_path / "wrong.mp4"
    video.write_bytes(b"video\x00unrelated payload")
    with pytest.raises(TextOperationError) as error:
        run_restore(video=video, key_file=exported[3], carrier=FakeCarrier())
    assert error.value.code == ErrorCode.INTEGRITY and pipeline_double[1] == []


@pytest.mark.parametrize("code", [ErrorCode.WRONG_PASSWORD, ErrorCode.NETWORK,
                                  ErrorCode.PAGE_CHANGED, ErrorCode.TIMEOUT,
                                  ErrorCode.CANCELLED, ErrorCode.MEDIA])
def test_carrier_failures_propagate_safe_codes(exported, pipeline_double, tmp_path, code):
    carrier = FakeCarrier(failure=TextOperationError(code))
    with pytest.raises(TextOperationError) as error:
        run_restore(video=tmp_path / "any.mp4", key_file=exported[3], carrier=carrier)
    assert error.value.code == code and error.value.__context__ is None
    assert pipeline_double[1] == []


@pytest.mark.parametrize("caps", [
    CarrierCapabilities("framewords", "fake"),
    CarrierCapabilities("wrong", "fake", ("standard",), can_decode=True, supports_password=True),
    CarrierCapabilities("framewords", "fake", ("other",), can_decode=True, supports_password=True),
    CarrierCapabilities("framewords", "fake", ("standard",), can_decode=True),
])
def test_unsupported_backend_rejected_before_decode(exported, pipeline_double, tmp_path, caps):
    carrier = FakeCarrier(caps=caps)
    with pytest.raises(TextOperationError) as error:
        run_restore(video=tmp_path / "any", key_file=exported[3], carrier=carrier)
    assert error.value.code == ErrorCode.UNSUPPORTED and carrier.calls == []


def test_missing_backend(exported, pipeline_double, tmp_path):
    with pytest.raises(TextOperationError) as error:
        run_restore(video=tmp_path / "any", key_file=exported[3])
    assert error.value.code == ErrorCode.UNSUPPORTED


@pytest.mark.parametrize("boundary", ["carrier", "pipeline"])
def test_private_exception_messages_and_chains_are_discarded(
        exported, pipeline_double, tmp_path, boundary):
    failure = ValueError("test-only-inner-0-秘密 raw body https://example.invalid/private")
    if boundary == "carrier":
        kwargs = dict(video=tmp_path / "any", carrier=FakeCarrier(failure=failure))
    else:
        def fail(*args):
            raise failure
        pipeline_double[0].decode_text = fail
        kwargs = dict(text=exported[1].text)
    with pytest.raises(TextOperationError) as error:
        run_restore(key_file=exported[3], **kwargs)
    assert "秘密" not in str(error.value) and "private" not in str(error.value)
    assert error.value.__context__ is None and error.value.__cause__ is None


@pytest.mark.parametrize("bad_result", ["wrong original", None, 12])
def test_final_original_digest_is_checked_even_if_a_returns_bad_result(
        exported, pipeline_double, bad_result):
    pipeline_double[0].decode_text = lambda *args: PipelineResult(bad_result, args[2])
    with pytest.raises(TextOperationError) as error:
        run_restore(text=exported[1].text, key_file=exported[3])
    assert error.value.code == ErrorCode.INTEGRITY


def test_middle_digest_failure_no_result_and_secrets_cleared(exported, pipeline_double):
    seen = []

    def fail(text, recipe, receipts, context):
        seen.append(context)
        assert context.secrets.require("synthetic/l0") == "test-only-inner-0-秘密"
        raise TextOperationError(ErrorCode.INTEGRITY)

    pipeline_double[0].decode_text = fail
    with pytest.raises(TextOperationError):
        run_restore(text=exported[1].text, key_file=exported[3])
    with pytest.raises(TextOperationError):
        seen[0].secrets.require("synthetic/l0")


@pytest.mark.parametrize("point", ["before", "carrier", "pipeline", "verify"])
def test_cancellation_at_boundaries(exported, pipeline_double, tmp_path, point):
    stop = threading.Event()
    kwargs = dict(text=exported[1].text)
    if point == "before":
        stop.set()
    elif point == "carrier":
        video = tmp_path / "video"
        video.write_bytes(("video\x00" + exported[1].text).encode())
        kwargs = dict(video=video, carrier=FakeCarrier(after=stop.set))
    elif point == "pipeline":
        original = pipeline_double[0].decode_text

        def cancel(*args):
            result = original(*args)
            stop.set()
            return result

        pipeline_double[0].decode_text = cancel

    def notify(event):
        if point == "verify" and event.stage == Stage.VERIFY:
            stop.set()

    with pytest.raises(TextOperationError) as error:
        run_restore(key_file=exported[3], context=OperationContext(cancel=stop, notify=notify), **kwargs)
    assert error.value.code == ErrorCode.CANCELLED


def test_timeout_before_work(exported, pipeline_double):
    with pytest.raises(TextOperationError) as error:
        run_restore(text=exported[1].text, key_file=exported[3],
                    context=OperationContext(deadline=time.monotonic() - 1))
    assert error.value.code == ErrorCode.TIMEOUT and pipeline_double[1] == []


def test_async_cancel_cleans_up(exported, pipeline_double, tmp_path):
    with pytest.raises(TextOperationError) as error:
        run_restore(video=tmp_path / "any", key_file=exported[3],
                    carrier=FakeCarrier(failure=asyncio.CancelledError()))
    assert error.value.code == ErrorCode.CANCELLED


def test_manual_missing_secret(recipe_double, pipeline_double):
    with pytest.raises(TextOperationError) as error:
        run_restore(text=synthetic_result().text, recipe=recipe_double(recipe_data()))
    assert error.value.code == ErrorCode.MISSING_SECRET and pipeline_double[1] == []


def test_manual_extracted_text_does_not_require_unused_video_password(
        recipe_double, pipeline_double):
    recipe = recipe_double(recipe_data(video=True))
    context = OperationContext(RuntimeSecrets({"synthetic/l0": "test-only-0",
                                               "synthetic/l1": "test-only-1"}))
    result = run_restore(text=synthetic_result().text, recipe=recipe, context=context)
    assert result.text == "  合成😀\r\ne\u0301\t" and not result.verified


def test_text_capacity_limit(recipe_double, pipeline_double):
    with pytest.raises(TextOperationError) as error:
        run_restore(text="x" * (text_key.MAX_TEXT_BYTES + 1),
                    recipe=recipe_double(recipe_data(layers=0)))
    assert error.value.code == ErrorCode.CAPACITY and pipeline_double[1] == []


def test_restore_creates_no_output_or_key_file(exported, pipeline_double, tmp_path):
    before = {p: p.read_bytes() for p in tmp_path.iterdir()}
    run_restore(text=exported[1].text, key_file=exported[3])
    assert before == {p: p.read_bytes() for p in tmp_path.iterdir()}


@pytest.mark.parametrize("fail", [False, True])
def test_loaded_payload_secret_references_released(exported, pipeline_double, monkeypatch, fail):
    payload = text_key.read(exported[3])
    monkeypatch.setattr(text_key, "read", lambda path: payload)
    if fail:
        with pytest.raises(TextOperationError):
            run_restore(text="unrelated", key_file=exported[3])
    else:
        assert run_restore(text=exported[1].text, key_file=exported[3]).verified
    assert payload["secrets"] == {}


@pytest.mark.parametrize("original", ["", "\r\n  \t", "e\u0301😀"])
def test_zero_layer_restore(recipe_double, pipeline_double, tmp_path, original):
    recipe = recipe_double(recipe_data(layers=0))
    key = text_key.write(tmp_path / "zero.tkey", text_key.build_payload(
        recipe, PipelineResult(original), OperationContext()))
    restored = run_restore(text=original, key_file=key)
    assert restored.text == original and restored.verified


@pytest.mark.parametrize("schemes", [(), ("base64", "reverse", "hex"),
                                     ("beast", "base64"), ("hajimi", "reverse")])
def test_real_a_text_roundtrip_when_available(tmp_path, schemes):
    """Optional real A+B integration, separate from the contract-double tests."""
    layers = pytest.importorskip("misong.text_layers")
    pipeline = pytest.importorskip("misong.text_pipeline")
    recipe = layers.DeliveryRecipe(1, "real-a", "合成真实文字链", tuple(
        layers.TextLayer(f"l{i}", scheme) for i, scheme in enumerate(schemes)
    ))
    original = "  https://example.invalid/s/synthetic\r\n中文😀e\u0301\t"
    context = OperationContext()
    encoded = pipeline.encode_text(original, recipe, context)
    key = text_key.write(tmp_path / "real-a.tkey", text_key.build_payload(recipe, encoded, context))
    result = run_restore(text=encoded.text, key_file=key)
    assert result.text == original and result.verified
    manual = run_restore(text=encoded.text, recipe=recipe)
    assert manual.text == original and not manual.verified


@pytest.mark.skipif(shutil.which("node") is None, reason="real mojibake integration requires Node")
def test_real_a_two_mojibake_passwords_and_wrong_key_when_available(tmp_path):
    layers = pytest.importorskip("misong.text_layers")
    pipeline = pytest.importorskip("misong.text_pipeline")
    recipe = layers.DeliveryRecipe(1, "real-moji", "双魔曰合成样本", (
        layers.TextLayer("first", "mojibake", params={"mode": "old"}, secret_slot="r/first"),
        layers.TextLayer("between", "base64"),
        layers.TextLayer("second", "mojibake", params={"mode": "old"}, secret_slot="r/second"),
        layers.TextLayer("base64", "base64"),
    ))
    context = OperationContext(RuntimeSecrets({"r/first": "test-only-一-123",
                                               "r/second": "test-only-二-456"}))
    original = "  合成😀\r\ne\u0301 https://example.invalid/s/demo\t"
    encoded = pipeline.encode_text(original, recipe, context)
    payload = text_key.build_payload(recipe, encoded, context)
    key = text_key.write(tmp_path / "two-moji.tkey", payload)
    result = run_restore(text=encoded.text, key_file=key)
    assert result.text == original and result.verified
    payload["secrets"]["r/first"] = "test-only-wrong-inner"
    wrong = text_key.write(tmp_path / "wrong.tkey", payload)
    with pytest.raises(TextOperationError) as error:
        run_restore(text=encoded.text, key_file=wrong)
    assert error.value.code == ErrorCode.INTEGRITY


@pytest.mark.skipif(shutil.which("node") is None, reason="real mojibake integration requires Node")
def test_real_a_adjacent_mojibake_never_delivers_on_digest_drift(tmp_path):
    """B must reject the observed A/vendor intermediate-ciphertext drift.

    A may reject this chain during its encode self-check, or B must reject a
    changed intermediate digest. If A later supports it exactly, B must restore
    exact text. This is not proof adjacent traditional mojibake is supported.
    """
    layers = pytest.importorskip("misong.text_layers")
    pipeline = pytest.importorskip("misong.text_pipeline")
    recipe = layers.DeliveryRecipe(1, "adjacent", "连续魔曰拒绝摘要漂移", tuple(
        layers.TextLayer(f"l{i}", "mojibake", params={"mode": "old"}, secret_slot=f"r/{i}")
        for i in range(2)
    ))
    context = OperationContext(RuntimeSecrets({"r/0": "test-only-0", "r/1": "test-only-1"}))
    original = "synthetic https://example.invalid/s/demo"
    try:
        encoded = pipeline.encode_text(original, recipe, context)
    except TextOperationError as encode_error:
        assert encode_error.code == ErrorCode.INTEGRITY
        assert list(tmp_path.iterdir()) == []
        return
    key = text_key.write(tmp_path / "adjacent.tkey", text_key.build_payload(recipe, encoded, context))
    try:
        direct = pipeline.decode_text(encoded.text, recipe, encoded.receipts, context)
    except TextOperationError as direct_error:
        assert direct_error.code == ErrorCode.INTEGRITY
        with pytest.raises(TextOperationError) as error:
            run_restore(text=encoded.text, key_file=key)
        assert error.value.code == ErrorCode.INTEGRITY
    else:
        assert direct.text == original
        restored = run_restore(text=encoded.text, key_file=key)
        assert restored.text == original and restored.verified


def test_real_a_rejects_altered_middle_receipt_when_available(tmp_path):
    layers = pytest.importorskip("misong.text_layers")
    pipeline = pytest.importorskip("misong.text_pipeline")
    recipe = layers.DeliveryRecipe(1, "real-middle", "中层计数错误", (
        layers.TextLayer("inner", "base64"), layers.TextLayer("outer", "reverse"),
    ))
    context = OperationContext()
    encoded = pipeline.encode_text("synthetic sample", recipe, context)
    payload = text_key.build_payload(recipe, encoded, context)
    payload["receipts"][0]["characters"] -= 1
    key = text_key.write(tmp_path / "wrong-count.tkey", payload)
    with pytest.raises(TextOperationError) as error:
        run_restore(text=encoded.text, key_file=key)
    assert error.value.code == ErrorCode.INTEGRITY
