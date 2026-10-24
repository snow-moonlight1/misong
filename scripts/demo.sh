#!/usr/bin/env bash
# End-to-end demo of the whole 备菜 pipeline. From repo root:
#   bash scripts/demo.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
D=demo && rm -rf $D && mkdir -p $D/res
echo "内部资料 $(date)" > $D/res/readme.txt
head -c 4000 /dev/urandom > $D/res/data2.bin 2>/dev/null || .venv/Scripts/python -c "import pathlib;pathlib.Path('$D/res/data2.bin').write_bytes(b'rand'*999)"
ffmpeg -y -hide_banner -loglevel error -f lavfi -i testsrc2=size=320x240:rate=15:duration=2 -c:v libx264 -preset ultrafast -movflags +faststart $D/intro.mp4

echo "== 1. 一键嵌套加密 lz4->zip->7z(头加密)，伪装 .mp4"
$PY -X utf8 misong.py nest $D/res -L lz4,zip,7z -P=-,pwInner,pwOuter -o $D/pkg --disguise .mp4

echo "== 2. 分卷 (800k/卷)"
$PY -X utf8 misong.py split $D/pkg.mp4 -s 800k -o $D/vol

echo "== 3. 合并门面视频 (zip 偏移自动修正)"
$PY -X utf8 misong.py merge $D/intro.mp4 $D/pkg.mp4 -o $D/cover.mp4
ffprobe -v error -show_entries format=format_name -of default=nw=1 $D/cover.mp4

echo "== 4. 中转计划模板"
$PY -X utf8 misong.py relay --form simple --disk1 飞猫盘 --disk2 夸克 --pwd-hint-at 00:47 -o $D/relay

echo "== 5. 链接混淆三连"
LINK="https://pan.example.com/s/Ab1 提取码:K9mZ 包密码见视频"
$PY -X utf8 misong.py code encode -S beast   -T "$LINK" | head -1
$PY -X utf8 misong.py code encode -S hajimi  -T "$LINK" | head -c 120; echo ...
$PY -X utf8 misong.py code encode -S mojibake --key 我的魔咒 -T "$LINK" | head -c 160; echo ...

echo "== 6. 接收方还原：分卷合并 -> 嗅探连剥 -> 内容一致"
$PY -X utf8 misong.py join $D/vol/pkg.mp4.part001 -o $D/pkg.re.mp4
$PY -X utf8 misong.py unwrap $D/cover.mp4 -o $D/unwrapped --chain-pwd=pwOuter,pwInner,-
diff $D/res/readme.txt $D/unwrapped/chain-tar/extracted/res/readme.txt && echo "DEMO OK: 全链路内容一致"
