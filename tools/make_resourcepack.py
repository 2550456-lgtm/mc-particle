"""生成一个资源包，把 dust 的 8 张软圆点贴图换成菱形。

dust 的定义在 assets/minecraft/particles/dust.json，引用的是
assets/minecraft/textures/particle/generic_0..7.png。
把这几张换成同尺寸的菱形，dust 粒子就整体变成菱形 —— 不需要改数据包，
也不需要自定义粒子类型。

用法：python tools/make_resourcepack.py
"""
import os
import struct
import subprocess
import sys
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# 1.21.11 资源包格式：resource_major = 75
PACK_FORMAT = 75
SIZE = 16


def diamond_rgba(size=SIZE):
    """白菱形 + 软边。dust 会用颜色去乘这张图，所以基色必须是纯白。"""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    cx = cy = (size - 1) / 2.0
    # 菱形距离：|dx| + |dy|
    d = (np.abs(xx - cx) + np.abs(yy - cy)) / (size / 2.0)
    alpha = np.clip((1.0 - d) * 4.0, 0.0, 1.0)  # 外缘 1/4 做抗锯齿
    rgba = np.zeros((size, size, 4), np.uint8)
    rgba[..., 0:3] = 255
    rgba[..., 3] = (alpha * 255).astype(np.uint8)
    return rgba


def write_png_via_ffmpeg(rgba, path):
    h, w = rgba.shape[:2]
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-i", "-",
        "-frames:v", "1", path,
    ]
    p = subprocess.run(cmd, input=np.ascontiguousarray(rgba).tobytes(), capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:800])


def main():
    root = os.path.join(HERE, "..", "..", "test", "build", "diamond_rp")
    tex = os.path.join(root, "assets", "minecraft", "textures", "particle")
    os.makedirs(tex, exist_ok=True)

    rgba = diamond_rgba()
    for i in range(8):
        write_png_via_ffmpeg(rgba, os.path.join(tex, f"generic_{i}.png"))

    with open(os.path.join(root, "pack.mcmeta"), "w", encoding="utf-8") as f:
        f.write(
            '{\n  "pack": {\n'
            f'    "pack_format": {PACK_FORMAT},\n'
            '    "description": "Diamond particles for the MC video wall"\n'
            "  }\n}\n"
        )

    # 用 python zipfile 打包（路径必须是正斜杠）
    out = os.path.join(HERE, "..", "..", "test", "build", "diamond_particles.zip")
    if os.path.exists(out):
        os.remove(out)
    import zipfile

    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for r, _d, files in os.walk(root):
            for fn in files:
                full = os.path.join(r, fn)
                z.write(full, os.path.relpath(full, root).replace(os.sep, "/"))
                n += 1

    print(f"packed {n} files -> {out} ({os.path.getsize(out)} bytes)")
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        bad = [x for x in names if "\\" in x]
        print("entries:", names[:3], "... backslash:", len(bad))
        assert not bad and "pack.mcmeta" in names


if __name__ == "__main__":
    main()
