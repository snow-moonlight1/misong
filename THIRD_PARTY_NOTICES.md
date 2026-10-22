# Third-Party Notices / 第三方组件声明

netdiskencrypt (nde) as a whole is licensed under **GPL-3.0-or-later** (see `LICENSE`).
The components below are redistributed in this repository or package and keep their own licenses.
本项目整体以 GPL-3.0-or-later 发布；以下组件随仓库或安装包分发，各自保留原许可证。

## 1. Abracadabra 魔曰 V3.0.11

- File: `src/nde/vendor/abracadabra/abracadabra-cn.mjs` — `dist/abracadabra-cn.js` from the npm package
  `abracadabra-cn@3.0.11`, content unmodified (renamed to `.mjs` only).
  SHA-256 `bf472ed92dd7cb16977241a06dd5fc0ddc1875e684706f3453d34b8e636a01f0`.
- Author: SheepChef. License: **GPL-3.0** (full text: `src/nde/vendor/abracadabra/LICENSE`).
- Corresponding source: <https://github.com/SheepChef/Abracadabra/tree/V3.0.11>
- Note: upstream switched to the AIPL license from V3.1.0. No AIPL-licensed code is used or distributed here.
- The bundle contains the following libraries (licenses unchanged):
  - Unishox2 (Siara Logics) — Apache-2.0
  - crypto-js — MIT; its RIPEMD-160 part © 2012 Cédric Mesnil, BSD-style license (notice retained in the bundle)
  - pako 2.1.0 — MIT AND Zlib (<https://github.com/nodeca/pako>)
  - js-base64 3.7.7 — BSD-3-Clause, © Dan Kogai
  - mersenne-twister — BSD-3-Clause, © Makoto Matsumoto and Takuji Nishimura; JavaScript port by Sean McCullough

## 2. 7-Zip 26.04 Extra — `7za.exe`

- Files: `src/nde/vendor/7zip/7za.exe`, `License.txt`, `README.txt`. Official binary, unmodified.
- Copyright (C) Igor Pavlov. License: GNU LGPL-2.1-or-later, with some parts under BSD-3-Clause
  (see `src/nde/vendor/7zip/License.txt`).
- Source code: <https://www.7-zip.org/> (download page provides the matching source package).
- nde runs 7za as a separate process; it is not linked or modified.

## 3. hachimi-wonameruto-translator 哈基米语翻译器

- `src/nde/encoders/hajimi.py` is a Python translation of its TypeScript implementation;
  `tests/harness/ref-bundle.mjs` is a build of its `src/lib/hachimiTranslator.ts` (tests only).
- Upstream: <https://github.com/Starpuccino/hachimi-wonameruto-translator>
- License: MIT, Copyright (c) 2025 Starpuccino (full text below).

## 4. fflate 0.8.3 (tests only)

- Included in `tests/harness/ref-bundle.mjs`. Upstream: <https://github.com/101arrowz/fflate>
- License: MIT, Copyright (c) 2026 Arjun Barrett (full text below).

## 5. Beast / 兽音译者

`src/nde/encoders/beast.py` is an independent implementation written from the published algorithm
description and checked against public sample vectors of <https://github.com/SycAlright/beast_sdk>.
No code or files from that repository are included.

## 6. Python dependencies (installed by pip, not included in this repository)

| Package | License |
|---|---|
| py7zr | LGPL-2.1-or-later |
| pyzipper | MIT |
| lz4 | BSD-3-Clause |
| zstandard | BSD-3-Clause |
| brotli | MIT |
| pywebview (optional `gui`) | BSD-3-Clause |
| playwright (optional `rpa`) | Apache-2.0 |
| pytest (optional `dev`) | MIT |

## 7. Trademarks / 商标

The netdisk icons in `src/nde/desktop/web/disks/` and the service names (Quark, Feimao, Baidu Netdisk, UC Drive,
Xunlei/Thunder, 123pan) belong to their respective owners and are used only to identify those services in the UI.
This project is not affiliated with or endorsed by any of them.

---

## MIT License text (applies to sections 3 and 4 with the copyright lines given there)

```
MIT License

Copyright (c) 2025 Starpuccino
Copyright (c) 2026 Arjun Barrett

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
