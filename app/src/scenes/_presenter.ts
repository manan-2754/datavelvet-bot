// "Vel", DataVelvet's own 3D presenter (an original character: big friendly head, round glasses, purple hoodie).
// Built from shaded primitives with a tiny rig (shoulders, elbows, head, eyes, brows, mouth) and rendered in the
// bottom band of the frame on top of the 3D world. The mouth follows the narration loudness, the eyes blink, and
// every beat has a gesture (wave, point at the screen, explain, think, shrug, thumbs up) blended in smoothly.
import * as THREE from 'three';
import { clamp, ease } from '../engine/util';

export type Gesture = 'idle' | 'wave' | 'point' | 'explain' | 'think' | 'shrug' | 'thumbs' | 'wow';
interface ArmPose { z: number; x: number; e: number }
interface Pose { L: ArmPose; R: ArmPose; up: number; tilt: number; look: number; brow: number }

const idle: Pose = { L: { z: 0.12, x: -0.1, e: -0.25 }, R: { z: -0.12, x: -0.1, e: -0.25 }, up: 0, tilt: 0, look: 0.15, brow: 0 };
const POSES: Record<Gesture, Pose> = {
  idle,
  wave: { ...idle, L: { z: 2.55, x: -0.1, e: -0.5 }, brow: 0.5 },
  point: { ...idle, L: { z: 2.2, x: -0.35, e: -0.1 }, look: 0.45, brow: 0.3 },
  explain: { ...idle, L: { z: 0.55, x: -0.95, e: -0.95 }, R: { z: -0.55, x: -0.95, e: -0.95 }, look: 0.1 },
  think: { ...idle, R: { z: -0.3, x: -1.75, e: -2.15 }, tilt: 0.12, look: 0.35, brow: 0.6 },
  shrug: { ...idle, L: { z: 0.75, x: -0.55, e: -1.25 }, R: { z: -0.75, x: -0.55, e: -1.25 }, up: 0.07, tilt: -0.12, brow: 0.8 },
  thumbs: { ...idle, L: { z: 0.45, x: -1.15, e: -1.15 }, R: { z: -0.45, x: -1.15, e: -1.15 }, brow: 0.4 },
  wow: { ...idle, L: { z: 1.1, x: -0.7, e: -1.6 }, R: { z: -1.1, x: -0.7, e: -1.6 }, brow: 1, up: 0.04 },
};
const lerpArm = (a: ArmPose, b: ArmPose, k: number): ArmPose => ({ z: a.z + (b.z - a.z) * k, x: a.x + (b.x - a.x) * k, e: a.e + (b.e - a.e) * k });

export class Presenter {
  scene = new THREE.Scene();
  cam = new THREE.PerspectiveCamera(30, 1080 / 615, 0.1, 50);
  root = new THREE.Group();
  head = new THREE.Group();
  eyes: THREE.Group[] = [];
  pupils: THREE.Mesh[] = [];
  brows: THREE.Mesh[] = [];
  mouth: THREE.Mesh;
  arms: { sh: THREE.Group; el: THREE.Group; thumb: THREE.Mesh }[] = [];
  constructor(env: THREE.Texture, outfit: THREE.Color) {
    this.scene.environment = env;
    this.scene.environmentIntensity = 0.9;
    const key = new THREE.DirectionalLight(0xffffff, 2.2); key.position.set(-2, 3, 4);
    const rim = new THREE.DirectionalLight(0xffffff, 1.4); rim.position.set(3, 2, -2);
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x666677, 0.5), key, rim, this.root);
    const mat = (c: string | THREE.Color, r = 0.55, o: Partial<THREE.MeshPhysicalMaterialParameters> = {}) => new THREE.MeshPhysicalMaterial({ color: c, roughness: r, clearcoat: 0.2, ...o });
    const skin = mat('#F1C4A0', 0.6, { sheen: 0.4, sheenColor: new THREE.Color('#ffb59a') }), hoodie = mat(outfit, 0.75), hoodDark = mat(outfit.clone().multiplyScalar(0.7), 0.8),
      hair = mat('#2B1D16', 0.5), dark = mat('#14161C', 0.3), white = mat('#FFFFFF', 0.25);
    const M = (g: THREE.BufferGeometry, m: THREE.Material, p: [number, number, number], s?: [number, number, number], parent: THREE.Object3D = this.root) => {
      const x = new THREE.Mesh(g, m); x.position.set(...p); if (s) x.scale.set(...s); parent.add(x); return x;
    };
    M(new THREE.CapsuleGeometry(0.42, 0.6, 12, 32), hoodie, [0, 0, 0], [1.2, 1, 0.78]);                    // torso
    M(new THREE.TorusGeometry(0.27, 0.1, 16, 40), hoodDark, [0, 0.6, -0.08], [1.1, 1, 0.8]).rotation.x = Math.PI / 2.4;  // hood
    for (const x of [-0.09, 0.09]) M(new THREE.CylinderGeometry(0.014, 0.014, 0.3), white, [x, 0.33, 0.33]);  // strings
    M(new THREE.CircleGeometry(0.1, 40), new THREE.MeshBasicMaterial({ color: '#ffffff' }), [0.2, 0.25, 0.335]);   // chest badge
    M(new THREE.CylinderGeometry(0.13, 0.15, 0.25, 24), skin, [0, 0.68, 0]);                               // neck
    this.head.position.set(0, 1.08, 0); this.root.add(this.head);
    M(new THREE.SphereGeometry(0.42, 48, 36), skin, [0, 0, 0], [1, 1.06, 0.96], this.head);
    const cap = M(new THREE.SphereGeometry(0.45, 48, 24, 0, Math.PI * 2, 0, Math.PI * 0.52), hair, [0, 0.03, -0.03], [1, 1.05, 1], this.head); cap.rotation.x = -0.35;
    M(new THREE.SphereGeometry(0.2, 32, 20), hair, [0.12, 0.33, 0.25], [1.5, 0.5, 0.8], this.head).rotation.z = -0.4;   // fringe swoosh
    for (const s of [-1, 1]) {
      M(new THREE.SphereGeometry(0.08, 20, 16), skin, [s * 0.41, -0.02, 0], [0.6, 1, 0.8], this.head);   // ears
      const eye = new THREE.Group(); eye.position.set(s * 0.15, 0.04, 0.36); this.head.add(eye); this.eyes.push(eye);
      M(new THREE.SphereGeometry(0.075, 24, 18), white, [0, 0, 0], [1, 1, 0.6], eye);
      this.pupils.push(M(new THREE.SphereGeometry(0.042, 20, 14), dark, [0, 0, 0.04], [1, 1, 0.6], eye));
      M(new THREE.TorusGeometry(0.105, 0.013, 10, 40), dark, [s * 0.15, 0.04, 0.4], undefined, this.head);   // round glasses
      this.brows.push(M(new THREE.CapsuleGeometry(0.018, 0.09, 6, 12), hair, [s * 0.15, 0.2, 0.38], undefined, this.head));
      this.brows[this.brows.length - 1]!.rotation.z = Math.PI / 2 + s * 0.1;
    }
    M(new THREE.CylinderGeometry(0.01, 0.01, 0.09), dark, [0, 0.05, 0.42], undefined, this.head).rotation.z = Math.PI / 2;   // glasses bridge
    M(new THREE.SphereGeometry(0.045, 20, 14), skin, [0, -0.06, 0.42], undefined, this.head);                                 // nose
    this.mouth = M(new THREE.SphereGeometry(1, 24, 16), mat('#7A2430', 0.5), [0, -0.2, 0.37], [0.09, 0.02, 0.04], this.head);
    for (const s of [-1, 1]) {                                                                           // arms: shoulder -> elbow -> hand
      const sh = new THREE.Group(); sh.position.set(s * 0.5, 0.36, 0); this.root.add(sh);
      M(new THREE.CapsuleGeometry(0.11, 0.3, 8, 20), hoodie, [0, -0.2, 0], undefined, sh);
      const el = new THREE.Group(); el.position.set(0, -0.42, 0); sh.add(el);
      M(new THREE.CapsuleGeometry(0.1, 0.28, 8, 20), hoodie, [0, -0.18, 0], undefined, el);
      M(new THREE.SphereGeometry(0.11, 24, 18), skin, [0, -0.42, 0], [1, 1.1, 0.8], el);
      const thumb = M(new THREE.CapsuleGeometry(0.03, 0.08, 6, 12), skin, [-s * 0.08, -0.38, 0.06], undefined, el);
      this.arms.push({ sh, el, thumb });
    }
    this.cam.position.set(1.15, 0.78, 4.4); this.cam.lookAt(1.15, 0.68, 0);
  }

  /** Pose at time t: gesture g started at t0 (blended from prev), talk = narration loudness 0..1. */
  update(t: number, g: Gesture, prev: Gesture, t0: number, talk: number) {
    const k = ease.inOutCubic(clamp((t - t0) / 0.35)), A = POSES[prev] ?? idle, B = POSES[g] ?? idle;
    const R = lerpArm(A.R, B.R, k), L = lerpArm(A.L, B.L, k);
    const up = A.up + (B.up - A.up) * k, tilt = A.tilt + (B.tilt - A.tilt) * k, look = A.look + (B.look - A.look) * k, brow = A.brow + (B.brow - A.brow) * k;
    const sway = Math.sin(t * 1.6) * 0.03, bob = Math.abs(Math.sin(t * 5)) * 0.015 * talk;
    [R, L].forEach((p, i) => {
      const a = this.arms[i]!, s = i ? 1 : -1;
      a.sh.rotation.set(p.x + sway * 0.5, 0, p.z + s * sway * 0.3);
      a.sh.position.y = 0.36 + up;
      a.el.rotation.x = p.e + (g === 'wave' && i === 1 ? 0.35 * Math.sin(t * 11) * k : 0) + (g === 'explain' ? 0.12 * Math.sin(t * 4 + i) * talk : 0);
      a.thumb.scale.setScalar(g === 'thumbs' ? 1.4 : 1);
      a.thumb.position.y = g === 'thumbs' ? -0.3 : -0.38;
    });
    this.root.rotation.z = sway * 0.4;
    this.root.position.y = bob;
    this.head.rotation.set(-0.06 + 0.05 * talk * Math.sin(t * 7), look * 0.6 + 0.05 * Math.sin(t * 0.7), tilt);
    const blink = (t % 3.7) < 0.12 || ((t + 1.3) % 5.3) < 0.1 ? 0.1 : 1;
    this.eyes.forEach((e) => (e.scale.y = blink));
    this.pupils.forEach((p) => p.position.set(0.02 + look * 0.04, g === 'think' ? 0.03 : 0, 0.04));
    this.brows.forEach((b) => (b.position.y = 0.2 + 0.05 * brow));
    this.mouth.scale.set(0.09 - 0.02 * talk, 0.018 + 0.075 * talk, 0.04);
  }

  /** Draw into the bottom band of `out` (keeps the world's colour, only clears depth). */
  render(renderer: THREE.WebGLRenderer, out: THREE.WebGLRenderTarget, band = 0.32) {
    const w = out.width, h = Math.round(out.height * band);
    this.cam.aspect = w / h; this.cam.updateProjectionMatrix();
    const ac = renderer.autoClear; renderer.autoClear = false;
    out.viewport.set(0, 0, w, h); out.scissor.set(0, 0, w, h); out.scissorTest = true;
    renderer.setRenderTarget(out);
    renderer.clearDepth();
    renderer.render(this.scene, this.cam);
    out.viewport.set(0, 0, out.width, out.height); out.scissor.set(0, 0, out.width, out.height); out.scissorTest = false;
    renderer.setRenderTarget(out);
    renderer.autoClear = ac;
  }
}
