---
phase: 2
plan: 1
wave: 2
depends_on: [01-text-chain]
files_modified: [src/misong/text_key.py, src/misong/text_restore.py, src/misong/cli.py, .gitignore, AGENTS.md, tests/test_text_key.py, tests/test_text_restore.py]
autonomous: true
must_haves:
  truths: [显式导出才保存文案密钥, 钥匙加文案可还原原文, 现有 mskey 兼容不变]
  artifacts: [src/misong/text_key.py, src/misong/text_restore.py]
---

# 02 文案钥匙与还原

## 上下文

本目录 README.md，src/misong/restore_key.py、restore.py、cli.py，以及现有 test_restore_key.py/test_restore.py。沿用已审查的封装结构和校验原则，首版不为代码去重而改变 `.mskey` 格式。

## 任务 1：`.tkey` 格式与敏感文件约定

- **文件**：`src/misong/text_key.py`、`tests/test_text_key.py`、`.gitignore`、`AGENTS.md`。
- **动作**：定义独立 magic/type/version；载荷含方案、由内到外的解码配方、兼容版本、层密钥槽、文字摘要及可选产物指纹。复用 AESGCM 封装思路；随机包装钥匙同行，明确持有者可解析。严格限制 4 MiB 总文件大小、32 层、字段类型与解码算法白名单；不保存原文、中间文本、本机视频路径、账号或远端会话。
- **动作**：写入拒绝覆盖，失败不留下可用半文件；提供 write/read API。仅显式 export_text_key 才写入，默认关闭，不记为全局偏好。添加 `*.tkey` 忽略和 AGENTS 中对应的显式导出例外，沿用钥匙敏感交付及清理保留规则。
- **验证**：`.venv\Scripts\python -m pytest -q tests/test_text_key.py tests/test_restore_key.py`；验证完整往返、错误类型、损坏/截断、恶意或超限结构、不会误认 `.mskey`、普通序列化不含密钥。验证旧 `.mskey` 样本保持可读。
- **完成**：一种明确有版本的 bearer 钥匙格式；未勾选导出时零钥匙文件，测试不保存真实密码或分享。

## 任务 2：还原入口与摘要绑定

- **文件**：`src/misong/text_restore.py`、`src/misong/cli.py`、`tests/test_text_restore.py`。
- **动作**：增加独立 `text-restore` CLI，接收文字文件和 `.tkey`，复用计划 01 逆向引擎；无钥匙时接受用户明确指定的配方并以交互输入密钥。输出为 UTF-8 文本，拒绝覆盖非空目标。钥匙配方只选择白名单算法，不执行命令，不自动打开解码后的 URL。
- **动作**：文字摘要逐层验证，原文最后验证；预留外层视频载体读取入口，并允许载体已被官方工具解开后从匹配的文字摘要继续，避免让 `.tkey` 依赖网站。视频指纹不匹配不能单独否定转码样本，后续必须成功提取并核对载荷。导入钥匙、检查错误和日志不能回显其内容。
- **验证**：`.venv\Scripts\python -m pytest -q tests/test_text_restore.py tests/test_text_pipeline.py tests/test_restore.py`；`.venv\Scripts\python misong.py text-restore --help`；覆盖多魔曰密钥、未知载体、错配文案、错误密码、中途失败和已有目标保护。
- **完成**：原始文本只在全部验证通过后交付；错误配方不自动尝试不受控层，现有文件还原命令行为不变。
