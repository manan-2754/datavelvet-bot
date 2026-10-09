// Generic plates for the bot. A generated script (data/lyrics.json → `scenes`) says which plate each scene
// uses and fills it with items + cue words; every plate is laid out from that data, in the house style:
// graph paper or bone paper, the plotter pen (spark), karaoke captions, mono notes, stamps.
// Layout is vertical (1080×1920): world origin at the centre, header at the top, diagram in the middle,
// captions in the lower third.
import type * as THREE from 'three';
import { Scene, type Frame, type PostOverrides } from '../engine/scene';
import { FSPass, Layer2D, W, H } from '../engine/gl';
import { LineBatch } from '../engine/lines';
import { rgba } from '../engine/palette';
import { F, font, measure } from '../engine/type';
import { norm, type Line, type Word } from '../engine/lyrics';
import { clamp, ease, mulberry32, noise1, prog, pulse } from '../engine/util';
import {
  Plot, Cam2D, gridPass, setGrid, drawKaraoke, placeRow, drawPen, w2s, setWorld, label, rowWidth, type KWord, type Cam,
} from './_vo';
import { Rig, View, Pen3, styleFor, floor, handheld, type Style, type V3 } from './_holo3d';

export const PAPER_GLSL = /* glsl */ `
uniform vec4 uCam; uniform vec2 uRes;
void main() {
  vec2 sp = vec2(vUv.x, 1.0 - vUv.y) * uRes;
  vec2 d = sp - 0.5 * uRes;
  float c = cos(-uCam.w), s = sin(-uCam.w);
  d = vec2(c * d.x - s * d.y, s * d.x + c * d.y) / uCam.z;
  vec2 p = uCam.xy + d;
  vec3 col = C_BONE * 0.965;
  float f = fbm(vec2(p.x * 0.004, p.y * 0.05), 4);
  float cloud = fbm(p * 0.0025 + 3.0, 4);
  col *= 1.0 - 0.035 * f - 0.03 * cloud;
  vec2 g = abs(fract(p / 24.0 + 0.5) - 0.5) * 24.0 * uCam.z;
  float gl = max(1.0 - smoothstep(0.0, 1.0, g.x), 1.0 - smoothstep(0.0, 1.0, g.y));
  col = mix(col, C_GRAPHITE, 0.035 * gl);
  fragColor = vec4(col, 1.0);
}`;

export const ARCH = (wd: number, wt: number) => F.archivo(wd, wt);
export const HALF_W = W / 2;          // 540
export const HALF_H = H / 2;          // 960

/** Greedy word wrap into centred karaoke rows; shrinks the size until it fits in maxRows. */
export function wrapKaraoke(words: Word[], cx: number, y0: number, maxW: number, size: number, fam: string, group: string, o: { maxRows?: number; lh?: number; minSize?: number; ant?: number; done?: string } = {}) {
  const maxRows = o.maxRows ?? 4, lh = o.lh ?? 1.2;
  let s = size, rows: Word[][] = [];
  for (; s >= (o.minSize ?? 30); s -= 2) {
    rows = [];
    let cur: Word[] = [];
    for (const w of words) {
      const next = [...cur, w];
      if (cur.length && rowWidth(next.map((x) => x.w), s, fam) > maxW) { rows.push(cur); cur = [w]; } else cur = next;
    }
    if (cur.length) rows.push(cur);
    if (rows.length <= maxRows) break;
  }
  const kws: KWord[] = [];
  rows.forEach((r, i) => {
    const pr = placeRow(r, 0, y0 + i * s * lh, s, fam, group, { ant: o.ant ?? 0.25, done: o.done });
    pr.words.forEach((k) => (k.x += cx - pr.width / 2));
    kws.push(...pr.words);
  });
  return { kws, size: s, height: rows.length * s * lh, rows: rows.length };
}

/** A rubber stamp (signal ink, double frame, knocked-out speckles), as a canvas. */
export function makeStamp(text: string, sub: string, seed = 7, SW = 1300, SH = 320) {
  const cv = document.createElement('canvas');
  cv.width = SW; cv.height = SH;
  const c = cv.getContext('2d')!;
  const col = '#FF4D12';
  c.strokeStyle = col; c.fillStyle = col;
  c.lineWidth = 12; c.strokeRect(16, 16, SW - 32, SH - 32);
  c.lineWidth = 4; c.strokeRect(40, 40, SW - 80, SH - 80);
  const fam = F.archivo(100, 900);
  const fs = Math.min(160, (150 * (SW - 180)) / Math.max(1, measure(text, fam, 150)));
  c.font = font(fam, fs);
  c.textAlign = 'center'; c.textBaseline = 'alphabetic';
  c.fillText(text, SW / 2, SH / 2 + fs * 0.32);
  if (sub) {
    c.font = font(F.mono(500), 24);
    (c as any).letterSpacing = '8px';
    c.fillText(sub, SW / 2, SH - 52);
  }
  c.globalCompositeOperation = 'destination-out';
  const r = mulberry32(seed);
  for (let i = 0; i < 3200; i++) { c.globalAlpha = 0.25 + 0.75 * r(); c.beginPath(); c.arc(r() * SW, r() * SH, 0.6 + r() * 2.4, 0, 6.3); c.fill(); }
  for (let i = 0; i < 30; i++) { c.globalAlpha = 0.18 * r(); c.fillRect(r() * SW, r() * SH, 60 + r() * 300, 2 + r() * 5); }
  c.globalAlpha = 1; c.globalCompositeOperation = 'source-over';
  return cv;
}

export function drawStamp(ctx: CanvasRenderingContext2D, c: Cam, stamp: HTMLCanvasElement, t: number, t0: number, x: number, y: number, scale: number, rot = -0.07) {
  if (t < t0) return;
  const age = t - t0;
  const sc = 1 + 0.6 * (1 - ease.outExpo(clamp(age / 0.12)));
  const [sx, sy] = w2s(c, x, y);
  const k = c.z * scale * sc, r = rot + c.roll;
  ctx.setTransform(k * Math.cos(r), k * Math.sin(r), -k * Math.sin(r), k * Math.cos(r), sx, sy);
  ctx.globalAlpha = 0.92 * clamp(age / 0.05);
  ctx.drawImage(stamp, -stamp.width / 2, -stamp.height / 2);
  ctx.globalAlpha = 1;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
}

function mixColor(a: string, b: string, k: number) {
  const pa = rgba(a).match(/\d+/g)!.map(Number), pb = rgba(b).match(/\d+/g)!.map(Number);
  return `rgba(${[0, 1, 2].map((i) => Math.round(pa[i]! + (pb[i]! - pa[i]!) * clamp(k))).join(',')},0.96)`;
}
export { mixColor };

/** Typed text: chars appear across [t0, t1]; hot (signal) while typing, cooling to `col`. */
export function typeText(ctx: CanvasRenderingContext2D, s: string, x: number, y: number, t: number, t0: number, t1: number, fam: string, size: number, col: string, paper: boolean, align: CanvasTextAlign = 'left') {
  if (t < t0 || !s) return 0;
  const n = Math.ceil(s.length * clamp((t - t0) / Math.max(0.08, t1 - t0)));
  const hot = 1 - prog(t, t1, t1 + 0.4);
  ctx.font = font(fam, size);
  const full = measure(s, fam, size);
  const x0 = align === 'center' ? x - full / 2 : align === 'right' ? x - full : x;
  const k = clamp(hot);
  ctx.fillStyle = k > 0.02 ? mixColor(paper ? 'blood' : 'signal', col, 1 - k) : rgba(col, 0.96);
  ctx.textAlign = 'left';
  ctx.fillText(s.slice(0, n), x0, y);
  return full;
}

/** Fit a single line of display text to a width. */
export function fitSize(s: string, fam: string, maxW: number, max: number) {
  return Math.min(max, (100 * maxW) / Math.max(1, measure(s, fam, 100)));
}

/** Word-wrapped plain text (mono notes on cards). */
export function wrapText(s: string, fam: string, size: number, maxW: number, maxLines = 3) {
  const out: string[] = [];
  let cur = '';
  for (const w of String(s || '').split(/\s+/)) {
    const t = cur ? `${cur} ${w}` : w;
    if (cur && measure(t, fam, size) > maxW) { out.push(cur); cur = w; } else cur = t;
  }
  if (cur) out.push(cur);
  return out.slice(0, maxLines);
}

export const seedOf = (s: string) => { let h = 2166136261; for (const ch of s) h = Math.imul(h ^ ch.charCodeAt(0), 16777619); return h >>> 0; };

export abstract class GenPlate extends Scene {
  /** Live 3D holo layer (perspective rig + hologram pen), drawn over the background, under the UI. */
  has3D = false;
  rig = new Rig();
  view: View | null = null;
  style!: Style;
  fx3: LineBatch | null = null;
  floorAt: V3 | null = [0, 0, 0];
  floorR = 7;
  gridInk = 0.8;
  viewCY = H / 2 - 150;
  /** Bone paper (ink) instead of graph paper in the dark. */
  paperMode = false;
  /** Draw the default header (plate number · topic, plate title). Paper plates draw their own band. */
  header = true;
  /** Caption block y (lower third), or 'none'. */
  captionY: number | 'none' = 620;
  captionSize = 50;
  grid = gridPass(24, 96);
  paper = new FSPass(PAPER_GLSL, { uCam: { value: [0, 0, 1, 0] }, uRes: { value: [W, H] } });
  plot = new Plot();
  cam = new Cam2D();
  lines!: LineBatch;
  fx = new LineBatch(60000);
  ui = new Layer2D();
  kw: KWord[] = [];
  sc: any = {};
  data: any = {};
  idx = 0;
  ws: Word[] = [];
  sl: Line[] = [];
  cursor = 0;
  hits: number[] = [];
  penFrom = 1e9;

  /** Build strokes, notes, camera keys from this.data. */
  abstract build(): void;
  /** Extra Canvas2D drawing (under the karaoke). */
  drawUI(_ctx: CanvasRenderingContext2D, _t: number, _c: Cam): void {}
  /** Extra additive line drawing (glows, packets, 3D). */
  drawFX(_X: LineBatch, _t: number, _c: Cam): void {}
  /** 3D holo drawing (world units, see _holo3d.ts). */
  draw3D(_P: Pen3, _t: number): void {}
  /** Over the karaoke (stamps). */
  drawOver(_ctx: CanvasRenderingContext2D, _t: number, _c: Cam): void {}
  /** Post overrides on top of the plate defaults. */
  postFX(_t: number): PostOverrides { return {}; }

  get t0() { return this.ctx.start; }
  get t1() { return this.ctx.end; }

  override init() {
    const ly = this.ctx.lyrics;
    this.idx = this.ctx.params.scene ?? 0;
    this.sc = ly.scenes[this.idx] ?? {};
    this.data = this.sc.data ?? {};
    this.sl = ly.lines.filter((l: any) => l.scene === this.idx);
    this.ws = this.sl.flatMap((l) => l.words).filter((w) => norm(w.w));
    this.plot.paper = this.paperMode;
    this.lines = new LineBatch(60000, this.paperMode ? { blend: 'normal' } : {});
    const meta = this.sc.meta ?? {};
    this.style = styleFor(Number(meta.seed) || seedOf(String(meta.topic ?? '')), this.idx);
    this.rig.t0 = this.t0;
    this.build();
    if (this.has3D && !this.fx3) this.fx3 = new LineBatch(140000);
    if (this.captionY !== 'none' && this.ws.length) {
      const r = wrapKaraoke(this.ws, 0, this.captionY, 960, this.captionSize, ARCH(100, 700), 'cap', { maxRows: 4, minSize: 34 });
      const over = this.captionY + r.height - 880;          // keep the whole caption block on screen
      if (over > 0) r.kws.forEach((k) => (k.y -= over));
      this.kw.push(...r.kws);
    }
    if (!this.cam.keys.length) {
      const s = (this.idx % 2 ? 1 : -1);
      this.cam.key(this.t0, 0, -20, 0.97, -0.006 * s);
      this.cam.key(this.t1, 0, 20, 1.03, 0.006 * s, ease.linear);
    }
    this.penFrom = Math.min(...this.plot.pens.map((p) => p.t0), 1e9) - 0.3;
  }

  /** The word for cue q in this scene (phrase match, then first token, then a spread fallback). */
  cue(q: string | undefined, k = 0, n = 3): Word {
    const ws = this.ws;
    if (!ws.length) return { w: '', start: this.t0 + 0.3, end: this.t0 + 0.6, line: 0, index: 0, gi: 0 } as Word;
    const toks = String(q ?? '').split(/\s+/).map(norm).filter(Boolean);
    const find = (from: number) => {
      if (!toks.length) return -1;
      for (let i = from; i <= ws.length - toks.length; i++) if (toks.every((tk, j) => norm(ws[i + j]!.w) === tk)) return i;
      for (let i = from; i < ws.length; i++) if (norm(ws[i]!.w) === toks[0]) return i;
      return -1;
    };
    let i = find(this.cursor);
    if (i < 0) i = find(0);
    if (i < 0) i = Math.min(ws.length - 1, Math.round(((k + 1) * ws.length) / (n + 1)));
    this.cursor = i + 1;
    return ws[i]!;
  }

  override render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides {
    const { renderer, comp } = this.ctx;
    const t = f.t;
    const c0 = this.cam.at(t);
    const c: Cam = { cx: c0.cx + 5 * noise1(t * 0.5, this.idx + 1), cy: c0.cy + 4 * noise1(t * 0.4, this.idx + 2), z: c0.z, roll: c0.roll + (this.paperMode ? 0.004 * noise1(t * 0.5, 3) : 0) };
    const pen = this.plot.penAt(t);
    const ps = pen && t > this.penFrom ? w2s(c, pen.x, pen.y) : null;
    if (this.paperMode) {
      (this.paper.u.uCam!.value as number[]).splice(0, 4, c.cx, c.cy, c.z, c.roll);
      this.paper.render(renderer, out);
    } else {
      setGrid(this.grid, c, { reveal: [0, 0, this.idx === 0 ? 4200 * ease.outCubic(prog(t, 0, 1.6)) : 1e5], ink: this.gridInk, pen: ps ? [ps[0], ps[1], 1] : [0, 0, 0] });
      this.grid.render(renderer, out);
    }
    if (this.has3D && this.fx3) {
      const v = new View(handheld(this.rig.at(t), t, this.style.hand));
      v.cy = this.viewCY;
      this.view = v;
      const Z = this.fx3; Z.clear();
      const P3 = new Pen3(Z, v, this.style.tint);
      if (this.floorAt) floor(P3, this.style.floor, this.floorAt, this.floorR, prog(t, this.t0 + 0.05, this.t0 + 1.1), this.style.tint, t);
      this.draw3D(P3, t);
      Z.render(renderer, out);
    }
    const U = this.ui; U.clear();
    if (this.paperMode) { this.drawUI(U.ctx, t, c); comp.draw(renderer, U.upload(), out); U.clear(); }
    const L = this.lines; L.clear();
    this.plot.draw(t, c, L);
    L.render(renderer, out);
    if (!this.paperMode) this.drawUI(U.ctx, t, c);
    if (this.header) this.drawHeader(U.ctx, t, c);
    drawKaraoke(U.ctx, c, t, this.kw, { paper: this.paperMode, pop: 0.04 });
    this.plot.drawNotes(t, c, U.ctx);
    this.drawOver(U.ctx, t, c);
    comp.draw(renderer, U.upload(), out);
    const X = this.fx; X.clear();
    this.drawFX(X, t, c);
    if (!this.paperMode && t > this.penFrom) drawPen(X, t, (tt) => { if (tt < this.penFrom) return null; const q = this.plot.penAt(tt); return q ? w2s(c, q.x, q.y) : null; }, { scale: 1, rate: 60, from: this.penFrom });
    X.render(renderer, out);
    const hit = this.hits.length ? Math.max(...this.hits.map((h) => pulse(t, h, 0.08))) : 0;
    const base: PostOverrides = this.paperMode
      ? { bloom: 0.15, bloomThreshold: 1.4, vignette: 0.28, grain: 0.04, halation: 0.05, ca: 0.6, paper: 1 }
      : { bloom: 0.72, bloomThreshold: 0.84, vignette: 0.42, grain: 0.05 };
    return { ...base, zoom: 1 + 0.016 * hit, shake: [5 * hit * noise1(t * 60, 1), 5 * hit * noise1(t * 60, 2)], ...this.postFX(t) };
  }

  /** A label pinned to a 3D point: leader line + chip (screen space, kept clear of header and captions). */
  tag(ctx: CanvasRenderingContext2D, p: V3, title: string, sub: string, a: number, o: { dx?: number; dy?: number; size?: number; hot?: number } = {}) {
    const q = this.view?.P(p);
    if (!q || a <= 0) return;
    const dx = o.dx ?? 0, dy = o.dy ?? -70, size = o.size ?? 34;
    const fam = ARCH(112.5, 900), tw = measure(title, fam, size), sw = sub ? measure(sub, F.mono(400), 18) : 0;
    const bw = Math.max(tw, sw) + 36, bh = sub ? size + 44 : size + 22;
    let x = q[0] + dx, y = q[1] + dy;
    const right = dx >= 0;
    let bx = right ? x : x - bw;
    bx = clamp(bx, 30, W - 30 - bw); y = clamp(y, 330, 1330);
    x = right ? bx : bx + bw;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = a;
    ctx.strokeStyle = this.style.tintHex; ctx.lineWidth = 1.6;
    ctx.beginPath(); ctx.moveTo(q[0], q[1]); ctx.lineTo(x, y); ctx.stroke();
    ctx.fillStyle = this.style.tintHex; ctx.beginPath(); ctx.arc(q[0], q[1], 4, 0, 6.3); ctx.fill();
    ctx.fillStyle = rgba('ink2', 0.82); ctx.fillRect(bx, y - bh, bw, bh);
    ctx.fillStyle = this.style.tintHex; ctx.fillRect(bx, y - 3, bw * ease.outCubic(clamp(a * 1.5)), 3);
    ctx.font = font(fam, size);
    ctx.fillStyle = (o.hot ?? 0) > 0 ? mixColor('signal', 'bone', 1 - (o.hot ?? 0)) : rgba('bone', 0.97);
    ctx.textAlign = 'left';
    ctx.fillText(title, bx + 18, y - bh + size + 8);
    if (sub) { ctx.font = font(F.mono(400), 18); ctx.fillStyle = rgba('ash', 0.95); ctx.fillText(sub, bx + 18, y - 14); }
    ctx.globalAlpha = 1;
  }

  drawHeader(ctx: CanvasRenderingContext2D, t: number, c: Cam) {
    const meta = this.sc.meta ?? {};
    const a = prog(t, this.t0, this.t0 + 0.35);
    const ink = this.paperMode ? 'ink' : 'bone';
    setWorld(ctx, c, -480, -830);
    label(ctx, `${String((meta.i ?? this.idx) + 1).padStart(2, '0')} / ${String(meta.n ?? '').padStart(2, '0')}`, 0, 0, { size: 18, col: rgba('signal', 0.95 * a), spacing: 4 });
    label(ctx, String(meta.topic ?? '').toUpperCase().slice(0, 44), 110, 0, { size: 16, col: rgba(this.paperMode ? 'graphite' : 'ash', 0.9 * a), spacing: 3 });
    const title = String(this.sc.title ?? '');
    if (title) {
      const fam = ARCH(112.5, 900);
      const s = fitSize(title, fam, 960, 76);
      ctx.font = font(fam, s);
      ctx.fillStyle = rgba(ink, 0.96 * a);
      ctx.fillText(title, 0, 84 + 24 * (1 - ease.outCubic(a)));
      ctx.fillStyle = rgba('signal', a);
      ctx.fillRect(0, 108, 140 * ease.outCubic(prog(t, this.t0 + 0.1, this.t0 + 0.6)), 6);
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
  }
}
