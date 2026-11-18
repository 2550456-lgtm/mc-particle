"""图片 -> 四角星粒子点阵（数据包）

  python tools/image2wall.py --input out/still.png --grid 64x36

产物：
  build/wall/<name>.zip          数据包（放进存档 datapacks/）
  build/wall/<name>_preview.png  用真实星形贴图模拟的预览

游戏里：
  /reload
  /function vid:test    画一次（在你正前方）
  /function vid:hold    一直亮着
  /schedule clear vid:hold   停
"""
import argparse
import json
import os
import subprocess
import sys
import zipfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcvideo import kmeans_palette, load_frames, quantize  # noqa: E402
from preview_star import load_sprite, sprite_kernel, to_png  # noqa: E402
from mcvideo import simulate_frame  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "..", "..", "test", "build")


def fmt_color(rgb):
    return ",".join(f"{c/255:.2f}" for c in rgb)


def build(input_path, grid, colors, pitch, fill, dist, name, sprite_path, preview_w):
    gw, gh = grid
    frames = load_frames(input_path, gw, gh)
    palette = kmeans_palette(frames, colors)
    idx = quantize(frames, palette)[0]

    dot_blocks = fill * pitch
    scale = dot_blocks / 0.2

    xstr = [f"{(c - (gw - 1) / 2) * pitch:.2f}" for c in range(gw)]
    ystr = [f"{(((gh - 1) / 2) - r) * pitch + 1.7:.2f}" for r in range(gh)]
    prefix = [f"particle dust{{color:[{fmt_color(rgb)}],scale:{scale:.2f}}} " for rgb in palette]

    lines = []
    for r in range(gh):
        for c in range(gw):
            lines.append(f"{prefix[idx[r, c]]}^{xstr[c]} ^{ystr[r]} ^{dist:.2f} 0 0 0 0 1")

    root = os.path.join(BUILD, "wall", name)
    fn = os.path.join(root, "data", "vid", "function")
    os.makedirs(fn, exist_ok=True)
    with open(os.path.join(fn, "draw.mcfunction"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(fn, "test.mcfunction"), "w", encoding="utf-8") as f:
        f.write("execute at @s rotated as @s run function vid:draw\n")
    with open(os.path.join(fn, "hold.mcfunction"), "w", encoding="utf-8") as f:
        f.write("execute at @p rotated as @p run function vid:draw\n")
        f.write("schedule function vid:hold 15t\n")
    with open(os.path.join(root, "pack.mcmeta"), "w", encoding="utf-8") as f:
        json.dump({"pack": {"pack_format": 94, "description": f"particle wall: {name}"}}, f, indent=2)

    out = os.path.join(BUILD, "wall", f"{name}.zip")
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for r_, _d, files in os.walk(root):
            for fn_ in files:
                p = os.path.join(r_, fn_)
                z.write(p, os.path.relpath(p, root).replace(os.sep, "/"))

    # 预览：用真实星形贴图
    preview_h = int(round(preview_w * gh / gw))
    alpha = load_sprite(sprite_path)
    px_per_block = preview_w / (gw * pitch)
    dot_px = max(2, int(round(dot_blocks * px_per_block)))
    cfg = dict(pitch=pitch, dot_blocks=dot_blocks, sprite_blocks=0.2,
               kernel=sprite_kernel(alpha, dot_px))
    sim = simulate_frame(idx, palette, cfg, preview_w, preview_h)
    pv = os.path.join(BUILD, "wall", f"{name}_preview.png")
    to_png(sim, pv)

    return dict(zip=out, preview=pv, cmds=len(lines), grid=[gw, gh],
                scale=round(scale, 2), wall=[round(gw * pitch, 1), round(gh * pitch, 1)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--grid", default="64x36")
    ap.add_argument("--colors", type=int, default=16)
    ap.add_argument("--pitch", type=float, default=0.25)
    ap.add_argument("--fill", type=float, default=1.6, help="星臂重叠程度，1.4~2.0")
    ap.add_argument("--dist", type=float, default=10.0, help="画在正前方多少格")
    ap.add_argument("--name", default="wall")
    ap.add_argument("--preview-w", type=int, default=1280)
    ap.add_argument("--sprite", default=os.path.join(BUILD, "_tmp", "glow.png"))
    args = ap.parse_args()

    gw, gh = (int(x) for x in args.grid.split("x"))
    r = build(args.input, (gw, gh), args.colors, args.pitch, args.fill,
              args.dist, args.name, args.sprite, args.preview_w)
    print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
