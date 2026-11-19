package com.pws.instanced;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.FloatBuffer;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.rendering.v1.WorldRenderEvents;
import org.joml.Matrix4f;
import org.lwjgl.opengl.GL11;
import org.lwjgl.opengl.GL15;
import org.lwjgl.opengl.GL20;
import org.lwjgl.opengl.GL30;
import org.lwjgl.opengl.GL31;
import org.lwjgl.opengl.GL33;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 把静态图片以 GPU instancing 渲染成粒子墙。
 *
 * 关键点：
 *  · 实例缓冲存 [位置 xyz][颜色 rgba][大小]，每粒子 32 字节
 *  · 顶点着色器用 gl_VertexID 把每个实例展开成 4 个角，CPU 不生成顶点
 *  · 每帧只有一次 glDrawArraysInstanced
 *  · 多级 LOD：按距离切换到更粗的采样，消除远处摩尔纹
 *
 * 依赖：ThreatenGL（把 GL 上下文从 3.2 提升到 4.x，否则没有 glVertexAttribDivisor）
 */
public class ParticleInstanced implements ClientModInitializer {
    public static final Logger LOG = LoggerFactory.getLogger("particle-instanced");

    // ---------------------------------------------------------------- 可调参数
    /** 各 LOD 档位的横向像素数（越大越细） */
    // 只用最高精度一档：粒子数量与大小恒定，不随距离变化
    private static final int[] LOD_COLS = {1280};
    /** 距离阈值：超过该距离就用下一档（最后一档兜底） */
    private static final float[] LOD_DIST = {70f, 140f, 280f, 560f, 1120f, Float.MAX_VALUE};
    /** 墙宽（格） */
    private static final float WALL_W = 40.0f;
    /** 墙的 z 坐标（世界坐标） */
    private static final float WALL_Z = -18.0f;
    /** 粒子边长 = 像素间距 × 该系数 */
    private static final float SIZE_RATIO = 1.32f;
    /** 粒子位置抖动幅度（相对像素间距），打散规则格点以消除摩尔纹 */
    private static final float POS_JITTER = 0.25f;
    /** 粒子尺寸随机扰动幅度 */
    private static final float SIZE_JITTER = 0.35f;

    // ---------------------------------------------------------------- 运行时
    private static final class Level {
        int vao = -1, vbo = -1, count = 0;
        float halfW, halfH;
    }

    private static Level[] levels;
    private static int program = -1;
    private static boolean failed = false;

    @Override
    public void onInitializeClient() {
        WorldRenderEvents.LAST.register(ctx -> {
            try {
                if (failed) return;
                if (program == -1) init();
                if (levels == null) return;
                var cam = ctx.camera();
                var cp = cam.getPos();
                Matrix4f view = new Matrix4f()
                        .rotation(cam.getRotation().conjugate())
                        .translate((float) -cp.x, (float) -cp.y, (float) -cp.z);
                draw(view, ctx.projectionMatrix(), cp);
            } catch (Throwable t) {
                failed = true;
                LOG.error("[pws-inst] disabled after error", t);
            }
        });
        LOG.info("[pws-inst] LOD version registered");
    }

    // ---------------------------------------------------------------- 初始化
    private static void init() {
        String ver = GL11.glGetString(GL11.GL_VERSION);
        LOG.info("[pws-inst] GL_VERSION = " + ver);
        boolean ok = ver != null && (ver.startsWith("3.3") || ver.startsWith("3.4") || ver.startsWith("4."));
        if (!ok) {
            failed = true;
            LOG.warn("[pws-inst] OpenGL < 3.3, instancing unavailable. Skipping.");
            return;
        }

        java.awt.image.BufferedImage im;
        try {
            im = javax.imageio.ImageIO.read(new java.io.File("particleImages/still.png"));
            if (im == null) throw new java.io.IOException("not an image");
            LOG.info("[pws-inst] image " + im.getWidth() + "x" + im.getHeight());
        } catch (Throwable t) {
            throw new IllegalStateException("cannot load still.png", t);
        }

        int vs = compile(GL20.GL_VERTEX_SHADER, VSH);
        int fs = compile(GL20.GL_FRAGMENT_SHADER, FSH);
        program = GL20.glCreateProgram();
        GL20.glAttachShader(program, vs);
        GL20.glAttachShader(program, fs);
        GL20.glLinkProgram(program);
        if (GL20.glGetProgrami(program, GL20.GL_LINK_STATUS) == 0) {
            throw new IllegalStateException("link: " + GL20.glGetProgramInfoLog(program));
        }
        GL20.glDeleteShader(vs);
        GL20.glDeleteShader(fs);

        levels = new Level[LOD_COLS.length];
        for (int i = 0; i < LOD_COLS.length; i++) {
            levels[i] = buildLevel(im, LOD_COLS[i]);
            LOG.info("[pws-inst] LOD" + i + " cols=" + LOD_COLS[i] + " instances=" + levels[i].count);
        }
        LOG.info("[pws-inst] initialized, " + levels.length + " LOD levels");
    }

    private static Level buildLevel(java.awt.image.BufferedImage im, int cols) {
        int rows = Math.max(1, Math.round(cols * (float) im.getHeight() / im.getWidth()));

        // 双线性降采样：相邻粒子颜色接近，降低高频对比
        java.awt.image.BufferedImage small = new java.awt.image.BufferedImage(
                cols, rows, java.awt.image.BufferedImage.TYPE_INT_ARGB);
        java.awt.Graphics2D g2 = small.createGraphics();
        g2.setRenderingHint(java.awt.RenderingHints.KEY_INTERPOLATION,
                java.awt.RenderingHints.VALUE_INTERPOLATION_BILINEAR);
        g2.drawImage(im, 0, 0, cols, rows, null);
        g2.dispose();

        float step = WALL_W / cols;
        float halfW = WALL_W / 2f;
        float halfH = step * rows / 2f;
        float dot = step * SIZE_RATIO;

        ByteBuffer buf = ByteBuffer.allocateDirect(cols * rows * 32).order(ByteOrder.nativeOrder());
        FloatBuffer fb = buf.asFloatBuffer();
        java.util.Random rnd = new java.util.Random(20261119L);
        int written = 0;

        for (int y = 0; y < rows; y++) {
            for (int x = 0; x < cols; x++) {
                int argb = small.getRGB(x, y);
                int a = (argb >>> 24) & 0xFF;
                if (a < 8) continue;
                int r = (argb >> 16) & 0xFF, g = (argb >> 8) & 0xFF, b = argb & 0xFF;
                float jit = 1.0f + (rnd.nextFloat() - 0.5f) * SIZE_JITTER;
                // 位置抖动：破坏规则格点，消除透视下的拍频条纹
                float jx = (rnd.nextFloat() - 0.5f) * POS_JITTER * step;
                float jy = (rnd.nextFloat() - 0.5f) * POS_JITTER * step;
                fb.put(-halfW + x * step + jx);
                fb.put(halfH - y * step + jy);
                fb.put(WALL_Z);
                fb.put(r / 255f);
                fb.put(g / 255f);
                fb.put(b / 255f);
                fb.put(1f);
                fb.put(dot * jit);
                written++;
            }
        }
        fb.flip();

        Level lv = new Level();
        lv.count = written;
        lv.halfW = halfW;
        lv.halfH = halfH;

        lv.vao = GL30.glGenVertexArrays();
        GL30.glBindVertexArray(lv.vao);
        lv.vbo = GL15.glGenBuffers();
        GL15.glBindBuffer(GL15.GL_ARRAY_BUFFER, lv.vbo);
        GL15.glBufferData(GL15.GL_ARRAY_BUFFER, buf, GL15.GL_STATIC_DRAW);

        int stride = 32;
        GL20.glEnableVertexAttribArray(0);
        GL20.glVertexAttribPointer(0, 3, GL11.GL_FLOAT, false, stride, 0L);
        GL33.glVertexAttribDivisor(0, 1);
        GL20.glEnableVertexAttribArray(1);
        GL20.glVertexAttribPointer(1, 4, GL11.GL_FLOAT, false, stride, 12L);
        GL33.glVertexAttribDivisor(1, 1);
        GL20.glEnableVertexAttribArray(2);
        GL20.glVertexAttribPointer(2, 1, GL11.GL_FLOAT, false, stride, 28L);
        GL33.glVertexAttribDivisor(2, 1);
        GL30.glBindVertexArray(0);

        return lv;
    }

    private static int compile(int type, String src) {
        int s = GL20.glCreateShader(type);
        GL20.glShaderSource(s, src);
        GL20.glCompileShader(s);
        if (GL20.glGetShaderi(s, GL20.GL_COMPILE_STATUS) == 0) {
            throw new IllegalStateException("compile: " + GL20.glGetShaderInfoLog(s));
        }
        return s;
    }

    // ---------------------------------------------------------------- 绘制
    private static void draw(Matrix4f view, Matrix4f proj, net.minecraft.util.math.Vec3d camPos) {
        // 相机到墙面中心的距离，决定用哪一档
        float dx = (float) camPos.x;
        float dy = (float) camPos.y;
        float dz = (float) (camPos.z - WALL_Z);
        float dist = (float) Math.sqrt(dx * dx + dy * dy + dz * dz);

        // 每个粒子在屏幕上要占 >= MIN_PX 像素，否则亚像素采样必然产生摩尔纹
        final float MIN_PX = 3.0f;
        var mc = net.minecraft.client.MinecraftClient.getInstance();
        int screenH = mc.getWindow().getFramebufferHeight();
        double fovDeg = mc.options.getFov().getValue();
        double halfTan = Math.tan(Math.toRadians(fovDeg) / 2.0);
        // 屏幕高度对应的世界高度（在墙的距离处）
        float worldH = (float) (2.0 * halfTan * Math.max(dist, 0.1));
        // 粒子投影到屏幕上的像素数 = (墙宽/列数) × (屏幕高/世界高)
        // 反解出"不超过该列数时每粒子仍 >= MIN_PX"
        int wantCols = (int) (WALL_W * screenH / (worldH * MIN_PX));
        if (wantCols < 40) wantCols = 40;

        int idx = levels.length - 1;
        for (int i = 0; i < levels.length; i++) {
            if (LOD_COLS[i] <= wantCols) { idx = i; break; }
        }
        Level lv = levels[idx];
        if (lv == null || lv.count == 0) return;

        GL20.glUseProgram(program);
        int locMv = GL20.glGetUniformLocation(program, "uModelView");
        int locProj = GL20.glGetUniformLocation(program, "uProjection");
        float[] mv = new float[16], pj = new float[16];
        view.get(mv);
        proj.get(pj);
        GL20.glUniformMatrix4fv(locMv, false, mv);
        GL20.glUniformMatrix4fv(locProj, false, pj);

        GL11.glEnable(GL11.GL_BLEND);
        GL11.glBlendFunc(GL11.GL_SRC_ALPHA, GL11.GL_ONE_MINUS_SRC_ALPHA);
        GL11.glDisable(GL11.GL_DEPTH_TEST);
        GL30.glBindVertexArray(lv.vao);
        GL31.glDrawArraysInstanced(GL11.GL_TRIANGLE_STRIP, 0, 4, lv.count);
        GL30.glBindVertexArray(0);
        GL11.glEnable(GL11.GL_DEPTH_TEST);
        GL20.glUseProgram(0);
    }

    // ---------------------------------------------------------------- 着色器
    private static final String VSH = """
            #version 330 core
            layout(location = 0) in vec3 iPos;
            layout(location = 1) in vec4 iColor;
            layout(location = 2) in float iSize;
            uniform mat4 uModelView;
            uniform mat4 uProjection;
            out vec2 vUv;
            out vec4 vColor;
            void main() {
                vec2 corner = vec2(float(gl_VertexID & 1), float((gl_VertexID >> 1) & 1)) * 2.0 - 1.0;
                vUv = corner * 0.5 + 0.5;
                vColor = iColor;
                vec3 world = iPos + vec3(corner * 0.5 * iSize, 0.0);
                gl_Position = uProjection * uModelView * vec4(world, 1.0);
            }
            """;

    private static final String FSH = """
            #version 330 core
            in vec2 vUv;
            in vec4 vColor;
            out vec4 fragColor;
            void main() {
                // 菱形 + 极窄的边缘过渡（只在最外侧 15% 做抗锯齿）
                vec2 c = vUv * 2.0 - 1.0;
                float d = abs(c.x) + abs(c.y);
                if (d > 1.0) discard;
                float a = 1.0 - smoothstep(0.75, 1.0, d);
                fragColor = vec4(vColor.rgb, vColor.a * a);
            }
            """;
}
