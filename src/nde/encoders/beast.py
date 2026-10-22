"""兽音译者 (beast) compatible codec, pure python.

Algorithm (from SycAlright/beast_sdk, verified against its official samples):
  plain char -> 4-hex-digit unicode code units (BMP only, UTF-16 code units)
  each hex nibble at position i -> k = (nibble + i) % 16 -> beast[k//4]+beast[k%2]
  dictionary is any 4 distinct chars; index order = given order.

Two wire dialects exist in the wild:
  sdk: raw nibble pairs only
  web: "~呜嗷" + sdk_payload + "啊"   (dict[3] dict[1] dict[0] ... dict[2])
       offsets restart at 0 after the 3-char header.
Decode auto-detects; encode defaults to web (what 兽音译者 app/tools speak).
"""

from __future__ import annotations

DEFAULT_DICT = ("嗷", "呜", "啊", "~")


def _validate_dict(chars: tuple[str, ...] | list[str] | str) -> tuple[str, ...]:
    if isinstance(chars, str):
        chars = tuple(chars)
    chars = tuple(chars)
    if len(chars) != 4 or len(set(chars)) != 4:
        raise ValueError("编码字符必须是 4 个互不重复的字符")
    return chars


def _to_utf16_units(text: str) -> list[int]:
    raw = text.encode("utf-16-le", "surrogatepass")
    return [raw[i] | (raw[i + 1] << 8) for i in range(0, len(raw), 2)]


def _from_utf16_units(units: list[int]) -> str:
    s = "".join(chr(u if 0 <= u <= 0xFFFF else 0x3F) for u in units)
    try:
        return s.encode("utf-16-le", "surrogatepass").decode("utf-16-le")
    except UnicodeDecodeError:
        return s


def _str2hex(text: str) -> str:
    return "".join(f"{u:04x}" for u in _to_utf16_units(text))


def _encode_payload(payload: str, d: tuple[str, ...]) -> str:
    code = []
    for i, x in enumerate(payload):
        k = (int(x, 16) + i) % 16
        code.append(d[k // 4])
        code.append(d[k % 4])
    return "".join(code)


def _decode_payload(cipher: str, d: tuple[str, ...]) -> str:
    if len(cipher) % 2:
        raise ValueError("密文长度不是偶数，可能缺少/多余字符")
    hexes = []
    for i in range(0, len(cipher), 2):
        try:
            p1 = d.index(cipher[i])
            p2 = d.index(cipher[i + 1])
        except ValueError:
            raise ValueError(f"第 {i} 位字符 {cipher[i]!r}{cipher[i+1]!r} 不在编码字符集内")
        k = ((p1 * 4) + p2 - (i // 2) % 16) % 16
        hexes.append(format(k, "x"))
    joined = "".join(hexes)
    units = [int(joined[i:i + 4], 16) for i in range(0, len(joined), 4)]
    return _from_utf16_units(units)


def _encode_pojie(text: str, d: tuple[str, ...]) -> str:
    """52pojie offline variant: header dict[3]dict[1]dict[0], per-16bit-nibble
    of charCode with a single global incrementing offset, footer dict[2].
    (Official app's own dictionary is 嗷呜喵~ in that dialect.)"""
    res = [d[3], d[1], d[0]]
    off = 0
    for c in text:
        v = ord(c) & 0xFFFF
        for b in (12, 8, 4, 0):
            hexv = (((v >> b) & 15) + off) & 15
            res.append(d[hexv >> 2])
            res.append(d[hexv & 3])
            off += 1
    res.append(d[2])
    return "".join(res)


def _decode_pojie(cipher: str, d: tuple[str, ...]) -> str:
    body = cipher[3:-1]
    if len(body) % 8:
        raise ValueError("pojie 方言密文长度不符")
    out = []
    off = 0
    for i in range(0, len(body), 8):
        code = 0
        for j in range(4):
            p1 = d.index(body[i + j * 2])
            p2 = d.index(body[i + j * 2 + 1])
            h = ((p1 * 4) + p2 - off) % 16
            off += 1
            code = (code << 4) | h
        out.append(code)
    return _from_utf16_units(out)


def encode(text: str, chars=DEFAULT_DICT, dialect: str = "web") -> str:
    d = _validate_dict(chars)
    if dialect == "auto":
        dialect = "web"
    if dialect == "pojie":
        return _encode_pojie(text, d)
    payload = _encode_payload(_str2hex(text), d)
    if dialect == "sdk":
        return payload
    if dialect == "web":
        return d[3] + d[1] + d[0] + payload + d[2]
    raise ValueError(f"未知方言: {dialect}")


def decode(cipher: str, chars=DEFAULT_DICT, dialect: str = "auto") -> str:
    d = _validate_dict(chars)
    cipher = "".join(cipher.split())  # tolerate whitespace between groups
    header = d[3] + d[1] + d[0]
    if dialect in ("auto", "web", "pojie") and cipher.startswith(header) and len(cipher) >= 4:
        if dialect in ("auto", "pojie") and cipher.endswith(d[2]) and (len(cipher) - 4) % 8 == 0:
            try:
                return _decode_pojie(cipher, d)
            except ValueError:
                if dialect == "pojie":
                    raise
        if dialect in ("auto", "web"):
            payload = cipher[3:-1] if cipher.endswith(d[2]) else cipher[3:]
            if len(payload) % 2 == 0:
                return _decode_payload(payload, d)
    if dialect in ("auto", "sdk"):
        return _decode_payload(cipher, d)
    raise ValueError("方言不匹配")
