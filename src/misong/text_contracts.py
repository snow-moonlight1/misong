"""Shared runtime contracts for text delivery; not a persistence format.

Never serialize these runtime objects with vars/asdict/pickle. Only the recipe
allowlist (owned by text_layers) may enter ordinary task/settings JSON.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Mapping, Protocol


class ErrorCode(str, Enum):
    INVALID_RECIPE = "invalid_recipe"
    UNSUPPORTED = "unsupported"
    CAPACITY = "capacity"
    MISSING_SECRET = "missing_secret"
    WRONG_PASSWORD = "wrong_password"
    INTEGRITY = "integrity"
    MEDIA = "media"
    NETWORK = "network"
    PAGE_CHANGED = "page_changed"
    DOWNLOAD = "download"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    IO = "io"


class TextOperationError(ValueError):
    """Safe machine-readable failure. Do not pass website/decoder messages."""

    def __init__(self, code: ErrorCode):
        self.code = ErrorCode(code)
        super().__init__(self.code.value)


def text_digest(text: str) -> str:
    """SHA-256 of exact UTF-8; preserve whitespace and Unicode representation."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class RuntimeSecrets:
    """Per-operation secrets; explicit lookup, no public serialization API."""

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[str, str] | None = None):
        self._values = dict(values or {})
        if any(not isinstance(k, str) or not k or not isinstance(v, str)
               for k, v in self._values.items()):
            raise TextOperationError(ErrorCode.INVALID_RECIPE)

    def __repr__(self) -> str:
        return "RuntimeSecrets(<redacted>)"

    def require(self, slot: str) -> str:
        if slot not in self._values:
            raise TextOperationError(ErrorCode.MISSING_SECRET)
        return self._values[slot]

    def clear(self) -> None:
        """Drop references after operation; not a guarantee of memory erasure."""
        self._values.clear()


class CancelSignal(Protocol):
    def is_set(self) -> bool: ...


class Stage(str, Enum):
    PREFLIGHT = "preflight"
    TEXT_ENCODE = "text_encode"
    TEXT_DECODE = "text_decode"
    CARRIER_ENCODE = "carrier_encode"
    CARRIER_DECODE = "carrier_decode"
    VERIFY = "verify"
    KEY_EXPORT = "key_export"


@dataclass(frozen=True)
class Progress:
    stage: Stage
    completed: int = 0
    total: int | None = None

    def __post_init__(self):
        if (not isinstance(self.stage, Stage) or type(self.completed) is not int
                or self.completed < 0 or self.total is not None
                and (type(self.total) is not int or self.total < self.completed)):
            raise TextOperationError(ErrorCode.INVALID_RECIPE)


@dataclass(frozen=True)
class OperationContext:
    secrets: RuntimeSecrets = field(default_factory=RuntimeSecrets, repr=False)
    cancel: CancelSignal | None = field(default=None, repr=False)
    deadline: float | None = None  # absolute time.monotonic(), never persisted
    notify: Callable[[Progress], None] | None = field(default=None, repr=False)

    def check(self) -> None:
        if self.cancel is not None and self.cancel.is_set():
            raise TextOperationError(ErrorCode.CANCELLED)
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise TextOperationError(ErrorCode.TIMEOUT)

    def report(self, stage: Stage, completed: int = 0, total: int | None = None) -> None:
        self.check()
        event = Progress(stage, completed, total)
        if self.notify is not None:
            self.notify(event)


@dataclass(frozen=True)
class LayerReceipt:
    layer_id: str
    input_sha256: str
    output_sha256: str
    characters: int  # output code points, not UTF-8 bytes
    utf8_bytes: int


@dataclass(frozen=True)
class PipelineResult:
    text: str = field(repr=False)
    receipts: tuple[LayerReceipt, ...] = ()

