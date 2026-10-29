"""Parse share text and reuse the existing encoders for local copy output."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .encoders import beast, hajimi, mojibake, plain
from .providers import ALIASES, HOSTS, disk_name
# Public migration entry for callers moving from parallel copy selections.
from .text_layers import recipes_from_schemes

COPY_SCHEMES = ("beast", "mojibake", "hajimi", "base64", "base64url", "base32", "base85", "hex", "url", "reverse", "rot13")


@dataclass
class ShareInfo:
    disk: str
    url: str = ""
    code: str = ""
    expire: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def text(self) -> str:
        return self.url + (f"\n提取码：{self.code}" if self.code else "") + (f"\n有效期：{self.expire}" if self.expire else "")


def parse_share(text: str, disk: str, *, allowed_hosts=None) -> ShareInfo:
    disk = disk_name(disk)
    hosts = allowed_hosts or HOSTS.get(disk, ())
    candidates = []
    for url in re.findall(r"https?://[^\s<>\"'，。；、）)]+", text):
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if any(host == h or host.endswith("." + h) for h in hosts):
            # Login and file-manager URLs on the same domain are not share links.
            if disk in HOSTS:
                valid_path = re.match(r"^/(?:s|f)/[^/]+/?$" if disk == "feimao" else r"^/s/[^/]+/?$", parsed.path)
                legacy_baidu = disk == "baidu" and parsed.path in ("/share/init", "/share/link") and parse_qs(parsed.query).get("surl")
                branded_123 = disk == "123pan" and host.endswith(".share.123pan.cn") and re.fullmatch(r"/123pan/[A-Za-z0-9_-]+/?", parsed.path)
                if not valid_path and not legacy_baidu and not branded_123:
                    continue
            if url not in candidates:
                candidates.append(url)
    if len(candidates) != 1:
        raise ValueError("请提供唯一的该网盘分享链接（包含提取码），不能使用网盘首页")
    url = candidates[0]
    parsed = urlsplit(url)
    if parsed.path in ("", "/") and not parsed.query:
        raise ValueError("检测到网盘首页，请复制分享弹窗内的链接")
    params = parse_qs(parsed.query)
    code = next((params[k][0] for k in ("pwd", "code", "password", "passcode") if params.get(k)), "")
    # Feemoo puts the access password in the fragment: https://host/f/id#密码：Ab12
    # A "密码" label before that URL would otherwise capture the scheme "https".
    fragment = re.search(r"(?:密码|pwd|passcode)\s*[：:=]\s*([A-Za-z0-9]{2,16})", parsed.fragment or "", re.I)
    if fragment:
        code = fragment[1]
    labeled = re.search(r"(?:提取码|访问码|提取密[码碼])\s*[：:=]?\s*([A-Za-z0-9]{2,16})", text, re.I)
    if labeled and labeled[1].lower() not in {"http", "https"}:
        code = labeled[1]
    elif not code:
        # A guide can contain both a cloud access code and an archive password.
        generic = re.search(r"(?:(?<!解压)密[码碼]|password|pwd)\s*[：:=]?\s*([A-Za-z0-9]{2,16})", text, re.I)
        if generic and generic[1].lower() not in {"http", "https"}:
            code = generic[1]
    expiry = re.search(r"永久有效|长期有效|\d+天后失效|\d+天后过期", text)
    return ShareInfo(disk, url, code, expiry[0] if expiry else "")


def encode_copy(text: str, schemes=("beast", "mojibake", "hajimi"), *, key="ABRACADABRA") -> dict[str, str]:
    """Legacy parallel outputs; each scheme always consumes the original text."""
    result = {}
    for scheme in schemes:
        if scheme == "beast":
            result[scheme] = beast.encode(text, dialect="web")
        elif scheme == "mojibake":
            result[scheme] = mojibake.encode(text, key=key)
        elif scheme == "hajimi":
            result[scheme] = hajimi.encode(text)
        else:
            result[scheme] = plain.encode(scheme, text)
    return result


def write_copy(folder: Path, share: ShareInfo, schemes, *, key="ABRACADABRA", text=None) -> dict[str, str]:
    text = share.text() if text is None else text
    output = encode_copy(text, schemes, key=key)
    folder.mkdir(parents=True, exist_ok=True)
    for scheme, cipher in output.items():
        (folder / f"{scheme}.txt").write_text(cipher + "\n", encoding="utf-8")
    (folder / "share-plain.txt").write_text(text + "\n", encoding="utf-8")
    return output
