#version 330 core

in vec2 vUv;
in vec4 vColor;

uniform sampler2D uTexture;

out vec4 fragColor;

void main() {
    vec4 tex = texture(uTexture, vUv);
    if (tex.a < 0.01) discard;
    fragColor = tex * vColor;
}