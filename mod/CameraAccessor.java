package com.noone.particleex.mixin;

import net.minecraft.client.render.Camera;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

@Mixin({Camera.class})
public interface CameraAccessor {
   @Invoker("setPos")
   void pwsSetPos(double x, double y, double z);

   @Invoker("setRotation")
   void pwsSetRotation(float yaw, float pitch);
}