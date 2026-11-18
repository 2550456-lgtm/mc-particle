"""用真实粒子贴图（四角星）离线模拟，把 fill 调准。

  python tools/preview_star.py --build build/galaxy-final --frame 45 --fills 1.0 1.3 1.6
"""
import argparse
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcvideo import simulate_frame, upscale  # noqa: E402


def load_sprite(path, size=8):
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-vf", "format=rgba",
         "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
        capture_output=True,
    )
    a = np.frombuffer(p.stdout, np.uint8)
    if a.size != size * size * 4:
        raise RuntimeError(f"{path}: got {a.size}, want {size*size*4}")
    return a.reshape(size, size, 4)[..., 3].astype(np.float32) / 255.0


def sprite_kernel(alpha, dot_px):
    """把 8x8 贴图重采样到屏幕上的 dot_px 像素，生成 (dy,dx,w) 权重表。"""
    s = alpha.shape[0]
    idx = np.clip(((np.arange(dot_px) + 0.5) * s / dot_px).astype(int), 0, s - 1)
    small = alpha[np.ix_(idx, idx)]
    r = dot_px // 2
    out = []
    for y in range(dot_px):
        for x in range(dot_px):
            w = float(small[y, x])
            if w > 0.02:
                out.append((y - r, x - r, w))
    return out


def to_png(img, path):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{img.shape[1]}x{img.shape[0]}", "-i", "-", "-frames:v", "1", path],
        input=np.ascontiguousarray(img).tobytes(), capture_output=True,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="test/build/galaxy-final")
    ap.add_argument("--frame", type=int, default=45)
    ap.add_argument("--fills", nargs="+", type=float, default=[1.0, 1.3, 1.6])
    ap.add_argument("--pitch", type=float, default=0.3)
    ap.add_argument("--sprite", default=r"build\_tmp\glow.png")
    ap.add_argument("--w", type=int, default=520)
    ap.add_argument("--h", type=int, default=293)
    args = ap.parse_args()

    d = np.load(os.path.join(args.build, "frames.npz"))
    idx, palette = d["idx"], d["palette"]
    k = min(args.frame, len(idx) - 1)
    alpha = load_sprite(args.sprite)

    tiles = []
    for f in args.fills:
        dot_blocks = f * args.pitch
        px_per_block = args.w / (idx.shape[2] * args.pitch)
        dot_px = max(2, int(round(dot_blocks * px_per_block)))
        cfg = dict(pitch=args.pitch, dot_blocks=dot_blocks, sprite_blocks=0.2,
                   kernel=sprite_kernel(alpha, dot_px))
        tiles.append(simulate_frame(idx[k], palette, cfg, args.w, args.h))
        print(f"fill={f}  dot={dot_blocks:.3f}格  {dot_px}px on screen")

    sheet = np.concatenate(tiles, axis=1)
    out = os.path.join(args.build, "preview", "star_fills.png")
    to_png(sheet, out)
    print(out, sheet.shape)


if __name__ == "__main__":
    main()
