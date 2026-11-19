# particle-instanced · 定稿说明

把静态图片渲染成粒子墙的 Minecraft 1.21.1 Fabric 客户端模组。
**92 万粒子，一次 draw call，CPU 不生成顶点。**

---

## 最终参数（v1.0 定稿）

| 参数 | 值 | 说明 |
|---|---|---|
| `LOD_COLS` | `{1280}` | 1280×720 = 921,600 粒子 |
| `WALL_W` | `40.0f` | 墙宽 40 格（高约 22.5 格） |
| `WALL_Z` | `-18.0f` | 距世界原点的 z 距离 |
| `SIZE_RATIO` | `1.32f` | 粒子边长 = 像素间距 × 1.32 |
| `POS_JITTER` | `0.25f` | 位置抖动 ±12.5% 间距（抑制摩尔纹） |
| `SIZE_JITTER` | `0.35f` | 尺寸抖动 ±17.5%（自然层次） |
| 边缘过渡 | `smoothstep(0.75, 1.0, d)` | 外侧 25% 柔化，约 1 像素 |

---

## 原理

```
① 生成（一次）
   图片 → 双线性降采样到 1280×720
   每像素一条实例：位置 xyz(12B) + 颜色 rgba(16B) + 大小(4B) = 32B
   → 上传 VBO（STATIC_DRAW）

② 渲染（每帧）
   glDrawArraysInstanced(GL_TRIANGLE_STRIP, 0, 4, 921600)
   顶点着色器：gl_VertexID 的 0..3 → 四个角
   片元着色器：|x|+|y|<=1 画菱形
```

---

## 硬性依赖：ThreatenGL 2.0.4+

MC 1.21.1 默认是 OpenGL **3.2** 上下文，而实例化需要 **3.3** 的 `glVertexAttribDivisor`。
缺失时调用会直接 JVM abort（Java 的 catch 拦不住）：

```
FATAL ERROR: No context is current ... glVertexAttribDivisor
```

模组已内置版本探测：GL < 3.3 时打印警告并跳过，不会崩溃。

启动正常时日志应为：

```
[pws-inst] GL_VERSION = 4.6.0 NVIDIA ...
[pws-inst] LOD0 cols=1280 instances=921600
```

---

## 摩尔纹调参经验（重要）

这是本次开发踩得最久的坑，结论按有效性排序：

| 手段 | 效果 | 代价 |
|---|---|---|
| **降低列数**（1280→640，每粒从 2px 变 4px） | ★★★★★ 最有效 | 清晰度减半 |
| **位置抖动 POS_JITTER** | ★★★★ 破坏规则格点，消拍频 | 观感变"散" |
| 边缘柔化（smoothstep 25%） | ★★★ 消硬边锯齿 | 略糊 |
| 尺寸抖动 | ★★ 打散规律感 | 无 |
| LOD 按距离切档 | ★ 实测几乎无效 | 切换跳变 |

**根本原因**：规则格点在透视投影下，屏幕间距连续变化，与像素栅格产生拍频。
只要粒子投影 <= 2 像素且排列规则，就一定会出现同心弧条纹。

当前 1280 版是"清晰度"和"纹路"的平衡点 —— 位置抖动 0.25 刚好压住条纹又不至于太散。

---

## 附带功能：纯黑世界

```
WorldRendererMixin  取消 renderSky（太阳/月亮/星星）和 renderClouds
ClientWorldMixin    getSkyColor 返回黑色（雾色 + 背景清屏色）
```

白天地面仍会被阳光照亮，要全黑还需：

```
/gamerule doDaylightCycle false
/time set midnight
```

---

## 安装

```
① Fabric Loader 0.17+ / Fabric API
② ThreatenGL 2.0.4+（必需）
③ jar 放进 mods\
④ 图片放 版本目录\particleImages\still.png
⑤ 进存档，站在世界原点附近朝北看
```

> 图片路径相对**版本目录**（工作目录），不是存档目录。

---

## 重新编译

需要 Gradle 8.12+、JDK 21：

```bash
gradle build --no-daemon --init-script 编译用-init.gradle
```

`编译用-init.gradle` 做两件事：本地 `.minecraft\libraries` 当 maven 仓库、补阿里云镜像
（国内直连 `libraries.minecraft.net` 会超时）。

---

## 已知限制

```
· 只支持 1.21.1
· 图片路径/分辨率/尺寸全部写死，改需重新编译
· 墙固定在世界坐标，不跟随玩家
· 墙宽超过 100 格时填充率过高，可能导致显卡驱动挂死（实测 320 格必死）
```

---

## 文件清单

```
particle-instanced-1.0.0.jar     成品
src/ParticleInstanced.java       主实现
src/WorldRendererMixin.java      去天空/云
src/ClientWorldMixin.java        天空色置黑
src/fabric.mod.json              元数据
src/particle-instanced.mixins.json
build.gradle / gradle.properties
编译用-init.gradle                国内编译必备
```
