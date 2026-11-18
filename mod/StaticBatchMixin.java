package com.noone.particleex.mixin;

import java.util.Map;
import java.util.Queue;

import com.mojang.blaze3d.systems.RenderSystem;
import net.minecraft.client.gl.VertexBuffer;
import net.minecraft.client.particle.Particle;
import net.minecraft.client.particle.ParticleManager;
import net.minecraft.client.particle.ParticleTextureSheet;
import net.minecraft.client.render.BufferBuilder;
import net.minecraft.client.render.BuiltBuffer;
import net.minecraft.client.render.Camera;
import net.minecraft.client.render.GameRenderer;
import net.minecraft.client.render.LightmapTextureManager;
import net.minecraft.client.render.Tessellator;
import net.minecraft.client.render.VertexFormat;
import net.minecraft.client.render.VertexFormats;
import net.minecraft.util.Identifier;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * 静态批次：把静止的粒子墙烘成一份顶点缓冲，每帧只提交一次 draw call。
 * 顶点固定朝 +Z（墙面朝向），因此可以缓存；绕到侧面看时粒子不再是公告板。
 * 任何异常都会自动停用本优化，退回原版渲染。
 */
@Mixin({ParticleManager.class})
public abstract class StaticBatchMixin {
   @Shadow
   private Map<ParticleTextureSheet, Queue<Particle>> particles;

   @Unique private static VertexBuffer pwsVbo;
   @Unique private static int pwsBakedCount = -1;
   @Unique private static boolean pwsBroken = false;
   @Unique private static boolean pwsLogged = false;

   @Inject(method = {"renderParticles"}, at = @At("HEAD"), cancellable = true)
   private void pwsRenderBatch(LightmapTextureManager lightmap, Camera camera, float tickDelta, CallbackInfo ci) {
      // 静态批次默认关闭（最后一步光照采样器未绑定）；-Dpws.batch=true 可启用
      if (!Boolean.getBoolean("pws.batch")) {
         return;
      }

      if (pwsBroken) {
         return;
      }
      try {
         Queue<Particle> queue = this.particles.get(ParticleTextureSheet.PARTICLE_SHEET_TRANSLUCENT);
         if (queue == null || queue.isEmpty()) {
            return;
         }
         int count = queue.size();

         if (count != pwsBakedCount) {
            if (pwsVbo != null) {
               pwsVbo.close();
               pwsVbo = null;
            }
            Camera zero = new Camera();
            CameraAccessor acc = (CameraAccessor) zero;
            acc.pwsSetPos(0.0D, 0.0D, 0.0D);
            acc.pwsSetRotation(0.0F, 0.0F);

            BufferBuilder bb = Tessellator.getInstance().begin(
                  VertexFormat.DrawMode.QUADS, VertexFormats.POSITION_COLOR_TEXTURE_LIGHT);
            for (Particle p : queue) {
               p.buildGeometry(bb, zero, tickDelta);
            }
            BuiltBuffer built = bb.endNullable();
            if (built == null) {
               pwsBroken = true;
               System.out.println("[particlex][pws] bake empty buffer, disabled");
               return;
            }
            pwsVbo = new VertexBuffer(VertexBuffer.Usage.STATIC);
            pwsVbo.upload(built);
            pwsBakedCount = count;
            System.out.println("[particlex][pws] baked " + count + " particles");
         }

         if (pwsVbo != null) {
            // 顶点已在世界坐标（烘焙相机位于原点），所以视图矩阵要自己算：
            //   view = R_cam^-1 * T(-camPos)
            org.joml.Matrix4f model = new org.joml.Matrix4f()
                  .rotation(camera.getRotation().conjugate())
                  .translate((float) -camera.getPos().x, (float) -camera.getPos().y, (float) -camera.getPos().z);

            RenderSystem.setShaderTexture(0, Identifier.of("minecraft", "textures/atlas/particles.png"));
            RenderSystem.enableBlend();
            RenderSystem.defaultBlendFunc();
            RenderSystem.enableDepthTest();
            RenderSystem.depthMask(false);
            RenderSystem.disableCull();
            pwsVbo.draw(model, RenderSystem.getProjectionMatrix(), GameRenderer.getParticleProgram());
            RenderSystem.enableCull();
            RenderSystem.depthMask(true);
            ci.cancel();
         }
      } catch (Throwable t) {
         pwsBroken = true;
         System.out.println("[particlex][pws] failed, fallback to vanilla: " + t);
      }
   }
}