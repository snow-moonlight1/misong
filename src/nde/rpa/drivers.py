"""Conservative DOM drivers; selectors can be corrected without changing the engine."""
from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from ..publish import Paused
from ..sharing import HOSTS, ShareInfo, parse_share
from ..share_options import ShareOptions, EXPIRY_LABELS


class DriverBlocked(RuntimeError):
    pass


class AccountActionRequired(Paused):
    """Account setup must be completed by its owner in the provider's UI."""
    pass


PROFILES = {
    "quark": {
        "url": "https://pan.quark.cn/", "hosts": list(HOSTS["quark"]),
        "logged_in": ".file-list, .file-list-container, .file-list-content, .file-list-table",
        "rows": "tr.ant-table-row",
        "upload": "input[type=file]", "new_folder": "新建文件夹",
        "folder_input": "input.input-edit", "folder_submit": "Enter",
        "folder_ready": ".bcrumb-filename",
        "refresh": ".fl-refresh",
        "listing_url": "/file/sort",
        "confirm": "确定", "share": "分享", "create_share": "创建分享",
        "dialog": ".ant-modal:visible, [role=dialog]:visible", "expire": "平台默认（以分享弹窗为准）",
    },
    "feimao": {
        "url": "https://www.feemoo.com/files", "hosts": list(HOSTS["feimao"]),
        "logged_in": ".user_info .name", "logged_in_nonempty": True,
        "persistent": True,
        "session_storage": True,
        "promotion_close": ".couponReceive .closeIcon",
        "login_hint": "飞猫可优先用手机 APP 扫码；本次密码登录遇到极验 60500 时请勿连续重试。",
        "session_invalid": "当前设备已被下线，如非本人操作请及时修改密码，避免所存储的数据丢失。",
        "rows": "#fc-content .file-item-hover",
        "upload": "input[type=file]", "new_folder": "新建文件夹",
        "upload_trigger": ".btn-add .fmbtn",
        "folder_input": ".openFoldername .edit-input input", "folder_submit": "Enter",
        "folder_ready": ".one .small-name", "refresh": "button.icon-refresh",
        "listing_ready": "#fc-content .file-item-hover, #upload-0", "folder_departed": True,
        "checkbox": ".icon_checks_wrap", "share_scope": "#fc-content .multiple-operation",
        "share_more": "更多",
        "account_prompt": "请绑定手机号后再继续操作",
        "share_notice": "为了共同维护良好的网络环境，每次分享的文件将会经过机器检测，请勿分享非法文件。",
        "confirm": "确定", "share": "分享", "create_share": "创建链接",
        "dialog": ".shareDialog:visible", "expire": "平台默认（以分享弹窗为准）",
    },
    "uc": {
        "url": "https://drive.uc.cn/list#/list/all", "hosts": list(HOSTS["uc"]),
        "persistent": True, "session_storage": True,
        "logged_in": "[class*='AsideFooter--tit-left--']",
        "logged_in_pattern": r"\d+(?:\.\d+)?(?:[KMGT]B?|B)\s*/\s*\d+(?:\.\d+)?(?:[KMGT]B?|B)",
        "rows": "tr.ant-table-row", "root_text": "我的文件", "root_role": "link",
        "upload": "input[type=file]", "upload_trigger": "button:has-text('上传文件')",
        "new_folder": "新建文件夹", "folder_input": "input.input-edit", "folder_submit": "Enter",
        "folder_ready": ".bcrumb-filename", "folder_departed": True,
        "account_prompt": "绑定手机号码", "confirm": "确定", "share": "分享",
        "create_share": "创建分享链接", "dialog": "[role=dialog]:visible",
        "expire": "平台默认（以分享设置为准）",
    },
    "xunlei": {
        "url": "https://pan.xunlei.com/", "hosts": list(HOSTS["xunlei"]),
        "persistent": True, "session_storage": True,
        "logged_in": "input[placeholder='搜索我的文件']", "logged_in_text": r"^我的分享$",
        "rows": "li.normal-item[class*='SourceListItem__item--']",
        "root_text": "全部", "new_folder_menu": "添加", "new_folder": "新建文件夹",
        "folder_input": ".sdff input", "folder_submit": "Enter", "folder_departed": True,
        "folder_query": "path", "folder_query_name": True,
        "upload": "input[type=file]", "upload_menu": "添加", "upload_button": "上传文件",
        "confirm": "确定", "share": "分享", "create_share": "创建链接",
        "dialog": ".dialog-web-create-share:visible", "uncheck_share": "允许快速访问分享链接",
        "share_code": ".code input", "require_share_code": True,
        "expire": "不限（平台分享设置）",
    },
    "123pan": {
        "url": "https://yun.123pan.cn/", "hosts": list(HOSTS["123pan"]),
        "persistent": True, "session_storage": True,
        "promotion_close": "button[class*='splashScreenModal__close_']",
        "logged_in": "[class*='totalUsageText_']",
        "logged_in_pattern": r"\d+(?:\.\d+)?[KMGT]?B\s*/\s*\d+(?:\.\d+)?[KMGT]?B",
        "rows": "[role=row].editable-row", "root_text": "全部文件", "root_role": "link",
        "new_folder": "新建", "folder_input": "input[placeholder='请输入名称']", "confirm": "确定",
        "folder_departed": True, "folder_query": "homeFilePath",
        "upload": "input[type=file]", "upload_trigger": "button:has-text('上传')",
        "share": "分享", "create_share": "创建链接", "dialog": ".create-share-modal:visible",
        "share_trigger": ".file-operator-group > .file-operator-group-button:text-is('分享')",
        "free_share_option": "无提取码", "free_share_selected": "[class*='selectedTextItem_']",
        "expire": "平台默认（以分享设置为准）",
    },
    "baidu": {
        "url": "https://pan.baidu.com/disk/main", "hosts": list(HOSTS["baidu"]),
        "persistent": True, "enter": "去登录",
        "logged_in": ".wp-s-aside-nav", "login_user": ".nd-user-info",
        "login_hint": "百度网盘请在软件窗口扫码登录；登录态只保存在本机专用配置中。",
        "rows": ".wp-s-pan-table__body-row", "row_name": "a.list-name-text",
        "toolbar": ".wp-s-agile-tool-bar",
        "new_folder": "新建文件夹", "folder_input": "textarea.u-textarea__inner",
        "folder_submit": "Enter", "folder_query": "path",
        "upload": "input[type=file][name=html5uploader]",
        "checkbox": ".wp-s-pan-table__body-row--checkbox-block",
        "share_dialog": '[role=dialog][aria-label^="分享文件(夹):"]',
        "expire": "平台默认（以分享弹窗为准）",
    },
}


class DiskDriver:
    name = "base"
    status = "probe"

    async def ensure_login(self, context):
        raise NotImplementedError

    async def upload(self, page, files: list[Path], folder: str) -> list[str]:
        raise NotImplementedError

    async def share(self, page, entry_ids: list[str]) -> ShareInfo:
        raise NotImplementedError


class BrowserDiskDriver(DiskDriver):
    def __init__(self, name, profile=None, *, notify=print, cancel=None, timeout=1800, login_timeout=300,
                 interactive=True):
        self.name = name
        self.profile = dict(profile or PROFILES[name])
        self.notify = notify
        self.cancel = cancel
        self.timeout = timeout
        self.login_timeout = login_timeout
        self.interactive = interactive
        self.folder = None
        self.remote_sizes = None
        self.remote_parent = None
        self.share_options = ShareOptions()
        self.share_expiry = ""

    def configure_share(self, options):
        options.validate_disk(self.name)
        self.share_options = options

    def check_cancel(self):
        if self.cancel and self.cancel.is_set():
            raise Paused("已暂停，上传检查点已保留")

    async def _visible(self, locator):
        for item in await locator.all():
            if await item.is_visible():
                return item
        return None

    async def _wait_visible(self, page, selector, timeout=15):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.check_cancel()
            element = await self._visible(page.locator(selector))
            if element:
                return element
            await asyncio.sleep(.2)
        raise DriverBlocked(f"{self.name} 等待控件超时，请探测当前页面并更新适配配置")

    async def _text(self, page, text):
        # Prefer exact labels; never click unrelated fuzzy matches.
        locator = page.get_by_text(text, exact=True)
        visible = [x for x in await locator.all() if await x.is_visible()]
        if len(visible) != 1:
            raise DriverBlocked(f"{self.name} 找不到唯一的“{text}”控件；请更新网盘适配配置")
        return visible[0]

    async def ensure_login(self, context):
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(self.profile["url"], wait_until="domcontentloaded", timeout=60000)
        if self.profile.get("enter"):
            enter = page.get_by_text(self.profile["enter"], exact=True)
            if await enter.count() == 1 and await enter.is_visible():
                await enter.click()
        end = None if self.login_timeout is None else time.monotonic() + self.login_timeout
        self.notify(f"{self.name}：检查登录；需要时请在浏览器完成扫码或验证")
        if self.profile.get("login_hint"):
            self.notify(self.profile["login_hint"])
        while end is None or time.monotonic() < end:
            self.check_cancel()
            if not context.pages:
                raise Paused("登录窗口已关闭；未完成的任务可以继续")
            for candidate in context.pages:
                if not candidate.is_closed() and await self.is_logged_in(candidate):
                    await self._dismiss_promotions(candidate)
                    self.notify(f"{self.name}：登录就绪")
                    return candidate
            await asyncio.sleep(.5)
        self.status = "blocked"
        raise DriverBlocked(f"{self.name} 登录未完成或页面结构已变化；请重新登录/探测")

    async def is_logged_in(self, page):
        invalid = self.profile.get("session_invalid")
        if invalid and await self._visible(page.get_by_text(invalid, exact=True)):
            return False
        marker = await self._visible(page.locator(self.profile["logged_in"]))
        if not marker:
            return False
        text = (await marker.inner_text()).strip()
        if self.profile.get("logged_in_nonempty") and not text:
            return False
        if self.profile.get("logged_in_pattern") and not re.search(self.profile["logged_in_pattern"], text, re.I):
            return False
        if self.profile.get("logged_in_text"):
            return bool(await self._visible(page.get_by_text(re.compile(self.profile["logged_in_text"], re.I))))
        return True

    def rows(self, page, name):
        # Exact filename text, scoped to file rows, not the global transfer queue.
        return page.locator(self.profile["rows"]).filter(has=page.get_by_text(name, exact=True))

    async def _dismiss_promotions(self, page):
        if self.profile.get("promotion_close"):
            close = await self._visible(page.locator(self.profile["promotion_close"]))
            if close and await close.evaluate("""el => {
                const r=el.getBoundingClientRect();
                const hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
                return r.width>0 && r.height>0 && (hit===el || el.contains(hit));
            }"""):
                await close.click(timeout=2000)

    async def check_restriction(self, page):
        await self._dismiss_promotions(page)
        invalid = self.profile.get("session_invalid")
        if invalid and await self._visible(page.get_by_text(invalid, exact=True)):
            raise AccountActionRequired("当前设备会话已下线，请在账号页重新扫码登录后恢复任务")
        restriction = page.get_by_text(re.compile("账号涉嫌违规已被封禁|账号已被封禁|账号被冻结"))
        for element in await restriction.all():
            # Quark keeps a ban-message template at y=-52 even on working accounts.
            # is_visible() alone returns True for offscreen templates.
            if await element.is_visible() and await element.evaluate("""el => {
                const r=el.getBoundingClientRect();
                return r.bottom>0 && r.right>0 && r.top<innerHeight && r.left<innerWidth
                       && getComputedStyle(el).opacity!=='0';
            }"""):
                self.status = "blocked"
                raise DriverBlocked("网盘当前显示账号受限提示；任务检查点已保留，请先确认平台允许操作")

    async def _refresh_remote(self, page):
        """Observe the site's own listing response after its normal refresh action.

        This does not send a handcrafted API request or implement private upload signing.
        Waiting for the server result avoids reuploading before React finishes rendering.
        """
        pattern = self.profile.get("listing_url")
        if not pattern:
            return None
        refresh = await self._wait_visible(page, self.profile["refresh"])
        def matches(response):
            if pattern not in urlsplit(response.url).path or response.request.method != "GET":
                return False
            parent = parse_qs(urlsplit(response.url).query).get("pdir_fid", [None])[0]
            return self.remote_parent is None or parent == self.remote_parent
        async with page.expect_response(matches, timeout=15000) as result:
            await refresh.click()
        response = await result.value
        if response.status != 200:
            raise DriverBlocked("网盘刷新文件列表失败，保留检查点后重试")
        data = await response.json()
        if data.get("code", 0) != 0 or not isinstance(data.get("data", {}).get("list"), list):
            raise DriverBlocked("网盘返回的列表结构已变化，需要重新探测")
        sizes = {entry["file_name"]: entry.get("size", 0) for entry in data["data"]["list"]}
        return sizes

    async def _row(self, page, name):
        rows = self.rows(page, name)
        if await rows.count() != 1:
            return None
        row = rows.first
        return row if await row.is_visible() else None

    async def _account_gate(self, page):
        prompt = self.profile.get("account_prompt")
        if not prompt or not await self._visible(page.get_by_text(prompt, exact=True)):
            return False
        message = f"{self.name}：{prompt}。请由账号所有者在网盘窗口完成，随后继续任务。"
        if not self.interactive:
            raise AccountActionRequired(message + " 当前是无头模式，请改为有头模式。")
        self.notify(message + " 程序正在等待，不会输入手机号或验证码。")
        end = None if self.login_timeout is None else time.monotonic() + self.login_timeout
        while end is None or time.monotonic() < end:
            self.check_cancel()
            if not await self._visible(page.get_by_text(prompt, exact=True)):
                return True
            await asyncio.sleep(.25)
        raise AccountActionRequired(message + " 等待超时，检查点已保留。")

    async def _trigger_upload(self, page, path):
        """Use the provider's upload action, including its account prerequisite gate."""
        if self.profile.get("upload_menu"):
            await (await self._text(page, self.profile["upload_menu"])).click()
        if self.profile.get("upload_trigger"):
            trigger = await self._wait_visible(page, self.profile["upload_trigger"])
        else:
            trigger = await self._text(page, self.profile["upload_button"])
        chooser = asyncio.get_running_loop().create_future()
        def selected(value):
            if not chooser.done():
                chooser.set_result(value)
        page.on("filechooser", selected)
        try:
            await trigger.click()
            end, gates = time.monotonic() + 15, 0
            while time.monotonic() < end:
                self.check_cancel()
                if await self._account_gate(page):
                    gates += 1
                    if gates > 2:
                        raise AccountActionRequired("账号前置操作尚未完成，请完成后恢复任务")
                    await trigger.click()
                    end = time.monotonic() + 15
                if chooser.done():
                    await chooser.result().set_files(str(path))
                    return
                await asyncio.sleep(.2)
            raise DriverBlocked("点击上传后未出现文件选择器；请检查账号前置提示或更新适配")
        finally:
            page.remove_listener("filechooser", selected)
            if not chooser.done():
                chooser.cancel()

    async def _open_folder(self, page, folder):
        await self.check_restriction(page)
        if self.folder == folder:
            return
        root_files = await self._refresh_remote(page)
        if self.profile.get("listing_ready"):
            await self._wait_visible(page, self.profile["listing_ready"])
        row = await self._row(page, folder)
        if row is None and root_files is not None and folder in root_files:
            await self.rows(page, folder).wait_for(state="visible", timeout=15000)
            row = await self._row(page, folder)
        if row is None:
            if self.profile.get("new_folder_menu"):
                await (await self._text(page, self.profile["new_folder_menu"])).click()
            await (await self._text(page, self.profile["new_folder"])).click()
            entry = await self._wait_visible(page, self.profile["folder_input"])
            await entry.fill(folder)
            if self.profile.get("folder_submit"):
                await entry.press(self.profile["folder_submit"])
            else:
                await (await self._text(page, self.profile["confirm"])).click()
            for _ in range(40):
                self.check_cancel()
                row = await self._row(page, folder)
                if row:
                    break
                await asyncio.sleep(.25)
        if row is None:
            raise DriverBlocked("未能确认任务目录已创建；未选择任何其他文件")
        self.remote_parent = await row.get_attribute("data-row-key")
        old_url = page.url
        # Quark attaches folder navigation to the filename, not the entire row.
        await row.get_by_text(folder, exact=True).dblclick()
        if self.profile.get("folder_query"):
            key = self.profile["folder_query"]
            def entered(url):
                value = parse_qs(urlsplit(str(url)).query).get(key, [""])[0]
                return str(url) != old_url and bool(value and value != "0") and (not self.profile.get("folder_query_name") or value == "/" + folder)
            await page.wait_for_url(entered, timeout=15000)
        if self.profile.get("folder_ready"):
            ready = page.locator(self.profile["folder_ready"]).filter(has_text=folder)
            await ready.wait_for(state="visible", timeout=15000)
        if self.profile.get("folder_departed"):
            # Feemoo updates its breadcrumb before replacing the parent's virtual rows.
            await self.rows(page, folder).wait_for(state="hidden", timeout=15000)
        if self.profile.get("listing_ready"):
            await self._wait_visible(page, self.profile["listing_ready"])
        self.remote_sizes = await self._refresh_remote(page)
        self.folder = folder

    async def upload(self, page, files: list[Path], folder: str) -> list[str]:
        await self._open_folder(page, folder)
        for path in files:
            self.check_cancel()
            existing = (path.name in self.remote_sizes if self.remote_sizes is not None else
                        bool(await self._row(page, path.name)))
            if existing:
                if self.remote_sizes is not None and self.remote_sizes[path.name] != path.stat().st_size:
                    raise DriverBlocked(f"远端同名文件大小不符，请检查任务目录：{path.name}")
                # Dedicated UUID folder: this may be the last upload before a process crash.
                self.notify(f"远端已存在，复用任务目录内文件：{path.name}")
                continue
            chooser = page.locator(self.profile["upload"])
            if self.profile.get("upload_trigger") or self.profile.get("upload_menu"):
                await self._trigger_upload(page, path)
            elif not await chooser.count():
                upload_label = self.profile.get("upload_button", "上传文件")
                trigger = await self._text(page, upload_label)
                async with page.expect_file_chooser() as choice:
                    await trigger.click()
                await (await choice.value).set_files(str(path))
            else:
                # Some sites offer one input for files and another for directories.
                file_inputs = chooser.locator("xpath=.")
                chosen = None
                for entry in await file_inputs.all():
                    if await entry.get_attribute("webkitdirectory") is None:
                        chosen = entry
                        break
                if chosen is None:
                    raise DriverBlocked("只有目录上传框，未找到文件上传框")
                await chosen.set_input_files(str(path))
            end = time.monotonic() + self.timeout
            refresh_interval = min(5, max(.2, self.timeout / 3))
            next_refresh = time.monotonic() + refresh_interval
            next_notice = time.monotonic() + 15
            while time.monotonic() < end:
                self.check_cancel()
                await self.check_restriction(page)
                confirmed = (self.remote_sizes.get(path.name) == path.stat().st_size if self.remote_sizes is not None else
                             bool(await self._row(page, path.name)))
                if confirmed:
                    break
                if time.monotonic() >= next_refresh and self.profile.get("refresh"):
                    refresh = page.locator(self.profile["refresh"])
                    if await refresh.count() == 1 and await refresh.is_visible():
                        # Refresh only the server file listing; never reload/interrupt an active upload.
                        if self.profile.get("listing_url"):
                            self.remote_sizes = await self._refresh_remote(page)
                        else:
                            await refresh.click()
                    next_refresh = time.monotonic() + refresh_interval
                if time.monotonic() >= next_notice:
                    self.notify(f"等待网盘确认上传：{path.name}")
                    next_notice = time.monotonic() + 15
                await asyncio.sleep(.75)
            else:
                raise DriverBlocked(f"{path.name} 上传未确认完成，检查配额、大小限制或验证弹窗后继续")
        return [folder]

    async def share(self, page, entry_ids: list[str]) -> ShareInfo:
        await self.check_restriction(page)
        if len(entry_ids) != 1:
            raise DriverBlocked("只能分享当前任务的独立目录")
        folder = entry_ids[0]
        # Return to the known root and locate exactly our isolated folder.
        if self.profile.get("root_text"):
            root = (page.get_by_role(self.profile["root_role"], name=self.profile["root_text"], exact=True)
                    if self.profile.get("root_role") else await self._text(page, self.profile["root_text"]))
            await root.click()
        else:
            await page.goto(self.profile["url"], wait_until="domcontentloaded", timeout=60000)
        self.folder = self.remote_parent = self.remote_sizes = None
        await self.rows(page, folder).wait_for(state="visible", timeout=15000)
        row = None
        for _ in range(40):
            self.check_cancel()
            row = await self._row(page, folder)
            if row:
                break
            await asyncio.sleep(.25)
        if row is None:
            raise DriverBlocked("未找到当前任务目录；拒绝分享不确定的文件")
        checkbox = row.locator(self.profile.get("checkbox", "input[type=checkbox], [role=checkbox], .ant-checkbox-wrapper"))
        if self.profile.get("share_selection") == "context":
            await row.get_by_text(folder, exact=True).click(button="right")
        elif await checkbox.count():
            await checkbox.first.click()
        else:
            await row.click()
        return await self._share_selected(page)

    async def _click_share(self, page):
        if self.profile.get("share_trigger"):
            await (await self._wait_visible(page, self.profile["share_trigger"])).click()
            return
        scope = page.locator(self.profile["share_scope"]) if self.profile.get("share_scope") else page
        if self.profile.get("share_more") and not await self._visible(scope.get_by_text(self.profile["share"], exact=True)):
            await (await self._text(scope, self.profile["share_more"])).click()
        await (await self._text(scope, self.profile["share"])).click()

    async def _share_selected(self, page):
        await self._click_share(page)
        for _ in range(40):
            self.check_cancel()
            if await self._account_gate(page):
                await self._click_share(page)
            notice = self.profile.get("share_notice")
            if notice and await self._visible(page.get_by_text(notice, exact=True)):
                acknowledgement = page.locator(".el-dialog:visible").filter(has_text=notice)
                await acknowledgement.get_by_role("button", name=re.compile(r"^确\s*认$")).click()
            dialog = await self._visible(page.locator(self.profile["dialog"]))
            if dialog:
                break
            await asyncio.sleep(.25)
        else:
            raise DriverBlocked("分享弹窗未出现")
        created = False
        pending_gate = False
        for _ in range(40):
            self.check_cancel()
            if await self._account_gate(page):
                created = False
                pending_gate = True
            dialog = await self._visible(page.locator(self.profile["dialog"]))
            if not dialog:
                if pending_gate:
                    await self._click_share(page)
                    pending_gate = False
                await asyncio.sleep(.25)
                continue
            create = dialog.get_by_text(self.profile["create_share"], exact=True)
            if not created and await create.count() == 1 and await create.is_visible() and await create.is_enabled():
                # Newly uploaded Feemoo files default to non-monetized sharing.
                # Never silently publish under a different revenue mode.
                if await dialog.get_by_text("收益模式", exact=True).count():
                    values = await dialog.locator("input").evaluate_all("els => els.map(e => e.value)")
                    if "无收益模式" not in values:
                        raise DriverBlocked("请先在分享弹窗选择无收益模式，再继续任务")
                await self._prepare_share(dialog)
                await create.click()
                created = True
            # A phone gate can arrive asynchronously after creating a UC share.
            if await self._visible(page.get_by_text(self.profile.get("account_prompt", "__no_account_prompt__"), exact=True)):
                continue
            text = await dialog.inner_text()
            values = await dialog.locator("input:not([type=checkbox]):not([type=radio]), textarea").evaluate_all(r"""els => els.filter(e => e.getBoundingClientRect().width > 0).map(e => {
                const label=(e.closest('label') || e.parentElement).innerText || '';
                return /提取码|访问码|密码/.test(label) && /^[A-Za-z0-9]{2,16}$/.test(e.value) ? '提取码：'+e.value : e.value;
            }).join('\n')""")
            hrefs = await dialog.locator("a[href]").evaluate_all(r"els => els.map(e => e.href).join('\n')")
            code = None
            if self.profile.get("share_code"):
                field = await self._visible(dialog.locator(self.profile["share_code"]))
                if field:
                    code = (await field.input_value()).strip()
                    values += "\n提取码：" + code
                if self.profile.get("require_share_code") and not code:
                    await asyncio.sleep(.25)
                    continue
            try:
                info = parse_share(text + "\n" + values + "\n" + hrefs, self.name,
                                   allowed_hosts=self.profile["hosts"])
                if code is not None:
                    info.code = code
                if (self.share_options.access == "code" and not info.code or
                        self.share_options.access == "none" and info.code):
                    await asyncio.sleep(.25)
                    continue
                if not self.share_options.is_default and not created:
                    raise DriverBlocked("分享已存在但无法核对本次设置，请回到分享设置后继续")
                expiry = re.search(r"永久有效|长期有效|\d+天后失效|\d+天后过期|\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2})?", text)
                info.expire = expiry[0] if expiry else self.share_expiry or self.profile["expire"]
                self.status = "ready"
                return info
            except ValueError:
                await asyncio.sleep(.25)
        raise DriverBlocked("分享弹窗没有唯一可验证的链接；请复制后用手动回填继续")

    async def _prepare_share(self, dialog):
        if self.profile.get("uncheck_share"):
            await dialog.get_by_role("checkbox", name=self.profile["uncheck_share"], exact=True).uncheck()
        await self._apply_share_options(dialog)
        if self.profile.get("free_share_option"):
            selected = dialog.locator(self.profile["free_share_selected"])
            paid = await self._visible(selected.filter(has_text="付费提取"))
            if paid:
                raise DriverBlocked("当前为付费提取，请选择免费分享形式")
            # Do not grant download sponsorship / activate a traffic package.
            for checkbox in await dialog.get_by_role("checkbox").all():
                if await checkbox.is_visible() and await checkbox.is_checked():
                    raise DriverBlocked("分享流量包选项已勾选，请取消后继续")

    async def _apply_share_options(self, dialog):
        o = self.share_options
        if o.expiry != "default":
            label = EXPIRY_LABELS[o.expiry]
            if self.name == "quark":
                option = dialog.get_by_role("radio", name=label, exact=True)
                await option.check()
                if not await option.is_checked():
                    raise DriverBlocked("未能确认分享有效期")
            elif self.name == "uc":
                option = dialog.locator(".slider-tabs-wrap .tabs").filter(
                    has_text=re.compile(r"^\s*" + ("永久" if o.expiry == "forever" else o.expiry) + r"\s*$"))
                await option.click()
                if "active" not in (await option.get_attribute("class") or "").split():
                    raise DriverBlocked("未能确认分享有效期")
            elif self.name == "123pan":
                option = dialog.get_by_text(label, exact=True)
                await option.click()
                if "selectedTextItem_" not in (await option.get_attribute("class") or ""):
                    raise DriverBlocked("未能确认分享有效期")
            elif self.name == "xunlei":
                group = dialog.locator(".dialog-web-create-share__form-item-extract__item").filter(has_text="提取期限")
                await group.locator(".td-select-group").click()
                value = "不限" if o.expiry == "forever" else label
                await group.get_by_role("listitem").filter(has_text=re.compile(r"^\s*" + re.escape(value) + r"\s*$")).click()
                if (await group.locator(".td-select-group__label").inner_text()).strip() != value:
                    raise DriverBlocked("未能确认分享有效期")
            elif self.name == "feimao":
                if not re.search(r"长期有效|永久有效", await dialog.inner_text()):
                    raise DriverBlocked("飞猫未显示长期有效提示，请核对当前分享设置")
            self.share_expiry = label
        if o.access != "default":
            enabled = o.access == "code"
            if self.name == "quark":
                await dialog.get_by_role("radio", name="需要" if enabled else "不需要", exact=True).check()
            elif self.name == "uc":
                await dialog.get_by_role("switch").set_checked(enabled)
            elif self.name == "123pan":
                value = "随机提取码" if enabled else "无提取码"
                option = dialog.get_by_text(value, exact=True)
                await option.click()
                if "selectedTextItem_" not in (await option.get_attribute("class") or ""):
                    raise DriverBlocked("未能确认提取码设置")
            elif self.name == "xunlei":
                # The checkbox is disabled and checked on the observed web UI.
                if not await dialog.get_by_role("checkbox", name="有提取码", exact=True).is_checked():
                    raise DriverBlocked("未能确认迅雷提取码设置")
            elif self.name == "feimao":
                choices = []
                for entry in await dialog.locator(".el-select input").all():
                    if await entry.is_visible() and (await entry.input_value()).startswith(("公开链接", "私密链接")):
                        choices.append(entry)
                if len(choices) != 1:
                    raise DriverBlocked("未找到唯一的飞猫分享形式选项")
                value = "私密链接，需要密码才可访问分享内容" if enabled else "公开链接，不需要密码即可访问分享内容"
                await choices[0].click()
                await (await self._text(dialog, value)).click()
                if await choices[0].input_value() != value:
                    raise DriverBlocked("未能确认飞猫分享形式")


class FeimaoDriver(BrowserDiskDriver):
    def __init__(self, **kw):
        super().__init__("feimao", **kw)

    async def upload(self, page, files: list[Path], folder: str) -> list[str]:
        await super().upload(page, files, folder)
        return [folder + "/" + path.name for path in files]

    async def share(self, page, entry_ids: list[str]) -> ShareInfo:
        # A Feemoo folder link hides files which have not individually been published.
        # Publish precisely the uploaded file names first; never return an empty folder link.
        entries = [target.split("/", 1) for target in entry_ids]
        if not entries or any(len(pair) != 2 for pair in entries) or len({pair[0] for pair in entries}) != 1:
            raise DriverBlocked("飞猫检查点缺少明确文件目标，请手动回填分享或创建新任务")
        folder = entries[0][0]
        last = None
        for _, name in entries:
            self.check_cancel()
            await page.goto(self.profile["url"], wait_until="domcontentloaded", timeout=60000)
            self.folder = self.remote_parent = self.remote_sizes = None
            await self._open_folder(page, folder)
            row = self.rows(page, name)
            await row.wait_for(state="visible", timeout=15000)
            await row.locator(self.profile["checkbox"]).click()
            last = await self._share_selected(page)
        if len(entries) == 1:
            return last
        # Folder sharing now includes the individually published, non-monetized files.
        return await super().share(page, [folder])


class QuarkDriver(BrowserDiskDriver):
    def __init__(self, **kw):
        super().__init__("quark", **kw)


class UCDriver(BrowserDiskDriver):
    def __init__(self, **kw):
        super().__init__("uc", **kw)


class XunleiDriver(BrowserDiskDriver):
    def __init__(self, **kw):
        super().__init__("xunlei", **kw)

    async def _dismiss_transfer_list(self, page):
        # The site opens this modal after every upload; its shadow covers 添加
        # and navigation. Use its own header close control, leaving tasks intact.
        panel = page.locator(".pan-task-list")
        close = panel.locator("[class*='TaskList__header--'] .xlp-list-del:visible")
        # The wrapper itself can have zero height while its fixed children cover
        # the page. Test the actual close control and shadow, not the wrapper.
        if await close.count():
            await close.click(timeout=5000)
            await panel.locator("[class*='TaskList__shadow--']").wait_for(state="hidden", timeout=5000)

    async def _trigger_upload(self, page, path):
        await self._dismiss_transfer_list(page)
        await super()._trigger_upload(page, path)

    async def share(self, page, entry_ids):
        await self._dismiss_transfer_list(page)
        return await super().share(page, entry_ids)


class Pan123Driver(BrowserDiskDriver):
    def __init__(self, **kw):
        super().__init__("123pan", **kw)

    async def _dismiss_transfer_list(self, page):
        panel = page.locator("[class*='popoverContent_']").filter(
            has=page.locator("[class*='titleBar_']", has_text="进度"))
        close = panel.locator("[class*='titleBar_'] [class*='closeIcon_']:visible")
        if await close.count():
            await close.click(timeout=5000)
            await panel.wait_for(state="hidden", timeout=5000)

    async def _trigger_upload(self, page, path):
        await self._dismiss_transfer_list(page)
        await super()._trigger_upload(page, path)

    async def share(self, page, entry_ids):
        await self._dismiss_transfer_list(page)
        return await super().share(page, entry_ids)


class BaiduDriver(BrowserDiskDriver):
    """Baidu's SPA keeps its route in the fragment; sharing is created by the dialog's copy action."""

    EXPIRE_VALUES = {"1": "1", "7": "7", "30": "30", "365": "365", "forever": "0"}
    EXPIRE_LABELS = {"0": "永久有效", "1": "1天", "7": "7天", "30": "30天", "365": "365天"}

    def __init__(self, **kw):
        super().__init__("baidu", **kw)
        self.folder_path = None

    @staticmethod
    def _hash_query(url):
        return parse_qs(urlsplit(str(url)).fragment.partition("?")[2])

    async def is_logged_in(self, page):
        if "passport.baidu.com" in page.url or "/login" in urlsplit(page.url).path:
            return False
        if not page.url.startswith("https://pan.baidu.com/"):
            return False
        user = await self._visible(page.locator(self.profile["login_user"]))
        return bool(user) and bool(await self._visible(page.locator(self.profile["logged_in"])))

    async def _root(self, page):
        await page.goto(self.profile["url"] + "#/index?category=all", wait_until="domcontentloaded",
                        timeout=60000)
        # The SPA keeps the previous virtual rows during route changes; a real reload
        # guarantees the list we then select from is the root listing, not the folder's.
        await page.reload(wait_until="domcontentloaded", timeout=60000)
        await self._wait_visible(page, self.profile["toolbar"], timeout=min(30, self.timeout))
        end = time.monotonic() + min(20, self.timeout)
        while time.monotonic() < end:
            self.check_cancel()
            if not await self._visible(page.get_by_text("返回上一级", exact=True)):
                break
            await asyncio.sleep(.25)
        else:
            raise DriverBlocked("百度网盘未回到根目录，拒绝在不确定位置创建或分享")
        await self.check_restriction(page)
        self.folder = self.folder_path = self.remote_sizes = None

    async def _wait_row(self, page, name, timeout=25):
        end = time.monotonic() + min(timeout, self.timeout)
        while time.monotonic() < end:
            self.check_cancel()
            row = await self._row(page, name)
            if row:
                return row
            await asyncio.sleep(.3)
        return None

    async def _wait_clickable(self, locator, label, timeout=20):
        end = time.monotonic() + min(timeout, self.timeout)
        while time.monotonic() < end:
            self.check_cancel()
            for item in await locator.all():
                if await item.is_visible() and await item.is_enabled():
                    return item
            await asyncio.sleep(.25)
        raise DriverBlocked(f"百度网盘未出现可用的“{label}”控件")

    async def _create_folder(self, page, folder):
        new_folder = page.locator(self.profile["toolbar"]).get_by_text(
            self.profile["new_folder"], exact=True)
        await (await self._wait_clickable(new_folder, self.profile["new_folder"])).click()
        entry = await self._wait_visible(page, self.profile["folder_input"], timeout=min(15, self.timeout))
        await entry.fill(folder)
        await entry.press(self.profile["folder_submit"])

    async def _enter_folder(self, page, row, folder):
        path = "/" + folder
        from playwright.async_api import TimeoutError as PlaywrightTimeout

        def listing(response):
            if urlsplit(response.url).path != "/api/list" or response.request.method != "GET":
                return False
            return parse_qs(urlsplit(response.url).query).get("dir", [""])[0] == path

        sizes = None
        try:
            async with page.expect_response(listing, timeout=min(20, self.timeout) * 1000) as result:
                await row.locator(self.profile["row_name"]).first.dblclick()
            response = await result.value
            data = await response.json()
            if isinstance(data.get("list"), list):
                sizes = {entry.get("server_filename"): entry.get("size", 0)
                         for entry in data["list"] if not entry.get("isdir")}
        except PlaywrightTimeout:
            # Empty/cached folders can render without a fresh listing; row checks still confirm uploads.
            sizes = None
        end = time.monotonic() + min(20, self.timeout)
        while time.monotonic() < end:
            self.check_cancel()
            if self._hash_query(page.url).get("path", [""])[0] == path:
                await self._wait_visible(page, self.profile["toolbar"], timeout=min(10, self.timeout))
                self.folder = folder
                self.folder_path = path
                self.remote_sizes = sizes
                return
            await asyncio.sleep(.25)
        raise DriverBlocked("进入任务目录后地址未确认，拒绝继续操作")

    async def _open_folder(self, page, folder):
        await self.check_restriction(page)
        if self.folder == folder and self.folder_path:
            return
        await self._root(page)
        row = await self._wait_row(page, folder)
        if row is None:
            await self._create_folder(page, folder)
            row = await self._wait_row(page, folder)
            if row is None:
                raise DriverBlocked("未能确认百度网盘任务目录已创建；未选择任何其他文件")
        await self._enter_folder(page, row, folder)

    async def upload(self, page, files: list[Path], folder: str) -> list[str]:
        await self._open_folder(page, folder)
        sizes = None if self.remote_sizes is None else dict(self.remote_sizes)
        for path in files:
            self.check_cancel()
            if sizes is not None and path.name in sizes:
                if sizes[path.name] != path.stat().st_size:
                    raise DriverBlocked(f"远端同名文件大小不符，请检查任务目录：{path.name}")
                self.notify(f"远端已存在，复用任务目录内文件：{path.name}")
                continue
            chosen = None
            for entry in await page.locator(self.profile["upload"]).all():
                if await entry.get_attribute("webkitdirectory") is None and await entry.is_visible():
                    chosen = entry
                    break
            if chosen is None:
                raise DriverBlocked("未找到百度网盘文件上传框")
            await chosen.set_input_files(str(path))
            end = time.monotonic() + self.timeout
            next_notice = time.monotonic() + 15
            while time.monotonic() < end:
                self.check_cancel()
                await self.check_restriction(page)
                # The file table row appears only after the server has stored the upload;
                # the transfer panel's completion text is not a confirmation.
                if await self._row(page, path.name):
                    break
                if time.monotonic() >= next_notice:
                    self.notify(f"等待网盘确认上传：{path.name}")
                    next_notice = time.monotonic() + 15
                await asyncio.sleep(.75)
            else:
                raise DriverBlocked(f"{path.name} 上传未确认完成，检查配额、大小限制或验证弹窗后继续")
            if sizes is not None:
                sizes[path.name] = path.stat().st_size
            self.notify(f"已确认上传：{path.name}")
        self.remote_sizes = sizes
        return [folder]

    async def _choose_radio(self, option, label):
        if await option.get_attribute("aria-checked") == "true":
            return
        await option.click()
        end = time.monotonic() + 5
        while time.monotonic() < end:
            self.check_cancel()
            if await option.get_attribute("aria-checked") == "true":
                return
            await asyncio.sleep(.2)
        raise DriverBlocked(f"未能确认百度网盘{label}设置")

    async def _apply_share_options(self, dialog):
        o = self.share_options
        pane = dialog.locator("#pane-link")
        if o.expiry != "default":
            value = self.EXPIRE_VALUES[o.expiry]
            await self._choose_radio(pane.locator(f'[role=radio]:has(input[value="{value}"])'),
                                     "分享有效期")
            self.share_expiry = EXPIRY_LABELS[o.expiry]
        if o.access != "default":
            if o.access != "code":
                raise DriverBlocked("百度网盘当前网页分享强制提取码，不能使用无提取码")
            await self._choose_radio(pane.locator('[role=radio]:has(input[value="random"])'),
                                     "提取码")

    async def _wait_dialog_ready(self, dialog):
        copy = dialog.locator("button.wp-share-file__link-create-ubtn").filter(
            has_text=re.compile("复制链接"))
        await self._wait_clickable(copy, "复制链接", timeout=min(20, self.timeout))
        # The dialog loads its stored settings asynchronously and can reset a choice
        # made too early; apply options only after two identical content snapshots.
        last, stable = None, 0
        end = time.monotonic() + min(10, self.timeout)
        while time.monotonic() < end:
            self.check_cancel()
            text = await dialog.inner_text()
            if text == last:
                stable += 1
                if stable >= 2:
                    break
            else:
                last, stable = text, 0
            await asyncio.sleep(.35)
        return copy

    async def _create_link(self, page, dialog, copy):
        collected = []

        def on_response(response):
            if urlsplit(response.url).path == "/share/pset" and response.request.method == "POST":
                collected.append(response)

        page.on("response", on_response)
        try:
            await copy.click()
            requested = (None if self.share_options.expiry == "default"
                         else self.EXPIRE_VALUES[self.share_options.expiry])
            actual = None
            end = time.monotonic() + min(20, self.timeout)
            while time.monotonic() < end:
                self.check_cancel()
                if collected:
                    response = collected[-1]
                    try:
                        data = await response.json()
                    except Exception:
                        data = None
                    if data and str(data.get("errno")) == "0" and data.get("link"):
                        actual = str(data.get("expiredType"))
                        if requested is None or actual == requested:
                            code = parse_qs(urlsplit(data.get("qrcodeurl") or "").query).get("pwd", [""])[0]
                            if not code:
                                raise DriverBlocked("分享响应缺少提取码，拒绝生成不完整的链接文案")
                            expire = self.EXPIRE_LABELS.get(actual, self.share_expiry or self.profile["expire"])
                            return ShareInfo("baidu", data["link"], code, expire), None
                await asyncio.sleep(.25)
            return None, actual
        finally:
            page.remove_listener("response", on_response)

    async def share(self, page, entry_ids: list[str]) -> ShareInfo:
        await self.check_restriction(page)
        if len(entry_ids) != 1:
            raise DriverBlocked("只能分享当前任务的独立目录")
        folder = entry_ids[0]
        await self._root(page)
        row = await self._wait_row(page, folder)
        if row is None:
            raise DriverBlocked("未找到当前任务目录；拒绝分享不确定的文件")
        await row.locator(self.profile["checkbox"]).first.click()
        share_button = page.locator("button.wp-s-agile-tool-bar__h-action-button").filter(
            has_text=re.compile(r"^\s*分享\s*$"))
        try:
            await self._wait_clickable(share_button, "分享", timeout=min(15, self.timeout))
        except DriverBlocked:
            # A click during list rendering can miss the checkbox; retry the row itself once.
            await row.locator(self.profile["checkbox"]).first.click()
            await self._wait_clickable(share_button, "分享", timeout=min(10, self.timeout))
        await (await self._wait_clickable(share_button, "分享", timeout=min(5, self.timeout))).click()
        dialog = await self._wait_visible(page, self.profile["share_dialog"], timeout=min(30, self.timeout))
        info = actual = None
        for _ in range(2):
            copy = await self._wait_dialog_ready(dialog)
            await self._apply_share_options(dialog)
            info, actual = await self._create_link(page, dialog, copy)
            if info is not None:
                break
        if info is None:
            if actual is None:
                raise DriverBlocked("百度网盘未返回有效分享链接；请手动核对分享弹窗")
            raise DriverBlocked(f"百度网盘分享有效期未按选择生效（实际 {actual}），请核对分享弹窗")
        parse_share(info.text(), self.name, allowed_hosts=self.profile["hosts"])
        close = dialog.locator("button.u-dialog__headerbtn")
        if await close.count():
            await close.first.click()
        else:
            await page.keyboard.press("Escape")
        self.status = "ready"
        return info


REGISTRY = {"feimao": FeimaoDriver, "quark": QuarkDriver, "uc": UCDriver,
            "xunlei": XunleiDriver, "123pan": Pan123Driver, "baidu": BaiduDriver}
