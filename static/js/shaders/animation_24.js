/*
 * Shader source for ANIMATION_24, ported verbatim from Stitch code.html.
 * Pulsing radial "Rule of Two" variant with glow/ring mask. Consumed by
 * shader_loader.js. Not yet wired into a real page — see
 * IMPLEMENTATION_PLAN.md §2.4 / §5 Q9.
 */
export const vertexShader = `attribute vec2 a_position;
varying vec2 v_texCoord;
void main() {
  v_texCoord = a_position * 0.5 + 0.5;
  gl_Position = vec4(a_position, 0.0, 1.0);
}`;

export const fragmentShader = `precision highp float;

uniform float u_time;
uniform vec2 u_resolution;

varying vec2 v_texCoord;

void main() {
    vec2 uv = v_texCoord;
    vec2 centered_uv = (uv - 0.5) * 2.0;
    centered_uv.x *= u_resolution.x / u_resolution.y;

    float pulse = sin(u_time * 2.0) * 0.5 + 0.5;

    float line1 = smoothstep(0.01, 0.0, abs(centered_uv.x - centered_uv.y * 0.5));
    float line2 = smoothstep(0.01, 0.0, abs(centered_uv.x + centered_uv.y * 0.5));

    float dist = length(centered_uv);
    vec3 base_color = vec3(0.04, 0.04, 0.04);
    vec3 accent_color = vec3(0.91, 0.36, 0.02);

    float glow = exp(-dist * 1.5) * 0.15;
    vec3 final_color = base_color + accent_color * glow * pulse;

    float circle = smoothstep(0.8, 0.79, dist);
    final_color += accent_color * (line1 + line2) * 0.4 * pulse;

    gl_FragColor = vec4(final_color, 1.0);
}`;
