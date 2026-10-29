"""Synchronous text layers only; carriers are invoked by the delivery service.

Receipts describe the one actual forward run, including randomized codecs.
Decoder errors are reduced to safe codes, never decoder text or secret values.
"""
from __future__ import annotations

import re
import shutil
import subprocess

from .encoders import beast, hajimi, mojibake, plain
from .text_contracts import (
    ErrorCode, LayerReceipt, OperationContext, PipelineResult, Stage,
    TextOperationError, text_digest,
)
from .text_layers import MAX_TEXT_BYTES, DeliveryRecipe, TextLayer

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _measure(text: str) -> tuple[int, int]:
    if not isinstance(text, str):
        raise TextOperationError(ErrorCode.INVALID_RECIPE)
    if len(text) > MAX_TEXT_BYTES:
        raise TextOperationError(ErrorCode.CAPACITY)
    invalid = False
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError:
        invalid = True
    if invalid:
        raise TextOperationError(ErrorCode.INTEGRITY)
    if size > MAX_TEXT_BYTES:
        raise TextOperationError(ErrorCode.CAPACITY)
    return len(text), size


def _prepare(text: str, recipe: DeliveryRecipe, context: OperationContext) -> None:
    context.report(Stage.PREFLIGHT)
    if not isinstance(recipe, DeliveryRecipe):
        raise TextOperationError(ErrorCode.INVALID_RECIPE)
    _measure(text)
    # Fail before encoding even one layer if an inner/outer text key is missing.
    # The carrier's key belongs to B/C, and is deliberately not read here.
    for layer in recipe.layers:
        context.check()
        if layer.secret_slot is not None:
            context.secrets.require(layer.secret_slot)


def _preflight_layer(text: str, layer: TextLayer) -> None:
    """Reject predictable expansion before allocating the encoded result."""
    size = len(text.encode("utf-8"))
    if layer.scheme in ("base64", "base64url"):
        lower_bound = ((size + 2) // 3) * 4
    elif layer.scheme == "base32":
        lower_bound = ((size + 4) // 5) * 8
    elif layer.scheme == "base85":
        lower_bound = (size * 5 + 3) // 4
    elif layer.scheme == "hex":
        lower_bound = size * 2
    elif layer.scheme == "beast":
        chars = layer.params.get("chars", beast.DEFAULT_DICT)
        count = len(text.encode("utf-16-le")) * 4
        lower_bound = count * min(len(c.encode("utf-8")) for c in chars)
        if layer.params.get("dialect", "web") != "sdk":
            lower_bound += sum(len(c.encode("utf-8")) for c in chars)
    else:
        lower_bound = 0
    if lower_bound > MAX_TEXT_BYTES:
        raise TextOperationError(ErrorCode.CAPACITY)


def _mojibake(text: str, key: str, mode: str, decode: bool,
              context: OperationContext) -> str:
    """Reuse the pinned encoder bridge, with cancellable, bounded process waits.

    The legacy Python wrapper uses an unbounded subprocess.run. Do not change
    that public API or the bridge/vendor; only adapt its process lifetime here.
    """
    mojibake._ensure()
    action = ("wenyan" if mode == "wenyan" else "old") + ("-dec" if decode else "-enc")
    process = subprocess.Popen(
        [shutil.which("node") or "node", str(mojibake.BRIDGE), action, key],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=str(mojibake.BRIDGE.parent), creationflags=mojibake.NO_WINDOW,
    )
    try:
        data = (text + "\n").encode("utf-8")
        while True:
            context.check()
            try:
                stdout, _ = process.communicate(input=data, timeout=0.05)
                break
            except subprocess.TimeoutExpired:
                data = None
        context.check()
        if process.returncode != 0:
            # Wrong keys and unsupported wenyan sentences cannot be reliably
            # distinguished by this codec. Never guess wrong_password.
            raise TextOperationError(ErrorCode.INTEGRITY)
        return stdout.decode("utf-8")
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


def _apply(text: str, layer: TextLayer, context: OperationContext, *, decode: bool) -> str:
    failure = None
    try:
        if layer.scheme == "mojibake":
            key = (context.secrets.require(layer.secret_slot)
                   if layer.secret_slot is not None else "ABRACADABRA")
            return _mojibake(text, key, layer.params.get("mode", "wenyan"), decode, context)
        if layer.scheme == "beast":
            # auto is an existing dialect alias for web on encode. Fix the
            # inverse to web too, rather than guessing a dialect on decode.
            params = dict(layer.params)
            params.setdefault("dialect", "web")
            if params.get("dialect") == "auto":
                params["dialect"] = "web"
            return (beast.decode if decode else beast.encode)(text, **params)
        if layer.scheme == "hajimi":
            return (hajimi.decode if decode else hajimi.encode)(text)
        return (plain.decode if decode else plain.encode)(layer.scheme, text)
    except TextOperationError as error:
        failure = error.code
    except mojibake.MojibakeUnavailable:
        failure = ErrorCode.UNSUPPORTED
    except Exception:
        failure = ErrorCode.INTEGRITY
    # Raise outside the except block: even __context__ must not retain a raw
    # codec error containing text, keys or process arguments.
    raise TextOperationError(failure)


def _validate_receipts(recipe: DeliveryRecipe, receipts: tuple[LayerReceipt, ...]) -> None:
    if not isinstance(receipts, tuple):
        raise TextOperationError(ErrorCode.INTEGRITY)
    if not receipts:
        return  # Explicit manual recipe mode, without original digest assurance.
    if len(receipts) != len(recipe.layers):
        raise TextOperationError(ErrorCode.INTEGRITY)
    previous = None
    for layer, receipt in zip(recipe.layers, receipts):
        if (not isinstance(receipt, LayerReceipt) or receipt.layer_id != layer.id
                or not isinstance(receipt.input_sha256, str)
                or not _DIGEST.fullmatch(receipt.input_sha256)
                or not isinstance(receipt.output_sha256, str)
                or not _DIGEST.fullmatch(receipt.output_sha256)
                or type(receipt.characters) is not int
                or type(receipt.utf8_bytes) is not int
                or not 0 <= receipt.characters <= receipt.utf8_bytes <= MAX_TEXT_BYTES
                or receipt.utf8_bytes > 4 * receipt.characters
                or previous is not None and previous != receipt.input_sha256):
            raise TextOperationError(ErrorCode.INTEGRITY)
        previous = receipt.output_sha256


def encode_text(text: str, recipe: DeliveryRecipe, context: OperationContext) -> PipelineResult:
    _prepare(text, recipe, context)
    receipts = []
    total = len(recipe.layers)
    context.report(Stage.TEXT_ENCODE, 0, total)
    for index, layer in enumerate(recipe.layers):
        context.check()
        _preflight_layer(text, layer)
        before = text_digest(text)
        text = _apply(text, layer, context, decode=False)
        context.check()
        characters, utf8_bytes = _measure(text)
        if layer.scheme == "mojibake" and layer.params.get("mode", "wenyan") == "old":
            # V3.0.11's traditional preCheck replaces its marker characters
            # even in forced encode mode. In particular, old -> old loses the
            # inner markers. Refuse such a result instead of exporting an
            # unrestorable recipe. Verification decodes this one generated
            # result; it never regenerates randomized ciphertext.
            restored = _apply(text, layer, context, decode=True)
            context.check()
            _measure(restored)
            if text_digest(restored) != before:
                raise TextOperationError(ErrorCode.INTEGRITY)
        receipts.append(LayerReceipt(layer.id, before, text_digest(text), characters, utf8_bytes))
        context.report(Stage.TEXT_ENCODE, index + 1, total)
    context.check()
    return PipelineResult(text, tuple(receipts))


def decode_text(text: str, recipe: DeliveryRecipe, receipts: tuple[LayerReceipt, ...],
                context: OperationContext) -> PipelineResult:
    _prepare(text, recipe, context)
    _validate_receipts(recipe, receipts)
    total = len(recipe.layers)
    context.report(Stage.TEXT_DECODE, 0, total)
    for index in range(total - 1, -1, -1):
        context.check()
        receipt = receipts[index] if receipts else None
        if receipt is not None:
            if (text_digest(text) != receipt.output_sha256
                    or _measure(text) != (receipt.characters, receipt.utf8_bytes)):
                raise TextOperationError(ErrorCode.INTEGRITY)
        text = _apply(text, recipe.layers[index], context, decode=True)
        context.check()
        _measure(text)
        if receipt is not None and text_digest(text) != receipt.input_sha256:
            raise TextOperationError(ErrorCode.INTEGRITY)
        context.report(Stage.TEXT_DECODE, total - index, total)
    context.check()
    return PipelineResult(text, receipts)
