# 魔曰 Abracadabra V3.0.11（内置副本）

- 上游：https://github.com/SheepChef/Abracadabra （作者 SheepChef）
- 版本：V3.0.11（2025-03-31 发布），是该项目以 **GPL-3.0** 发布的最后一个版本。
  V3.1.0 起上游改用 AIPL（非开源许可证），因此本项目固定使用此版本。
- 来源：npm 包 `abracadabra-cn@3.0.11` 的 `dist/abracadabra-cn.js`
  （https://registry.npmjs.org/abracadabra-cn/-/abracadabra-cn-3.0.11.tgz）。
  内容未修改，仅改扩展名为 `.mjs` 以便 Node 按 ES 模块加载。
- SHA-256：`bf472ed92dd7cb16977241a06dd5fc0ddc1875e684706f3453d34b8e636a01f0`
- 许可证：GPL-3.0，全文见同目录 `LICENSE`（取自同一 npm 包）。
- 对应源码：https://github.com/SheepChef/Abracadabra/tree/V3.0.11

该构建产物内含以下第三方组件（各自许可证不变）：
Unishox2（Apache-2.0）、crypto-js（MIT）、pako（MIT AND Zlib）、
js-base64（BSD-3-Clause）、mersenne-twister（BSD-3-Clause）。详见仓库根目录
`THIRD_PARTY_NOTICES.md`。

## 兼容性

| 方向 | 结果 |
|---|---|
| 本工具（3.0.11）加密 → 新版魔曰解密（文言、传统） | 完全兼容 |
| 新版魔曰传统模式 → 本工具解密 | 完全兼容 |
| 新版魔曰文言模式 → 本工具解密 | 部分可解；含新句式（骈文/逻辑）时会失败并提示改用官方网页 |

由 `src/nde/encoders/abra_bridge.mjs` 调用：`Input_Next()` 为文言模式，`Input()` 为传统模式。
