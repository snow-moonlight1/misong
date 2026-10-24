# 网盘资源加密/中转套路调研（2026-10）

下文是技术调研，未实现候选不代表后续承诺。实现状态见[支持情况](../status.md)，
用法见[使用指南](../user-guide.md)，现场机制见[RPA/验证码调研](rpa-research.md)。

> 用途限定：自己的资源做私密备份与可控分发。本文档只整理公开社区已知的
> 技术模式，不针对任何具体内容；各平台规则不同，风险自担。

## 一、文件层套路（本项目已实现大部分）

### 1. 多层嵌套加密压缩包
逐层压缩+密码，接收方"解压两次/多次"。要点（来源：B站国强极客教程、什么值得买工具帖、微博教程）：
- **7z + AES-256 + 加密文件名(头加密)**：没有密码时无法直接读取归档目录；不保证平台不会识别或限制归档。
- **ZIP 不支持加密文件名**，只当内层用。
- **分卷归档**：接收方需要完整分卷；平台是否能识别、扫描或在线解压取决于具体实现。
- **自解压 EXE**：同样不被在线解压，但很多盘限制上传 exe（我们未实现，
  当前可选择7z头加密和字节分卷，但两者不等于自解压EXE）。
- 嵌套顺序常见为：`原始 -> tar/lz4(冷门层) -> zip(密码) -> 7z(密码+头加密)`。
  ✅ `misong nest MyRes -L lz4,zip,7z '-P=-,pw1,pw2'`

### 2. 冷门格式层（lz4 等）
冷门压缩层和后缀伪装是不同步骤：真实lz4/zstd数据必须按其格式解压，改名不会转换格式，
lz4等压缩算法本身也不提供密码加密。支持的格式家族有lz4、zstd、brotli、lzma/xz、bz2、tar.*、7z、zip。
✅ 全部支持，且 raw 格式吃目录时自动垫 uncompressed tar 层（还原了社区
"tar 再 lz4"的手感）。冷门压缩 CLI（lrzip、zpaq、esd、wim、alz/ice 等韩国
格式）暂未接入。

### 3. 一键分卷
- 7z/RAR 原生分卷（`.001/.part1.rar`）——接收方需全齐。
- ✅ 我们的字节分卷 `.partNNN` + sha256 清单：任何格式产物都能切，`misong join`
  自动验卷（缺卷/坏卷直接报"请重新下载第 N 卷"，解决社区高频痛点）。
- `misong split`默认4000M，`misong publish`默认1900M；均为分卷配置，不代表已确认的账号单文件上限。

### 4. 格式合并 / 后缀互换（"视频里藏包"）
调研确认社区实际有三种形态，本项目三种全覆盖：
- **A. copy /b 纯拼接**（图种同款原理：文件头识别机制）：`视频+压缩包` 拼成
  一个文件，播放器从头读、压缩软件扫尾找 EOCD。改后缀即可解。
  ✅ `misong merge a.mp4 b.zip -o cover.mp4 --raw`
- **B. 拼接+zip 偏移修正**（我们额外做的正确性升级）：把 zip 的所有绝对偏移
  +len(前段)，产物是 **标准合法 zip（SFX 同款布局）**，实测连严格的 Python
  zipfile 都能直接打开；A 形态则依赖 WinRAR 式宽容扫描。
  ✅ 默认开启（`--raw` 关闭）
- **C. 纯改后缀伪装**：7z/zip 本体改名叫 `.mp4/.png/.lz4`。播放器读 0 偏移
  失败，归档工具从尾部 EOCD 入手。资源站"mp4 改 zip 用 WinRAR 解压"、
  隐写者工具（MKV 需 WinRAR 修复、7z 用 `#` 号模式、`7z x -t# file -i!*.zip`）
  全属这一类。✅ `misong nest --disguise .mp4`，还原用 `misong unwrap/unest`
- 注意：视频需 `-movflags +faststart`（moov 在头部）才经得起尾部追加，
  demo 实测合并体 ffprobe 正常解析。

### 5. 网盘中转（两段式导流）
- **简易版**：第一跳（飞猫盘等）只放 guide.txt → txt 内是第二跳链接+提取码，
  密码则藏在视频/帖子里。✅ `misong relay --form simple` 生成 guide.txt 模板+
  relay-plan.json（旧版静态占位模板）。自动回填、上传和文案使用`misong publish --form simple`。
- **复杂版**：第一跳直接放**带密码压缩包**，包内才是 guide.txt，再导流第二跳
  下载本体。✅ `misong relay --form complex`；配合 nest 产物即开即用。
- 文件层与链接层解耦；换本体链接时，发布编排会重建指引及第一跳，然后重出文案。

## 二、链接/文本层套路（本项目实现 4 族 + 备忘若干）

| 方案 | 形态 | 离线 | 密钥 | 本项目 |
|------|------|------|------|--------|
| 兽音译者(兽曰) | 嗷呜啊~ 拟声 | ✅ | 4字符集 | ✅ 3 方言(sdk/web/pojie)+自定义字符集，与官方 SDK 向量互验 |
| 魔曰 Abracadabra | 文言文/汉字映射 | ✅ | 魔咒(AES) | ✅ 内置魔曰 V3.0.11 原版 JS（GPL-3.0），wenyan+old 双模式 |
| 哈基米语 | 哈基米南北绿豆 | ✅ | 权重表 | ✅ 纯 Py 重写，与原版 JS 双向互通实测 |
| base64/hex/url 等 | 编码 | ✅ | 无 | ✅ 另加 base32/85、reverse、rot13 |
| 截断法 | 链接掐头去尾+掩码 | ✅ | 平台先验 | ✅ `trunc`（半自动：中段需接收方补） |
| 熊曰/与熊论道 | 呋食性類… | ❌服务端 | 无 | 未接入（魔曰 V3.0.11 不含熊曰解码） |
| 佛曰/新佛曰 | 諸南隸僧… | ❌服务端 | 追加式 | 未做（同源 unishox 路线，魔曰已覆盖需求） |
| 火星文 | 囙uos→ | ✅ | 表 | 未做（Abracadabra 声称不支持英文，价值低） |
| 零宽字符水印/隐文 | 不可见字符 | ✅ | 无 | 可扩充：`--scheme zero` |
| EXIF/图片元数据藏链接 | 图片描述字段 | ✅ | 无 | 未实现；候选工具exiftool，暂无misong meta命令 |
| 文件名即密码/文件名哈希 | 首N位=密码 | ✅ | 约定 | 属分享约定，写进 guide.txt 模板即可 |
| 密码变形 | 密码的 反转/base64/兽曰 | ✅ | 同方案 | ✅ 对密码串直接跑 `misong code` 即可 |

## 三、其他社区做法（记录备查）

- 文件名加空格/符号、拼音缩写规避关键词扫描（低成本，已被 MD5 库比对击穿）。
- 改后缀不会改变文件字节和哈希；重新打包或加密会改变字节，但不能据此保证绕过平台识别。
- 多层目录套娃后再压（增大在线解压遍历成本）✅ nest 支持任意深目录。
- PDF 加密当容器（少见，转换损耗大，未实现）。
- 每卷分散到不同盘：尚未实现；当前多盘发布会将同一套完整产物分别上传到每个盘。
- 部分损坏伪装、"假种子"诱饵文件（攻防成本高，收益低，未实现）。

## 四、参考来源

- 兽音译者算法与官方多语言实现：https://github.com/SycAlright/beast_sdk
- 魔曰 Abracadabra（V3.0.11 及以前为 GPL-3.0；V3.1.0 起改为 AIPL）：https://github.com/SheepChef/Abracadabra 在线版 https://abra.halu.ca
- 哈基米语翻译器（开源 TS 实现）：https://github.com/Starpuccino/hachimi-wonameruto-translator
- 兽音离线版原理帖（52pojie）：https://www.52pojie.cn/thread-2074343-1-1.html
- 兽音原理拆解：https://m.php.cn/faq/1921757.html 、CSDN 实现笔记 https://blog.csdn.net/2301_80688586/article/details/148570058
- 在线兽音（方言差异实证，不同站点互不兼容）：https://roar.iiilab.com/ 、https://www.wangdu.site/roar 、https://toolshu.com/beast-translator
- MP4/MKV 隐写工具说明（改后缀+WinRAR/7z #号模式）：https://www.bilibili.com/read/cv42186666
- 图种 copy /b 原理：https://bbs.huaweicloud.com/blogs/476558
- galgame 资源站"mp4改zip解压"惯例：https://galgamewebsite.com/jc
- 7z 四层打包做法（密码/头加密/分卷/自解压）：https://www.bilibili.com/video/av875812349 、https://tagqwl.com/10170.html
- 网盘分享杂项（改名/加密/文本加密/图片加密）：https://wk.baidu.com/view/b1d731cc142ded630b1c59eef8c75fbfc77d9469
- 截断法与分享安全分级：https://www.bilibili.com/opus/1050937647920316425
- 同类打包工具介绍：https://post.m.smzdm.com/p/arz3d6pq/
- 微博老教程（7z 重复压缩两层）：https://m.weibo.cn/status/4615031897981774

