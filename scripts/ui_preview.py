"""Render the desktop UI with canned data for visual QA (developer tool, no network).

Static data (formats, disks, share options, encoders) comes from the real ``Api``;
files, jobs and tasks are faked so every screen can be captured without touching
netdisks.  Screenshots go to ``tmp/ui`` (git-ignored).

    .venv\\Scripts\\python scripts\\ui_preview.py [--dark] [--scale 1.25]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from playwright.sync_api import sync_playwright  # noqa: E402

from misong.desktop.api import Api  # noqa: E402

WEB = ROOT / "src" / "misong" / "desktop" / "web" / "index.html"
FILES = {
    r"D:\资源\纪录片合集": {"name": "纪录片合集", "dir": True, "count": 12, "size": 7_450_000_000},
    r"D:\资源\S01E01.mkv": {"name": "S01E01.mkv", "dir": False, "size": 1_380_000_000},
    r"D:\资源\字幕.zip": {"name": "字幕.zip", "dir": False, "size": 2_400_000},
}
COPIES = {
    "beast": "~呜嗷嗷嗷嗷呜呜啊呜嗷呜嗷~呜啊~啊嗷啊呜嗷呜~嗷~呜呜嗷呜嗷嗷啊呜啊嗷~嗷呜~呜嗷啊呜呜啊~啊嗷啊嗷~",
    "mojibake": "曰：夫道者，常以无为而知其所往，故能静而观之。是以圣人之行也，若水之就下，莫之能争。",
    "hajimi": "哈基米南北绿豆 阿西噶哈呀库那路 曼波曼波 哈基米哦南北绿豆 欧马吉利曼波",
}


class Fake:
    def __init__(self, api: Api):
        self.api = api
        self.job = None
        self.events: list[dict] = []
        self.ticks = 0
        self.space_blocked = False
        self.preflight_calls = 0
        self.output_choices = 0
        self.edits: dict[str, dict] = {
            r"D:\misong\runs\a": {"starred": True, "note": "周末发群用，记得补 UC 中转", "error": "网盘页面操作受阻（本体上传）"},
        }
        self.extra: list[dict] = []
        self.removed: set[str] = set()
        self.live_state = ""

    def stages(self, done):
        return [
            {"id": "body", "role": "body", "disk": "quark", "label": "夸克网盘", "state": "uploading" if done < 4 else "shared", "done": done, "total": 4},
            {"id": "body-2", "role": "body", "disk": "123pan", "label": "123云盘", "state": "pending", "done": 0, "total": 4},
        ]

    def tasks(self):
        base = [
            {"plan": r"D:\misong\runs\a\relay-plan.json", "dir": r"D:\misong\runs\a", "kind": "pipeline", "title": "纪录片合集", "state": "uploading",
             "created": "2026-10-18T21:40:00", "updated": "2026-10-18T22:10:00", "form": "simple", "stages": self.stages(2),
             "settings": {"layers": [{"fmt": "lz4", "locked": False}, {"fmt": "7z", "locked": True, "header_enc": True}], "disguise": "mp4", "size": "1900M",
                          "disks": ["quark", "123pan"], "form": "simple"}},
            {"plan": r"D:\misong\runs\b\relay-plan.json", "dir": r"D:\misong\runs\b", "kind": "upload", "title": "S01E01.mkv 等 3 个文件", "state": "complete",
             "created": "2026-10-17T19:02:00", "form": "direct", "stages": [{"id": "body", "role": "body", "disk": "feimao", "label": "飞猫盘", "state": "shared", "done": 3, "total": 3}]},
            {"plan": None, "dir": r"D:\misong\runs\c", "kind": "pack", "title": "字幕.zip", "state": "complete", "created": "2026-10-16T10:00:00", "chain": "lz4 → 7z🔒", "stages": []},
        ]
        out = []
        for t in base + self.extra:
            if t["dir"] in self.removed:
                continue
            t = {"starred": False, "note": "", "error": "", "imported": False, "settings": {}, **t, **self.edits.get(t["dir"], {})}
            if self.live_state and t["dir"] == r"D:\misong\runs\a":
                t["state"] = self.live_state
                if self.live_state == "complete":
                    t["error"] = ""
            out.append(t)
        return out

    def __call__(self, method, args):
        args = args or []
        api = self.api
        if method in ("bootstrap", "share_choices", "encode", "decode", "save_settings", "templates", "save_template", "delete_template",
                      "reset_templates"):
            if method == "save_settings":
                return {"ok": True, "data": True}
            return getattr(api, method)(*args)
        if method == "choose_output_dir":
            self.output_choices += 1
            selected = api._state.parent / ("selected-output" if self.output_choices == 1 else "selected-output-2")
            selected.mkdir(exist_ok=True)
            return api.set_output_dir(str(selected))
        data = None
        if method == "accounts":
            data = api.accounts()["data"]
            for a in data:
                if a["key"] == "quark":
                    a.update(state="tested", session=True, status="ready", verified=True, verified_at="2026-10-18T21:52:00",
                             session_at="2026-10-19T09:30:00", browser="chromium")
                elif a["key"] == "feimao":
                    a.update(state="loggedin", session=True, session_saved="2026-10-18T15:20:00", status="probe", verified=False,
                             session_at="")
                elif a["key"] == "uc":
                    a.update(state="neterr", session=True, session_error=True, net_error=True, status="blocked", verified=True,
                             verified_at="2026-10-18T21:55:00", browser="chrome", last_error_at="2026-10-19T20:11:00",
                             last_error="无法打开 drive.uc.cn：连接超时（ERR_TIMED_OUT），请检查网络或代理后重试")
                elif a["key"] == "baidu":
                    a.update(state="expired", session=True, session_error=True, status="blocked", verified=False,
                             last_error="登录超时：未检测到已登录的网盘页面", last_error_at="2026-10-19T08:02:00")
        elif method == "update_task":
            self.edits.setdefault(args[0], {}).update(args[1])
            data = next(t for t in self.tasks() if t["dir"] == args[0])
        elif method == "delete_task":
            t = next(t for t in self.tasks() if t["dir"] == args[0])
            self.removed.add(args[0])
            data = {"trashed": not t["imported"]}
        elif method == "import_task":
            t = {"plan": None, "dir": args[0], "kind": "pack", "title": Path(args[0]).name + "（导入）", "state": "complete",
                 "created": "2026-09-30T08:00:00", "chain": "7z🔒", "stages": [], "imported": True}
            self.extra = [x for x in self.extra if x["dir"] != args[0]] + [t]
            data = next(x for x in self.tasks() if x["dir"] == args[0])
        elif method == "preflight_pack":
            self.preflight_calls += 1
            data = {"ok": not self.space_blocked, "required_bytes": 27_000_000_000, "out": r"D:\misong\runs\pending",
                    "message": "需要约 25.15 GB，当前最大可用盘仅 1 GB，请更换位置" if self.space_blocked else "本次约需中间空间 25.15 GB，总读写约 74.20 GB，预计约 8.4 分钟"}
        elif method == "pick_files":
            data = [r"D:\资源\intro.mp4"] if len(args) > 1 and args[1] else [r"D:\资源\S01E01.mkv", r"D:\资源\字幕.zip"]
        elif method == "pick_folder":
            data = [r"D:\资源\纪录片合集"]
        elif method == "describe_paths":
            data = [{"path": p, **FILES.get(p, {"name": Path(p).name, "dir": False, "size": 1})} for p in args[0]]
        elif method == "folder_files":
            data = [r"D:\资源\S01E01.mkv"]
        elif method in ("start_pipeline", "start_upload", "start_pack", "resume_task"):
            kind = {"start_pipeline": "pipeline", "start_upload": "upload", "start_pack": "pack"}.get(method, "pipeline")
            self.job = {"id": "j1", "kind": kind, "title": "发布 纪录片合集", "step": "上传 夸克网盘：S01E01.part2.mp4（2/4）",
                        "plan": r"D:\misong\runs\a\relay-plan.json"}
            data = dict(self.job)
        elif method == "poll":
            job = dict(self.job) if self.job else None
            if job:
                job["task"] = {"stages": self.stages(2)}
            data = {"events": self.events, "job": job}
            self.events = []
        elif method == "list_tasks":
            data = self.tasks()
        elif method == "task_detail":
            want = args[1] if len(args) > 1 and args[1] else None
            t = next(t for t in self.tasks() if ((t["dir"] == want) if want else t["plan"] == args[0]))
            data = {**t, "copies": COPIES if t["kind"] != "pack" else {},
                    "files": [{"name": f"纪录片合集.mp4.{i:03d}", "size": 1_900_000_000} for i in range(1, 5)]}
        elif method in ("open_path", "pause", "import_share", "account_action"):
            data = True
        return {"ok": True, "data": data}

    def finish(self, kind="pipeline", promote=False):
        job, self.job = self.job, None
        if promote:
            self.live_state = "complete"
        result = {"plan": r"D:\misong\runs\a\relay-plan.json", "copies": COPIES}
        if kind == "pack":
            result = {"out": r"D:\misong\runs\c", "chain": "lz4 → 7z🔒", "files": [{"name": "纪录片合集.7z", "size": 7_300_000_000}],
                      "parts": [{"name": f"纪录片合集.7z.{i:03d}", "size": 1_900_000_000} for i in range(1, 4)]}
        self.events.append({"type": "job", "state": "done", "job": job or {"kind": kind}, "result": result})
        self.events.append({"type": "log", "text": "夸克网盘：分享完成"})


MOCK_JS = """
window.__MISONG_MOCK__ = new Proxy({}, { get: (_, m) => m === "then" ? undefined : (...args) => window.__py(m, args) });
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dark", action="store_true")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--height", type=int, default=880)
    ap.add_argument("--out", default=str(ROOT / "tmp" / "ui"))
    ap.add_argument("--only", default="")
    ns = ap.parse_args()
    out = Path(ns.out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="misong-ui-"))
    fake = Fake(Api(runs_dir=tmp / "runs", state_dir=tmp / "state"))
    suffix = "-dark" if ns.dark else ""
    errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(viewport={"width": 1320, "height": ns.height}, device_scale_factor=ns.scale,
                                  color_scheme="dark" if ns.dark else "light", locale="zh-CN")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.expose_function("__py", lambda m, a: json.loads(json.dumps(fake(m, a), ensure_ascii=False)))
        page.add_init_script(MOCK_JS)
        page.goto(WEB.as_uri())
        try:
            page.wait_for_selector(".page.active [data-mount='run'] .run", timeout=8000)
        except Exception:
            page.screenshot(path=str(out / "00-boot-failed.png"))
            print("\n".join(errors))
            raise

        def shot(name, scroll=0):
            if ns.only and ns.only not in name:
                return
            page.evaluate(f"document.querySelector('.main').scrollTop = {scroll}")
            page.wait_for_timeout(250)
            page.screenshot(path=str(out / f"{name}{suffix}.png"))

        def shot_at(name, sel):
            if ns.only and ns.only not in name:
                return
            page.evaluate("s => { const m = document.querySelector('.main'); const e = document.querySelector(s);"
                          " if (e) m.scrollTop += e.getBoundingClientRect().top - 90; }", sel)
            page.wait_for_timeout(250)
            page.screenshot(path=str(out / f"{name}{suffix}.png"))

        def nav(name):
            page.click(f".nav-item[data-page='{name}']")
            page.wait_for_timeout(300)

        def click(sel, wait=250):
            page.click(sel)
            page.wait_for_timeout(wait)

        def modal_open():
            return page.evaluate("() => !document.querySelector('#modal').hidden")

        click("#outputChoose", 300)
        assert "selected-output" in page.locator("#outputPath").inner_text()
        assert fake.api._runs.name == "selected-output"
        shot("00-output-directory")

        # step 1: resources (下一步 is refused until something is added)
        shot("01-pipeline-step1-empty")
        click(".page.active [data-stepnext]", 300)
        shot("01b-pipeline-step1-blocked")
        click(".page.active [data-act='pick-folder']", 200)
        click(".page.active [data-act='pick-files']", 200)
        shot("02-pipeline-step1-filled")
        click(".page.active [data-stepnext]", 300)
        # step 2: a template only fills the editor; it never opens a password dialog
        click(".page.active [data-tpl='1']", 400)
        assert not modal_open(), "template click must not open a modal"
        shot("03-pipeline-step2-template")
        click(".page.active [data-stepnext]", 300)
        assert modal_open(), "no-password confirm expected"
        shot("03b-step2-nopw-confirm")
        click("#modal [data-x]", 300)
        click(".page.active [data-tpl='3']", 300)
        page.fill(".page.active [data-lpw]:not([disabled])", "secret")
        click(".page.active [data-stepnext]", 300)
        assert modal_open(), "missing locked password confirm expected"
        shot("03c-step2-locked-confirm")
        click("#modal [data-x]", 300)
        click(".page.active [data-tpl='0']", 300)
        page.fill(".page.active [data-lpw]:not([disabled])", "secret")
        click(".page.active [data-tplsave]", 200)
        page.fill("#modal input[data-model='name']", "发群用 lz4+7z")
        shot("04a-template-save-modal")
        click("#modal [data-ok]", 500)
        shot_at("04b-template-chip", ".page.active [data-mount='layers']")
        click(".page.active [data-tpldel='2']", 200)
        shot("04d-template-delete")
        click("#modal [data-ok]", 500)
        shot_at("04e-template-restore", ".page.active [data-mount='layers']")
        click(".page.active [data-tplreset]", 500)
        assert page.locator(".page.active [data-tpl]").count() == 5, "defaults restored"
        page.fill(".page.active [data-lpw]:not([disabled])", "secret")
        page.select_option(".page.active [data-addtype]", "cover")
        click(".page.active [data-addlayer]", 200)
        click(".page.active [data-dropkind='video']", 500)
        page.select_option(".page.active [data-addtype]", "rename")
        click(".page.active [data-addlayer]", 200)
        page.select_option(".page.active [data-addtype]", "split")
        click(".page.active [data-addlayer]", 200)
        page.fill(".page.active [data-lsize]", "1900")
        page.select_option(".page.active [data-lunit]", "MB")
        assert "上一层产物不超过每卷大小时，将保留单文件，不生成分卷" in page.locator(".page.active .layer").last.inner_text()
        assert "后续压缩层会把所有卷重新打包" in page.locator(".page.active .layer").last.inner_text()
        shot_at("04c-pipeline-layers", ".page.active .layer[data-i='2']")
        assert page.locator("[data-model='raw_merge']").count() == 0
        assert page.locator(".page.active [data-ltype]").count() == 5
        page.check(".page.active [data-model='checksum']")
        # Save every layer parameter, including the video path, without passwords.
        click(".page.active [data-tplsave]", 200)
        page.fill("#modal input[data-model='name']", "四类型模板")
        click("#modal [data-ok]", 300)
        saved = fake.api.templates()["data"][-1]
        assert [x.get("type", "archive") for x in saved["layers"]] == ["archive", "archive", "cover", "rename", "split"]
        assert saved["layers"][2]["video"].endswith("intro.mp4")
        assert "secret" not in json.dumps(saved)
        last_template = len(fake.api.templates()["data"]) - 1
        click(f".page.active [data-tpl='{last_template}']", 300)
        assert page.locator(".page.active [data-dropkind='video']").inner_text().find("intro.mp4") >= 0
        page.fill(".page.active [data-lpw]:not([disabled])", "secret")
        click(".page.active [data-stepnext]", 400)
        assert not modal_open(), "filled passwords need no confirm"
        # step 3: disks + relay
        click(".page.active [data-disk='quark']", 200)
        click(".page.active [data-disk='123pan']", 300)
        shot("05a-pipeline-step3")
        page.select_option(".page.active select[data-model='form']", "complex")
        page.wait_for_timeout(400)
        shot("05-pipeline-relay")
        page.fill(".page.active input[data-model='hopPw']", "hop")
        page.wait_for_timeout(200)
        click(".page.active [data-stepnext]", 400)
        # step 4: copy schemes, then publish
        shot("05b-pipeline-step4")
        page.click(".page.active [data-run='publish']")
        page.wait_for_timeout(1500)
        shot("06-pipeline-running")
        fake.finish()
        page.wait_for_timeout(1500)
        shot("07-pipeline-done")
        page.click("#logToggle")
        page.wait_for_timeout(200)
        shot("08-log-drawer")
        page.click("#logClose")

        nav("pack")
        page.click(".page.active [data-act='pick-files']")
        page.wait_for_timeout(200)
        page.select_option(".page.active [data-addtype]", "split")
        click(".page.active [data-addlayer]", 200)
        page.wait_for_timeout(200)
        shot("09-pack")
        shot("10-pack-bottom", 5000)
        fake.space_blocked = True
        page.fill(".page.active [data-lsize]", "2000")
        page.wait_for_timeout(700)
        assert page.locator(".page.active [data-run='go']").is_disabled()
        shot("10b-pack-space-blocked", 5000)
        fake.space_blocked = False
        page.fill(".page.active [data-lsize]", "1900")
        page.wait_for_timeout(700)
        previous_calls = fake.preflight_calls
        click("#outputChoose", 700)
        assert fake.preflight_calls > previous_calls, "changing output directory must refresh space preflight"
        assert "selected-output-2" in page.locator(".page.active .run-note").inner_text()
        shot("10c-output-directory-changed", 5000)

        nav("upload")
        page.click(".page.active [data-act='pick-files']")
        page.wait_for_timeout(200)
        page.click(".page.active [data-disk='feimao']")
        page.wait_for_timeout(300)
        shot("11-upload")
        shot("12-upload-bottom", 5000)

        nav("codec")
        page.fill("#codecInput", "https://pan.quark.cn/s/abc123 提取码：x7k2")
        page.click("#codecSchemes [data-cs='mojibake']")
        page.click("#codecRun")
        page.wait_for_timeout(600)
        shot("13-codec")

        nav("tasks")
        page.wait_for_timeout(500)
        assert page.locator("#tasksOpen").count() == 0
        assert page.locator("#taskDetail [data-open]").inner_text() == "打开当前任务目录"
        assert "上传中" in page.locator("#taskDetail").inner_text()
        fake.finish(promote=True)
        page.wait_for_timeout(2600)
        detail = page.locator("#taskDetail").inner_text()
        assert "已完成" in detail, detail
        assert "上次中断原因" not in detail
        shot("14-tasks")
        page.click("#taskFilter [data-v='star']")
        page.wait_for_timeout(300)
        shot("14b-tasks-starred")
        page.click("#taskFilter [data-v='all']")
        page.fill("#taskSearch", "字幕")
        page.wait_for_timeout(300)
        shot("14c-tasks-search")
        page.fill("#taskSearch", "")
        page.wait_for_timeout(300)
        page.click(".task[data-task]")
        page.wait_for_timeout(400)
        page.click("[data-edit]")
        page.wait_for_timeout(200)
        shot("14d-task-edit")
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        page.click("[data-del]")
        page.wait_for_timeout(200)
        shot("14e-task-delete")
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        page.click("[data-fill]")
        page.wait_for_timeout(200)
        shot("15-fill-modal")
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        page.click("#tasksImport")
        page.wait_for_timeout(800)
        shot("15b-task-imported")

        # Reuse an old task: migrate disguise+size into explicit typed layers.
        page.locator(".task[data-task]").first.click()
        page.wait_for_timeout(300)
        click("[data-reuse]", 300)
        state = page.evaluate("window.__MISONG_APP__.S.pipeline.layers")
        assert [x["type"] for x in state] == ["archive", "archive", "rename", "split"]
        assert state[1]["_lock"] and not state[1]["password"]
        assert state[-1]["size"] == "1900M"
        shot("15c-legacy-task-migrated")
        nav("accounts")
        page.wait_for_timeout(300)
        shot("16-accounts")
        shot("16b-accounts-bottom", 5000)
        page.close()
        browser.close()
    assert not errors, "\n".join(errors)
    print("no console errors")
    print("saved to", out)


if __name__ == "__main__":
    main()
