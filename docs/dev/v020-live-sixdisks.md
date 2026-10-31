# v0.2.0 六网盘真实只读验收报告

> 日期：2026-10-30  
> 基线集成提交：`a4a8435 Integrate F/G/H and prepare v0.2.0`  
> 运行模式：完全只读、串行单盘执行；无任何远端写入（无上传、无分享、无新建/删除目录）；不开启 `--diagnostics`；所有认证快照哈希在测试前后严格核对，未发生任何覆盖、清空或修改。

---

## 一、验收概述与执行环境

- **运行环境**：Windows 11，Python 3.13（`.venv`），Playwright 1.56。
- **快照保护基线**：在检查前对 `rpa/state/` 下全部 27 个状态文件（包括 `quark.json`、`feimao.json`、`uc.json`、`xunlei.json`、`123pan.json`、`baidu.json` 及其对应的 `-browser.json`、`session-data/*.json`）建立 SHA-256 和字节大小基线，并在每项检查后实时校验。
- **未登录隔离策略**：使用全新的临时独立目录 `tmp/unlogged_state`，设置 `MISONG_HOME` 环境变量进行严格隔离，确保测试时不包含任何历史 Cookie、sessionStorage 或持久档案，且不影响主状态目录。
- **真实过期策略**：仅针对确有自然过期现场的现有凭据进行验证；未过期的有效会话保持原样，不伪造凭据，不破坏有效会话。

---

## 二、六网盘实测结果矩阵

### 1. 夸克网盘 (`quark`)

- **浏览器渠道**：`chromium`（由 `quark-browser.json` 显式配置）
- **预算配置**：默认超时 45 秒（无头）；重试超时 90 秒（有头重试）
- **状态验证结果**：
  - **A. 已登录**：**通过**（`status: logged_in`, `code: authenticated_marker`, `headless: true`, `attempts: 1`, 耗时约 23 秒）。准确识别第一方登录态。
  - **B. 未登录**：**异常（超时）**（`status: timeout`, `code: check_timeout`, `attempts: 1`；在 `--headed-retry --timeout 90` 下 `attempts: 2`, `headless: false`, 仍为 `timeout`）。
    - **原因分析**：夸克未登录首页文案为“手机登录”、“微信登录”、“或夸克APP扫码登录”、“请使用夸克网盘APP扫码登录”。驱动通用正则 `r"^(?:登录|去登录|立即登录|请先登录|扫码登录|二维码登录|账号登录|帐号登录|密码登录|短信登录|登录已失效|登录已过期|请重新登录)$"` 未收录“手机登录”和“微信登录”，且 `PROFILES["quark"]` 未配置 `logged_out` 选择器，导致未登录页无法被驱动识别为明确登出，轮询直至超时。
  - **C. 真实过期**：**未验证**（现有会话自然有效，不破坏有效会话）。
- **只读选择器自检 (`selfcheck`)**：**失败**（`status: failed`, `code: selectors_failed`）
  - `upload`: `passed`（文件输入元素已挂载）
  - `new_folder`: `covered`（“新建文件夹”元素存在，但在坐标命中测试中被顶栏遮罩/活动浮层覆盖）
  - `share`: `not_observed`（自检严格只读，未选中文件，分享入口按预期未呈现）
- **人工操作需求**：无弹窗阻断，无需人工验证介入。
- **快照保持情况**：`quark.json` 及相关会话文件 SHA-256 完全一致，未发生任何写入或修改。

---

### 2. 飞猫云盘 (`feimao`)

- **浏览器渠道**：`chromium`（由 `feimao-browser.json` 配置）
- **预算配置**：默认超时 45 秒（无头）
- **状态验证结果**：
  - **A. 已登录**：**通过**（`status: logged_in`, `code: authenticated_marker`, `headless: true`, `attempts: 1`, 耗时约 18 秒）。
  - **B. 未登录**：**通过**（`status: logged_out`, `code: login_required`, `headless: true`, `attempts: 1`, 耗时约 17 秒）。准确识别登录页并归类为 `logged_out`。
  - **C. 真实过期**：**未验证**（现有会话有效）。
- **只读选择器自检 (`selfcheck`)**：**不完全**（`status: incomplete`, `code: selectors_incomplete`）
  - `upload`: `passed`
  - `upload_trigger`: `passed`
  - `new_folder`: `passed`
  - `share`: `not_observed`（条件入口，需选中文件）
  - `share_more`: `not_observed`（条件入口，需选中文件）
- **人工操作需求**：无人工验证码，正常放行。
- **快照保持情况**：`feimao.json` 及 `session-data/feimao-chromium.json` SHA-256 完全一致。

---

### 3. UC网盘 (`uc`)

- **浏览器渠道**：`chromium`（由 `uc-browser.json` 配置）
- **预算配置**：默认超时 45 秒（无头）
- **状态验证结果**：
  - **A. 已登录**：**通过**（`status: logged_in`, `code: authenticated_marker`, `headless: true`, `attempts: 1`, 耗时约 22 秒）。
  - **B. 未登录**：**通过**（`status: logged_out`, `code: login_required`, `headless: true`, `attempts: 1`, 耗时约 14 秒）。
  - **C. 真实过期**：**未验证**（现有会话有效）。
- **只读选择器自检 (`selfcheck`)**：**失败**（`status: failed`, `code: selectors_failed`）
  - `upload`: `passed`
  - `upload_trigger`: `passed`
  - `new_folder`: `covered`（“新建文件夹”被页面头部横幅/VIP促销栏覆盖）
  - `share`: `not_observed`（条件入口，需选中文件）
- **人工操作需求**：直连网络下正常加载，无人工介入。
- **快照保持情况**：`uc.json` 及 `session-data/uc-chromium.json` SHA-256 完全一致。

---

### 4. 迅雷云盘 (`xunlei`)

- **浏览器渠道**：`chromium`（由 `xunlei-browser.json` 配置）
- **预算配置**：默认超时 45 秒（无头）；重试超时 90 秒（有头重试）
- **状态验证结果**：
  - **A. 已登录**：**阻塞（凭据已自然过期）**。现有凭据在真实站点测试中返回 `logged_out`。若需补齐登录态验证，需由所有者手动重新扫码登录。
  - **B. 未登录**：**通过**（`status: logged_out`, `code: login_required`, `headless: true`, `attempts: 1`, 耗时约 10 秒）。
  - **C. 真实过期**：**通过**（`status: logged_out`, `code: login_required`；在 `--headed-retry` 下有头重试确认，`attempts: 2`, `headless: false`, 准确返回 `logged_out`）。**现场证明了自然失效的会话不会被误判为有效，且失效状态下不会清空/删除原快照文件**。
- **只读选择器自检 (`selfcheck`)**：**正确阻断**（`status: logged_out`, `code: login_required`, `selectors: []`）。自检前置登录门禁正常工作，未登录时不执行选择器检查。
- **人工操作需求**：需所有者重新扫码方可恢复已登录状态。
- **快照保持情况**：`xunlei.json` SHA-256 完全一致，即使登录失效也完整保留快照现场。

---

### 5. 123云盘 (`123pan`)

- **浏览器渠道**：`chrome`（由 `123pan-browser.json` 显式配置）
- **预算配置**：默认超时 45 秒（无头）
- **状态验证结果**：
  - **A. 已登录**：**通过**（`status: logged_in`, `code: authenticated_marker`, `headless: true`, `attempts: 1`, 耗时约 11 秒）。
  - **B. 未登录**：**异常（域名未识别）**（`status: unknown`, `code: unexpected_origin`, `headless: true`, `attempts: 1`, 耗时约 8 秒）。
    - **原因分析**：未登录访问 `https://yun.123pan.cn/` 时，123云盘平台重定向至 `https://user.123pan.cn/centerlogin?redirect_url=...`。`PROFILES["123pan"]["hosts"]` 目前仅包含 `['123pan.com', '123pan.cn', '123865.com', '123912.com']`，而驱动的域名比对使用严格的 `host in hosts`（仅剥离 `www.`），未包含子域名 `user.123pan.cn`，导致第一方域名判定失败，返回 `unknown / unexpected_origin` 而非 `logged_out`。
  - **C. 真实过期**：**未验证**（现有会话有效）。
- **只读选择器自检 (`selfcheck`)**：**失败**（`status: failed`, `code: selectors_failed`）
  - `upload`: `passed`
  - `upload_trigger`: `covered`（被全站公告/浮层遮罩拦截）
  - `new_folder`: `covered`（被全站公告/浮层遮罩拦截）
  - `share`: `not_observed`（条件入口，需选中文件）
- **人工操作需求**：无人工验证阻断。
- **快照保持情况**：`123pan.json` 及 `session-data/123pan-chrome.json` SHA-256 完全一致。

---

### 6. 百度网盘 (`baidu`)

- **浏览器渠道**：`chrome`（由 `baidu-browser.json` 显式配置）
- **预算配置**：默认超时 45 秒（无头）
- **状态验证结果**：
  - **A. 已登录**：**通过**（`status: logged_in`, `code: authenticated_marker`, `headless: true`, `attempts: 1`, 耗时约 15 秒）。
  - **B. 未登录**：**异常（信号冲突）**（`status: unknown`, `code: conflicting_login_signals`, `headless: true`, `attempts: 1`, 耗时约 8 秒）。
    - **原因分析**：`PROFILES["baidu"]["logged_in"]` 设置为 `.wp-s-aside-nav`（侧边导航栏容器）。在百度网盘主页 `https://pan.baidu.com/disk/main` 上，即使处于未登录状态，该侧边导航栏依然存在并可见，导致 `is_logged_in()` 判定为 True。同时未登录页面上出现登录提示按钮（“去登录”），驱动检测到 `authenticated` 与 `prompt` 同时为真，触发 `conflicting_login_signals` 判定为 `unknown`，未能归为 `logged_out`。
  - **C. 真实过期**：**未验证**（现有会话有效）。
- **只读选择器自检 (`selfcheck`)**：**异常（选择器超时）**（`status: failed`, `code: selectors_failed`）
  - `upload`: `passed`
  - `new_folder`: `selector_error`
    - **原因分析**：`open_inspection` 中配置了 `context.set_default_timeout(1000)`（1 秒）。百度网盘主页面包含 30 个 `.wp-s-agile-tool-bar` 元素，在执行 `locator.evaluate()` 解析时超过 1000ms 阈值抛出 `PlaywrightError: TimeoutError 1000ms exceeded`，驱动的自检逻辑将所有 `PlaywrightError` 捕获并统一标为 `selector_error`。
  - `share`: `not_observed`（需选中文件）
- **人工操作需求**：无验证码阻断。
- **快照保持情况**：`baidu.json` SHA-256 完全一致。

---

## 三、故障分类与短路机制验证

### 1. 网络故障隔离验证
在隔离环境中将入口 URL 导向不可达服务（本地拒连端口 `127.0.0.1:59999`）：
- 检查结果准确返回 `status: network_error`, `code: navigation_failed`。
- **确认未被误报为会话失效或登录过期**。

### 2. 检查取消与批量短路
在批量任务执行中置位 `cancel` 信号：
- 当前正在执行的网盘即刻中止并返回 `status: cancelled`。
- `AccountHealth.check_all` 触发短路退出（`break`），未继续对后续网盘启动浏览器。

### 3. 批量检查一致性 (`account check --all`)
串行执行全量六网盘检查（`--headless --timeout 45`）：
- 结果依次为：
  - 飞猫：`logged_in`
  - 夸克：`logged_in`
  - UC：`logged_in`
  - 迅雷：`logged_out`（真实自然过期）
  - 123云盘：`logged_in`
  - 百度：`logged_in`
- 批量结果与单盘独立执行结果完全一致，证明多盘串行运行时浏览器资源清理和排他锁机制可靠。

---

## 四、核心结论与交付分类

### 1. 已补齐的真实验收
1. **已登录状态真实识别**：夸克、飞猫、UC、123云盘、百度网盘均实测通过，能准确认定有效登录态。
2. **未登录状态真实识别**：飞猫、UC、迅雷在隔离环境中实测通过，准确识别为 `logged_out / login_required`。
3. **真实自然过期凭据识别**：迅雷凭借现有自然失效凭据实测通过，准确识别为 `logged_out`，且无头/有头重试均验证通过。
4. **认证快照不可变保护**：在全部单盘、批量、超时、失败及过期检查中，`rpa/state/` 下所有凭据快照 SHA-256 均保持一致，严格证明了只读检查不写盘、不清空、不覆盖。
5. **只读选择器挂载检查**：六盘均真实探测了 `upload` 文件输入挂载，未执行任何文件上传；条件入口（如分享、更多）在未选文件时准确反馈 `not_observed`。
6. **故障分类防误报**：证实网络故障不会被误报为登录过期，任务取消能即时生效并阻断后续网盘。

### 2. 仍受账号或环境限制项
1. **迅雷已登录状态**：迅雷凭据当前已自然过期，需账号所有者扫码重新登录后方可复验已登录态及选择器通过项。
2. **夸克/飞猫/UC/123/百度真实过期状态**：五盘现有会话均处于有效期内；依据不破坏有效会话的原则，标为“未验证”。

### 3. 发现的产品缺陷与修复建议（交回集成会话处理）

| 缺陷编号 | 影响网盘 | 现象描述 | 建议修改位置与修复思路 |
|---|---|---|---|
| **BUG-01** | **夸克 (`quark`)** | 未登录状态下无头及有头重试均超时返回 `timeout`，无法判定为 `logged_out` | `src/misong/rpa/drivers.py` 中的 `_login_observation`：增加“手机登录”、“微信登录”到登录提示正则 `r"^(?:登录|去登录|...|手机登录|微信登录)$"`；并在 `PROFILES["quark"]` 中补充登录入口选择器或特定标志。 |
| **BUG-02** | **123云盘 (`123pan`)** | 未登录重定向至 `https://user.123pan.cn/centerlogin` 时，被误判为 `unknown / unexpected_origin` | `src/misong/rpa/drivers.py` 的 `PROFILES["123pan"]["hosts"]`：追加 `'user.123pan.cn'`，或在 `_login_observation` 域名白名单匹配时支持 `*.123pan.cn` / `*.123pan.com` 顶级主域后缀归属判定。 |
| **BUG-03** | **百度网盘 (`baidu`)** | 未登录状态下返回 `unknown / conflicting_login_signals`，未返回 `logged_out` | `src/misong/rpa/drivers.py` 的 `PROFILES["baidu"]["logged_in"]`：将 `.wp-s-aside-nav`（未登录时也渲染的通用侧边栏）替换为仅在登录后存在的元素，例如使用已有的 `'login_user': '.nd-user-info'` 或用户头像/退出登录入口。 |
| **BUG-04** | **百度网盘 (`baidu`)** | 只读自检中 `new_folder` 报错 `selector_error` | `src/misong/rpa/runtime.py` 的 `open_inspection`：1000ms 的全局操作超时对含有数十个工具栏候选的复杂 DOM 树过短；建议将自检期间的特定 evaluate 超时放宽至 3000ms，或优化百度 `toolbar` 选择器为更精确的单一工具栏容器。 |
| **BUG-05** | **夸克 / UC / 123** | 只读自检中 `new_folder` / `upload_trigger` 频繁反馈 `covered` | 自检规范中命中测试严格拒绝被顶栏或促销弹窗遮挡的元素。若自检不主动关弹窗，可将促销提示或顶部横幅导致的遮挡在报告中与真正的选择器失效做明确的分类标注。 |

---

## 五、2026-10-31 缺陷修复与复验

本轮修复已包含在 v0.2.0 发布准备提交中，基于 `a4a8435`。

### 修复内容

| 缺陷 | 修复 |
|---|---|
| BUG-01 | 登录提示正则加入「手机登录」「微信登录」；夸克未登录由 `timeout` 变为 `logged_out / login_required` |
| BUG-02 | `PROFILES["123pan"]` 增加 `login_hosts`：`user.123pan.cn` 仅在 HTTPS、无凭据、443 端口时视为第一方登录跳转 |
| BUG-03 | `PROFILES["baidu"]` 增加「去登录」显式门禁，优先于未登录也会渲染的页面骨架；通用登录冲突改为在 3 秒内继续观察，避免 SPA 水合期误报 |
| BUG-04 | 自检期间把检查页的默认操作超时提高到 3 秒（仅一次性检查页），百度 `new_folder` 不再因复杂工具栏超时 |
| BUG-05 | 命中测试把包裹文本的祖先按钮视为可点击；固定/浮动公告、弹窗、促销层标注 `covered_overlay`，普通布局遮挡仍为 `covered` |

### 复验结果（2026-10-31，真实站点，只读）

- **已登录**：飞猫、夸克、UC、123、百度均为 `logged_in / authenticated_marker`；迅雷为 `logged_out`（现有凭据自然过期）。
- **隔离未登录**：夸克、123、百度均返回 `logged_out / login_required`（修复前分别为 `timeout`、`unexpected_origin`、`conflicting_login_signals`）。
- **批量一致性**：`account check --all --headless --timeout 45` 与单盘结果一致，六盘串行完成。
- **只读自检**：
  - 夸克：`incomplete`，`upload`、`new_folder` 通过，`share` 未选中文件时 `not_observed`（此前的 `covered` 为文本 span 被祖先按钮命中的误报）。
  - 飞猫：`incomplete`，`upload`、`upload_trigger`、`new_folder` 通过，分享子项 `not_observed`。
  - UC：`incomplete`，`upload`、`upload_trigger`、`new_folder` 通过，`share` 为 `not_observed`（`new_folder` 误报已消除）。
  - 123：`failed`，`upload` 通过；`upload_trigger`、`new_folder` 为 `covered_overlay`（未关闭的全站 splash 浮层，非选择器失效）；`share` 为 `not_observed`。
  - 百度：`incomplete`，`upload`、`new_folder` 通过，`share` 为 `not_observed`；不再出现 `selector_error`。
  - 迅雷：`logged_out`，自检前置登录门禁阻断；已登录自检需所有者扫码后复验。

### 本轮仍未覆盖

- 迅雷已登录态及选择器自检：需账号所有者重新扫码。
- 夸克、飞猫、UC、123、百度的真实自然过期态：现有会话有效，无自然失效样本。
- 真实上传、分享、主动金丝雀及平台转码：不在本轮只读验收范围。

