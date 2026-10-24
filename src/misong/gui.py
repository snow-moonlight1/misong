"""Chinese desktop workspace. All Tk access stays on the UI thread."""
from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import tkinter as tk
import uuid
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import pack
from .publish import PublishOptions, import_share, prepare, publish
from .rpa.runtime import BrowserRuntime, DEFAULT_STATE, ROOT
from .sharing import encode_copy
from .providers import PROVIDERS
from .rpa.drivers import PROFILES
from .share_options import ShareOptions, EXPIRY_LABELS, ACCESS_LABELS, common_options


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("密送（Misong）· 资源发布工作台")
        root.geometry("1180x820")
        root.minsize(1020, 740)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.closing = False
        self.inputs: list[Path] = []
        self.current_plan: Path | None = None
        self.copies = {}
        self.vars = {}
        self._style()
        self._build()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)

    def _style(self):
        self.root.configure(bg="#EEF3F8")
        self.root.option_add("*Font", ("Microsoft YaHei UI", 10))
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background="#EEF3F8", foreground="#23364D", font=("Microsoft YaHei UI", 10))
        style.configure("TNotebook.Tab", padding=(20, 9))
        style.configure("TButton", padding=(13, 8), background="#E0E9F1", borderwidth=0)
        style.map("TButton", background=[("active", "#C8DDE8")])
        style.configure("Primary.TButton", background="#247C91", foreground="white")
        style.map("Primary.TButton", background=[("active", "#196579"), ("disabled", "#90ACB4")])
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 24, "bold"))
        style.configure("Sub.TLabel", foreground="#65758B")
        style.configure("TLabelframe", borderwidth=1, relief="solid")
        style.configure("TLabelframe.Label", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("TEntry", padding=5, fieldbackground="white")

    def var(self, key, default=""):
        v = tk.StringVar(value=default)
        self.vars[key] = v
        return v

    def _build(self):
        header = ttk.Frame(self.root, padding=(26, 20, 26, 12))
        header.pack(fill="x")
        ttk.Label(header, text="资源发布工作台", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="密送 Misong     打包  →  上传  →  分享  →  加密文案", style="Sub.TLabel").pack(anchor="w", pady=(6, 0))
        book = ttk.Notebook(self.root)
        book.pack(fill="both", expand=True, padx=24, pady=(0, 14))
        workspace = ttk.Frame(book, padding=16)
        accounts = ttk.Frame(book, padding=24)
        codec = ttk.Frame(book, padding=20)
        book.add(workspace, text="发布与恢复")
        book.add(accounts, text="网盘账号")
        book.add(codec, text="链接编解码")
        workspace.columnconfigure(0, weight=5)
        workspace.columnconfigure(1, weight=6)
        workspace.rowconfigure(0, weight=1)
        left_outer = ttk.Frame(workspace)
        left_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        scroll_area = ttk.Frame(left_outer)
        scroll_area.pack(fill="both", expand=True)
        canvas = tk.Canvas(scroll_area, bg="#EEF3F8", highlightthickness=0, width=420)
        bar = ttk.Scrollbar(scroll_area, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        left = ttk.Frame(canvas)
        item = canvas.create_window((0, 0), window=left, anchor="nw")
        left.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(item, width=e.width))
        right = ttk.Frame(workspace)
        right.grid(row=0, column=1, sticky="nsew")
        self._config(left, left_outer)
        def wheel(event):
            steps = -int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
            canvas.yview_scroll(steps, "units")
            return "break"
        def bind_wheel(widget):
            widget.bind("<MouseWheel>", wheel)
            for child in widget.winfo_children():
                bind_wheel(child)
        bind_wheel(left)
        canvas.bind("<MouseWheel>", wheel)
        self._results(right)
        self._accounts(accounts)
        self._codec(codec)
        footer = ttk.Frame(self.root, padding=(26, 0, 26, 14))
        footer.pack(fill="x")
        self.status = tk.StringVar(value="就绪 · 选择自己的资源开始，或打开已有任务继续。")
        ttk.Label(footer, textvariable=self.status, style="Sub.TLabel").pack(side="left")
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=120)
        self.progress.pack(side="right")

    def field(self, parent, row, text, key, default="", *, values=None, secret=False):
        ttk.Label(parent, text=text).grid(row=row, column=0, sticky="w", pady=5)
        var = self.var(key, default)
        widget = (ttk.Combobox(parent, textvariable=var, values=values, state="readonly") if values else
                  ttk.Entry(parent, textvariable=var, show="●" if secret else ""))
        widget.grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=4)
        return widget

    def _config(self, parent, footer):
        source = ttk.LabelFrame(parent, text="资源", padding=12)
        source.pack(fill="x", pady=(0, 12))
        self.source_list = tk.Listbox(source, height=3, bg="white", fg="#23364D", relief="flat", selectmode="extended")
        self.source_list.pack(fill="x")
        actions = ttk.Frame(source)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="添加文件", command=self.add_files).pack(side="left")
        ttk.Button(actions, text="添加文件夹", command=self.add_dir).pack(side="left", padx=6)
        ttk.Button(actions, text="移除", command=self.remove_inputs).pack(side="left")
        config = ttk.LabelFrame(parent, text="打包与分发", padding=12)
        config.pack(fill="x")
        config.columnconfigure(1, weight=1)
        self.field(config, 0, "格式链 · 内到外", "layers", "lz4,7z")
        self.field(config, 1, "逐层密码 · 逗号分隔", "password", "", secret=True)
        ttk.Label(config, text="例：-,密码；无密码层填 -，7z 自动加密文件名。", style="Sub.TLabel").grid(row=2, column=0, columnspan=2, sticky="w")
        self.field(config, 3, "每卷大小", "size", "1900M")
        self.field(config, 4, "伪装后缀 · 可留空", "disguise")
        self.field(config, 5, "门面视频 · 可留空", "video")
        ttk.Button(config, text="选择 MP4", command=self.pick_video).grid(row=6, column=1, sticky="e")
        self.field(config, 7, "视频合并方式", "merge", "ZIP 偏移修正", values=["ZIP 偏移修正", "copy /b 纯拼接"])
        ttk.Label(config, text="本体网盘 · 可多选").grid(row=8, column=0, sticky="w", pady=5)
        disks = ttk.Frame(config)
        disks.grid(row=8, column=1, sticky="ew", padx=(12, 0))
        self.body_disks = {}
        for i, disk in enumerate(PROFILES):
            var = tk.BooleanVar(value=disk == "quark")
            self.body_disks[disk] = var
            ttk.Checkbutton(disks, text=PROVIDERS[disk]["label"], variable=var,
                            command=self.refresh_share_choices).grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 8))
        self.field(config, 9, "中转方式", "form", "直接分享", values=["直接分享", "简易中转", "加密中转"])
        self.field(config, 10, "第一跳网盘", "hop_disk", "feimao", values=["feimao"] + [d for d in PROFILES if d != "feimao"])
        self.field(config, 11, "第一跳包密码", "hop_password", "", secret=True)
        self.field(config, 12, "给接收方的密码提示", "pwd_hint", "请向分享者获取解压密码。")
        self.expiry_combo = self.field(config, 13, "分享有效期 · 全部网盘", "share_expiry", EXPIRY_LABELS["default"], values=list(EXPIRY_LABELS.values()))
        self.access_combo = self.field(config, 14, "提取码 · 全部网盘", "share_access", ACCESS_LABELS["default"], values=list(ACCESS_LABELS.values()))
        ttk.Label(config, text="只显示所选网盘（含第一跳）共同支持的选项。旧任务续跑沿用已保存设置。",
                  style="Sub.TLabel", wraplength=280).grid(row=15, column=0, columnspan=2, sticky="w")
        for key in ("hop_disk", "form"):
            self.vars[key].trace_add("write", lambda *_: self.refresh_share_choices())
        self.refresh_share_choices()
        actions = ttk.Frame(footer)
        actions.pack(fill="x", pady=(12, 0))
        self.prepare_button = ttk.Button(actions, text="仅生成本地产物", command=lambda: self.new_job(False))
        self.prepare_button.pack(side="left")
        self.publish_button = ttk.Button(actions, text="打包并上传", style="Primary.TButton", command=lambda: self.new_job(True))
        self.publish_button.pack(side="right")

    def refresh_share_choices(self):
        if not hasattr(self, "expiry_combo"):
            return
        disks = [disk for disk, var in self.body_disks.items() if var.get()]
        if self.vars["form"].get() != "直接分享":
            disks.append(self.vars["hop_disk"].get())
        expiry, access = common_options(disks)
        for combo, key, available, labels in (
                (self.expiry_combo, "share_expiry", expiry, EXPIRY_LABELS),
                (self.access_combo, "share_access", access, ACCESS_LABELS)):
            values = [labels[k] for k in available]
            combo.configure(values=values)
            if self.vars[key].get() not in values:
                self.vars[key].set(values[0])

    def _results(self, parent):
        task = ttk.LabelFrame(parent, text="当前任务", padding=12)
        task.pack(fill="x")
        self.plan_label = tk.StringVar(value="尚未选择任务")
        ttk.Label(task, textvariable=self.plan_label, wraplength=470).pack(anchor="w")
        row = ttk.Frame(task)
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="打开任务", command=self.open_plan).pack(side="left")
        ttk.Button(row, text="继续发布", command=self.resume).pack(side="left", padx=6)
        ttk.Button(row, text="暂停", command=self.pause).pack(side="left")
        row = ttk.Frame(task)
        row.pack(fill="x")
        ttk.Button(row, text="打开产物目录", command=self.open_output).pack(side="left")
        ttk.Button(row, text="手动回填分享", command=self.import_share).pack(side="left", padx=6)
        self.task_summary = tk.StringVar(value="每个文件上传完成后自动保存进度。")
        ttk.Label(task, textvariable=self.task_summary, style="Sub.TLabel", wraplength=470).pack(anchor="w", pady=(8, 0))
        result = ttk.LabelFrame(parent, text="加密链接文案", padding=12)
        result.pack(fill="both", expand=True, pady=(12, 12))
        row = ttk.Frame(result)
        row.pack(fill="x", pady=(0, 8))
        self.copy_scheme = tk.StringVar(value="beast")
        combo = ttk.Combobox(row, textvariable=self.copy_scheme, values=["beast", "mojibake", "hajimi"], state="readonly", width=16)
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda _: self.show_copy())
        ttk.Button(row, text="复制文案", command=self.copy_result).pack(side="right")
        self.copy_text = tk.Text(result, height=7, wrap="word", bg="white", fg="#23364D", relief="flat", padx=12, pady=12)
        self.copy_text.pack(fill="both", expand=True)
        self.copy_text.insert("1.0", "发布完成后，这里显示可直接复制的兽曰、魔曰和哈基米链接文案。")
        self.copy_text.configure(state="disabled")
        log = ttk.LabelFrame(parent, text="执行记录", padding=8)
        log.pack(fill="both", expand=True)
        self.log_text = tk.Text(log, height=7, wrap="word", font=("Consolas", 10), bg="#E4ECF3", fg="#23364D", relief="flat")
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")

    def _accounts(self, parent):
        ttk.Label(parent, text="登录一次，后续复用", font=("Microsoft YaHei UI", 19, "bold")).pack(anchor="w")
        ttk.Label(parent, text="在打开的浏览器中完成登录；飞猫建议用手机 APP 扫码。会话仅保存在本机，过期时提示重登。", style="Sub.TLabel").pack(anchor="w", pady=(10, 24))
        self.account_labels = {}
        self.account_browsers = {}
        for disk, provider in PROVIDERS.items():
            box = ttk.LabelFrame(parent, text=provider["label"], padding=(12, 8))
            box.pack(fill="x", pady=4)
            v = tk.StringVar()
            self.account_labels[disk] = v
            ttk.Label(box, textvariable=v).pack(side="left")
            runtime = BrowserRuntime()
            selected = tk.StringVar(value=runtime.browser_for(disk))
            self.account_browsers[disk] = selected
            ttk.Combobox(box, textvariable=selected, values=["chromium", "chrome", "msedge"], state="readonly", width=10).pack(side="left", padx=12)
            state = "normal" if disk in PROFILES else "disabled"
            ttk.Button(box, text="登录 / 刷新会话", state=state, command=lambda d=disk: self.account_action(d, "login")).pack(side="right")
            ttk.Button(box, text="探测当前页面", state=state, command=lambda d=disk: self.account_action(d, "probe")).pack(side="right", padx=10)
        ttk.Button(parent, text="刷新状态", command=self.refresh_accounts).pack(anchor="w", pady=16)
        ttk.Label(parent, text="probe：尚未完成真实上传分享验证    ready：驱动已跑通    blocked：需要处理页面或登录", style="Sub.TLabel").pack(anchor="w")
        self.refresh_accounts()

    def _codec(self, parent):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 14))
        ttk.Label(row, text="方案").pack(side="left")
        self.codec_scheme = tk.StringVar(value="beast")
        ttk.Combobox(row, textvariable=self.codec_scheme, values=["beast", "mojibake", "hajimi", "base64", "base64url"], state="readonly", width=14).pack(side="left", padx=10)
        ttk.Label(row, text="魔曰密钥").pack(side="left", padx=(15, 8))
        ttk.Entry(row, textvariable=self.var("key", "ABRACADABRA"), show="●", width=22).pack(side="left")
        ttk.Label(parent, text="输入链接、分享文本或密文").pack(anchor="w")
        self.codec_input = tk.Text(parent, height=7, wrap="word", relief="flat", padx=12, pady=12)
        self.codec_input.pack(fill="both", expand=True, pady=8)
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="生成密文", style="Primary.TButton", command=lambda: self.convert(False)).pack(side="left")
        ttk.Button(row, text="解回原文", command=lambda: self.convert(True)).pack(side="left", padx=10)
        ttk.Button(row, text="复制结果", command=lambda: self.to_clipboard(self.codec_output.get("1.0", "end-1c"))).pack(side="right")
        self.codec_output = tk.Text(parent, height=7, wrap="word", relief="flat", padx=12, pady=12)
        self.codec_output.pack(fill="both", expand=True, pady=8)

    def add_files(self):
        self.inputs.extend(Path(x) for x in filedialog.askopenfilenames(title="选择资源文件"))
        self.update_inputs()

    def add_dir(self):
        path = filedialog.askdirectory(title="选择资源文件夹")
        if path:
            self.inputs.append(Path(path))
            self.update_inputs()

    def update_inputs(self):
        self.inputs = list(dict.fromkeys(self.inputs))
        self.source_list.delete(0, "end")
        for path in self.inputs:
            self.source_list.insert("end", str(path))

    def remove_inputs(self):
        for i in reversed(self.source_list.curselection()):
            self.inputs.pop(i)
        self.update_inputs()

    def pick_video(self):
        path = filedialog.askopenfilename(filetypes=[("MP4", "*.mp4"), ("所有文件", "*.*")])
        if path:
            self.vars["video"].set(path)

    def start(self, fn):
        if self.busy:
            messagebox.showinfo("任务运行中", "请等待当前操作完成，或先暂停。")
            return
        self.cancel.clear()
        self.busy = True
        self.progress.start(15)
        self.prepare_button.configure(state="disabled")
        self.publish_button.configure(state="disabled")
        def work():
            try:
                self.events.put(("result", fn()))
            except Exception as e:
                self.events.put(("error", str(e)))
            finally:
                self.events.put(("done", None))
        threading.Thread(target=work, daemon=True).start()

    def notify(self, text):
        self.events.put(("log", str(text)))

    def new_job(self, upload):
        if not self.inputs:
            messagebox.showinfo("选择资源", "请先添加自己的资源文件或文件夹。")
            return
        values = {k: v.get() for k, v in self.vars.items()}
        selected_disks = tuple(d for d, v in self.body_disks.items() if v.get())
        if not selected_disks:
            messagebox.showinfo("选择网盘", "请至少勾选一个本体网盘。")
            return
        try:
            from .cli import _parse_layers, _split_pswd
            layers = _parse_layers(values["layers"], _split_pswd(values["password"]), None)
        except (Exception, SystemExit) as e:
            messagebox.showerror("配置有误", str(e))
            return
        out = ROOT / "runs" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
        options = PublishOptions(list(self.inputs), out, layers, values["size"], values["disguise"],
                                 Path(values["video"]) if values["video"] else None,
                                 values["merge"] == "copy /b 纯拼接", selected_disks[0], values["hop_disk"],
                                 {"直接分享": "direct", "简易中转": "simple", "加密中转": "complex"}[values["form"]], values["pwd_hint"])
        options.share_options = ShareOptions(
            next(k for k, v in EXPIRY_LABELS.items() if v == values["share_expiry"]),
            next(k for k, v in ACCESS_LABELS.items() if v == values["share_access"]))
        options.body_disks = selected_disks
        try:
            for disk in list(selected_disks) + ([options.hop_disk] if options.form != "direct" else []):
                options.share_options.validate_disk(disk)
        except ValueError as e:
            messagebox.showerror("分享选项不兼容", str(e))
            return
        if options.form == "complex" and not values["hop_password"]:
            messagebox.showinfo("填写密码", "加密中转需要第一跳包密码。")
            return
        def work():
            path = prepare(options, self.notify)
            self.events.put(("plan", path))
            if upload:
                return asyncio.run(publish(path, notify=self.notify, cancel=self.cancel,
                                           key=values["key"], hop_password=values["hop_password"]))
        self.start(work)

    def open_plan(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(title="选择发布任务", filetypes=[("任务 JSON", "*.json")])
        if path:
            try:
                self.load_plan(Path(path))
            except Exception as e:
                messagebox.showerror("无法打开", str(e))

    def load_plan(self, path):
        plan = json.loads(path.read_text(encoding="utf-8"))
        if plan.get("version") != 2 or "stages" not in plan:
            raise ValueError("请选择新版 publish 生成的 relay-plan.json")
        self.current_plan = path
        bodies = {s["disk"] for s in plan["stages"] if s["id"] != "hop"}
        for disk, var in self.body_disks.items():
            var.set(disk in bodies)
        self.vars["form"].set({"direct": "直接分享", "simple": "简易中转", "complex": "加密中转"}[plan["form"]])
        hop = next((s for s in plan["stages"] if s["id"] == "hop"), None)
        if hop:
            self.vars["hop_disk"].set(hop["disk"])
        self.refresh_share_choices()
        saved_share = ShareOptions(**plan.get("share_options", {}))
        self.vars["share_expiry"].set(EXPIRY_LABELS[saved_share.expiry])
        self.vars["share_access"].set(ACCESS_LABELS[saved_share.access])
        self.plan_label.set(str(path))
        self.task_summary.set(plan["state"] + " · " + " / ".join(
            f"{s['id']} {s['disk']}：{s['state']} {len(s['uploaded'])}/{len(s['files'])}" for s in plan["stages"]))
        self.copies = {s: p.read_text(encoding="utf-8").rstrip("\n") for s in plan["schemes"]
                       if plan["state"] == "complete" and (p := path.parent / "copy" / (s + ".txt")).exists()}
        self.show_copy()

    def resume(self):
        if not self.current_plan:
            self.open_plan()
        if self.current_plan:
            path = self.current_plan
            key, hop = self.vars["key"].get(), self.vars["hop_password"].get()
            self.start(lambda: asyncio.run(publish(path, notify=self.notify, cancel=self.cancel, key=key, hop_password=hop)))

    def pause(self):
        self.cancel.set()
        self.status.set("正在暂停 · 本地打包会在当前阶段完成后停止；上传检查点将保留。")

    def open_output(self):
        folder = self.current_plan.parent if self.current_plan else ROOT / "runs"
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))

    def import_share(self):
        if self.busy or not self.current_plan:
            messagebox.showinfo("先打开任务", "暂停当前任务并打开任务文件后回填。")
            return
        stage_id = simpledialog.askstring("回填阶段", "本体填 body，第一跳填 hop：", initialvalue="body")
        if not stage_id:
            return
        text = simpledialog.askstring("分享文本", "粘贴你已上传文件的完整分享文本（含提取码）：")
        if not text:
            return
        try:
            import_share(self.current_plan, stage_id, text)
            self.load_plan(self.current_plan)
        except Exception as e:
            messagebox.showerror("回填失败", str(e))

    def account_action(self, disk, op):
        browser = self.account_browsers[disk].get()
        self.start(lambda: asyncio.run(getattr(BrowserRuntime(notify=self.notify, cancel=self.cancel,
                                                             browser_channel=browser), op)(disk)))

    def refresh_accounts(self):
        for disk, var in self.account_labels.items():
            if disk not in PROFILES:
                var.set("自动驱动待适配 · 可手动回填分享")
                continue
            status_file = DEFAULT_STATE / (disk + "-status.json")
            try:
                status = json.loads(status_file.read_text(encoding="utf-8"))["status"] if status_file.exists() else "probe"
            except (ValueError, KeyError):
                status = "probe"
            var.set(("已有本机会话" if (DEFAULT_STATE / (disk + ".json")).exists() else "尚未登录") + " · " + status)

    def convert(self, decode):
        scheme, text, key = self.codec_scheme.get(), self.codec_input.get("1.0", "end-1c"), self.vars["key"].get()
        if not text:
            return
        def work():
            if decode:
                from .encoders import beast, hajimi, mojibake, plain
                if scheme == "beast":
                    output = beast.decode(text, dialect="auto")
                elif scheme == "hajimi":
                    output = hajimi.decode(text)
                elif scheme == "mojibake":
                    output = mojibake.decode(text, key=key)
                else:
                    output = plain.decode(scheme, text)
            else:
                output = encode_copy(text, [scheme], key=key)[scheme]
            self.events.put(("codec", output))
        self.start(work)

    def show_copy(self):
        self.copy_text.configure(state="normal")
        self.copy_text.delete("1.0", "end")
        self.copy_text.insert("1.0", self.copies.get(self.copy_scheme.get(), "当前任务还没有此版本文案。"))
        self.copy_text.configure(state="disabled")

    def to_clipboard(self, text):
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.status.set("已复制到剪贴板")

    def copy_result(self):
        self.to_clipboard(self.copies.get(self.copy_scheme.get(), ""))

    def poll(self):
        while not self.events.empty():
            kind, data = self.events.get_nowait()
            if kind == "log":
                self.status.set(data)
                self.log_text.configure(state="normal")
                self.log_text.insert("end", data + "\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
            elif kind == "plan":
                self.load_plan(data)
            elif kind == "codec":
                self.codec_output.delete("1.0", "end")
                self.codec_output.insert("1.0", data)
                self.status.set("文本转换完成")
            elif kind == "result" and data and "copies" in data:
                self.copies = data["copies"]
                self.show_copy()
            elif kind == "error":
                self.status.set("操作已停止；检查提示后可以继续。")
                if not self.closing:
                    messagebox.showerror("需要处理", data)
            elif kind == "done":
                self.busy = False
                self.progress.stop()
                self.prepare_button.configure(state="normal")
                self.publish_button.configure(state="normal")
                self.refresh_accounts()
                if self.current_plan:
                    self.load_plan(self.current_plan)
        if self.closing and not self.busy:
            self.root.destroy()
        else:
            self.root.after(100, self.poll)

    def close(self):
        self.closing = True
        if self.busy:
            self.pause()
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    main()
