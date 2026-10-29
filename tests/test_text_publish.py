"""D package: step-4 orchestration, status, retry and cleanup with fake drivers only."""
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from misong import cleanup, publish as publisher, text_delivery, workflows
from misong.jobs import fingerprint, save_json
from misong.sharing import ShareInfo
from misong.text_contracts import ErrorCode, TextOperationError
from misong.text_layers import DeliveryRecipe, TextLayer

SECRET = "synthetic-secret-value"


class Runtime:
    def __init__(self):
        self.events = []
        outer = self

        class Driver:
            async def upload(self, page, files, folder):
                outer.events.append("upload")
                return ["synthetic"]

            async def share(self, page, targets):
                outer.events.append("share")
                return ShareInfo("quark", "https://pan.quark.cn/s/synthetic-test")
        self.driver = Driver()

    @asynccontextmanager
    async def open(self, disk):
        yield self.driver, None


def recipes():
    return [DeliveryRecipe(1, "plain", "原文"),
            DeliveryRecipe(1, "encoded", "编码", (TextLayer("text", "base64"),))]


def make_plan(tmp_path, *, clean=False, legacy=False):
    body = tmp_path / "body"
    body.mkdir()
    artifact = body / "artifact.bin"
    artifact.write_bytes(b"synthetic upload")
    record = fingerprint(artifact)
    plan = {"version": 2, "id": "synthetic", "form": "direct", "state": "prepared",
            "schemes": ["base64"] if legacy else [],
            "stages": [{"id": "body", "disk": "quark", "folder": "synthetic", "files": [record],
                        "uploaded": {}, "state": "pending"}]}
    if not legacy:
        plan["text_recipes"] = [r.to_dict() for r in recipes()]
    plan["local_cleanup"] = cleanup.inventory(tmp_path, [], [record], clean)
    path = tmp_path / "relay-plan.json"
    save_json(path, plan)
    return path, artifact


def fail_first(monkeypatch, target_id, code=ErrorCode.NETWORK):
    original = text_delivery.deliver_recipe
    calls, state = [], {"failed": False}

    async def wrapper(text, recipe, *args, **kwargs):
        calls.append(recipe.id)
        if recipe.id == target_id and not state["failed"]:
            state["failed"] = True
            raise TextOperationError(code)
        return await original(text, recipe, *args, **kwargs)
    monkeypatch.setattr(text_delivery, "deliver_recipe", wrapper)
    return calls


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_status_distinguishes_shared_from_fully_delivered(tmp_path, monkeypatch):
    path, _ = make_plan(tmp_path)
    assert workflows.delivery_status(load(path))["label"] == "未分享"
    fail_first(monkeypatch, "encoded")
    runtime = Runtime()
    with pytest.raises(TextOperationError):
        asyncio.run(publisher.publish(path, runtime=runtime, notify=lambda _: None))
    status = workflows.delivery_status(load(path))
    assert status["share_complete"] and not status["delivery_complete"]
    assert status["label"] == "分享完成、文案未完成"
    assert [r["status"] for r in status["recipes"]] == ["complete", "blocked"]
    assert status["recipes"][1]["error_code"] == ErrorCode.NETWORK.value
    assert load(path)["error"]["stage"] == "text_delivery"
    asyncio.run(publisher.publish(path, runtime=runtime, notify=lambda _: None))
    final = workflows.delivery_status(load(path))
    assert final["delivery_complete"] and final["label"] == "全部交付完成"
    assert runtime.events == ["upload", "share"]


def test_retry_reruns_only_failed_recipe_without_upload_or_share(tmp_path, monkeypatch):
    path, _ = make_plan(tmp_path)
    calls = fail_first(monkeypatch, "encoded")
    runtime = Runtime()
    with pytest.raises(TextOperationError):
        asyncio.run(publisher.publish(path, runtime=runtime, notify=lambda _: None))
    first_files = load(path)["text_delivery"]["recipes"][0]["artifacts"]
    asyncio.run(publisher.publish(path, runtime=runtime, notify=lambda _: None))
    assert runtime.events == ["upload", "share"]
    assert calls == ["plain", "encoded", "encoded"]
    assert load(path)["text_delivery"]["recipes"][0]["artifacts"] == first_files


def test_cancelled_recipe_keeps_share_and_is_resumable(tmp_path, monkeypatch):
    path, _ = make_plan(tmp_path)
    fail_first(monkeypatch, "plain", ErrorCode.CANCELLED)
    runtime = Runtime()
    with pytest.raises(TextOperationError):
        asyncio.run(publisher.publish(path, runtime=runtime, notify=lambda _: None))
    saved = load(path)
    assert saved["state"] == "paused" and saved["stages"][0]["share"]
    assert [r["status"] for r in saved["text_delivery"]["recipes"]] == ["cancelled"]
    asyncio.run(publisher.publish(path, runtime=runtime, notify=lambda _: None))
    assert workflows.delivery_status(load(path))["delivery_complete"]
    assert runtime.events == ["upload", "share"]


def test_secrets_and_plaintext_share_never_enter_checkpoint(tmp_path):
    from misong.text_contracts import OperationContext, RuntimeSecrets
    path, _ = make_plan(tmp_path)
    plan = load(path)
    plan["text_recipes"] = [DeliveryRecipe(1, "keyed", "魔曰", (TextLayer("m", "mojibake", secret_slot="keyed/m"),)).to_dict()]
    save_json(path, plan)
    context = OperationContext(RuntimeSecrets({"keyed/m": SECRET}))
    asyncio.run(publisher.publish(path, runtime=Runtime(), notify=lambda _: None, text_context=context,
                                  export_text_keys=["keyed"]))
    raw = path.read_text(encoding="utf-8")
    assert SECRET not in raw and "synthetic-test" not in json.dumps(load(path)["text_delivery"])
    assert any(a["role"] == "text_key" for a in load(path)["text_delivery"]["recipes"][0]["artifacts"])


def test_cleanup_waits_for_all_recipes_and_keeps_deliveries(tmp_path, monkeypatch):
    path, artifact = make_plan(tmp_path, clean=True)
    fail_first(monkeypatch, "encoded")
    runtime = Runtime()
    with pytest.raises(TextOperationError):
        asyncio.run(publisher.publish(path, runtime=runtime, notify=lambda _: None,
                                      export_text_keys=["plain"]))
    assert artifact.exists(), "blocked step 4 must not clean generated payloads"
    asyncio.run(publisher.publish(path, runtime=runtime, notify=lambda _: None))
    saved = load(path)
    assert not artifact.exists() and saved["local_cleanup"]["state"] == "complete"
    for record in saved["text_delivery"]["recipes"]:
        for item in record["artifacts"]:
            assert Path(item["path"]).exists()
    assert list(tmp_path.rglob("*.tkey"))


def test_cleanup_gate_and_protected_keys_unit(tmp_path):
    plan = {"text_recipes": [{"id": "a"}], "text_delivery": {"recipes": [{"recipe_id": "a", "status": "blocked"}]}}
    assert cleanup.text_delivery_pending(plan)
    plan["text_delivery"]["recipes"][0]["status"] = "complete"
    assert not cleanup.text_delivery_pending(plan)
    assert not cleanup.text_delivery_pending({"schemes": ["base64"]})
    (tmp_path / "body").mkdir()
    for name in ("x.tkey", "x.mskey"):
        key = tmp_path / "body" / name
        key.write_bytes(b"k")
        with pytest.raises(ValueError, match="protected_key"):
            cleanup._safe_path(tmp_path, {"path": str(key)}, [])


def test_legacy_schemes_status_and_publish_unchanged(tmp_path):
    path, _ = make_plan(tmp_path, legacy=True)
    result = asyncio.run(publisher.publish(path, runtime=Runtime(), notify=lambda _: None))
    assert result["copies"] and "text_delivery" not in result["plan"]
    status = workflows.delivery_status(load(path))
    assert status["mode"] == "legacy" and status["delivery_complete"]
    old = {"stages": [{"share": {"url": "x"}}], "state": "blocked"}
    assert workflows.delivery_status(old)["label"] == "网盘已分享"
