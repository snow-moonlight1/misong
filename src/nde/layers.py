"""Unified inner-to-outer layer specifications and legacy option migration."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

from . import formats
from .split import parse_size


@dataclass
class LayerSpec:
    # Keep the original positional archive constructor compatible.
    fmt: str = "7z"
    password: str | None = None
    header_enc: bool = False
    type: str = "archive"
    level: int | None = None
    video: str = ""
    size: str = "1900MB"
    ext: str = ""

    @classmethod
    def from_dict(cls, raw):
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in raw.items() if k in fields})

    def public(self):
        data = asdict(self)
        data["password"] = bool(self.password)
        return data


def migrate(layers, *, disguise="", video=None, size="") -> list[LayerSpec]:
    result = [LayerSpec.from_dict(x) if isinstance(x, dict) else x for x in layers]
    # New models already carry all transformations. Legacy archive-only calls
    # append the old post-processing options in their original order.
    if all(x.type == "archive" for x in result):
        if disguise:
            result.append(LayerSpec(type="rename", ext=disguise))
        if video:
            # Old disguise affected the archive name, not its signature.
            result.append(LayerSpec(type="cover", video=str(video)))
        if size:
            result.append(LayerSpec(type="split", size=size))
    return result


def validate(layers, inputs=None, *, check_video=True):
    if not layers:
        raise ValueError("请至少设置一层打包格式")
    single = inputs is None or (len(inputs) == 1 and Path(inputs[0]).is_file())
    archive_kind = None
    for i, layer in enumerate(layers):
        prefix = f"第 {i + 1} 层："
        if layer.type == "archive":
            fmt = formats.get(layer.fmt)
            if layer.password and not fmt.supports_password:
                raise ValueError(prefix + f"{layer.fmt} 不支持密码，请把密码放到 7z/zip 层")
            if layer.level is not None and not 0 <= layer.level <= 9:
                raise ValueError(prefix + "压缩等级应为 0–9")
            single, archive_kind = True, fmt.key
        elif layer.type in ("cover", "split", "rename"):
            if not single:
                raise ValueError(prefix + "只接受单文件；分卷或多个输入之后必须先添加 archive 层")
            if layer.type == "cover":
                if archive_kind not in ("7z", "zip"):
                    raise ValueError(prefix + "门面视频前必须有 7z/zip 归档层（可先改后缀）")
                if not layer.video or (check_video and not Path(layer.video).is_file()):
                    raise ValueError(prefix + "请选择有效的 MP4 门面视频")
                archive_kind = None
            elif layer.type == "split":
                parse_size(str(layer.size))
                single, archive_kind = False, None
            else:
                ext = layer.ext.lstrip(".")
                if not ext or any(c in ext for c in '/\\:\x00*?"<>|'):
                    raise ValueError(prefix + "请填写有效的产物后缀")
        else:
            raise ValueError(prefix + f"未知层类型：{layer.type}")


def output_ext(layers):
    if not layers:
        return ".bin"
    last = layers[-1]
    if last.type == "split":
        return output_ext(layers[:-1])
    if last.type == "cover":
        return ".mp4"
    if last.type == "rename":
        return "." + last.ext.lstrip(".")
    return formats.get(last.fmt).native_exts[0]
