"""图片 → NebulaFX .nbl（单帧、静态粒子墙）

NBL v1 格式（Little-Endian）：
    48B 文件头 | 纹理块 | 帧索引表 | 关键帧表 | 帧数据块(Zstd)

用法：
    python image2nbl.py 输入.png 输出.nbl [横向像素数] [墙宽格数]

例：
    python image2nbl.py still.png still.nbl 640 25.6
"""
import struct
import sys

import zstandard
from PIL import Image

TEXTURE = "minecraft:textures/particle/glow.png"


def build(path_in, path_out, cols=640, wall_w=25.6, fps=30, size_scale=1.5):
    img = Image.open(path_in).convert("RGBA")
    rows = max(1, round(cols * img.height / img.width))
    img = img.resize((cols, rows), Image.LANCZOS)

    step = wall_w / cols                       # 每像素间隔（格）
    half_w = wall_w / 2.0
    half_h = step * rows / 2.0
    size_u16 = max(1, min(65535, int(step * size_scale * 100)))  # 大小 ×100

    px = img.load()
    xs, ys, zs = [], [], []
    rs, gs, bs, als = [], [], [], []
    sizes, tids, seqs, ids = [], [], [], []

    n = 0
    for y in range(rows):
        for x in range(cols):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            xs.append(-half_w + x * step)
            ys.append(half_h - y * step)
            zs.append(0.0)
            rs.append(r); gs.append(g); bs.append(b); als.append(255)
            sizes.append(size_u16)
            tids.append(0); seqs.append(0); ids.append(n)
            n += 1

    # ---- I-Frame payload（SoA）----
    payload = bytearray()
    payload += struct.pack("<%df" % n, *xs)
    payload += struct.pack("<%df" % n, *ys)
    payload += struct.pack("<%df" % n, *zs)
    payload += bytes(rs) + bytes(gs) + bytes(bs) + bytes(als)
    payload += struct.pack("<%dH" % n, *sizes)
    payload += bytes(tids) + bytes(seqs)
    payload += struct.pack("<%di" % n, *ids)

    chunk = struct.pack("<BI", 0, n) + bytes(payload)       # type=0, count
    cctx = zstandard.ZstdCompressor(level=3)
    comp = cctx.compress(chunk)                              # 每帧独立上下文

    # ---- 头部 ----
    tex = TEXTURE.encode("utf-8")
    header_len = 48
    tex_len = 2 + len(tex) + 2
    frame_idx_len = 8 + 4
    key_len = 4 + 4
    data_off = header_len + tex_len + frame_idx_len + key_len

    out = bytearray()
    out += b"NEBULAFX"
    out += struct.pack("<H", 1)             # version
    out += struct.pack("<H", fps)           # targetFPS
    out += struct.pack("<I", 1)             # totalFrames
    out += struct.pack("<H", 1)             # textureCount
    out += struct.pack("<H", 3)             # attributes: alpha|size
    out += struct.pack("<3f", -half_w, -half_h, -0.5)   # bbox min
    out += struct.pack("<3f", half_w, half_h, 0.5)      # bbox max
    out += b"\x00\x00\x00\x00"              # reserved

    out += struct.pack("<H", len(tex)) + tex + bytes([1, 1])
    out += struct.pack("<QI", data_off, len(comp))
    out += struct.pack("<I", 1) + struct.pack("<I", 0)
    out += comp

    with open(path_out, "wb") as f:
        f.write(out)

    print(f"网格      {cols} x {rows}")
    print(f"粒子数    {n:,}")
    print(f"墙尺寸    {wall_w:.1f} x {step*rows:.1f} 格")
    print(f"粒子大小  {size_u16/100:.3f} 格")
    print(f"未压缩    {len(chunk)/1024/1024:.1f} MB")
    print(f"压缩后    {len(comp)/1024/1024:.1f} MB  -> {path_out}")
    return n


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 2:
        print(__doc__)
        sys.exit(1)
    cols = int(a[2]) if len(a) > 2 else 640
    wall = float(a[3]) if len(a) > 3 else 25.6
    build(a[0], a[1], cols, wall)
