"""Explicitly exported bearer text keys; never ordinary task/settings data.

v1 envelope: MISONGTKEY + NUL + version byte 1, random 32-byte wrapping
key, 12-byte nonce, AES-256-GCM ciphertext and 16-byte tag. The complete
header is AAD. Anyone holding the file can unwrap it; this is corruption
detection, not source authentication or protection against its holder.
"""
from __future__ import annotations

import json
import re
import secrets
from pathlib import Path
from typing import TYPE_CHECKING

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .text_contracts import (
    ErrorCode, OperationContext, PipelineResult, TextOperationError,
    text_digest,
)

if TYPE_CHECKING:
    from .text_layers import DeliveryRecipe

EXT = ".tkey"
MAGIC = b"MISONGTKEY\x00\x01"
MAX_SIZE = 4 * 1024 * 1024
MAX_LAYERS = 32
MAX_TEXT_BYTES = 1024 * 1024
_HEADER_SIZE = len(MAGIC) + 32 + 12
_PAYLOAD_FIELDS = {
    "type", "version", "recipe", "receipts", "original_sha256",
    "payload_sha256", "secrets",
}
_RECEIPT_FIELDS = {
    "layer_id", "input_sha256", "output_sha256", "characters", "utf8_bytes",
}
_SCHEMES = {
    "beast", "mojibake", "hajimi", "base64", "base64url", "base32",
    "base85", "hex", "url", "reverse", "rot13",
}


def _fail(code=ErrorCode.INVALID_RECIPE):
    raise TextOperationError(code)


def _fields(value, fields):
    if type(value) is not dict or value.keys() != fields:
        _fail()


def _json_tree(value, depth=0):
    # Only JSON types, before serialization can coerce tuples or numeric keys.
    # Our fixed schema is shallow; bound malicious nesting/cycles explicitly.
    if depth > 16:
        _fail()
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                _fail()
            _json_tree(item, depth + 1)
    elif type(value) is list:
        for item in value:
            _json_tree(item, depth + 1)
    elif type(value) not in (str, int, bool, type(None)):
        _fail()


def _json_bytes(value):
    _json_tree(value)
    code = None
    try:
        data = json.dumps(value, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        code = ErrorCode.INVALID_RECIPE
    if code is not None:
        _fail(code)
    if len(data) + _HEADER_SIZE + 16 > MAX_SIZE:
        _fail(ErrorCode.CAPACITY)
    return data


def _parse_recipe(data):
    """Check the key boundary, then reuse A's algorithm/parameter validator.

    Delayed import permits B's contract-double tests without A installed and
    importing key/carrier contracts never loads a browser or an encoder.
    """
    _fields(data, {"version", "id", "name", "layers", "carrier"})
    if type(data["version"]) is not int or data["version"] != 1:
        _fail()
    if any(type(data[k]) is not str or not data[k] for k in ("id", "name")):
        _fail()
    layers = data["layers"]
    if type(layers) is not list or len(layers) > MAX_LAYERS:
        _fail()
    ids, slots = set(), set()
    for layer in layers:
        _fields(layer, {"id", "scheme", "version", "params", "secret_slot"})
        if (type(layer["id"]) is not str or not layer["id"] or layer["id"] in ids
                or type(layer["version"]) is not int or layer["version"] != 1
                or type(layer["scheme"]) is not str or layer["scheme"] not in _SCHEMES
                or type(layer["params"]) is not dict):
            _fail()
        ids.add(layer["id"])
    carrier = data["carrier"]
    _fields(carrier, {"format_id", "version", "mode", "params", "secret_slot"})
    if (type(carrier["version"]) is not int or carrier["version"] != 1
            or (carrier["format_id"], carrier["mode"]) not in
            (("text", "plain"), ("framewords", "standard"))
            or type(carrier["params"]) is not dict or carrier["params"]):
        _fail()
    for item in [*layers, carrier]:
        slot = item["secret_slot"]
        if slot is not None:
            if type(slot) is not str or not slot or slot in slots:
                _fail()
            slots.add(slot)
    code = None
    try:
        from .text_layers import DeliveryRecipe
        parsed = DeliveryRecipe.from_dict(data)
    except ImportError:
        code = ErrorCode.UNSUPPORTED
    except Exception:
        code = ErrorCode.INVALID_RECIPE
    if code is not None:
        _fail(code)
    return parsed


def _digest(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        _fail()


def _slots(recipe):
    return {item["secret_slot"] for item in [*recipe["layers"], recipe["carrier"]]
            if item["secret_slot"] is not None}


def validate(payload: dict) -> dict:
    """Validate a sensitive in-memory payload; return a detached JSON snapshot."""
    # JSON roundtrip bounds size/depth, rejects cycles and detaches nested params.
    data = json.loads(_json_bytes(payload))
    _fields(data, _PAYLOAD_FIELDS)
    if (data["type"] != "misong-text-key" or type(data["version"]) is not int
            or data["version"] != 1):
        _fail()
    _parse_recipe(data["recipe"])
    layers, receipts = data["recipe"]["layers"], data["receipts"]
    if type(receipts) is not list or len(receipts) != len(layers):
        _fail()
    _digest(data["original_sha256"])
    _digest(data["payload_sha256"])
    previous = data["original_sha256"]
    for layer, receipt in zip(layers, receipts):
        _fields(receipt, _RECEIPT_FIELDS)
        _digest(receipt["input_sha256"])
        _digest(receipt["output_sha256"])
        if (receipt["layer_id"] != layer["id"] or receipt["input_sha256"] != previous
                or type(receipt["characters"]) is not int
                or type(receipt["utf8_bytes"]) is not int
                or not 0 <= receipt["characters"] <= receipt["utf8_bytes"] <= MAX_TEXT_BYTES
                or receipt["utf8_bytes"] > 4 * receipt["characters"]):
            _fail()
        previous = receipt["output_sha256"]
    if previous != data["payload_sha256"]:
        _fail()
    values = data["secrets"]
    if (type(values) is not dict or values.keys() != _slots(data["recipe"])
            or any(type(v) is not str for v in values.values())):
        _fail()
    return data


def build_payload(recipe: DeliveryRecipe, result: PipelineResult,
                  context: OperationContext) -> dict:
    """Build only in memory. This never implicitly exports a key file."""
    context.check()
    code = None
    try:
        public = recipe.to_dict()
        _parse_recipe(public)
        digest = text_digest(result.text)
        if len(result.text.encode("utf-8")) > MAX_TEXT_BYTES:
            _fail(ErrorCode.CAPACITY)
        receipts = [{
            "layer_id": r.layer_id, "input_sha256": r.input_sha256,
            "output_sha256": r.output_sha256, "characters": r.characters,
            "utf8_bytes": r.utf8_bytes,
        } for r in result.receipts]
        payload = validate({
            "type": "misong-text-key", "version": 1, "recipe": public,
            "receipts": receipts,
            "original_sha256": receipts[0]["input_sha256"] if receipts else digest,
            "payload_sha256": digest,
            "secrets": {slot: context.secrets.require(slot) for slot in _slots(public)},
        })
        if receipts and (receipts[-1]["characters"] != len(result.text)
                         or receipts[-1]["utf8_bytes"] != len(result.text.encode("utf-8"))):
            _fail(ErrorCode.INTEGRITY)
    except TextOperationError as error:
        code = error.code
    except Exception:
        code = ErrorCode.INVALID_RECIPE
    if code is not None:
        _fail(code)
    context.check()
    return payload


def write(path: Path, payload: dict) -> Path:
    """Explicit sensitive export. Refuse existing destinations (including links).

    Exclusive creation avoids a replacement race. A failed/short write removes
    only this newly created file; no usable half-key remains after failure.
    """
    plain = _json_bytes(validate(payload))
    key, nonce = secrets.token_bytes(32), secrets.token_bytes(12)
    header = MAGIC + key + nonce
    data = header + AESGCM(key).encrypt(nonce, plain, header)
    created, complete, code = False, False, None
    try:
        path = Path(path)
        with path.open("xb") as fh:
            created = True
            if fh.write(data) != len(data):
                raise OSError()
            fh.flush()
        complete = True
    except (OSError, ValueError, TypeError):
        code = ErrorCode.IO
    finally:
        if created and not complete:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                code = ErrorCode.IO
    if code is not None:
        _fail(code)
    return path


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def read(path: Path) -> dict:
    """Read by magic, authenticate and strictly validate; never log contents."""
    code = None
    try:
        with Path(path).open("rb") as fh:
            data = fh.read(MAX_SIZE + 1)
    except (OSError, ValueError, TypeError):
        code = ErrorCode.IO
    if code is not None:
        _fail(code)
    if (len(data) > MAX_SIZE or len(data) < _HEADER_SIZE + 16
            or not data.startswith(MAGIC)):
        _fail(ErrorCode.INTEGRITY)
    try:
        header = data[:_HEADER_SIZE]
        key = header[len(MAGIC):len(MAGIC) + 32]
        plain = AESGCM(key).decrypt(header[-12:], data[_HEADER_SIZE:], header)
        payload = json.loads(plain.decode("utf-8"), object_pairs_hook=_unique_object)
    except (InvalidTag, ValueError, TypeError, UnicodeError, RecursionError):
        code = ErrorCode.INTEGRITY
    if code is not None:
        _fail(code)
    return validate(payload)
