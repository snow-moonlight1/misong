# ⑨a 智能体 Skill 文档交接（H 包）

> 2026-10-30 S 已补齐 account check、selfcheck、diag export 与 template import/export 的命令表、示例和公共链接。下文为 H 初始交接，原“待接线”清单已完成；最终验证见[发布记录](../releases/0.2.0.md)。

## 交付

- `skills/misong/SKILL.md`：主文档，覆盖打包、分卷、`.mskey` 还原、`code` 编解码、`text-deliver`/`text-restore`（含 `.tkey`）、`publish --prepare` → 确认 → `publish --plan`、续跑与 `share-import`。
- `skills/misong/references/cli.md`：命令表（是否联网、密码输入方式）、文案配方示例、产物敏感性。
- `skills/misong/references/safety.md`：钥匙、密码、发布确认、登录风控、外部内容视为数据。
- 未新增仓库脚本或测试；验证脚本留在被忽略的 `tmp/skill-check/run.cmd`（`MISONG_HOME` 指向该目录下的空 home）。

## 写作中确认的事实（以源码为准）

- `nest/unest/unwrap/publish -P`、`unwrap --chain-pwd`、`publish --hop-password/--key`、`code --key` 只能从命令行传入，没有交互、stdin 或环境变量方式。Skill 因此要求智能体把带密码的操作交给 GUI 或用户自行运行。
- 仅 `_text_secrets()` 使用 `getpass`：`text-deliver`、`text-restore --recipe`、非 `--prepare` 的 `publish`（未完成方案的 slot）。
- `publish --plan` 续跑拒绝覆盖配方、钥匙位置、清理、名称、网盘、分享选项和输入资源。

## 实际验证（2026-10-29，合成数据，`tmp/skill-check/`）

- 所有引用命令的 `--help`：顶层及 nest、unest、restore、text-deliver、text-restore、split、join、merge、unwrap、code、relay、publish、account、share-import、doctor。
- `nest src -L zip,7z --export-key` → `restore pkg.7z -o restored`：2 层校验还原成功；`unest`（无密码层）成功。
- `split -s 1`（3 MiB 随机文件 → 3 卷）→ `join` 校验通过，`fc /b` 一致。
- `code encode/decode -S beast,base64`（虚构链接）往返一致；`hajimi` 编码成功。
- `text-deliver --export-key encoded` → `text-restore --key-file ...tkey`：摘要校验通过，字节一致；对已存在输出目录返回 `TextOperationError: io`（退出 1）。
- `publish ... --body-disk baidu -L zip -s 1 --restore-key-location local --text-recipes recipes.json --prepare`：生成 4 卷、清单、`.mskey`、`relay-plan.json`，未联网。
- `doctor --json`、隔离 `MISONG_HOME` 下的 `account status`（全部“未登录”）成功。

## 未验证

- 带密码层的 `-P` 示例（有意不在命令行写密码）；`merge`/`unwrap` 门面视频、`relay`、`mojibake`（需 Node）未在本轮重跑。
- 带 `secret_slot` 的配方（getpass 需交互终端）。
- 帧语视频 `--video`/`--input-kind video`：依赖官网与浏览器，未执行。
- 非 `--prepare` 的 `publish`、`publish --plan` 续跑、`share-import`、`account login/probe`：需真实网盘/登录，未执行。

## H 初始待办（历史，S 已完成）

H 交付时以下命令尚未接线；2026-10-30 已按实际 `--help` 更新 Skill，并移除了“尚未接入 CLI”的旧声明。原清单保留以便追溯：

1. ⑧ 登录批量检查：路线图拟定 `misong account check --all [--headless]`；补入「账号与环境」，并把发布前预检写进发布流程第 1 步。
2. ④ 只读选择器自检：拟定 `misong selfcheck --disk <盘>`；补入排障一节，注明联网、只读。
3. ⑦ 诊断包：拟定 `misong diag export`（见 `docs/dev/diagnostics-templates.md`）；补入时说明截图默认不包含、显式附加为敏感材料，导出前需用户同意，禁止自动上传。
4. ⑦ 模板导入导出：命令名待 S 定；补入时强调模板不含密码/账号，导入不启动任务。
5. 在 `skills/misong/references/cli.md` 命令表增加上述行。
6. 链接：可在 `docs/dev/development.md` 或 `docs/roadmap.md` ⑨a 条目引用 `skills/misong/SKILL.md` 与本文；`docs/status.md`、`CHANGELOG.md` 记录本交付（本包按要求未改公共文档）。
7. 若将来增加密码交互输入（如 `nest`/`publish` 的 getpass），更新 SKILL.md 规则 2 与 safety.md 密码一节。
# S 集成更新（2026-10-30）

account check、selfcheck、diag export 和 template import/export 已接线，Skill 及命令表已补充。原有密码命令仍没有交互密码入口，保持桌面界面/用户自行执行的规则，不编造新参数。上方 H 初始交付中的待接线条目以此更新为准。
