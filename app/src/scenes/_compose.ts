// COMPOSE plate: no template. The script writer designs every scene's visual from primitives (geometry, charts,
// networks, particle fields, surfaces, library objects, text), picks the layout, each element's entrance + idle
// animation, links between elements, the camera and the scene transition. The style genome then re-skins all of
// it (palette, hologram tints, type, label style, camera feel, post). Two scenes only look alike if every one of
// those choices matches, and the bot refuses to reuse a scene composition.
import { LIN, rgba } from '../engine/palette';
import { F, font, measure } from '../engine/type';
import { norm, type Word } from '../engine/lyrics';
import { clamp, ease, hash, hexToLinear, mulberry32, noise1, prog, pulse, TAU } from '../engine/util';
import { type Cam, type RGB } from './_vo';
import { GenPlate, ARCH, wrapKaraoke, mixColor } from './_gen';
import { asObj, shape, arcPts, link, along, drawObj, v3, type Obj, type Pen3, type V3, type Reveal } from './_holo3d';
import { plan } from './_plates3d';
import type { GlassItem, GeoKind } from './_glass';

type Seg = [V3, V3];
const scl = (c: RGB, s: number): RGB => [c[0] * s, c[1] * s, c[2] * s];
const numIn = (v: any) => { const m = String(v ?? '').replace(/,/g, '').match(/-?\d+(\.\d+)?/); return m ? parseFloat(m[0]) : null; };

export const TYPES = ['object', 'box', 'sphere', 'cylinder', 'cone', 'torus', 'prism', 'panel', 'ring', 'helix', 'wave', 'surface', 'particles',
  'link', 'beam', 'bars', 'donut', 'line', 'matrix', 'network', 'gauge', 'counter', 'text', 'orbit', 'stack', 'tunnel', 'code', 'stream', 'burst'] as const;
const APPEAR = ['grow', 'pop', 'fly', 'drop', 'rise', 'unfold', 'draw', 'assemble', 'glitch', 'scan'] as const;
const IDLE = ['spin', 'pulse', 'orbit', 'float', 'none'] as const;
const TRANS = ['cut', 'flash', 'zoom', 'whip', 'fade', 'glitch', 'iris', 'morph'] as const;

interface El {
  type: string; label: string; sub: string; value: string; values: number[]; anim: string; idle: string; tone: string;
  size: number; to: number; from: number; parent: number; object: Obj; count: number; word: Word; p: V3; k: number; side: number; lines: string[];
}

// ------------------------------------------------------------------ primitives (local space, base at y=0, ~1 unit)
function ringPts(c: V3, r: number, n: number, plane: 'xz' | 'xy' = 'xz', a0 = 0, a1 = TAU): V3[] {
  const o: V3[] = [];
  for (let i = 0; i <= n; i++) { const a = a0 + ((a1 - a0) * i) / n; o.push(plane === 'xz' ? [c[0] + r * Math.cos(a), c[1], c[2] + r * Math.sin(a)] : [c[0] + r * Math.cos(a), c[1] + r * Math.sin(a), c[2]]); }
  return o;
}
const polySegs = (ps: V3[], out: Seg[]) => { for (let i = 1; i < ps.length; i++) out.push([ps[i - 1]!, ps[i]!]); };
function boxSegs(w: number, h: number, d: number, y0: number, out: Seg[]) {
  const c: V3[] = [[-w, y0, -d], [w, y0, -d], [w, y0, d], [-w, y0, d], [-w, y0 + h, -d], [w, y0 + h, -d], [w, y0 + h, d], [-w, y0 + h, d]];
  for (const [a, b] of [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]]) out.push([c[a!]!, c[b!]!]);
}
interface Geo { segs: Seg[]; dots: V3[]; hot: Seg[]; h: number }
function geometry(e: El, t: number, tt: number): Geo {
  const segs: Seg[] = [], dots: V3[] = [], hot: Seg[] = [];
  const r = mulberry32(e.k * 977 + 13);
  switch (e.type) {
    case 'object': { const s = shape(e.object, t); return { segs: s.segs, dots: s.leds, hot, h: s.h }; }
    case 'box': boxSegs(0.5, 1, 0.5, 0, segs); boxSegs(0.3, 0.6, 0.3, 0.2, segs); return { segs, dots, hot, h: 1 };
    case 'sphere':
      for (const k of [-0.7, -0.35, 0, 0.35, 0.7]) polySegs(ringPts([0, 0.6 + k * 0.55, 0], 0.55 * Math.sqrt(1 - k * k), 28), segs);
      for (let j = 0; j < 4; j++) { const a = (j * Math.PI) / 4 + t * 0.3; const ps: V3[] = []; for (let i = 0; i <= 28; i++) { const u = (i / 28) * TAU; ps.push([0.55 * Math.cos(u) * Math.cos(a), 0.6 + 0.55 * Math.sin(u), 0.55 * Math.cos(u) * Math.sin(a)]); } polySegs(ps, segs); }
      return { segs, dots, hot, h: 1.15 };
    case 'cylinder':
      for (const y of [0, 0.5, 1]) polySegs(ringPts([0, y, 0], 0.45, 28), segs);
      for (let i = 0; i < 8; i++) { const a = (i / 8) * TAU; segs.push([[0.45 * Math.cos(a), 0, 0.45 * Math.sin(a)], [0.45 * Math.cos(a), 1, 0.45 * Math.sin(a)]]); }
      return { segs, dots, hot, h: 1 };
    case 'cone':
      polySegs(ringPts([0, 0, 0], 0.55, 28), segs); polySegs(ringPts([0, 0.45, 0], 0.33, 24), segs);
      for (let i = 0; i < 10; i++) { const a = (i / 10) * TAU; segs.push([[0.55 * Math.cos(a), 0, 0.55 * Math.sin(a)], [0, 1.15, 0]]); }
      dots.push([0, 1.15, 0]); return { segs, dots, hot, h: 1.15 };
    case 'torus':
      for (let i = 0; i < 18; i++) { const a = (i / 18) * TAU + t * 0.4; const c: V3 = [0.5 * Math.cos(a), 0.45, 0.5 * Math.sin(a)]; const ps: V3[] = []; for (let j = 0; j <= 12; j++) { const b = (j / 12) * TAU; ps.push([c[0] + 0.17 * Math.cos(b) * Math.cos(a), c[1] + 0.17 * Math.sin(b), c[2] + 0.17 * Math.cos(b) * Math.sin(a)]); } polySegs(ps, segs); }
      polySegs(ringPts([0, 0.45, 0], 0.67, 36), segs); polySegs(ringPts([0, 0.45, 0], 0.33, 30), segs);
      return { segs, dots, hot, h: 0.65 };
    case 'prism': {
      const ring = (y: number): V3[] => Array.from({ length: 7 }, (_, i) => [0.5 * Math.cos((i / 6) * TAU), y, 0.5 * Math.sin((i / 6) * TAU)] as V3);
      polySegs(ring(0), segs); polySegs(ring(1.1), segs);
      for (let i = 0; i < 6; i++) segs.push([ring(0)[i]!, ring(1.1)[i]!]);
      return { segs, dots, hot, h: 1.1 };
    }
    case 'panel': {
      const w = 0.9, h = 0.6, y = 0.8;
      polySegs([[-w, y - h, 0], [w, y - h, 0], [w, y + h, 0], [-w, y + h, 0], [-w, y - h, 0]], segs);
      for (let i = 1; i < 4; i++) segs.push([[-w * 0.8, y + h - i * 0.28, 0.01], [-w * 0.8 + (0.6 + 0.8 * r()) * w, y + h - i * 0.28, 0.01]]);
      hot.push([[-w, y + h + 0.08, 0], [-w * 0.2, y + h + 0.08, 0]]);
      return { segs, dots, hot, h: y + h };
    }
    case 'ring':
      polySegs(ringPts([0, 0.05, 0], 0.85, 48), segs); polySegs(ringPts([0, 0.05, 0], 0.6, 40, 'xz', t, t + TAU * 0.75), hot);
      for (let i = 0; i < 12; i++) { const a = (i / 12) * TAU; segs.push([[0.85 * Math.cos(a), 0.05, 0.85 * Math.sin(a)], [0.95 * Math.cos(a), 0.05, 0.95 * Math.sin(a)]]); }
      return { segs, dots, hot, h: 0.2 };
    case 'helix': { const s = shape('helix', t); return { segs: s.segs, dots, hot, h: s.h }; }
    case 'wave': {
      for (const z of [-0.12, 0.12]) { const ps: V3[] = []; for (let i = 0; i <= 40; i++) { const x = -1.4 + (2.8 * i) / 40; ps.push([x, 0.5 + 0.28 * Math.sin(x * 3 + t * 2.4 + z * 4), z]); } polySegs(ps, segs); }
      for (let i = 0; i <= 40; i += 4) { const x = -1.4 + (2.8 * i) / 40, y = 0.5 + 0.28 * Math.sin(x * 3 + t * 2.4); segs.push([[x, 0, 0], [x, y, 0]]); }
      return { segs, dots, hot, h: 0.8 };
    }
    case 'surface': {
      const N = 9, f = (x: number, z: number) => 0.4 + 0.3 * Math.sin(x * 2.2 + t * 1.2) * Math.cos(z * 2.0 + t * 0.8);
      for (let i = 0; i <= N; i++) { const a: V3[] = [], b: V3[] = []; for (let j = 0; j <= N; j++) { const x = -1.2 + (2.4 * i) / N, z = -1.2 + (2.4 * j) / N; a.push([x, f(x, z), z]); b.push([z, f(z, x), x]); } polySegs(a, segs); polySegs(b, segs); }
      return { segs, dots, hot, h: 0.8 };
    }
    case 'particles': {
      const n = Math.min(220, Math.max(40, e.count || 120));
      for (let i = 0; i < n; i++) { const u = hash(i, e.k), v = hash(i, e.k + 7), rr = 0.25 + 0.75 * hash(i, e.k + 3), a = u * TAU + t * (0.3 + 0.6 * (1 - rr)); dots.push([rr * Math.cos(a), 0.15 + v * 1.3, rr * Math.sin(a)]); }
      return { segs, dots, hot, h: 1.4 };
    }
    case 'bars': {
      const vs = e.values.length ? e.values : [3, 5, 2, 7, 4], mx = Math.max(...vs.map(Math.abs), 1e-9), n = vs.length, w = Math.min(0.22, 1.1 / n);
      vs.forEach((v, i) => {
        const x = -1.1 + (2.2 * (i + 0.5)) / n, h = 0.1 + (1.4 * Math.abs(v)) / mx * ease.outBack(clamp((tt - i * 0.12) / 0.6));
        const q = (y: number): V3[] => [[x - w, y, -w], [x + w, y, -w], [x + w, y, w], [x - w, y, w], [x - w, y, -w]];
        polySegs(q(0), segs); polySegs(q(h), hot); for (const c of q(0).slice(0, 4)) segs.push([c, [c[0], h, c[2]]]);
      });
      segs.push([[-1.25, 0, 0.3], [1.25, 0, 0.3]]);
      return { segs, dots, hot, h: 1.5 };
    }
    case 'donut': {
      const vs = e.values.length ? e.values.map(Math.abs) : [40, 25, 20, 15], tot = vs.reduce((s, v) => s + v, 0) || 1;
      let a = -Math.PI / 2;
      vs.forEach((v, i) => { const da = (v / tot) * TAU * clamp((tt - i * 0.15) / 0.5), gap = 0.05; if (da > gap * 2) for (const [rr, y] of [[0.85, 0.05], [0.55, 0.05], [0.85, 0.22], [0.55, 0.22]] as const) polySegs(ringPts([0, y, 0], rr, 24, 'xz', a + gap, a + da - gap), i === 0 ? hot : segs); a += (v / tot) * TAU; });
      return { segs, dots, hot, h: 0.3 };
    }
    case 'line': {
      const vs = e.values.length > 1 ? e.values : [2, 3, 2.5, 5, 4, 7], mx = Math.max(...vs), mn = Math.min(...vs, 0), n = vs.length;
      segs.push([[-1.2, 0.1, 0], [1.2, 0.1, 0]], [[-1.2, 0.1, 0], [-1.2, 1.7, 0]]);
      const pts: V3[] = vs.map((v, i) => [-1.1 + (2.2 * i) / Math.max(1, n - 1), 0.2 + (1.4 * (v - mn)) / (mx - mn || 1), 0] as V3);
      const m = clamp(tt / 1.0) * (n - 1);
      for (let i = 1; i <= Math.floor(m); i++) hot.push([pts[i - 1]!, pts[i]!]);
      if (m < n - 1) { const i = Math.floor(m); hot.push([pts[i]!, v3.lerp(pts[i]!, pts[i + 1]!, m - i)]); }
      pts.slice(0, Math.floor(m) + 1).forEach((p) => dots.push(p));
      return { segs, dots, hot, h: 1.7 };
    }
    case 'matrix': {
      const k = Math.min(7, Math.max(3, e.count || 5)), s = 1.8 / k;
      for (let i = 0; i < k; i++) for (let j = 0; j < k; j++) {
        const x = -0.9 + i * s, y = 0.1 + j * s, lit = hash(i * 31 + j, Math.floor(t * 3)) > 0.62 && tt > (i + j) * 0.04;
        const q: V3[] = [[x + 0.03, y + 0.03, 0], [x + s - 0.03, y + 0.03, 0], [x + s - 0.03, y + s - 0.03, 0], [x + 0.03, y + s - 0.03, 0], [x + 0.03, y + 0.03, 0]];
        polySegs(q, lit ? hot : segs);
        if (lit) hot.push([q[0]!, q[2]!]);
      }
      return { segs, dots, hot, h: 1.9 };
    }
    case 'network': {
      const n = Math.min(14, Math.max(5, e.count || 9)), P: V3[] = [];
      for (let i = 0; i < n; i++) { const a = hash(i, e.k) * TAU, b = Math.acos(2 * hash(i, e.k + 1) - 1); P.push([0.95 * Math.sin(b) * Math.cos(a + t * 0.15), 0.8 + 0.7 * Math.cos(b), 0.95 * Math.sin(b) * Math.sin(a + t * 0.15)]); }
      P.forEach((p, i) => { dots.push(p); const d = P.map((q, j) => [j, (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 + (q[2] - p[2]) ** 2] as [number, number]).sort((x, y) => x[1] - y[1]); for (const [j] of d.slice(1, 3)) if (j > i) segs.push([p, P[j]!]); });
      const live = Math.floor(t * 2) % Math.max(1, segs.length); if (segs[live]) hot.push(segs[live]!);
      return { segs, dots, hot, h: 1.6 };
    }
    case 'gauge': {
      const f = clamp((numIn(e.value) ?? 70) / 100), a0 = Math.PI * 1.25, sweep = -Math.PI * 1.5;
      polySegs(ringPts([0, 0.9, 0], 0.8, 40, 'xy', a0, a0 + sweep), segs);
      polySegs(ringPts([0, 0.9, 0.01], 0.72, 40, 'xy', a0, a0 + sweep * f * ease.outCubic(clamp(tt / 1.0))), hot);
      for (let i = 0; i <= 10; i++) { const a = a0 + (sweep * i) / 10; segs.push([[0.62 * Math.cos(a), 0.9 + 0.62 * Math.sin(a), 0], [0.55 * Math.cos(a), 0.9 + 0.55 * Math.sin(a), 0]]); }
      const na = a0 + sweep * f * ease.outBack(clamp(tt / 1.0)); hot.push([[0, 0.9, 0.02], [0.68 * Math.cos(na), 0.9 + 0.68 * Math.sin(na), 0.02]]);
      return { segs, dots, hot, h: 1.7 };
    }
    case 'counter': case 'text':
      polySegs(ringPts([0, 0, 0], 0.7, 36), segs); polySegs(ringPts([0, 0, 0], 0.9, 36, 'xz', t * 0.6, t * 0.6 + TAU * 0.6), segs);
      return { segs, dots, hot, h: 0.9 };
    case 'orbit': {
      polySegs(ringPts([0, 0.6, 0], 0.18, 16), hot);
      for (let k = 0; k < 3; k++) { const R = 0.5 + k * 0.28, inc = 0.3 * (k - 1); const ps: V3[] = []; for (let i = 0; i <= 40; i++) { const a = (i / 40) * TAU; ps.push([R * Math.cos(a), 0.6 + R * Math.sin(a) * Math.sin(inc), R * Math.sin(a) * Math.cos(inc)]); } polySegs(ps, segs); const a = t * (0.9 - k * 0.2) + k * 2; dots.push([R * Math.cos(a), 0.6 + R * Math.sin(a) * Math.sin(inc), R * Math.sin(a) * Math.cos(inc)]); }
      return { segs, dots, hot, h: 1.3 };
    }
    case 'stack': {
      const n = Math.min(5, Math.max(2, e.count || 3));
      for (let i = 0; i < n; i++) { const y = i * 0.32 + 0.04 * Math.sin(t * 2 + i), w = 0.6 - i * 0.05; polySegs([[-w, y, -w], [w, y, -w], [w, y, w], [-w, y, w], [-w, y, -w]], i === n - 1 ? hot : segs); polySegs([[-w, y + 0.12, -w], [w, y + 0.12, -w], [w, y + 0.12, w], [-w, y + 0.12, w], [-w, y + 0.12, -w]], segs); }
      return { segs, dots, hot, h: n * 0.32 };
    }
    case 'code': {
      const w = 1.05, h = 0.72, y = 0.85;
      polySegs([[-w, y - h, 0], [w, y - h, 0], [w, y + h, 0], [-w, y + h, 0], [-w, y - h, 0]], segs);
      hot.push([[-w, y + h - 0.16, 0.01], [w, y + h - 0.16, 0.01]]);
      for (let i = 0; i < 3; i++) dots.push([-w + 0.12 + i * 0.12, y + h - 0.08, 0.01]);
      return { segs, dots, hot, h: y + h };
    }
    case 'burst': {
      for (let i = 0; i < 90; i++) {
        const a = hash(i, e.k) * TAU, b = Math.acos(2 * hash(i, e.k + 2) - 1), rr = ((tt * 0.7 + hash(i, e.k + 5)) % 1) * 1.5;
        dots.push([rr * Math.sin(b) * Math.cos(a), 0.8 + rr * Math.cos(b) * 0.8, rr * Math.sin(b) * Math.sin(a)]);
      }
      polySegs(ringPts([0, 0.8, 0], 0.12, 12, 'xy'), hot);
      return { segs, dots, hot, h: 1.6 };
    }
    case 'tunnel':
      for (let i = 0; i < 9; i++) { const z = -((i * 0.45 + t * 0.6) % 4.05); polySegs(ringPts([0, 0.7, z], 0.6, 24, 'xy'), i % 3 ? segs : hot); }
      for (let i = 0; i < 6; i++) { const a = (i / 6) * TAU; segs.push([[0.6 * Math.cos(a), 0.7 + 0.6 * Math.sin(a), 0], [0.6 * Math.cos(a), 0.7 + 0.6 * Math.sin(a), -4]]); }
      return { segs, dots, hot, h: 1.3 };
  }
  boxSegs(0.5, 1, 0.5, 0, segs);
  return { segs, dots, hot, h: 1 };
}

// ------------------------------------------------------------------ layouts
export const LAYOUTS = ['radial', 'ring', 'grid', 'row', 'stack', 'timeline', 'spiral', 'tree', 'cluster', 'depth', 'pyramid', 'sphere', 'diagonal', 'wave', 'scatter'] as const;
function layout(name: string, n: number, parents: number[], r: () => number): V3[] {
  const L: V3[] = [];
  const depthOf = (i: number, g = 0): number => (g < 6 && parents[i]! >= 0 && parents[i]! < i ? 1 + depthOf(parents[i]!, g + 1) : 0);
  for (let k = 0; k < n; k++) {
    let p: V3;
    switch (name) {
      case 'radial': p = k === 0 ? [0, 0, 0] : [2.3 * Math.cos(((k - 1) / Math.max(1, n - 1)) * TAU), 0, 2.3 * Math.sin(((k - 1) / Math.max(1, n - 1)) * TAU)]; break;
      case 'ring': { const R = 1.5 + 0.35 * n, a = (k / n) * TAU + Math.PI / 2; p = [R * Math.cos(a), 0, R * Math.sin(a)]; break; }
      case 'grid': { const c = Math.ceil(Math.sqrt(n)); p = [((k % c) - (c - 1) / 2) * 2.2, 0, (Math.floor(k / c) - (Math.ceil(n / c) - 1) / 2) * 2.2]; break; }
      case 'row': case 'timeline': p = [(k - (n - 1) / 2) * 2.1, 0, 0]; break;
      case 'stack': p = [((k % 2) - 0.5) * 0.7, k * 1.6, 0]; break;
      case 'spiral': p = [(0.8 + 0.55 * k) * Math.cos(k * 1.15), k * 0.35, (0.8 + 0.55 * k) * Math.sin(k * 1.15)]; break;
      case 'tree': {
        const d = depthOf(k), sib = parents.slice(0, k).filter((_, i) => depthOf(i) === d).length, cnt = parents.filter((_, i) => depthOf(i) === d).length;
        p = [(sib - (cnt - 1) / 2) * 2.0, (3 - d) * 1.3, 0]; break;
      }
      case 'cluster': case 'scatter': {
        let best: V3 = [0, 0, 0];
        for (let tr = 0; tr < 40; tr++) { const a = r() * TAU, rr = 2.4 * Math.sqrt(r()); const c: V3 = [rr * Math.cos(a), name === 'scatter' ? r() * 1.6 : 0, rr * Math.sin(a)]; best = c; if (L.every((q) => Math.hypot(q[0] - c[0], q[2] - c[2]) > 1.7)) break; }
        p = best; break;
      }
      case 'depth': p = [(k % 2 ? 0.9 : -0.9), 0, -k * 3]; break;
      case 'pyramid': { const tier = k === 0 ? 0 : k < 3 ? 1 : 2, idx = k === 0 ? 0 : k < 3 ? k - 1 : k - 3, cnt = tier === 0 ? 1 : tier === 1 ? 2 : Math.max(1, n - 3); p = [(idx - (cnt - 1) / 2) * 2.1, (2 - tier) * 1.5, tier * 0.6]; break; }
      case 'sphere': { const y = 1 - (2 * (k + 0.5)) / n, rr = Math.sqrt(1 - y * y), a = k * 2.399963; p = [2.3 * rr * Math.cos(a), 1.2 + 2.0 * y, 2.3 * rr * Math.sin(a)]; break; }
      case 'diagonal': p = [(k - (n - 1) / 2) * 1.3, k * 0.9, -(k - (n - 1) / 2) * 1.3]; break;
      case 'wave': p = [(k - (n - 1) / 2) * 1.9, 0.9 * Math.sin(k * 1.4) + 0.9, 0.6 * Math.cos(k * 1.4)]; break;
      default: p = k === 0 ? [0, 0, 0] : [(1.4 + 0.5 * k) * Math.cos(k * 2.1), 0.4 * k, (1.4 + 0.5 * k) * Math.sin(k * 2.1)];
    }
    L.push(p);
  }
  return L;
}

/** Reveal a segment list with progress p in one of the reveal styles. Returns segments with per-segment alpha. */
function reveal(segs: Seg[], p: number, style: Reveal | 'draw', h: number, seed: number, t: number): [Seg, number][] {
  if (p >= 1) return segs.map((s) => [s, 1]);
  const n = segs.length, out: [Seg, number][] = [];
  const ycut = (h + 0.05) * ease.inOutQuad(p);
  segs.forEach(([a0, b0], i) => {
    let a = a0, b = b0, al = 0.7 + 0.3 * Math.abs(Math.sin(t * 37 + seed));
    if (style === 'scan') {
      if (a[1] > ycut && b[1] > ycut) return;
      if (a[1] > ycut || b[1] > ycut) { const u = (ycut - a[1]) / (b[1] - a[1] || 1e-9); const m: V3 = [a[0] + (b[0] - a[0]) * u, ycut, a[2] + (b[2] - a[2]) * u]; if (a[1] > ycut) a = m; else b = m; }
    } else if (style === 'draw') {
      const u = clamp(p * 1.25 * n - i * 0.95); if (u <= 0) return; b = v3.lerp(a, b, u);
    } else if (style === 'assemble') {
      const rr = hash(i, seed), q = ease.outCubic(clamp(p * 1.4 - rr * 0.4)), mid = v3.mul(v3.add(a, b), 0.5);
      const off = v3.mul(v3.nrm([mid[0] + 0.01, mid[1] - h / 2 + 0.3 * (rr - 0.5), mid[2] + 0.01]), 2.4 * (1 - q));
      a = v3.add(a, off); b = v3.add(b, off); al *= q;
    } else {
      if (hash(i, seed) > p * 1.15) return; al *= hash(i, Math.round(t * 30), seed) > 0.25 ? 1 : 0.15;
    }
    out.push([[a, b], al]);
  });
  return out;
}

export class Compose extends GenPlate {
  override has3D = true;
  override gridInk = 0.22;
  els: El[] = [];
  hookMode = false; cta = false; tEnd = 0;
  trans = 'cut';
  lay = 'radial';
  tones: Record<string, RGB> = {};
  ctr: V3 = [0, 0, 0];
  exitMorph = false;
  ls = 1;
  quizT = 1e9;
  build() {
    const d = this.data, st = this.style, r = st.r;
    this.hookMode = !!d.hook; this.cta = !!d.cta;
    this.ls = clamp(Number(d.labelScale) || 1, 0.8, 1.5);
    this.exitMorph = this.ctx.lyrics.scenes[this.idx + 1]?.data?.transition === 'morph';
    this.lay = (LAYOUTS as readonly string[]).includes(d.layout) ? d.layout : LAYOUTS[Math.floor(r() * LAYOUTS.length)]!;
    this.trans = (TRANS as readonly string[]).includes(d.transition) ? d.transition : TRANS[Math.floor(r() * TRANS.length)]!;
    const holo = Array.isArray(this.G.holo) && this.G.holo.length ? this.G.holo : [st.tintHex];
    this.tones = { holo: st.tint, alt: hexToLinear(String(holo[1] ?? holo[0])), accent: LIN.signal, ink: scl(LIN.bone, 0.85), ember: LIN.ember };
    if (this.hookMode || this.cta) {
      this.header = false; this.captionY = 'none';
      const r2 = wrapKaraoke(this.ws, 0, this.cta ? -560 : -680, 960, this.cta ? 104 : 96, ARCH(110, 850), 'q', { maxRows: 4, minSize: 54, lh: 1.08 });
      this.kw.push(...r2.kws);
      this.viewCY = 960 + 330;
      const last = this.ws[this.ws.length - 1]; this.tEnd = last ? last.end : this.t1 - 1;
    } else this.captionY = 680;
    const raw: any[] = Array.isArray(d.elements) ? d.elements.slice(0, 9) : [];
    const n = Math.max(1, raw.length);
    raw.forEach((x, k) => {
      let w = this.cue(x.cue ?? x.label, k, n);
      if (this.hookMode && k === 0) w = { ...w, start: Math.min(w.start, this.t0 + 0.2) };   // motion from the first second
      this.els.push({
        type: (TYPES as readonly string[]).includes(x.type) ? x.type : 'box', label: String(x.label ?? '').slice(0, 22).toUpperCase(), sub: String(x.sub ?? '').slice(0, 30),
        value: String(x.value ?? '').slice(0, 12), values: (Array.isArray(x.values) ? x.values : []).map(Number).filter((v: number) => isFinite(v)).slice(0, 8),
        anim: (APPEAR as readonly string[]).includes(x.anim) ? x.anim : APPEAR[Math.floor(r() * APPEAR.length)]!,
        idle: (IDLE as readonly string[]).includes(x.idle) ? x.idle : IDLE[Math.floor(r() * IDLE.length)]!,
        tone: ['holo', 'alt', 'accent', 'ink', 'ember'].includes(x.tone) ? x.tone : (k % 2 ? 'alt' : 'holo'),
        size: clamp(Number(x.size) || 1, 0.5, 2), to: Number.isInteger(x.to) ? x.to : -1, from: Number.isInteger(x.from) ? x.from : -1,
        parent: Number.isInteger(x.parent) ? x.parent : -1, lines: (Array.isArray(x.lines) ? x.lines : []).map(String).slice(0, 5),
        object: asObj(x.object, k + (Number(this.sc.meta?.seed) || 0)), count: Number(x.count) || 0, word: w, p: [0, 0, 0], k, side: 1,
      });
      this.hits.push(w.start);
    });
    const isLink = (e: El) => e.type === 'link' || e.type === 'beam' || e.type === 'stream';
    const placed = this.els.filter((e) => !isLink(e));
    const pos = layout(this.lay, placed.length, placed.map((e) => (e.parent >= 0 && this.els[e.parent] ? placed.indexOf(this.els[e.parent]!) : -1)), r);
    const yaw = (r() - 0.5) * 0.9, cy = Math.cos(yaw), sy = Math.sin(yaw);
    placed.forEach((e, i) => { const p = pos[i]!; e.p = [p[0] * cy - p[2] * sy, p[1], p[0] * sy + p[2] * cy]; e.side = e.p[0] >= 0 ? 1 : -1; });
    // links: default endpoints are the placed elements around them in the list
    for (const e of this.els) if (isLink(e)) {
      const before = this.els.slice(0, e.k).reverse().find((q) => !isLink(q)), after = this.els.slice(e.k + 1).find((q) => !isLink(q));
      if (!(this.els[e.from] && !isLink(this.els[e.from]!))) e.from = before ? before.k : (placed[0]?.k ?? 0);
      if (!(this.els[e.to] && !isLink(this.els[e.to]!)) || e.to === e.from) e.to = after ? after.k : (placed[placed.length - 1]?.k ?? 0);
    }
    const ext = Math.max(2.2, ...placed.map((e) => Math.hypot(e.p[0], e.p[2]) + 1.1 * e.size));
    const maxY = Math.max(1.2, ...placed.map((e) => e.p[1] + e.size * 1.2));
    const zc = this.lay === 'depth' ? -((placed.length - 1) * 1.5) : 0;
    const ctr: V3 = [0, maxY * 0.45, zc];
    if (typeof d.camera === 'string') (st as any).cam = d.camera;
    this.ctr = ctr;
    const cd = clamp(Number(d.camDist) || 1, 0.6, 2.2);
    plan(this, placed.map((e) => ({ t: e.word.start, p: v3.lerp(ctr, [e.p[0], e.p[1] + e.size * 0.6, e.p[2]], 0.7), d: (4.2 + 2.0 * e.size) * cd })), { tgt: ctr, dist: (Math.max(ext, maxY * 0.9) * 2.5 + 3) * cd });
    if (d.quiz) this.quizT = d.quiz.cue ? this.cue(d.quiz.cue, n, n + 1).start : this.t0 + (this.t1 - this.t0) * 0.7;
    this.floorR = Math.ceil(ext + 2);
    this.floorAt = ['stack', 'sphere', 'spiral', 'diagonal', 'wave', 'scatter'].includes(this.lay) ? null : [0, 0, zc];
  }
  override init() {
    super.init();
    const em = new Set((Array.isArray(this.data.emphasis) ? this.data.emphasis : []).flatMap((w: string) => String(w).split(/\s+/)).map(norm).filter(Boolean));
    if (em.size) for (const k of this.kw) if (em.has(norm(k.w.w))) { k.hot = 'ember'; k.done = 'signal'; k.pop = 0.3; }
  }
  override glassItems(t: number): GlassItem[] {
    const out: GlassItem[] = [];
    const G: Record<string, [GeoKind, V3, number, number?]> = {
      box: ['box', [0.96, 0.96, 0.96], 0.02], sphere: ['sphere', [1.06, 1.06, 1.06], 0.07], cylinder: ['cyl', [0.88, 0.98, 0.88], 0.01],
      cone: ['cone', [1.06, 1.12, 1.06], 0.01], torus: ['torus', [1.32, 1.32, 1.32], -0.21], prism: ['prism', [0.96, 1.08, 0.96], 0.01],
      panel: ['box', [1.8, 1.2, 0.05], 0.2, 0.6], code: ['box', [2.1, 1.44, 0.05], 0.13, 0.7], orbit: ['sphere', [0.34, 0.34, 0.34], 0.43],
    };
    const O: Record<string, [GeoKind, V3, number]> = {
      server: ['box', [0.96, 1.66, 0.96], 0.02], db: ['cyl', [1.2, 1.24, 1.2], 0], globe: ['sphere', [1.4, 1.4, 1.4], 0.08], cube: ['box', [1.16, 1.16, 1.16], 0.02],
      pyramid: ['pyr', [1.95, 1.33, 1.95], 0], chip: ['box', [1.22, 0.17, 1.22], 0.005], phone: ['box', [0.7, 1.28, 0.12], 0.01], lock: ['box', [0.98, 0.63, 0.42], 0.01],
    };
    for (const e of this.els) {
      const spec = e.type === 'object' ? O[e.object] : G[e.type];
      if (!spec) continue;
      const X = this.xf(e, t);
      if (X.al <= 0) continue;
      const revealing = ['draw', 'assemble', 'glitch', 'scan'].includes(e.anim);
      out.push({ key: `${this.idx}:${e.k}`, geo: spec[0], dims: spec[1], y0: spec[2], pos: X.pos, scale: X.s, yaw: X.yaw,
        color: this.tones[e.tone] ?? this.style.tint, alpha: X.al * (revealing ? ease.inQuad(X.rev) : 1), frost: (spec as any)[3] ?? 0 });
    }
    return out;
  }
  /** Element transform at time t: position, scale vector, yaw, reveal progress, alpha. */
  xf(e: El, t: number) {
    const age = t - e.word.start, p = clamp((age + 0.05) / 0.85), q = ease.outCubic(p);
    let pos: V3 = [e.p[0], e.p[1], e.p[2]], s: V3 = [e.size, e.size, e.size], yaw = 0, al = 1, rev = 1;
    switch (e.anim) {
      case 'grow': s = v3.mul(s, Math.max(0.001, q)); break;
      case 'pop': s = v3.mul(s, Math.max(0.001, ease.outBack(p))); break;
      case 'fly': pos = v3.add(pos, [e.side * 6 * (1 - q), 0.6 * (1 - q), 0]); break;
      case 'drop': pos = v3.add(pos, [0, 4 * (1 - ease.outBack(p)), 0]); break;
      case 'rise': pos = v3.add(pos, [0, -2 * (1 - q), 0]); al = q; break;
      case 'unfold': s = [s[0], s[1] * Math.max(0.001, q), s[2]]; break;
      default: rev = p;
    }
    const sp = this.style.spin;
    if (e.idle === 'spin') yaw = t * 0.6 * sp + e.k;
    else if (e.idle === 'pulse') s = v3.mul(s, 1 + 0.06 * Math.sin(t * 3 + e.k));
    else if (e.idle === 'float') pos = v3.add(pos, [0, 0.12 * Math.sin(t * 1.5 + e.k), 0]);
    else if (e.idle === 'orbit' && age > 0.8) { const a = (age - 0.8) * 0.25 * sp, c = Math.cos(a), si = Math.sin(a); pos = [pos[0] * c - pos[2] * si, pos[1], pos[0] * si + pos[2] * c]; }
    if (this.trans === 'morph' && age < 0.7) pos = v3.lerp(this.ctr, pos, ease.outCubic(clamp(age / 0.7)));
    if (this.exitMorph && t > this.t1 - 0.4) { const k = ease.inCubic(prog(t, this.t1 - 0.4, this.t1)); pos = v3.lerp(pos, this.ctr, k); s = v3.mul(s, 1 - 0.9 * k); }
    return { pos, s, yaw, al: age < -0.05 ? 0 : al, rev, age };
  }
  override draw3D(P: Pen3, t: number) {
    const st = this.style, seed = (Number(this.sc.meta?.seed) || 7) + this.idx * 31;
    if (this.lay === 'timeline') {
      const xs = this.els.filter((e) => e.type !== 'link' && e.type !== 'beam').map((e) => e.p);
      if (xs.length) { const a = xs[0]!, b = xs[xs.length - 1]!, g = prog(t, this.t0 + 0.2, this.t0 + 1.2), A: V3 = [a[0] - 1, 0.02, a[2]], B: V3 = [b[0] + 1, 0.02, b[2]]; P.seg(A, v3.lerp(A, B, g), 2, scl(this.tones.accent!, 1.4), 1); }
    }
    for (const e of this.els) {
      const col = this.tones[e.tone] ?? st.tint;
      if (e.type === 'stream') {
        const pa = this.xf(this.els[e.from]!, t).pos, pb = this.xf(this.els[e.to]!, t).pos;
        const ps = arcPts([pa[0], pa[1] + 0.4, pa[2]], [pb[0], pb[1] + 0.4, pb[2]], 0.6 + 0.5 * hash(e.k, seed), 30);
        const g = prog(t, e.word.start - 0.1, e.word.start + 0.6);
        if (g > 0) for (let i = 0; i < 60; i++) {
          const u = (t * (0.3 + 0.2 * hash(i, 9)) + hash(i, e.k)) % 1;
          if (u > g) continue;
          const q = along(ps, u), j = 0.12 * Math.sin(i * 7.3 + t * 3);
          P.dot([q[0] + j, q[1] + 0.1 * Math.cos(i * 3.1 + t * 2), q[2] - j], 5 + 4 * hash(i, 4), scl(i % 5 ? col : LIN.ember, 2.0), 0.9);
        }
        continue;
      }
      if (e.type === 'link' || e.type === 'beam') {
        const pa = this.xf(this.els[e.from]!, t).pos, pb = this.xf(this.els[e.to]!, t).pos;
        const ps = e.type === 'beam' ? Array.from({ length: 13 }, (_, i) => v3.lerp([pa[0], pa[1] + 0.5, pa[2]], [pb[0], pb[1] + 0.5, pb[2]], i / 12)) : arcPts([pa[0], pa[1] + 0.2, pa[2]], [pb[0], pb[1] + 0.2, pb[2]], 0.8 + 0.4 * hash(e.k, seed), 30);
        link(P, ps, prog(t, e.word.start - 0.1, e.word.start + 0.5, ease.inOutQuad), prog(t, e.word.start + 0.4, e.word.start + 0.7), t, col, 0.45 + 0.2 * hash(e.k, 3), e.k * 0.21, e.idle === 'orbit');
        continue;
      }
      const X = this.xf(e, t);
      if (X.al <= 0) continue;
      const g = geometry(e, t, Math.max(0, X.age));
      const cy = Math.cos(X.yaw), sy = Math.sin(X.yaw);
      const Wp = (q: V3): V3 => [X.pos[0] + X.s[0] * (q[0] * cy - q[2] * sy), X.pos[1] + X.s[1] * q[1], X.pos[2] + X.s[2] * (q[0] * sy + q[2] * cy)];
      const style = (['draw', 'assemble', 'glitch', 'scan'].includes(e.anim) ? e.anim : 'scan') as Reveal | 'draw';
      const hot = pulse(t, e.word.start + 0.85, 0.3);
      const base = scl(col, 1.05 + 1.3 * hot);
      for (const [[a, b], al] of reveal(g.segs, X.rev, style, g.h, seed + e.k, t)) P.seg(Wp(a), Wp(b), 1.9, base, al * X.al, 0.15);
      for (const [[a, b], al] of reveal(g.hot, X.rev, style, g.h, seed + e.k + 5, t)) P.seg(Wp(a), Wp(b), 2.6, scl(LIN.signal, 1.6 + hot), al * X.al, 0.18);
      if (X.rev > 0.6) for (const dt of g.dots) P.dot(Wp(dt), e.type === 'particles' ? 4 : 8, scl(e.type === 'particles' ? col : LIN.signal, e.type === 'particles' ? 1.6 : 2.4), X.al * (e.type === 'particles' ? 0.85 : 1));
      if (style === 'scan' && X.rev < 1) P.ring(Wp([0, (g.h + 0.05) * ease.inOutQuad(X.rev), 0]), 0.9, 3, scl(LIN.signal, 2), 1, 36);
    }
    const m = this.G.mascot, v = this.view;
    if (m && m.on && v && P.mirror === null && !this.cta) {
      const side = m.side === -1 ? -1 : 1, hop = this.hits.reduce((acc, h) => acc + pulse(t, h, 0.12), 0);
      const base = v3.add(v3.add(v3.add(v.pos, v3.mul(v.right, side * 1.18)), v3.mul(v.up, 0.15 + 0.22 * Math.min(1, hop))), v3.mul(v.fwd, 5.2));
      const yaw = Math.atan2(v.pos[0] - base[0], v.pos[2] - base[2]) + 0.5 * Math.sin(t * 0.9) - side * 0.4;
      drawObj(P, asObj(m.kind ?? 'bot'), base, 0.32, yaw, clamp((t - this.t0) / 0.6), t, 'scan', this.tones.alt ?? st.tint, 9, Math.min(1, hop));
    }
  }
  override drawUI(ctx: CanvasRenderingContext2D, t: number, _c: Cam) {
    const v = this.view; if (!v) return;
    const used: [number, number, number, number][] = [];   // big words never overlap: later ones step down
    for (const e of this.els) {
      if (e.type === 'link' || e.type === 'beam' || e.type === 'stream') continue;
      const X = this.xf(e, t); if (X.al <= 0) continue;
      const g = geometry(e, t, Math.max(0, X.age));
      const a = prog(t, e.word.start + 0.25, e.word.start + 0.55) * X.al;
      const top: V3 = [X.pos[0], X.pos[1] + g.h * X.s[1] + 0.12, X.pos[2]];
      if (e.type === 'counter' || e.type === 'text') {
        const q = v.P([X.pos[0], X.pos[1] + 0.55 * e.size, X.pos[2]]); if (!q) continue;
        const txt = e.type === 'counter' ? countUp(e.value || e.label, X.age / 0.9) : (e.label || e.value);
        const fam = ARCH(118, 900), size = clamp((150 * e.size * v.s.dist) / q[2], 40, 230) * (1 + 0.25 * (1 - ease.outExpo(clamp(X.age / 0.18))));
        const s2 = Math.min(size, (940 * 100) / Math.max(1, measure(txt, fam, 100)));
        const half = measure(txt, fam, s2) / 2;
        ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = clamp(X.age / 0.15) * X.al;
        ctx.font = font(fam, s2); ctx.textAlign = 'center';
        ctx.fillStyle = mixColor('signal', 'bone', prog(t, e.word.start + 0.9, e.word.start + 1.5));
        const tx = clamp(q[0], 30 + half, 1050 - half);
        let ty = clamp(q[1], 380, 1400);
        for (let g2 = 0; g2 < 6; g2++) { const hit = used.find(([x0, y0, x1, y1]) => tx + half > x0 && tx - half < x1 && ty > y0 && ty - s2 < y1); if (!hit) break; ty = Math.min(1460, hit[3] + s2 * 1.05); }
        used.push([tx - half, ty - s2, tx + half, ty]);
        ctx.fillText(txt, tx, ty);
        ctx.textAlign = 'left'; ctx.globalAlpha = 1;
        if (e.type === 'counter' && e.label && e.value) this.tag(ctx, [X.pos[0], X.pos[1], X.pos[2]], e.label, e.sub, a, { dx: 40 * e.side, dy: 70, size: 26 });
        continue;
      }
      if (e.type === 'code') {
        const fam = F.mono(500);
        e.lines.forEach((ln, j) => {
          const q = v.P([X.pos[0] - 0.92 * X.s[0], X.pos[1] + (1.3 - 0.24 * j) * X.s[1], X.pos[2] + 0.02]);
          if (!q) return;
          const size = clamp((30 * e.size * v.s.dist) / q[2], 14, 42) * this.ls, nch = Math.floor((X.age - 0.3 - j * 0.35) * 26);
          if (nch <= 0) return;
          ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.font = font(fam, size); ctx.textAlign = 'left';
          ctx.fillStyle = j === 0 ? rgba('signal', X.al) : rgba('bone', 0.95 * X.al);
          ctx.fillText(ln.slice(0, nch) + (nch < ln.length && Math.floor(t * 4) % 2 ? '_' : ''), q[0], q[1]);
        });
      }
      if (e.label) this.tag(ctx, top, e.label, e.sub || (e.value && e.type !== 'gauge' ? e.value : ''), a, { dx: (50 + 20 * (e.k % 3)) * e.side, dy: -50 - 45 * (e.k % 3), size: (e.size > 1.3 ? 36 : 30) * this.ls, hot: 1 - prog(t, e.word.start + 0.3, e.word.start + 1.1) });
      if (e.type === 'gauge' && e.value) {
        const q = v.P([X.pos[0], X.pos[1] + 0.75 * X.s[1], X.pos[2]]);
        if (q) { ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.font = font(F.mono(500), 40); ctx.textAlign = 'center'; ctx.fillStyle = rgba('bone', a); ctx.fillText(countUp(e.value, X.age / 1.0), q[0], q[1]); ctx.textAlign = 'left'; }
      }
    }
    const qz = this.data.quiz;
    if (qz && Array.isArray(qz.options)) {
      const t0q = (this.ws[0]?.start ?? this.t0) + 0.4, a = prog(t, t0q, t0q + 0.3), rev = t >= this.quizT;
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = a;
      const y0 = 1060, fam = ARCH(105, 800);
      ctx.fillStyle = rgba('ink', 0.78); ctx.fillRect(70, y0 - 70, 940, 90 + qz.options.length * 92);
      ctx.font = font(F.mono(500), 26); ctx.fillStyle = rgba('ash', 1); ctx.fillText(String(qz.question ?? '').toUpperCase(), 100, y0 - 22);
      qz.options.forEach((o: string, i: number) => {
        const y = y0 + i * 92, right = i === qz.answer, tin = prog(t, t0q + 0.15 * i, t0q + 0.15 * i + 0.25);
        ctx.globalAlpha = a * tin * (rev && !right ? 0.35 : 1);
        ctx.strokeStyle = rev && right ? this.style.tintHex : rgba('bone', 0.6); ctx.lineWidth = rev && right ? 4 : 2;
        if (rev && right) { ctx.fillStyle = rgba('signal', 0.22 + 0.2 * pulse(t, this.quizT, 0.3)); ctx.fillRect(100, y, 880, 72); }
        ctx.strokeRect(100, y, 880, 72);
        ctx.font = font(fam, 40); ctx.fillStyle = rgba(rev && right ? 'signal' : 'bone', 1);
        ctx.fillText(`${'ABC'[i]}   ${o}`, 126, y + 51);
        if (rev && !right) { ctx.fillStyle = rgba('bone', 0.8); ctx.fillRect(120, y + 36, 840, 3); }
      });
      if (!rev && t > this.quizT - 1.6) {
        const left = Math.ceil(this.quizT - t), k = (this.quizT - t) % 1;
        ctx.globalAlpha = 1; ctx.strokeStyle = this.style.tintHex; ctx.lineWidth = 6;
        ctx.beginPath(); ctx.arc(920, y0 - 110, 46, -Math.PI / 2, -Math.PI / 2 + TAU * k); ctx.stroke();
        ctx.font = font(ARCH(110, 900), 56); ctx.textAlign = 'center'; ctx.fillStyle = rgba('bone', 1); ctx.fillText(String(Math.max(1, left)), 920, y0 - 90); ctx.textAlign = 'left';
      }
      ctx.globalAlpha = 1;
    }
    if (this.cta) {
      const a = prog(t, this.tEnd - 0.2, this.tEnd + 0.4), pos = (Number(this.sc.meta?.seed) || 0) % 3;
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = a;
      const fam = ARCH(115, 900), txt = 'FOLLOW @DATAVELVET', s = Math.min(64, (900 * 100) / measure(txt, fam, 100));
      const y = pos === 0 ? 1450 : pos === 1 ? 1600 : 1350;
      ctx.font = font(fam, s); ctx.textAlign = 'center'; ctx.fillStyle = rgba('bone', 1); ctx.fillText(txt, 540, y);
      ctx.fillStyle = this.style.tintHex; ctx.fillRect(540 - 300 * ease.outCubic(a), y + 22, 600 * ease.outCubic(a), 4);
      ctx.textAlign = 'left'; ctx.globalAlpha = 1;
    }
  }
  override postFX(t: number) {
    const k = 1 - prog(t, this.t0, this.t0 + 0.45), j = noise1(t * 40, this.idx);
    let o: any = {};
    switch (this.trans) {
      case 'flash': o = { flash: 0.8 * k * k }; break;
      case 'zoom': o = { zoom: 1 + 0.3 * k * k }; break;
      case 'whip': o = { shake: [140 * k * k * (this.idx % 2 ? 1 : -1), 0], ca: 1.2 + 6 * k }; break;
      case 'fade': o = { fade: k }; break;
      case 'glitch': o = { shake: [30 * k * j, 12 * k * noise1(t * 50, 2)], ca: 1 + 10 * k, invert: k > 0.5 && Math.floor(t * 30) % 3 === 0 ? 1 : 0 }; break;
      case 'iris': o = { vignette: 0.4 + 2.2 * k }; break;
      case 'morph': o = { zoom: 1 + 0.08 * k * k, ca: 1 + 3 * k }; break;
    }
    if (this.idx === 0) o.fade = Math.max(o.fade ?? 0, 1 - prog(t, 0, 0.35));
    if (this.cta) o.fade = Math.max(o.fade ?? 0, prog(t, this.t1 - 0.9, this.t1 - 0.05, ease.inCubic));
    return o;
  }
}
function countUp(v: string, k: number) {
  const m = v.match(/\d[\d,]*(\.\d+)?/); if (!m) return v;
  const target = parseFloat(m[0].replace(/,/g, '')), cur = target * ease.outCubic(clamp(k)), dec = m[1] ? m[1].length - 1 : 0;
  return v.replace(m[0], m[0].includes(',') ? Math.round(cur).toLocaleString('en-US') : cur.toFixed(dec));
}
