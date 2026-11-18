# 模组补丁（1.21.1）

基于 [AnotherColorBlock](https://github.com/noone89A/AnotherColorBlock) 的 `1.21` 分支，
只改了一个文件：`ParticleMixin.java`。

## 补丁内容

### ① 静态粒子跳过 tick

```java
public void customTick() {
   if (this.exe == null && !this.customMove
         && this.velocityX == 0.0D && this.velocityY == 0.0D && this.velocityZ == 0.0D) {
      return;
   }
   ...
}
```

图片墙的粒子不移动、不衰减、无表达式，完全不需要 tick。
原版 `Particle.tick()` 会对每个粒子做一次方块碰撞检测，几十万粒子时极耗 CPU。

### ② 光照缓存

```java
@Inject(method = "getBrightness", at = @At("HEAD"), cancellable = true)
private void pwsUseCachedBrightness(float tickDelta, CallbackInfoReturnable<Integer> cir) {
   if (this.pwsBrightness >= 0 && this.pwsIsStatic()) {
      cir.setReturnValue(this.pwsBrightness);
   }
}
```

静态粒子的光照不会变，缓存第一次的结果，省掉每帧每粒子一次光照查询。

## 实测

| 场景 | 结论 |
|---|---|
| 921,600 粒子 | 5 fps（瓶颈在每帧重建 370 万顶点，不在这两个补丁） |
| 230,400 粒子 | ~30 fps |

## 重新编译

```bash
# 1. 克隆 1.21 分支
git clone --depth 1 --branch 1.21 https://github.com/noone89A/AnotherColorBlock.git particlex-1.21

# 2. 用本目录的 ParticleMixin.java 覆盖
#    src/main/java/com/noone/particleex/mixin/ParticleMixin.java

# 3. 编译（Gradle 8.12 + 国内镜像）
gradle build --no-daemon --init-script local-libs.init.gradle
```

产物：`build/libs/AnotherColorBlock-1.0.0.jar`

## 国内编译的三个坑

| 坑 | 解决 |
|---|---|
| Gradle 官方源 6 KB/s | 腾讯镜像 `mirrors.cloud.tencent.com/gradle/` |
| Loom 1.10.5 要求 Gradle ≥ 8.12 | 用 8.12，不能用 8.10 |
| `libraries.minecraft.net` 连不上 | `local-libs.init.gradle`：本地 `.minecraft\libraries` + 阿里云镜像 |

## 安装

```
mods\AnotherColorBlock-1.21.1-patched.jar
```

同时把 `config\particleex.json` 的 `maxParticleCount` 调大（默认 65536 会截断大图）：

```json
{ "maxParticleCount": 1100000, "ParallelParticleUpdate": true }
```
