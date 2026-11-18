package com.noone.particleex.mixin;

import com.noone.particleex.util.ClientMessageUtil;
import com.noone.particleex.util.IExecutable;
import com.noone.particleex.util.IParticle;
import com.noone.particleex.util.ParticleStruct;
import net.minecraft.client.particle.Particle;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;


@Mixin({Particle.class})
public abstract class ParticleMixin implements IParticleMixin, IParticle {
   @Unique
   private IExecutable exe;
   @Unique
   private double step;
   @Unique
   private double centerX;
   @Unique
   private double centerY;
   @Unique
   private double centerZ;
   @Unique
   private boolean customMove;
   @Unique
   private boolean stop;
   @Unique
   private int pwsBrightness = -1;
   @Unique
   private double moveT;
   @Unique
   private double preX;
   @Unique
   private double preY;
   @Unique
   private double preZ;
   @Shadow
   protected double x;
   @Shadow
   protected double y;
   @Shadow
   protected double z;
   @Shadow
   protected double velocityX;
   @Shadow
   protected double velocityY;
   @Shadow
   protected double velocityZ;
   @Shadow
   protected float red = 1.0F;
   @Shadow
   protected float green = 1.0F;
   @Shadow
   protected float blue = 1.0F;
   @Shadow
   protected float alpha = 1.0F;

   public void setExe(IExecutable exe) {
      this.exe = exe;
   }

   public void setStep(double step) {
      this.step = step;
   }

   public double getCenterX() {
      return this.centerX;
   }

   public void setCenterX(double centerX) {
      this.centerX = centerX;
   }

   public double getCenterY() {
      return this.centerY;
   }

   public void setCenterY(double centerY) {
      this.centerY = centerY;
   }

   public double getCenterZ() {
      return this.centerZ;
   }

   public void setCenterZ(double centerZ) {
      this.centerZ = centerZ;
   }

   public void setCustomMove(boolean customMove) {
      this.customMove = customMove;
   }

   public void setStop(boolean stop) {
      this.stop = stop;
   }

   @Shadow
   public abstract void tick();

   @Shadow
   public abstract void move(double var1, double var3, double var5);

   @Shadow
   public abstract void markDead();

   @Shadow
   public abstract void setPos(double var1, double var3, double var5);

   @Unique
   private boolean pwsIsStatic() {
      return this.exe == null && !this.customMove
            && this.velocityX == 0.0D && this.velocityY == 0.0D && this.velocityZ == 0.0D;
   }

   // 静态粒子的光照不会变，缓存第一次的结果，避免每帧每粒子重复查询
   @Inject(method = "getBrightness", at = @At("HEAD"), cancellable = true)
   private void pwsUseCachedBrightness(float tickDelta, CallbackInfoReturnable<Integer> cir) {
      if (this.pwsBrightness >= 0 && this.pwsIsStatic()) {
         cir.setReturnValue(this.pwsBrightness);
      }
   }

   @Inject(method = "getBrightness", at = @At("RETURN"))
   private void pwsStoreBrightness(float tickDelta, CallbackInfoReturnable<Integer> cir) {
      if (this.pwsBrightness < 0 && this.pwsIsStatic()) {
         this.pwsBrightness = cir.getReturnValue();
      }
   }

   public void customTick() {
      // 静态粒子优化：没有表达式、没有初速度、不跟随中心移动时，
      // 粒子永远停在原地，无需 tick（原版 tick 会做方块碰撞检测，量大了极耗 CPU）。
      if (this.exe == null && !this.customMove
            && this.velocityX == 0.0D && this.velocityY == 0.0D && this.velocityZ == 0.0D) {
         return;
      }
      this.preX = this.x;
      this.preY = this.y;
      this.preZ = this.z;
      this.tick();
      if (this.stop) {
         this.setPos(this.preX, this.preY, this.preZ);
      }

      this.customMove();
   }

   @Unique
   protected void customMove() {
      if (this.customMove && this.exe != null) {
         ParticleStruct data = this.exe.getData();
         if (this.moveT == 0.0D) {
            data.cx = this.centerX;
            data.cy = this.centerY;
            data.cz = this.centerZ;
            data.dx = this.x - this.centerX;
            data.dy = this.y - this.centerY;
            data.dz = this.z - this.centerZ;
            data.ddis = Math.sqrt((this.x - this.centerX) * (this.x - this.centerX) + (this.y - this.centerY) * (this.y - this.centerY) + (this.z - this.centerZ) * (this.z - this.centerZ));
            data.ds1 = Math.atan2(this.z - this.centerZ, this.x - this.centerX);
            data.ds2 = Math.atan2(this.y - this.centerY, Math.hypot(this.x - this.centerX, this.z - this.centerZ));
         }

         data.vx = Double.NaN;
         data.vy = Double.NaN;
         data.vz = Double.NaN;
         data.x = this.x - this.centerX;
         data.y = this.y - this.centerY;
         data.z = this.z - this.centerZ;
         data.cr = this.red;
         data.cg = this.green;
         data.cb = this.blue;
         data.alpha = this.alpha;
         data.dis = Math.sqrt((this.x - this.centerX) * (this.x - this.centerX) + (this.y - this.centerY) * (this.y - this.centerY) + (this.z - this.centerZ) * (this.z - this.centerZ));
         data.s1 = Math.atan2(this.z - this.centerZ, this.x - this.centerX);
         data.s2 = Math.atan2(this.y - this.centerY, Math.hypot(this.x - this.centerX, this.z - this.centerZ));
         data.t = this.moveT;
         this.moveT += this.step;

         try {
            this.exe.invoke();
         } catch (RuntimeException var3) {
            ClientMessageUtil.addChatMessage(var3);
            this.markDead();
            return;
         }

          if (data.destroy != 0.0D) {
            this.markDead();
            return;
         }

         if (data.vx == data.vx || data.vy == data.vy || data.vz == data.vz) {
            this.setPos(this.preX, this.preY, this.preZ);
            data.vx = this.nanToZero(data.vx);
            data.vy = this.nanToZero(data.vy);
            data.vz = this.nanToZero(data.vz);
            this.move(data.vx, data.vy, data.vz);
         }

         this.red = (float)data.cr;
         this.green = (float)data.cg;
         this.blue = (float)data.cb;
         this.alpha = (float)data.alpha;
      }

   }

   @Unique
   private double nanToZero(double num) {
      return num == num ? num : 0.0D;
   }
}
