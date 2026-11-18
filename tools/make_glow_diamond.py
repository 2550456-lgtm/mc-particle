"""把 minecraft:glow 的贴图换成菱形。

模组能给 SingleQuadParticle 染色，而 glow 是最普通的四边面片粒子 ——
所以换掉 glow.png 之后，minecraft:glow 就变成"能上色的菱形"，
不需要改粒子类型，也不需要动 dust 的那套贴图。

输出 build/glow_diamond.zip
"""
import os
import subprocess
import sys
import zipfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from make_particle_packs import hard_diamond  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "test", "build")
PACK_FORMAT = 34  # 1.21.1 资源包格式


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
    work = os.path.join(OUT, "_glowpack")
    tex = os.path.join(work, "assets", "minecraft", "textures", "particle")
    os.makedirs(tex, exist_ok=True)

    rgba = hard_diamond()               # 8x8 硬边菱形
    encode_png(rgba, os.path.join(tex, "glow.png"))

    with open(os.path.join(work, "pack.mcmeta"), "w", encoding="utf-8") as f:
        f.write(
            '{\n  "pack": {\n'
            f'    "pack_format": {PACK_FORMAT},\n'
            '    "description": "Diamond instead of four-point star (glow.png)"\n'
            "  }\n}\n"
        )

    out = os.path.join(OUT, "glow_diamond.zip")
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for r, _d, files in os.walk(work):
            for fn in files:
                p = os.path.join(r, fn)
                z.write(p, os.path.relpath(p, work).replace(os.sep, "/"))
    with zipfile.ZipFile(out) as z:
        assert "assets/minecraft/textures/particle/glow.png" in z.namelist()
    print(out, os.path.getsize(out), "bytes")


if __name__ == "__main__":
    main()
