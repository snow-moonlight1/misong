"""统一脱敏：诊断与日志的安全占位（roadmap 前置工作，④⑦②⑨ 共用）。

只做纯字符串与结构变换：不打开文件、不联网、不读取 ``.mskey`` 钥匙内容；
输入不被修改，输出为递归复制的 JSON 兼容结构。占位符统一为 ``[REDACTED]``，
平台域名、路径结构与数量保留以便排障。本模块不接入任何输出通道，
日志 / CLI / GUI / 诊断包的集成由主线负责。
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from .providers import HOSTS

PLACEHOLDER = "[REDACTED]"

__all__ = ["PLACEHOLDER", "redact_data", "redact_text"]

# 标签族与 sharing.parse_share 保持一致；脱敏比解析更宽：不带 (?<!解压) 负向断言，
# “解压密码”等归档口令同样是敏感值。显式标签允许省略分隔符，泛化标签必须带分隔符，
# 避免 "password policy" 这类普通文本被误伤。分隔符并入首组，替换时原样保留。
_EXPLICIT_CODE_RE = re.compile(
    r"((?:提取码|访问码|取件码|提取密[码碼])\s*[：:=]?\s*)([A-Za-z0-9]{2,16})")
_GENERIC_CODE_RE = re.compile(
    r"((?:密[码碼]|password|passwd|pwd|passcode|api[_-]?key|secret|token|key)\s*[：:=]\s*)"
    r"([^\s<>\"'，。；、）)\[\]{}]+)", re.I)
_QUOTED_SECRET_RE = re.compile(
    r"((?:密[码碼]|password|passwd|pwd|passcode|api[_-]?key|secret|token|key)\s*[：:=]\s*)"
    r"([\"'])([^\r\n]*?)\2", re.I)
_URL_RE = re.compile(r"https?://[^\s<>\"'，。；、）)]+", re.I)
# 百分号编码形态的 URL（常见于日志里的 redirect/嵌套引用）：冒号必须是 %3a，
# 斜杠允许原样或编码；裸 & 视为同层参数分隔符（编码 URL 内部应为 %26）。
_ENCODED_URL_RE = re.compile(r"https?%3a(?:%2f%2f|//)[^\s<>\"'，。；、）)&]*", re.I)
# 六个网盘分享链接的 ID 路径段：/s/<id>、飞猫 /f/<id>、123 品牌域 /123pan/<id>。
_PROVIDER_PATH_RE = re.compile(r"^(/(?:s|f|123pan)/)[^/]+(/?)$")
# Authorization 头：bearer/basic/token 方案词保留，其余值整体占位。
_AUTH_HEADER_RE = re.compile(
    r"(?i)\b(authorization)(\s*:\s*)(?:(bearer|basic|token)(\s+)\S.*|[^\r\n]+)")
_COOKIE_HEADER_RE = re.compile(r"(?i)\b((?:set-)?cookie)(\s*:\s*)[^\r\n]*")
_TOKEN_KV_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?key|private[_-]?key|access[_-]?token|refresh[_-]?token"
    r"|secret|token|session[_-]?id|key)(\s*[=:]\s*)([A-Za-z0-9._~+/=-]{8,})")
_WIN_USER_RE = re.compile(r"(?i)\b([A-Z]:[\\/]+Users[\\/]+)([^\\/\"'\s，。；、）)]+)")
_POSIX_USER_RE = re.compile(r"(?<![\w.\-])(/(?:home|Users)/)([^/\"'\s，。；、）)]+)")

_SCHEME_WORDS = {"http", "https"}
# 敏感查询参数与敏感 JSON 键的识别标记（子串匹配，宁可多脱）。
_PARAM_MARKS = ("pwd", "password", "passwd", "passcode", "token", "secret", "surl",
                "sign", "auth", "key", "code")
_KEY_MARKS = ("password", "passwd", "pwd", "passcode", "secret", "token", "cookie",
              "authorization", "credential", "auth", "key")


def _is_provider_host(host: str) -> bool:
    return any(host == h or host.endswith("." + h)
               for hosts in HOSTS.values() for h in hosts)


def _redact_code_value(match: re.Match) -> str:
    if match.group(2).lower() in _SCHEME_WORDS:
        return match.group(0)  # “提取码：https://...” 的 https 不是提取码
    return match.group(1) + PLACEHOLDER


def _sensitive_param(name: str) -> bool:
    try:
        decoded = unquote(name).lower()
    except Exception:
        decoded = name.lower()
    return any(mark in decoded for mark in _PARAM_MARKS)


def _redact_query(query: str) -> str:
    parts = []
    for pair in query.split("&"):
        key, sep, _ = pair.partition("=")
        parts.append(key + "=" + PLACEHOLDER if sep and _sensitive_param(key) else pair)
    return "&".join(parts)


def _redact_fragment(fragment: str) -> str:
    redacted = _GENERIC_CODE_RE.sub(_redact_code_value, fragment)
    if "%" not in fragment:
        return redacted
    decoded = unquote(fragment)
    redacted_decoded = _GENERIC_CODE_RE.sub(_redact_code_value, decoded)
    # 仅在确实脱敏了内容时重编码，避免改动 /list/all 这类管理页片段。
    return quote(redacted_decoded, safe="[]%/?=&") if redacted_decoded != decoded else redacted


def _redact_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return PLACEHOLDER
    host = (parts.hostname or "").lower()
    if not host:
        return url
    netloc = parts.netloc
    if "@" in netloc:  # userinfo 凭据
        netloc = PLACEHOLDER + "@" + netloc.rpartition("@")[2]
    path = parts.path
    if _is_provider_host(host):
        path = _PROVIDER_PATH_RE.sub(
            lambda m: m.group(1) + PLACEHOLDER + m.group(2), path)
    query = _redact_query(parts.query) if parts.query else ""
    fragment = _redact_fragment(parts.fragment) if parts.fragment else ""
    try:
        return urlunsplit((parts.scheme, netloc, path, query, fragment))
    except ValueError:
        return PLACEHOLDER


def _redact_auth_header(match: re.Match) -> str:
    if match.group(3):
        return f"{match.group(1)}: {match.group(3)} {PLACEHOLDER}"
    return f"{match.group(1)}: {PLACEHOLDER}"


def _redact_plain(text: str) -> str:
    text = _URL_RE.sub(lambda m: _redact_url(m.group(0)), text)
    text = _AUTH_HEADER_RE.sub(_redact_auth_header, text)
    text = _COOKIE_HEADER_RE.sub(lambda m: m.group(1) + ": " + PLACEHOLDER, text)
    text = _EXPLICIT_CODE_RE.sub(_redact_code_value, text)
    text = _QUOTED_SECRET_RE.sub(lambda m: m[1] + m[2] + PLACEHOLDER + m[2], text)
    text = _GENERIC_CODE_RE.sub(_redact_code_value, text)
    text = _TOKEN_KV_RE.sub(lambda m: m.group(1) + m.group(2) + PLACEHOLDER, text)
    text = _WIN_USER_RE.sub(lambda m: m.group(1) + PLACEHOLDER, text)
    text = _POSIX_USER_RE.sub(lambda m: m.group(1) + PLACEHOLDER, text)
    return text


def redact_text(text: str) -> str:
    """脱敏一段自由文本；保留结构（域名、路径、数量、时间戳）以便排障。"""
    if not isinstance(text, str):
        raise TypeError("redact_text 只接受 str")
    # 先处理百分号编码的 URL：解码 → 脱敏 → 按固定规则重编码（占位符括号不编码）。
    text = _ENCODED_URL_RE.sub(
        lambda m: quote(_redact_plain(unquote(m.group(0))), safe="[]"), text)
    return _redact_plain(text)


def _sensitive_key(key) -> bool:
    if not isinstance(key, str):
        return False
    name = key.lower()
    if name == "code" or name.endswith(("_code", "-code")):  # ShareInfo.code 等提取码字段
        return True
    return any(mark in name for mark in _KEY_MARKS)


def _redact_field(key, value):
    if not _sensitive_key(key):
        return redact_data(value)
    if value is None or isinstance(value, bool):
        return value  # has_password 这类布尔标志不是口令本身
    if isinstance(value, str):
        return PLACEHOLDER if value else value
    if isinstance(value, (bytes, bytearray)):
        return PLACEHOLDER  # 不解码、不嗅探内容（例如误入的 .mskey 载荷）
    if isinstance(value, (int, float)):
        return value  # 数量/长度/大小等计数信息按约定保留
    if isinstance(value, (list, tuple)):
        return type(value)(
            PLACEHOLDER if isinstance(item, (str, bytes, bytearray, dict, list, tuple))
            else redact_data(item)
            for item in value)
    return PLACEHOLDER  # 凭据字段下的 dict / 未知对象整体折叠，绝不深入


def redact_data(value):
    """递归复制 JSON 兼容结构并脱敏；不修改输入，绝不做文件 I/O。

    dict / list / tuple 逐层复制，字符串统一走 redact_text；
    Path 转为脱敏文本，bytes 整体替换为占位符；
    bool / None / int / float 及契约外的其他对象原样保留。
    """
    if isinstance(value, dict):
        return {k: _redact_field(k, v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(redact_data(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Path):
        return redact_text(str(value))
    if isinstance(value, (bytes, bytearray)):
        return PLACEHOLDER
    return value
