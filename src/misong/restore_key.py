"""Portable bearer restore keys. Possession of this file grants decryption.

The per-file wrapping key travels inside the envelope: this hides plain-text
password lists and detects accidental corruption, not a hostile file holder.
Never put this payload in task JSON, settings, diagnostics or logs.
"""
from __future__ import annotations

import copy
import json
import re
import secrets
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

EXT = ".mskey"
MAGIC = b"MISONGKEY\x00\x01"
MAX_SIZE = 4 * 1024 * 1024


def sidecar(artifact: Path) -> Path:
    return Path(artifact).with_name(Path(artifact).name + EXT)


def _name(value):
    if (not isinstance(value, str) or not value or len(value) > 255 or
            value in (".", "..") or value.endswith((".", " ")) or
            re.search(r'[<>:"/\\|?*\x00-\x1f]', value) or
            re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", value)):
        raise ValueError("还原钥匙包含不安全的文件名")


def _record(rec):
    if not isinstance(rec, dict):
        raise ValueError("还原钥匙的文件记录无效")
    _name(rec.get("name"))
    if (type(rec.get("size")) is not int or rec["size"] < 0 or
            not re.fullmatch(r"[0-9a-f]{64}", str(rec.get("sha256", "")))):
        raise ValueError("还原钥匙的文件校验信息无效")


def validate(payload):
    """Validate all names used as extraction destinations before touching files."""
    from . import formats
    if not isinstance(payload, dict) or type(payload.get("version")) is not int or payload["version"] != 1:
        raise ValueError("不支持的还原钥匙版本")
    mf, passwords = payload.get("manifest"), payload.get("passwords")
    if not isinstance(mf, dict) or mf.get("version") != 2:
        raise ValueError("还原钥匙缺少完整层清单")
    _name(mf.get("artifact"))
    artifacts, layers = mf.get("artifacts"), mf.get("layers")
    if (not isinstance(artifacts, list) or not 1 <= len(artifacts) <= 100000 or
            not isinstance(layers, list) or not 1 <= len(layers) <= 128 or
            not isinstance(passwords, list) or len(passwords) != len(layers)):
        raise ValueError("还原钥匙的层序或文件数量无效")
    for rec in artifacts:
        _record(rec)
    if len({r["name"].casefold() for r in artifacts}) != len(artifacts):
        raise ValueError("还原钥匙包含重复文件名")
    for rec, password in zip(layers, passwords):
        if (not isinstance(rec, dict) or rec.get("type") not in ("archive", "cover", "split", "rename") or
                password is not None and (not isinstance(password, str) or len(password) > 8192)):
            raise ValueError("还原钥匙的层记录无效")
        names = rec.get("input_names")
        if not isinstance(names, list) or not names:
            raise ValueError("还原钥匙缺少层文件名")
        for name in names:
            _name(name)
        if rec["type"] == "archive":
            if not isinstance(rec.get("format"), str) or type(rec.get("password")) is not bool:
                raise ValueError("还原钥匙的归档层无效")
            fmt = formats.get(rec["format"])
            if bool(rec.get("password")) != bool(password) or password and not fmt.supports_password:
                raise ValueError("还原钥匙缺少所需的层密码")
        elif password is not None:
            raise ValueError("还原钥匙的非归档层不能含密码")
        if rec["type"] == "split":
            sm = rec.get("split_manifest")
            if not isinstance(sm, dict) or not isinstance(sm.get("parts"), list) or not sm["parts"]:
                raise ValueError("还原钥匙缺少分卷清单")
            _name(sm.get("source"))
            if (type(sm.get("part_count")) is not int or sm["part_count"] != len(sm["parts"]) or
                    not re.fullmatch(r"[0-9a-f]{64}", str(sm.get("source_sha256", "")))):
                raise ValueError("还原钥匙的分卷校验信息无效")
            for part in sm["parts"]:
                _record(part)
            if len({r["name"].casefold() for r in sm["parts"]}) != len(sm["parts"]):
                raise ValueError("还原钥匙包含重复分卷名")
    return payload


def write(path: Path, manifest: dict, passwords: list[str | None]) -> Path:
    """Explicit export only. No human passwords or local video paths in clear text."""
    mf = copy.deepcopy(manifest)
    for layer in mf["layers"]:
        # Only retain fields used by the inverse engine, never a local cover path.
        for field in list(layer):
            if field not in ("type", "format", "password", "input_names", "tar_pre", "split_manifest"):
                layer.pop(field)
    payload = validate({"version": 1, "manifest": mf, "passwords": passwords})
    plain = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    key, nonce = secrets.token_bytes(32), secrets.token_bytes(12)
    header = MAGIC + key + nonce
    data = header + AESGCM(key).encrypt(nonce, plain, header)
    if len(data) > MAX_SIZE:
        raise ValueError("还原钥匙过大，请减少分卷或层数")
    path = Path(path)
    # Never replace an existing key or follow a destination symlink.
    with path.open("xb") as fh:
        fh.write(data)
    return path


def read(path: Path) -> dict:
    with Path(path).open("rb") as fh:
        data = fh.read(MAX_SIZE + 1)
    size = len(MAGIC) + 32 + 12
    if len(data) > MAX_SIZE or len(data) < size + 16 or not data.startswith(MAGIC):
        raise ValueError("不是受支持的 .mskey 还原钥匙，或文件已损坏")
    try:
        header = data[:size]
        plain = AESGCM(data[len(MAGIC):len(MAGIC) + 32]).decrypt(data[size - 12:size], data[size:], header)
        payload = json.loads(plain)
    except (InvalidTag, UnicodeError, ValueError, RecursionError):
        raise ValueError("还原钥匙已损坏，无法读取") from None
    try:
        return validate(payload)
    except (KeyError, TypeError, RecursionError):
        raise ValueError("还原钥匙结构无效") from None
