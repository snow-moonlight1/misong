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
