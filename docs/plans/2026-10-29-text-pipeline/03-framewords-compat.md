---
phase: 3
plan: 1
wave: 3
status: deferred
depends_on: [01-text-chain, 02-text-key, behavioral-handoff]
files_modified: [src/misong/carriers/__init__.py, src/misong/carriers/base.py, src/misong/carriers/framewords_compat.py, src/misong/text_restore.py, tests/test_framewords_compat.py, scripts/verify_framewords_compat.py]
autonomous: true
must_haves:
  truths: [本地视频编解码离线完成, 官方与密送两个方向都可互读, 协议事实可追溯至允许的来源]
  artifacts: [src/misong/carriers/framewords_compat.py, tests/test_framewords_compat.py, scripts/verify_framewords_compat.py]
---

# 备用：帧语本地兼容（未排期）

本计划及两份净室提示词保留供未来用户明确启动自主兼容时使用，当前不执行，不是 v0.2 发布依赖。当前第三阶段为[帧语官网 RPA](03-framewords-rpa.md)。以下离线及双向互通标准只用于未来自主实现，不能用来描述当前 RPA 能力；开始时重新核对版本和已有公共接口，避免重写届时已完成的功能。

## 输入边界和开始条件

行为侧按 [行为提示词](prompts/behavior-agent.md)输出材料，实现侧按 [实现提示词](prompts/implementation-agent.md)执行。先读本目录 README.md 与 [交接约定](handoff/README.md)。不读取 RESEARCH.md、本轮聊天、tmp 中原实现、原脚本/WASM/客户端或源码改写。

本阶段不预填任何从原实现检查得到的格式参数。公开使用指南中的“加密＋嵌入＋纠错”只能说明大类原理；缺少字节格式、位置/同步、参数等证据时不能推出互通协议。交接材料尚未存在或关键字段仍 unknown 时，先完成 01/02，列出具体实验请求；不得默默自定协议冒充帧语。

## 任务 1：规范接收与载体契约

- **文件**：`src/misong/carriers/__init__.py`、`src/misong/carriers/base.py`、`src/misong/text_restore.py`。
- **动作**：检查交接 spec、vectors、provenance、open-questions、review 状态，核对每项协议事实来源和向量哈希。来源含原实现或关键字段未验证的内容不能作为规范；记录缺口并回交行为侧。已有官方标准可引用，但不能声称帧语采用某具体参数而没有证据。
- **动作**：定义 capabilities/encode/decode/verify 接口，类型、容量、进度、取消和错误分类清晰。逻辑载体 framewords 与自主实现 framewords_compat 分离；钥匙记录格式/兼容版本，而非实现路径。恢复时复用文字层逆向引擎，外层视频没有钥匙也可按手动密码读取。
- **验证**：`.venv\Scripts\python -m pytest -q tests/test_text_restore.py`，增加 fake carrier 用例覆盖能力缺失、读取/解锁错误、取消和“视频字节不同但载荷一致”。
- **完成**：规范覆盖的模式清晰且来源可复核；未知模式报告不支持，不切换成网页后端。

## 任务 2：自主本地编解码

- **文件**：`src/misong/carriers/framewords_compat.py`、`tests/test_framewords_compat.py`。
- **动作**：只从通过检查的规范与公开标准实现媒体信号提取/嵌入、封包、纠错与密码处理；使用授权兼容的成熟密码/媒体库，不重新发明密码原语。新依赖在实现前核对文档、许可证与离线可用性，按实际必要性选择，不预定算法栈。
- **动作**：先实现可验证的单一画面模式，再补其有密码路径；只有两者均通过才能宣称该模式完整支持。对不支持的分辨率/编码/格式版本明确失败。输出临时视频，成功本地回读且精确文字一致才交付；不改原视频。限制内存、文件体积和处理时长，可取消。
- **动作**：支持官方原始载荷（普通文字/兽曰/魔曰等），不强制在其前加密送私有头；`.tkey` 是独立层序辅助。不得把密送先前生成的自有格式作为“官方向量”。
- **验证**：`.venv\Scripts\python -m pytest -q tests/test_framewords_compat.py tests/test_text_restore.py`；官方生成的自制样本本地解码、独立留出的样本、随机化往返、错密码、坏帧、缺包、超限、取消与原输入保护。使用已存在于本机的依赖并断网测试，运行时不得访问官网/远端服务或调用官方助手。
- **完成**：独立官方样本逐字恢复；自主编码视频能回读，但在下一任务外部交叉验证完成前仍不标记帧语编码兼容。

## 任务 3：双向互通与离线验收

- **文件**：`scripts/verify_framewords_compat.py`、`tests/test_framewords_compat.py`。
- **动作**：生成本地验证批次及候选视频、期望文字摘要，由行为侧在正常官方产品读取，回传带样本 ID、版本、模式、实际文字摘要的结果。交换用自制媒体/虚构链接，不含真实资源、账号或密码。官网交叉检验可以由行为侧工具辅助操作，但不把该操作维护成产品 RPA 模块。
- **动作**：脚本验证证据与候选视频哈希相符，分别报告 official_to_misong、misong_to_official、offline_roundtrip、tkey_restore；不能只有一个总体 pass 掩盖单向失败。官方端有版本变化时重新记录，不承诺所有版本兼容。
- **验证**：`.venv\Scripts\python scripts/verify_framewords_compat.py --help`；实现后提供 `--handoff <目录> --work tmp/framewords-local-check`，检查独立向量及双向证据。密送断网完成本地生成、官方样本提取、密码解锁及 `.tkey` 全链路；标准 pytest 不访问官网。本地转码压力实验可追加，不能等同 B 站实际转码验收。
- **完成**：两个互通方向、离线运行及 `.tkey` 均有可复验结果；普通文本、兽曰/魔曰载荷、中文/emoji、有无密码覆盖对应承诺范围。未通过的模式单列，不交付“自有协议但叫帧语”的结果。
