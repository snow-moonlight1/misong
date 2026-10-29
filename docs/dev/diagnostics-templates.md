# ⑦ 诊断包导出与模板导入导出 · 交接说明

> 2026-10-30 S 已接入 CLI/API/设置页，并补齐公共文档。下文保留 G 初始交接；原待办中模板重写丢失 options/配方、源视频路径残留及脱敏第 1–5 项已修复。第 6 项仍由严格白名单控制，不能把任意原文交给日志。当前验收见[发布记录](../releases/0.2.0.md)。

初始交付状态：服务层与测试已完成（`src/misong/diagnostics.py`、`src/misong/templates.py`、
`tests/test_diagnostics.py`、`tests/test_templates.py`）。CLI / API / 设置页接线与公共文档、
status.md、CHANGELOG 更新由 S 完成（本包不得修改这些文件）。

## 1. 诊断包 `misong.diagnostics`

```python
export_diagnostics(output, *, tasks=(), state_dir=None, log_lines=(), screenshots=(),
                   secrets=(), environment=None, extra_paths=()) -> dict
# -> {"path", "members", "bytes", "screenshots", "notice"}
build_members(...) -> dict[str, bytes]   # 不写文件，预览/测试用
task_summary(folder) / account_status(state_dir) / failure_listing(state_dir)
DiagnosticsError(ValueError)             # 拒绝原因，可直接展示
SCREENSHOT_NOTICE                         # 附截图时必须展示给用户
```

- `output`：必须 `.zip`，不存在，父目录存在且不是链接；以 `xb` 独占创建，绝不覆盖。
- `tasks`：用户在任务中心**显式选择**的任务目录（≤ 20）。
- `state_dir`：`resolve_paths().state`。传 `None` 时不生成 accounts/failures。
- `log_lines`：调用方手上的界面日志行（桌面端事件日志、CLI 输出）。仓库目前没有落盘日志文件，
  模块不会自行寻找日志。最多 2000 行 / 40 万字符，单行截断 2000。
- `secrets`：调用方内存中的密码、魔曰密钥、提取码等，仅用于字面抗去（长度 ≥ 3），不写入包。
  导出前会对生成内容做自检，若仍含任一值则整体拒绝。
- `screenshots`：只接受用户本次在文件对话框选中的 png/jpg/jpeg/webp 普通文件（≤ 8 张、每张 ≤ 8 MB），
  拒绝链接、目录、`.mskey`/`.tkey`、HTML。截图**未经文本脱敏**；返回的 `notice` 非空时必须展示。
- `environment`：测试注入；默认调用 `doctor.check_environment()`，失败时仍导出。
- 总限制：成员 ≤ 64，未压缩总量 ≤ 40 MB；单条 JSON 记录 ≤ 2 MB。

### 压缩包成员（固定白名单，全部由模块生成）

| 成员 | 内容 |
| --- | --- |
| `manifest.json` | `schema_version: 1`、创建时间、成员列表、排除策略、截图数量与 `text_redacted: false` |
| `version.json` | misong 版本、Python、系统/版本/架构、是否打包版 |
| `environment.json` | `doctor.check_environment()` 报告 |
| `logs.txt` | 脱敏日志行 |
| `accounts.json` | 仅六个已知网盘的 `<disk>-status.json` 白名单字段：status / verified_at / session_at / session_error / last_error / last_error_at |
| `failures.json` | `state/failures/<disk>/page.png|page.html` 的名称、大小、修改时间，`included: false`；**不含内容** |
| `tasks/task-NN.json` | 选定任务的公开概要（见下） |
| `screenshots/NN.ext` | 仅显式附加时 |

任务概要只读 `misong-task.json`/`nde-task.json`/`relay-plan.json`，字段白名单：
- task：kind、title、created、chain、folder_name、settings（form、body_disks、hop_disk、expiry、access、schemes、
  layers_version、checksum、raw_merge、size、disguise、split、cleanup_after_upload；layers 仅 type/fmt/locked/header_enc/level/size/ext）。
  不含 pwd_hint、门面视频路径、artifacts 路径。
- plan：version、form、state、share_options(expiry/access)、schemes、stages（id/role/disk/state/文件数/总字节/已上传数/
  shared 布尔/custom_folder/error{type,stage}）、error{type,stage}、text_recipes（id/name/schemes/secret_slots 数量/carrier）、
  delivery（`workflows.delivery_status` 的 mode/label/完成标志/各配方状态、error_code、产物 role，不含路径）。
  分享链接、提取码、uploaded 映射、远端目录名、文案、错误 message 一律不进入。
- 损坏/超限/链接/越界记录记入 `problems`（`task:corrupt`、`plan:too_large`、`plan:rejected_link_or_outside` 等），不中断导出。

脱敏顺序：字面秘密 → 数据目录路径替换（`<MISONG_HOME>`/`<STATE>`/`<RUNS>`/`<TASK-N>`/`<USER_HOME>`，
大小写与斜杠不敏感）→ `redact.redact_data`。从不读取：登录状态 `<disk>.json`、`session-data/`、
`browser-data/`、`profiles/`、失败 HTML/截图内容、任务目录内的文案、`RESTORE.txt`、清单、钥匙。

## 2. 模板 `misong.templates`

```python
export_document(items) -> dict             # items = Api._load_templates() 中用户选中的项
export_file(items, path) -> {"path", "count"}   # .json，拒绝覆盖
parse_document(text_or_bytes) -> list       # 严格校验，返回干净模板
read_file(path) -> list                     # 只读用户选中的普通 .json（≤ 256 KB，非链接）
merge(existing, incoming, max_templates=30) -> {"templates", "added", "renamed"}
import_file(path, existing) -> 同 merge
unique_name(name, taken) -> str             # "名称 (2)"，大小写不敏感，截断到 24 字符
TemplateError(ValueError)
```

### 格式（schema_version 1）

```json
{"schema_version": 1, "kind": "misong-templates", "exported_at": "2026-10-29T23:59:00",
 "templates": [{
   "name": "lz4 → 7z加密",
   "layers": [{"fmt": "lz4", "locked": false, "header_enc": true},
              {"fmt": "7z", "locked": true, "header_enc": true, "level": 5},
              {"type": "cover", "video": ""}, {"type": "split", "size": "1G"},
              {"type": "rename", "ext": ".mp4"}],
   "disguise": "", "size": "",
   "options": {"raw_merge": false, "checksum": true},
   "text_recipes": [ /* DeliveryRecipe.to_dict()，可选 */ ]}]}
```

规则：
- 顶层必须且只能有 schema_version / kind / templates（可选 exported_at）；schema_version 必须是整数 1（布尔、字符串、其他版本拒绝）。
- 模板必须有 name / layers，可选 disguise / size / options / text_recipes；其他字段（password、account、inputs、
  session、export_keys、created…）一律拒绝。
- 层字段按类型严格白名单；archive 的 fmt 必须是已知格式，level 0–9；cover 的 video 必须为空串；之后复用
  `Api._clean_layers` + `layers.validate(check_video=False)`，不支持密码的格式 locked 归一为 false（与 save_template 一致）。
- disguise 复用 `Api._disguise` 的固定后缀表；size 复用 `split.parse_size`。
- text_recipes 复用 `DeliveryRecipe.from_dict` + `validate_recipes`（字段全等、≤ 16、槽位全局唯一）；只含槽位名，不含密钥。
  “导出 .tkey”选中状态不属于格式。
- JSON 重复键、NaN/Infinity、非 UTF-8、过深嵌套、> 256 KB、> 30 个模板、> 32 层均拒绝。
- 导出时（`strict=False`）从已存模板丢弃 created、密码、门面视频路径等非公开字段。
- 导入只做校验并返回数据；不写设置、不执行命令、不打开 URL、不读其他文件、不启动任务。
  合并后容量超过 30 整体拒绝，不做部分导入。

## 3. 初始接线建议（已完成，实际入口见发布记录）

### desktop/api.py
- `export_diagnostics(cfg)`（`@_safe`）：弹保存对话框取 `.zip` 路径（默认名 `misong-diagnostics-<时间>.zip`）；
  `tasks` 只接受 `self._managed(folder)` 通过的目录；`state_dir=self._state`；`log_lines` 传前端当前日志面板文本；
  `secrets` 传本次会话仍在内存中的密码/密钥（若有）；`extra_paths=[("<RUNS>", r) for r in self._output_roots]`。
  返回值原样交前端，`notice` 非空必须展示。
- `pick_screenshots()`：只用文件对话框返回的路径，不接受前端任意路径字符串（或在 API 侧记住本次对话框结果再核对）。
- `export_templates(names)`：`templates.export_file([t for t in self._load_templates() if t["name"] in names], path)`。
- `import_templates()`：打开对话框 → `templates.import_file(path, self._load_templates())` → `self._save_templates(result["templates"])`；
  返回 `added` / `renamed` 给前端提示。
- 注意：现有 `save_template()` 重写模板时只保留 name/layers/disguise/size/created，会丢掉导入的 options、text_recipes；
  且 `_clean_layers` 会把 cover 层的门面视频路径存进 `ui-templates.json`。导出已清空该路径，但本地模板文件仍含路径。

### cli.py
- `misong diagnostics export -o FILE.zip [--task DIR ...] [--screenshot FILE ...]`：`state_dir=resolve_paths().state`，
  无 `--screenshot` 时不附截图，有时打印 `notice`；目标已存在返回非 0。
- `misong template export -o FILE.json [--name N ...]` / `misong template import FILE.json`：读写 `<state>/ui-templates.json`
  （与桌面同一文件、同 seeded 语义），打印重命名结果。

### 设置页 / 前端（desktop/web）
- 设置页“诊断”区：勾选任务（默认当前任务或不选）、“附加截图”按钮默认关闭，选中后在按钮旁显示 `SCREENSHOT_NOTICE`；
  导出完成后显示成员列表与“打开所在文件夹”。文案说明“不含登录状态、Cookie、钥匙、文案与密码”。
- 模板区：“导出模板”（多选）与“导入模板”；导入结果列出重命名；错误以 `TemplateError` 文本展示。
- `scripts/ui_preview.py` 的 Fake 需补 `export_diagnostics`/`export_templates`/`import_templates`。

### 文档
- docs/status.md、docs/roadmap.md（⑦ 标记完成）、用户文档与 CHANGELOG 由 S 更新。

## 4. 给 S 的公共脱敏 / 模型缺陷（未修改，需协调）

实测 `redact.redact_text`（合成样本）：
1. 中文标签“密钥 / 魔曰密钥 / 魔咒 / 口令”未覆盖：`魔曰密钥：XXXX`、`口令：XXXX` 原样保留。
2. 无分隔符写法未覆盖：`密码 是 XXXX`、`魔曰密钥 XXXX`。
3. 非 `Users`/`home` 下的路径不脱敏：`D:\Data\alice\secret.mp4` 原样保留（文件名可能即敏感资源名）。
4. `sid=` 等短 Cookie/会话键名只在 `Cookie:` 头中被覆盖；裸 `sid=abcdefgh1234` 不脱敏。
5. 非六大网盘域名的分享链接路径 ID（如 `https://example.com/share/XYZ789`）不脱敏（按设计，但手动回填的其他网盘受影响）。
6. `redact_data` 对键名 `magic`/`spell`/`text`/`video` 不处理；文案原文与门面视频路径只能靠调用方白名单。

诊断包通过白名单 + 字面秘密 + 数据目录路径替换绕过了以上问题，但 `logs.txt` 中的第 1–4 类内容
在调用方未传 `secrets` 时仍可能漏出，建议 S 在 redact.py 补规则。

模型侧：`ui-templates.json` 中 cover 层保存本机视频路径（见上）；`Api._snapshot` 的 `video` 与 `settings.layers` 同样
保存本机路径。
# S 集成更新（2026-10-30）

已接入 CLI `diag export`、`template import/export`，桌面设置页和 API。模板重命名/重写保留 options/text_recipes，套用模板恢复公开参数和自定义密钥槽并清空密钥/视频源/导出勾选；模板内不再保存门面视频路径。中文口令、魔咒、无冒号标签、独立 sid 和自定义 Windows/挂载用户路径脱敏已修复并回归。外部分享 URL 的 share/s/f 路径 ID 也会脱敏。文案/任意未知正文仍由诊断白名单排除，不能把模式匹配说成能识别所有秘密。上方为 G 原始格式与交接记录。
