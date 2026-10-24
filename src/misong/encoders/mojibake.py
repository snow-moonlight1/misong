"""魔曰 (Abracadabra) wrapper: drives the vendored V3.0.11 build via node.

Requires only `node` on PATH; the bundled build (src/misong/vendor/abracadabra,
GPL-3.0) has no npm dependencies. Modes:
  wenyan — 文言文模式（推荐，AES 密钥即"魔咒"）
  old    — 传统魔曰（映射表+密钥）

Compatibility: text produced here decodes in every newer 魔曰 release.
Wenyan text produced by 魔曰 3.1+ may use new sentence patterns (骈文/逻辑)
that V3.0.11 cannot decode; such failures raise with a hint to use the
official 魔曰 site instead.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().with_name("abra_bridge.mjs")
VENDORED = Path(__file__).resolve().parents[1] / "vendor" / "abracadabra" / "abracadabra-cn.mjs"
VENDORED_VERSION = "3.0.11"
# GUI 由 pythonw 启动时没有控制台，node 是控制台程序，不加此标志会弹出一个黑框。
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

WENYAN_DECODE_HINT = (
    "解不开时请先确认密钥；若密文由新版魔曰（3.1 及以后）生成，可能含有内置版本"
    f"（{VENDORED_VERSION}）不支持的新句式，请改用魔曰官方网页解密。"
)


class MojibakeUnavailable(RuntimeError):
    pass


def _ensure() -> None:
    if shutil.which("node") is None:
        raise MojibakeUnavailable("未找到 node；魔曰需要安装 Node.js 后使用")
    for path in (BRIDGE, VENDORED):
        if not path.exists():
            raise MojibakeUnavailable(f"魔曰组件缺失: {path}")


def _run(mode: str, key: str, text: str) -> str:
    _ensure()
    r = subprocess.run(
        [shutil.which("node") or "node", str(BRIDGE), mode, key],
        input=(text + "\n").encode("utf-8"),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(BRIDGE.parent),
        creationflags=NO_WINDOW,
    )
    if r.returncode != 0:
        detail = r.stderr.decode("utf-8", "replace").strip()
        hint = f"；{WENYAN_DECODE_HINT}" if mode == "wenyan-dec" else ""
        raise RuntimeError(f"魔曰 {mode} 失败: {detail}{hint}")
    return r.stdout.decode("utf-8")


def encode(text: str, key: str = "ABRACADABRA", mode: str = "wenyan") -> str:
    if mode == "wenyan":
        return _run("wenyan-enc", key, text)
    if mode == "old":
        return _run("old-enc", key, text)
    raise ValueError(f"未知魔曰模式: {mode}")


def decode(cipher: str, key: str = "ABRACADABRA", mode: str = "wenyan") -> str:
    if mode == "wenyan":
        return _run("wenyan-dec", key, cipher)
    if mode == "old":
        return _run("old-dec", key, cipher)
    raise ValueError(f"未知魔曰模式: {mode}（内置 {VENDORED_VERSION} 版只支持 wenyan / old）")
