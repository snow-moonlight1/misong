"""Streaming MP4 embedding and ZIP/ZIP64 relocation.

Only MP4 metadata and one ZIP central record are held in memory. Payloads
are copied in bounded blocks, including archives larger than 4 GiB.
"""
from __future__ import annotations

import io
import shutil
import struct
import tempfile
from pathlib import Path

U32 = 0xFFFFFFFF
CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts", b"dinf", b"udta", b"mvex"}


def copy_range(src, dst, start, count):
    src.seek(start)
    while count:
        block = src.read(min(count, 8 * 1024 * 1024))
        if not block:
            raise ValueError("文件提前结束")
        dst.write(block)
        count -= len(block)


def box_header(kind, size):
    return (struct.pack(">I4s", size + 8, kind) if size + 8 <= U32 else
            struct.pack(">I4sQ", 1, kind, size + 16))


def boxes(fh, start, end):
    pos = start
    while pos < end:
        fh.seek(pos)
        head = fh.read(8)
        if len(head) != 8:
            raise ValueError("MP4 box 头不完整")
        size, kind = struct.unpack(">I4s", head)
        hdr = 8
        if size == 1:
            raw = fh.read(8)
            if len(raw) != 8:
                raise ValueError("MP4 扩展 box 头不完整")
            size, hdr = struct.unpack(">Q", raw)[0], 16
        elif size == 0:
            size = end - pos
        if size < hdr or pos + size > end:
            raise ValueError("MP4 box 长度无效")
        yield pos, size, kind, hdr
        pos += size


def rewrite_moov(data, shift):
    """Rebuild ancestor sizes when stco entries grow into co64 entries."""
    result = bytearray()
    with io.BytesIO(data) as src:
        for off, size, kind, hdr in boxes(src, 0, len(data)):
            payload = data[off + hdr:off + size]
            if kind in CONTAINERS:
                payload = rewrite_moov(payload, shift)
            elif kind in (b"stco", b"co64"):
                if len(payload) < 8:
                    raise ValueError("MP4 chunk 表不完整")
                count = struct.unpack_from(">I", payload, 4)[0]
                width = 4 if kind == b"stco" else 8
                if len(payload) != 8 + count * width:
                    raise ValueError("MP4 chunk 表长度无效")
                values = [shift(v[0]) for v in struct.iter_unpack(">I" if width == 4 else ">Q", payload[8:])]
                if kind == b"stco" and any(v > U32 for v in values):
                    kind = b"co64"
                fmt = ">Q" if kind == b"co64" else ">I"
                payload = payload[:8] + b"".join(struct.pack(fmt, v) for v in values)
            result.extend(box_header(kind, len(payload)))
            result.extend(payload)
    return bytes(result)


def zip_directory(src, start=0, length=None, offset_base=0):
    """Locate the real EOCD by its comment length, including ZIP64 locator."""
    if length is None:
        src.seek(0, 2)
        length = src.tell() - start
    tail_start = start + max(0, length - 65557)
    src.seek(tail_start)
    tail = src.read(start + length - tail_start)
    idx = len(tail)
    while True:
        idx = tail.rfind(b"PK\x05\x06", 0, idx)
        if idx < 0:
            raise ValueError("不是标准 ZIP（找不到有效 EOCD）")
        if idx + 22 <= len(tail) and idx + 22 + struct.unpack_from("<H", tail, idx + 20)[0] == len(tail):
            break
    eocd = tail[idx:]
    disk, cd_disk, disk_count, count, cd_size, cd_off = struct.unpack_from("<HHHHII", eocd, 4)
    if disk or cd_disk or disk_count != count:
        raise ValueError("不支持多磁盘 ZIP；请先合卷")
    eocd_pos = tail_start + idx
    src.seek(max(start, eocd_pos - 20))
    locator = src.read(20)
    is64 = locator[:4] == b"PK\x06\x07"
    if is64:
        z_disk, z_off, disks = struct.unpack_from("<IQI", locator, 4)
        if z_disk or disks != 1:
            raise ValueError("不支持多磁盘 ZIP64")
        src.seek(start + z_off - offset_base)
        record = src.read(56)
        if len(record) != 56 or record[:4] != b"PK\x06\x06":
            raise ValueError("ZIP64 EOCD 无效")
        count, cd_size, cd_off = struct.unpack_from("<QQQ", record, 32)
    if cd_off < offset_base or cd_off - offset_base + cd_size > length:
        raise ValueError("ZIP 中央目录超出文件范围")
    return count, cd_size, cd_off, eocd, is64


def relocate_zip(src, dst, delta, *, start=0, length=None, offset_base=0):
    """Copy ZIP with absolute offsets adjusted by delta; promote to ZIP64.

    offset_base is the original embedded payload's absolute origin. Local
    headers contain sizes (not offsets); preserve those and their ZIP64 extras.
    """
    count, cd_size, cd_off, eocd, was64 = zip_directory(src, start, length, offset_base)
    relative_cd = cd_off - offset_base
    copy_range(src, dst, start, relative_cd)
    new_cd_off = cd_off + delta
    cd_begin = dst.tell()
    pos = start + relative_cd
    for _ in range(count):
        src.seek(pos)
        head = bytearray(src.read(46))
        if len(head) != 46 or head[:4] != b"PK\x01\x02":
            raise ValueError("ZIP 中央目录条目损坏")
        name_len, extra_len, comment_len = struct.unpack_from("<HHH", head, 28)
        name, extra, comment = src.read(name_len), src.read(extra_len), src.read(comment_len)
        pos += 46 + name_len + extra_len + comment_len
        usize, csize, local = (struct.unpack_from("<I", head, at)[0] for at in (24, 20, 42))
        fields, zip64_data = [], None
        ep = 0
        while ep < len(extra):
            if ep + 4 > len(extra):
                raise ValueError("ZIP extra field 损坏")
            tag, n = struct.unpack_from("<HH", extra, ep)
            field = extra[ep + 4:ep + 4 + n]
            if len(field) != n:
                raise ValueError("ZIP extra field 长度无效")
            if tag == 1:
                zip64_data = bytearray(field)
            else:
                fields.append(extra[ep:ep + 4 + n])
            ep += 4 + n
        before = 8 * ((usize == U32) + (csize == U32))
        if local == U32:
            if zip64_data is None or len(zip64_data) < before + 8:
                raise ValueError("ZIP64 缺少 local header 偏移")
            local = struct.unpack_from("<Q", zip64_data, before)[0]
        adjusted = local + delta
        if adjusted < 0:
            raise ValueError("ZIP 偏移不能为负数")
        if adjusted >= U32 or struct.unpack_from("<I", head, 42)[0] == U32:
            z = zip64_data if zip64_data is not None else bytearray()
            if len(z) < before:
                raise ValueError("ZIP64 大小字段缺失")
            if struct.unpack_from("<I", head, 42)[0] == U32:
                z[before:before + 8] = struct.pack("<Q", adjusted)
            else:
                z[before:before] = struct.pack("<Q", adjusted)
            zip64_data = z
            struct.pack_into("<I", head, 42, U32)
            struct.pack_into("<H", head, 6, max(45, struct.unpack_from("<H", head, 6)[0]))
        else:
            struct.pack_into("<I", head, 42, adjusted)
        if zip64_data is not None:
            fields.insert(0, struct.pack("<HH", 1, len(zip64_data)) + zip64_data)
        extra = b"".join(fields)
        struct.pack_into("<H", head, 30, len(extra))
        dst.write(head + name + extra + comment)
    new_cd_size = dst.tell() - cd_begin
    # Preserve only supported central records; reject silent truncation.
    if pos != start + relative_cd + cd_size:
        raise ValueError("ZIP 中央目录长度不符")
    needs64 = was64 or count >= 65535 or new_cd_off >= U32 or new_cd_size >= U32
    if needs64:
        zip64_off = new_cd_off + new_cd_size
        dst.write(struct.pack("<4sQHHIIQQQQ", b"PK\x06\x06", 44, 45, 45, 0, 0,
                              count, count, new_cd_size, new_cd_off))
        dst.write(struct.pack("<4sIQI", b"PK\x06\x07", 0, zip64_off, 1))
    tail = bytearray(eocd)
    struct.pack_into("<HHII", tail, 8, min(count, 65535), min(count, 65535),
                     min(new_cd_size, U32), min(new_cd_off, U32))
    dst.write(tail)
    return {"cd_relative": cd_begin, "cd_size": new_cd_size, "count": count, "zip64": needs64,
            "eocd": bytes(tail)}


def embed_in_mp4(video: Path, archive_path: Path, out_path: Path, kind: str) -> dict:
    video, archive_path, out_path = map(Path, (video, archive_path, out_path))
    if kind not in ("7z", "zip"):
        raise ValueError("门面视频只支持 7z/zip 归档载荷")
    if out_path.resolve() in (video.resolve(), archive_path.resolve()):
        raise ValueError("输出不能覆盖视频或归档")
    with video.open("rb") as vf:
        top = list(boxes(vf, 0, video.stat().st_size))
        if not top or top[0][2] != b"ftyp":
            raise ValueError("门面视频必须是 ftyp 在开头的 MP4 文件")
        # Fragmented MP4 has additional addressing schemes (tfhd/trun/sidx).
        # Refuse it until those have a complete relocation implementation.
        if any(b[2] in (b"moof", b"sidx") for b in top):
            raise ValueError("暂不支持碎片化 MP4，请先用 ffmpeg 转为普通 MP4")
        ftyp_end = top[0][1]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=out_path.parent) as payload:
            payload_size = archive_path.stat().st_size
            zip_info = None
            for _ in range(3):
                header = box_header(b"free", payload_size)
                payload_off = ftyp_end + len(header)
                if kind == "zip":
                    payload.seek(0)
                    payload.truncate()
                    with archive_path.open("rb") as arc:
                        zip_info = relocate_zip(arc, payload, payload_off)
                    measured = payload.tell()
                    if len(box_header(b"free", measured)) != len(header):
                        payload_size = measured
                        continue
                    payload_size = measured
                break
            header = box_header(b"free", payload_size)
            delta = len(header) + payload_size
            moovs = {}
            for off, size, typ, hdr in top[1:]:
                if typ == b"moov":
                    vf.seek(off)
                    data = vf.read(size)
                    if b"mvex" in data:
                        raise ValueError("暂不支持碎片化 MP4 的 mvex")
                    moovs[off] = data
            if not moovs:
                raise ValueError("MP4 缺少 moov")
            # Conversion grows moov boxes, moving all later media again. Iterate
            # to a stable layout; each stco can be promoted only once.
            rewritten = dict(moovs)
            for _ in range(100):
                growth = {off: len(rewritten[off]) - len(data) for off, data in moovs.items()}
                def shift(value):
                    return value + (delta if value >= ftyp_end else 0) + sum(
                        n for off, n in growth.items() if value >= off + len(moovs[off]))
                new = {off: rewrite_moov(data, shift) for off, data in moovs.items()}
                if all(len(new[o]) == len(rewritten[o]) for o in new):
                    rewritten = new
                    break
                rewritten = new
            else:
                raise ValueError("MP4 偏移转换未收敛")
            with out_path.open("wb") as out:
                copy_range(vf, out, 0, ftyp_end)
                out.write(header)
                if kind == "zip":
                    copy_range(payload, out, 0, payload_size)
                else:
                    with archive_path.open("rb") as arc:
                        copy_range(arc, out, 0, payload_size)
                for off, size, typ, hdr in top[1:]:
                    if off in rewritten:
                        out.write(rewritten[off])
                    else:
                        vf.seek(off)
                        # Explicit length allows appending the ZIP trailer after
                        # an original size=0 mdat box.
                        if vf.read(4) == b"\0\0\0\0":
                            if size > U32:
                                raise ValueError("超过 4GB 的 size=0 MP4 box 需先重封装")
                            out.write(struct.pack(">I", size))
                            copy_range(vf, out, off + 4, size - 4)
                        else:
                            copy_range(vf, out, off, size)
                if zip_info:
                    # Duplicate the small directory as well as EOCD. This keeps
                    # Python's strict ZIP readers compatible with the media gap.
                    trailer_off = out.tell()
                    cd_absolute = trailer_off + len(box_header(b"free", zip_info["cd_size"] + 98 + len(zip_info["eocd"])))
                    tail = io.BytesIO()
                    copy_range(payload, tail, zip_info["cd_relative"], zip_info["cd_size"])
                    if zip_info["zip64"] or cd_absolute >= U32:
                        z_off = cd_absolute + zip_info["cd_size"]
                        tail.write(struct.pack("<4sQHHIIQQQQ", b"PK\x06\x06", 44, 45, 45, 0, 0,
                                               zip_info["count"], zip_info["count"], zip_info["cd_size"], cd_absolute))
                        tail.write(struct.pack("<4sIQI", b"PK\x06\x07", 0, z_off, 1))
                    eocd = bytearray(zip_info["eocd"])
                    struct.pack_into("<I", eocd, 16, min(cd_absolute, U32))
                    tail.write(eocd)
                    out.write(box_header(b"free", tail.tell()))
                    out.write(tail.getvalue())
    return {"payload_offset": payload_off, "payload_size": payload_size, "kind": kind,
            "mode": "mp4-embedded"}


def embedded_payload(path):
    with Path(path).open("rb") as src:
        top = boxes(src, 0, Path(path).stat().st_size)
        first = next(top, None)
        if not first or first[2] != b"ftyp":
            return None
        for off, size, kind, hdr in top:
            if kind == b"free":
                src.seek(off + hdr)
                magic = src.read(6)
                fmt = "7z" if magic.startswith(b"7z\xbc\xaf\x27\x1c") else "zip" if magic.startswith(b"PK\x03\x04") else None
                if fmt:
                    return off + hdr, size - hdr, fmt
    return None


def extract_embedded(path, out):
    info = embedded_payload(path)
    if not info:
        raise ValueError("没有找到 MP4 内嵌归档")
    off, length, kind = info
    with Path(path).open("rb") as src, Path(out).open("wb") as dst:
        if kind == "zip":
            relocate_zip(src, dst, -off, start=off, length=length, offset_base=off)
        else:
            copy_range(src, dst, off, length)
    return Path(out)
