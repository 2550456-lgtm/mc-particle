# particle-instanced · 视频粒子墙

把视频渲染成 Minecraft 里的粒子墙：**921,600 个粒子，一次 draw call**。

---

## 当前版本：视频模式

| 参数 | 值 |
|---|---|
| 网格 | 1280 × 720 = 921,600 粒子 |
| 墙宽 | 40 格（高 22.5 格） |
| 距原点 | z = -18 |
| 粒子边长 | 像素间距 × 1.32 |
| 位置抖动 | ±12.5% 间距 |
| 尺寸抖动 | ±17.5% |
| 边缘柔化 | 外侧 25%（约 1 像素） |
| 帧率 | 12 fps |
| 帧数 | 由 op.rgb 文件大小自动推导（当前 1106 帧 / 92 秒） |

## 命令

| 命令 | 作用 |
|---|---|
| `/start` | 从头开始播放 |
| `/run` | 继续播放（保留进度） |
| `/stop` | 暂停（画面保留） |
| `/end` | 结束并隐藏 |

---

## 为什么粒子位置和大小是固定的

设计如此：**位置/大小写死在静态 VBO 里，只有颜色每帧更新**。

```
静态 VBO  位置 xyz + 大小 = 16 B × 921,600 = 14.7 MB   上传一次
动态 VBO  颜色 rgb        = 3 B × 921,600 = 2.76 MB    每帧上传
```

好处：

```
· 每帧 CPU 只做一次 read + 一次 glBufferSubData
· 顶点完全由 GPU 用 gl_VertexID 生成
· 921,600 粒子的动画只花 2.76 MB/帧带宽
```

如果粒子位置每帧都变，需要额外 33 MB/帧的位置数据，而且画面会糊成一团 ——
视频是"逐像素采样"，粒子一旦移动就无法对应原画面的像素。

---

## 素材准备

```bash
ffmpeg -y -i 你的视频.mp4 \
  -vf "scale=1280:720:flags=lanczos" \
  -r 12 -f rawvideo -pix_fmt rgb24 \
  "版本目录\particleImages\op.rgb"
```

- `-r 12` 抽帧率（须与代码 `FRAME_FPS` 一致，否则播放速度不对）
- `scale` 必须是 1280:720
- 帧数不用管，模组按 `文件大小 / 每帧字节数` 自动推导

---

## 实现要点

```
① 静态 VBO：位置+大小，VAO 里 divisor=1
② 动态 VBO：颜色 3 字节归一化，每帧 glBufferSubData
③ 帧数据用 FileChannel 按帧读入复用缓冲（文件可达数 GB，
   不能整体 map —— Java 单次映射上限 2 GB）
④ 偏移必须用 long：frame * FRAME_BYTES 会超过 Integer.MAX_VALUE
```

## 硬性依赖

**ThreatenGL 2.0.4+** —— MC 1.21.1 是 GL 3.2，实例化需要 3.3 的
`glVertexAttribDivisor`，缺失会直接 JVM abort。模组已内置版本探测。

---

## 附带功能：纯黑世界

```
WorldRendererMixin  取消 renderSky（日月星辰）和 renderClouds
ClientWorldMixin    getSkyColor → 黑色（雾色 + 背景清屏色）
```

白天地面仍被阳光照亮，要全黑再加：

```
/gamerule doDaylightCycle false
/time set midnight
```

---

## 重新编译

```bash
gradle build --no-daemon --init-script 编译用-init.gradle
```

Gradle 8.12+、JDK 21。init 脚本提供本地库仓库 + 阿里云镜像（国内必需）。

---

## 已知限制

```
· 只支持 1.21.1
· 分辨率/墙宽/帧率写死在代码里
· 墙固定在世界坐标，不跟随玩家
· 墙宽超过 100 格时填充率过高，实测 320 格会拖死显卡驱动
```

---

## 每帧粒子抖动（v1.2）

每颗粒子每帧的位置和大小都不同，用整数哈希在**着色器内**生成，不增加任何上传数据。

```glsl
uniform int uFrame;                       // 帧号

uint pcg(uint v) {                        // PCG 哈希
    uint state = v * 747796405u + 2891336453u;
    uint word = ((state >> ((state >> 28u) + 4u)) ^ state) * 277803737u;
    return (word >> 22u) ^ word;
}

uint base = uint(gl_InstanceID);
uint f    = uint(uFrame);
float h1 = rnd(base ^ (f * 0x9E3779B9u));
float h2 = rnd((base + 0x1234u) ^ (f * 0x85EBCA6Bu));
float h3 = rnd((base + 0x5678u) ^ (f * 0xC2B2AE35u));

vec2  jit  = (vec2(h1, h2) - 0.5) * iSize * 0.18;   // 位置 ±18% 尺寸
float sMul = 1.0 + (h3 - 0.5) * 0.15;                // 大小 ±7.5%
```

**为什么必须用整数哈希**：早期版本用 `hash(id) = fract(sin(id*12.9898)*43758.5)`，
当 id 到 92 万时 `id*12.9898 ≈ 1.2e7`，超出 float32 的 24 位尾数精度，
`sin()` 结果在相邻 id 间几乎相同 → 所有粒子抖动同步。
整数位运算没有这个问题。

幅度参考：

| 系数 | 观感 |
|---|---|
| 0.10 | 几乎静止，只有轻微"呼吸" |
| **0.18** | **当前：细碎颤动，图像稳定** |
| 0.35 | 明显晃动 |
| 0.60 | 接近粒子雾 |
