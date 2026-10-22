"""Plain link-obfuscation schemes collected from resource-sharing practice.

These are encoding/obfuscation (not encryption). They dodge naive text
filters and keyword scanners; none of them protects file contents — that is
what the nested archive layers are for.
"""

from __future__ import annotations

import base64
import binascii
import urllib.parse

MASK = "⚠️屏蔽词勿删⚠️"  # arbitrary filler used by the trunc(截断法) scheme


def b64(t: str) -> str:
    return base64.b64encode(t.encode("utf-8")).decode("ascii")


def b64d(t: str) -> str:
    return base64.b64decode(t.strip().encode("ascii")).decode("utf-8")


def b64u(t: str) -> str:
    return base64.urlsafe_b64encode(t.encode("utf-8")).decode("ascii")


def b64ud(t: str) -> str:
    return base64.urlsafe_b64decode(t.strip().encode("ascii")).decode("utf-8")


def b32(t: str) -> str:
    return base64.b32encode(t.encode("utf-8")).decode("ascii")


def b32d(t: str) -> str:
    return base64.b32decode(t.strip().encode("ascii")).decode("utf-8")


def b85(t: str) -> str:
    return base64.b85encode(t.encode("utf-8")).decode("ascii")


def b85d(t: str) -> str:
    return base64.b85decode(t.strip().encode("ascii")).decode("utf-8")


def hexc(t: str) -> str:
    return t.encode("utf-8").hex()


def hexd(t: str) -> str:
    return bytes.fromhex("".join(t.split())).decode("utf-8")


def urlenc(t: str) -> str:
    return urllib.parse.quote(t, safe="")


def urllibd(t: str) -> str:
    return urllib.parse.unquote(t.strip())


def reverse(t: str) -> str:
    return t[::-1]


def rot13(t: str) -> str:
    import codecs
    return codecs.decode(t, "rot_13")


def trunc(t: str, mask: str = MASK) -> str:
    """截断法: keep head/tail of the link, replace the middle with filler text.
    Receiver must know the platform to reassemble: e.g. https://pan.baidu.com/
    + <middle> + ?pwd=xxxx."""
    if len(t) <= 12:
        raise ValueError("链接太短，截断法无意义")
    return t[:8] + mask + t[-10:]


def truncd(t: str, mask: str = MASK) -> str:
    if mask not in t:
        raise ValueError(f"密文中没有掩码 {mask}；截断法解码需提供原始掩码")
    head, rest = t.split(mask, 1)
    return head + rest  # middle must be supplied separately by the sharer


SCHEMES = {
    "base64": (b64, b64d),
    "base64url": (b64u, b64ud),
    "base32": (b32, b32d),
    "base85": (b85, b85d),
    "hex": (hexc, hexd),
    "url": (urlenc, urllibd),
    "reverse": (reverse, reverse),
    "rot13": (rot13, rot13),
    "trunc": (trunc, truncd),
}


def encode(scheme: str, text: str) -> str:
    if scheme not in SCHEMES:
        raise KeyError(f"未知方案 {scheme}; 可选: {', '.join(SCHEMES)}")
    return SCHEMES[scheme][0](text)


def decode(scheme: str, cipher: str) -> str:
    if scheme not in SCHEMES:
        raise KeyError(f"未知方案 {scheme}; 可选: {', '.join(SCHEMES)}")
    return SCHEMES[scheme][1](cipher)
