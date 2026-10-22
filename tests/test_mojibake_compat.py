"""魔曰 vendored V3.0.11 build: integrity and cross-version compatibility fixtures.

The fixtures below were produced by the official 魔曰 V3.5.5 release with key
ABRACADABRA and plaintext "提取码：ab12".
"""
import hashlib
import shutil

import pytest

from nde.encoders import mojibake

PLAIN = "提取码：ab12"
V355_WENYAN_DEFAULT = "进鹂而返之者，非其云谨也。读绿书，裳和曲慧，乃允见。道冰惟微，谓微妙而难去也。以雅树为韵者，铃应弗而返之。非书也，彩鸢曾定。"
V355_WENYAN_PIANWEN = "夜作以鹂，非可成也。非欲行也。岩琴致莺，舒于花苗，不应关也。人有想歌，福有永然。林有必度，镜有诚然，本必说新，非看楼铃。"
V355_OLD = "眼游镓谈那棠里每桜到珏从老此硼朩甄但获翎饴酿钕向子苑座氧"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node unavailable")


def test_vendored_build_is_pinned_gpl_release():
    data = mojibake.VENDORED.read_bytes()
    assert hashlib.sha256(data).hexdigest() == "bf472ed92dd7cb16977241a06dd5fc0ddc1875e684706f3453d34b8e636a01f0"
    license_text = (mojibake.VENDORED.parent / "LICENSE").read_text(encoding="utf-8")
    assert "GNU GENERAL PUBLIC LICENSE" in license_text and "Version 3" in license_text


@needs_node
def test_decodes_official_new_release_texts():
    assert mojibake.decode(V355_WENYAN_DEFAULT) == PLAIN
    assert mojibake.decode(V355_OLD, mode="old") == PLAIN


@needs_node
def test_new_sentence_patterns_fail_with_hint():
    with pytest.raises(RuntimeError) as err:
        mojibake.decode(V355_WENYAN_PIANWEN)
    assert "官方网页" in str(err.value)


def test_bear_mode_is_not_offered():
    with pytest.raises(ValueError):
        mojibake.decode("熊曰：呵", mode="bear")
