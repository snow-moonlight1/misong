# 账号有效性与驱动只读自检交接

> 2026-10-30 S 已完成 CLI/API/GUI/发布接线及取消清理，以下保留 F 初始交付记录。当前默认检查预算为 CLI/API/发布每盘 45 秒；服务库默认值仍为 20 秒。完整范围及真实账号验证边界见[发布记录](../releases/0.2.0.md)。

本包实现原 v0.2 的⑧登录有效性检查、④第二级只读选择器检查服务，供 S 接入 CLI、桌面 API 和发布流程。
本轮只修改 `rpa/drivers.py`、`rpa/runtime.py`、`account_health.py`、两份专用测试和本文；公共入口、版本、
路线图、支持情况与 CHANGELOG 由 S 汇总。**服务实现与模拟验证不等于六盘真实账号验收。**

## 服务入口

```python
import asyncio
from threading import Event

from misong.account_health import AccountHealth
from misong.rpa.runtime import BrowserRuntime

cancel = Event()
runtime = BrowserRuntime(
    state_dir=chosen_private_state_dir,  # 沿用调用方的数据目录
    headless=True,
    browser_channel=None,              # 沿用各盘已保存的浏览器选择
    cancel=cancel,
    notify=lambda message: None,
)
health = AccountHealth(runtime)

async def inspect():
    single = await health.check_login("quark", timeout=20)
    batch = await health.check_all(timeout=20)   # 默认全部六个自动盘，逐盘执行
    subset = await health.check_all(["quark", "baidu"], timeout=20)
    selectors = await health.selfcheck("quark", timeout=20)
    return single.to_dict(), [r.to_dict() for r in batch], selectors.to_dict()

result = asyncio.run(inspect())
```

已有 runtime 也可直接调用 `await runtime.check_login(disk, timeout=20)` 和
`await runtime.selfcheck(disk, timeout=20)`。这些方法委托同一服务，不调用原 `probe()` 或 `open()`。
未注入 runtime 时，`AccountHealth()` 默认无头，使用现有路径解析器及浏览器配置。

`check_all(disks=None)` 检查 `REGISTRY` 的六盘：飞猫、夸克、UC、迅雷、123、百度；传入子集时规范化别名、去重。
不支持的盘返回 `unsupported`，报告的 disk 固定为 `unsupported`，避免把误传的 URL 或敏感文本带出。
每份 `HealthReport` 有 `disk / status / code / headless / attempts / selectors`，可用 `.to_dict()` 交给 JSON 编码器。

### 登录结果

| status | 含义与调用方处理 |
| --- | --- |
| `logged_in` | 当前页面与第一方来源匹配，既有 `is_logged_in()` 证据成立；并非永久有效保证 |
| `logged_out` | 明确登录入口、登录路由或会话失效提示；由所有者重新登录 |
| `verification_required` | 可见验证码、安全验证、手机号绑定、账号限制提示；交给所有者处理 |
| `network_error` | 导航失败、导航超时、HTTP 错误或可见网络故障；提示重试，不能写成已过期 |
| `unknown` | 非预期来源、登录提示与文件页证据矛盾等；不能宣称有效或失效 |
| `timeout` | 有界检查结束仍无确定结果；`login_markers_missing` 不表示登录失效 |
| `cancelled` | 所有者的 Event 已置位；不继续登录等待 |
| `unsupported` | 无检查实现或缺浏览器依赖 |
| `error` | 配置、占用锁、浏览器启动/关闭等检查故障；不能写成已过期 |

HTTP 401/403/429 仅在页面有明确人工验证证据时归为 `verification_required`，否则仍是网络/访问故障。
有头重试默认关闭；显式 `headed_retry=True` 时，无头的未登录、网络、人工验证、未知或超时最多再做**一次**有头检查。
两次共享每盘 timeout 预算，首次最多分配一半；有头重试仍不进入扫码/绑定等待，不自动输入或点击登录。
`headless=False` 的 runtime 只检查一次。调用期间不修改原 runtime 的配置。

## 发布前预检

```python
from misong.account_health import AccountPreflightBlocked, required_disks

# plan 是已校验的 v2 relay-plan 内存字典，不是文件路径。
pending_disks = required_disks(plan)
report = await health.preflight(plan, timeout=20)
try:
    report.require_ready()
except AccountPreflightBlocked as error:
    # error.report 与 report 相同，供 UI 区分重新登录、网络重试、人工操作和取消。
    show_preflight_result(error.report.to_dict())
    raise
```

规则与现有 `publish.publish()` 一致：只选 `not stage.get("share")` 的阶段，按盘去重；上传已完成但分享尚未完成仍要检查。
已分享的本体跳过，尚未分享的第一跳仍要检查。所有阶段已有分享、仅重试第四步文案或清理时，disks/results 均为空、
`allowed=True`，不打开浏览器，不要求任何网盘重新登录。不能只凭 `plan.state` 或 `text_delivery.share_complete` 推断跳过。
手动回填的已有 `share` 同样复用；换链清掉某个阶段的 `share` 后，该盘会重新进入预检。

`allowed` 仅在所有所需网盘均 `logged_in`（或没有需检查的盘）时为真。任何其他结果都阻止开始远端发布，
同时保留原始分类；网络错误不能显示成账号过期。预检不会修改计划、文件检查点、旧分享或账号状态文件。
检查取消时，调用方应按现有暂停语义结束；不要把取消改记成登录失效。

## 驱动可选接口与只读清单

`DiskDriver.check_login(page, *, timeout=10)`、`selfcheck(page, *, timeout=10)` 基类明确返回 `unsupported`。
浏览器驱动复用原 `is_logged_in()` 和运行时读取的有效 profile；直接调用驱动自检时，调用方须先确认该页面登录有效。
公共服务自动先检查登录，再检查选择器。

`BrowserDiskDriver.selfcheck_selectors()` 从每盘 profile 声明实际使用的关键入口：

- `upload`：文件输入存在；输入被隐藏是网站正常做法，只检查挂载，绝不设置文件。
- `upload_trigger / upload_menu / upload_button`：配置中存在时检查，保持与上传逻辑一致。
- `new_folder_menu / new_folder`：菜单入口和新建入口；百度按 toolbar 限定范围。
- `share`：优先使用 `share_trigger`，否则按 `share_scope` 内的精确分享文案查找；百度增加 profile 中的分享按钮声明。
- `share_more`：飞猫更多入口。

每个 `SelectorCheck` 只返回 `item` 与 `status`，例如 `{"item": "upload", "status": "missing"}`。
item 指向有效 profile 的同名配置；`share` 对应 `share_trigger`（如有）或 `share`。不把原始选择器、页面文字或错误堆栈放进报告。

| 项目 status | 含义 |
| --- | --- |
| `passed` | 输入存在，或可见入口可用且中心点未被遮挡 |
| `missing / hidden / disabled` | 必需入口缺失、隐藏或禁用 |
| `not_configured` | 必需的选择器配置缺失或为空 |
| `covered` | 可见入口被页面遮罩覆盖；不移除遮罩、不强制点击 |
| `ambiguous` | 精确文案同时匹配多个可见入口，实际驱动不能唯一选择 |
| `selector_error` | 选择器执行错误；包括人为损坏的 CSS，不返回原始 Playwright 异常 |
| `not_observed` | 分享或菜单子项依赖选中/展开，当前未呈现或未启用；不能计作成功 |

总结果为 `passed / failed / incomplete / timeout / cancelled / unsupported`；登录未通过时保留登录检查分类。
自检不点击、不选中文件、不展开菜单、不滚动绕过遮挡、不上传、不创建目录或分享。
因此空盘、延迟挂载菜单、未选中文件时可能得到 `incomplete`，不能宣称所有分享路径已验证。
只读检查只证明当前页面可观察的入口；弹窗内创建分享、有效期设置及远端读写仍需独立功能验收。

## 会话与资源边界

`BrowserRuntime.open_inspection()` 用已验证的 `<disk>.json` 快照建立临时非持久上下文，沿用 profile、
`browser_for()` 和按盘/浏览器渠道隔离的 sessionStorage 文件。sessionStorage 继续按原来源白名单恢复。
不打开或复制活跃 `browser-data/` 档案，不使用个人浏览器档案；临时上下文中的 Cookie/存储变更随关闭丢弃。
检查结果针对快照；若有效认证尚未保存到快照，不能据此保证与活跃专用档案完全一致，应通过既有显式登录保存流程处理。

不调用 `ensure_login()`、`_save_auth()`、`_record()`，不写浏览器选择，不覆盖有效登录快照，亦不删除/清空任何已有会话。
使用现有按盘独占锁，占用时返回检查故障；仅锁文件可能被创建。
检查操作包含浏览器启动和导航的预算，取消 Event 每 50 ms 轮询；每次尝试清理上下文与浏览器各最多额外 3 秒。
批量最大工作预算为盘数乘单盘 timeout，另加有限清理开销；外部 `asyncio.CancelledError` 传播给调用方并清理资源。

普通检查不输出 Cookie、认证数据、密码、分享地址或原始异常；服务本身不保存检查结果，桌面调用方仅保存公开状态报告。
登录批量检查不抓取页面。只读选择器自检仅在用户显式启用 `selfcheck --diagnostics` 或桌面开关时，将失败截图/HTML 保存到独立的本机私密目录；诊断包默认只列文件元数据，不附带内容，也不调用普通发布的抓取路径。
S 如需账号页记录最后检查时间，可单独保存报告白名单；不得用一份检查报告覆盖原认证文件或 `verified_at` 历史事实。

## 可选金丝雀的独立入口

`await health.run_canary(disk, allow_remote_writes=True, timeout=30)` 是独立主动扩展入口；缺少显式开关时直接拒绝。
普通 `check_login / check_all / preflight / selfcheck` 永不调用它。S 不得把该开关绑定到“全部检查”或默认自检。
未来所有者明确选择远端写入时，驱动须独立实现 `canary_selfcheck(page, *, allow_remote_writes=False)`，
完整覆盖独立测试目标的上传、分享、读回与清理，才可报告通过；入口对整个主动操作也设置超时和取消。

**当前六个驱动没有完整的金丝雀读回/删除实现，显式开启仍返回 `unsupported / canary_unsupported`，且不打开浏览器。**
这不是远端金丝雀已实现或已验收的声明；不能把占位回调的测试算作六盘远端验证。本包没有执行任何主动金丝雀。

## 需要 S 接线与汇总的调用点

1. `cli.py`：`account check <disk>`、`account check --all [--headless]` 调用服务；新增 `selfcheck --disk` 调用只读服务。
   不要复用会等待人工登录并保存原始现场的 `runtime.open()` 或 `probe()`。按 status 展示并返回合适退出码。
2. `desktop/api.py`：账号单盘检测、全部检查、自检共用服务，传入本机 state_dir、渠道和任务取消 Event；
   `desktop/web/` 展示逐盘/逐项结果，网络错误给重试入口、验证给所有者处理入口、`incomplete` 明确为未完整观察。
3. `publish.py`：在计划版本/阶段合法性确认后、远端访问前调用 `preflight(...).require_ready()`；
   使用本次 runtime，保留测试假 runtime 的注入能力，取消按暂停处理。不要在纯第四步重试前强行按全局账号列表检查。
4. 公共 `docs/status.md`、`docs/roadmap.md`、开发指南及 `CHANGELOG.md`：记录服务与接线进度、模拟结果和真实验证边界；
   第④一级环境检查仍使用原 doctor，第二级入口与金丝雀主动入口保持分离。本包未修改任何公共文档/版本字段。
5. 若保留金丝雀 UI/CLI，默认关闭，当前六盘显示“不支持”；不得宣称真实上传、读回、删除通过。

## 验证记录

测试文件：`tests/test_account_health.py`、`tests/test_driver_selfcheck.py`。
六盘使用真实 Playwright Chromium 引擎与全量 route 拦截的自制页面；快照保护使用 pytest 临时目录中的合成 Cookie、
localStorage/sessionStorage 和专用档案哨兵。取消/总预算/重试策略部分使用注入 runtime；没有访问真实网盘或读写既有真实会话。

首轮专用测试：

```powershell
.venv\Scripts\python -m pytest -q tests/test_account_health.py tests/test_driver_selfcheck.py
```

初次完成 **35 passed，78.83 秒**。随后增加矛盾登录证据、导航超时分类、全部账号有效时预检放行及重复/禁用入口测试。

```powershell
.venv\Scripts\python -m pytest -q tests/test_account_health.py tests/test_driver_selfcheck.py tests/test_browser_driver.py tests/test_new_drivers.py tests/test_baidu.py tests/test_providers.py tests/test_publish.py tests/test_text_publish.py
# 137 passed，236.88 秒（此轮收集后补了 1 项重复/禁用入口测试）

.venv\Scripts\python -m pytest -q tests/test_account_health.py tests/test_driver_selfcheck.py tests/test_browser_selection.py
# 43 passed，90.19 秒

.venv\Scripts\python -m pytest -q tests/test_driver_selfcheck.py tests/test_baidu.py
# 16 passed，65.77 秒；最终复验缺失配置逐项报告及百度实际分享复用 profile 选择器
```

以上回归均无跳过，测试有重叠，不合计为独立用例数。本轮未运行完整 pytest 套件。
另对本包五份 Python 文件按 Python 3.11 语法解析通过，`git diff --check` 通过。

尚未完成：真实六盘已登录/已过期账号检查、有头风控回退实测、真实页面选择器自检、远端金丝雀，
以及 S 所有权范围内的 CLI/API/UI/发布接线与最终整体验收。没有把这些项目写为已验收，也没有改变其 v0.2 范围。
# S 集成更新（2026-10-30）

已接入 account check、selfcheck、桌面单盘/全部检查和发布前预检。预检只访问没有分享检查点的盘，取消按暂停处理，网络错误不写成登录过期；检查缓存与认证快照分开。主动金丝雀保持可选扩展且六盘明确不支持，不把只读检查标为写入验收。上方 F 的模拟测试记录保留，最终整体验收见[支持情况](../status.md)和[发布记录](../releases/0.2.0.md)。
