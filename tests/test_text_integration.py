"""Real A+B integration and C wiring; fake video transport, never a real site."""
import asyncio
import json
import threading
import time
from pathlib import Path
from contextlib import asynccontextmanager

import pytest

from misong import text_delivery, text_key
from misong.carriers import CarrierCapabilities, DecodedText, EncodedVideo
from misong.cli import main
from misong.desktop.api import Api
from misong.text_contracts import (
    ErrorCode, OperationContext, RuntimeSecrets, TextOperationError, text_digest,
)
from misong.text_layers import CarrierSpec, DeliveryRecipe, TextLayer


def recipe(*, video=False, keyed=False):
    return DeliveryRecipe(1, "demo", "合成方案", (
        TextLayer("first", "mojibake" if keyed else "base64",
                  secret_slot="inner" if keyed else None),
        TextLayer("second", "base85"),
    ), CarrierSpec("framewords", mode="standard", secret_slot="outer") if video else CarrierSpec())


class FakeVideo:
    def __init__(self):
        self.text = None
        self.calls = []

    def capabilities(self):
        return CarrierCapabilities("framewords", "test", ("standard",), True, True, True)

    async def encode(self, request, context):
        assert request.password == "outer-test"
        with pytest.raises(TextOperationError):
            context.secrets.require("inner")
        self.calls.append("encode")
        self.text = request.text
        request.destination.write_bytes(b"synthetic video transport")
        return EncodedVideo(request.destination, text_digest(request.text), True)

    async def decode(self, request, context):
        assert request.password == "outer-test"
        with pytest.raises(TextOperationError):
            context.secrets.require("inner")
        self.calls.append("decode")
        return DecodedText(self.text)


def test_real_text_chain_key_and_restore_preserve_exact_utf8(tmp_path):
    original = "  https://example.invalid/s/demo\r\n中文😀\n  "
    r = recipe()
    result = asyncio.run(text_delivery.deliver_text(original, (r,), tmp_path / "out",
                                                   OperationContext(), export_keys=[r.id]))
    assert result["recipes"][0]["verified"]
    folder = tmp_path / "out" / r.id
    restored = asyncio.run(text_delivery.restore_to_file(
        tmp_path / "restored.txt", context=OperationContext(),
        text=text_delivery.read_text_file(folder / "message.txt"), video=None,
        key_file=folder / "message.tkey", recipe=None))
    assert restored["verified"]
    assert (tmp_path / "restored.txt").read_bytes() == original.encode("utf-8")
    assert original not in json.dumps(result)
    assert text_key.read(folder / "message.tkey")["recipe"] == r.to_dict()


def test_key_export_is_off_and_existing_output_is_protected(tmp_path):
    r = DeliveryRecipe(1, "plain", "原文")
    asyncio.run(text_delivery.deliver_text("\r\ntext", (r,), tmp_path / "out", OperationContext()))
    assert list(tmp_path.rglob("*.tkey")) == []
    assert (tmp_path / "out/plain/message.txt").read_bytes() == b"\r\ntext"
    with pytest.raises(TextOperationError) as error:
        asyncio.run(text_delivery.deliver_text("replace", (r,), tmp_path / "out", OperationContext()))
    assert error.value.code == ErrorCode.IO and error.value.__context__ is None
    assert (tmp_path / "out/plain/message.txt").read_bytes() == b"\r\ntext"


def test_video_key_restore_and_inner_secrets_are_not_sent_to_carrier(tmp_path):
    r = recipe(video=True, keyed=True)
    backend = FakeVideo()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"original")
    values = RuntimeSecrets({"inner": "inner-test", "outer": "outer-test"})
    original = "https://example.invalid/s/test 中文😀"
    asyncio.run(text_delivery.deliver_text(original, (r,), tmp_path / "out", OperationContext(values),
                                          video_sources={r.id: source}, export_keys=[r.id], carrier=backend))
    restored = asyncio.run(text_delivery.restore_to_file(
        tmp_path / "restored.txt", context=OperationContext(), text=None,
        video=tmp_path / "out/demo/message.mp4", key_file=tmp_path / "out/demo/message.tkey",
        recipe=None, carrier=backend))
    assert restored["verified"] and backend.calls == ["encode", "decode"]
    assert (tmp_path / "restored.txt").read_bytes() == original.encode("utf-8")
    assert source.read_bytes() == b"original"


def test_bad_key_does_not_create_restore_target(tmp_path):
    key = tmp_path / "bad.tkey"
    key.write_bytes(b"synthetic corruption")
    with pytest.raises(TextOperationError):
        asyncio.run(text_delivery.restore_to_file(tmp_path / "out.txt", context=OperationContext(),
                    text="text", video=None, key_file=key, recipe=None))
    assert not (tmp_path / "out.txt").exists()


def test_failed_key_export_removes_only_this_recipe(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("synthetic private backend detail")
    monkeypatch.setattr(text_key, "write", fail)
    other = tmp_path / "keep"
    other.write_text("keep")
    with pytest.raises(TextOperationError) as error:
        asyncio.run(text_delivery.deliver_recipe("text", recipe(), tmp_path / "recipe",
                                                OperationContext(), export_key=True))
    assert error.value.code == ErrorCode.IO and error.value.__context__ is None
    assert not (tmp_path / "recipe").exists() and other.read_text() == "keep"


def test_cli_roundtrip_and_no_overwrite(tmp_path, capsys):
    source = tmp_path / "original.txt"
    source.write_bytes("中文😀\r\n ".encode("utf-8"))
    config = tmp_path / "recipe.json"
    config.write_text(json.dumps(recipe().to_dict()), encoding="utf-8")
    assert main(["text-deliver", str(source), "--recipes", str(config), "--export-key", "demo",
                 "-o", str(tmp_path / "out")]) == 0
    args = ["text-restore", str(tmp_path / "out/demo/message.txt"), "--input-kind", "text",
            "--key-file", str(tmp_path / "out/demo/message.tkey"), "-o", str(tmp_path / "restored.txt")]
    assert main(args) == 0
    assert (tmp_path / "restored.txt").read_bytes() == source.read_bytes()
    assert main(args) == 1
    assert "中文😀" not in capsys.readouterr().out


def wait(api):
    deadline = time.monotonic() + 10
    events = []
    while time.monotonic() < deadline:
        events.extend(api.poll()["data"]["events"])
        done = [e for e in events if e["type"] == "job" and e["state"] != "running"]
        if done:
            return done[-1], events
        time.sleep(.01)
    pytest.fail("text job timed out")


def test_api_jobs_use_existing_envelope_and_do_not_persist_requests(tmp_path):
    api = Api(tmp_path / "runs", tmp_path / "state")
    r = recipe()
    original = "synthetic-private-message\r\n"
    request = {"text": original, "recipes": [r.to_dict()], "export_keys": [r.id]}
    preview = api.preview_text_delivery({"text": original, "recipes": [r.to_dict()]})
    assert preview["ok"] and preview["data"]["recipes"][0]["recipe_id"] == r.id
    start = api.start_text_delivery(request)
    assert start["ok"] and start["data"]["kind"] == "text-delivery"
    done, events = wait(api)
    assert done["state"] == "done", done
    files = done["result"]["recipes"][0]["files"]
    source = Path(next(f["path"] for f in files if f["role"] == "text"))
    key = next(f["path"] for f in files if f["role"] == "text_key")
    assert request["text"] == original  # private request copy only is cleared
    assert api.start_text_restore({"text": text_delivery.read_text_file(source), "key_file": key})["ok"]
    restored, more = wait(api)
    assert restored["state"] == "done" and restored["result"]["verified"]
    assert Path(restored["result"]["out"]).read_bytes() == original.encode("utf-8")
    assert original not in json.dumps(events + more)
    assert not any("recipe" in f.name for f in (tmp_path / "state").rglob("*.json"))


def test_api_invalid_request_and_worker_error_are_safe(tmp_path, monkeypatch):
    api = Api(tmp_path / "runs", tmp_path / "state")
    assert not api.preview_text_delivery({"text": "text", "recipes": [], "password": "private"})["ok"]
    async def fail(*args, **kwargs):
        raise RuntimeError("synthetic-secret-from-backend")
    monkeypatch.setattr(text_delivery, "deliver_text", fail)
    assert api.start_text_delivery({"text": "private text", "recipes": [recipe().to_dict()]})["ok"]
    done, events = wait(api)
    assert done["state"] == "error"
    assert "synthetic-secret-from-backend" not in json.dumps(events)
    assert "private text" not in json.dumps(events)


def test_cancel_before_delivery_leaves_no_output(tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(TextOperationError) as error:
        asyncio.run(text_delivery.deliver_recipe("text", recipe(), tmp_path / "out",
                                                OperationContext(cancel=cancel)))
    assert error.value.code == ErrorCode.CANCELLED
    assert not (tmp_path / "out").exists()


def test_publish_recipe_retry_does_not_repeat_upload_share_or_completed_recipe(tmp_path, monkeypatch):
    from misong import publish as publisher
    from misong.jobs import fingerprint, save_json
    from misong.sharing import ShareInfo
    source = tmp_path / "artifact.bin"
    source.write_bytes(b"synthetic upload")
    first = DeliveryRecipe(1, "first", "first")
    second = DeliveryRecipe(1, "second", "second", (TextLayer("text", "base64"),))
    plan = {"version": 2, "id": "synthetic", "form": "direct", "schemes": [],
            "state": "prepared", "text_recipes": [first.to_dict(), second.to_dict()],
            "stages": [{"id": "body", "disk": "quark", "folder": "synthetic", "files": [fingerprint(source)],
                        "uploaded": {}, "state": "pending"}]}
    path = tmp_path / "relay-plan.json"
    save_json(path, plan)
    events = []
    class Driver:
        async def upload(self, page, files, folder):
            events.append("upload")
            return ["synthetic"]
        async def share(self, page, targets):
            events.append("share")
            return ShareInfo("quark", "https://pan.quark.cn/s/synthetic-test")
    class Runtime:
        @asynccontextmanager
        async def open(self, disk):
            yield Driver(), None
    original = text_delivery.deliver_recipe
    failed = False
    calls = []
    async def fail_once(text, r, *args, **kwargs):
        nonlocal failed
        calls.append(r.id)
        if r.id == "second" and not failed:
            failed = True
            raise TextOperationError(ErrorCode.NETWORK)
        return await original(text, r, *args, **kwargs)
    monkeypatch.setattr(text_delivery, "deliver_recipe", fail_once)
    with pytest.raises(TextOperationError):
        asyncio.run(publisher.publish(path, runtime=Runtime(), notify=lambda _: None, export_text_keys=["first"]))
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["state"] == "blocked" and saved["text_delivery"]["share_complete"]
    records = saved["text_delivery"]["recipes"]
    assert [r["status"] for r in records] == ["complete", "blocked"]
    key = next(Path(a["path"]) for a in records[0]["artifacts"] if a["role"] == "text_key")
    before = key.read_bytes()
    result = asyncio.run(publisher.publish(path, runtime=Runtime(), notify=lambda _: None))
    assert events == ["upload", "share"]
    assert calls == ["first", "second", "second"]
    assert key.read_bytes() == before
    assert result["plan"]["state"] == "complete"
    assert result["copies"] == {}


def test_preview_does_not_reencode_and_capabilities_are_public(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("preview must not encode or prompt")
    monkeypatch.setattr(text_delivery, "encode_text", forbidden)
    assert text_delivery.preview("text", (recipe(),))["recipes"][0]["capacity_known"]
    api = Api(tmp_path / "runs", tmp_path / "state")
    caps = api.text_capabilities()
    assert caps["ok"] and caps["data"]["carriers"][0]["format_id"] == "text"
