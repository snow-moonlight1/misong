"""Cross-package boundary checks, without browser or text algorithm dependencies."""
import asyncio
import threading
import time
from dataclasses import asdict
from pathlib import Path

import pytest

from misong.carriers import (
    CarrierCapabilities, DecodeRequest, DecodedText, EncodeRequest,
    verify_saved_video,
)
from misong.text_contracts import (
    ErrorCode, OperationContext, PipelineResult, RuntimeSecrets, Stage,
    TextOperationError, text_digest,
)


def test_runtime_values_not_in_representations_or_progress():
    secret = "synthetic-test-secret"
    text = "synthetic private text"
    events = []
    secrets = RuntimeSecrets({"layer-1": secret})
    context = OperationContext(secrets=secrets, notify=events.append)
    context.report(Stage.TEXT_ENCODE, 1, 2)
    objects = [secrets, context, PipelineResult(text), DecodedText(text),
               EncodeRequest(Path("private-source"), Path("private-target"), text, password=secret),
               DecodeRequest(Path("private-source"), password=secret)]
    for obj in objects:
        assert secret not in repr(obj) and text not in repr(obj)
        assert "private-source" not in repr(obj)
    assert asdict(events[0]) == {"stage": Stage.TEXT_ENCODE, "completed": 1, "total": 2}
    assert secrets.require("layer-1") == secret
    secrets.clear()
    with pytest.raises(TextOperationError) as error:
        secrets.require("layer-1")
    assert error.value.code == ErrorCode.MISSING_SECRET
    assert secret not in str(error.value)


def test_cancellation_prevents_progress_and_deadline_expires():
    cancel = threading.Event()
    cancel.set()
    events = []
    with pytest.raises(TextOperationError) as error:
        OperationContext(cancel=cancel, notify=events.append).report(Stage.VERIFY)
    assert error.value.code == ErrorCode.CANCELLED
    assert events == []
    with pytest.raises(TextOperationError) as error:
        OperationContext(deadline=time.monotonic() - 1).check()
    assert error.value.code == ErrorCode.TIMEOUT


@pytest.mark.parametrize("completed,total", [(-1, None), (2, 1), (True, 2), (0, -1)])
def test_invalid_progress_rejected(completed, total):
    with pytest.raises(TextOperationError):
        OperationContext().report(Stage.VERIFY, completed, total)


def test_exact_text_hash_preserves_whitespace_and_unicode():
    assert text_digest("é") != text_digest("e\u0301")
    assert text_digest("hello\r\n") != text_digest("hello\n")
    assert DecodedText("中文😀\n").sha256 == text_digest("中文😀\n")


class FileReader:
    def __init__(self, cancel=None):
        self.calls = []
        self.cancel = cancel

    async def decode(self, request, context):
        self.calls.append(request.source)
        if self.cancel is not None:
            self.cancel.set()
        return DecodedText(request.source.read_text(encoding="utf-8"))


def test_verify_reads_saved_artifact_and_rejects_stale_input(tmp_path):
    saved = tmp_path / "synthetic-media"
    saved.write_text("中文😀\n", encoding="utf-8")
    backend = FileReader()
    request = DecodeRequest(saved)
    result = asyncio.run(verify_saved_video(backend, request, "中文😀\n", OperationContext()))
    assert result.text == "中文😀\n" and backend.calls == [saved]
    saved.write_text("changed", encoding="utf-8")
    with pytest.raises(TextOperationError) as error:
        asyncio.run(verify_saved_video(backend, request, "中文😀\n", OperationContext()))
    assert error.value.code == ErrorCode.INTEGRITY
    assert "changed" not in str(error.value)


def test_cancel_during_decode_does_not_return_text(tmp_path):
    saved = tmp_path / "synthetic-media"
    saved.write_text("test", encoding="utf-8")
    cancel = threading.Event()
    with pytest.raises(TextOperationError) as error:
        asyncio.run(verify_saved_video(FileReader(cancel), DecodeRequest(saved), "test",
                                      OperationContext(cancel=cancel)))
    assert error.value.code == ErrorCode.CANCELLED


def test_capability_defaults_do_not_advertise_implementation():
    caps = CarrierCapabilities("framewords", "framewords_web")
    assert not caps.can_encode and not caps.can_decode
    assert caps.modes == caps.verified_versions == ()
