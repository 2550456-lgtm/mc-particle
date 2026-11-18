"""生成一张 1280x720 的测试卡，用来判断粒子墙的对齐、颜色和密度。

  python tools/make_testcard.py

输出 out/testcard_720p.png，并复制到 1.21.1-Fabric 的 particleImages/。
"""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "test", "out")
W, H = 1280, 720


def base():
    img = np.zeros((H, W, 3), np.uint8)
    # 上半：8 条标准彩条
    bars = [(255,255,255),(255,255,0),(0,255,255),(0,255,0),
            (255,0,255),(255,0,0),(0,0,255),(20,20,20)]
    bw = W // len(bars)
    for i, c in enumerate(bars):
        img[0:250, i*bw:(i+1)*bw] = c
    # 中段：灰阶渐变（左->右）
    ramp = np.tile(np.linspace(0, 255, W, dtype=np.uint8), (90, 1))
    img[250:340, :, :] = ramp[..., None]
    # 中段：色彩渐变
    gy, gx = 0, 0
    seg = np.zeros((90, W, 3), np.uint8)
    t = np.linspace(0, 1, W)
    seg[..., 0] = (255 * (1 - t)).astype(np.uint8)
    seg[..., 1] = (255 * np.sin(np.pi * t)).astype(np.uint8)
    seg[..., 2] = (255 * t).astype(np.uint8)
    img[340:430] = seg
    # 下部：2px 棋盘 + 64px 网格
    yy, xx = np.mgrid[0:H-430, 0:W]
    cb = ((xx // 2 + yy // 2) % 2) * 60 + 40
    img[430:H, :, :] = cb[..., None].astype(np.uint8)
    for x in range(0, W, 64):
        img[430:H, x:x+1] = (255, 255, 255)
        img[430:H, max(0, x-1):max(1, x)] = (255, 255, 255)
    for y in range(430, H, 64):
        img[y:y+1, :] = (255, 255, 255)
    # 中心十字 + 圆
    cx, cy = W // 2, H // 2
    img[cy-2:cy+2, cx-160:cx+160] = (255, 0, 0)
    img[cy-160:cy+160, cx-2:cx+2] = (255, 0, 0)
    yy2, xx2 = np.mgrid[0:H, 0:W]
    r = np.hypot(xx2 - cx, yy2 - cy)
    ring = (r > 148) & (r < 152)
    img[ring] = (255, 0, 0)
    return img


def write_png(img, path):
    p = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{img.shape[1]}x{img.shape[0]}", "-i", "-", "-frames:v", "1", path],
        input=np.ascontiguousarray(img).tobytes(), capture_output=True,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:500])
    return path


def add_text(src, dst):
    font = r"C\:/Windows/Fonts/arial.ttf"
    if not os.path.exists(r"C:\Windows\Fonts\arial.ttf"):
        os.replace(src, dst)
        return dst
    vf = (
        f"drawtext=fontfile='{font}':text='1280x720  PARTICLE TEST':"
        f"x=(w-text_w)/2:y=h-70:fontsize=40:fontcolor=black:box=1:boxcolor=white@0.85:boxborderw=12"
    )
    p = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", src, "-vf", vf, "-frames:v", "1", dst],
        capture_output=True,
    )
    if p.returncode != 0:
        os.replace(src, dst)
    else:
        os.remove(src)
    return dst


def main():
    os.makedirs(OUT, exist_ok=True)
    tmp = os.path.join(OUT, "_tc_base.png")
    out = os.path.join(OUT, "testcard_720p.png")
    write_png(base(), tmp)
    add_text(tmp, out)
    print(out, os.path.getsize(out), "bytes")

    # 复制到游戏目录
    for prof in ("1.21.1-Fabric 0.20.1",):
        d = rf"D:\games\PCL\.minecraft\versions\{prof}\particleImages"
        if os.path.isdir(os.path.dirname(d)):
            os.makedirs(d, exist_ok=True)
            import shutil
            shutil.copy2(out, os.path.join(d, "testcard.png"))
            print("copied ->", os.path.join(d, "testcard.png"))


if __name__ == "__main__":
    main()
