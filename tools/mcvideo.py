"""视频 → Minecraft 粒子墙：生成管线。

流程：ffmpeg 解码 → area 缩放成网格 → 调色板量化 → 行游程合并 → 发射指令

产物：
  build/<name>/datapack/  1.21.1 数据包，/function vid:fNNNN 画单帧
  build/<name>/preview/   粒子模拟预览 mp4 + 对比图
  build/<name>/stats.json 指令条数 / 体积 / 每帧统计

用法：
  python tools/mcvideo.py --input X.mp4 --grid 160x90 --colors 16 --pitch 0.25
"""
import argparse
import json
import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


# ----------------------------------------------------------------- 解码


def load_frames(path, w, h):
    """用 ffmpeg 直接缩放到目标网格（area 滤镜 = 区域平均）。"""
    cmd = [
        "ffmpeg", "-v", "error", "-i", path,
        "-vf", f"scale={w}:{h}:flags=area",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:2000])
    buf = np.frombuffer(p.stdout, np.uint8)
    n = buf.size // (w * h * 3)
    return buf[: n * w * h * 3].reshape(n, h, w, 3)


# ----------------------------------------------------------------- 调色板


def kmeans_palette(pixels, k, iters=30, seed=7, sample_cap=120000):
    rng = np.random.default_rng(seed)
    flat = pixels.reshape(-1, 3).astype(np.float32)
    if len(flat) > sample_cap:
        flat = flat[rng.choice(len(flat), sample_cap, replace=False)]

    centers = np.array([flat[rng.integers(len(flat))]], np.float32)
    for _ in range(k - 1):  # k-means++ 初始化
        d = ((flat[:, None, :] - centers[None]) ** 2).sum(-1).min(1)
        tot = d.sum()
        probs = np.full(len(flat), 1.0 / len(flat)) if tot <= 0 else d / tot
        centers = np.vstack([centers, flat[rng.choice(len(flat), p=probs)]])

    for _ in range(iters):
        d = ((flat[:, None, :] - centers[None]) ** 2).sum(-1)
        lab = d.argmin(1)
        for j in range(k):
            m = lab == j
            if m.any():
                centers[j] = flat[m].mean(0)
    return np.clip(centers, 0, 255)


def quantize(frames, palette):
    out = np.empty(frames.shape[:3], np.uint8)
    pal = palette[None, None, :, :]
    for i in range(frames.shape[0]):
        d = ((frames[i].astype(np.float32)[:, :, None, :] - pal) ** 2).sum(-1)
        out[i] = d.argmin(-1)
    return out


# ----------------------------------------------------------------- 合并


def row_runs(row):
    """把一行调色板索引切成等值游程：[(start, length, color_index), ...]"""
    if len(row) == 0:
        return []
    change = np.flatnonzero(np.diff(row) != 0) + 1
    starts = np.concatenate(([0], change))
    ends = np.concatenate((change, [len(row)]))
    return [(int(s), int(e - s), int(row[s])) for s, e in zip(starts, ends)]


def frame_runs(idx):
    return [row_runs(idx[r]) for r in range(idx.shape[0])]


def frame_rects(idx):
    """贪心矩形分解：同色相邻像素合并成矩形，一条指令画一整块。

    按行游程只能横向合并；这里再纵向合并，实测能再省 30~40% 指令。
    """
    h, w = idx.shape
    covered = np.zeros((h, w), bool)
    rects = []
    for y in range(h):
        x = 0
        while x < w:
            if covered[y, x]:
                x += 1
                continue
            c = idx[y, x]
            x2 = x
            while x2 + 1 < w and idx[y, x2 + 1] == c and not covered[y, x2 + 1]:
                x2 += 1
            y2 = y
            while y2 + 1 < h:
                span = idx[y2 + 1, x : x2 + 1]
                if np.all(span == c) and not covered[y2 + 1, x : x2 + 1].any():
                    y2 += 1
                else:
                    break
            covered[y : y2 + 1, x : x2 + 1] = True
            rects.append((int(x), int(y), int(x2 - x + 1), int(y2 - y + 1), int(c)))
            x = x2 + 1
    return rects


# ----------------------------------------------------------------- 发射


def fmt_color(rgb):
    return ",".join(f"{c/255:.2f}" for c in rgb)


def frame_commands(idx, palette, cfg):
    """严格点阵：一格一条指令，count=1、扩散全 0 —— 粒子钉死在格点上。

    这是"整齐矩阵"的唯一做法：只要用 count>1 加扩散盒，位置就是随机的，
    出来一定是雾状颗粒，不可能是点阵。
    """
    h, w = idx.shape
    ox, oy, oz = cfg["origin"]
    pitch = cfg["pitch"]
    left = ox - w * pitch / 2
    top = oy + h * pitch / 2
    scale = cfg["dot_blocks"] / cfg["sprite_blocks"]

    # 位置和颜色都只有有限种，先建表，避免每条指令都做浮点格式化
    xstr = [f"{left + (c + 0.5) * pitch:.2f}" for c in range(w)]
    ystr = [f"{top - (r + 0.5) * pitch:.2f}" for r in range(h)]
    zstr = f"{oz:.2f}"
    prefix = [
        f"particle dust{{color:[{fmt_color(rgb)}],scale:{scale:.2f}}} " for rgb in palette
    ]
    tail = f" {zstr} 0 0 0 0 1"

    cmds = []
    for r in range(h):
        pre = prefix
        y = ystr[r]
        row = idx[r]
        for c in range(w):
            cmds.append(pre[row[c]] + xstr[c] + " " + y + tail)
    return cmds


# ----------------------------------------------------------------- 数据包


def write_datapack(root, frame_cmds, cfg):
    fn_dir = os.path.join(root, "data", "vid", "function")
    os.makedirs(fn_dir, exist_ok=True)
    os.makedirs(os.path.join(root, "data", "minecraft", "tags", "function"), exist_ok=True)

    with open(os.path.join(root, "pack.mcmeta"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "pack": {
                    "pack_format": 94,
                    "description": "mc-particle video wall",
                    "supported_formats": {"min_inclusive": 48, "max_inclusive": 99},
                }
            },
            f,
            indent=2,
        )

    n = len(frame_cmds)
    hold = cfg.get("hold_ticks", 0)
    for i, cmds in enumerate(frame_cmds):
        with open(os.path.join(fn_dir, f"f{i:04d}.mcfunction"), "w", encoding="utf-8") as f:
            f.write("\n".join(cmds) + "\n")
        if hold:
            # h####：画这一帧并每 hold tick 重画一次，让画面一直亮着（粒子只活 0.7 秒）
            with open(os.path.join(fn_dir, f"h{i:04d}.mcfunction"), "w", encoding="utf-8") as f:
                f.write(f"function vid:f{i:04d}\n")
                f.write(f"schedule function vid:h{i:04d} {hold}t\n")

    step = cfg["step_ticks"]
    with open(os.path.join(fn_dir, "play.mcfunction"), "w", encoding="utf-8") as f:
        f.write(
            "scoreboard players set #t vid.t 0\n"
            "scoreboard players set #run vid.run 1\n"
            "schedule function vid:tick 1t\n"
        )

    lines = ["scoreboard players add #t vid.t 1"]
    for i in range(n):
        lines.append(f"execute if score #t vid.t matches {i*step+1} run function vid:f{i:04d}")
    lines.append(f"execute if score #t vid.t matches {n*step+1} run function vid:stop")
    lines.append("execute if score #run vid.run matches 1 run schedule function vid:tick 1t")
    with open(os.path.join(fn_dir, "tick.mcfunction"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    with open(os.path.join(fn_dir, "stop.mcfunction"), "w", encoding="utf-8") as f:
        f.write("scoreboard players set #run vid.run 0\n")

    with open(os.path.join(fn_dir, "load.mcfunction"), "w", encoding="utf-8") as f:
        f.write(
            "scoreboard objectives add vid.t dummy\n"
            "scoreboard objectives add vid.run dummy\n"
        )
    with open(
        os.path.join(root, "data", "minecraft", "tags", "function", "load.json"),
        "w",
        encoding="utf-8",
    ) as f:
        json.dump({"values": ["vid:load"]}, f, indent=2)

    return n


# ----------------------------------------------------------------- 预览


def _disc_weights(radius):
    """点阵用光斑：近似硬边圆片，只在最外圈做一点抗锯齿。

    点阵里每个点几乎不重叠，渐变椭圆会让每个点变成半透明小雀斑、整幅图发暗。
    这里 w 在 d<=0.9 时恒为 1，最后 10% 半径快速衰减。
    """
    out = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            d2 = (dx * dx + dy * dy) / max(radius * radius, 1e-6)
            if d2 > 1.0:
                continue
            out.append((dy, dx, min(1.0, 9.0 * (1.0 - d2))))
    return out


def simulate_frame(idx, palette, cfg, out_w, out_h):
    """严格点阵的模拟：一格一个点，落在格心，无抖动、无随机。

    真实 dust 粒子是软圆片、alpha 混合，重叠只遮挡不加亮，
    所以累计覆盖权重后解 alpha，颜色取加权平均。
    """
    h, w = idx.shape
    pitch = cfg["pitch"]
    px_per_block = out_w / (w * pitch)

    yy0 = ((np.arange(h) + 0.5) / h * out_h).astype(np.int32)
    xx0 = ((np.arange(w) + 0.5) / w * out_w).astype(np.int32)
    YY, XX = np.meshgrid(yy0, xx0, indexing="ij")
    cs = palette[idx].astype(np.float32) / 255.0  # (h,w,3)

    radius = max(1, int(round(cfg["dot_blocks"] * px_per_block / 2)))
    kern = cfg.get("kernel")
    if kern is None:
        kern = _disc_weights(radius)
    wsum = np.zeros((out_h, out_w), np.float32)
    csum = np.zeros((out_h, out_w, 3), np.float32)
    for dy, dx, wgt in kern:
        y = YY + dy
        x = XX + dx
        m = (y >= 0) & (y < out_h) & (x >= 0) & (x < out_w)
        np.add.at(wsum, (y[m], x[m]), wgt)
        np.add.at(csum, (y[m], x[m]), cs[m] * wgt)

    alpha = 1.0 - np.exp(-wsum * 4.0)
    col = np.where(wsum[..., None] > 0, csum / np.maximum(wsum[..., None], 1e-6), 0.0)
    out = col * alpha[..., None]
    return np.clip(out * 255, 0, 255).astype(np.uint8)


def encode_video(frames, path, w, h, fps):
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", path,
    ]
    p = subprocess.run(cmd, input=frames.tobytes(), capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:2000])


def upscale(idx, palette, w, h):
    img = palette[idx].astype(np.uint8)
    return np.repeat(np.repeat(img, h // img.shape[0], 0), w // img.shape[1], 1)


def contact_sheet(orig, idx, palette, cfg, path, cols=4):
    T = len(idx)
    picks = np.linspace(0, T - 1, cols).astype(int)
    oh, ow = orig.shape[1:3]
    rows = []
    for kind in ("orig", "quant", "sim"):
        row = []
        for p in picks:
            if kind == "orig":
                im = orig[p]
            elif kind == "quant":
                im = upscale(idx[p], palette, ow, oh)
            else:
                im = simulate_frame(idx[p], palette, cfg, ow, oh)
            row.append(im)
        rows.append(np.concatenate(row, axis=1))
    sheet = np.concatenate(rows, axis=0)
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{sheet.shape[1]}x{sheet.shape[0]}", "-i", "-",
        "-frames:v", "1", path,
    ]
    p = subprocess.run(cmd, input=sheet.tobytes(), capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:2000])


# ----------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--name", default="galaxy")
    ap.add_argument("--grid", default="160x90")
    ap.add_argument("--colors", type=int, default=16)
    ap.add_argument("--pitch", type=float, default=0.15)
    ap.add_argument("--fill", type=float, default=1.2,
                    help="光斑直径/格距；<1 会露出黑底，1.1~1.3 连续")
    ap.add_argument("--sprite-blocks", type=float, default=0.2,
                    help="dust scale=1 时精灵实际边长（格），需游戏内标定")
    ap.add_argument("--jitter-y", type=float, default=0.5,
                    help="纵向抖动幅度（占格距比例），打散规则行结构")
    ap.add_argument("--hold-ticks", type=int, default=15,
                    help="hold 函数的重绘间隔；0=不生成 hold 函数")
    ap.add_argument("--density", type=float, default=1.5,
                    help="每格发射多少粒子；越高洞越少，但越糊越贵")
    ap.add_argument("--origin", default="0,64,0")
    ap.add_argument("--step-ticks", type=int, default=20)
    ap.add_argument("--preview-gain", type=float, default=6.0)
    ap.add_argument("--dump-frame", type=int, default=None)
    ap.add_argument("--out", default=os.path.join(HERE, "..", "..", "test", "build"))
    args = ap.parse_args()

    gw, gh = (int(x) for x in args.grid.split("x"))
    ox, oy, oz = (float(x) for x in args.origin.split(","))
    cfg = dict(
        grid_w=gw, grid_h=gh, pitch=args.pitch,
        dot_blocks=args.fill * args.pitch,
        sprite_blocks=args.sprite_blocks,
        origin=(ox, oy, oz), step_ticks=args.step_ticks,
        preview_gain=args.preview_gain,
        density=args.density, jitter_y=args.jitter_y, hold_ticks=args.hold_ticks,
    )
    cfg["scale"] = cfg["dot_blocks"] / cfg["sprite_blocks"]

    root = os.path.join(args.out, args.name)
    dp = os.path.join(root, "datapack", "mcvideo")
    pv = os.path.join(root, "preview")
    os.makedirs(pv, exist_ok=True)

    print(f"[1/5] 解码 {args.input} → {gw}x{gh}")
    frames = load_frames(args.input, gw, gh)
    print(f"      {len(frames)} 帧")

    print(f"[2/5] 量化 {args.colors} 色")
    palette = kmeans_palette(frames, args.colors)
    idx = quantize(frames, palette)

    print("[3/5] 生成点阵指令")
    frame_cmds = [frame_commands(idx[i], palette, cfg) for i in range(len(idx))]
    per_frame = [len(c) for c in frame_cmds]
    print(
        f"      每帧指令 {min(per_frame)}~{max(per_frame)}，平均 {sum(per_frame)/len(per_frame):.0f}"
    )

    print("[4/5] 写数据包")
    n = write_datapack(dp, frame_cmds, cfg)
    print(f"      {n} 帧函数")
    np.savez_compressed(os.path.join(root, "frames.npz"), idx=idx, palette=palette)

    print("[5/5] 预览")
    ow, oh = 1280, 720
    sim = np.stack([simulate_frame(idx[i], palette, cfg, ow, oh) for i in range(len(idx))])
    encode_video(sim, os.path.join(pv, "particles.mp4"), ow, oh, 30)
    contact_sheet(frames, idx, palette, cfg, os.path.join(pv, "contact.png"))

    if args.dump_frame is not None:
        k = min(args.dump_frame, len(idx) - 1)
        for tag, im in (
            ("orig", frames[k]),
            ("quant", upscale(idx[k], palette, ow, oh)),
            ("sim", sim[k]),
        ):
            p = os.path.join(pv, f"frame{k:04d}_{tag}.png")
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                 "-s", f"{im.shape[1]}x{im.shape[0]}", "-i", "-", "-frames:v", "1", p],
                input=np.ascontiguousarray(im).tobytes(), capture_output=True,
            )
            print(f"      {p}")

    dp_size = sum(
        os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(dp) for f in fs
    )
    stats = dict(
        source=args.input,
        grid=[gw, gh],
        colors=args.colors,
        frames=len(idx),
        particles_per_frame=gw * gh,
        commands_per_frame=dict(min=min(per_frame), max=max(per_frame),
                                avg=round(sum(per_frame) / len(per_frame), 1)),
        wall_blocks=[round(gw * args.pitch, 2), round(gh * args.pitch, 2)],
        datapack_bytes=dp_size,
        step_ticks=args.step_ticks,
        scale=round(cfg["scale"], 3),
        dot_blocks=round(cfg["dot_blocks"], 3),
        capture_seconds=round(len(idx) * args.step_ticks / 20, 1),
        palette=[[int(v) for v in c] for c in palette],
    )
    with open(os.path.join(root, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(json.dumps(stats["commands_per_frame"], ensure_ascii=False))
    print(f"OK {root}")


if __name__ == "__main__":
    main()

