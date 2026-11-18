"""16x16 发光菱形贴图，同时覆盖 generic_0~7（给 dust）和 glow（给 glow 粒子）。

设计：中心实心菱形 + 外圈柔和衰减 => 在游戏里看起来像"发光"。
Minecraft 没有 bloom，粒子只受世界光照，所以发光感必须烘进贴图。
"""
import os
import subprocess
import sys
import zipfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "test", "build")
PACK_FORMAT = 34
SIZE = 16


def glowing_diamond(size=SIZE):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2.0
    dx, dy = xx - c, yy - c

    # 菱形距离：边缘处为 1
    d = (np.abs(dx) + np.abs(dy)) / (size / 2.0)
    # 实心菱形芯，边缘 1.5 像素抗锯齿
    core = np.clip((1.0 - d) * 7.0, 0.0, 1.0)

    # 圆形柔光晕（比菱形大一圈）
    r = np.sqrt(dx * dx + dy * dy) / (size / 2.0)
    halo = np.clip(1.0 - r / 1.15, 0.0, 1.0) ** 2 * 0.55

    alpha = np.maximum(core, halo)
    rgba = np.zeros((size, size, 4), np.uint8)
    rgba[..., 0:3] = 255          # 纯白，游戏用粒子颜色去乘
    rgba[..., 3] = (np.clip(alpha, 0, 1) * 255).astype(np.uint8)
    return rgba


def encode_png(rgba, path):
    h, w = rgba.shape[:2]
    p = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
         "-s", f"{w}x{h}", "-i", "-", "-frames:v", "1", path],
        input=np.ascontiguousarray(rgba).tobytes(), capture_output=True,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:500])


def main():
    work = os.path.join(OUT, "_glow16")
    tex = os.path.join(work, "assets", "minecraft", "textures", "particle")
    os.makedirs(tex, exist_ok=True)

    rgba = glowing_diamond()
    for i in range(8):
        encode_png(rgba, os.path.join(tex, f"generic_{i}.png"))
    encode_png(rgba, os.path.join(tex, "glow.png"))
    # 预览图（放大 16 倍）
    big = np.repeat(np.repeat(rgba, 16, 0), 16, 1)
    encode_png(big, os.path.join(OUT, "glow16_preview.png"))

    with open(os.path.join(work, "pack.mcmeta"), "w", encoding="utf-8") as f:
        f.write(
            '{\n  "pack": {\n'
            f'    "pack_format": {PACK_FORMAT},\n'
            '    "description": "Glowing diamond particles 16x16"\n'
            "  }\n}\n"
        )

    out = os.path.join(OUT, "glow_diamond16.zip")
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for r, _d, files in os.walk(work):
            for fn in files:
                p = os.path.join(r, fn)
                z.write(p, os.path.relpath(p, work).replace(os.sep, "/"))
    print(out, os.path.getsize(out), "bytes")
    print("preview:", os.path.join(OUT, "glow16_preview.png"))


if __name__ == "__main__":
    main()
