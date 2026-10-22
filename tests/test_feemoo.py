"""Feemoo-specific targets and publish-before-folder behavior, without external accounts."""
import asyncio
from pathlib import Path

import pytest

from nde.rpa.drivers import BrowserDiskDriver, DriverBlocked, FeimaoDriver
from nde.sharing import ShareInfo, parse_share


@pytest.mark.parametrize("url", ["https://cm1.hk/s/abc123", "https://cm2.hk/s/abc123", "https://cm1.hk/f/folder123"])
def test_actual_feemoo_share_domains_and_pickup_semantics(url):
    info = parse_share(url + "\n分享取件码：abc123\n分享链接长期有效", "feimao")
    assert info.url == url and info.code == "" and info.expire == "长期有效"


def test_upload_targets_preserve_each_filename(monkeypatch):
    async def upload(self, page, files, folder):
        return [folder]
    monkeypatch.setattr(BrowserDiskDriver, "upload", upload)
    result = asyncio.run(FeimaoDriver().upload(None, [Path("guide.txt"), Path("guide.7z")], "nde-job"))
    assert result == ["nde-job/guide.txt", "nde-job/guide.7z"]


def share_fixture(monkeypatch):
    events = []
    selected = []
    class Check:
        def __init__(self, name):
            self.name = name
        async def click(self):
            selected[:] = [self.name]
            events.append(("select", self.name))
    class Row:
        def __init__(self, name):
            self.name = name
        async def wait_for(self, **kwargs):
            pass
        def locator(self, selector):
            return Check(self.name)
    class Page:
        async def goto(self, url, **kwargs):
            events.append(("root",))
    driver = FeimaoDriver()
    async def open_folder(page, folder):
        events.append(("open", folder))
    async def publish_selected(page):
        events.append(("publish-file", selected[0]))
        return ShareInfo("feimao", "https://cm1.hk/s/" + selected[0], expire="长期有效")
    async def folder_share(self, page, targets):
        events.append(("publish-folder", targets[0]))
        return ShareInfo("feimao", "https://cm1.hk/f/collection", expire="长期有效")
    monkeypatch.setattr(driver, "_open_folder", open_folder)
    monkeypatch.setattr(driver, "rows", lambda page, name: Row(name))
    monkeypatch.setattr(driver, "_share_selected", publish_selected)
    monkeypatch.setattr(BrowserDiskDriver, "share", folder_share)
    return driver, Page(), events


def test_single_hop_returns_file_link_not_empty_folder(monkeypatch):
    driver, page, events = share_fixture(monkeypatch)
    info = asyncio.run(driver.share(page, ["nde-job/guide.txt"]))
    assert info.url == "https://cm1.hk/s/guide.txt"
    assert ("publish-file", "guide.txt") in events
    assert not any(event[0] == "publish-folder" for event in events)


def test_publish_files_before_sharing_multi_file_folder(monkeypatch):
    driver, page, events = share_fixture(monkeypatch)
    info = asyncio.run(driver.share(page, ["nde-job/part001", "nde-job/part002"]))
    assert info.url == "https://cm1.hk/f/collection"
    assert events.index(("publish-file", "part001")) < events.index(("publish-folder", "nde-job"))
    assert events.index(("publish-file", "part002")) < events.index(("publish-folder", "nde-job"))


@pytest.mark.parametrize("targets", [[], ["nde-job"], ["nde-one/a", "nde-two/b"]])
def test_rejects_ambiguous_file_targets(monkeypatch, targets):
    driver, page, events = share_fixture(monkeypatch)
    with pytest.raises(DriverBlocked, match="明确文件目标"):
        asyncio.run(driver.share(page, targets))
    assert events == []
