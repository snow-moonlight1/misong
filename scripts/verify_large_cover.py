"""Opt-in >4GiB compatibility check; keeps all evidence in --work (ignored).

Run with the project's Python, --video, --ffmpeg and optionally --winrar.
This deliberately creates large files; it never uses a personal account.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from misong import formats, merge, pack


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--ffmpeg", required=True)
    ap.add_argument("--winrar")
    ns = ap.parse_args()
    ns.work.mkdir(parents=True, exist_ok=False)
    src = ns.work / "large-source.bin"
    with src.open("wb") as fh:
        fh.write(b"MISONG large archive verification\n")
        fh.truncate(2**32 + 1024**2)
    expected = pack._sha256(src)
    def frames(path):
        r = subprocess.run([ns.ffmpeg, "-v", "error", "-i", str(path), "-map", "0", "-f", "framemd5", "-"],
                           capture_output=True, check=True)
        return [l for l in r.stdout.splitlines() if l and not l.startswith(b"#")]
    original = frames(ns.video)
    report = {"source_size": src.stat().st_size, "source_sha256": expected,
              "original_frames": len(original), "cases": []}
    for kind in ("7z", "zip"):
        print(f"Building >4GiB {kind}", flush=True)
        archive = ns.work / ("large." + kind)
        formats.compress(kind, src, archive, level=0)
        assert archive.stat().st_size > 2**32
        out = ns.work / ("large-" + kind + ".mp4")
        embedding = merge.embed_in_mp4(ns.video, archive, out, kind)
        assert frames(out) == original
        result = {"kind": kind, "archive_size": archive.stat().st_size,
                  "mp4_size": out.stat().st_size, "playback_frames_identical": True, **embedding}
        exe = formats.sevenzip_executable()
        test = subprocess.run([str(exe), "t", str(out)], capture_output=True)
        (ns.work / (kind + "-7za-test.txt")).write_bytes(test.stdout + test.stderr)
        assert test.returncode in (0, 1), test.stdout
        restored = merge.extract_embedded(out, ns.work / ("extracted." + kind))
        got = formats.extract(kind, restored, ns.work / (kind + "-7za"))
        assert pack._sha256(got) == expected
        result["7za_extracted_sha256_identical"] = True
        if ns.winrar:
            dest = ns.work / (kind + "-winrar")
            dest.mkdir()
            r = subprocess.run([ns.winrar, "x", "-ibck", "-inul", "-y", str(out.resolve()), str(dest.resolve()) + "\\"],
                               creationflags=formats.NO_WINDOW)
            result["winrar_exit"] = r.returncode
            assert (dest / src.name).is_file(), f"WinRAR did not extract {kind}: {r.returncode}"
            assert pack._sha256(dest / src.name) == expected
            result["winrar_extracted_sha256_identical"] = True
        report["cases"].append(result)
        (ns.work / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(result), flush=True)
    print("LARGE COVER CHECK PASSED", flush=True)


if __name__ == "__main__":
    main()
