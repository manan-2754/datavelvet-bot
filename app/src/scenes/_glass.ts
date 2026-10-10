// Premium glass layer: real three.js meshes under the hologram wireframes - physically based glass (transmission,
// refraction, IOR, thickness, tinted attenuation, clearcoat) lit by a studio environment + a key and a coloured rim
// light, rendered into its own target and composited with a depth-of-field blur (focus on what the camera looks at).
// The camera is the exact same projection as the CPU hologram pen (View), so glass bodies sit inside the wireframes.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { FSPass, W, H, makeRT } from '../engine/gl';
import type { View, V3 } from './_holo3d';
import type { RGB } from './_vo';

export type GeoKind = 'box' | 'sphere' | 'cyl' | 'cone' | 'torus' | 'prism' | 'pyr';
export interface GlassItem { key: string; geo: GeoKind; dims: V3; y0: number; pos: V3; scale: V3; yaw: number; color: RGB; alpha: number; frost?: number }
export interface GlassStyle { roughness: number; ior: number; thickness: number; dof: number; rim: RGB; key: number }

const BOKEH = /* glsl */ `
uniform sampler2D tCol; uniform sampler2D tDepth; uniform vec2 uRes; uniform float uFocus, uNear, uFar, uStrength, uMaxR;
float lin(float d) { float z = d * 2.0 - 1.0; return (2.0 * uNear * uFar) / (uFar + uNear - z * (uFar - uNear)); }
void main() {
  vec2 uv = vUv;
  float d = texture(tDepth, uv).r;
  float z = d >= 0.99999 ? uFocus * 2.5 : lin(d);
  float coc = clamp(abs(z - uFocus) / max(0.001, uFocus) * uStrength, 0.0, uMaxR);
  vec4 acc = texture(tCol, uv); float wsum = 1.0;
  if (coc > 0.6) {
    for (int i = 1; i < 24; i++) {
      float fi = float(i), r = sqrt(fi / 24.0) * coc, a = fi * 2.39996;
      acc += texture(tCol, uv + vec2(cos(a), sin(a)) * r / uRes); wsum += 1.0;
    }
  }
  fragColor = acc / wsum;
}`;

let shared: GlassLayer | null = null;

export class GlassLayer {
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(40, W / H, 0.1, 300);
  meshes = new Map<string, THREE.Mesh>();
  geos = new Map<string, THREE.BufferGeometry>();
  rt: THREE.WebGLRenderTarget;
  bokeh: FSPass;
  key = new THREE.DirectionalLight(0xffffff, 2.2);
  rim = new THREE.PointLight(0xffffff, 60, 40, 1.6);
  constructor(renderer: THREE.WebGLRenderer) {
    const pm = new THREE.PMREMGenerator(renderer);
    this.scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.15), this.key, this.rim);
    this.rt = makeRT(W, H);
    this.rt.depthTexture = new THREE.DepthTexture(this.rt.width, this.rt.height);
    this.rt.depthTexture.type = THREE.UnsignedIntType;
    this.bokeh = new FSPass(BOKEH, {
      tCol: { value: this.rt.texture }, tDepth: { value: this.rt.depthTexture }, uRes: { value: new THREE.Vector2(this.rt.width, this.rt.height) },
      uFocus: { value: 8 }, uNear: { value: 0.1 }, uFar: { value: 300 }, uStrength: { value: 6 }, uMaxR: { value: 9 },
    }, { blending: THREE.CustomBlending, transparent: true });
    this.bokeh.mat.blendEquation = THREE.AddEquation;
    this.bokeh.mat.blendSrc = THREE.OneFactor;
    this.bokeh.mat.blendDst = THREE.OneMinusSrcAlphaFactor;
  }
  static get(renderer: THREE.WebGLRenderer) { return (shared ??= new GlassLayer(renderer)); }

  geo(kind: GeoKind): THREE.BufferGeometry {
    let g = this.geos.get(kind);
    if (!g) {
      switch (kind) {
        case 'sphere': g = new THREE.SphereGeometry(0.5, 48, 32); break;
        case 'cyl': g = new THREE.CylinderGeometry(0.5, 0.5, 1, 48, 1); break;
        case 'cone': g = new THREE.ConeGeometry(0.5, 1, 48, 1); break;
        case 'pyr': g = new THREE.ConeGeometry(0.5, 1, 4, 1); break;
        case 'prism': g = new THREE.CylinderGeometry(0.5, 0.5, 1, 6, 1); break;
        case 'torus': g = new THREE.TorusGeometry(0.38, 0.12, 24, 64); g.rotateX(Math.PI / 2); break;
        default: g = new THREE.BoxGeometry(1, 1, 1);
      }
      this.geos.set(kind, g);
    }
    return g;
  }

  setView(v: View, viewCY: number) {
    const c = this.camera, s = v.s;
    c.fov = s.fov; c.aspect = W / H;
    c.position.set(v.pos[0], v.pos[1], v.pos[2]);
    const up = new THREE.Vector3(v.up[0], v.up[1], v.up[2]), right = new THREE.Vector3(v.right[0], v.right[1], v.right[2]);
    c.up.copy(up.multiplyScalar(Math.cos(s.roll)).addScaledVector(right, -Math.sin(s.roll)));
    c.lookAt(s.tgt[0], s.tgt[1], s.tgt[2]);
    c.setViewOffset(W, H, 0, H / 2 - viewCY, W, H);
    c.updateProjectionMatrix();
    this.key.position.set(c.position.x - 4, c.position.y + 8, c.position.z + 2);
    this.rim.position.set(s.tgt[0] - v.fwd[0] * 4, s.tgt[1] + 3, s.tgt[2] - v.fwd[2] * 4);
    this.bokeh.u.uFocus!.value = s.dist;
  }

  render(renderer: THREE.WebGLRenderer, out: THREE.WebGLRenderTarget, items: GlassItem[], st: GlassStyle) {
    const seen = new Set<string>();
    for (const it of items) {
      if (it.alpha <= 0.01) continue;
      const dc = Math.hypot(it.pos[0] - this.camera.position.x, it.pos[1] - this.camera.position.y, it.pos[2] - this.camera.position.z);
      if (dc < 2.4 * Math.max(it.dims[0], it.dims[1]) * it.scale[0]) continue;   // never let a glass body swallow the lens
      seen.add(it.key);
      let m = this.meshes.get(it.key);
      if (!m) {
        m = new THREE.Mesh(this.geo(it.geo), new THREE.MeshPhysicalMaterial({ transmission: 1, metalness: 0, transparent: true, clearcoat: 1, clearcoatRoughness: 0.08, specularIntensity: 1 }));
        this.meshes.set(it.key, m);
        this.scene.add(m);
      }
      const mat = m.material as THREE.MeshPhysicalMaterial, col = new THREE.Color(it.color[0], it.color[1], it.color[2]);
      const frost = it.frost ?? 0;
      mat.color.copy(col).lerp(new THREE.Color(1, 1, 1), 0.55);
      mat.attenuationColor.copy(col);
      mat.attenuationDistance = 1.4;
      mat.roughness = Math.min(0.9, st.roughness + frost * 0.45);
      mat.ior = st.ior;
      mat.thickness = st.thickness * Math.max(it.dims[0], it.dims[2]) * it.scale[0];
      mat.transmission = 1 - frost * 0.35;
      mat.opacity = Math.min(1, it.alpha);
      mat.envMapIntensity = 1.3;
      m.visible = true;
      m.scale.set(it.dims[0] * it.scale[0], Math.max(0.001, it.dims[1] * it.scale[1]), it.dims[2] * it.scale[2]);
      m.position.set(it.pos[0], it.pos[1] + (it.y0 + it.dims[1] / 2) * it.scale[1], it.pos[2]);
      m.rotation.set(0, -it.yaw, 0);
    }
    for (const [k, m] of this.meshes) if (!seen.has(k)) m.visible = false;
    if (!seen.size) return;
    this.key.intensity = st.key;
    this.rim.color.setRGB(st.rim[0], st.rim[1], st.rim[2]);
    const cc = new THREE.Color();
    renderer.getClearColor(cc);
    const ca = renderer.getClearAlpha();
    renderer.setRenderTarget(this.rt);
    renderer.setClearColor(0x000000, 0);
    renderer.clear(true, true, true);
    renderer.render(this.scene, this.camera);
    renderer.setClearColor(cc, ca);
    this.bokeh.u.uStrength!.value = st.dof;
    this.bokeh.render(renderer, out);
  }
}
