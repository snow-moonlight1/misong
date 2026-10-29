"""Immutable, public text recipes. Runtime secrets never belong in this model."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from .text_contracts import ErrorCode, TextOperationError

MAX_TEXT_LAYERS = 32
MAX_RECIPES = 16
MAX_TEXT_BYTES = 1024 * 1024
TEXT_SCHEMES = (
    "beast", "mojibake", "hajimi", "base64", "base64url", "base32",
    "base85", "hex", "url", "reverse", "rot13",
)
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_SLOT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,255}\Z")


def _invalid() -> None:
    raise TextOperationError(ErrorCode.INVALID_RECIPE)


def _identifier(value: str, *, slot: bool = False) -> None:
    if not isinstance(value, str) or not (_SLOT if slot else _ID).fullmatch(value):
        _invalid()


def _version(value: int) -> None:
    if type(value) is not int or value != 1:
        _invalid()


def _fields(data: dict, names: tuple[str, ...]) -> None:
    if not isinstance(data, dict) or set(data) != set(names):
        _invalid()


def _params(params: Mapping, scheme: str) -> Mapping:
    if not isinstance(params, Mapping):
        _invalid()
    allowed = {"dialect", "chars"} if scheme == "beast" else {"mode"} if scheme == "mojibake" else set()
    if set(params) - allowed:
        _invalid()
    copied = dict(params)
    if scheme == "beast":
        if "dialect" in copied and (not isinstance(copied["dialect"], str)
                                    or copied["dialect"] not in ("auto", "web", "sdk", "pojie")):
            _invalid()
        if "chars" in copied:
            chars = copied["chars"]
            if not isinstance(chars, (str, list, tuple)) or len(chars) != 4:
                _invalid()
            # The existing decoder removes whitespace. Such dictionaries cannot
            # round-trip, so do not accept them as reversible recipe parameters.
            if any(not isinstance(c, str) or len(c) != 1 or c.isspace()
                   or 0xD800 <= ord(c) <= 0xDFFF for c in chars):
                _invalid()
            if len(set(chars)) != 4:
                _invalid()
            copied["chars"] = chars if isinstance(chars, str) else tuple(chars)
    elif scheme == "mojibake":
        if "mode" in copied and (not isinstance(copied["mode"], str)
                                 or copied["mode"] not in ("wenyan", "old")):
            _invalid()
    return MappingProxyType(copied)


def _public_params(params: Mapping) -> dict:
    return {key: list(value) if isinstance(value, tuple) else value
            for key, value in params.items()}


@dataclass(frozen=True)
class TextLayer:
    id: str
    scheme: str
    version: int = 1
    params: Mapping = field(default_factory=dict)
    secret_slot: str | None = None

    def __post_init__(self):
        _identifier(self.id)
        _version(self.version)
        if not isinstance(self.scheme, str) or self.scheme not in TEXT_SCHEMES:
            _invalid()
        if self.secret_slot is not None:
            _identifier(self.secret_slot, slot=True)
            if self.scheme != "mojibake":
                _invalid()
        object.__setattr__(self, "params", _params(self.params, self.scheme))

    @classmethod
    def from_dict(cls, data: dict) -> TextLayer:
        _fields(data, ("id", "scheme", "version", "params", "secret_slot"))
        return cls(**data)

    def to_dict(self) -> dict:
        return {"id": self.id, "scheme": self.scheme, "version": self.version,
                "params": _public_params(self.params), "secret_slot": self.secret_slot}


@dataclass(frozen=True)
class CarrierSpec:
    format_id: str = "text"
    version: int = 1
    mode: str = "plain"
    params: Mapping = field(default_factory=dict)
    secret_slot: str | None = None

    def __post_init__(self):
        _version(self.version)
        if (self.format_id, self.mode) not in (("text", "plain"), ("framewords", "standard")):
            _invalid()
        object.__setattr__(self, "params", _params(self.params, "carrier"))
        if self.secret_slot is not None:
            _identifier(self.secret_slot, slot=True)
            if self.format_id == "text":
                _invalid()

    @classmethod
    def from_dict(cls, data: dict) -> CarrierSpec:
        _fields(data, ("format_id", "version", "mode", "params", "secret_slot"))
        return cls(**data)

    def to_dict(self) -> dict:
        return {"format_id": self.format_id, "version": self.version, "mode": self.mode,
                "params": _public_params(self.params), "secret_slot": self.secret_slot}


@dataclass(frozen=True)
class DeliveryRecipe:
    version: int
    id: str
    name: str
    layers: tuple[TextLayer, ...] = ()
    carrier: CarrierSpec = field(default_factory=CarrierSpec)

    def __post_init__(self):
        _version(self.version)
        _identifier(self.id)
        if (not isinstance(self.name, str) or not self.name.strip()
                or len(self.name) > 128
                or any(0xD800 <= ord(c) <= 0xDFFF for c in self.name)):
            _invalid()
        if not isinstance(self.layers, (list, tuple)):
            _invalid()
        if len(self.layers) > MAX_TEXT_LAYERS:
            raise TextOperationError(ErrorCode.CAPACITY)
        layers = tuple(self.layers)
        if any(not isinstance(layer, TextLayer) for layer in layers):
            _invalid()
        if len({layer.id for layer in layers}) != len(layers):
            _invalid()
        if not isinstance(self.carrier, CarrierSpec):
            _invalid()
        slots = [layer.secret_slot for layer in layers if layer.secret_slot is not None]
        if self.carrier.secret_slot is not None:
            slots.append(self.carrier.secret_slot)
        if len(slots) != len(set(slots)):
            _invalid()
        object.__setattr__(self, "layers", layers)

    @classmethod
    def from_dict(cls, data: dict) -> DeliveryRecipe:
        _fields(data, ("version", "id", "name", "layers", "carrier"))
        if not isinstance(data["layers"], list):
            _invalid()
        if len(data["layers"]) > MAX_TEXT_LAYERS:
            raise TextOperationError(ErrorCode.CAPACITY)
        return cls(version=data["version"], id=data["id"], name=data["name"],
                   layers=tuple(TextLayer.from_dict(layer) for layer in data["layers"]),
                   carrier=CarrierSpec.from_dict(data["carrier"]))

    def to_dict(self) -> dict:
        return {"version": self.version, "id": self.id, "name": self.name,
                "layers": [layer.to_dict() for layer in self.layers],
                "carrier": self.carrier.to_dict()}


def validate_recipes(recipes: list[DeliveryRecipe] | tuple[DeliveryRecipe, ...]) -> tuple[DeliveryRecipe, ...]:
    """Validate a task's recipe count, IDs and globally unique secret slots."""
    if not isinstance(recipes, (list, tuple)):
        _invalid()
    if len(recipes) > MAX_RECIPES:
        raise TextOperationError(ErrorCode.CAPACITY)
    ids, slots = set(), set()
    for recipe in recipes:
        if not isinstance(recipe, DeliveryRecipe) or recipe.id in ids:
            _invalid()
        ids.add(recipe.id)
        for item in (*recipe.layers, recipe.carrier):
            if item.secret_slot is not None:
                if item.secret_slot in slots:
                    _invalid()
                slots.add(item.secret_slot)
    return tuple(recipes)


def recipes_from_schemes(schemes: list[str] | tuple[str, ...]) -> tuple[DeliveryRecipe, ...]:
    """Migrate old parallel selections, never turning them into a serial chain.

    Empty selections stay empty (write_copy still writes share-plain.txt).
    A custom legacy mojibake key is supplied at runtime as legacy-mojibake/text.
    Export selection is deliberately absent from the public recipe contract.
    """
    if not isinstance(schemes, (list, tuple)):
        _invalid()
    if len(schemes) > MAX_RECIPES:
        raise TextOperationError(ErrorCode.CAPACITY)
    recipes, seen = [], set()
    for scheme in schemes:
        if not isinstance(scheme, str) or scheme not in TEXT_SCHEMES:
            _invalid()
        if scheme in seen:
            continue
        seen.add(scheme)
        recipe_id = f"legacy-{scheme}"
        layer = TextLayer("text", scheme,
                          secret_slot=f"{recipe_id}/text" if scheme == "mojibake" else None)
        recipes.append(DeliveryRecipe(1, recipe_id, scheme, (layer,)))
    return validate_recipes(recipes)
