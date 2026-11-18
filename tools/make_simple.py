"""最小可用版：一条命令，在玩家面前画一面粒子墙。

不需要坐标、不需要传送、不需要资源包。
- draw.mcfunction  : 用局部坐标 ^ ^ ^ 画一帧
- test.mcfunction  : 以玩家为基准调用 draw
- hold.mcfunction  : 循环重绘（粒子只活 0.7 秒，所以要一直重画）

用法：/function vid:test    画一次
      /function vid:hold    一直亮着（再执行 /schedule clear vid:hold 停）
"""
import json
import os
import subprocess
import sys
import zipfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "..", "..", "test", "build")

PITCH = 0.3
DIST = 8.0          # 墙在正前方多少格
EYE = 1.7           # 相对脚底抬高
SCALE = 2.4         # 星形贴图下约 0.48 格


def fmt_color(rgb):
    return ",".join(f"{c/255:.2f}" for c in rgb)


def main():
    d = np.load(os.path.join(BUILD, "galaxy-star", "frames.npz"))
    idx, palette = d["idx"], d["palette"]
    frame = idx[45]
    h, w = frame.shape

    xstr = [f"{(c - (w - 1) / 2) * PITCH:.2f}" for c in range(w)]
    ystr = [f"{(((h - 1) / 2) - r) * PITCH + EYE:.2f}" for r in range(h)]
    prefix = [f"particle dust{{color:[{fmt_color(rgb)}],scale:{SCALE:.2f}}} " for rgb in palette]

    lines = []
    for r in range(h):
        for c in range(w):
            lines.append(f"{prefix[frame[r, c]]}^{xstr[c]} ^{ystr[r]} ^{DIST:.2f} 0 0 0 0 1")

    root = os.path.join(BUILD, "simple")
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
        json.dump({"pack": {"pack_format": 94, "description": "particle wall (simple)"}}, f, indent=2)

    out = os.path.join(BUILD, "simple.zip")
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for r_, _d, files in os.walk(root):
            for fn_ in files:
                p = os.path.join(r_, fn_)
                z.write(p, os.path.relpath(p, root).replace(os.sep, "/"))
    print(f"{w}x{h} = {len(lines)} 条指令 -> {out} ({os.path.getsize(out)} bytes)")


if __name__ == "__main__":
    main()
