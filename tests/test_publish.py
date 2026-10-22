"""Orchestration tests use fake disks; no personal account or external network."""
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Event

import pytest

from nde import pack, split
from nde.jobs import exclusive, fingerprint
from nde.publish import Paused, PublishOptions, import_share, prepare, publish
from nde.sharing import ShareInfo, parse_share
from nde.encoders import beast, hajimi, mojibake


class FakeRuntime:
    def __init__(self, fail_upload=0, fail_share=False):
        self.events = []
        self.count = 0
        self.fail_upload = fail_upload
        self.fail_share = fail_share
        self.payloads = {}

    @asynccontextmanager
    async def open(self, disk):
        self.events.append(("open", disk))
        runtime = self
        class Driver:
            def configure_share(self, options):
                runtime.events.append(("share-options", disk, options.to_dict()))

            async def upload(self, page, files, folder):
                runtime.count += 1
                if runtime.count == runtime.fail_upload:
                    raise RuntimeError("simulated connection failure")
                for file in files:
                    runtime.payloads[file.name] = file.read_bytes()
                    runtime.events.append(("upload", disk, file.name))
                return [folder]

            async def share(self, page, targets):
                runtime.events.append(("share", disk))
                if runtime.fail_share:
                    raise RuntimeError("simulated share failure")
                return ShareInfo(disk, f"https://{'pan.quark.cn' if disk == 'quark' else 'www.feemoo.com'}/s/{targets[0]}", "a123", "7天")
        yield Driver(), None


def make_job(tmp_path, form="direct", **kwargs):
    src = tmp_path / "input"
    src.mkdir()
    (src / "中文.txt").write_text("自己的资源 hello 世界 " * 30, encoding="utf-8")
    options = PublishOptions([src], tmp_path / "output", [pack.LayerSpec("lz4"), pack.LayerSpec("zip", "secret")],
                             size="100B", form=form, schemes=("beast", "hajimi"), **kwargs)
    return prepare(options, lambda _: None)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def run(path, runtime, **kwargs):
    return asyncio.run(publish(path, runtime=runtime, notify=lambda _: None, **kwargs))


def test_direct_pack_upload_share_roundtrip(tmp_path):
    path = make_job(tmp_path)
    rt = FakeRuntime()
    result = run(path, rt)
    assert load(path)["state"] == "complete"
    text = ShareInfo(**result["plan"]["final_share"]).text()
    assert beast.decode(result["copies"]["beast"], dialect="auto") == text
    assert hajimi.decode(result["copies"]["hajimi"]) == text
    body = path.parent / "body"
    first = next(body.glob("*.001"))
    artifact = split.join(first)
    restored = pack.unest(artifact, tmp_path / "restored", [None, "secret", None])
    assert any(p.name == "中文.txt" for root in restored for p in ([root] if root.is_file() else root.rglob("*")))
    assert "secret" not in path.read_text(encoding="utf-8")


def test_simple_body_before_guide_and_hop(tmp_path):
    path = make_job(tmp_path, "simple")
    rt = FakeRuntime()
    run(path, rt)
    assert rt.events[0] == ("open", "quark")
    assert rt.events.index(("share", "quark")) < rt.events.index(("upload", "feimao", "guide.txt"))
    guide = rt.payloads["guide.txt"].decode("utf-8")
    assert "https://pan.quark.cn/s/" in guide and "a123" in guide
    assert "待RPA" not in guide
    assert load(path)["final_share"]["disk"] == "feimao"


def test_multi_disk_copy_contains_all_links_and_resumes_without_upload(tmp_path):
    from nde.share_options import ShareOptions
    path = make_job(tmp_path, body_disks=("uc", "xunlei"), share_options=ShareOptions("7", "code"))
    rt = FakeRuntime()
    result = run(path, rt)
    assert [s["disk"] for s in result["plan"]["final_shares"]] == ["uc", "xunlei"]
    plain = (path.parent / "copy/share-plain.txt").read_text(encoding="utf-8").rstrip("\n")
    for share in result["plan"]["final_shares"]:
        assert share["url"] in plain
    assert hajimi.decode(result["copies"]["hajimi"]) == plain
    assert ("share-options", "uc", {"expiry": "7", "access": "code"}) in rt.events
    again = FakeRuntime()
    run(path, again)
    assert again.events == []


def test_replacing_any_body_link_invalidates_multi_disk_guide(tmp_path):
    path = make_job(tmp_path, "simple", body_disks=("quark", "uc"))
    run(path, FakeRuntime())
    import_share(path, "body-uc", "https://drive.uc.cn/s/replacement")
    hop = next(s for s in load(path)["stages"] if s["id"] == "hop")
    assert hop["state"] == "pending" and hop["files"] == [] and "share" not in hop
    rt = FakeRuntime()
    run(path, rt)
    assert "https://drive.uc.cn/s/replacement" in rt.payloads["guide.txt"].decode("utf-8")
    assert not any(event[:1] == ("open",) and event[1] in ("quark", "uc") for event in rt.events)


def test_unsupported_policy_rejected_before_pack(tmp_path):
    from nde.share_options import ShareOptions
    with pytest.raises(ValueError, match="不支持"):
        make_job(tmp_path, body_disks=("uc", "xunlei"), share_options=ShareOptions("60", "none"))
    assert not (tmp_path / "output").exists()


def test_upload_failure_resumes_only_missing_files(tmp_path):
    path = make_job(tmp_path)
    rt = FakeRuntime(fail_upload=2)
    with pytest.raises(RuntimeError):
        run(path, rt)
    plan = load(path)
    assert len(plan["stages"][0]["uploaded"]) == 1
    assert plan["state"] == "blocked"
    resumed = FakeRuntime()
    run(path, resumed)
    first_name = next(iter(plan["stages"][0]["uploaded"]))
    assert all(e[-1] != Path(first_name).name for e in resumed.events if e[0] == "upload")
    assert len([e for e in resumed.events if e[0] == "upload"]) == len(plan["stages"][0]["files"]) - 1


def test_share_failure_does_not_reupload(tmp_path):
    path = make_job(tmp_path)
    with pytest.raises(RuntimeError):
        run(path, FakeRuntime(fail_share=True))
    assert load(path)["stages"][0]["state"] == "uploaded"
    rt = FakeRuntime()
    run(path, rt)
    assert not [e for e in rt.events if e[0] == "upload"]


def test_completed_job_never_opens_disk_again(tmp_path):
    path = make_job(tmp_path, "simple")
    run(path, FakeRuntime())
    rt = FakeRuntime()
    run(path, rt)
    assert rt.events == []


def test_changed_part_rejected_before_network(tmp_path):
    path = make_job(tmp_path)
    first = Path(load(path)["stages"][0]["files"][0]["path"])
    first.write_bytes(b"changed")
    rt = FakeRuntime()
    with pytest.raises(ValueError, match="文件已改变"):
        run(path, rt)
    assert rt.events == []


def test_complex_hop_requires_password_and_resumes(tmp_path):
    path = make_job(tmp_path, "complex")
    with pytest.raises(Paused):
        run(path, FakeRuntime())
    assert load(path)["state"] == "paused"
    rt = FakeRuntime()
    run(path, rt, hop_password="hop-secret")
    assert "guide.7z" in rt.payloads
    assert not any(e[:2] == ("open", "quark") for e in rt.events)
    files = pack.unest(path.parent / "guide.7z", tmp_path / "hop-out", ["hop-secret"])
    guide = next(p for root in files for p in ([root] if root.is_file() else root.rglob("*")) if p.name == "guide.txt")
    assert "https://pan.quark.cn/s/" in guide.read_text(encoding="utf-8")
    assert "hop-secret" not in path.read_text(encoding="utf-8")


def test_cancel_preserves_plan(tmp_path):
    path = make_job(tmp_path)
    event = Event()
    event.set()
    rt = FakeRuntime()
    with pytest.raises(Paused):
        run(path, rt, cancel=event)
    assert rt.events == [] and load(path)["state"] == "paused"


def test_output_inside_input_rejected(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    with pytest.raises(ValueError, match="资源内部"):
        prepare(PublishOptions([src], src / "output"))
    assert not (src / "output").exists()


def test_existing_output_rejected(tmp_path):
    src = tmp_path / "file.txt"
    src.write_text("hello")
    with pytest.raises(FileExistsError):
        prepare(PublishOptions([src], tmp_path))


def test_job_lock_prevents_parallel_run(tmp_path):
    path = make_job(tmp_path)
    with exclusive(path.with_suffix(".lock")):
        with pytest.raises(RuntimeError, match="正在使用"):
            run(path, FakeRuntime())


@pytest.mark.parametrize("text,disk,url,code", [
    ("链接：https://pan.quark.cn/s/abc?pwd=ab12", "夸克", "https://pan.quark.cn/s/abc?pwd=ab12", "ab12"),
    ("https://www.feemoo.com/s/hello 提取码：XYZ1", "飞猫盘", "https://www.feemoo.com/s/hello", "XYZ1"),
    ("https://pan.quark.cn/s/hello", "quark", "https://pan.quark.cn/s/hello", ""),
    ("解压密码:zipPW https://pan.quark.cn/s/demo 提取码:xy12", "quark", "https://pan.quark.cn/s/demo", "xy12"),
    ("https://pan.quark.cn/s/demo?pwd=ab12 解压密码:zipPW", "quark", "https://pan.quark.cn/s/demo?pwd=ab12", "ab12"),
])
def test_share_parser(text, disk, url, code):
    info = parse_share(text, disk)
    assert info.url == url and info.code == code


@pytest.mark.parametrize("text", ["https://evil.example/s/abc", "https://pan.quark.cn/", "no link",
    "https://pan.quark.cn/s/a https://pan.quark.cn/s/b", "https://pan.quark.cn.evil.example/s/a"])
def test_reject_bad_or_ambiguous_share(text):
    with pytest.raises(ValueError):
        parse_share(text, "quark")


def test_cli_prepare_and_import_share(tmp_path):
    from nde.cli import main
    src = tmp_path / "src.txt"
    src.write_text("test")
    out = tmp_path / "job"
    assert main(["publish", str(src), "-o", str(out), "--prepare", "-L", "zip", "--schemes", "beast,hajimi"]) == 0
    path = out / "relay-plan.json"
    assert main(["share-import", "--plan", str(path), "--stage", "body", "--text", "https://pan.quark.cn/s/demo 提取码:1234"]) == 0
    rt = FakeRuntime()
    result = run(path, rt)
    assert result["plan"]["final_share"]["code"] == "1234" and rt.events == []


def test_replacing_body_link_rebuilds_downstream_guide(tmp_path):
    path = make_job(tmp_path, "simple")
    run(path, FakeRuntime())
    old = load(path)
    old_folder = old["stages"][0]["folder"]
    import_share(path, "body", "https://pan.quark.cn/s/replacement 提取码:9876")
    changed = load(path)
    assert changed["state"] == "prepared" and "final_share" not in changed
    assert next(s for s in changed["stages"] if s["id"] == "body")["manual"] is True  # not a driver success
    hop = changed["stages"][0]
    assert hop["files"] == [] and hop["uploaded"] == {} and "share" not in hop
    assert hop["folder"] != old_folder
    rt = FakeRuntime()
    run(path, rt)
    assert ("open", "quark") not in rt.events
    guide = rt.payloads["guide.txt"].decode("utf-8")
    assert "replacement" in guide and "9876" in guide


def test_copy_failure_reuses_shares_on_retry(tmp_path, monkeypatch):
    import nde.publish as module
    path = make_job(tmp_path)
    original = module.write_copy
    def fail(*args, **kwargs):
        raise RuntimeError("simulated encoder unavailable")
    monkeypatch.setattr(module, "write_copy", fail)
    with pytest.raises(RuntimeError):
        run(path, FakeRuntime())
    assert load(path)["stages"][0]["share"]["url"]
    monkeypatch.setattr(module, "write_copy", original)
    rt = FakeRuntime()
    run(path, rt)
    assert rt.events == []


def test_three_copy_versions_roundtrip():
    import shutil
    from nde.encoders.mojibake import BRIDGE
    from nde.sharing import encode_copy
    if not shutil.which("node") or not BRIDGE.exists():
        pytest.skip("Node vendored bridge unavailable")
    text = ShareInfo("quark", "https://pan.quark.cn/s/fixture", "a123", "永久有效").text()
    result = encode_copy(text)
    assert beast.decode(result["beast"], dialect="auto") == text
    assert mojibake.decode(result["mojibake"]) == text
    assert hajimi.decode(result["hajimi"]) == text


@pytest.mark.parametrize("scheme", ["", "unknown", "../output", "trunc"])
def test_invalid_schemes_rejected_before_pack(tmp_path, scheme):
    src = tmp_path / "file.txt"
    src.write_text("test")
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="文案方案"):
        prepare(PublishOptions([src], out, schemes=(scheme,)))
    assert not out.exists()
