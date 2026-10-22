// SPDX-License-Identifier: GPL-3.0-or-later
// Bridge CLI for the vendored 魔曰 (Abracadabra) V3.0.11 build (GPL-3.0).
// Called from Python via subprocess. Reads UTF-8 text from stdin and writes
// the UTF-8 result to stdout. Exit code non-zero + stderr message on error.
//
// usage: node abra_bridge.mjs <mode> [key]
//   mode: wenyan-enc | wenyan-dec | old-enc | old-dec
//   key : 魔咒/密钥, default "ABRACADABRA"
//
// V3.0.11 API: Input_Next() = 文言文模式, Input() = 传统模式.
// 新版魔曰（3.1+）的骈文/逻辑句式无法由 V3.0.11 解密；本工具生成的密文
// 可被所有新版魔曰正常解密。

import { Abracadabra } from "../vendor/abracadabra/abracadabra-cn.mjs";

const [mode, key = "ABRACADABRA"] = process.argv.slice(2);

const chunks = [];
for await (const c of process.stdin) chunks.push(c);
const input = Buffer.concat(chunks).toString("utf8");
// strip exactly one trailing newline added by callers, keep everything else
const text = input.endsWith("\n") ? input.slice(0, -1) : input;

try {
  const abra = new Abracadabra(Abracadabra.TEXT, Abracadabra.TEXT);
  switch (mode) {
    case "wenyan-enc":
      abra.Input_Next(text, Abracadabra.ENCRYPT, key);
      break;
    case "wenyan-dec":
      abra.Input_Next(text, Abracadabra.DECRYPT, key);
      break;
    case "old-enc":
      abra.Input(text, Abracadabra.ENCRYPT, key, false);
      break;
    case "old-dec":
      abra.Input(text, Abracadabra.DECRYPT, key);
      break;
    default:
      console.error(`unknown mode: ${mode}`);
      process.exit(2);
  }
  const out = abra.Output();
  process.stdout.write(typeof out === "string" ? out : Buffer.from(out));
} catch (err) {
  console.error(String(err && err.message ? err.message : err));
  process.exit(1);
}
