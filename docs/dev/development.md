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
- Node.js 18+ 在 PATH 上时运行魔曰与哈基米互通测试；ffmpeg 在 PATH 上（或 `MISONG_FFMPEG` 指向 ffmpeg.exe）
  时运行门面视频播放校验；未安装 Playwright 时浏览器驱动测试跳过。
- 界面自查：`.venv\Scripts\python scripts\ui_preview.py [--dark]` 用模拟数据在无头 Edge 中截取各页面到 `tmp/ui`。
- 大文件离线验证：`scripts/verify_large_cover.py --work <目录> --video <mp4> --ffmpeg <ffmpeg.exe> [--winrar <WinRAR.exe>]`，
  会生成 >4GB 样本并保留现场，不自动清理。
- `misong.py gui --debug`（或 `MISONG_DEBUG=1`）打开 WebView 开发者工具。

## 更名兼容

- 发行包、Python 包和 CLI 均为 `misong`；旧版 `nde` 清单名称集中定义在 `misong.metadata`，
  按新名优先、旧名回退读取，v1/v2 内容格式不变；新文件只写新名。
- 任务元数据同时读取 `misong-task.json` 和旧版 `nde-task.json`，更新时保留已有字段并写新名。
  旧任务的远端目录、检查点和文件指纹沿用原记录，不因更名重新上传。
- 源码运行的仓库根推算深度不变，继续使用 `rpa/state/`、`ui-settings.json`、`ui-templates.json`。
  包改名不搬迁浏览器档案或认证数据；数据目录可配置及安装后的迁移仍按 0.2 前置工作实施。
- `MISONG_DEBUG`、测试用 `MISONG_FFMPEG` 优先，仍兼容旧 `NDE_DEBUG`、`NDE_FFMPEG`。

## 目录结构

```
misong.py                入口（等同安装后的 misong 命令）
start-gui.cmd         Windows 双击启动桌面应用
src/misong/
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

文件区“粘贴路径”通过 `Api.clipboard_paths` 显式读取系统剪贴板，再复用 `describe_paths`；Windows 原生 Unicode 剪贴板读取不依赖 WebView 文档焦点，读取失败不回显原文。
文件区提示与操作按钮分行布局；浏览器回归覆盖 940、1090、1320 像素宽度，检查提示可读且三个按钮均在区域内。

## 打包层模型

- `layers.py` 定义四类层：archive（压缩/加密）、cover（门面视频）、split（分卷）、rename（改后缀），按内到外执行。
  `.misong.json` v2 记录完整层序（外到内存储），v1 清单、旧模板和旧任务设置自动兼容。
- 压缩层支持 7z/ZIP 密码，有密码的 7z 自动加密文件名；后续 7z/ZIP 层默认仅存储，避免重复压缩。
  raw 格式（lz4 等）遇到目录时自动垫一层 tar。
- cover、split、rename 只接受单文件；split 后要继续叠层须先 archive 把全部卷归档。
  cover 前必须是 7z/ZIP 载荷，产物恒为 `.mp4`。
- 门面视频把归档嵌入 `ftyp` 之后的 `free` box，自动修正媒体偏移；超过 4GB 时 stco 提升为 co64，
  ZIP 按 ZIP64 修正偏移，并在尾部 free box 补中央目录与 EOCD。仅支持非碎片化 MP4；旧 `merge` 命令保留尾部拼接。
- 分卷命名 `名字.001/.002`，不超过阈值则保持单文件；数字默认 MB，显式 `B` 按字节；`join` 兼容旧 `.partNNN`。
- 只上传最终层文件/分卷；`.misong.json`、`.misongsplit.json`、`RESTORE.txt` 只留本地，可选 `.sha256` 默认关闭。
- 每次开始前预检中间空间、总读写量和耗时（按 150MB/s 粗估）；每层完成即清理上层临时文件，
  峰值约 2–3 份资源；目标盘不足时换最大可用本地盘，都不足则阻止。
- 7-Zip 定位顺序：内置 `7za.exe`（也识别 7z.exe + 7z.dll 布局）→ 已安装的 7-Zip → py7zr / pyzipper 回退。
  7za 不含 RAR 解码。

## 网盘驱动约定

实现在 `src/misong/rpa/`，发布编排在 `src/misong/publish.py`，现场机制与选择器依据见[RPA 现场机制](rpa-research.md)。

- 只走网站正常的上传、分享交互；不实现私有对象存储签名、验证码破解或账号前置绕过。
- 每个任务建独立目录，只分享该目录；精确匹配文件列表中的文件行，传输队列里的同名文字不算成功。
  不得把首卷成功或单纯登录视为整批上传分享成功。
- 多本体盘顺序上传、复用同一份产物；本体完成后才填写 guide 并上传第一跳。
- `PublishOptions.task_name/folder_name` 和 `prepare_upload` 的同名参数供 CLI / 桌面端共用；
  名称先校验再创建本地任务。标题写 `misong-task.json`，远端目录写各 stage 的 `folder`。
  自定义目录带 `custom_folder`；驱动拒绝已有同名目录，确认新建后立即回调写 `folder_created` 检查点，
  续跑才可重新进入。若进程在新建与检查点之间终止，保守停止，人工核对后另建新任务；不自动认领目录。
  中转第一跳加 `-hop`；换链失效重建时仍分配独立随机目录，不复用旧指引目录。
- 分享有效期、提取码统一保存；GUI 按所有目标盘（含第一跳）的能力交集展示（`share_options.py`）。
- 迅雷传输列表和 123 进度面板须用站点自己的关闭控件收起；不使用强制点击或移除遮罩。
- 夸克分享的有效期和提取码：可见单选仍用勾选；隐藏或点不中的单选改为点击同名可见文案，并核对单选或选中样式。
- 刷新按钮被传输面板挡住时，跳过这一次点击并继续等待文件行确认；不把遮挡当成上传失败，也不强制点击或移除遮罩。
- 飞猫多文件须逐个发布后再创建目录分享。
- 飞猫分享形式的下拉菜单挂在页面上、不在分享弹窗内部；打开选择框后要点可见菜单项，并核对输入框的值。
- 飞猫私密链接的访问密码写在链接片段（`#密码：`）里。文案解析优先取片段，不能把链接前面的“密码”标签读成 `https`。

### 账号与会话

- 登录窗口在成功保存后保留，直到用户关闭；发布任务在结束或异常清理时关闭其任务浏览器。
- 有头模式登录及认证等待不限时；无头模式未确认登录时 30 秒暂停/失败并保留检查点。
- 支持 `--browser chrome/msedge/chromium`，按盘保存选择；持久档案按盘和渠道隔离。
  飞猫、UC、迅雷、123 另保存标签页 sessionStorage；不复制个人浏览器档案。
- 只在确认第一方登录后保存状态，不用匿名页面元素判断登录，不把有效会话覆盖为匿名快照。
- 持久档案重开也会丢失会话 Cookie；首次认证导航前，从已验证快照补回档案中缺失的会话 Cookie
  （`expires == -1`，按名称、域名、路径和分区区分）。保留档案中的现有 Cookie、到期时间及来源存储；
  不恢复快照中带到期时间的 Cookie，不延长平台会话，也不保证服务端尚未撤销登录。
  使用 `add_cookies`，不向 `launch_persistent_context` 传不支持的 `storage_state`，不整体替换持久档案存储。
- 标签页会话按实际登录来源保存，恢复时仅接受入口或适配列表中的平台域名（兼容 `www`）、相同协议和端口；不跨来源复制数据。
- 手机绑定、短信、扫码等账号验证由账号所有者完成；复用现有会话以降低操作频率。
- `rpa/state/` 含认证状态、锁、账号结果和显式启用的诊断截图/HTML，不得提交或复制进文档。

### 驱动接口

- `DiskDriver` 提供 `ensure_login(context)`、`upload(page, files, folder)`、`share(page, entry_ids)`。
- 状态字段 `probe / ready / blocked`：`ready` 表示该账号驱动完成过上传分享，不保证会话始终有效。
- 逐文件成功即写检查点；重跑先核对本地产物 SHA-256，已有阶段的分享直接复用。
- `PublishOptions.cleanup_after_upload` / CLI `--cleanup-after-upload` 默认关闭，仅适用于加工后发布。
  准备时写入 `local_cleanup` 的精确生成文件、SHA-256、输入保护路径和任务根目录；生成中转时追加登记。
  所有阶段均有逐文件上传确认和分享，文案及 complete 检查点保存后才删除登记文件；不递归扫描删除，不清理旧任务或单独上传的源文件。
  删除前核对任务目录、链接/硬链接、输入范围及哈希；源资源、清单、任务、还原说明、文案与未登记文件保留。
  清理逐文件保存进度，文件占用/变化只记清理未完成，不改变发布成功状态；`publish --plan <任务>` 可重试，已分享阶段不因登记产物已清理而重传。
  选项保存在本任务用于续跑，不存全局默认，复用设置及新建任务时关闭；`--plan` 不接受覆盖该选项。
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
