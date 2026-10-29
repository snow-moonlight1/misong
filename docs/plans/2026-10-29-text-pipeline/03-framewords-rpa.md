---
phase: 3
plan: 1
wave: 3
status: planned
depends_on: [01-text-chain, 02-text-key]
files_modified: [src/misong/carriers/__init__.py, src/misong/carriers/base.py, src/misong/carriers/framewords_web.py, src/misong/text_restore.py, tests/test_framewords_web.py, tests/test_text_restore.py, scripts/verify_framewords_web.py]
autonomous: true
must_haves:
  truths: [官网自动写入读取及解锁形成闭环, 保存后独立读取并逐字核对, 视频失败不重做网盘分享]
  artifacts: [src/misong/carriers/framewords_web.py, tests/test_framewords_web.py, scripts/verify_framewords_web.py]
---

# 03 帧语官网 RPA

当前第三阶段。先读本目录 README.md、01/02 及仓库开发指南，复用现有 Playwright 基础设施。先完成最小的真实网页生成与独立回读实验，再扩展功能。首版限定本地视频、一个实测通过的标准画面模式及有无密码；不做 B 站取流、投稿、音频/混合或自定义区域。

RPA 自动操作正常网页，不需要研究帧语协议，也不把官网自有脚本/组件复制进密送发行包。网站加载并在浏览器运行自身程序属于使用方式，不能表述为密送离线编解码。独立兼容已移至[未排期的备用计划](03-framewords-compat.md)，不是本阶段前置条件。

## 任务 1：载体接口与还原接线

- **文件**：`src/misong/carriers/__init__.py`、`src/misong/carriers/base.py`、`src/misong/text_restore.py`、`tests/test_text_restore.py`。
- **动作**：定义最小 capabilities/encode/decode/verify 接口，覆盖容量、进度、取消与错误分类。逻辑格式 framewords 与执行后端 framewords_web 分离；`.tkey` 记录载体格式、已验证兼容范围及解码参数，不写选择器、网页步骤或实现路径。未来 framewords_compat 可复用同一文字链与钥匙入口。
- **动作**：视频＋`.tkey` 自动提取并解锁外层，再在本机逆序还原文字层；只向页面提供本次视频密码，不传整个钥匙或内层密钥。无钥匙也能读取无密码视频或交互输入密码。不能自动打开恢复的链接。
- **验证**：`.venv\Scripts\python -m pytest -q tests/test_text_restore.py`；fake carrier 覆盖正确/错误密码、能力不支持、网络故障、取消、提取文本错配及视频字节变化但载荷相同。
- **完成**：文字层可独立离线运行；视频步骤明确需要官网。错误不会交付部分还原结果，也不会触发网盘重传。

## 任务 2：正常网页写入、读取及独立回读

- **文件**：`src/misong/carriers/framewords_web.py`、`tests/test_framewords_web.py`。
- **动作**：集中管理官网地址、语义选择器、超时及已验证模式。正常选择文件、填写文字和可选密码、生成并接收下载；另开读取页面导入保存的视频，逐字比较恢复的 UTF-8 文字，不复用生成页显示的输入作为回读证据。提供独立 decode 路径，支持接收方自己的本地视频及密码输入，不依赖编码时的浏览器会话。
- **动作**：生成前检查文字膨胀和页面实际容量，不截断、不隐式 trim 或归一化。捕获实际下载完成并保护原输入；失败不把未验证输出标成可交付。支持取消、限时等待、组件下载失败、页面变化和官网不可用，错误可重试且保留已完成分享。
- **动作**：使用隔离的临时浏览器上下文，默认禁用包含文案、密码、会话的 trace、截图、HTML 和响应正文留存；不能沿用网盘驱动的敏感现场采集。仅保留脱敏错误分类和阶段。正常运行官网组件，不直接调用未公开的内部服务、不绕过验证码或风控；遇到人工验证交由用户。传给文件选择器不等于上传到服务器，实际处理路径在真实实验中核查，不作未经验证的隐私保证。
- **验证**：`.venv\Scripts\python -m pytest -q tests/test_framewords_web.py tests/test_text_restore.py`；自制最小模拟页面覆盖下载、页面变化、错密码、超时、取消、容量不足及敏感信息不落日志。不保存官网 HTML/脚本作为测试夹具；日常测试禁止访问官网和真实网盘。
- **完成**：自动生成、独立读回与独立导入读取均有测试，成功判定依赖实际载荷一致；“按钮已点击”或“页面显示完成”不算通过。

## 任务 3：显式真实网站验收

- **文件**：`scripts/verify_framewords_web.py`、`tests/test_framewords_web.py`。
- **动作**：提供必须显式启用的 `--live --work tmp/framewords-smoke` 验收入口，默认不访问官网。使用自制短视频、虚构链接和测试专用密码，覆盖裸链接、兽曰/魔曰载荷、中文/emoji、有无密码；生成后关闭生成上下文，再从保存文件读取、核对全文，并用对应 `.tkey` 完成内层还原。
- **动作**：记录日期、浏览器/网页显示版本、模式、样本 ID、载荷摘要及各阶段通过/失败；只保存脱敏元数据，视频与现场材料留在忽略目录。检查运行时网络请求的目的地/类型是否符合页面声明，不记录敏感正文；若发现文件或文字向远端发送，明确记录并在产品交互中如实说明。组件首次加载和官网不可用分别报告，不把缓存命中等同离线保证。
- **验证**：`.venv\Scripts\python scripts/verify_framewords_web.py --help`；显式运行真实批次，分列 encode、saved_file_readback、independent_decode、tkey_restore。独立读取应包含只拿到视频和钥匙的新上下文；模拟网络中断后证明只重试第四步。标准 pytest 仍不联网。
- **完成**：目标模式的真实生成、保存文件回读、接收方还原均有证据。官网不可用或个别模式失败时标明未验收，不以模拟测试替代；平台转码另行验证，不承诺任意视频或所有版本可用。
