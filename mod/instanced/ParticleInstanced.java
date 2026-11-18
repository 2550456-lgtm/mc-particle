package com.pws.instanced;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.FloatBuffer;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.rendering.v1.WorldRenderEvents;
import net.minecraft.client.MinecraftClient;
import net.minecraft.util.Identifier;
import org.joml.Matrix4f;
import org.lwjgl.opengl.GL11;
import org.lwjgl.opengl.GL13;
import org.lwjgl.opengl.GL15;
import org.lwjgl.opengl.GL20;
import org.lwjgl.opengl.GL30;
import org.lwjgl.opengl.GL33;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class ParticleInstanced implements ClientModInitializer {
    public static final Logger LOG = LoggerFactory.getLogger("particle-instanced");

    private static int program = -1, vao = -1, vbo = -1;
    private static int instanceCount = 0;
    private static boolean failed = false;

    @Override
    public void onInitializeClient() {
        WorldRenderEvents.LAST.register(ctx -> {
            try {
                if (failed) return;
                if (program == -1) init();
                if (instanceCount == 0) return;
                draw(ctx.matrixStack().peek().getPositionMatrix(), ctx.projectionMatrix());
            } catch (Throwable t) {
                failed = true;
                LOG.error("[pws-inst] disabled after error", t);
            }
        });
        LOG.info("[pws-inst] milestone 2 registered");
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

        // M3：从 particleImages/still.png 生成实例数据
        int cols = 1280;
        java.awt.image.BufferedImage im = null;
        try {
            java.io.File f = new java.io.File("particleImages/still.png");
            im = javax.imageio.ImageIO.read(f);
            if (im == null) throw new java.io.IOException("not an image");
            LOG.info("[pws-inst] image " + im.getWidth() + "x" + im.getHeight());
        } catch (Throwable t) {
            throw new IllegalStateException("cannot load still.png: " + t);
        }
        int rows = Math.max(1, Math.round(cols * (float) im.getHeight() / im.getWidth()));
        int n = cols * rows;
        float step = 25.6f / cols;
        float halfW = 25.6f / 2f;
        float halfH = step * rows / 2f;
        float dot = step * 1.4f;

        ByteBuffer buf = ByteBuffer.allocateDirect(n * 32).order(ByteOrder.nativeOrder());
        FloatBuffer fb = buf.asFloatBuffer();
        int written = 0;
        for (int y = 0; y < rows; y++) {
            for (int x = 0; x < cols; x++) {
                int argb = im.getRGB(x * im.getWidth() / cols, y * im.getHeight() / rows);
                int a = (argb >>> 24) & 0xFF;
                int r = (argb >> 16) & 0xFF, g = (argb >> 8) & 0xFF, b = argb & 0xFF;
                if (a < 8) continue;
                fb.put(-halfW + x * step);      // px
                fb.put(halfH - y * step);       // py
                fb.put(-18.0f);                 // pz
                fb.put(r / 255f); fb.put(g / 255f); fb.put(b / 255f); fb.put(1f);
                fb.put(dot);                    // size
                written++;
            }
        }
        fb.flip();

        vao = GL30.glGenVertexArrays();
        GL30.glBindVertexArray(vao);
        vbo = GL15.glGenBuffers();
        GL15.glBindBuffer(GL15.GL_ARRAY_BUFFER, vbo);
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
        instanceCount = written;
        LOG.info("[pws-inst] initialized with " + written + " instances");
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
    private static void draw(Matrix4f modelView, Matrix4f projection) {
        GL20.glUseProgram(program);
        int locMv = GL20.glGetUniformLocation(program, "uModelView");
        int locProj = GL20.glGetUniformLocation(program, "uProjection");
        int locTex = GL20.glGetUniformLocation(program, "uTexture");
        float[] mv = new float[16], pj = new float[16];
        modelView.get(mv);
        projection.get(pj);
        GL20.glUniformMatrix4fv(locMv, false, mv);
        GL20.glUniformMatrix4fv(locProj, false, pj);

        var tex = MinecraftClient.getInstance().getTextureManager()
                .getTexture(Identifier.of("minecraft", "textures/atlas/particles.png"));
        GL13.glActiveTexture(GL13.GL_TEXTURE0);
        GL11.glBindTexture(GL11.GL_TEXTURE_2D, tex.getGlId());
        GL20.glUniform1i(locTex, 0);

        GL11.glEnable(GL11.GL_BLEND);
        GL11.glBlendFunc(GL11.GL_SRC_ALPHA, GL11.GL_ONE_MINUS_SRC_ALPHA);
        GL11.glDisable(GL11.GL_DEPTH_TEST);
        GL30.glBindVertexArray(vao);
        GL31Draw();
        GL30.glBindVertexArray(0);
        GL11.glEnable(GL11.GL_DEPTH_TEST);
        GL20.glUseProgram(0);
    }

    private static void GL31Draw() {
        org.lwjgl.opengl.GL31.glDrawArraysInstanced(GL11.GL_TRIANGLE_STRIP, 0, 4, instanceCount);
    }

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
            uniform sampler2D uTexture;
            out vec4 fragColor;
            void main() {
                vec4 t = texture(uTexture, vUv);
                if (t.a < 0.01) discard;
                fragColor = t * vColor;
            }
            """;
}