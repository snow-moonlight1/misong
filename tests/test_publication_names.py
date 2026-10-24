"""Custom remote names must never adopt an unrelated existing directory."""
import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from misong.rpa.drivers import BrowserDiskDriver, BaiduDriver, DriverBlocked


@pytest.mark.parametrize("baidu", [False, True])
def test_custom_folder_refuses_existing_before_navigation_or_upload(baidu):
    driver = BaiduDriver() if baidu else BrowserDiskDriver("quark")
    driver.check_restriction = AsyncMock()
    driver._root = AsyncMock()
    driver._wait_row = AsyncMock(return_value=Mock())
    driver._refresh_remote = AsyncMock(return_value={"misong-existing": 0})
    driver._row = AsyncMock(return_value=Mock())
    driver.profile = {}
    created = Mock()
    driver.require_new_folder("misong-existing", created)
    with pytest.raises(DriverBlocked, match="已存在"):
        asyncio.run(driver._open_folder(Mock(), "misong-existing"))
    created.assert_not_called()


def test_folder_confirmation_is_checkpointed_once():
    driver = BrowserDiskDriver("quark")
    created = Mock()
    driver.require_new_folder("misong-new", created)
    driver._check_folder_claim("misong-new", False)
    driver._confirm_folder_claim("misong-new")
    driver._check_folder_claim("misong-new", True)
    driver._confirm_folder_claim("misong-new")
    created.assert_called_once_with()
