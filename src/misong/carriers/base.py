"""Backend-neutral video carrier boundary; no website/browser imports here."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..text_contracts import (
    ErrorCode, OperationContext, Stage, TextOperationError, text_digest,
)


@dataclass(frozen=True)
class CarrierCapabilities:
    format_id: str
    backend_id: str
    modes: tuple[str, ...] = ()  # empty until implemented and verified
    can_encode: bool = False
    can_decode: bool = False
    supports_password: bool = False
    requires_network: bool = True
    max_characters: int | None = None
    max_utf8_bytes: int | None = None
    verified_versions: tuple[str, ...] = ()


@dataclass(frozen=True)
class EncodeRequest:
    source: Path = field(repr=False)
    destination: Path = field(repr=False)
    text: str = field(repr=False)
    mode: str = "standard"
    password: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class DecodeRequest:
    source: Path = field(repr=False)
    mode: str = "standard"
    password: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class DecodedText:
    text: str = field(repr=False)

    @property
    def sha256(self) -> str:
        return text_digest(self.text)


@dataclass(frozen=True)
class EncodedVideo:
    path: Path = field(repr=False)
    payload_sha256: str
    verified: bool  # true only after independent saved-file decode


class VideoCarrier(Protocol):
    def capabilities(self) -> CarrierCapabilities: ...

    async def encode(self, request: EncodeRequest, context: OperationContext) -> EncodedVideo: ...

    async def decode(self, request: DecodeRequest, context: OperationContext) -> DecodedText: ...

    async def verify(
        self, request: DecodeRequest, expected_text: str, context: OperationContext,
    ) -> DecodedText: ...


async def verify_saved_video(
    carrier: VideoCarrier, request: DecodeRequest, expected_text: str,
    context: OperationContext,
) -> DecodedText:
    """Read the actual saved file, then compare exact text before success.

    The backend's decode must create an independent reading operation, not
    return cached encoder input. Backend failures propagate without partial text.
    """
    context.report(Stage.VERIFY)
    result = await carrier.decode(request, context)
    context.check()
    if result.text != expected_text:
        raise TextOperationError(ErrorCode.INTEGRITY)
    return result

