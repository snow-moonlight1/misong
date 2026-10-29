"""脱敏回归：全部使用合成标记（syn 前缀），不含真实凭据、链接与本机路径。"""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from misong.redact import PLACEHOLDER as P
from misong.redact import redact_data, redact_text

# 覆盖 providers.py 六个网盘的全部分享链接形态（含 123 品牌域与百度旧版 surl）。
SHARE_URLS = [
    ("https://pan.baidu.com/s/1synABC?pwd=syn1", "1synABC", "syn1"),
    ("https://pan.quark.cn/s/synQkd?pwd=syn2", "synQkd", "syn2"),
    ("https://pan.xunlei.com/s/synXL?pwd=syn3", "synXL", "syn3"),
    ("https://drive.uc.cn/s/synUC?pwd=syn4", "synUC", "syn4"),
    ("https://www.123865.com/s/syn123?pwd=syn5", "syn123", "syn5"),
    ("https://fixture.share.123pan.cn/123pan/Syn-Branded?pwd=syn6", "Syn-Branded", "syn6"),
    ("https://www.feemoo.com/f/synFM?pwd=syn7", "synFM", "syn7"),
    ("https://pan.baidu.com/share/init?surl=synLegacy", "synLegacy", ""),
]


@pytest.mark.parametrize("url,share_id,code", SHARE_URLS)
def test_share_link_ids_and_code_params_are_redacted(url, share_id, code):
    out = redact_text(url)
    assert share_id not in out and P in out
    assert code == "" or code not in out
    assert url.split("/")[2] in out  # 平台域名保留，便于排障


def test_share_structure_stays_visible():
    out = redact_text("https://pan.quark.cn/s/synQkd?pwd=syn2&from=timeline")
    assert out == f"https://pan.quark.cn/s/{P}?pwd={P}&from=timeline"


def test_non_share_pages_are_left_alone():
    text = "https://pan.baidu.com/disk/main#/index https://pan.xunlei.com/login/"
    assert redact_text(text) == text


def test_userinfo_credentials_are_redacted():
    out = redact_text("https://synuser:supersecret@example.com/path")
    assert "synuser" not in out and "supersecret" not in out
    assert out == f"https://{P}@example.com/path"


def test_sensitive_params_on_plain_urls():
    out = redact_text("https://example.com/api?token=syn-token-123&x=1")
    assert "syn-token-123" not in out and "x=1" in out


def test_labeled_share_codes_are_redacted():
    samples = [
        ("提取码：Syn12", "提取码：" + P),
        ("提取码:Syn12", "提取码:" + P),
        ("访问码 Syn34", "访问码 " + P),
        ("取件码 ab56", "取件码 " + P),
        ("解压密码：SynPw88", "解压密码：" + P),
        ("密码：SynPw88", "密码：" + P),
        ("password: synpw123", "password: " + P),
        ("passwd=synpw123", "passwd=" + P),
        ("pwd=synpw123", "pwd=" + P),
    ]
    for src, want in samples:
        assert redact_text(src) == want, src


def test_scheme_is_not_mangled_by_code_label():
    out = redact_text("提取码：https://pan.baidu.com/s/1syn?pwd=syn1")
    assert out.startswith("提取码：https://pan.baidu.com/s/")
    assert "1syn" not in out and "syn1" not in out


@pytest.mark.parametrize("src,want", [
    (r"C:\Users\synuser\Videos\syn.mp4", rf"C:\Users\{P}\Videos\syn.mp4"),
    ("C:/Users/synuser/syn.mp4", f"C:/Users/{P}/syn.mp4"),
    ("/home/synuser/data/syn.mp4", f"/home/{P}/data/syn.mp4"),
    ("/Users/synuser/Movies/syn.mp4", f"/Users/{P}/Movies/syn.mp4"),
])
def test_user_paths_are_redacted(src, want):
    assert redact_text(src) == want


def test_non_user_paths_stay():
    text = "/var/log/misong.log D:\\data\\syn.mp4"
    assert redact_text(text) == text


def test_cookie_and_authorization_headers():
    assert redact_text("Cookie: SESSID=syn1; CSRFToken=syn2; uid=3") == "Cookie: " + P
    assert redact_text("set-cookie: SID=syn; HttpOnly") == "set-cookie: " + P
    assert redact_text("Authorization: Bearer syn-token-abc123") == "Authorization: Bearer " + P
    assert redact_text("authorization: Basic c3luOnN5bg==") == "authorization: Basic " + P
    assert redact_text("authorization: c3luOnN5bg==") == "authorization: " + P


def test_bare_token_kv_pairs():
    assert redact_text("token=syn-token-123") == "token=" + P
    assert redact_text("api_key=synapikey12345") == "api_key=" + P
    assert redact_text("size=1024") == "size=1024"


def test_urls_inside_log_lines():
    line = "2026-10-26 12:00:00 INFO 上传完成 https://pan.baidu.com/s/1syn?pwd=syn1 size=1024 卷 2/3"
    out = redact_text(line)
    assert "1syn" not in out and "syn1" not in out
    assert "size=1024" in out and "2/3" in out and "pan.baidu.com" in out


def test_percent_encoded_url_and_fragment_are_redacted():
    out = redact_text("redirect=https%3A%2F%2Fpan.baidu.com%2Fs%2F1syn%3Fpwd%3Dsyn1&ok=1")
    assert "1syn" not in out and "syn1" not in out
    assert "ok=1" in out and "pan.baidu.com" in out
    out = redact_text("https://cm2.hk/f/synID#%E5%AF%86%E7%A0%81%EF%BC%9AabC2")
    assert "abC2" not in out


def test_unicode_text_around_secrets():
    out = redact_text("文件✅已上传🎉 提取码：Syn12，卷2/3")
    assert out == f"文件✅已上传🎉 提取码：{P}，卷2/3"


def test_redact_text_rejects_non_str():
    with pytest.raises(TypeError):
        redact_text(123)


def test_mskey_path_and_content_are_never_read(monkeypatch):
    import builtins

    def boom(*args, **kwargs):
        raise AssertionError("脱敏不得读取文件内容")

    monkeypatch.setattr(builtins, "open", boom)
    text = r"钥匙已生成 C:\Users\synuser\task.mp4.mskey 请勿外传"
    out = redact_text(text)
    assert "synuser" not in out and out.endswith("task.mp4.mskey 请勿外传")
    data = {"mskey": {"passwords": ["syn-layer-pw"]}, "key_path": Path("t.mp4.mskey"),
            "payload": b"MISONGKEY\x00\x01syn"}
    assert redact_data(data) == {"mskey": P, "key_path": P, "payload": P}


def test_redact_data_nested_preserves_debug_info():
    task = {
        "task": "syn-task",
        "layers": [
            {"type": "archive", "format": "7z", "has_password": True, "password": "syn-layer-pw",
             "size": 1024},
            {"type": "cover", "format": "mp4", "password": None},
        ],
        "status": "failed",
        "counts": {"files": 3, "volumes": 2},
        "cookies": "SESSID=syn1; CSRF=syn2",
        "share": {"disk": "baidu", "url": "https://pan.baidu.com/s/1syn?pwd=syn1", "code": "Syn12"},
    }
    snapshot = deepcopy(task)
    out = redact_data(task)
    assert task == snapshot  # 输入不被修改
    layer = out["layers"][0]
    assert layer["type"] == "archive" and layer["format"] == "7z"
    assert layer["has_password"] is True and layer["size"] == 1024
    assert layer["password"] == P
    assert out["layers"][1]["password"] is None
    assert [l["type"] for l in out["layers"]] == ["archive", "cover"]  # 层序保留
    assert out["status"] == "failed"
    assert out["counts"] == {"files": 3, "volumes": 2}
    assert out["cookies"] == P
    assert out["share"]["disk"] == "baidu"
    assert out["share"]["url"] == f"https://pan.baidu.com/s/{P}?pwd={P}"
    assert out["share"]["code"] == P
    json.dumps(out)  # 输出保持可 JSON 序列化


def test_redact_data_password_bool_and_counts_survive():
    out = redact_data({"password": False, "password_length": 16, "pwd": "synpw",
                       "retry": 2, "note": None, "empty": ""})
    assert out == {"password": False, "password_length": 16, "pwd": P,
                   "retry": 2, "note": None, "empty": ""}


def test_redact_data_cookie_variants():
    out = redact_data({
        "cookie": "SESSID=syn1; CSRF=syn2",
        "cookies": [{"name": "SESSID", "value": "syn1"}, {"name": "T", "value": "syn2"}],
        "cookie_count": 2,
    })
    assert out["cookie"] == P
    assert out["cookies"] == [P, P]  # 条目内容折叠，数量保留
    assert out["cookie_count"] == 2


def test_redact_data_json_scalars_and_types():
    data = {"n": 3.5, "flag": False, "when": "2026-10-26",
            "path": Path("C:/Users/synuser/x"), "a": ("x", 1)}
    out = redact_data(data)
    assert out["n"] == 3.5 and out["flag"] is False and out["when"] == "2026-10-26"
    assert out["a"] == ("x", 1)
    assert isinstance(out["a"], tuple)
    assert "synuser" not in out["path"]  # Path 转文本后用户名脱敏（分隔符随平台规范化）
    json.dumps(out)


IDEMPOTENT_TEXT_CORPUS = [
    "百度 https://pan.baidu.com/s/1synABC?pwd=syn1 提取码：Syn12",
    "https://cm2.hk/f/synID#密码：abC2",
    "Cookie: SESSID=syn1; CSRF=syn2; uid=3",
    r"C:\Users\synuser\Videos\syn.mp4",
    "/home/synuser/data/syn.mp4",
    "redirect=https%3A%2F%2Fpan.baidu.com%2Fs%2F1syn%3Fpwd%3Dsyn1",
    "Authorization: Bearer syn-token-abc123",
    "https://example.com/api?token=syn-token-123&x=1",
    "plain text 无敏感内容",
]


@pytest.mark.parametrize("sample", IDEMPOTENT_TEXT_CORPUS)
def test_redact_text_is_idempotent(sample):
    once = redact_text(sample)
    assert redact_text(once) == once


def test_redact_data_is_idempotent():
    data = {"log": "上传完成 提取码：Syn12 https://pan.quark.cn/s/synQ?pwd=syn2",
            "auth": {"password": "syn-pw"}, "cookies": ["a=syn1", "b=syn2"], "n": 1}
    once = redact_data(data)
    assert redact_data(once) == once
