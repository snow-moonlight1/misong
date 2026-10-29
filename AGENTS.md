# AGENTS.md

面向在本仓库工作的编码代理和贡献者。开始前先读 [开发指南](docs/dev/development.md) 与 [支持情况](docs/status.md)。

## 运行

- 安装：`.venv\Scripts\python -m pip install -e ".[dev,gui,rpa]"`，再 `.venv\Scripts\python -m playwright install chromium`。
- 回归：`.venv\Scripts\python -m pytest -q`（不访问真实网盘）。
- GUI：`start-gui.cmd` 或 `.venv\Scripts\python misong.py gui`；CLI：`.venv\Scripts\python misong.py --help`。
- 改界面后运行 `scripts/ui_preview.py`（可加 `--dark`）截图自查。

## 约定

- 复用 `layers` / `pack` / `split` / `merge` / `encoders`；不要重写已有加密与打包逻辑。
- `src/misong/vendor/` 下的第三方文件不得修改；魔曰不得升级到 V3.1.0 及以后（AIPL）。
- 驱动只以文件列表中的精确文件行确认上传；首卷成功、传输队列文字或单纯登录都不算整批成功。
- 登录、验证码、手机号绑定等由账号所有者完成；不实现验证码破解、风控绕过或私有接口签名。
- 密码和魔曰密钥只在内存中使用，不得写入任务文件、设置或日志。
- 用户明确选择导出时，可将打包层密码封装进 `.mskey` 还原钥匙；钥匙是敏感交付文件，
  不得写入普通清单、诊断包或提交 Git。上传位置仅按本次任务明确选择，清理产物时保留钥匙。
- 文案钥匙 `.tkey` 同属敏感交付文件：仅用户明确导出时可封装文字层和视频层所需密钥；
  默认本地交付，不自动上传，不写入任务、设置或日志，不提交 Git，清理时保留。该例外不表示功能已实现。
- 不提交账号凭据、会话、真实分享链接、截图/HTML、`runs/`、`rpa/state/`、`tmp/`。
- 行为变更同步 `docs/` 相关文档、`docs/status.md` 和 `CHANGELOG.md`；新功能附测试。
