---
phase: 1
plan: 1
wave: 1
depends_on: []
files_modified: [src/misong/text_layers.py, src/misong/text_pipeline.py, src/misong/sharing.py, tests/test_text_pipeline.py]
autonomous: true
must_haves:
  truths: [文字链可按指定顺序正逆向处理, 旧多选迁移仍为并列方案]
  artifacts: [src/misong/text_layers.py, src/misong/text_pipeline.py, tests/test_text_pipeline.py]
---

# 01 文字处理链

## 上下文

先读本目录 README.md、仓库 AGENTS.md、docs/dev/development.md、docs/status.md，再读 src/misong/sharing.py 与 encoders 下的现有接口。沿用原编码实现和魔曰版本，不改 vendor。

## 任务 1：模型、迁移与限制

- **文件**：`src/misong/text_layers.py`、`tests/test_text_pipeline.py`。
- **动作**：定义多个交付方案，每份含稳定 ID、名称、有序文字层、一个末端载体及显式钥匙导出选项。文字层使用现有 scheme 参数；密钥仅存在运行时上下文，公共序列化只保留需要密钥的标志。末端默认纯文本。旧 schemes 的每项迁移为独立单层方案，旧空选保持其入口已有语义。原始链接方案允许零文字层。
- **限制**：初始最多 32 个文字层、16 个方案，输入及中间 UTF-8 文本上限 1 MiB；载体可以施加更低限制。算法必须在注册白名单内，拒绝不可逆 trunc、未知版本、循环引用和视频后接文本层。允许多个魔曰层使用各自独立密钥槽。
- **验证**：`.venv\Scripts\python -m pytest -q tests/test_text_pipeline.py`。
- **完成**：旧的 beast/mojibake 多选映射为两份方案，零层与非法层组合均有覆盖，公共数据里无任何密钥值。

## 任务 2：顺序执行、逆序还原及容量预检

- **文件**：`src/misong/text_pipeline.py`、`src/misong/sharing.py`、`tests/test_text_pipeline.py`。
- **动作**：复用现有 encode/decode 实现；保留旧 encode_copy/write_copy 调用兼容层。每层返回字符数、UTF-8 字节数及摘要，展示预检统计时不泄露密钥或原文。解码严格逆序，完整成功后才返回结果；默认不猜测算法，不 trim 或归一化文字。输出载体所需的最后一级文字，载体具体操作留给计划 03。
- **验证**：上述 pytest；合成 ASCII 链接、中文、emoji、空白/换行、兽曰→魔曰与魔曰→Base64 往返逐字一致；错误密码、超限、取消不返回部分结果。随机化编码的正向结果只生成一次并在同次运行复用，不能用重新编码产生的不同结果做容量/摘要对照。
- **完成**：纯文字路径可独立运行，旧接口结果含义不变；新模型能表达多个并行输出，每份内部串行处理。
