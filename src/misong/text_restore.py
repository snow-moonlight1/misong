"""All-or-nothing text restore, with optional outer video decoding.

No output files or browser backends are selected implicitly. S owns explicit
UTF-8 file delivery and its no-overwrite policy at the CLI/API boundary.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from . import text_key
from .carriers import DecodeRequest, VideoCarrier
from .text_contracts import (
    ErrorCode, LayerReceipt, OperationContext, RuntimeSecrets, Stage,
    TextOperationError, text_digest,
)

if TYPE_CHECKING:
    from .text_layers import DeliveryRecipe


@dataclass(frozen=True)
class RestoreResult:
    text: str = field(repr=False)
    original_sha256: str
    verified: bool


def _bounded_text(text):
    if type(text) is not str:
        raise TextOperationError(ErrorCode.INTEGRITY)
    if len(text.encode("utf-8")) > text_key.MAX_TEXT_BYTES:
        raise TextOperationError(ErrorCode.CAPACITY)


async def restore_text(*, text: str | None, video: Path | None,
                       key_file: Path | None, recipe: DeliveryRecipe | None,
                       context: OperationContext,
                       carrier: VideoCarrier | None = None) -> RestoreResult:
    """Restore exactly one input using exactly one key or manual recipe.

    Manual decoding computes a digest of its result but cannot authenticate the
    original, so verified is always False. Private key secrets are cleared on
    every exit and never inserted into the caller's context.
    """
    private = RuntimeSecrets()
    external = RuntimeSecrets()
    payload = None
    code, failure_code = None, ErrorCode.INVALID_RECIPE
    try:
        context.report(Stage.PREFLIGHT)
        if ((text is None) == (video is None)
                or (key_file is None) == (recipe is None)):
            raise TextOperationError(ErrorCode.INVALID_RECIPE)
        payload = text_key.read(key_file) if key_file is not None else None
        public = payload["recipe"] if payload is not None else recipe.to_dict()
        parsed = text_key._parse_recipe(public)
        slots = text_key._slots(public)
        if payload is None and video is None:
            # An already extracted text input needs no outer video password.
            slots = {layer["secret_slot"] for layer in public["layers"]
                     if layer["secret_slot"] is not None}
        private = RuntimeSecrets(payload["secrets"] if payload is not None else
                                 {slot: context.secrets.require(slot) for slot in slots})
        local = OperationContext(private, context.cancel, context.deadline, context.notify)
        receipts = tuple(LayerReceipt(**r) for r in payload["receipts"]) if payload else ()
        local.check()
        if video is not None:
            failure_code = ErrorCode.MEDIA
            spec = public["carrier"]
            if carrier is None or spec["format_id"] == "text":
                raise TextOperationError(ErrorCode.UNSUPPORTED)
            caps = carrier.capabilities()
            if (not caps.can_decode or caps.format_id != spec["format_id"]
                    or spec["mode"] not in caps.modes
                    or spec["secret_slot"] is not None and not caps.supports_password):
                raise TextOperationError(ErrorCode.UNSUPPORTED)
            request = DecodeRequest(
                Path(video), spec["mode"],
                private.require(spec["secret_slot"]) if spec["secret_slot"] else None,
            )
            outer = OperationContext(external, context.cancel, context.deadline, context.notify)
            outer.report(Stage.CARRIER_DECODE)
            decoded = await carrier.decode(request, outer)
            local.check()
            text = decoded.text
        failure_code = ErrorCode.INTEGRITY
        _bounded_text(text)
        if payload is not None:
            if text_digest(text) != payload["payload_sha256"]:
                raise TextOperationError(ErrorCode.INTEGRITY)
            if receipts and (receipts[-1].characters != len(text)
                             or receipts[-1].utf8_bytes != len(text.encode("utf-8"))):
                raise TextOperationError(ErrorCode.INTEGRITY)
        local.report(Stage.TEXT_DECODE)
        from .text_pipeline import decode_text
        result = decode_text(text, parsed, receipts, local)
        local.check()
        _bounded_text(result.text)
        digest = text_digest(result.text)
        local.report(Stage.VERIFY)
        if payload is not None and (digest != payload["original_sha256"]
                                    or result.receipts != receipts):
            raise TextOperationError(ErrorCode.INTEGRITY)
        restored = RestoreResult(result.text, digest, payload is not None)
        local.check()
    except TextOperationError as error:
        code = error.code
    except asyncio.CancelledError:
        code = ErrorCode.CANCELLED
    except ImportError:
        code = ErrorCode.UNSUPPORTED
    except Exception:
        code = failure_code
    finally:
        private.clear()
        external.clear()
        if payload is not None:
            payload["secrets"].clear()
    # Raise outside the except block so a sensitive backend exception is not
    # retained as __context__, even by code that ignores __suppress_context__.
    if code is not None:
        raise TextOperationError(code)
    return restored
