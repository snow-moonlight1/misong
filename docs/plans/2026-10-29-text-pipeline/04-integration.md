---
phase: 4
plan: 1
wave: 4
depends_on: [01-text-chain, 02-text-key, 03-framewords-rpa]
files_modified: [src/misong/publish.py, src/misong/workflows.py, src/misong/cleanup.py, src/misong/desktop/api.py, src/misong/cli.py, src/misong/desktop/web/app.js, src/misong/desktop/web/index.html, src/misong/desktop/web/app.css, tests/test_text_publish.py, tests/test_text_api.py, tests/test_text_ui.py, scripts/ui_preview.py]
autonomous: true
must_haves:
  truths: [文案失败只重试第四步, 用户可以编辑多个有序方案并导出钥匙]
  artifacts: [tests/test_text_publish.py, tests/test_text_api.py, tests/test_text_ui.py]
---

# 04 发布与桌面接线

## 任务 1：发布、状态与恢复

- **文件**：`src/misong/publish.py`、`src/misong/workflows.py`、`src/misong/cleanup.py`、`tests/test_text_publish.py`。
- **动作**：第三步完成后的最终分享文案作为所有交付方案的共同输入。增加分享完成与第四步各方案 pending/running/complete/blocked/cancelled 状态；兼容旧 complete 记录。已有逐文件上传和分享检查点继续有效，第四步失败只重跑失败方案。
- **动作**：密钥不进入检查点。进程内尽量复用已计算的随机化编码结果；进程重开若中间结果未保存，要求重新输入必要密钥并从该方案起点重算，作废旧的未完成派生产物和摘要，不混合两个运行的链。新 `.tkey` 必须与最终成功产物同次生成。
- **动作**：清理仍只处理已登记的生成文件，并显式保留 `.mskey`、`.tkey`、源载体与本次最终交付视频。第四步全部成功及钥匙已安全保存后才允许相关任务自动清理；不得把最终视频列入可删的中间文件。钥匙首版仅显式本地导出，不重开云端分享以塞入钥匙。
- **验证**：`.venv\Scripts\python -m pytest -q tests/test_text_publish.py tests/test_publish.py tests/test_cleanup.py`；假驱动断言第四步失败重试时 upload/share 调用次数不增加，两份方案之一成功后不重复生成它。
- **完成**：显示与状态可区分“网盘已分享”和“全部交付完成”，恢复不遗失已有分享，不将密码写入任务。

## 任务 2：API、CLI 与旧调用兼容

- **文件**：`src/misong/desktop/api.py`、`src/misong/cli.py`、`tests/test_text_api.py`。
- **动作**：提供文案方案预检/执行、钥匙导出与还原、载体能力查询。旧 schemes 参数保持兼容；新旧参数同时出现时明确拒绝歧义。新模板只保存公开配方，不含密码、钥匙文件内容或自动导出选中状态；旧模板按并列方案迁移。
- **动作**：命令行密钥优先交互输入，不能新增把 `.tkey` 内容或密码输出到计划预览的行为。普通设置/任务摘要仅显示有无钥匙及路径，不显示内容。保留旧 encode/decode API 的结果形状。
- **验证**：`.venv\Scripts\python -m pytest -q tests/test_text_api.py tests/test_desktop_api.py tests/test_text_restore.py`；既有 CLI 帮助与新增命令帮助能正常运行。
- **完成**：老调用可用，新调用能表达零文字层、多个独立方案和每层独立密钥。

## 任务 3：第四步与文案还原界面

- **文件**：`src/misong/desktop/web/app.js`、`src/misong/desktop/web/index.html`、`src/misong/desktop/web/app.css`、`scripts/ui_preview.py`、`tests/test_text_ui.py`。
- **动作**：复用第二步交互风格提供方案增删、层排序、参数、逐层字符数与末端载体；支持裸链接方案、纯文本和帧语官网视频输出。使用“编码/加密/载体”的准确文案，不能把 Base64 描述为密码保护。仅开放实际验证过的网页模式，清楚标识需联网和官网依赖。
- **动作**：钥匙为明确选择导出、默认关闭；结果区分别展示文本/视频、独立回读验证状态和钥匙位置。文案还原支持文字或本地视频加 `.tkey`，密送自动操作官网提取并解锁外层视频，在本机解开内层文字；不要求用户先手动去官网，也不承诺离线视频解码。保留手动配方和粘贴已提取文字的入口，不改变原文件还原语义。
- **动作**：B 站链接暂不实现取流或自动读取，给出用户主动打开的官网入口；不在 URL 自动携带链接/密码。网站故障时保留已有文案/分享，当前方案显示可重试，不重新上传网盘。
- **验证**：`.venv\Scripts\python -m pytest -q tests/test_text_ui.py tests/test_restore_ui.py`；`.venv\Scripts\python scripts/ui_preview.py` 和追加 `--dark` 的预览，目视第四步、结果、文案还原与窄窗口；无 console 错误、遮挡或密码值快照。
- **完成**：用户可以配置魔曰→视频和另一份纯文本方案，看到容量限制，并在密送内联网使用对应钥匙还原视频；取消操作保留已完成分享。纯文字离线、视频官网依赖与 B 站手动入口清楚区分。
