# netdiskencrypt（nde）

面向个人的**私密备份与加密分发**工具箱（Windows）：把自己的文件打包成多层加密归档，
按需分卷或嵌入门面视频，自动上传到网盘并创建分享，再把分享链接转换成兽曰/魔曰/哈基米等文本。

> **使用须知**：仅用于你有权处理的资源。请遵守所在地法律和各网盘的用户协议。
> 网盘自动化依赖网页结构，可能随时失效，也可能不符合部分平台的条款，风险由使用者自行承担。
> 本项目不提供、也不接受验证码破解、风控绕过或私有接口签名等功能。

## 功能

- **多层嵌套打包**：7z（AES-256，可加密文件名）、ZIP（AES）、lz4 / zstd / brotli / xz / bz2 / tar 等，任意顺序叠加。
- **门面视频**：把 7z/ZIP 嵌入普通 MP4 开头，视频照常播放，归档软件可直接解出；支持 >4GB（co64 / ZIP64）。
- **分卷**：`.001/.002` 字节分卷并附校验清单，可选标准 `.sha256`。
- **网盘发布**：夸克、飞猫、百度、UC、迅雷、123 网页自动上传与分享；多盘同时发布，统一有效期与提取码；
  逐文件检查点、断点续跑，站点改版时可手动回填分享。
- **两段中转**：第一跳放指引（明文 guide.txt 或加密 guide.7z），指向本体分享。
- **链接文案**：兽曰（3 种方言）、魔曰（文言 / 传统）、哈基米、base64 / base32 / base85 / hex / url / rot13 等，可串联，离线编解码。
- **桌面应用**：4 步一条龙发布向导、层编辑器与模板、任务中心、网盘账号管理；同时提供完整 CLI。

## 环境要求

- Windows 10/11 x64；桌面应用需要 Microsoft Edge WebView2 Runtime（Windows 11 自带）。
- Python 3.11+。
- Node.js 18+（仅生成或解码魔曰文案时需要）。
- 网盘自动上传需要 Playwright 浏览器（见下方安装步骤）。
- 已内置官方 7-Zip `7za.exe`，无需另装。

## 安装

```powershell
git clone <仓库地址> netdiskencrypt
cd netdiskencrypt
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[gui,rpa]"
.venv\Scripts\python -m playwright install chromium
```

## 快速开始

**桌面应用**：双击 `start-gui.cmd`，或运行 `.venv\Scripts\python nde.py gui`。
首次使用先到“网盘账号”页登录（软件会打开专用浏览器窗口，扫码、密码、短信等由你自己完成），
登录状态只保存在本机被 Git 忽略的 `rpa/state/`。

**命令行**：

```powershell
# 登录网盘（窗口保持打开，关闭即可）；可加 --browser chrome / msedge 使用本机浏览器
.venv\Scripts\python nde.py account login quark

# 一条命令：打包 → 分卷 → 上传 → 分享 → 生成兽曰/魔曰/哈基米文案
.venv\Scripts\python nde.py publish MyRes -L 'lz4,7z' '-P=-,myPW' -o runs/my-release

# 多盘发布，统一 7 天有效期并带提取码
.venv\Scripts\python nde.py publish MyRes -L zip --body-disks uc,xunlei,123pan --share-expiry 7 --share-access code -o runs/multi

# 只在本地打包：lz4 → zip(密码) → 7z(密码+文件名加密)，外层改后缀为 .mp4
.venv\Scripts\python nde.py nest MyRes -L lz4,zip,7z '-P=-,pw1,outerPW' --disguise .mp4

# 用 JSON 描述任意层：zip → 门面视频 → 150MB 分卷
$layers = '[{"type":"archive","fmt":"zip"},{"type":"cover","video":"C:/media/intro.mp4"},{"type":"split","size":"150MB"}]'
.venv\Scripts\python nde.py nest MyRes -L $layers -o runs/cover.mp4

# 链接文案编解码（可逗号串联）
.venv\Scripts\python nde.py code encode -S beast -T "https://example.com/s/abc 提取码:1234"
.venv\Scripts\python nde.py code encode -S mojibake --key 我的魔咒 -T "同上"
.venv\Scripts\python nde.py code decode -S beast,hajimi -F cipher.txt
```

密码链以 `-` 开头时，PowerShell 中请整体加引号写成 `'-P=-,pw1,pw2'`（`-` 表示该层无密码）。
完整用法见[使用指南](docs/user-guide.md)。

## 命令一览

| 命令 | 说明 |
|------|------|
| `gui` | 桌面应用（`--legacy` 为旧版 Tk 界面） |
| `publish` | 打包、分卷、上传、分享、中转回填、生成文案；`--plan` 断点续跑 |
| `account` | 网盘登录、状态、诊断探测 |
| `share-import` | 手动上传后回填分享文本；换链时重建下游指引 |
| `nest` / `unest` | 多层打包 / 按清单还原 |
| `unwrap` | 无清单时按文件特征逐层剥离（`--chain-pwd` 提供各归档层密码） |
| `split` / `join` | 字节分卷 / 校验并合卷 |
| `merge` | 旧版尾部拼接（保留兼容） |
| `code` | 链接文本编解码：beast · mojibake · hajimi · base64 等 |
| `relay` | 生成中转指引模板 |
| `formats` | 列出支持的层格式 |

## 接收方如何还原

解开链接文案 → 打开分享并下载**全部**文件/分卷 → 用 7-Zip / WinRAR 打开 `.001` 或单个文件并输入密码；
含冷门格式层或多层嵌套时，用 `nde unwrap 第一卷.001 -o restored --chain-pwd="外层密码,内层密码"` 一次剥离。
详见[接收方指南](docs/receiver-guide.md)。

## 文档

- [使用指南](docs/user-guide.md)：桌面应用、发布、中转、续跑与回填
- [接收方指南](docs/receiver-guide.md)：解码文案、下载与还原
- [支持情况与验证状态](docs/status.md)：各网盘验收范围、已知限制、待验证项
- [路线图](docs/roadmap.md)：后续版本规划
- [开发指南](docs/dev/development.md)：环境、结构、测试、驱动约定
- 调研资料：[网盘 RPA 现场机制](docs/dev/rpa-research.md)、[加密/中转套路调研](docs/dev/tactics.md)
- [更新记录](CHANGELOG.md) · [参与贡献](CONTRIBUTING.md) · [安全策略](SECURITY.md)

## 隐私

归档密码和魔曰密钥只在内存中使用，不写入任务文件或界面设置。账号会话、任务记录和分享文案只保存在本机，
默认被 Git 忽略。软件只访问你选择的网盘网站，不包含遥测。

## 许可证

本项目以 [GPL-3.0-or-later](LICENSE) 发布。内置的第三方组件及其许可证见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

**关于魔曰**：内置 [Abracadabra](https://github.com/SheepChef/Abracadabra) **V3.0.11**，这是该项目以 GPL-3.0
发布的最后一个版本。上游自 V3.1.0 起改用 AIPL 许可证（含限制条款，与 GPL 不兼容），因此本项目固定使用 V3.0.11。
本工具生成的魔曰文案可被新版魔曰（包括官方网页）解密；新版文言模式生成的部分新句式本工具无法解密，
此时会提示改用官方网页。

本项目与各网盘服务商以及魔曰、兽音译者、哈基米翻译器的作者均无关联。
