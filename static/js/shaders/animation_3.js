/*
 * Shader source for ANIMATION_3, ported verbatim from Stitch code.html.
 * "Rule of Two" converging lines, concrete-grain noise, Matte Black + Fire
 * Orange. Consumed by shader_loader.js. Not yet wired into a real page —
 * see IMPLEMENTATION_PLAN.md §2.4 / §5 Q9.
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
uniform vec2 u_mouse;
varying vec2 v_texCoord;

void main() {
    vec2 uv = v_texCoord;
    vec2 mouse = u_mouse / u_resolution;

    vec3 color = vec3(0.0588, 0.0588, 0.0588);

    float line1 = smoothstep(0.002, 0.0, abs(uv.x - 0.45 + sin(u_time * 0.5 + uv.y * 2.0) * 0.02));
    float line2 = smoothstep(0.002, 0.0, abs(uv.x - 0.55 - sin(u_time * 0.5 + uv.y * 2.0) * 0.02));

    float convergence = smoothstep(0.8, 0.5, uv.y);
    float finalLines = mix(line1 + line2, smoothstep(0.004, 0.0, abs(uv.x - 0.5)), 1.0 - convergence);

    vec3 orange = vec3(0.91, 0.36, 0.016);
    color += finalLines * orange * 0.4;

    float noise = fract(sin(dot(uv, vec2(12.9898, 78.233))) * 43758.5453);
    color *= (0.95 + 0.05 * noise);

    gl_FragColor = vec4(color, 1.0);
}`;
