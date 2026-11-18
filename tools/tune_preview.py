"""在已生成的 frames.npz 上试不同的光斑大小，拼成一张对比图（不重跑整条管线）。

  python tools/tune_preview.py --build build/galaxy --frame 45 --scales 1 1.5 2 3
"""
import argparse
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcvideo import simulate_frame, upscale  # noqa: E402


def to_png(img, path):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{img.shape[1]}x{img.shape[0]}", "-i", "-", "-frames:v", "1", path],
        input=np.ascontiguousarray(img).tobytes(), capture_output=True,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="build/galaxy")
    ap.add_argument("--frame", type=int, default=45)
    ap.add_argument("--scales", nargs="+", type=float, default=[1.0, 1.5, 2.0, 3.0])
    ap.add_argument("--pitch", type=float, default=0.15)
    ap.add_argument("--w", type=int, default=640)
    ap.add_argument("--h", type=int, default=360)
    args = ap.parse_args()

    d = np.load(os.path.join(args.build, "frames.npz"))
    idx, palette = d["idx"], d["palette"]
    k = min(args.frame, len(idx) - 1)

    tiles = [upscale(idx[k], palette, args.w, args.h)]
    labels = ["quantized"]
    for s in args.scales:
        cfg = dict(pitch=args.pitch, dot_blocks=s * args.pitch, sprite_blocks=0.2)
        tiles.append(simulate_frame(idx[k], palette, cfg, args.w, args.h))
        labels.append(f"scale={s}")

    sheet = np.concatenate(tiles, axis=1)
    out = os.path.join(args.build, "preview", "scale_compare.png")
    to_png(sheet, out)
    print(" | ".join(labels))
    print(out, sheet.shape)


if __name__ == "__main__":
    main()
