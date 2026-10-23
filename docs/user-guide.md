# 使用指南：桌面应用与一键发布

安装步骤见 [README](../README.md#安装)。运行产物默认放在仓库下被 Git 忽略的 `runs/`；
接收方如何还原见[接收方指南](receiver-guide.md)，各网盘支持情况见[支持情况](status.md)。

## 启动

双击仓库根目录 `start-gui.cmd`，或：

```powershell
.venv\Scripts\python nde.py gui
```

桌面端用 pywebview（Windows 上为 Edge WebView2）渲染本地 HTML/CSS/JS，开启高 DPI 感知，
跟随系统浅色/深色。左侧导航：

- **一条龙发布**：分 4 步向导——① 选择资源 → ② 加密打包 → ③ 上传与分享 → ④ 链接文案，每页只显示当前步骤，
  顶部步骤条显示每步摘要，可点回已完成的步骤修改；“下一步”会先检查本步是否填好，第 4 步一键执行，可只生成本地产物。
- **单独使用**：加密打包（可选门面视频、分卷）、上传分享（已有文件直接多盘上传）、链接加密/解密。
- **管理**：任务中心（续跑、手动回填分享、查看文案与产物、搜索/收藏/重命名/备注/删除/导入）、网盘账号。

界面要点：

- **粘贴路径**：发布、打包及上传的文件区可读取剪贴板中的完整路径，每行一个，兼容资源管理器“复制文件地址”附带的双引号；重复路径只添加一次。单独上传会展开目录第一层文件。剪贴板只在点击按钮时读取，不保存。

- **产物目录**：左下角“产物目录”可选择新任务的输出位置，默认是仓库的 `runs/`。
  打包、一条龙发布和单独上传共用该目录；选择会保存在本机并在重启后恢复。
  切换目录不会移动已有文件，先前目录中的任务仍能在任务中心查看和续跑。任务运行中不能切换。

- **发布命名**：一条龙第 1 步、单独上传的文件区可填写“任务名称”和“网盘目录名”。
  任务名称最多 120 字，留空取资源名；目录名最多 100 字，仅接受单个目录名，不能填写路径。
  目录留空仍自动生成 `nde-<任务id>-body-<盘名>`。自定义名称在每个本体盘使用同名目录，
  中转第一跳加 `-hop`；已有同名目录会停止，避免混入旧文件，请换一个新名称。
  续跑保持原名称；“复用设置”会清空这两项，避免新任务重复使用旧目录。任务中心后续重命名只改标题。

- **快速模板**：内置“lz4 → 7z加密”“单层 7z加密”“zip加密”“7z → 7z 双层”四个默认模板，首次启动写入
  `rpa/state/ui-templates.json`，之后与自建模板一样可重命名/删除；删掉默认模板后出现“恢复默认”，只补回缺少的默认项。
  加密层编辑器可“存为模板”，记录四类型层顺序、格式、压缩等级、门面视频路径、分卷大小、后缀和哪些归档层需要密码，**不保存密码**。
  点模板只套用层结构，不弹密码框，直接在层编辑器里填写。
- **共用层编辑器**：添加archive（压缩/加密）、cover（门面视频）、split（分卷）、rename（改后缀），可上下移动。
  cover/split/rename只接单文件；split后若继续，先archive把所有卷归档。后续7z/ZIP默认仅存储，可选压缩等级。
- **门面视频层**：选择或拖入普通MP4，归档嵌入ftyp后的free box，自动修正偏移（含stco→co64和ZIP64）。
  ZIP尾部free box同时补目录与EOCD，支持Python读取器；碎片化MP4先重封装。输出固定`.mp4`，前层需7z/ZIP载荷。
  无“修正ZIP偏移”复选框。改后缀使用rename层，旧固定伪装参数仍兼容迁移。
- **分卷层**：数字+MB/GB下拉，默认MB；无单位数字按MB，显式B按字节。`.001/.002…`命名，未超过阈值不分卷，兼容旧`.partNNN`合卷。
  阈值比较的是上一层产物大小，不是原文件或后续门面视频大小；后续archive层会将所有卷重新打包为一个文件。
  若要最终上传多个分卷，请把split放在最后一层。执行记录显示每个分卷层的实际输入大小、阈值和卷数（或未分卷原因）。
- **空间/耗时预检**：每次开始前显示中间空间GB、总读写GB和预计分钟（150MB/s粗估）；每层完成清理上层临时文件，
  峰值约2–3份资源，ZIP重定位含额外暂存，层数增加主要影响读写与耗时。目标盘不足自动换最大可用本地盘，全部不足则禁用开始。
- **只上传最终产物**：`.nde.json`、`.ndesplit.json`、RESTORE.txt只留本地；附带校验文件默认关，开启才额外上传标准`.sha256`。
  单独上传也排除这些本地元信息，开启校验则重新生成本批文件的校验文本。
- 右侧摘要列出“还缺：…”清单，缺项时按钮不可点。进入下一步或开始前检查密码：所有层都没填时提示
  “没有设置任何密码”（确认后按仅压缩继续）；模板要求加密的层有部分没填时提示“还有加密层没填密码”，
  可返回填写（自动定位到空的密码框）或继续（这些层只压缩）。同一设置确认过一次后不再重复询问。
- **任务中心**：按名称/备注/网盘搜索，“收藏”筛选；重命名与备注写入任务元信息；
  仅在选中任务详情保留“打开当前任务目录”，打开该任务的文件夹；一条龙的最终产物在其body子目录。
  删除 `runs/` 内任务会把目录移到系统回收站（运行中的任务拒绝删除），导入的外部任务只从列表移除、不动文件；
  “导入”可登记含 `relay-plan.json`、`nde-task.json` 或 `*.nde.json` 的文件夹（登记在 `rpa/state/ui-tasks.json`）；
  “复用设置”按任务记录的层/伪装/网盘等设置预填新任务（密码需重新填写）。上次中断原因以中文显示。

单独上传同样生成 v2 `relay-plan.json`，暂停/失败后在任务中心续跑；单独打包在输出目录写
`nde-task.json` 元信息。任务在后台线程执行，同一时间只允许一个；进度只显示真实阶段与文件数。
暂停上传会保留已确认文件的检查点；本地压缩只能在该阶段结束后响应暂停。任务运行中关闭窗口会先暂停，
检查点保存后自动关闭。密码和魔曰密钥只在内存中使用；界面偏好存入 `rpa/state/ui-settings.json`，不含密码。

- `nde.py gui --debug`（或环境变量 `NDE_DEBUG=1`）打开 WebView 开发者工具。
- `nde.py gui --legacy` 使用旧版 Tk 界面；未安装 pywebview 时也会自动回退到旧版。
- 视觉检查：`.venv\Scripts\python scripts\ui_preview.py [--dark]` 用模拟数据在无头 Edge 中截取各页面到 `tmp/ui`。

若从新环境安装：

```powershell
.venv\Scripts\python -m pip install -e ".[rpa,gui,dev]"
.venv\Scripts\python -m playwright install chromium
```

魔曰文案需要本机安装 Node.js 18+，使用随包附带的魔曰 V3.0.11（见 [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md)）；
Windows 上 Node 子进程以 `CREATE_NO_WINDOW` 启动，生成魔曰文案时不会闪出命令行窗口。

## 登录与状态

```powershell
.venv\Scripts\python nde.py account login quark
.venv\Scripts\python nde.py account login baidu
.venv\Scripts\python nde.py account login feimao
.venv\Scripts\python nde.py account login feimao --browser chrome
.venv\Scripts\python nde.py account status
```

首次在浏览器里登录。检测成功后保存本机状态，**登录窗口保留到你主动关闭**。
之后普通发布任务复用会话；确认已有有效会话后，可加 `--headless` 无头执行。
登录后跳转到平台已适配的另一个域名时，标签页会话按实际来源保存与恢复，避免带 `www` 的入口跳转后再次要求登录。
日常使用的个人浏览器登录状态不会导入软件的专用浏览器档案。
账号页也可选择 `chrome` / `msedge` 使用本机已安装的正式版 Chrome / Edge，
或 `chromium` 使用自带版本。启动成功后按网盘记住选择，后续发布沿用；
`publish --browser` 可以覆盖选择。有头模式的登录及发布等待不设认证超时；
无头模式在30秒内未确认登录时退出并保留检查点。
飞猫建议使用手机 APP 扫码；密码登录可能触发极验 60500（短时频繁验证限制）。
飞猫会话同时保存在软件专用的 `browser-data/` 和 `session-data/` 中，均位于忽略的
`rpa/state/` 下。浏览器渠道不同使用不同档案；切换渠道可能需要首次重新扫码。

- `probe`：实现/选择器待现场验证，不能当作支持承诺。
- `ready`：该驱动已成功完成上传及分享。
- `blocked`：需要处理登录、页面结构或平台错误。

桌面端账号页每个网盘只显示一个状态及其时间：

| 状态 | 含义 |
|---|---|
| 未登录 | 本机没有该盘的登录会话 |
| 已登录 · 未测试 | 已登录，但本机还没有用该盘完整跑通一次上传 + 分享 |
| 已通过测试 | 本机已用该盘自动完成过上传 + 分享（时间取状态文件与任务历史中较新的一次） |
| 登录失效 | 上次打开网盘时确认不到已登录，需要重新登录 |
| 检测失败 · 网络 | 上次检测时网盘页面打不开，登录未必失效，网络恢复后再检测 |

“检测登录”只打开网盘确认是否仍登录，不上传文件；仍登录时保持“已通过测试”。“已通过测试”也会从
`runs/` 与已导入任务的 `relay-plan.json` 恢复：该盘某阶段已自动分享、拿到链接且文件全部上传；
任务中心**手动回填**的链接（阶段带 `manual` 标记）不计入。暂无自动驱动的盘显示“仅手动回填”。
最近一次失败原因会转成中文（如 `ERR_TIMED_OUT` 显示为连接超时、请检查网络/代理）。
浏览器下拉默认推荐自带 Chromium，未安装的渠道不可选；已为某盘保存的 Chrome/Edge 选择不会自动重置。

部分账号在上传或分享前要求绑定手机号等前置操作，这属于账号自身条件。
有头模式会等待账号所有者完成前置操作并重试，无头模式则明确暂停；不会自动输入手机号或验证码。
状态与登录文件只保存在 `rpa/state/`。

## 多盘选择与统一分享设置

本体网盘可以同时勾选夸克、飞猫、百度、迅雷、UC、123；同一套最终文件/分卷逐盘上传（可选附带.sha256，清单和还原说明只留本地）。
有效期和提取码下拉框按已选本体盘及启用的第一跳取交集。取消网盘后会恢复更多选项；
已有选择不再适用时回到“平台默认”。“平台默认”沿用各盘自己的设置，选择具体值时才要求一致。
设置写入任务文件，打开任务时回显，续跑沿用保存值。

| 网盘 | 已探测的有效期 | 提取码 |
|---|---|---|
| 夸克 | 1、7、30天、永久 | 有/无 |
| 飞猫 | 长期有效（映射“永久”） | 私密/公开（映射有/无） |
| 百度 | 1、7、30、365天、永久 | 当前网页强制有（随机/自定义） |
| UC | 1、7、30、60、180天、永久 | 有/无 |
| 迅雷 | 1至7天、不限（映射“永久”） | 当前网页强制有 |
| 123 | 1、7、30天、永久 | 随机/无 |

只选 UC 时保留全部六种期限；UC＋迅雷只保留1天、7天、永久，并移除“无提取码”。
百度与其他盘一起选时，只保留所有盘共同支持的具体期限；百度没有“无提取码”，
因此任何含百度的组合都不会显示该选项，驱动也会拒绝。全部六盘一起选时具体期限仅剩永久，
提取码仅有“有”。提取码由平台生成后自动回填。
CLI 单选百度也可使用 `--share-expiry 365 --share-access code`；其他网盘或组合仍按各盘能力校验。
123 不启用付费提取、下载赞助或流量包。

上传后自动弹出的迅雷传输列表及123进度面板通过站点自己的关闭控件收起，再上传下一文件或分享。
百度接收方匿名可打开分享、输码查看目录，但下载要求登录百度账号，这是平台限制。

```powershell
.venv\Scripts\python nde.py publish MyRes -L zip --body-disks uc,xunlei,123pan --share-expiry 7 --share-access code -o runs/multi-release
```

原有 `--body-disk` 单盘参数继续可用。直接发布将所有本体链接编成同一段文案；
中转时 guide 包含全部本体链接，最终文案仍交付第一跳链接。
手动替换任意本体链接，会重新生成指引及第一跳。命令行续跑不接受覆盖任务内分享设置。

各盘实际验收范围见[支持情况](status.md)。首次运行软件需在它的专用浏览器窗口登录。

## 单命令直接发布

```powershell
.venv\Scripts\python nde.py publish MyRes -L 'lz4,zip,7z' '-P=-,innerPW,outerPW' `
  --disguise .mp4 -s 1900M --body-disk quark -o runs/my-release
```

可用 `--task-name "第八期资源" --folder-name "nde-release-08"` 分别指定任务标题和新建网盘目录名。
两项均可省略，续跑 `--plan` 不接受覆盖名称；自定义目录与已有目录重名会停止上传。

输出目录必须不存在；不会覆盖旧任务。命令行密码会进入 shell 历史，GUI 适合日常输入。
PowerShell 中密码链含逗号、且以 `-` 开头时，请像示例那样引用整个 `'-P=-,innerPW,outerPW'` 参数。
有密码的 7z 层自动启用文件名加密，lz4 等原本无密码的格式保持原有行为。
选择多个输入时，名称不得重复。输出目录不能放进要打包的源目录内。

需要真实视频外观：

```powershell
.venv\Scripts\python nde.py publish MyRes -L zip -P myPW --video intro.mp4 `
  -s 1900M --body-disk quark -o runs/video-release
# 门面视频自动嵌入开头并修正偏移；--raw旧参数兼容但不再改变发布行为。
```

`--disguise .mp4` 是改后缀，`--video intro.mp4` 才会把视频与归档合在一起。
`1900M`（1900MB）用于减少下载出错后的重传代价，并要求全部卷齐全才能解包，不代表网盘配额限制。
可加`--checksum`附带校验；无需分卷时`--size ""`。`-L`也接受JSON四类型层数组，参见README。

## 两段中转

```powershell
# 本体先传夸克，取得链接后回填 guide.txt，再把 guide.txt 上传第一跳。
.venv\Scripts\python nde.py publish MyRes -L 'lz4,7z' '-P=-,outerPW' `
  --form simple --body-disk quark --hop-disk feimao `
  --pwd-hint "解压密码见视频第30秒" -o runs/relay-simple

# 复杂中转：第一跳上传加密文件名的 guide.7z，内含填好链接的 guide.txt。
.venv\Scripts\python nde.py publish MyRes -L 7z -P outerPW `
  --form complex --hop-password hopPW --body-disk quark --hop-disk feimao `
  -o runs/relay-complex
```

本体和第一跳可选同一个已支持网盘，使用不同的任务目录。
飞猫作为本体盘的多文件目录模式只有编排/驱动测试，尚未做真实多文件分享验收。

飞猫目录分享不显示未单独分享的文件。驱动先逐个发布文件：单文件直接返回文件链接，
多文件再返回目录链接。`取件码` 是文件定位码，不等于访问密码；公开分享不填提取密码。
极验出现 `60500` 时，官方建议间隔 30 分钟再验证，不能把它当成账号被封或不停重试。
见[极验帮助中心](https://www.geetest.com/Helper)。

## 仅本地准备、续跑与手动回填

```powershell
.venv\Scripts\python nde.py publish MyRes -L 'lz4,7z' '-P=-,outerPW' --prepare -o runs/prepared
.venv\Scripts\python nde.py publish --plan runs/prepared/relay-plan.json
# 复杂版续跑仍须提供 --hop-password，密码不会写入计划。
```

每个文件上传后原子保存检查点；分享失败不会重传已完成的文件。续跑前重新计算
SHA-256，文件改变则拒绝复用旧任务。任务和账号都持有操作系统锁，进程崩溃后锁会释放。
程序 Ctrl+C 后可继续；如果在本地打包阶段就中断、还没生成任务文件，请另建输出目录。

站点改版或其他盘未适配时，手动上传当前阶段 `files` 中列出的全部文件到同一目录，
将分享弹窗文本保存为文件，然后回填：

```powershell
.venv\Scripts\python nde.py share-import --plan runs/prepared/relay-plan.json `
  --stage body --file share.txt
.venv\Scripts\python nde.py publish --plan runs/prepared/relay-plan.json
```

GUI 也提供“手动回填分享”。替换本体链接时，下游 guide 和第一跳上传会失效并重新生成，
使用新目录以免复用旧说明。程序不会撤销已经发出的旧分享，旧链接按平台设置的有效期处理。
原有 `nde relay` 的 version 1 占位模板继续保留；新的发布使用 version 2，拒绝自动上传
旧模板中的占位内容。

## 结果与还原

```
输出目录/
  relay-plan.json         逐文件进度及分享信息（不含归档密码和魔曰密钥）
  body/                  最终文件或 .001/.002 分卷（仅这些上传）
    *.sha256             可选，开启后才额外上传
    *.nde.json           本地v2完整层序（兼容v1），不上传
    *.ndesplit.json       本地逐卷校验清单，不上传
    RESTORE.txt          本地还原说明，不上传
  guide.txt / guide.7z    选用中转时才生成
  copy/
    beast.txt            兽曰文案
    mojibake.txt         魔曰文案
    hajimi.txt           哈基米文案
    share-plain.txt      便于核对的原始分享文本
```

接收方步骤详见[接收方指南](receiver-guide.md)。简要：先解开链接文案，取回全部最终文件/分卷；可从`.001`用7-Zip/WinRAR打开，或`nde join 第一卷.001`。
有清单时`nde unest 第一卷.001 -o restored -P="外到内密码链"`，密码对齐所有层，非归档层用`-`占位；
没有清单时`nde unwrap 第一卷.001 -o restored --chain-pwd="归档密码链"`，只对齐归档层，自动嗅探连剥。
本地清单v2记录全部层序，v1继续可还原，模板及旧任务设置自动迁移。GUI 的“链接编解码”可以离线完成三种方案互转；自定义魔曰密钥
在该页填写，同样用于发布文案。默认密钥与既有 CLI 一致。

这些运行产物含分享链接和你填写的密码提示，应只留本机；`runs/` 已排除版本控制。
诊断需显式运行 `account probe quark` 或发布时加 `--diagnostics`。

## 适配配置

`account probe <disk>` 保存本机截图、HTML 和当前配置。需要修正选择器时，将完整配置
放入 `rpa/state/profiles/<disk>.json`，无需修改加密核心。不要把账号快照提交到仓库。
默认目标和精确文件名定位不使用“全选已有资源”，只分享当前任务的专用目录。

## 内置7-Zip与离线兼容验证

内置官方7-Zip Extra 26.04 x64的独立`src/nde/vendor/7zip/7za.exe`，以无窗口子进程调用；
分发必须同时附带原始License.txt与来源README，二进制未修改。定位为内置7za（亦识别7z+DLL布局）→
已安装7-Zip→Python库回退。7za不支持RAR解码，原生RAR分卷/SFX不在当前范围。

离线验证：7z和ZIP均使用实际>4GB的仅存储归档嵌入指定视频，ffmpeg逐帧1606帧一致，
7za与WinRAR命令行解压后SHA-256一致；详见[支持情况](status.md)。可复跑`scripts/verify_large_cover.py`，
需要显式指定--work、--video、--ffmpeg和可选--winrar。脚本会创建大文件并保留现场，默认不自动清理。
网盘在线预览目前只在123手动复验，其他网盘及边下边播未验证；真实WebView2拖放、播放器双击和归档软件GUI打开需人工复核。
