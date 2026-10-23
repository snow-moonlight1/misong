"""Provider coverage identifies link support separately from live driver verification."""
import pytest

from nde.providers import disk_name, PROVIDERS
from nde.sharing import parse_share


@pytest.mark.parametrize("name,canonical", [
    ("百度网盘", "baidu"), ("UC网盘", "uc"), (" uc ", "uc"),
    ("迅雷云盘", "xunlei"), ("123", "123pan"), ("123云盘", "123pan"),
])
def test_aliases(name, canonical):
    assert disk_name(name) == canonical


@pytest.mark.parametrize("disk,url", [
    ("百度网盘", "https://pan.baidu.com/s/1fixture?pwd=a123"),
    ("UC网盘", "https://drive.uc.cn/s/fixture?pwd=a123"),
    ("迅雷云盘", "https://pan.xunlei.com/s/fixture?pwd=a123"),
    ("123云盘", "https://www.123865.com/s/fixture?pwd=a123"),
    ("123云盘", "https://fixture.share.123pan.cn/123pan/Abc-test?pwd=a123"),
])
def test_share_links_for_new_providers(disk, url):
    info = parse_share(url, disk)
    assert info.url == url and info.code == "a123"
    assert info.disk in PROVIDERS


@pytest.mark.parametrize("url,disk", [
    ("https://pan.baidu.com/disk/main#/index", "baidu"),
    ("https://pan.xunlei.com/login/", "xunlei"),
    ("https://drive.uc.cn/list", "uc"),
    ("https://user.123pan.cn/centerlogin?redirect_url=example", "123pan"),
    ("https://yun.123pan.cn/?homeFilePath=12345", "123pan"),
    ("https://yun.123pan.cn/123pan/fake", "123pan"),
    ("https://fixture.share.123pan.cn/123pan/", "123pan"),
])
def test_login_and_file_manager_urls_are_rejected(url, disk):
    with pytest.raises(ValueError):
        parse_share(url, disk)


def test_feemoo_private_link_fragment_and_pickup_code():
    info = parse_share("https://cm2.hk/f/fixture#密码：abC2\n取件码：fixture 密码：abC2", "feimao")
    assert info.code == "abC2" and "/f/fixture" in info.url


def test_feemoo_password_label_before_the_url_does_not_capture_the_scheme():
    info = parse_share("分享密码\nhttps://cm2.hk/f/fixture#密码：abC2\n分享链接长期有效", "feimao")
    assert info.code == "abC2"
    assert info.url.endswith("#密码：abC2")
    assert info.expire == "长期有效"
