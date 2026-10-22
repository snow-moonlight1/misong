# 开发指南

## 环境与测试

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev,gui,rpa]"
.venv\Scripts\python -m playwright install chromium
.venv\Scripts\python -m pytest -q
```

- 测试只使用假驱动和本地模拟页面，不访问真实网盘。
- 默认只收集 `tests/`，不会把 `runs/` 中安装复核用的克隆副本当成另一套测试收集。
- Node.js 18+ 在 PATH 上时运行魔曰与哈基米互通测试；ffmpeg 在 PATH 上（或 `NDE_FFMPEG` 指向 ffmpeg.exe）
  时运行门面视频播放校验；未安装 Playwright 时浏览器驱动测试跳过。
- 界面自查：`.venv\Scripts\python scripts\ui_preview.py [--dark]` 用模拟数据在无头 Edge 中截取各页面到 `tmp/ui`。
- 大文件离线验证：`scripts/verify_large_cover.py --work <目录> --video <mp4> --ffmpeg <ffmpeg.exe> [--winrar <WinRAR.exe>]`，
  会生成 >4GB 样本并保留现场，不自动清理。
- `nde.py gui --debug`（或 `NDE_DEBUG=1`）打开 WebView 开发者工具。

## 目录结构

```
nde.py                入口（等同安装后的 nde 命令）
start-gui.cmd         Windows 双击启动桌面应用
src/nde/
  cli.py              命令行
  formats.py pack.py layers.py split.py merge.py mp4.py preflight.py
                      层格式、打包/还原、分卷、门面视频、空间与耗时预检
  publish.py workflows.py jobs.py
                      发布编排、单独打包/上传、任务记录
  sharing.py providers.py share_options.py
                      分享文本、网盘链接识别、各盘分享能力表
  encoders/           兽曰 / 魔曰 / 哈基米 / 通用编码；abra_bridge.mjs 是魔曰 Node 桥
  rpa/                浏览器运行时（runtime.py）与各网盘驱动（drivers.py）
  desktop/            pywebview 桌面端：api.py 是 JS 桥，web/ 是前端
  gui.py              旧版 Tk 界面（gui --legacy）
  vendor/7zip/        官方 7za.exe 与许可证（未修改）
  vendor/abracadabra/ 魔曰 V3.0.11 发行文件与许可证（未修改）
scripts/              demo.sh、ui_preview.py、verify_large_cover.py
tests/                pytest；tests/harness/ 为哈基米参考实现测试桩
docs/                 用户文档；docs/dev/ 为开发与调研资料
```

运行时生成、均被 Git 忽略：`runs/`（任务与文案）、`rpa/state/`（专用浏览器档案、会话、界面设置、诊断）、`tmp/`。
桌面端可在左下角选择新任务产物目录；当前目录和历史目录保存在本机 `ui-settings.json`，
任务中心只扫描这些目录的直接子任务与显式导入任务。选择仓库外目录时仍须自行避免提交私密产物。

## 打包层模型

- `layers.py` 定义四类层：archive（压缩/加密）、cover（门面视频）、split（分卷）、rename（改后缀），按内到外执行。
  `.nde.json` v2 记录完整层序（外到内存储），v1 清单、旧模板和旧任务设置自动兼容。
- 压缩层支持 7z/ZIP 密码，有密码的 7z 自动加密文件名；后续 7z/ZIP 层默认仅存储，避免重复压缩。
  raw 格式（lz4 等）遇到目录时自动垫一层 tar。
- cover、split、rename 只接受单文件；split 后要继续叠层须先 archive 把全部卷归档。
  cover 前必须是 7z/ZIP 载荷，产物恒为 `.mp4`。
- 门面视频把归档嵌入 `ftyp` 之后的 `free` box，自动修正媒体偏移；超过 4GB 时 stco 提升为 co64，
  ZIP 按 ZIP64 修正偏移，并在尾部 free box 补中央目录与 EOCD。仅支持非碎片化 MP4；旧 `merge` 命令保留尾部拼接。
- 分卷命名 `名字.001/.002`，不超过阈值则保持单文件；数字默认 MB，显式 `B` 按字节；`join` 兼容旧 `.partNNN`。
- 只上传最终层文件/分卷；`.nde.json`、`.ndesplit.json`、`RESTORE.txt` 只留本地，可选 `.sha256` 默认关闭。
- 每次开始前预检中间空间、总读写量和耗时（按 150MB/s 粗估）；每层完成即清理上层临时文件，
  峰值约 2–3 份资源；目标盘不足时换最大可用本地盘，都不足则阻止。
- 7-Zip 定位顺序：内置 `7za.exe`（也识别 7z.exe + 7z.dll 布局）→ 已安装的 7-Zip → py7zr / pyzipper 回退。
  7za 不含 RAR 解码。

## 网盘驱动约定

实现在 `src/nde/rpa/`，发布编排在 `src/nde/publish.py`，现场机制与选择器依据见[RPA 现场机制](rpa-research.md)。

- 只走网站正常的上传、分享交互；不实现私有对象存储签名、验证码破解或账号前置绕过。
- 每个任务建独立目录，只分享该目录；精确匹配文件列表中的文件行，传输队列里的同名文字不算成功。
  不得把首卷成功或单纯登录视为整批上传分享成功。
- 多本体盘顺序上传、复用同一份产物；本体完成后才填写 guide 并上传第一跳。
- 分享有效期、提取码统一保存；GUI 按所有目标盘（含第一跳）的能力交集展示（`share_options.py`）。
- 迅雷传输列表和 123 进度面板须用站点自己的关闭控件收起；不使用强制点击或移除遮罩。
- 飞猫多文件须逐个发布后再创建目录分享。

### 账号与会话

- 登录窗口在成功保存后保留，直到用户关闭；发布任务在结束或异常清理时关闭其任务浏览器。
- 有头模式登录及认证等待不限时；无头模式未确认登录时 30 秒暂停/失败并保留检查点。
- 支持 `--browser chrome/msedge/chromium`，按盘保存选择；持久档案按盘和渠道隔离。
  飞猫、UC、迅雷、123 另保存标签页 sessionStorage；不复制个人浏览器档案。
- 只在确认第一方登录后保存状态，不用匿名页面元素判断登录，不把有效会话覆盖为匿名快照。
- 手机绑定、短信、扫码等账号验证由账号所有者完成；复用现有会话以降低操作频率。
- `rpa/state/` 含认证状态、锁、账号结果和显式启用的诊断截图/HTML，不得提交或复制进文档。

### 驱动接口

- `DiskDriver` 提供 `ensure_login(context)`、`upload(page, files, folder)`、`share(page, entry_ids)`。
- 状态字段 `probe / ready / blocked`：`ready` 表示该账号驱动完成过上传分享，不保证会话始终有效。
- 逐文件成功即写检查点；重跑先核对本地产物 SHA-256，已有阶段的分享直接复用。
- Windows 检查点原子替换遇到短暂读取锁时，最多重试 6 次（总等待约 0.3 秒）；持续拒绝访问仍报错，保留旧记录并移除临时文件。
- `share-import` 换链会使下游指引和第一跳失效重建，不自动撤销旧分享。
- 站点改版时先用 `account probe <disk>` 或 `--diagnostics` 抓取现场；选择器可用
  `rpa/state/profiles/<disk>.json` 覆盖，无需修改加密核心。

## 第三方组件规则

- 魔曰固定在 V3.0.11（GPL-3.0）。不要升级到 V3.1.0 及以后（AIPL，与本项目的 GPL 不兼容）。
  更换内置文件须同步 `vendor/abracadabra/README.md`、`THIRD_PARTY_NOTICES.md` 与 `tests/test_mojibake_compat.py` 的 SHA-256。
- `7za.exe` 保持官方原件，必须同时分发 `License.txt` 与来源 `README.txt`。
- `encoders/hajimi.py` 改写自 MIT 项目，须保留其版权声明；`encoders/beast.py` 是独立实现，不要复制未声明许可证的代码。
- 修改哈基米、TAR 权限恢复、魔曰 Node 桥前先读相关回归测试，它们覆盖了已知兼容问题。
