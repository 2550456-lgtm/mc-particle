package com.pws.instanced;

import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.FloatBuffer;
import java.nio.channels.FileChannel;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.command.v2.ClientCommandManager;
import net.fabricmc.fabric.api.client.command.v2.ClientCommandRegistrationCallback;
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
 * 视频 → 粒子墙。
 *
 * 位置/大小固定（静态 VBO），只有颜色逐帧变化（动态 VBO + glBufferSubData）。
 * 每帧上传 1280×720×3 ≈ 2.7 MB，12fps 下约 33 MB/s，开销可忽略。
 *
 * 帧数据来自 particleImages/op.rgb（ffmpeg 抽出的 rawvideo rgb24，内存映射读取）。
 * 需要 ThreatenGL 让 GL 上下文达到 3.3+（实例化属性需要).
 */
public class ParticleInstanced implements ClientModInitializer {
    public static final Logger LOG = LoggerFactory.getLogger("particle-instanced");

    // ---------------------------------------------------------------- 参数
    private static final int COLS = 1280;
    private static final int ROWS = 720;
    private static int frameCount = 0;             // 由文件大小推导
    private static final float FRAME_FPS = 12.0f;  // 播放帧率

    private static final float WALL_W = 40.0f;     // 墙宽（格）
    private static final float WALL_Z = -18.0f;    // 墙中心的世界 z
    private static final float WALL_CENTER_X = 0.0f;
    private static final float WALL_CENTER_Y = 5.75f;
    private static final float SIZE_RATIO = 1.32f;
    private static final float POS_JITTER = 0.25f;
    private static final float SIZE_JITTER = 0.35f;

    private static final String FRAMES_PATH = "particleImages/op.rgb";

    // ---------------------------------------------------------------- 运行时
    private static int program = -1;
    private static int vao = -1;
    private static int vboStatic = -1;
    private static int vboColor = -1;
    private static int instanceCount = 0;
    private static boolean failed = false;

    private static FileChannel frameChannel;
    private static ByteBuffer frameBuf;   // 复用的直接缓冲，每帧读入 2.76MB
    private static long startNanos;
    private static int lastFrame = -1;
    /** 是否正在推进时间轴（/run /start 打开，/stop 暂停） */
    private static boolean playing = false;
    /** 是否显示画面（/end 关闭，/start /run 打开） */
    private static boolean visible = false;
    /** 已累积的播放时间（秒），暂停时保留 */
    private static double accTime = 0.0;
    private static long lastFrameNanos = 0;
    private static final int FRAME_BYTES = COLS * ROWS * 3;

    @Override
    public void onInitializeClient() {
        WorldRenderEvents.LAST.register(ctx -> {
            try {
                if (failed) return;
                if (program == -1) init();
                if (instanceCount == 0) return;
                if (!visible) return;
                var cam = ctx.camera();
                var cp = cam.getPos();
                Matrix4f view = new Matrix4f()
                        .rotation(cam.getRotation().conjugate())
                        .translate((float) -cp.x, (float) -cp.y, (float) -cp.z);
                draw(view, ctx.projectionMatrix(), cam.getRotation());
            } catch (Throwable t) {
                failed = true;
                LOG.error("[pws-inst] disabled after error", t);
            }
        });
        ClientCommandRegistrationCallback.EVENT.register((dispatcher, access) -> {
            // 从头开始播放
            dispatcher.register(ClientCommandManager.literal("start").executes(ctx -> {
                accTime = 0.0;
                lastFrameNanos = System.nanoTime();
                visible = true;
                playing = true;
                LOG.info("[pws-inst] start");
                return 1;
            }));
            // 继续播放（保留当前进度）
            dispatcher.register(ClientCommandManager.literal("run").executes(ctx -> {
                lastFrameNanos = System.nanoTime();
                visible = true;
                playing = true;
                LOG.info("[pws-inst] run");
                return 1;
            }));
            // 暂停：画面保留，时间不动
            dispatcher.register(ClientCommandManager.literal("stop").executes(ctx -> {
                playing = false;
                LOG.info("[pws-inst] stop (paused)");
                return 1;
            }));
            // 结束：立即消失
            dispatcher.register(ClientCommandManager.literal("end").executes(ctx -> {
                playing = false;
                visible = false;
                LOG.info("[pws-inst] end");
                return 1;
            }));
        });
        LOG.info("[pws-inst] video version registered");
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

        // 帧数据可能超过 2GB，不能整体映射；按帧读入复用缓冲
        try {
            RandomAccessFile raf = new RandomAccessFile(FRAMES_PATH, "r");
            frameChannel = raf.getChannel();
            frameCount = (int) (frameChannel.size() / FRAME_BYTES);
            if (frameCount <= 0) {
                throw new IllegalStateException("op.rgb too small: " + frameChannel.size());
            }
            frameBuf = ByteBuffer.allocateDirect(FRAME_BYTES);
            LOG.info("[pws-inst] frames ready: " + frameCount + " x " + FRAME_BYTES
                    + " bytes (" + String.format("%.2f", frameChannel.size() / 1073741824.0) + " GB)");
        } catch (Throwable t) {
            throw new IllegalStateException("cannot open " + FRAMES_PATH, t);
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

        float step = WALL_W / COLS;
        float halfW = WALL_W / 2f;
        float halfH = step * ROWS / 2f;
        float dot = step * SIZE_RATIO;

        int n = COLS * ROWS;
        ByteBuffer stat = ByteBuffer.allocateDirect(n * 16).order(ByteOrder.nativeOrder());
        FloatBuffer fb = stat.asFloatBuffer();
        java.util.Random rnd = new java.util.Random(20261119L);
        for (int y = 0; y < ROWS; y++) {
            for (int x = 0; x < COLS; x++) {
                float jx = (rnd.nextFloat() - 0.5f) * POS_JITTER * step;
                float jy = (rnd.nextFloat() - 0.5f) * POS_JITTER * step;
                float jit = 1.0f + (rnd.nextFloat() - 0.5f) * SIZE_JITTER;
                fb.put(WALL_CENTER_X - halfW + x * step + jx);
                fb.put(WALL_CENTER_Y + halfH - y * step + jy);
                fb.put(WALL_Z);
                fb.put(dot * jit);
            }
        }
        fb.flip();

        vao = GL30.glGenVertexArrays();
        GL30.glBindVertexArray(vao);

        vboStatic = GL15.glGenBuffers();
        GL15.glBindBuffer(GL15.GL_ARRAY_BUFFER, vboStatic);
        GL15.glBufferData(GL15.GL_ARRAY_BUFFER, stat, GL15.GL_STATIC_DRAW);
        GL20.glEnableVertexAttribArray(0);
        GL20.glVertexAttribPointer(0, 3, GL11.GL_FLOAT, false, 16, 0L);
        GL33.glVertexAttribDivisor(0, 1);
        GL20.glEnableVertexAttribArray(2);
        GL20.glVertexAttribPointer(2, 1, GL11.GL_FLOAT, false, 16, 12L);
        GL33.glVertexAttribDivisor(2, 1);

        vboColor = GL15.glGenBuffers();
        GL15.glBindBuffer(GL15.GL_ARRAY_BUFFER, vboColor);
        GL15.glBufferData(GL15.GL_ARRAY_BUFFER, (long) n * 3, GL15.GL_DYNAMIC_DRAW);
        GL20.glEnableVertexAttribArray(1);
        GL20.glVertexAttribPointer(1, 3, GL11.GL_UNSIGNED_BYTE, true, 3, 0L);
        GL33.glVertexAttribDivisor(1, 1);

        GL30.glBindVertexArray(0);
        GL15.glBindBuffer(GL15.GL_ARRAY_BUFFER, 0);

        instanceCount = n;
        startNanos = System.nanoTime();
        LOG.info("[pws-inst] initialized " + n + " instances, " + frameCount + " frames");
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
    private static void draw(Matrix4f view, Matrix4f proj, org.joml.Quaternionf camRot) {
        // 当前帧
        long now = System.nanoTime();
        if (playing && lastFrameNanos != 0) {
            accTime += (now - lastFrameNanos) / 1e9;
        }
        lastFrameNanos = now;
        int frame = (int) (accTime * FRAME_FPS) % frameCount;

        if (frame != lastFrame) {
            lastFrame = frame;
            try {
                frameBuf.clear();
                long off = (long) frame * FRAME_BYTES;
                while (frameBuf.hasRemaining()) {
                    int r = frameChannel.read(frameBuf, off + frameBuf.position());
                    if (r < 0) break;
                }
                frameBuf.flip();
                GL15.glBindBuffer(GL15.GL_ARRAY_BUFFER, vboColor);
                GL15.glBufferSubData(GL15.GL_ARRAY_BUFFER, 0L, frameBuf);
                GL15.glBindBuffer(GL15.GL_ARRAY_BUFFER, 0);
            } catch (java.io.IOException e) {
                throw new RuntimeException(e);
            }
        }

        GL20.glUseProgram(program);
        float[] mv = new float[16], pj = new float[16];
        view.get(mv);
        proj.get(pj);
        GL20.glUniformMatrix4fv(GL20.glGetUniformLocation(program, "uModelView"), false, mv);
        GL20.glUniformMatrix4fv(GL20.glGetUniformLocation(program, "uProjection"), false, pj);
        GL20.glUniform1i(GL20.glGetUniformLocation(program, "uFrame"), frame);
        // 从视图矩阵取相机基：view 的上 3x3 是 world->camera，转置即 camera->world
        org.joml.Matrix3f basis = new org.joml.Matrix3f();
        view.get3x3(basis);
        basis.transpose();
        org.joml.Vector3f right = basis.getColumn(0, new org.joml.Vector3f());
        org.joml.Vector3f up = basis.getColumn(1, new org.joml.Vector3f());
        right.normalize();
        up.normalize();
        GL20.glUniform3f(GL20.glGetUniformLocation(program, "uCamRight"), right.x, right.y, right.z);
        GL20.glUniform3f(GL20.glGetUniformLocation(program, "uCamUp"), up.x, up.y, up.z);

GL11.glEnable(GL11.GL_BLEND);
        GL11.glBlendFunc(GL11.GL_SRC_ALPHA, GL11.GL_ONE_MINUS_SRC_ALPHA);
        GL11.glDisable(GL11.GL_DEPTH_TEST);
        GL11.glDisable(GL11.GL_CULL_FACE);
        GL30.glBindVertexArray(vao);
        GL31.glDrawArraysInstanced(GL11.GL_TRIANGLE_STRIP, 0, 4, instanceCount);
        GL30.glBindVertexArray(0);
        GL11.glEnable(GL11.GL_CULL_FACE);
        GL11.glEnable(GL11.GL_DEPTH_TEST);
        GL20.glUseProgram(0);
    }

    // ---------------------------------------------------------------- 着色器
    private static final String VSH = """
            #version 330 core
            layout(location = 0) in vec3 iPos;    // 世界坐标（墙固定不动）
            layout(location = 1) in vec3 iColor;
            layout(location = 2) in float iSize;
            uniform mat4 uModelView;
            uniform mat4 uProjection;
            uniform int uFrame;
            uniform vec3 uCamRight;
            uniform vec3 uCamUp;
            out vec2 vUv;
            out vec4 vColor;

            uint pcg(uint v) {
                uint state = v * 747796405u + 2891336453u;
                uint word = ((state >> ((state >> 28u) + 4u)) ^ state) * 277803737u;
                return (word >> 22u) ^ word;
            }
            float rnd(uint seed) {
                return float(pcg(seed) & 0xFFFFFFu) / 16777215.0;
            }

            void main() {
                uint base = uint(gl_InstanceID);
                uint f = uint(uFrame);
                float h1 = rnd(base ^ (f * 0x9E3779B9u));
                float h2 = rnd((base + 0x1234u) ^ (f * 0x85EBCA6Bu));
                float h3 = rnd((base + 0x5678u) ^ (f * 0xC2B2AE35u));

                float sMul = 1.0 + (h3 - 0.5) * 0.15;
                vec2 jit = (vec2(h1, h2) - 0.5) * 0.18;

                vec2 corner = vec2(float(gl_VertexID & 1), float((gl_VertexID >> 1) & 1)) * 2.0 - 1.0;
                vUv = corner * 0.5 + 0.5;
                vColor = vec4(iColor, 1.0);

                // 只有粒子自身朝向相机；墙面本身固定在世界坐标
                vec3 offset = (uCamRight * (corner.x + jit.x) + uCamUp * (corner.y + jit.y))
                              * 0.5 * iSize * sMul;
                vec3 world = iPos + offset;
                gl_Position = uProjection * uModelView * vec4(world, 1.0);
            }
            """;

    private static final String FSH = """
            #version 330 core
            in vec2 vUv;
            in vec4 vColor;
            out vec4 fragColor;
            void main() {
                vec2 c = vUv * 2.0 - 1.0;
                float d = abs(c.x) + abs(c.y);
                if (d > 1.0) discard;
                float a = 1.0 - smoothstep(0.75, 1.0, d);
                fragColor = vec4(vColor.rgb, a);
            }
            """;
}
