# 命令参考（2026-10-30 v0.2 接线）

以实际 `misong <命令> --help` 为准；本表只记录对智能体重要的行为。

| 命令 | 联网 | 密码/密钥输入 | 要点 |
|---|---|---|---|
| `formats` | 否 | — | 列出层格式 |
| `nest` | 否 | `-P` 命令行（无交互） | `-L` 内到外；`-P` 按层逗号对齐，`-` 表示无密码；`--export-key` 生成 `.mskey`（含层密码）；同时写 `.misong.json` 公开清单 |
| `unest` | 否 | `-P` 外→内 | 默认找同名 `.misong.json` |
| `restore` | 否 | 不需要（钥匙内含） | `source` 可为产物、任意分卷或文件夹；`-o` 必须是空目录；缺卷/损坏/不匹配时不交付半成品 |
| `split` | 否 | — | `-s` 如 `1900MB`，纯数字按 MB；未超过不分卷；生成 `.misongsplit.json` |
| `join` | 否 | — | 传任意 `.001`；有清单时自动校验，`--no-verify` 关闭 |
| `merge` | 否 | — | 视频放第一个；默认修正 zip 偏移，`--raw` 纯拼接 |
| `unwrap` | 否 | `-P` / `--chain-pwd` 命令行 | 从伪装/合并文件提取归档 |
| `code` | 否 | 魔曰 `--key` 命令行 | 方案 beast/mojibake/hajimi/base64/base64url/base32/base85/hex/url/reverse/rot13/trunc；逗号串联 |
| `relay` | 否 | — | 生成中转 `relay-plan.json` 与 `guide.txt` 模板，不上传 |
| `text-deliver` | 纯文字否；帧语是 | `getpass` 交互 | `-o` 必须不存在（已存在报 `TextOperationError: io`）；`--export-key <id>` 可重复 |
| `text-restore` | 纯文字否；视频是 | `--key-file` 或 `--recipe`+`getpass` | `-o` 为不存在的文件 |
| `publish --prepare` | 否 | `-P` 命令行 | 只生成产物与 `relay-plan.json`/`misong-task.json` |
| `publish`（无 `--prepare`）/ `--plan` | 是（上传分享） | 文案密钥 `getpass`；`--key`、`--hop-password` 命令行 | 需用户确认；续跑不能覆盖任务选项 |
| `share-import` | 否 | — | 手动上传后回填分享文本 |
| `account status` | 否 | — | 只看本地是否有会话文件 |
| `account login/probe <盘>` | 是 | 用户在浏览器中完成 | 盘名：quark feimao baidu xunlei uc 123pan |
| `doctor [--json]` | 否 | — | 只读，已脱敏 |
| `account check <盘>` / `account check --all` | 是 | 不输入凭据 | 有界只读检查，`--timeout`、`--headless`、`--headed-retry`；失效/网络/人工验证分开 |
| `selfcheck --disk <盘>` | 是 | 不输入凭据 | 只读检查关键入口，逐项报告；不上传或分享；仅显式 `--diagnostics` 保存原始失败页面快照 |
| `diag export -o <新文件.zip>` | 否 | — | 白名单诊断；`--task` 可重复，截图仅显式 `--screenshot` 才附加 |
| `template export/import <文件.json>` | 否 | — | 公开模板，严格校验与冲突改名；导入不执行任务 |
| `data-migrate` | 否 | — | 显式复制数据目录；涉及登录会话，需用户明确要求 |
| `gui` | — | GUI 内输入 | 桌面界面；带密码的操作优先引导到这里 |

`MISONG_HOME` 环境变量控制会话与任务数据位置。做实验时可指向一个空的临时目录，避免碰到真实登录态。

## 文案配方

纯文字（离线）——`recipes.json`，可含多个方案：

```json
[
  {"version":1,"id":"encoded","name":"Base64 文案","layers":[
    {"id":"text","scheme":"base64","version":1,"params":{},"secret_slot":null}
  ],"carrier":{"format_id":"text","version":1,"mode":"plain","params":{},"secret_slot":null}}
]
```

帧语视频（联网操作官网）——将 carrier 换成：

```json
{"format_id":"framewords","version":1,"mode":"standard","params":{},"secret_slot":"encoded/video"}
```

视频无密码时 `secret_slot` 设为 `null`。层的可用 scheme 与参数白名单以 `docs/dev/text-delivery.md` 和契约文档为准，配方里不写密码。

## 产物里哪些可以公开

| 文件 | 性质 |
|---|---|
| `*.misong.json`、`*.misongsplit.json`、`RESTORE.txt` | 公开清单/说明，不含密码 |
| `relay-plan.json`、`misong-task.json` | 任务记录，可能含真实分享链接，不要贴出或提交 |
| `*.mskey`、`*.tkey` | 敏感还原凭据 |
| `rpa/state/` 会话、诊断快照 | 私密，不手动读取凭据或自动外发；应用运行时正常复用专用会话 |
| `runs/` 任务 | 私密，仅为用户授权任务读取必要公开计划/状态；不回显分享链接或钥匙 |
