# 统一脱敏模块 `misong.redact`

roadmap 前置工作，供 ④ 驱动自检、⑦ 诊断包导出、② 链接体检、⑨ 智能体输出共用。
模块只提供纯函数：不打开文件、不联网、不读取 `.mskey` 钥匙内容，不接入任何
输出通道。主线在桌面执行日志、任务进度、doctor 与诊断出口调用本模块；诊断另外用固定文件白名单控制读取范围。单元测试见
`tests/test_redact.py`，全部使用合成标记（`syn` 前缀），不含真实凭据。

## API

| 函数 | 说明 |
| --- | --- |
| `redact_text(text: str) -> str` | 脱敏自由文本；非 `str` 抛 `TypeError`。 |
| `redact_data(value)` | 递归复制 JSON 兼容结构并脱敏；不修改输入。 |
| `PLACEHOLDER` | 统一占位符 `[REDACTED]`，可用作验收检索标记。 |

`redact_data` 的结构规则：dict / list / tuple 逐层复制（层序保留），字符串统一走
`redact_text`；`pathlib.Path` 转为脱敏文本；bytes / bytearray 不解码、整体占位；
`bool` / `None` / `int` / `float` 原样保留；契约外的其他对象原样透传（调用方应
传入 JSON 兼容数据）。输出可用 `json.dumps` 序列化，且脱敏幂等（重复脱敏结果不变）。

## 覆盖范围

- **分享链接**：`providers.py` 六个网盘（夸克、飞猫、百度、迅雷、UC、123）链接中的
  ID 路径段（`/s/<id>`、飞猫 `/f/<id>`、123 品牌域 `/123pan/<id>`、百度旧版 `surl`
  参数）与提取码查询参数（`pwd` / `code` / `password` / `passcode`）。平台域名保留。
- **提取码与口令标签**：`提取码` / `访问码` / `取件码` / `提取密码`（分隔符可省略），
  `密码` / `password` / `passwd` / `pwd` / `passcode`，以及 `魔曰密钥` / `密钥` / `魔咒` / `口令`；中文标签支持分隔符、空白或“是”，
  包括中文、emoji、长口令和带引号的含空格口令；`key` / `secret` / `token` 也覆盖短值及带引号值。
  比 `sharing.parse_share` 更宽：`解压密码` 等归档口令同样脱敏；`提取码：https://…`
  的 `https` 不会被当作提取码。
- **HTTP 头**：`Cookie` / `Set-Cookie` 整值占位（多项 Cookie 一次覆盖）；
  `Authorization` 保留 `Bearer` / `Basic` / `Token` 方案词，其余整体占位。
- **任意 URL 的敏感查询参数**：名称含 `pwd` / `password` / `passcode` / `token` /
  `secret` / `surl` / `sign` / `auth` / `key` / `code`（含百分号编码的参数名）；
  URL userinfo（`user:pass@host`）占位。
- **百分号编码的 URL**（日志中的 redirect / 嵌套引用）：解码后脱敏再按固定规则重编码，
  占位符括号保持明文以便检索；URL 片段中的编码提取码同样处理。
- **裸键值对**：`token=` / `api_key=` / `secret=` / `session_id=` 等；`sid` / `sessid` / `sessionid` 也覆盖短值。
- **用户路径**：`C:\Users\<名>`（含正斜杠写法）与 `/home/<名>`、`/Users/<名>`（macOS）；
  这些路径替换用户名段。其他盘符绝对路径（包括引号内带空格路径）整体替换；`/mnt`、`/media`、`/Volumes`、`/data` 的用户路径也覆盖。
- **结构化数据键名**：含 `password` / `passwd` / `pwd` / `passcode` / `secret` /
  `token` / `cookie` / `authorization` / `credential` / `auth` / `key` 子串的键，
  以及恰好叫 `code` 或以 `_code` / `-code` 结尾的键（如 `ShareInfo.to_dict()` 的
  `code`），以及中文密钥标签和会话 sid 类键。此类键下的字符串与 bytes 占位；`bool` / `None` 保留（`has_password`
  等标志不是口令本身）；list 逐项折叠为占位（条目数保留）；dict 整体占位。

## 保留的排障信息

平台域名、可保留的路径结构、非敏感查询参数、时间戳、数量（文件数 / 卷数 / 大小 / 长度）、
布尔标志、格式（`format`）与状态（`status`）、层序均保留。

## 已知边界

- 数值即使位于密码类字段也按计数保留（本项目口令恒为字符串；数值口令无法与计数区分）。
- `key` / `auth` / `code` 采用子串匹配，良性键（如 `author`、`barcode`）会被过度脱敏；
  宁多脱、不泄漏。
- 仅识别标准 JSON 兼容结构加 `Path` / `bytes`；其他对象不检查即透传。
  输入含循环引用时行为未定义（JSON 兼容数据不会有环）。
- 双重百分号编码的 URL、编码后藏在非敏感参数值里的子参数不保证识别；未知域名的常见 `/s/<id>`、`/f/<id>`、`/share/<id>` 也会脱敏，但无法识别所有自定义链接格式。
- 网盘管理页 URL 的目录 `fid`、`pdir_fid` 等账号内目录标识不在覆盖范围。
- 没有引号的含空格口令无法可靠区分边界；应通过结构化字段脱敏，日志写入方仍应避免输出凭据原值。
- `.mskey` / `.tkey` 钥匙：本模块只处理其**路径文本**（按普通路径规则脱敏），
  绝不打开文件；bytes 形态的钥匙载荷整体占位、不嗅探内容。但若有人把钥匙的
  base64 文本当作普通字符串塞进诊断数据，无法可靠识别——调用方不得把钥匙内容
  放进任何诊断数据（见 `restore_key.py` 模块说明）。
- 替换会做轻度归一（如 `Cookie:  x` 变为 `Cookie: [REDACTED]`），不保证逐字节保形。

## 验收建议

诊断包等产物的验收（roadmap ⑦）：在脱敏产物中检索真实链接 ID、提取码、密码与
Cookie 样本，均不得命中；`[REDACTED]` 出现次数可作为覆盖参考，但不能替代前者。
