# mc-particle

把**图片 / 视频**变成 Minecraft 里的**粒子墙**。

配套模组：[AnotherColorBlock (ParticleEx)](https://github.com/noone89A/AnotherColorBlock) · Fabric 1.21.1

---

## 目录

```
mc-particle/
├─ app/particle-wall-studio.html   主工具（单文件网页，双击即用）
└─ tools/                          生成器与辅助脚本（Python 3.10+，仅需 numpy）
```

## 主工具：粒子墙工作台

浏览器打开 `app/particle-wall-studio.html`，无需安装、无需联网。

![工作台](docs/screenshot.png)

- 拖入图片 → 实时粒子点阵预览（纯黑背景，保持原图长宽比）
- **亮度** 0.2–2.0：模拟游戏内光照
- **清晰度** 32–480：横向粒子数，决定细节
- **疏密** 2–24：每方块粒子数 `dpb`，越大越密、墙越小
- **放大预览** 1–12×（滚轮也可）：像素级放大，检查菱形边缘和缝隙
- 一键：复制 `/particleex` 命令 / 下载数据包 / 导出预览图（不透明黑底）

## 游戏侧前置

| 项 | 放到 |
|---|---|
| `AnotherColorBlock-*.jar` + `fabric-api-*.jar` | `.minecraft\versions\<版本>\mods\` |
| 发光菱形贴图 `star_particles.zip` | 同目录 `resourcepacks\`（启用） |
| 粒子图片 | 同目录 `particleImages\` |

## 游戏内流程

墙**固定朝北**（`-Z`），所以光源平面和粒子平面天然对齐，不需要转身。

```mcfunction
/particleex clearparticle
/fill ~-15 ~-14 ~-19 ~15 ~14 ~-19 minecraft:light
/particleex image minecraft:glow ~ ~2 ~-18 chibi.png 0.58 0 0 0 not 16 0 0 0 -1
```

三条分别：清场 / 铺隐形光源 / 画墙。装数据包后只要 `/function vid:wall` 一条。

看不到墙就转身朝北 —— 它在 `-Z` 方向 18 格。

## 参数含义（读模组源码确认）

| 参数 | 含义 |
|---|---|
| `缩放` | 图片缩放倍数。`1.0` = 原图；粒子数 = (宽×缩放) × (高×缩放) |
| `dpb` | 每方块粒子数。**越大越密、墙越小**；墙宽 = 图宽×缩放 ÷ dpb |
| `age` | `-1` = 永久存在，不会淡出 |

## 踩过的坑

| 现象 | 原因 |
|---|---|
| 720p（`缩放 1.0`，92 万粒子）只渲染出一部分 | 触到模组内部上限，实际可用约 `缩放 0.58`（360p，15 万粒子） |
| 粒子发暗 | 粒子亮度 = 所在位置光照等级；用 `minecraft:light` 隐形光源铺在墙后 |
| `end_rod` 全是白的 | 它自己管颜色动画，模组染色只对 `SingleQuadParticle` 生效 |
| `dust` 是圆点 | 形状由贴图决定，需替换 `generic_*` / `glow.png` |



## 粒子数上限（10 万+ 的关键）

模组默认只保留 **65,536** 个粒子，超出的被丢弃 —— 表现是**图片被压扁成一条横带**，很容易误判成"长宽比算错"。

改 `config/particleex.json`（**必须重启游戏**才生效）：

```json
{
  "maxParticleCount": 300000,
  "ParallelParticleUpdate": true
}
```

| 字段 | 说明 |
|---|---|
| `maxParticleCount` | 粒子队列上限。要 23 万粒子就写 30 万 |
| `ParallelParticleUpdate` | 每帧 tick 用并行流，粒子多时减少卡顿 |

改完重启，`/function vid:gal` 之类的大图才会完整显示。

## 数据包的两个坑（1.21 实测）


| 坑 | 现象 | 正确做法 |
|---|---|---|
| 函数文件里带前导 `/` | `/function` 报"未知的函数"，日志写 `Failed to load function` | 每行**不要**写 `/` |
| 目录写成 `functions`（复数） | 同上 | 必须是 `data/<ns>/function/`（**单数**） |

这两条是 1.21 的行为，和网上 1.16 时代的教程正好相反。

## tools/

| 脚本 | 作用 |
|---|---|
| `image2wall.py` | 图片 → 数据包（原版 `particle` 命令，相对坐标） |
| `mcvideo.py` | 视频 → 数据包 / 帧数据（含调色板量化、矩形合并） |
| `make_glow16.py` | 生成 16×16 发光菱形贴图资源包 |
| `make_testcard.py` | 生成 1280×720 测试卡 |
| `nbtlib.py` | 手写的最小 NBT 编解码器 |
| `pack_datapack.py` | 打 zip（强制正斜杠，规避 `Compress-Archive` 的坑） |

## License

工具代码 MIT。模组本身为 GPL-3.0，本仓库不含其代码。
