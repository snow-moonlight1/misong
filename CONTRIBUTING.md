# 参与贡献

欢迎提交 issue 和 pull request。

- 提交前运行 `.venv\Scripts\python -m pytest -q` 并全部通过；新功能请附测试，并同步相关文档与 `CHANGELOG.md`。
- 本项目以 GPL-3.0-or-later 发布；提交贡献即表示你同意以同一许可证发布该贡献。
- 不要提交账号、会话、真实分享链接、截图/HTML、`runs/`、`rpa/state/` 等本机数据。
- 报告网盘驱动失效时，请说明网盘、操作步骤和错误提示。`account probe` / `--diagnostics` 生成的截图和 HTML
  可能包含账号信息，请自行打码后再附上。
- 不接受验证码破解、风控绕过、私有接口签名、批量账号等功能。
- `src/misong/vendor/` 下的第三方文件保持原样；魔曰不升级到 V3.1.0 及以后（AIPL 与 GPL 不兼容）。

开发环境与代码结构见[开发指南](docs/dev/development.md)。
