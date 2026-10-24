"""哈基米语 (hajimi "南北绿豆") codec, faithful python port of
Starpuccino/hachimi-wonameruto-translator (Svelte/TS).

Payload pipeline: utf8 + fnv1a checksum -> gzip -> 10-bit chunks ->
(+salt mod 1024) -> tokens from a 1024-entry template table; random salt
makes each encoding unique (decode is deterministic).

Interoperability is validated against the vendored JS reference in tests.

Portions translated from hachimi-wonameruto-translator,
Copyright (c) 2025 Starpuccino, MIT License (full text in
THIRD_PARTY_NOTICES.md). This file as a whole is distributed under
GPL-3.0-or-later together with the rest of MISONG.
"""

from __future__ import annotations

import gzip
import random
import re
from dataclasses import dataclass

RADIX = 1024
HEADER_SCALE = 16
SALT_RANGE = 64

BASE_WORDS = ["哈基米", "南北绿豆", "阿西嘎", "哈亚库", "哈亚库纳咯", "曼波",
              "曼波波波", "哦玛吉利", "大狗叫", "没有", "蛋蛋", "叮咚鸡",
              "叮叮咚咚", "奶龙", "哦么吉利", "哈呀库", "哦耶", "内个"]
LEAD_BASES = ["哈基米", "南北绿豆", "曼波"]
ONOMATOPOEIA = ["啊", "哦", "呀", "呵", "耶", "喵", "诶", "叫", "噔",
                "duang", "leg", "mua", "miao"]
SYMBOLS = ["♪", "♫", "♬", "♩", "♭", "♮", "♯", "#", "↗", "↘", "↑", "↓",
           "→", "~", "~~", "。", ",", "!", "?", "…", "·", "★", "☆", "❤",
           "𝄞", "𝄢", "𝄡"]
EMOJIS = ["🐈", "😻", "🐱", "🐈\u200d⬛", "😺", "😸", "😹", "😼", "😽",
          "🙀", "😿", "😾"]
KAOMOJIS = ["≧▽≦", "＾▽＾", "￣▽￣", "•‿•", "◠‿◠", "♥‿♥", "¬‿¬", "ʘ‿ʘ",
            "•ω•", "◕‿◕", "≧◡≦", "･ω･", "ʕ•ᴥ•ʔ"]

BASE_COUNT = len(BASE_WORDS)
DEFAULT_WEIGHTS = {"base": 5.0, "onomat": 5.0, "symbol": 1.0, "emoji": 0.5,
                   "kaomoji": 0.2}

ERR_MSG = "喵！你在狗叫什么！！！😾😾😾"


@dataclass(frozen=True)
class Variant:
    onomat: int | None
    emoji: int | None
    symbol: int | None
    kaomoji: int | None


class HajimiError(ValueError):
    pass


def _fnv1a(b: bytes) -> int:
    h = 0x811C9DC5
    for byte in b:
        h ^= byte
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def _pack_payload(text: str) -> bytes:
    body = text.encode("utf-8")
    cs = _fnv1a(body)
    return body + bytes([(cs >> 24) & 255, (cs >> 16) & 255, (cs >> 8) & 255, cs & 255])


def _unpack_payload(payload: bytes) -> str:
    if len(payload) < 4:
        raise HajimiError("payload too short")
    body, cs = payload[:-4], int.from_bytes(payload[-4:], "big")
    if _fnv1a(body) != cs:
        raise HajimiError("checksum mismatch")
    return body.decode("utf-8")


def _gzip(data: bytes) -> bytes:
    out = gzip.compress(data, compresslevel=9, mtime=0)
    # JS reference (fflate) writes OS byte 0x03; its decode self-check re-gzips
    # and compares bytes, including CRC32 over the header. Match it exactly.
    if len(out) > 9:
        out = out[:9] + b"\x03" + out[10:]
    return out


def _chunkify(data: bytes) -> tuple[list[int], int]:
    buf = 0
    bits = 0
    chunks: list[int] = []
    for byte in data:
        buf = (buf << 8) | byte
        bits += 8
        while bits >= 10:
            bits -= 10
            chunks.append((buf >> bits) & 0x3FF)
            buf &= (1 << bits) - 1
    tail = bits
    if bits > 0:
        chunks.append((buf << (10 - bits)) & 0x3FF)
    return chunks, tail


def _unchunkify(chunks: list[int], tail_bits: int) -> bytes:
    if not chunks:
        return b""
    out = bytearray()
    buf = 0
    bits = 0
    last = len(chunks) - 1
    for idx, chunk in enumerate(chunks):
        value, width = chunk, 10
        if idx == last and 0 < tail_bits < 10:
            value >>= 10 - tail_bits
            width = tail_bits
        buf = (buf << width) | value
        bits += width
        while bits >= 8:
            bits -= 8
            out.append((buf >> bits) & 0xFF)
            buf &= (1 << bits) - 1
    if bits != 0:
        raise HajimiError("dangling bits")
    return bytes(out)


def _sig(v: Variant) -> tuple:
    return (v.onomat if v.onomat is not None else "x",
            v.emoji if v.emoji is not None else "x",
            v.symbol if v.symbol is not None else "x",
            v.kaomoji if v.kaomoji is not None else "x")


def build_templates(weights: dict | None = None) -> list[Variant]:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    if w["base"] <= 0:
        w["base"] = DEFAULT_WEIGHTS["base"]
    combos = -(-RADIX // BASE_COUNT)  # ceil

    def ratio(val: float) -> float:
        if val <= 0 or w["base"] <= 0:
            return 0.0
        return min(1.0, val / w["base"])

    targets = {
        "onomat": min(combos, round(combos * ratio(w["onomat"]))),
        "symbol": min(combos, round(combos * ratio(w["symbol"]))),
        "emoji": min(combos, round(combos * ratio(w["emoji"]))),
        "kaomoji": min(combos, round(combos * ratio(w["kaomoji"]))),
    }
    templates = [Variant(None, None, None, None) for _ in range(combos)]

    def field(v: Variant, key: str):
        return getattr(v, {"onomat": "onomat", "symbol": "symbol",
                           "emoji": "emoji", "kaomoji": "kaomoji"}[key])

    def with_field(v: Variant, key: str, val):
        return dataclass_replace(v, **{key: val})

    def distribute(key: str, count: int, pool_len: int):
        if count <= 0 or pool_len == 0:
            return
        step = len(templates) / count
        cursor = 0.0
        for assigned in range(count):
            preferred = min(len(templates) - 1, int(cursor))
            slot = _find_available(templates, preferred, key)
            templates[slot] = with_field(templates[slot], key, assigned % pool_len)
            cursor += step

    distribute("onomat", targets["onomat"], len(ONOMATOPOEIA))
    distribute("symbol", targets["symbol"], len(SYMBOLS))
    distribute("emoji", targets["emoji"], len(EMOJIS))
    distribute("kaomoji", targets["kaomoji"], len(KAOMOJIS))

    # dedup pass (same order as reference impl)
    used: set[tuple] = set()
    for index, tmpl in enumerate(templates):
        s = _sig(tmpl)
        if s not in used:
            used.add(s)
            continue
        s2 = _force_unique(templates, index, used)
        used.add(s2)
    return templates


def _find_available(templates: list[Variant], start: int, key: str) -> int:
    n = len(templates)
    for off in range(n):
        idx = (start + off) % n
        if field_is_none(templates[idx], key):
            return idx
    return start % n


def field_is_none(v: Variant, key: str) -> bool:
    return getattr(v, key) is None


def dataclass_replace(v: Variant, **kw) -> Variant:
    return Variant(**{**{"onomat": v.onomat, "emoji": v.emoji,
                         "symbol": v.symbol, "kaomoji": v.kaomoji}, **kw})


def _force_unique(templates: list[Variant], vi: int, used: set) -> tuple:
    base_candidates = [("emoji", len(EMOJIS)), ("symbol", len(SYMBOLS)),
                       ("kaomoji", len(KAOMOJIS)), ("onomat", len(ONOMATOPOEIA))]
    cands = [c for c in base_candidates if c[1] > 0]
    if not cands:
        raise HajimiError("no-category-to-break-collision")
    prioritized = ([c for c in cands if field_is_none(templates[vi], c[0])]
                   + [c for c in cands if not field_is_none(templates[vi], c[0])])
    for key, pool in prioritized:
        original = getattr(templates[vi], key)
        base_seed = (original if original is not None else vi) % pool
        for step in range(pool):
            updated = (base_seed + step) % pool
            templates[vi] = dataclass_replace(templates[vi], **{key: updated})
            s = _sig(templates[vi])
            if s not in used:
                return s
        if original is None:
            templates[vi] = dataclass_replace(templates[vi], **{key: None})
        else:
            templates[vi] = dataclass_replace(templates[vi], **{key: original})
    raise HajimiError("unable-to-deduplicate-variants")


class Encoder:
    def __init__(self, weights: dict | None = None, rng: random.Random | None = None):
        self.templates = build_templates(weights)
        self.rng = rng or random.Random()

    # ---- value <-> token
    def value_to_token(self, value: int) -> str:
        if not 0 <= value < RADIX:
            raise HajimiError("value-out-of-range")
        variant_index = value // BASE_COUNT
        base_index = value % BASE_COUNT
        if variant_index >= len(self.templates):
            raise HajimiError("variant-overflow")
        t = self.templates[variant_index]
        tok = BASE_WORDS[base_index]
        if t.onomat is not None:
            tok += ONOMATOPOEIA[(t.onomat + base_index) % len(ONOMATOPOEIA)]
        if t.emoji is not None:
            tok += EMOJIS[(t.emoji + base_index) % len(EMOJIS)]
        if t.symbol is not None:
            tok += SYMBOLS[(t.symbol + base_index) % len(SYMBOLS)]
        if t.kaomoji is not None:
            tok += KAOMOJIS[(t.kaomoji + base_index) % len(KAOMOJIS)]
        return tok

    # ---- encode
    def encode(self, text: str) -> str:
        if not text.strip():
            raise HajimiError("empty input")
        payload = _pack_payload(text)
        compressed = _gzip(payload)
        chunks, tail_bits = _chunkify(compressed)
        salt = self.rng.randrange(SALT_RANGE) if SALT_RANGE > 1 else 0
        header_value = tail_bits + HEADER_SCALE * salt
        tokens = [self.value_to_token(header_value)]
        for c in chunks:
            tokens.append(self.value_to_token((c + salt) % RADIX))
        lead = self.rng.choice(LEAD_BASES)
        return lead + "".join(tokens)

    # ---- decode
    def decode(self, cipher: str) -> str:
        compact = re.sub(r"\s+", "", cipher)
        if not compact:
            raise HajimiError("empty input")
        tokens = self._parse_tokens(compact)
        if not tokens or len(tokens) < 2:
            raise HajimiError(ERR_MSG)
        lead_word = BASE_WORDS[tokens[0][0]]
        if lead_word not in LEAD_BASES:
            raise HajimiError(ERR_MSG)
        hv = self._token_value(tokens[1])
        if hv is None:
            raise HajimiError(ERR_MSG)
        salt = hv // HEADER_SCALE
        tail_bits = hv % HEADER_SCALE
        if salt >= SALT_RANGE or tail_bits >= 10:
            raise HajimiError(ERR_MSG)
        chunk_values = []
        for tok in tokens[2:]:
            ev = self._token_value(tok)
            if ev is None:
                raise HajimiError(ERR_MSG)
            chunk_values.append((ev - salt) % RADIX)
        if not chunk_values:
            raise HajimiError(ERR_MSG)
        compressed = _unchunkify(chunk_values, tail_bits)
        try:
            payload = gzip.decompress(compressed)
        except OSError:
            raise HajimiError(ERR_MSG)
        try:
            return _unpack_payload(payload)
        except (HajimiError, UnicodeDecodeError):
            raise HajimiError(ERR_MSG)

    # ---- token parsing: greedy DFS over base+category sequence
    def _parse_tokens(self, text: str) -> list[tuple[int, Variant]] | None:
        memo: dict[int, list | None] = {}

        def dfs(i: int):
            if i == len(text):
                return []
            if i in memo:
                return memo[i]
            result = None
            for opt in self._collect_options(text, i):
                cont = dfs(opt[2])
                if cont is not None:
                    result = [(opt[0], opt[1])] + cont
                    break
            memo[i] = result
            return result

        return dfs(0)

    def _collect_options(self, text: str, start: int):
        base = _match_longest(BASE_WORDS, text, start)
        if base is None:
            return []
        b_idx, b_end = base
        results = []

        def walk(idx: int, cursor: int, parts: dict):
            if idx == len(_CATEGORY_SEQ):
                v = Variant(parts.get("onomat"), parts.get("emoji"),
                            parts.get("symbol"), parts.get("kaomoji"))
                results.append((b_idx, v, cursor))
                return
            key, pool = _CATEGORY_SEQ[idx]
            m = _match_longest(pool, text, cursor)
            if m is not None:
                nxt = dict(parts)
                nxt[key] = m[0]
                walk(idx + 1, m[1], nxt)
            walk(idx + 1, cursor, parts)  # skip category

        walk(0, b_end, {})
        return results

    def _token_value(self, token: tuple[int, Variant]) -> int | None:
        b_idx, parts = token
        vi = self._locate_variant(b_idx, parts)
        if vi < 0:
            return None
        value = vi * BASE_COUNT + b_idx
        return value if value < RADIX else None

    def _locate_variant(self, b_idx: int, v: Variant) -> int:
        for i, t in enumerate(self.templates):
            if self._matches(t, b_idx, v):
                return i
        return -1

    @staticmethod
    def _matches(t: Variant, b_idx: int, v: Variant) -> bool:
        for key, pool in (("onomat", len(ONOMATOPOEIA)), ("symbol", len(SYMBOLS)),
                          ("emoji", len(EMOJIS)), ("kaomoji", len(KAOMOJIS))):
            seed = getattr(t, key)
            observed = getattr(v, key)
            if seed is None or pool == 0:
                if observed is not None:
                    return False
            else:
                if observed is None:
                    return False
                if (seed + b_idx) % pool != observed:
                    return False
        return True


_CATEGORY_SEQ = [("onomat", ONOMATOPOEIA), ("emoji", EMOJIS),
                 ("symbol", SYMBOLS), ("kaomoji", KAOMOJIS)]


def _match_longest(pool: list[str], text: str, start: int):
    best = None
    for idx, tok in enumerate(pool):
        if text.startswith(tok, start):
            if best is None or len(tok) > len(pool[best[0]]):
                best = (idx, start + len(tok))
    return best


_DEFAULT: Encoder | None = None


def _default_encoder() -> Encoder:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Encoder()
    return _DEFAULT


def encode(text: str) -> str:
    return _default_encoder().encode(text)


def decode(cipher: str) -> str:
    return _default_encoder().decode(cipher)
