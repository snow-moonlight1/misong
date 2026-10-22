"""Browser choices persist per account without sharing a personal browser profile."""
import pytest

from nde.cli import build_parser
from nde.jobs import save_json
from nde.rpa.runtime import BrowserRuntime


def test_choice_is_per_account_and_explicit_option_wins(tmp_path):
    save_json(tmp_path / "feimao-browser.json", {"channel": "chrome"})
    runtime = BrowserRuntime(state_dir=tmp_path)
    assert runtime.browser_for("feimao") == "chrome"
    assert runtime.browser_for("quark") == "chromium"
    assert BrowserRuntime(state_dir=tmp_path, browser_channel="msedge").browser_for("feimao") == "msedge"
    with pytest.raises(ValueError):
        BrowserRuntime(browser_channel="unknown")
    save_json(tmp_path / "quark-browser.json", {"channel": "unknown"})
    with pytest.raises(ValueError):
        runtime.browser_for("quark")


@pytest.mark.parametrize("args", [
    ["account", "login", "feimao", "--browser", "chrome"],
    ["publish", "--plan", "plan.json", "--browser", "chrome"],
])
def test_cli_accepts_official_browser(args):
    assert build_parser().parse_args(args).browser == "chrome"


def test_session_storage_origin_is_limited_to_approved_hosts_and_transport():
    profile = {"url": "https://www.nde.test/", "hosts": ["nde.test", "nde-alias.test"]}
    origin = BrowserRuntime._session_origin
    assert origin(profile, "https://nde.test/files") == "https://nde.test"
    assert origin(profile, "https://www.nde-alias.test/files") == "https://www.nde-alias.test"
    for url in ("https://unrelated.test/", "https://other.nde.test/", "http://nde.test/",
                "https://nde.test:8443/", "https://user@nde.test/", "https://nde.test:invalid/"):
        assert origin(profile, url) is None
