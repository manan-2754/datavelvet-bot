// 3D holo plates (the holo bot's look, inside the kit engine): every plate is a GenPlate with the live 3D layer
// on, a perspective rig whose camera language (fly / orbit / crane / dolly), floor, reveal style and tint come
// from the video seed + scene index, so no two videos (and no two scenes) move the same way.
import { LIN } from '../engine/palette';
import { F } from '../engine/type';
import { type Word } from '../engine/lyrics';
import { clamp, ease, prog, pulse, TAU } from '../engine/util';
import { type Cam, type RGB } from './_vo';
import { GenPlate, typeText, fitSize } from './_gen';
import { asObj, drawObj, pedestal, arcPts, link, shape, v3, type Obj, type Pen3, type V3 } from './_holo3d';

const items = (d: any, max: number) => (Array.isArray(d?.items) ? d.items : []).slice(0, max);
const numIn = (v: any) => { const m = String(v ?? '').replace(/,/g, '').match(/-?\d+(\.\d+)?/); return m ? parseFloat(m[0]) : null; };
const up = (s: any, n: number) => String(s ?? '').slice(0, n).toUpperCase();
const scl = (c: RGB, s: number): RGB => [c[0] * s, c[1] * s, c[2] * s];
function counting(v: any, k: number) {
  const s = String(v ?? '');
  const m = s.match(/\d[\d,]*(\.\d+)?/);
  if (!m) return s;
  const target = parseFloat(m[0].replace(/,/g, ''));
  const cur = target * ease.outCubic(clamp(k));
  const dec = m[1] ? m[1].length - 1 : 0;
  return s.replace(m[0], m[0].includes(',') ? Math.round(cur).toLocaleString('en-US') : cur.toFixed(dec));
}

/** Camera language for a set of beats (time, focus point, close distance) and a wide framing. */
function plan(pl: GenPlate, tg: { t: number; p: V3; d: number }[], wide: { tgt: V3; dist: number }) {
  const st = pl.style, R = pl.rig, sp = st.spin, y0 = (0.3 + st.r() * 0.5) * sp, t0 = pl.t0, t1 = pl.t1, n = Math.max(1, tg.length);
  if (st.cam === 'fly') {
    R.key(t0, { tgt: wide.tgt, yaw: y0 - 0.6 * sp, pitch: 0.62, dist: wide.dist * 1.15, fov: 50 });
    tg.forEach((g, k) => R.key(Math.max(t0 + 0.3, g.t - 0.1), { tgt: g.p, yaw: y0 + k * 0.42 * sp, pitch: 0.28 + 0.08 * (k % 2), dist: g.d, fov: 48 }));
    R.key(t1, { tgt: wide.tgt, yaw: y0 + (n + 0.6) * 0.42 * sp, pitch: 0.42, dist: wide.dist, fov: 50 });
  } else if (st.cam === 'orbit') {
    R.drift = 0.2 * sp;
    R.key(t0, { tgt: wide.tgt, yaw: y0, pitch: 0.52, dist: wide.dist * 1.12, fov: 50 });
    tg.forEach((g) => R.key(g.t, { tgt: v3.lerp(wide.tgt, g.p, 0.45), yaw: y0, pitch: 0.34, dist: wide.dist * 0.84 }));
    R.key(t1, { tgt: wide.tgt, yaw: y0, pitch: 0.44, dist: wide.dist * 0.98 });
  } else if (st.cam === 'crane') {
    R.key(t0, { tgt: wide.tgt, yaw: y0, pitch: 1.28, dist: wide.dist * 1.05, fov: 50 });
    tg.forEach((g, k) => R.key(g.t, { tgt: v3.lerp(wide.tgt, g.p, 0.6), yaw: y0 + k * 0.14 * sp, pitch: 1.12 - 0.9 * ((k + 1) / n), dist: wide.dist * 0.8 }));
    R.key(t1, { tgt: wide.tgt, yaw: y0 + 0.5 * sp, pitch: 0.24, dist: wide.dist * 0.96 });
  } else {
    R.key(t0, { tgt: tg[0]?.p ?? wide.tgt, yaw: y0, pitch: 0.2, dist: wide.dist * 0.6, fov: 46 });
    tg.forEach((g) => R.key(g.t, { tgt: g.p, yaw: y0 + 0.08 * sp, pitch: 0.22, dist: wide.dist * 0.58 }));
    R.key(t1, { tgt: wide.tgt, yaw: y0 + 0.35 * sp, pitch: 0.42, dist: wide.dist });
  }
}

// ===================================================================== DIORAMA (objects + 3D links) / HOLO (showcase)
interface DObj { kind: Obj; p: V3; s: number; h: number; word: Word; label: string; sub: string; yaw0: number; side: number }
interface DLink { ps: V3[]; t0: number; phase: number }
function layout(n: number, r: () => number): V3[] {
  const pick = Math.floor(r() * 4);
  if (n <= 1) return [[0, 0, 0]];
  if (pick === 0) return Array.from({ length: n }, (_, k) => [(k % 2 ? 1 : -1) * 1.15, 0, (n - 1) * 1.3 - k * 2.6] as V3);
  if (pick === 1) return Array.from({ length: n }, (_, k) => { const a = Math.PI * (0.15 + (0.7 * k) / (n - 1)); return [-2.6 * Math.cos(a), 0, -2.6 * Math.sin(a) + 1.3] as V3; });
  if (pick === 2) return Array.from({ length: n }, (_, k) => { const a = (k / n) * TAU + Math.PI / 2; return [2.2 * Math.cos(a), 0, 2.2 * Math.sin(a)] as V3; });
  return Array.from({ length: n }, (_, k) => [(k - (n - 1) / 2) * 2.1, 0, k % 2 ? -1.1 : 1.1] as V3);
}
export class Scene3D extends GenPlate {
  override has3D = true;
  override gridInk = 0.25;
  links3 = true;
  objs: DObj[] = [];
  lks: DLink[] = [];
  mode = 'chain';
  tLive = 1e9;
  build() {
    const d = this.data, st = this.style, its = items(d, this.links3 ? 4 : 3), n = Math.max(1, its.length);
    const pts: V3[] = this.links3 ? layout(n, st.r) : n === 1 ? [[0, 0, 0]] : n === 2 ? [[-1.25, 0, 0.5], [1.25, 0, -0.5]] : [[-1.35, 0, 0.9], [1.35, 0, 0.9], [0, 0, -1.4]];
    const scale = this.links3 ? 1.0 : n === 1 ? 1.7 : n === 2 ? 1.15 : 1.0;
    its.forEach((it: any, k: number) => {
      const wd = this.cue(it.cue ?? it.label, k, n);
      const kind = asObj(it.object, k + (Number(this.sc.meta?.seed) || 0));
      const p = pts[k]!;
      this.objs.push({ kind, p, s: scale, h: shape(kind, 0).h, word: wd, label: up(it.label ?? kind, 18), sub: String(it.sub ?? '').slice(0, 30), yaw0: st.r() * TAU, side: p[0] > 0.2 ? 1 : p[0] < -0.2 ? -1 : (k % 2 ? 1 : -1) });
      this.hits.push(wd.start);
    });
    if (this.links3 && n > 1) {
      this.mode = ['chain', 'hub', 'ring'].includes(d.link) ? d.link : (['chain', 'hub', 'ring'] as const)[Math.floor(st.r() * 3)]!;
      const pairs: [number, number][] = this.mode === 'hub' ? this.objs.slice(1).map((_, k) => [0, k + 1]) : this.objs.slice(1).map((_, k) => [k, k + 1]);
      if (this.mode === 'ring' && n > 2) pairs.push([n - 1, 0]);
      pairs.forEach(([a, b], i) => {
        const A = this.objs[a]!, B = this.objs[b]!;
        this.lks.push({ ps: arcPts([A.p[0], 0.15, A.p[2]], [B.p[0], 0.15, B.p[2]], 0.9 + st.r() * 0.7, 32), t0: Math.max(A.word.start, B.word.start) + 0.35, phase: i * 0.27 });
      });
      const lastLink = Math.max(...this.lks.map((l) => l.t0));
      this.tLive = d.packetsCue ? Math.max(this.cue(d.packetsCue, n, n + 1).start, this.t0 + 0.5) : lastLink + 0.5;
    }
    const ext = Math.max(2.4, ...this.objs.map((o) => Math.hypot(o.p[0], o.p[2]) + 1.2 * o.s));
    const ctr: V3 = [0, 0.75 * scale, 0];
    plan(this, this.objs.map((o) => ({ t: o.word.start, p: [o.p[0], o.p[1] + o.h * o.s * 0.5, o.p[2]] as V3, d: 3.6 + 1.6 * o.s })), { tgt: ctr, dist: ext * 2.6 + 3 });
    this.floorR = Math.ceil(ext + 2.5);
    this.captionY = 660;
  }
  override draw3D(P: Pen3, t: number) {
    const st = this.style, seed = Number(this.sc.meta?.seed) || 7;
    const ped = prog(t, this.t0 + 0.2, this.t0 + 0.9);
    this.objs.forEach((o, k) => {
      const p = clamp((t - o.word.start + 0.05) / 0.9);
      pedestal(P, o.p, 0.95 * o.s, t, ped * (0.4 + 0.6 * clamp(p * 3)), st.tint);
      drawObj(P, o.kind, o.p, o.s, o.yaw0 + t * 0.35 * st.spin, p, t, st.reveal, st.tint, seed + k * 13, pulse(t, o.word.start + 0.9, 0.3));
    });
    for (const l of this.lks) link(P, l.ps, prog(t, l.t0, l.t0 + 0.55, ease.inOutQuad), prog(t, this.tLive, this.tLive + 0.3), t, st.tint, 0.42, l.phase, this.mode === 'hub');
  }
  override drawUI(ctx: CanvasRenderingContext2D, t: number, _c: Cam) {
    for (const [k, o] of this.objs.entries()) {
      const a = prog(t, o.word.start + 0.3, o.word.start + 0.6);
      this.tag(ctx, [o.p[0], o.p[1] + o.h * o.s + 0.12, o.p[2]], o.label, o.sub, a, { dx: 70 * o.side, dy: -60 - 55 * (k % 3), size: 32, hot: 1 - prog(t, o.word.start + 0.3, o.word.start + 1.1) });
    }
  }
  override postFX() { return { bloom: 0.9, bloomThreshold: 0.78, halation: 0.25 }; }
}
/** Showcase: 1-3 big objects on pedestals, no links. */
export class Holo extends Scene3D { override links3 = false; }

// ===================================================================== LAYERS (exploded architecture stack)
interface Slab { y: number; word: Word; label: string; sub: string; kind: Obj | null; mods: [number, number, number, number][]; dx: number; dy: number }
export class Layers extends GenPlate {
  override has3D = true;
  override gridInk = 0.25;
  slabs: Slab[] = [];
  enter = 'slide';
  tLive = 1e9;
  HW = 1.55; HD = 1.25;
  build() {
    const d = this.data, st = this.style, its = items(d, 5), n = Math.max(1, its.length), gap = 1.15;
    this.enter = (['slide', 'drop', 'unfold'] as const)[Math.floor(st.r() * 3)]!;
    its.forEach((it: any, k: number) => {
      const wd = this.cue(it.cue ?? it.label, k, n);
      const mods: [number, number, number, number][] = [];
      const m = 2 + Math.floor(st.r() * 4);
      for (let i = 0; i < m; i++) mods.push([(-0.75 + st.r() * 1.5) * this.HW, (-0.6 + st.r() * 1.2) * this.HD, 0.15 + st.r() * 0.25, 0.08 + st.r() * 0.3]);
      this.slabs.push({ y: (n - 1 - k) * gap + 0.5, word: wd, label: up(it.label, 20), sub: String(it.sub ?? '').slice(0, 30), kind: it.object ? asObj(it.object, k) : null, mods, dx: (k % 2 ? 1 : -1) * 7, dy: 4 });
      this.hits.push(wd.start);
    });
    const last = this.slabs[this.slabs.length - 1];
    this.tLive = (last?.word.start ?? this.t0) + 0.8;
    const top = (n - 1) * gap + 0.5;
    plan(this, this.slabs.map((s) => ({ t: s.word.start, p: [0, s.y, 0] as V3, d: 6.2 })), { tgt: [0, top / 2, 0], dist: top * 1.7 + 6.5 });
    this.floorAt = [0, -0.2, 0]; this.floorR = 4;
    this.captionY = 660;
  }
  slabAt(s: Slab, t: number): { o: V3; k: number } {
    const p = ease.outCubic(clamp((t - s.word.start + 0.1) / 0.6));
    if (this.enter === 'slide') return { o: [s.dx * (1 - p), s.y, 0], k: 1 };
    if (this.enter === 'drop') return { o: [0, s.y + s.dy * (1 - p), 0], k: 1 };
    return { o: [0, s.y, 0], k: Math.max(0.001, p) };
  }
  override draw3D(P: Pen3, t: number) {
    const st = this.style, tint = st.tint;
    const live = this.slabs.filter((s) => t > s.word.start - 0.1);
    live.forEach((s, i) => {
      const { o, k } = this.slabAt(s, t), a = prog(t, s.word.start - 0.1, s.word.start + 0.2), hot = pulse(t, s.word.start + 0.5, 0.25);
      const hw = this.HW * k, hd = this.HD * k, c = scl(tint, 1.1 + 1.5 * hot);
      const C: V3[] = [[o[0] - hw, o[1], o[2] - hd], [o[0] + hw, o[1], o[2] - hd], [o[0] + hw, o[1], o[2] + hd], [o[0] - hw, o[1], o[2] + hd]];
      P.poly(C, 2.2, c, a, true);
      P.poly(C.map((q) => [q[0], q[1] - 0.12, q[2]] as V3), 1.2, scl(tint, 0.5), a, true, 0);
      for (let g = 1; g < 4; g++) { const u = -hw + (2 * hw * g) / 4; P.seg([o[0] + u, o[1], o[2] - hd], [o[0] + u, o[1], o[2] + hd], 1, scl(tint, 0.35), a, 0); }
      for (const [mx, mz, mw, mh] of s.mods) {
        const x = o[0] + mx * k, z = o[2] + mz * k, hh = mh * clamp((t - s.word.start - 0.3) / 0.4);
        if (hh <= 0) continue;
        const b: V3[] = [[x - mw, o[1], z - mw], [x + mw, o[1], z - mw], [x + mw, o[1], z + mw], [x - mw, o[1], z + mw]];
        P.poly(b.map((q) => [q[0], q[1] + hh, q[2]] as V3), 1.4, scl(tint, 0.9), a, true, 0.1);
        for (const q of b) P.seg(q, [q[0], q[1] + hh, q[2]], 1.2, scl(tint, 0.7), a, 0);
      }
      if (s.kind) drawObj(P, s.kind, [o[0], o[1], o[2]], 0.55 * k, t * 0.5 * st.spin, clamp((t - s.word.start - 0.2) / 0.8), t, st.reveal, tint, i + 3);
      const prev = live[i - 1];
      if (prev) {
        const po = this.slabAt(prev, t).o;
        for (const [sx, sz] of [[-1, -1], [1, -1], [1, 1], [-1, 1]] as const) {
          for (let j = 0; j < 6; j += 2) {
            const y0 = o[1] + ((po[1] - o[1]) * j) / 6, y1 = o[1] + ((po[1] - o[1]) * (j + 1)) / 6;
            P.seg([o[0] + sx * hw, y0, o[2] + sz * hd], [o[0] + sx * hw, y1, o[2] + sz * hd], 1, scl(tint, 0.45), a * 0.8, 0);
          }
        }
      }
    });
    if (t > this.tLive && this.slabs.length > 1) {
      const top = this.slabs[0]!.y + 1, bot = -0.2, ramp = prog(t, this.tLive, this.tLive + 0.4);
      for (let k = 0; k < 4; k++) {
        const u = ((t - this.tLive) * 0.45 + k / 4) % 1, x = 0.5 * Math.cos(k * 1.7), z = 0.5 * Math.sin(k * 1.7);
        for (let j = 0; j < 6; j++) {
          const y = top + (bot - top) * clamp(u - j * 0.012), y2 = top + (bot - top) * clamp(u - (j + 1) * 0.012), f = 1 - j / 6;
          P.seg([x, y, z], [x, y2, z], (j ? 3 : 7) * f + 1, scl(j ? LIN.signal : LIN.ember, (j ? 1.8 : 3) * f), ramp * f, 0.05);
        }
      }
    }
  }
  override drawUI(ctx: CanvasRenderingContext2D, t: number, _c: Cam) {
    this.slabs.forEach((s, i) => {
      const a = prog(t, s.word.start + 0.2, s.word.start + 0.5), { o, k } = this.slabAt(s, t);
      const side = i % 2 ? -1 : 1;
      this.tag(ctx, [o[0] + side * this.HW * k, o[1], o[2] + this.HD * k], `${String(i + 1).padStart(2, '0')}  ${s.label}`, s.sub, a, { dx: side * 40, dy: -30, size: 30, hot: 1 - prog(t, s.word.start + 0.2, s.word.start + 1) });
    });
  }
  override postFX() { return { bloom: 0.85, bloomThreshold: 0.8, halation: 0.2 }; }
}

// ===================================================================== ORBIT (core + satellites on tilted rings)
interface Sat { kind: Obj; word: Word; label: string; R: number; incl: number; ph: number; w: number }
export class Orbit extends GenPlate {
  override has3D = true;
  override gridInk = 0.2;
  core!: { kind: Obj; word: Word; label: string };
  sats: Sat[] = [];
  build() {
    const d = this.data, st = this.style, its = items(d, 5), n = its.length;
    const c = d.core && typeof d.core === 'object' ? d.core : {};
    this.core = { kind: asObj(c.object, 3), word: this.cue(c.cue ?? c.label, 0, n + 1), label: up(c.label ?? 'CORE', 16) };
    this.hits.push(this.core.word.start);
    its.forEach((it: any, k: number) => {
      const wd = this.cue(it.cue ?? it.label, k + 1, n + 1);
      this.sats.push({ kind: asObj(it.object, k + 5), word: wd, label: up(it.label, 16), R: 2.0 + k * 0.55, incl: (k % 2 ? 1 : -1) * (0.12 + 0.1 * k), ph: st.r() * TAU, w: (0.45 / (1 + k * 0.35)) * st.spin });
      this.hits.push(wd.start);
    });
    const R = this.rig, y0 = st.r() * TAU;
    R.drift = 0.16 * st.spin;
    R.key(this.t0, { tgt: [0, 0.8, 0], yaw: y0, pitch: 0.75, dist: 13, fov: 50 });
    R.key(this.core.word.start, { tgt: [0, 0.8, 0], yaw: y0, pitch: 0.3, dist: 6.5 });
    this.sats.forEach((s, k) => R.key(s.word.start, { tgt: [0, 0.8, 0], yaw: y0 + 0.2 * k * st.spin, pitch: k % 2 ? 0.55 : 0.22, dist: 7.6 + s.R * 0.9 }));
    R.key(this.t1, { tgt: [0, 0.8, 0], yaw: y0 + 0.4 * st.spin, pitch: 0.45, dist: 9 + this.sats.length * 0.6 });
    this.floorAt = [0, -0.6, 0]; this.floorR = 6;
    this.captionY = 660;
  }
  satPos(s: Sat, t: number): V3 {
    const a = s.ph + s.w * (t - this.t0), x = s.R * Math.cos(a), z = s.R * Math.sin(a);
    return [x, 0.8 + z * Math.sin(s.incl), z * Math.cos(s.incl)];
  }
  override draw3D(P: Pen3, t: number) {
    const st = this.style, tint = st.tint, seed = Number(this.sc.meta?.seed) || 5;
    const pc = clamp((t - this.core.word.start + 0.05) / 0.9);
    drawObj(P, this.core.kind, [0, 0, 0], 1.25, t * 0.3 * st.spin, pc, t, st.reveal, tint, seed, pulse(t, this.core.word.start + 0.9, 0.3));
    if (pc > 0) P.ring([0, 0, 0], 1.0, 1.6, scl(tint, 0.6), 0.6 * pc, 48);
    this.sats.forEach((s, k) => {
      const g = prog(t, s.word.start - 0.25, s.word.start + 0.35, ease.inOutQuad);
      if (g <= 0) return;
      const pts: V3[] = [];
      for (let i = 0; i <= 72; i++) { const a = s.ph + s.w * (t - this.t0) + (i / 72) * TAU * g; const x = s.R * Math.cos(a), z = s.R * Math.sin(a); pts.push([x, 0.8 + z * Math.sin(s.incl), z * Math.cos(s.incl)]); }
      for (let i = 1; i < pts.length; i++) if (i % 3) P.seg(pts[i - 1]!, pts[i]!, 1.2, scl(tint, 0.55), 0.8, 0.08);
      const q = this.satPos(s, t), ps = clamp((t - s.word.start) / 0.7);
      drawObj(P, s.kind, [q[0], q[1] - 0.25, q[2]], 0.45, t * 0.8, ps, t, st.reveal, tint, seed + k * 7, pulse(t, s.word.start + 0.7, 0.3));
      if (ps > 0.5) {
        const tether: V3[] = Array.from({ length: 13 }, (_, i) => v3.lerp([0, 0.8, 0], q, i / 12));
        link(P, tether, 1, prog(t, s.word.start + 0.6, s.word.start + 0.9), t, tint, 0.8, k * 0.3);
      }
    });
  }
  override drawUI(ctx: CanvasRenderingContext2D, t: number, _c: Cam) {
    this.tag(ctx, [0, 1.25 * shape(this.core.kind, 0).h + 0.1, 0], this.core.label, '', prog(t, this.core.word.start + 0.3, this.core.word.start + 0.6), { dx: 60, dy: -90, size: 38, hot: 1 - prog(t, this.core.word.start + 0.3, this.core.word.start + 1.1) });
    for (const s of this.sats) {
      const q = this.satPos(s, t);
      this.tag(ctx, [q[0], q[1] + 0.35, q[2]], s.label, '', prog(t, s.word.start + 0.3, s.word.start + 0.6), { dx: q[0] >= 0 ? 50 : -50, dy: -50, size: 28 });
    }
  }
  override postFX() { return { bloom: 0.95, bloomThreshold: 0.76, halation: 0.3 }; }
}

// ===================================================================== TUNNEL (fly through the pipeline's gates)
interface Gate { z: number; word: Word; label: string; sub: string }
export class Tunnel extends GenPlate {
  override has3D = true;
  override gridInk = 0.15;
  override floorAt: V3 | null = null;
  gates: Gate[] = [];
  keysZ: [number, number][] = [];
  GW = 1.6; GH = 3.0; SP = 6;
  build() {
    const d = this.data, st = this.style, its = items(d, 5), n = Math.max(1, its.length);
    its.forEach((it: any, k: number) => {
      const wd = this.cue(it.cue ?? it.label, k, n);
      this.gates.push({ z: -k * this.SP, word: wd, label: up(it.label, 20), sub: String(it.sub ?? '').slice(0, 30) });
      this.hits.push(wd.start + 0.05);
    });
    this.keysZ = [[this.t0, 5], ...this.gates.map((g) => [g.word.start + 0.05, g.z] as [number, number]), [this.t1, (this.gates[this.gates.length - 1]?.z ?? 0) - 4]];
    const sway = 0.28 + st.r() * 0.25, sp = st.spin, lo = st.r() < 0.5;
    this.rig.at = (t: number) => {
      const z = this.zAt(t);
      return { tgt: [0, 1.4, z - 3.2], yaw: sp * sway * Math.sin((t - this.t0) * 0.55), pitch: (lo ? 0.1 : 0.26) + 0.05 * Math.sin((t - this.t0) * 0.4), dist: 6.2, fov: 54, roll: 0.03 * sp * Math.sin((t - this.t0) * 0.7) };
    };
    this.captionY = 660;
  }
  zAt(t: number) {
    const ks = this.keysZ;
    if (t <= ks[0]![0]) return ks[0]![1];
    for (let i = 1; i < ks.length; i++) {
      const [tb, zb] = ks[i]!, [ta, za] = ks[i - 1]!;
      if (t <= tb) return za + (zb - za) * ease.inOutCubic(clamp((t - ta) / Math.max(0.05, tb - ta)));
    }
    return ks[ks.length - 1]![1];
  }
  override draw3D(P: Pen3, t: number) {
    const st = this.style, tint = st.tint, z = this.zAt(t), GW = this.GW, GH = this.GH;
    const zFar = (this.gates[this.gates.length - 1]?.z ?? 0) - 10;
    const rv = prog(t, this.t0, this.t0 + 1.2);
    for (const x of [-GW, GW]) P.seg([x, 0, 8], [x, 0, 8 + (zFar - 8) * rv], 1.4, scl(tint, 0.6), 0.9, 0.08);
    for (let zz = Math.floor(z + 6); zz > Math.max(zFar, z - 40); zz -= 1) if (zz > 8 + (zFar - 8) * rv) P.seg([-GW, 0, zz], [GW, 0, zz], 1, scl(tint, 0.28), 0.8, 0);
    for (const g of this.gates) {
      const a = clamp(rv * 1.5 - Math.abs(g.z) / 40), passed = t > g.word.start + 0.05, hot = pulse(t, g.word.start + 0.05, 0.25);
      const col = passed ? scl(LIN.signal, 1.2 + 2 * hot) : scl(tint, 1.1);
      const C: V3[] = [[-GW, 0, g.z], [-GW, GH, g.z], [GW, GH, g.z], [GW, 0, g.z]];
      P.poly(C, 2.4 + 2 * hot, col, a);
      const b = 0.35;
      for (const [x, y, sx, sy] of [[-GW, GH, 1, -1], [GW, GH, -1, -1]] as const) {
        P.seg([x + sx * 0.12, y + sy * 0.12, g.z + 0.3], [x + sx * (0.12 + b), y + sy * 0.12, g.z + 0.3], 2, scl(tint, 1.4), a);
        P.seg([x + sx * 0.12, y + sy * 0.12, g.z + 0.3], [x + sx * 0.12, y + sy * (0.12 + b), g.z + 0.3], 2, scl(tint, 1.4), a);
      }
      if (hot > 0.02) { const k = 1 + (1 - hot) * 0.6; P.poly(C.map((q) => [q[0] * k, (q[1] - GH / 2) * k + GH / 2, g.z] as V3), 2, scl(LIN.ember, 2.5), hot, true); }
    }
    // the packet: a spinning octahedron with a comet trail
    const o: V3 = [0, 1.4, z], r = 0.32, sp = t * 2.2;
    const V: V3[] = ([[r, 0], [0, r], [-r, 0], [0, -r]] as const).map(([x, w]) => [o[0] + x * Math.cos(sp) - w * Math.sin(sp), o[1], o[2] + x * Math.sin(sp) + w * Math.cos(sp)] as V3);
    const top: V3 = [o[0], o[1] + r * 1.3, o[2]], bot: V3 = [o[0], o[1] - r * 1.3, o[2]];
    for (let i = 0; i < 4; i++) { P.seg(V[i]!, V[(i + 1) % 4]!, 2.4, scl(LIN.ember, 2.4), 1); P.seg(V[i]!, top, 2, scl(LIN.ember, 2.2), 1); P.seg(V[i]!, bot, 2, scl(LIN.ember, 2.2), 1); }
    for (let j = 1; j < 10; j++) { const z1 = this.zAt(t - j * 0.03), z2 = this.zAt(t - (j + 1) * 0.03); P.seg([0, 1.4, z1], [0, 1.4, z2], 7 * (1 - j / 10) + 1, scl(LIN.signal, 2 * (1 - j / 10)), 1 - j / 10, 0.05); }
  }
  override drawUI(ctx: CanvasRenderingContext2D, t: number, _c: Cam) {
    this.gates.forEach((g, i) => {
      const a = prog(t, g.word.start - 0.5, g.word.start - 0.2) * (1 - prog(t, g.word.start + 2.5, g.word.start + 3.2));
      const side = i % 2 ? 1 : -1;
      this.tag(ctx, [side * this.GW, this.GH, g.z], `${String(i + 1).padStart(2, '0')}  ${g.label}`, g.sub, a, { dx: side * 30, dy: -40, size: 32, hot: pulse(t, g.word.start + 0.05, 0.4) });
    });
  }
  override postFX(t: number) { const hit = this.gates.reduce((m, g) => Math.max(m, pulse(t, g.word.start + 0.05, 0.1)), 0); return { bloom: 0.95, bloomThreshold: 0.76, halation: 0.25, zoom: 1 + 0.03 * hit }; }
}

// ===================================================================== BARS3D (holographic 3D bar chart)
interface Bar { x: number; h: number; word: Word; value: string; label: string }
export class Bars3D extends GenPlate {
  override has3D = true;
  override gridInk = 0.25;
  bars: Bar[] = [];
  total = ''; tTotal = 1e9;
  build() {
    const d = this.data, st = this.style, its = items(d, 5), n = Math.max(1, its.length);
    const vals = its.map((it: any) => Math.abs(numIn(it.value) ?? 1));
    const mx = Math.max(...vals, 1e-9);
    const sp = 1.3;
    its.forEach((it: any, k: number) => {
      const wd = this.cue(it.cue ?? it.value, k, n);
      this.bars.push({ x: (k - (n - 1) / 2) * sp, h: 0.45 + 2.5 * Math.max(0.05, vals[k]! / mx), word: wd, value: String(it.value ?? '').slice(0, 10), label: up(it.label, 22) });
      this.hits.push(wd.start);
    });
    if (d.total) { this.total = String(d.total).slice(0, 34); this.tTotal = Math.max(this.cue(d.totalCue, n, n + 1).start, (this.bars[this.bars.length - 1]?.word.end ?? 0) + 0.3); }
    const R = this.rig, s = st.spin, half = ((n - 1) / 2) * sp + 0.8;
    const wide = (half / 0.29) * 1.1 + 2;
    if (st.cam === 'orbit' || st.cam === 'crane') {
      R.drift = 0.12 * s;
      R.key(this.t0, { tgt: [0, 1.6, 0], yaw: 0.5 * s, pitch: st.cam === 'crane' ? 1.2 : 0.08, dist: wide * 1.05, fov: 50 });
      this.bars.forEach((b, k) => R.key(b.word.start, { tgt: [b.x * 0.5, b.h * 0.6, 0], yaw: 0.5 * s, pitch: 0.2 + 0.1 * k, dist: wide * 0.85 }));
      R.key(this.t1, { tgt: [0, 1.8, 0], yaw: 0.5 * s, pitch: 0.4, dist: wide });
    } else {
      R.key(this.t0, { tgt: [this.bars[0]?.x ?? 0, 0.8, 0], yaw: 0.95 * s, pitch: 0.05, dist: 6, fov: 48 });
      this.bars.forEach((b) => R.key(b.word.start + 0.15, { tgt: [b.x, b.h * 0.6, 0], yaw: 0.7 * s, pitch: 0.14, dist: 6.4 + b.h * 1.1 }));
      R.key(this.t1, { tgt: [0, 1.8, 0], yaw: 0.35 * s, pitch: 0.36, dist: wide });
    }
    this.floorR = Math.ceil(half + 2.5);
    this.captionY = 660;
  }
  hAt(b: Bar, t: number) { return b.h * ease.outBack(clamp((t - b.word.start) / 0.7)); }
  override draw3D(P: Pen3, t: number) {
    const tint = this.style.tint, w = 0.38;
    for (const b of this.bars) {
      if (t < b.word.start) continue;
      const h = Math.max(0.01, this.hAt(b, t)), hot = pulse(t, b.word.start + 0.7, 0.3);
      const q = (y: number): V3[] => [[b.x - w, y, -w], [b.x + w, y, -w], [b.x + w, y, w], [b.x - w, y, w]];
      const B = q(0), T = q(h), col = scl(tint, 1.15 + 1.4 * hot);
      P.poly(B, 1.6, scl(tint, 0.7), 1, true);
      P.poly(T, 2.6, scl(LIN.signal, 1.6 + 1.5 * hot), 1, true);
      for (let i = 0; i < 4; i++) P.seg(B[i]!, T[i]!, 2.2, col, 1);
      for (let y = 0.4; y < h - 0.05; y += 0.4) P.poly(q(y), 1, scl(tint, 0.4), 0.7, true, 0);
      P.seg([b.x - w, h, -w], [b.x + w, h, w], 1.2, scl(LIN.signal, 1.2), 0.8, 0);
    }
  }
  override drawUI(ctx: CanvasRenderingContext2D, t: number, _c: Cam) {
    for (const b of this.bars) {
      if (t < b.word.start) continue;
      const age = t - b.word.start, top = this.hAt(b, t);
      this.tag(ctx, [b.x, top + 0.1, 0], counting(b.value, age / 0.9), b.label, prog(t, b.word.start, b.word.start + 0.2), { dx: 0, dy: -60, size: 40, hot: 1 - prog(t, b.word.start + 0.9, b.word.start + 1.5) });
    }
    if (this.total && t > this.tTotal) {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      typeText(ctx, this.total, 540, 1420, t, this.tTotal, this.tTotal + 0.6, F.mono(500), Math.min(40, fitSize(this.total, F.mono(500), 940, 40)), 'bone', false, 'center');
    }
  }
  override postFX() { return { bloom: 0.9, bloomThreshold: 0.78 }; }
}
