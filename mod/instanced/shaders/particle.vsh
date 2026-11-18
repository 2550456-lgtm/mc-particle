#version 330 core

// 每个实例一条数据
layout(location = 0) in vec3 iPos;     // 世界坐标
layout(location = 1) in vec4 iColor;   // RGBA
layout(location = 2) in float iSize;   // 边长（格）

uniform mat4 uModelView;   // 相机视图矩阵
uniform mat4 uProjection;  // 投影矩阵
uniform vec2 uCornerOffset;// (0.5, 0.5)

out vec2 vUv;
out vec4 vColor;

void main() {
    // 0..3 -> 四角
    vec2 corner = vec2(float(gl_VertexID & 1), float((gl_VertexID >> 1) & 1)) * 2.0 - 1.0;
    vUv    = corner * 0.5 + 0.5;
    vColor = iColor;

    vec3 world = iPos + vec3(corner * uCornerOffset * iSize, 0.0);
    gl_Position = uProjection * uModelView * vec4(world, 1.0);
}