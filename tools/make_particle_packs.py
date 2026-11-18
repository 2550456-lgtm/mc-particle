"""生成两种形状的 dust 贴图资源包：

  diamond_particles.zip  硬边实心菱形
  star_particles.zip     原版 glow 那种四角星（从 1.21.11.jar 里取原图）

两者都只是替换 assets/minecraft/textures/particle/generic_0..7.png，
所以 dust 的颜色（RGB）完全不受影响。
"""
import os
import subprocess
import sys
import zipfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PACK_FORMAT = 75
SIZE = 8
JAR = r"D:\games\PCL\.minecraft\versions\1.21.11\1.21.11.jar"


def hard_diamond(size=SIZE):
    """硬边菱形：只有最外 1 圈做 1px 抗锯齿，小尺寸下才不糊。"""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2.0
    d = (np.abs(xx - c) + np.abs(yy - c)) / (size / 2.0)
    alpha = np.where(d <= 0.86, 1.0, np.clip((1.0 - d) * 7.0, 0.0, 1.0))
    rgba = np.zeros((size, size, 4), np.uint8)
    rgba[..., 0:3] = 255
    rgba[..., 3] = (alpha * 255).astype(np.uint8)
    return rgba


def decode_png(path, w=16, h=16):
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-vf", "format=rgba", "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
        capture_output=True,
    )
    a = np.frombuffer(p.stdout, np.uint8)
    if a.size != w * h * 4:
        raise RuntimeError(f"{path}: got {a.size} bytes, want {w*h*4}")
    return a.reshape(h, w, 4)


def encode_png(rgba, path):
    h, w = rgba.shape[:2]
    p = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
         "-s", f"{w}x{h}", "-i", "-", "-frames:v", "1", path],
        input=np.ascontiguousarray(rgba).tobytes(), capture_output=True,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:500])


def build(rgba, out_zip, desc, workdir):
    root = os.path.join(workdir, "_pack")
    tex = os.path.join(root, "assets", "minecraft", "textures", "particle")
    os.makedirs(tex, exist_ok=True)
    for i in range(8):
        encode_png(rgba, os.path.join(tex, f"generic_{i}.png"))
    with open(os.path.join(root, "pack.mcmeta"), "w", encoding="utf-8") as f:
        f.write(
            '{\n  "pack": {\n'
            f'    "pack_format": {PACK_FORMAT},\n'
            f'    "description": "{desc}"\n'
            "  }\n}\n"
        )
    if os.path.exists(out_zip):
        os.remove(out_zip)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for r, _d, files in os.walk(root):
            for fn in files:
                full = os.path.join(r, fn)
                z.write(full, os.path.relpath(full, root).replace(os.sep, "/"))
    with zipfile.ZipFile(out_zip) as z:
        names = z.namelist()
        assert "pack.mcmeta" in names and not any("\\" in n for n in names)
    return out_zip


def main():
    out = os.path.join(HERE, "..", "..", "test", "build")
    tmp = os.path.join(out, "_tmp")
    os.makedirs(tmp, exist_ok=True)

    a = build(hard_diamond(), os.path.join(out, "diamond_particles.zip"),
              "Solid diamond particles", tmp)
    print("diamond ->", a, os.path.getsize(a), "bytes")

    # 从 jar 取原版 glow 贴图作为形状
    sys.path.insert(0, HERE)
    import zipfile as zf
    with zf.ZipFile(JAR) as z:
        with z.open("assets/minecraft/textures/particle/glow.png") as f:
            raw = f.read()
    src = os.path.join(tmp, "glow.png")
    with open(src, "wb") as f:
        f.write(raw)
    star = decode_png(src, 8, 8)
    b = build(star, os.path.join(out, "star_particles.zip"),
              "Four-point star particles (vanilla glow sprite)", tmp)
    print("star    ->", b, os.path.getsize(b), "bytes")

    # 预览图：两种形状各出 16px（实际大小）和 128px（放大）
    def scale(img, k):
        return np.repeat(np.repeat(img, k, 0), k, 1)

    canvas = np.zeros((256, 16 * 8 + 128 * 2 + 40, 4), np.uint8)
    canvas[..., 3] = 255
    x = 0
    for img in (hard_diamond(), star):
        canvas[:8, x:x+8] = img; x += 16
        canvas[:128, x:x+128] = scale(img, 16); x += 144
    encode_png(canvas, os.path.join(out, "shape_preview.png"))
    print("preview ->", os.path.join(out, "shape_preview.png"))


if __name__ == "__main__":
    main()
