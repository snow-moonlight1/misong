"""Provider identities shared by parsing, account controls and upload adapters.

Presence here identifies a service; it does not certify an upload driver.
"""
PROVIDERS = {
    "quark": {"label": "夸克网盘", "hosts": ("pan.quark.cn",)},
    "feimao": {"label": "飞猫盘", "hosts": ("feemoo.com", "feimaoyun.com", "cm1.hk", "cm2.hk")},
    "baidu": {"label": "百度网盘", "hosts": ("pan.baidu.com", "yun.baidu.com")},
    "xunlei": {"label": "迅雷云盘", "hosts": ("pan.xunlei.com", "xlpan.xunlei.com")},
    "uc": {"label": "UC网盘", "hosts": ("drive.uc.cn",)},
    "123pan": {"label": "123云盘", "hosts": ("123pan.com", "123pan.cn", "123865.com", "123912.com")},
}
ALIASES = {
    "飞猫盘": "feimao", "飞猫": "feimao", "feemoo": "feimao",
    "夸克": "quark", "夸克网盘": "quark", "百度": "baidu", "百度网盘": "baidu",
    "迅雷": "xunlei", "迅雷云盘": "xunlei", "迅雷网盘": "xunlei",
    "uc网盘": "uc", "uc云盘": "uc", "123": "123pan", "123盘": "123pan", "123云盘": "123pan",
}
HOSTS = {key: value["hosts"] for key, value in PROVIDERS.items()}


def disk_name(name: str) -> str:
    value = name.strip().lower()
    return ALIASES.get(value, value)
