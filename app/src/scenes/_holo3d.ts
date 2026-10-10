// 3D holo layer for the bot's plates: a real perspective camera rig (orbit / dolly / crane / fly-through),
// a library of hologram wireframe objects, floors, reveal styles and per-video style seeds. Everything is
// projected on the CPU into screen-space hairlines (LineBatch.seg2) so it shares the kit's glow + bloom look.
import { LineBatch } from '../engine/lines';
import { W, H } from '../engine/gl';
import { LIN } from '../engine/palette';
import { clamp, ease, hash, hexToLinear, lerp, mulberry32, noise1, TAU } from '../engine/util';
import type { RGB } from './_vo';

export type V3 = [number, number, number];
const add = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const mul = (a: V3, s: number): V3 => [a[0] * s, a[1] * s, a[2] * s];
const dot = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const nrm = (a: V3): V3 => mul(a, 1 / (Math.hypot(a[0], a[1], a[2]) || 1));
export const v3 = { add, sub, mul, dot, cross, nrm, lerp: (a: V3, b: V3, k: number): V3 => [lerp(a[0], b[0], k), lerp(a[1], b[1], k), lerp(a[2], b[2], k)] };
const sc = (c: RGB, s: number): RGB => [c[0] * s, c[1] * s, c[2] * s];

// ------------------------------------------------------------------ style (per video + per scene)
export const TINTS = ['#3CE1FF', '#4DFFB8', '#9B8CFF', '#FFB23D', '#5CA8FF', '#FF6FD8'] as const;
export type Floor = 'grid' | 'polar' | 'dots' | 'hex';
export type Reveal = 'scan' | 'draw' | 'assemble' | 'glitch';
export type CamMode = 'fly' | 'orbit' | 'crane' | 'dolly' | 'low' | 'top' | 'dutch' | 'spiral' | 'whip' | 'push';
export const CAM_MODES: CamMode[] = ['fly', 'orbit', 'crane', 'dolly', 'low', 'top', 'dutch', 'spiral', 'whip', 'push'];
export interface Style { tint: RGB; tintHex: string; floor: Floor; reveal: Reveal; cam: CamMode; spin: 1 | -1; hand: number; r: () => number }
/** Tint is per video (all scenes share it); floor, reveal and camera language rotate per scene and per video. */
export function styleFor(videoSeed: number, idx: number, G: any = {}): Style {
  const gl = Array.isArray(G.holo) && G.holo.length ? G.holo : null;
  const tintHex = gl ? String(gl[idx % gl.length]) : TINTS[videoSeed % TINTS.length]!;
  const r = mulberry32((videoSeed ^ Math.imul(idx + 1, 0x9e3779b1)) >>> 0);
  const rot = <T,>(xs: readonly T[], k: number) => xs[(k + (videoSeed >>> 3)) % xs.length]!;
  const gs = Array.isArray(G.scenes) ? G.scenes[idx] ?? {} : {};
  const pickOr = <T,>(v: any, ok: readonly T[], d: T): T => (ok as readonly any[]).includes(v) ? v : d;
  if (G.scenes) return {
    tint: hexToLinear(tintHex), tintHex,
    floor: pickOr(gs.floor, ['grid', 'polar', 'dots', 'hex'] as const, 'grid'),
    reveal: pickOr(gs.reveal, ['scan', 'assemble', 'draw', 'glitch'] as const, 'scan'),
    cam: pickOr(gs.cam, CAM_MODES, 'orbit'),
    spin: gs.spin === -1 ? -1 : 1, hand: Number(G.cam3d?.hand ?? 0.6 + r() * 0.8), r,
  };
  return {
    tint: hexToLinear(tintHex), tintHex,
    floor: rot(['grid', 'polar', 'dots', 'hex'] as const, idx),
    reveal: rot(['scan', 'assemble', 'draw', 'glitch'] as const, idx + (videoSeed >>> 5)),
    cam: rot(['fly', 'orbit', 'crane', 'dolly'] as const, idx * 3 + (videoSeed >>> 7)),
    spin: r() < 0.5 ? 1 : -1, hand: 0.6 + r() * 0.8, r,
  };
}

// ------------------------------------------------------------------ camera
export interface Shot { tgt: V3; yaw: number; pitch: number; dist: number; fov: number; roll: number }
interface ShotKey extends Shot { t: number; ez: (x: number) => number }
/** Spherical camera keys around a moving target: interpolating yaw/pitch/dist gives real arcs, not chords. */
export class Rig {
  keys: ShotKey[] = [];
  drift = 0;          // extra yaw rad/s on top of the keys (continuous orbit)
  t0 = 0;
  key(t: number, s: Partial<Shot> & { tgt: V3 }, ez: (x: number) => number = ease.inOutCubic) {
    const prev = this.keys[this.keys.length - 1];
    this.keys.push({ t, yaw: s.yaw ?? prev?.yaw ?? 0.6, pitch: s.pitch ?? prev?.pitch ?? 0.35, dist: s.dist ?? prev?.dist ?? 8, fov: s.fov ?? prev?.fov ?? 38, roll: s.roll ?? 0, tgt: s.tgt, ez });
    this.keys.sort((a, b) => a.t - b.t);
    return this;
  }
  at(t: number): Shot {
    const ks = this.keys;
    let s: Shot;
    if (!ks.length) s = { tgt: [0, 0.8, 0], yaw: 0.6, pitch: 0.35, dist: 8, fov: 38, roll: 0 };
    else if (t <= ks[0]!.t) s = ks[0]!;
    else if (t >= ks[ks.length - 1]!.t) s = ks[ks.length - 1]!;
    else {
      let i = 1;
      while (ks[i]!.t < t) i++;
      const a = ks[i - 1]!, b = ks[i]!, k = b.ez(clamp((t - a.t) / Math.max(1e-4, b.t - a.t)));
      s = { tgt: v3.lerp(a.tgt, b.tgt, k), yaw: lerp(a.yaw, b.yaw, k), pitch: lerp(a.pitch, b.pitch, k), dist: Math.exp(lerp(Math.log(a.dist), Math.log(b.dist), k)), fov: lerp(a.fov, b.fov, k), roll: lerp(a.roll, b.roll, k) };
    }
    return { ...s, yaw: s.yaw + this.drift * (t - this.t0) };
  }
}

/** Projection for one frame. Screen centre sits above the middle (captions own the lower third). */
export class View {
  pos: V3; fwd: V3; right: V3; up: V3; f: number; cr: number; sr: number; cx = W / 2; cy = H / 2 - 150; near = 0.2;
  constructor(public s: Shot) {
    const cp = Math.cos(s.pitch);
    this.pos = add(s.tgt, mul([cp * Math.sin(s.yaw), Math.sin(s.pitch), cp * Math.cos(s.yaw)], s.dist));
    this.fwd = nrm(sub(s.tgt, this.pos));
    this.right = nrm(cross(this.fwd, [0, 1, 0]));
    this.up = cross(this.right, this.fwd);
    this.f = (H / 2) / Math.tan((s.fov * Math.PI) / 360);
    this.cr = Math.cos(s.roll); this.sr = Math.sin(s.roll);
  }
  cam(p: V3): V3 { const d = sub(p, this.pos); return [dot(d, this.right), dot(d, this.up), dot(d, this.fwd)]; }
  scr(c: V3): [number, number] {
    const x = (this.f * c[0]) / c[2], y = (-this.f * c[1]) / c[2];
    return [this.cx + this.cr * x - this.sr * y, this.cy + this.sr * x + this.cr * y];
  }
  /** Screen position + camera depth, or null behind the camera. */
  P(p: V3): [number, number, number] | null { const c = this.cam(p); if (c[2] < this.near) return null; const s = this.scr(c); return [s[0], s[1], c[2]]; }
}

/** Glowing hairline pen in 3D: near clipping, depth fog, perspective width. */
export class Pen3 {
  fogNear: number; fogFar: number;
  constructor(public X: LineBatch, public v: View, public tint: RGB) { this.fogNear = v.s.dist * 0.9; this.fogFar = v.s.dist * 3.2; }
  seg(a: V3, b: V3, w: number, col: RGB, alpha = 1, glow = 0.16) {
    let ca = this.v.cam(a), cb = this.v.cam(b);
    const n = this.v.near;
    if (ca[2] < n && cb[2] < n) return;
    if (ca[2] < n) ca = v3.lerp(ca, cb, (n - ca[2]) / (cb[2] - ca[2]));
    else if (cb[2] < n) cb = v3.lerp(cb, ca, (n - cb[2]) / (ca[2] - cb[2]));
    const z = (ca[2] + cb[2]) / 2;
    const fog = 1 - 0.85 * clamp((z - this.fogNear) / (this.fogFar - this.fogNear));
    const k = clamp(this.v.s.dist / z, 0.55, 1.8);
    const sa = this.v.scr(ca), sb = this.v.scr(cb);
    if (glow > 0) this.X.seg2(sa[0], sa[1], sb[0], sb[1], w * k * 4, sc(col, glow), alpha * fog);
    this.X.seg2(sa[0], sa[1], sb[0], sb[1], w * k, col, alpha * fog);
  }
  poly(ps: V3[], w: number, col: RGB, alpha = 1, closed = false, glow = 0.16) {
    for (let i = 1; i < ps.length; i++) this.seg(ps[i - 1]!, ps[i]!, w, col, alpha, glow);
    if (closed && ps.length > 2) this.seg(ps[ps.length - 1]!, ps[0]!, w, col, alpha, glow);
  }
  ring(c: V3, r: number, w: number, col: RGB, alpha = 1, n = 48, from = 0, to = TAU, dash = 0, phase = 0) {
    for (let i = 0; i < n; i++) {
      if (dash && (i + Math.floor(phase)) % dash === 0) continue;
      const a0 = from + ((to - from) * i) / n, a1 = from + ((to - from) * (i + 1)) / n;
      this.seg([c[0] + r * Math.cos(a0), c[1], c[2] + r * Math.sin(a0)], [c[0] + r * Math.cos(a1), c[1], c[2] + r * Math.sin(a1)], w, col, alpha);
    }
  }
  dot(p: V3, s: number, col: RGB, alpha = 1) {
    const q = this.v.P(p); if (!q) return;
    const k = clamp(this.v.s.dist / q[2], 0.5, 2);
    this.X.seg2(q[0] - s * k * 0.5, q[1], q[0] + s * k * 0.5, q[1], s * k, col, alpha);
  }
}

// ------------------------------------------------------------------ object library
export const OBJECTS = ['server', 'db', 'globe', 'cube', 'pyramid', 'chip', 'router', 'cloud', 'lock', 'gear', 'user', 'phone', 'laptop', 'stack', 'shield', 'helix', 'bot'] as const;
export type Obj = typeof OBJECTS[number];
export const asObj = (s: any, k = 0): Obj => (OBJECTS as readonly string[]).includes(s) ? s : OBJECTS[k % OBJECTS.length]!;
type Seg = [V3, V3];
export interface Shape { segs: Seg[]; leds: V3[]; h: number }

export function shape(kind: Obj, t: number): Shape {
  const segs: Seg[] = [], leds: V3[] = [];
  const ringY = (y: number, r: number, n = 28) => { for (let i = 0; i < n; i++) { const a = (i / n) * TAU, b = ((i + 1) / n) * TAU; segs.push([[r * Math.cos(a), y, r * Math.sin(a)], [r * Math.cos(b), y, r * Math.sin(b)]]); } };
  const ringZ = (cx: number, cy: number, z: number, r: number, n = 24, a0 = 0, a1 = TAU) => { for (let i = 0; i < n; i++) { const a = a0 + ((a1 - a0) * i) / n, b = a0 + ((a1 - a0) * (i + 1)) / n; segs.push([[cx + r * Math.cos(a), cy + r * Math.sin(a), z], [cx + r * Math.cos(b), cy + r * Math.sin(b), z]]); } };
  const box = (w: number, h: number, d: number, y0 = 0) => {
    const c: V3[] = [[-w, y0, -d], [w, y0, -d], [w, y0, d], [-w, y0, d], [-w, y0 + h, -d], [w, y0 + h, -d], [w, y0 + h, d], [-w, y0 + h, d]];
    for (const [a, b] of [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]]) segs.push([c[a!]!, c[b!]!]);
  };
  const rect = (pts: V3[]) => { for (let i = 0; i < pts.length; i++) segs.push([pts[i]!, pts[(i + 1) % pts.length]!]); };
  switch (kind) {
    case 'server': {
      box(0.5, 1.7, 0.5);
      for (const y of [0.2, 0.67, 1.14]) {
        const z = 0.505;
        rect([[-0.4, y, z], [0.4, y, z], [0.4, y + 0.3, z], [-0.4, y + 0.3, z]]);
        for (let k = 0; k < 2; k++) if (Math.sin(t * 5 + y * 7 + k * 2) > -0.2) leds.push([0.14 + k * 0.14, y + 0.15, z]);
      }
      return { segs, leds, h: 1.7 };
    }
    case 'db': {
      for (const y of [0, 0.42, 0.84, 1.25]) ringY(y, 0.62);
      for (let i = 0; i < 8; i++) { const a = (i / 8) * TAU; segs.push([[0.62 * Math.cos(a), 0, 0.62 * Math.sin(a)], [0.62 * Math.cos(a), 1.25, 0.62 * Math.sin(a)]]); }
      for (const y of [0.21, 0.63, 1.04]) if (Math.sin(t * 4 + y * 9) > 0) leds.push([0, y, 0.62]);
      return { segs, leds, h: 1.25 };
    }
    case 'globe': {
      const cy = 0.78, r = 0.72;
      for (const k of [-0.6, -0.3, 0, 0.3, 0.6]) { const rr = r * Math.sqrt(1 - k * k); for (let i = 0; i < 28; i++) { const a = (i / 28) * TAU, b = ((i + 1) / 28) * TAU; segs.push([[rr * Math.cos(a), cy + k * r, rr * Math.sin(a)], [rr * Math.cos(b), cy + k * r, rr * Math.sin(b)]]); } }
      for (let j = 0; j < 4; j++) {
        const a0 = t * 0.5 + (j * Math.PI) / 4;
        for (let i = 0; i < 28; i++) { const u = (i / 28) * TAU, v = ((i + 1) / 28) * TAU; segs.push([[r * Math.cos(u) * Math.cos(a0), cy + r * Math.sin(u), r * Math.cos(u) * Math.sin(a0)], [r * Math.cos(v) * Math.cos(a0), cy + r * Math.sin(v), r * Math.cos(v) * Math.sin(a0)]]); }
      }
      return { segs, leds, h: 1.5 };
    }
    case 'cube': box(0.6, 1.2, 0.6); box(0.36, 0.72, 0.36, 0.24 + 0.05 * Math.sin(t * 2)); return { segs, leds, h: 1.2 };
    case 'pyramid': {
      const b: V3[] = [[-0.7, 0, -0.7], [0.7, 0, -0.7], [0.7, 0, 0.7], [-0.7, 0, 0.7]], apex: V3 = [0, 1.35, 0];
      for (let i = 0; i < 4; i++) segs.push([b[i]!, b[(i + 1) % 4]!], [b[i]!, apex]);
      for (const y of [0.45, 0.9]) { const s = 0.7 * (1 - y / 1.35); rect([[-s, y, -s], [s, y, -s], [s, y, s], [-s, y, s]]); }
      leds.push(apex);
      return { segs, leds, h: 1.35 };
    }
    case 'chip': {
      box(0.62, 0.18, 0.62); box(0.3, 0.12, 0.3, 0.18);
      for (let i = 0; i < 4; i++) { const o = -0.42 + i * 0.28; segs.push([[o, 0.09, -0.62], [o, 0.09, -0.85]], [[0.62, 0.09, o], [0.85, 0.09, o]], [[o, 0.09, 0.62], [o, 0.09, 0.85]], [[-0.62, 0.09, o], [-0.85, 0.09, o]]); }
      if (Math.sin(t * 4) > 0) leds.push([0, 0.32, 0]);
      return { segs, leds, h: 0.5 };
    }
    case 'router': {
      box(0.75, 0.24, 0.45);
      for (const x of [-0.55, 0.55]) segs.push([[x, 0.24, -0.4], [x * 1.1, 1.0, -0.5]]);
      for (let k = 0; k < 5; k++) if (Math.sin(t * 6 + k * 1.7) > -0.3) leds.push([-0.5 + k * 0.25, 0.12, 0.455]);
      for (let k = 1; k <= 3; k++) { const ph = (t * 0.8 + k / 3) % 1; ringZ(0, 0.3, -0.45, 0.25 + ph * 0.55, 16, Math.PI * 0.25, Math.PI * 0.75); }
      return { segs, leds, h: 1.0 };
    }
    case 'cloud': {
      const puffs: [number, number, number][] = [[-0.45, 0.5, 0.32], [0, 0.72, 0.44], [0.45, 0.52, 0.32]];
      for (const z of [-0.2, 0.2]) {
        for (const [x, y, r] of puffs) ringZ(x, y, z, r, 22, -0.15, Math.PI + 0.15);
        segs.push([[-0.78, 0.36, z], [0.78, 0.36, z]]);
      }
      for (const [x, y] of [[-0.78, 0.36], [0.78, 0.36], [0, 1.16]] as const) segs.push([[x, y, -0.2], [x, y, 0.2]]);
      return { segs, leds, h: 1.16 };
    }
    case 'lock': {
      box(0.5, 0.65, 0.22);
      for (const z of [-0.08, 0.08]) ringZ(0, 0.65, z, 0.32, 18, 0, Math.PI);
      ringZ(0, 0.36, 0.225, 0.08, 12);
      segs.push([[0, 0.28, 0.225], [0, 0.16, 0.225]]);
      if (Math.sin(t * 3) > 0) leds.push([0, 0.36, 0.225]);
      return { segs, leds, h: 0.97 };
    }
    case 'gear': {
      const n = 10, R = 0.55, ro = 0.72, a0 = t * 0.6;
      for (const y of [0.3, 0.55]) {
        for (let i = 0; i < n; i++) {
          const a = a0 + (i / n) * TAU, d = TAU / n;
          const p = (r: number, aa: number): V3 => [r * Math.cos(aa), y, r * Math.sin(aa)];
          segs.push([p(R, a), p(R, a + d * 0.3)], [p(R, a + d * 0.3), p(ro, a + d * 0.38)], [p(ro, a + d * 0.38), p(ro, a + d * 0.62)], [p(ro, a + d * 0.62), p(R, a + d * 0.7)], [p(R, a + d * 0.7), p(R, a + d)]);
          if (y === 0.3) segs.push([p(ro, a + d * 0.5), [ro * Math.cos(a + d * 0.5), 0.55, ro * Math.sin(a + d * 0.5)]]);
        }
        for (let i = 0; i < 16; i++) { const a = (i / 16) * TAU, b = ((i + 1) / 16) * TAU; segs.push([[0.2 * Math.cos(a), y, 0.2 * Math.sin(a)], [0.2 * Math.cos(b), y, 0.2 * Math.sin(b)]]); }
      }
      return { segs, leds, h: 0.8 };
    }
    case 'user': {
      ringY(0, 0.55); ringY(0.7, 0.32); ringY(0.38, 0.46, 24);
      for (let i = 0; i < 8; i++) { const a = (i / 8) * TAU; segs.push([[0.55 * Math.cos(a), 0, 0.55 * Math.sin(a)], [0.32 * Math.cos(a), 0.7, 0.32 * Math.sin(a)]]); }
      for (let i = 0; i < 22; i++) { const a = (i / 22) * TAU, b = ((i + 1) / 22) * TAU; segs.push([[0.26 * Math.cos(a), 1.12, 0.26 * Math.sin(a)], [0.26 * Math.cos(b), 1.12, 0.26 * Math.sin(b)]]); }
      for (let j = 0; j < 2; j++) { const a = t * 0.8 + j * Math.PI / 2; for (let i = 0; i < 22; i++) { const u = (i / 22) * TAU, v = ((i + 1) / 22) * TAU; segs.push([[0.26 * Math.cos(u) * Math.cos(a), 1.12 + 0.26 * Math.sin(u), 0.26 * Math.cos(u) * Math.sin(a)], [0.26 * Math.cos(v) * Math.cos(a), 1.12 + 0.26 * Math.sin(v), 0.26 * Math.cos(v) * Math.sin(a)]]); } }
      return { segs, leds, h: 1.4 };
    }
    case 'phone': {
      box(0.36, 1.3, 0.07);
      rect([[-0.3, 0.16, 0.075], [0.3, 0.16, 0.075], [0.3, 1.16, 0.075], [-0.3, 1.16, 0.075]]);
      for (let k = 0; k < 4; k++) { const y = 0.95 - k * 0.2, wv = 0.18 + 0.08 * Math.sin(t * 3 + k); segs.push([[-0.22, y, 0.075], [-0.22 + wv * 2, y, 0.075]]); }
      leds.push([0, 1.24, 0.075]);
      return { segs, leds, h: 1.3 };
    }
    case 'laptop': {
      box(0.75, 0.06, 0.48);
      rect([[-0.75, 0.06, -0.48], [0.75, 0.06, -0.48], [0.75, 1.02, -0.68], [-0.75, 1.02, -0.68]]);
      rect([[-0.64, 0.16, -0.5], [0.64, 0.16, -0.5], [0.64, 0.93, -0.66], [-0.64, 0.93, -0.66]]);
      for (let k = 0; k < 4; k++) { const u = 0.28 + k * 0.17, w0 = 0.3 + 0.25 * Math.abs(Math.sin(t * 2 + k)); segs.push([[-0.55, 0.06 + u * 0.96, -0.48 - u * 0.2], [-0.55 + w0 * 1.6, 0.06 + u * 0.96, -0.48 - u * 0.2]]); }
      return { segs, leds, h: 1.02 };
    }
    case 'stack': {
      for (let k = 0; k < 3; k++) box(0.7, 0.14, 0.7, k * 0.4 + 0.05 * Math.sin(t * 2 + k));
      for (let k = 0; k < 3; k++) if (Math.sin(t * 5 + k * 2) > 0) leds.push([0.5, k * 0.4 + 0.07 + 0.05 * Math.sin(t * 2 + k), 0.705]);
      return { segs, leds, h: 1.0 };
    }
    case 'shield': {
      const out: [number, number][] = [[-0.6, 1.25], [0, 1.4], [0.6, 1.25], [0.58, 0.7], [0.35, 0.28], [0, 0], [-0.35, 0.28], [-0.58, 0.7]];
      for (const z of [-0.12, 0.12]) for (let i = 0; i < out.length; i++) { const a = out[i]!, b = out[(i + 1) % out.length]!; segs.push([[a[0], a[1], z], [b[0], b[1], z]]); }
      for (const [x, y] of out) segs.push([[x, y, -0.12], [x, y, 0.12]]);
      segs.push([[-0.26, 0.72, 0.13], [-0.06, 0.5, 0.13]], [[-0.06, 0.5, 0.13], [0.3, 0.95, 0.13]]);
      return { segs, leds, h: 1.4 };
    }
    case 'helix': {
      const n = 40, hh = 1.6, r = 0.42, ph = t * 1.2;
      for (const off of [0, Math.PI]) for (let i = 0; i < n; i++) {
        const a = ph + off + (i / n) * TAU * 1.5, b = ph + off + ((i + 1) / n) * TAU * 1.5;
        segs.push([[r * Math.cos(a), (i / n) * hh, r * Math.sin(a)], [r * Math.cos(b), ((i + 1) / n) * hh, r * Math.sin(b)]]);
      }
      for (let i = 0; i < n; i += 4) { const a = ph + (i / n) * TAU * 1.5, y = (i / n) * hh; segs.push([[r * Math.cos(a), y, r * Math.sin(a)], [-r * Math.cos(a), y, -r * Math.sin(a)]]); }
      return { segs, leds, h: hh };
    }
    case 'bot': {
      box(0.5, 0.75, 0.42, 0.1);
      box(0.32, 0.12, 0.3, 0.85);
      segs.push([[0, 0.97, 0], [0, 1.25, 0]]);
      const blink = Math.sin(t * 2.3) > 0.92 ? 0.02 : 0.1;
      for (const x of [-0.2, 0.2]) rect([[x - 0.08, 0.5 - blink, 0.425], [x + 0.08, 0.5 - blink, 0.425], [x + 0.08, 0.5 + blink, 0.425], [x - 0.08, 0.5 + blink, 0.425]]);
      segs.push([[-0.18, 0.28, 0.425], [0.18, 0.28, 0.425]]);
      leds.push([0, 1.3, 0]);
      return { segs, leds, h: 1.32 };
    }
  }
}

/** Draw an object at `o` (scale s, yaw) with reveal progress p in [0,1] in one of the reveal styles. */
export function drawObj(P: Pen3, kind: Obj, o: V3, s: number, yaw: number, p: number, t: number, reveal: Reveal, col: RGB, seed = 1, hot = 0) {
  if (p <= 0) return;
  const { segs, leds, h } = shape(kind, t);
  const cy = Math.cos(yaw), sy = Math.sin(yaw);
  const X = (q: V3): V3 => [o[0] + s * (q[0] * cy - q[2] * sy), o[1] + s * q[1], o[2] + s * (q[0] * sy + q[2] * cy)];
  const flick = p < 1 ? 0.65 + 0.35 * Math.abs(Math.sin(t * 37 + seed)) : 1;
  const base = sc(col, 1.1 + hot * 1.5);
  const n = segs.length;
  const ycut = (h + 0.05) * ease.inOutQuad(p);
  segs.forEach(([a0, b0], i) => {
    let a = a0, b = b0, alpha = flick;
    if (reveal === 'scan' && p < 1) {
      if (a[1] > ycut && b[1] > ycut) return;
      if (a[1] > ycut || b[1] > ycut) {
        const u = (ycut - a[1]) / (b[1] - a[1] || 1e-9);
        const m: V3 = [a[0] + (b[0] - a[0]) * u, ycut, a[2] + (b[2] - a[2]) * u];
        if (a[1] > ycut) a = m; else b = m;
      }
    } else if (reveal === 'draw' && p < 1) {
      const u = clamp(p * 1.25 * n - i * 0.95);
      if (u <= 0) return;
      b = v3.lerp(a, b, u);
    } else if (reveal === 'assemble' && p < 1) {
      const r = hash(i, seed), q = ease.outCubic(clamp(p * 1.4 - r * 0.4));
      const mid = v3.mul(v3.add(a, b), 0.5);
      const dir = v3.nrm([mid[0] + 0.01, mid[1] - h / 2, mid[2] + 0.01]);
      const off = v3.mul(v3.add(dir, [0, 0.6 * (r - 0.3), 0]), 2.6 * (1 - q));
      a = v3.add(a, off); b = v3.add(b, off);
      alpha *= q;
    } else if (reveal === 'glitch' && p < 1) {
      const r = hash(i, seed);
      if (r > p * 1.15) return;
      alpha *= hash(i, Math.round(t * 30), seed) > 0.25 ? 1 : 0.15;
    }
    P.seg(X(a), X(b), 2.0, base, alpha, 0.16);
  });
  if (reveal === 'scan' && p < 1) P.ring(X([0, ycut, 0]), 0.95 * s, 3, sc(LIN.signal, 2.2), 1, 40);
  for (const l of leds) if (p >= 1 || l[1] <= ycut) P.dot(X(l), 7, sc(LIN.signal, 2.6), 1);
}

/** Pedestal under an object: solid ring + rotating dashed ring. */
export function pedestal(P: Pen3, o: V3, r: number, t: number, a: number, col: RGB) {
  P.ring(o, r, 1.5, sc(col, 0.55), 0.6 * a, 48);
  P.ring(o, r * 1.3, 1.6, sc(LIN.signal, 0.9), 0.7 * a, 48, t * 0.6, t * 0.6 + TAU, 3, t * 8);
}

/** A floor plane at y=c[1] around c, revealed as a widening disc (rv in [0,1]). */
export function floor(P: Pen3, kind: Floor, c: V3, R: number, rv: number, col: RGB, t: number) {
  if (rv <= 0) return;
  const rad = R * ease.outCubic(rv);
  const dim = sc(col, 0.32);
  const y = c[1];
  const fade = (x: number, z: number) => clamp(1 - Math.hypot(x, z) / rad) * 0.9;
  if (kind === 'grid' || kind === 'hex') {
    const step = kind === 'grid' ? 1 : 1.2;
    for (let g = -R; g <= R + 1e-6; g += step) {
      for (let u = -R; u < R; u += step / 2) {
        const f1 = fade(g, u + step / 4), f2 = fade(u + step / 4, g);
        if (f1 > 0) P.seg([c[0] + g, y, c[2] + u], [c[0] + g, y, c[2] + u + step / 2], 1.1, dim, f1, 0);
        if (kind === 'grid' && f2 > 0) P.seg([c[0] + u, y, c[2] + g], [c[0] + u + step / 2, y, c[2] + g], 1.1, dim, f2, 0);
      }
    }
    if (kind === 'hex') for (let g = -R; g <= R; g += step) for (let u = -R; u <= R; u += step) {
      const f = fade(g + u * 0.5, u); if (f <= 0) continue;
      P.seg([c[0] + g + u * 0.5, y, c[2] + u], [c[0] + g + u * 0.5 + step * 0.5, y, c[2] + u - step * 0.86], 1.1, dim, f, 0);
    }
  } else if (kind === 'polar') {
    for (let r = 1; r <= R; r += 1) if (r <= rad) P.ring(c, r, 1.1, dim, 0.8 * (1 - r / (R + 1)), 64);
    for (let i = 0; i < 16; i++) { const a = (i / 16) * TAU + t * 0.03; P.seg(c, [c[0] + rad * Math.cos(a), y, c[2] + rad * Math.sin(a)], 1, dim, 0.5, 0); }
  } else {
    for (let x = -R; x <= R; x += 0.75) for (let z = -R; z <= R; z += 0.75) { const f = fade(x, z); if (f > 0) P.dot([c[0] + x, y, c[2] + z], 3, sc(col, 0.8), f); }
  }
  if (rv < 1) P.ring(c, rad, 2.5, sc(LIN.signal, 1.6), 1 - rv, 72);
}

/** A lifted arc between two points (quadratic, peak `lift`), as n+1 points. */
export function arcPts(a: V3, b: V3, lift: number, n = 28): V3[] {
  const m: V3 = [(a[0] + b[0]) / 2, Math.max(a[1], b[1]) + lift, (a[2] + b[2]) / 2];
  const out: V3[] = [];
  for (let i = 0; i <= n; i++) { const u = i / n, k = 1 - u; out.push([k * k * a[0] + 2 * k * u * m[0] + u * u * b[0], k * k * a[1] + 2 * k * u * m[1] + u * u * b[1], k * k * a[2] + 2 * k * u * m[2] + u * u * b[2]]); }
  return out;
}
const along = (ps: V3[], u: number): V3 => { const f = clamp(u) * (ps.length - 1), i = Math.floor(f); return v3.lerp(ps[i]!, ps[Math.min(ps.length - 1, i + 1)]!, f - i); };
export { along };
/** A link growing over grow in [0,1], with packets streaming once live > 0. */
export function link(P: Pen3, ps: V3[], grow: number, live: number, t: number, col: RGB, speed = 0.5, phase = 0, both = false) {
  if (grow <= 0) return;
  const m = Math.max(1, Math.floor((ps.length - 1) * clamp(grow)));
  for (let i = 1; i <= m; i++) if (i % 2 === 1) P.seg(ps[i - 1]!, ps[i]!, 1.4, sc(col, 0.7), 0.85, 0.1);
  if (grow < 1) P.dot(ps[m]!, 9, sc(LIN.signal, 2.5), 1);
  if (live <= 0) return;
  for (const dir of both ? [1, -1] : [1]) for (let k = 0; k < 2; k++) {
    let u = (t * speed + phase + k * 0.5 + (dir < 0 ? 0.25 : 0)) % 1;
    if (dir < 0) u = 1 - u;
    for (let j = 0; j < 6; j++) {
      const q = along(ps, u - dir * j * 0.015), r = along(ps, u - dir * (j + 1) * 0.015);
      const fade = 1 - j / 6;
      P.seg(q, r, (j === 0 ? 6 : 3) * fade + 1, sc(j === 0 ? LIN.ember : LIN.signal, (j === 0 ? 3 : 1.8) * fade), live * fade, 0.05);
    }
  }
}

/** Handheld micro-shake on a shot (deterministic). */
export function handheld(s: Shot, t: number, amt: number): Shot {
  return { ...s, yaw: s.yaw + 0.006 * amt * noise1(t * 0.7, 11), pitch: s.pitch + 0.005 * amt * noise1(t * 0.6, 12), roll: s.roll + 0.004 * amt * noise1(t * 0.5, 13) };
}
