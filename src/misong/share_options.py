"""One saved sharing policy for every stage of a publication."""
from dataclasses import asdict, dataclass

from .providers import PROVIDERS, disk_name

EXPIRY_LABELS = {"default": "平台默认", "1": "1天", "2": "2天", "3": "3天", "4": "4天", "5": "5天", "6": "6天", "7": "7天", "30": "30天",
                 "60": "60天", "180": "180天", "365": "365天", "forever": "永久有效"}
ACCESS_LABELS = {"default": "平台默认", "none": "无提取码", "code": "有提取码（自动生成）"}
CAPABILITIES = {
    "quark": ({"1", "7", "30", "forever"}, {"none", "code"}),
    "uc": ({"1", "7", "30", "60", "180", "forever"}, {"none", "code"}),
    "123pan": ({"1", "7", "30", "forever"}, {"none", "code"}),
    "xunlei": ({"1", "2", "3", "4", "5", "6", "7", "forever"}, {"code"}),
    "feimao": ({"forever"}, {"none", "code"}),
    "baidu": ({"1", "7", "30", "365", "forever"}, {"code"}),
}


def common_options(disks):
    """Keep only choices every selected provider can actually honor."""
    durations = set(EXPIRY_LABELS) - {"default"}
    access = set(ACCESS_LABELS) - {"default"}
    disks = set(map(disk_name, disks))
    if not disks:
        return ["default"], ["default"]
    for disk in disks:
        d, a = CAPABILITIES.get(disk, (set(), set()))
        durations &= d
        access &= a
    return (["default"] + [k for k in EXPIRY_LABELS if k in durations],
            ["default"] + [k for k in ACCESS_LABELS if k in access])


@dataclass(frozen=True)
class ShareOptions:
    expiry: str = "default"
    access: str = "default"

    def __post_init__(self):
        if self.expiry not in EXPIRY_LABELS or self.access not in ACCESS_LABELS:
            raise ValueError("分享选项无效，请选择有效期和提取码设置")

    def to_dict(self):
        return asdict(self)

    @property
    def is_default(self):
        return self == ShareOptions()

    def validate_disk(self, disk):
        disk = disk_name(disk)
        durations, access = CAPABILITIES.get(disk, (set(), set()))
        label = PROVIDERS.get(disk, {}).get("label", disk)
        if self.expiry != "default" and self.expiry not in durations:
            raise ValueError(f"{label} 当前网页适配不支持 {EXPIRY_LABELS[self.expiry]}；请选择平台默认或该盘支持的期限")
        if self.access != "default" and self.access not in access:
            raise ValueError(f"{label} 当前网页适配不支持 {ACCESS_LABELS[self.access]}；请选择平台默认或该盘支持的提取码形式")
