# 环境自检（doctor 第一级）

`misong.doctor` 对应[路线图](../roadmap.md) ④ 驱动自检的第一级：只读检查运行环境，
为 `misong doctor` 和故障排查提供统一数据。主线已接入 CLI 与桌面 `check_environment()` API，
CLI 支持 `--json`；必需项失败退出码为 1，其余情况为 0。桌面暂未新增诊断页面。

## 接口

```python
from misong.doctor import check_environment

report = check_environment()
# {"ok": True, "checks": [{"id": "python", "required": True, "status": "ok", "message": "..."}]}
```

- `ok`：仅在**必需项**出现 `error` 时为 `False`；可选项缺失只会产生 `warn`。
- `checks`：固定顺序的列表，每项含 `id`、`required`、`status`、`message`。
- `status`：`ok` / `warn` / `error`；`message` 为中文，可直接展示。
- 每次调用都会重新探测，不缓存结果，也不读取或写入设置。

## 检查项

| `id` | 必需 | 检查内容 | 缺失或失败时 |
| --- | --- | --- | --- |
| `python` | 是 | 当前解释器是否不低于 3.11 | `error`，提示最低版本 |
| `dependencies` | 是 | `cryptography`、`py7zr`、`pyzipper`、`lz4`、`zstandard`、`brotli` | `error`，列出缺失项 |
| `7zip` | 是 | `formats.sevenzip_executable()` 的定位结果，并执行一次 7-Zip 的 `i` 子命令 | `error`（未找到、超时、无法执行或返回非零） |
| `node` | 否 | `shutil.which("node")` 与 `node --version`，建议 18+ | `warn`，魔曰不可用 |
| `playwright` | 否 | `playwright` 包是否可导入，读取分发包版本 | `warn`，网页上传不可用 |
| `browsers` | 否 | Playwright Chromium 安装目录；缺失时再用 `desktop.api.installed_browsers()` 查系统 Chrome/Edge | `warn`；有系统通道时仍视为网页上传可用 |
| `desktop` | 否 | `webview`（pywebview）是否可导入 | `warn`，桌面界面不可用 |

说明：

- 7-Zip 缺失按必需项处理：项目随包分发 `vendor/7zip/7za.exe`，缺失通常意味着安装不完整。
  Python 回退仍能处理部分格式，但本检查不会把这种情况当作完全正常。
- Node 仅魔曰需要，Playwright 与浏览器仅网页上传需要，pywebview 仅桌面界面需要；
  三者都不影响基础打包与还原。
- Playwright 浏览器只检查安装目录与 `INSTALLATION_COMPLETE` / 可执行文件是否存在，
  不启动 Playwright 驱动或浏览器。支持 `PLAYWRIGHT_BROWSERS_PATH`（含 `0`）与各平台默认缓存目录。
- `browsers` 只在 Playwright Chromium 未确认安装时才导入桌面端的浏览器探测函数；
  导入失败时按 Windows 常见安装目录或 `PATH` 自行判断，报告仍会完成。

## 只读与隐私边界

- 不登录、不打开交互浏览器、不访问网盘、不下载安装、不修改设置，也不写入任务、设置或诊断数据。
- 只执行两类无副作用子命令：`node --version` 与 7-Zip 的 `i`；均带 5 秒超时、不经过 shell、
  不继承交互输入，Windows 下不弹控制台窗口。
- 报告不包含可执行文件路径、用户目录、环境变量值或命令原始输出。
  版本号只提取数字部分；异常文本不进入 `message`，避免把路径带进日志或截图。
- 依赖探测使用 `importlib.util.find_spec`，单个依赖缺失或探测抛错只形成结果，不会让整份报告崩溃。
  每个检查外还有兜底：必需项异常为 `error`，可选项异常为 `warn`。

## 测试

```powershell
.venv\Scripts\python -m pytest tests/test_doctor.py -q
```

测试全部使用 `monkeypatch` 和合成路径，不依赖本机是否安装 Node、Playwright 或浏览器，也不访问网络。
覆盖：健康环境、Python 过低、核心依赖缺失、7-Zip 缺失/非零/超时、Node 超时、
不可解码或空输出、系统浏览器回退、可选工具缺失仅警告、异常包裹以及“报告不含路径和环境变量值”。

## 后续集成

- CLI 可新增 `misong doctor`：调用 `check_environment()` 后按 `status` 着色输出，
  有 `error` 时返回非零退出码；`--json` 直接输出该字典。
- 驱动自检（第二级）与本模块分属不同阶段；本模块不导入驱动、不读取账号状态。
- 与诊断包（⑦）共用时，可直接序列化本报告；其中已不含路径、凭据或原始命令输出。
