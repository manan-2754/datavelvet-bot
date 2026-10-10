// The bot's plate library. Every class is a GenPlate laid out from its scene's data (written by the script
// writer, see bot/writer.py for the schema) — the same visual language as the hand-made plates: graph paper,
// bone-paper forms, the plotter pen, karaoke, stamps, live 3D hairlines.
import { LineBatch } from '../engine/lines';
import { LIN, rgba } from '../engine/palette';
import { F, font, measure } from '../engine/type';
import { type Word } from '../engine/lyrics';
import { clamp, ease, noise1, prog, pulse, TAU } from '../engine/util';
import { strokeText, type StrokeFontName } from '../engine/stroke';
import { pt, arc, rectPts, bezier, lengths, at, w2s, setWorld, label, scl, type Cam, type P, type RGB } from './_vo';
import { asObj, drawObj, pedestal, type Obj, type Pen3 } from './_holo3d';
import { GenPlate, seedOf as seedOfG, ARCH, wrapKaraoke, makeStamp, drawStamp, typeText, fitSize, wrapText, mixColor } from './_gen';

const seedOf = (s: string) => { let h = 2166136261; for (const ch of s) h = Math.imul(h ^ ch.charCodeAt(0), 16777619); return h >>> 0; };
const items = (d: any, max: number) => (Array.isArray(d?.items) ? d.items : []).slice(0, max);
const numIn = (v: any) => { const m = String(v ?? '').replace(/,/g, '').match(/-?\d+(\.\d+)?/); return m ? parseFloat(m[0]) : null; };
/** "100,000" counting up: replaces the number inside the string with its current value. */
function counting(v: any, k: number) {
  const s = String(v ?? '');
  const m = s.match(/\d[\d,]*(\.\d+)?/);
  if (!m) return s;
  const target = parseFloat(m[0].replace(/,/g, ''));
  const cur = target * ease.outCubic(clamp(k));
  const dec = m[1] ? m[1].length - 1 : 0;
  const txt = m[0].includes(',') ? Math.round(cur).toLocaleString('en-US') : cur.toFixed(dec);
  return s.replace(m[0], txt);
}

// ===================================================================== HOOK
export class Hook extends GenPlate {
  override header = false;
  override captionY: 'none' = 'none';
  motifY = 0; big = ''; bigT = 0; motif = 'dial';
  holoKind: Obj = 'globe'; holoT = 0;
  build() {
    const d = this.data, P = this.plot;
    const r = wrapKaraoke(this.ws, 0, -600, 960, 118, ARCH(100, 800), 'q', { maxRows: 5, minSize: 58, lh: 1.08 });
    this.kw.push(...r.kws);
    const cy = Math.max(-600 + r.height + 330, 140);
    this.motifY = cy;
    const w = this.cue(d.cue, 0, 1), t = w.start;
    this.motif = ['dial', 'chart', 'number', 'strike', 'holo'].includes(d.motif) ? d.motif : 'number';
    this.hits.push(t);
    if (this.motif === 'dial') {
      const R = 230;
      P.add(arc(0, cy, R, -Math.PI / 2, -Math.PI / 2 + TAU, 120), t - 0.2, t + 0.3, 'plot', { pen: true, ez: ease.inOutQuad, width: 2.4 });
      for (let i = 0; i < 24; i++) {
        const a = -Math.PI / 2 + (i / 24) * TAU, r0 = i % 6 === 0 ? R - 28 : R - 14, tt = t + 0.3 + i * 0.01;
        P.add([pt(r0 * Math.cos(a), cy + r0 * Math.sin(a)), pt(R * Math.cos(a), cy + R * Math.sin(a))], tt, tt + 0.03, 'dim', { width: 1.3 });
      }
      for (let i = 0; i < 3; i++) {
        const a = -Math.PI / 2 + (i / 3) * TAU, t0 = t + 0.6 + i * 0.16;
        P.add([pt(0, cy), pt((R - 40) * Math.cos(a), cy + (R - 40) * Math.sin(a))], t0, t0 + 0.12, 'signal', { pen: true, width: 5 });
      }
    } else if (this.motif === 'chart') {
      const x0 = -380, x1 = 380, yb = cy + 210, yt = cy - 230;
      P.add([pt(x0, yt), pt(x0, yb), pt(x1, yb)], t - 0.25, t + 0.15, 'plot', { pen: true, ez: ease.inOutQuad, width: 2.2 });
      const pts = [pt(x0 + 20, yb - 30), pt(x0 + 160, yb - 110), pt(x0 + 270, yb - 80), pt(x0 + 410, yb - 220), pt(x0 + 530, yb - 190), pt(x1 - 30, yt + 20)];
      P.add(pts, t + 0.15, t + 0.8, 'signal', { pen: true, ez: ease.inOutQuad, width: 5 });
      const e = pts[pts.length - 1]!;
      P.add([pt(e.x - 34, e.y + 6), e, pt(e.x - 6, e.y + 34)], t + 0.78, t + 0.86, 'signal', { pen: true, width: 5 });
      for (let i = 1; i < 5; i++) P.add([pt(x0, yb - i * 88), pt(x1, yb - i * 88)], t + 0.1, t + 0.4, 'cons', { dash: 10, alpha: 0.5, width: 1 });
    } else if (this.motif === 'holo') {
      this.has3D = true;
      this.holoKind = asObj(d.object, seedOfG(String(this.sc.meta?.topic ?? '')));
      this.holoT = t;
      this.viewCY = 960 + cy * 0.85 + 40;
      this.floorR = 3;
      const R = this.rig, y0 = this.style.r() * TAU;
      R.drift = 0.35 * this.style.spin;
      R.key(this.t0, { tgt: [0, 0.9, 0], yaw: y0, pitch: 0.55, dist: 8, fov: 40 });
      R.key(t, { tgt: [0, 0.6, 0], yaw: y0, pitch: 0.3, dist: 6.2 });
      R.key(this.t1, { tgt: [0, 0.6, 0], yaw: y0, pitch: 0.36, dist: 6.6 });
    } else if (this.motif === 'number') {
      this.big = String(d.value ?? '').slice(0, 9);
      this.bigT = t;
      P.add(arc(0, cy - 40, 280, Math.PI * 0.75, Math.PI * 0.75 + TAU * 0.98, 120), t - 0.1, t + 0.6, 'signal', { pen: true, ez: ease.inOutQuad, width: 3 });
    } else {
      P.add(rectPts(-330, cy - 130, 660, 260), t - 0.45, t - 0.05, 'plot', { pen: true, ez: ease.inOutQuad, width: 2.4 });
      P.add([pt(-380, cy - 180), pt(380, cy + 180)], t + 0.05, t + 0.18, 'signal', { pen: true, width: 9 });
      P.add([pt(380, cy - 180), pt(-380, cy + 180)], t + 0.2, t + 0.33, 'signal', { pen: true, width: 9 });
      P.note(String(d.value ?? '').slice(0, 26).toUpperCase(), 0, cy + 14, t - 0.35, { size: 40, col: 'bone', align: 'center', weight: 500 });
    }
    if (d.label) P.note(String(d.label).slice(0, 34).toUpperCase(), 0, cy + (this.motif === 'number' ? 230 : this.motif === 'holo' ? 380 : 330), t + 0.7, { size: 30, col: 'signal', align: 'center', hot: 0.3, spacing: 0.08 });
    this.cam.key(this.t0, 0, -120, 0.92, -0.008);
    this.cam.key(t, 0, cy * 0.25, 1.0, 0.002, ease.inOutCubic);
    this.cam.key(this.t1, 0, cy * 0.3, 1.04, 0.006, ease.linear);
  }
  override drawUI(ctx: CanvasRenderingContext2D, t: number, c: Cam) {
    setWorld(ctx, c, 0, -860);
    label(ctx, 'DATAVELVET', 0, 0, { size: 18, col: rgba('signal', 0.9 * prog(t, 0.2, 0.6)), spacing: 8, align: 'center' });
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    if (this.big && t > this.bigT) {
      const age = t - this.bigT, sc = 1 + 0.3 * (1 - ease.outExpo(clamp(age / 0.16)));
      const fam = ARCH(125, 900), txt = counting(this.big, age / 0.9);
      const s = fitSize(this.big, fam, 820, 300) * sc;
      setWorld(ctx, c, 0, this.motifY + s * 0.3);
      ctx.font = font(fam, s);
      ctx.fillStyle = mixColor('signal', 'bone', prog(t, this.bigT + 0.9, this.bigT + 1.5));
      ctx.fillText(txt, -measure(txt, fam, s) / 2, 0);
      ctx.setTransform(1, 0, 0, 1, 0, 0);
    }
  }
  override draw3D(P: Pen3, t: number) {
    const st = this.style;
    pedestal(P, [0, 0, 0], 0.8, t, prog(t, this.holoT - 0.5, this.holoT), st.tint);
    drawObj(P, this.holoKind, [0, 0, 0], 0.85, t * 0.6 * st.spin, clamp((t - this.holoT + 0.3) / 0.9), t, st.reveal, st.tint, 3, pulse(t, this.holoT + 0.6, 0.3));
  }
  override postFX(t: number) { return { fade: 1 - prog(t, 0, 0.35), frame: ease.outCubic(prog(t, 0.1, 0.9)) * (1 - prog(t, this.t1 - 0.4, this.t1)) }; }
}

// ===================================================================== TITLE
interface Box { x: number; y: number; w: number; h: number; word: Word; label: string; sub: string }
export class Title extends GenPlate {
  boxes: Box[] = [];
  build() {
    const d = this.data, P = this.plot;
    const fonts: StrokeFontName[] = ['osmotron', 'tech', 'sans', 'readable'];
    const fn = fonts[seedOf(String(this.sc.meta?.topic ?? '')) % fonts.length]!;
    const term = String(d.term ?? this.sc.title ?? '').toUpperCase().slice(0, 16) || 'IDEA';
    const st100 = strokeText(term, fn, 100, 0.04);
    const size = Math.min(230, (940 * 100) / Math.max(1, st100.width));
    const st = strokeText(term, fn, size, 0.04);
    const w0 = this.cue(d.termCue ?? term.split(' ')[0], 0, 4);
    const i0 = Math.max(0, this.ws.indexOf(w0));
    const toks = term.split(' ').filter(Boolean);
    const words = toks.map((_, k) => this.ws[Math.min(this.ws.length - 1, i0 + k)]!);
    const yT = -470;
    P.writeWords(term, words, fn, size, -st.width / 2, yT, 'title', { width: 4.4, minDur: 0.55 });
    const tu = Math.max(...words.map((x) => x.end)) + 0.3;
    P.add([pt(-st.width / 2, yT + 40), pt(st.width / 2, yT + 40)], tu, tu + 0.25, 'signal', { pen: true, width: 3.2 });
    if (d.note) P.note(String(d.note).slice(0, 48), 0, yT + 90, tu + 0.15, { size: 22, col: 'ash', align: 'center' });
    const its = items(d, 3);
    const bw = 880, bh = 160, gap = 66, y0 = -300;
    its.forEach((it: any, k: number) => {
      const wd = this.cue(it.cue ?? it.label, k + 1, its.length + 1);
      const b: Box = { x: -bw / 2, y: y0 + k * (bh + gap), w: bw, h: bh, word: wd, label: String(it.label ?? '').slice(0, 26), sub: String(it.sub ?? '').slice(0, 60) };
      this.boxes.push(b);
      P.add(rectPts(b.x, b.y, b.w, b.h), wd.start - 0.08, wd.start + 0.32, 'plot', { pen: true, ez: ease.inOutQuad, width: 2 });
      if (k > 0) {
        const ya = b.y - gap + 10, yb = b.y - 10;
        P.add([pt(0, ya), pt(0, yb)], wd.start - 0.26, wd.start - 0.12, 'plot', { pen: true, width: 2 });
        P.add([pt(-10, yb - 15), pt(0, yb), pt(10, yb - 15)], wd.start - 0.12, wd.start - 0.08, 'plot', { pen: true, width: 2 });
      }
      this.hits.push(wd.start);
    });
    const last = this.boxes[this.boxes.length - 1];
    if (last) {
      const tc = last.word.end + 0.45, cx = last.x + last.w - 70, cy = last.y + 50;
      P.add([pt(cx - 30, cy), pt(cx - 8, cy + 24), pt(cx + 36, cy - 28)], tc, tc + 0.2, 'signal', { pen: true, width: 7 });
    }
    const K = this.cam;
    K.key(this.t0, 0, yT + 40, 1.14, -0.008);
    K.key(tu + 0.2, 0, yT + 120, 1.06, -0.003, ease.inOutCubic);
    if (this.boxes[0]) K.key(this.boxes[0].word.start, 0, -60, 0.98, 0.003, ease.inOutCubic);
    K.key(this.t1, 0, -20, 0.97, 0.005, ease.linear);
  }
  override drawUI(ctx: CanvasRenderingContext2D, t: number, c: Cam) {
    this.boxes.forEach((b, i) => {
      if (t < b.word.start) return;
      setWorld(ctx, c, b.x, b.y);
      ctx.fillStyle = rgba('ink2', 0.85 * prog(t, b.word.start, b.word.start + 0.3));
      ctx.fillRect(1, 1, b.w - 2, b.h - 2);
      label(ctx, `0${i + 1}`, 24, 34, { size: 15, col: rgba('signal', 0.95), spacing: 3 });
      const fam = ARCH(112.5, 900);
      typeText(ctx, b.label, 24, 96, t, b.word.start, Math.max(b.word.end, b.word.start + 0.35), fam, Math.min(56, fitSize(b.label, fam, b.w - 60, 56)), 'bone', false);
      if (t > b.word.end) {
        ctx.font = font(F.mono(400), 22);
        ctx.fillStyle = rgba('ash', 0.92 * prog(t, b.word.end, b.word.end + 0.3));
        wrapText(b.sub, F.mono(400), 22, b.w - 60, 1).forEach((ln, j) => ctx.fillText(ln, 24, 136 + j * 26));
      }
      ctx.setTransform(1, 0, 0, 1, 0, 0);
    });
  }
}

// ===================================================================== SPECIMEN (paper)
interface Gene { x: number; y: number; cx: number; cy: number; w: number; h: number; word: Word; label: string; sub: string; glyph: number }
export class Specimen extends GenPlate {
  override paperMode = true;
  override header = false;
  genes: Gene[] = [];
  stamp: HTMLCanvasElement | null = null;
  tStamp = 1e9;
  build() {
    const d = this.data, P = this.plot;
    const HY = -440, AMP = 62, FR = 1 / 88, X0 = -470, X1 = 470;
    const sy = (x: number, ph: number) => HY + AMP * Math.sin(x * FR + ph);
    const strand = (ph: number) => { const ps: P[] = []; for (let x = X0; x <= X1; x += 8) ps.push(pt(x, sy(x, ph))); return ps; };
    const t0 = this.t0;
    P.add(strand(0), t0 + 0.2, t0 + 0.9, 'ink', { pen: true, ez: ease.inOutQuad, width: 2.4 });
    P.add(strand(Math.PI), t0 + 0.9, t0 + 1.5, 'ink', { pen: true, ez: ease.inOutQuad, width: 2.4 });
    for (let x = X0 + 16, i = 0; x < X1; x += 30, i++) P.add([pt(x, sy(x, 0)), pt(x, sy(x, Math.PI))], t0 + 1.0 + i * 0.012, t0 + 1.05 + i * 0.012, 'hatch', { width: 1.1, alpha: 0.7 });
    const its = items(d, 4), n = its.length || 1;
    const seed = seedOf(String(this.sc.meta?.topic ?? ''));
    its.forEach((it: any, k: number) => {
      const wd = this.cue(it.cue ?? it.label, k, n);
      const x = n === 1 ? 0 : X0 + 70 + (k * (X1 - X0 - 140)) / (n - 1);
      const col = k % 2, row = Math.floor(k / 2);
      const cw = n === 1 ? 900 : 440, ch = 330;
      const cx = n === 1 ? -450 : (col ? 20 : -460), cy = -250 + row * 390;
      const g: Gene = { x, y: sy(x, 0), cx, cy, w: cw, h: ch, word: wd, label: String(it.label ?? '').slice(0, 22).toUpperCase(), sub: String(it.sub ?? ''), glyph: (k + seed) % 5 };
      this.genes.push(g);
      P.add(arc(x, g.y, 20, 0, TAU, 40), wd.start, wd.start + 0.16, 'signal', { pen: true, width: 3 });
      P.add([pt(x, g.y + 22), pt(cx + cw / 2, cy - 14)], wd.start + 0.1, wd.start + 0.24, 'ink', { pen: true, width: 1.5 });
      P.add(rectPts(cx, cy, cw, ch), wd.start + 0.2, wd.start + 0.42, 'ink', { pen: true, ez: ease.inOutQuad, width: 1.8 });
      const t1 = wd.start + 0.42, gx = cx + cw / 2, gy = cy + 150;
      if (g.glyph === 2) {
        P.add(bezier(pt(gx - 140, gy + 60), pt(gx - 70, gy - 70), pt(gx + 50, gy + 90), pt(gx + 140, gy - 40), 40), t1, t1 + 0.4, 'signal', { pen: true, ez: ease.inOutQuad, width: 3 });
      } else if (g.glyph === 3) {
        const s = 52, o = 26, f = [pt(gx - s, gy - s + o), pt(gx + s, gy - s + o), pt(gx + s, gy + s + o), pt(gx - s, gy + s + o), pt(gx - s, gy - s + o)];
        const b = f.map((p) => pt(p.x + o, p.y - o));
        P.add(f, t1, t1 + 0.18, 'ink', { pen: true, width: 2 });
        P.add(b, t1 + 0.18, t1 + 0.34, 'ink', { pen: true, width: 1.4, dash: 9 });
        for (let q = 0; q < 4; q++) P.add([f[q]!, b[q]!], t1 + 0.34 + q * 0.03, t1 + 0.38 + q * 0.03, 'signal', { width: 2 });
      } else if (g.glyph === 4) {
        P.add(arc(gx, gy, 70, -Math.PI / 2, -Math.PI / 2 + TAU * 0.72, 60), t1, t1 + 0.4, 'signal', { pen: true, ez: ease.inOutQuad, width: 7 });
        P.add(arc(gx, gy, 70, 0, TAU, 60), t1, t1 + 0.2, 'cons', { width: 1.2, alpha: 0.5 });
      }
      this.hits.push(wd.start);
    });
    if (d.stamp) {
      this.stamp = makeStamp(String(d.stamp).toUpperCase().slice(0, 22), String(this.sc.meta?.topic ?? '').toUpperCase().slice(0, 38), seed % 97);
      const ws = this.cue(d.stampCue, 3, 4);
      this.tStamp = Math.max(ws.start + 0.05, (this.genes[this.genes.length - 1]?.word.start ?? 0) + 0.6);
      this.hits.push(this.tStamp);
    }
    const K = this.cam;
    K.key(this.t0, 0, -420, 1.12, -0.01);
    K.key(this.t0 + 1.5, 0, -300, 1.02, -0.004, ease.inOutCubic);
    this.genes.forEach((g) => K.key(g.word.start + 0.3, g.cx + g.w / 2 > 0 ? 60 : -60, g.cy + 80, 1.05, 0.003, ease.inOutCubic));
    K.key(this.t1, 0, -40, 0.95, -0.004, ease.inOutCubic);
  }
  override drawUI(ctx: CanvasRenderingContext2D, t: number, c: Cam) {
    const meta = this.sc.meta ?? {};
    setWorld(ctx, c, -500, -900);
    ctx.fillStyle = rgba('ink', 0.94);
    ctx.fillRect(0, 0, 1000, 150);
    const fam = ARCH(112.5, 900);
    ctx.font = font(fam, 46);
    ctx.fillStyle = rgba('bone', 0.97);
    ctx.fillText(`SPECIMEN ${String((meta.i ?? this.idx) + 1).padStart(2, '0')}`, 28, 60);
    label(ctx, `${String(meta.topic ?? '').toUpperCase().slice(0, 30)}`, 972, 56, { size: 15, col: rgba('signal', 0.95), spacing: 3, align: 'right' });
    const title = String(this.sc.title ?? '');
    ctx.font = font(ARCH(100, 700), fitSize(title, ARCH(100, 700), 940, 46));
    ctx.fillStyle = rgba('bone', 0.92);
    ctx.fillText(title, 28, 126);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    for (const g of this.genes) {
      const t0 = g.word.start + 0.3;
      if (t < t0) continue;
      const a = prog(t, t0, t0 + 0.2);
      setWorld(ctx, c, g.cx, g.cy);
      label(ctx, g.label, 14, -14, { size: 16, col: rgba('ink', 0.9 * a), spacing: 3, weight: 600 });
      const gx = g.w / 2, gy = 150;
      if (g.glyph === 0) {
        ['ink', 'signal', 'ember', 'blood', 'graphite'].forEach((k, i) => {
          const tt = t0 + 0.1 + i * 0.07;
          if (t < tt) return;
          const s = ease.outBack(clamp((t - tt) / 0.18));
          ctx.fillStyle = rgba(k, 0.95);
          ctx.fillRect(gx - 135 + i * 56, gy - 50 + (1 - s) * 20, 46, 100 * s);
        });
      } else if (g.glyph === 1) {
        ctx.font = font(ARCH(125, 900), 110);
        ctx.fillStyle = rgba('ink', 0.95 * prog(t, t0, t0 + 0.2));
        ctx.fillText('Aa', gx - 150, gy + 40);
        ctx.font = font(F.serif(600, true), 120);
        ctx.fillStyle = rgba('blood', 0.95 * prog(t, t0 + 0.15, t0 + 0.35));
        ctx.fillText('Aa', gx + 10, gy + 42);
      }
      ctx.font = font(F.mono(400), 19);
      ctx.fillStyle = rgba('graphite', a);
      wrapText(g.sub, F.mono(400), 19, g.w - 40, 2).forEach((ln, j) => ctx.fillText(ln, 20, g.h - 54 + j * 24));
      ctx.setTransform(1, 0, 0, 1, 0, 0);
    }
  }
  override drawOver(ctx: CanvasRenderingContext2D, t: number, c: Cam) {
    if (this.stamp) drawStamp(ctx, c, this.stamp, t, this.tStamp, 0, 330, 0.6, -0.06);
  }
}

// ===================================================================== FLOWS (hub, packets, live counters)
interface FNode { x: number; y: number; w: number; h: number; name: string; unit: string; rate: number; word: Word }
interface Lane { pts: P[]; L: Float32Array; tot: number; dir: 1 | -1; phase: number }
export class Flows extends GenPlate {
  nodes: FNode[] = [];
  lanes: Lane[] = [];
  tPackets = 0; tCount = 0; tOrbit = 0;
  build() {
    const d = this.data, P = this.plot;
    const hubW = this.cue(d.hub?.cue ?? d.hub?.label, 0, 5);
    const hub: FNode = { x: 0, y: -60, w: 440, h: 170, name: String(d.hub?.label ?? 'SYSTEM').slice(0, 14).toUpperCase(), unit: String(d.hub?.unit ?? 'ops').slice(0, 10), rate: numIn(d.hub?.value) ?? 12, word: hubW };
    const its = items(d, 4);
    const spots = [[-270, -480], [270, -480], [-270, 360], [270, 360]];
    this.nodes = [hub];
    its.forEach((it: any, k: number) => {
      const wd = this.cue(it.cue ?? it.label, k + 1, its.length + 1);
      const [x, y] = spots[k]!;
      this.nodes.push({ x: x!, y: y!, w: 380, h: 150, name: String(it.label ?? '').slice(0, 12).toUpperCase(), unit: String(it.unit ?? 'events').slice(0, 10), rate: numIn(it.value) ?? (k + 1) * 37, word: wd });
    });
    this.nodes.forEach((n, i) => {
      const ta = Math.min(n.word.start, this.t0 + 0.3 + i * 0.1) - 0.1;
      P.add(rectPts(n.x - n.w / 2, n.y - n.h / 2, n.w, n.h), ta, ta + 0.3, 'plot', { pen: i === 0, ez: ease.inOutQuad, width: 1.8 });
    });
    this.nodes.slice(1).forEach((s, i) => {
      const up = s.y < hub.y ? -1 : 1;
      for (const [off, dir] of [[-16, 1], [16, -1]] as const) {
        const a = pt(hub.x + off + Math.sign(s.x) * 60, hub.y + up * hub.h / 2), b = pt(s.x + off, s.y - up * s.h / 2);
        const pts = bezier(a, pt(a.x, a.y + up * 160), pt(b.x, b.y - up * 160), b, 40);
        const L = lengths(pts);
        this.lanes.push({ pts, L, tot: L[L.length - 1]!, dir, phase: i * 0.21 + (dir < 0 ? 0.5 : 0) });
        P.add(pts, s.word.start - 0.1, s.word.start + 0.4, 'cons', { ez: ease.outCubic, alpha: 0.9, dash: 12, width: 1.4 });
      }
      this.hits.push(s.word.start);
    });
    const ws = this.ws;
    this.tPackets = d.packetsCue ? this.cue(d.packetsCue, 1, 3).start : (this.nodes[1]?.word.start ?? this.t0 + 0.6) + 0.4;
    this.tCount = d.countersCue ? this.cue(d.countersCue, 2, 3).start : ws[Math.floor(ws.length * 0.45)]?.start ?? this.t0 + 1;
    this.tOrbit = ws[Math.floor(ws.length * 0.7)]?.start ?? this.t1 - 2;
    this.captionY = 640;
  }
  orbitCam(t: number, c: Cam): Cam {
    const orb = ease.inOutCubic(prog(t, this.tOrbit, this.tOrbit + 0.8)), ph = (t - this.tOrbit) * 1.3;
    return { cx: c.cx + orb * 40 * Math.sin(ph), cy: c.cy + orb * 40 * Math.cos(ph * 0.9), z: c.z * (0.96 + orb * 0.03 * Math.sin(ph * 0.7)), roll: c.roll + orb * 0.025 * Math.sin(ph * 0.8) };
  }
  override init() { super.init(); const base = this.cam.at.bind(this.cam); this.cam.at = (t: number) => this.orbitCam(t, base(t)); }
  override drawFX(X: LineBatch, t: number, c: Cam) {
    if (t < this.tPackets) return;
    const ramp = prog(t, this.tPackets, this.tPackets + 0.3);
    for (const ln of this.lanes) for (let k = 0; k < 2; k++) {
      let u = ((t - this.tPackets) * 0.55 + ln.phase + k * 0.5) % 1;
      if (ln.dir < 0) u = 1 - u;
      for (let j = 0; j < 7; j++) {
        const uu = clamp(u - ln.dir * j * 0.012);
        const q = at(ln.pts, ln.L, uu * ln.tot), q2 = at(ln.pts, ln.L, clamp(uu - ln.dir * 0.012) * ln.tot);
        const [ax, ay] = w2s(c, q.x, q.y), [bx, by] = w2s(c, q2.x, q2.y);
        const fade = 1 - j / 7;
        X.seg2(ax, ay, bx, by, (j === 0 ? 9 : 4) * fade + 1, scl(j === 0 ? LIN.ember : LIN.signal, (j === 0 ? 3 : 1.8) * fade), ramp * fade);
      }
    }
  }
  override drawUI(ctx: CanvasRenderingContext2D, t: number, c: Cam) {
    this.nodes.forEach((n, i) => {
      const ta = Math.min(n.word.start, this.t0 + 0.3 + i * 0.1);
      const a = prog(t, ta, ta + 0.3);
      if (a <= 0) return;
      setWorld(ctx, c, n.x - n.w / 2, n.y - n.h / 2);
      ctx.fillStyle = rgba('ink2', 0.9 * a);
      ctx.fillRect(1, 1, n.w - 2, n.h - 2);
      const big = i === 0, fam = ARCH(112.5, 900);
      ctx.font = font(fam, Math.min(big ? 52 : 40, fitSize(n.name, fam, n.w - 120, big ? 52 : 40)));
      ctx.fillStyle = rgba('bone', 0.96 * a);
      ctx.fillText(n.name, 22, big ? 70 : 60);
      const live = t > this.tCount;
      const v = live ? (t - this.tCount) * n.rate * (1 + 0.1 * noise1(t * 3, i)) : 0;
      const txt = Math.floor(v).toLocaleString('en-US');
      ctx.font = font(F.mono(500), big ? 32 : 28);
      ctx.fillStyle = live ? mixColor('signal', 'bone', 1 - pulse(t, this.tCount, 0.4) - 0.3 * (Math.floor(t * 12) % 2)) : rgba('graphite', a);
      ctx.fillText(txt, 22, n.h - 28);
      label(ctx, n.unit.toUpperCase(), 30 + measure(txt, F.mono(500), big ? 32 : 28), n.h - 28, { size: 13, col: rgba('ash', 0.85 * a), spacing: 3 });
      if (live) {
        ctx.fillStyle = rgba('signal', Math.floor(t * 2) % 2 === 0 ? 1 : 0.35);
        ctx.beginPath(); ctx.arc(n.w - 26, 28, 6, 0, 6.3); ctx.fill();
        label(ctx, 'LIVE', n.w - 40, 33, { size: 12, col: rgba('bone', 0.8), spacing: 3, align: 'right' });
      }
      ctx.setTransform(1, 0, 0, 1, 0, 0);
    });
  }
  override postFX() { return { bloom: 0.8, bloomThreshold: 0.82 }; }
}

// ===================================================================== FORM (paper process sheet)
interface Step { x: number; y: number; w: number; h: number; word: Word; label: string; sub: string }
export class Form extends GenPlate {
  override paperMode = true;
  override header = false;
  steps: Step[] = [];
  stamp: HTMLCanvasElement | null = null;
  tStamp = 1e9;
  formNo = '';
  build() {
    const d = this.data, P = this.plot, its = items(d, 5), n = Math.max(1, its.length);
    const seed = seedOf(String(this.sc.meta?.topic ?? ''));
    this.formNo = String(d.form ?? `FORM ${(seed % 9) + 1}-${'ABCDEFGHK'[seed % 9]}`).toUpperCase().slice(0, 12);
    const bh = 118, gap = n > 4 ? 46 : 62, y0 = -560;
    its.forEach((it: any, k: number) => {
      const wd = this.cue(it.cue ?? it.label, k, n);
      const s: Step = { x: -410, y: y0 + k * (bh + gap), w: 820, h: bh, word: wd, label: String(it.label ?? '').slice(0, 28), sub: String(it.sub ?? '').slice(0, 44) };
      this.steps.push(s);
      if (k > 0) {
        const ya = s.y - gap + 8, yb = s.y - 8;
        P.add([pt(0, ya), pt(0, yb)], wd.start - 0.22, wd.start - 0.08, 'ink', { pen: true, ez: ease.inOutQuad, width: 2.2 });
        P.add([pt(-9, yb - 13), pt(0, yb), pt(9, yb - 13)], wd.start - 0.08, wd.start - 0.03, 'ink', { pen: true, width: 2.2 });
      }
      this.hits.push(wd.start);
    });
    if (d.stamp) {
      this.stamp = makeStamp(String(d.stamp).toUpperCase().slice(0, 20), `${this.formNo} · APPROVED`, seed % 89);
      const last = this.steps[this.steps.length - 1];
      this.tStamp = d.stampCue ? Math.max(this.cue(d.stampCue, 4, 5).start, (last?.word.end ?? 0) + 0.3) : (last?.word.end ?? this.t1 - 1) + 0.35;
      this.hits.push(this.tStamp);
    }
    const K = this.cam;
    K.key(this.t0, -120, -620, 1.12, -0.012);
    this.steps.forEach((s, i) => K.key(s.word.start + 0.1, 0, s.y + 40, 1.12, (i % 2 ? 1 : -1) * 0.004, ease.inOutCubic));
    K.key(Math.min(this.t1, this.tStamp + 0.05), 0, -150, 0.94, -0.006, ease.outExpo);
    K.key(this.t1, 0, -140, 0.95, -0.008, ease.linear);
    this.captionY = 640;
  }
  override drawUI(ctx: CanvasRenderingContext2D, t: number, c: Cam) {
    setWorld(ctx, c, -500, -880);
    ctx.fillStyle = rgba('ink', 0.94);
    ctx.fillRect(0, 0, 1000, 120);
    ctx.font = font(ARCH(112.5, 900), 56);
    ctx.fillStyle = rgba('bone', 0.97);
    ctx.fillText(this.formNo, 28, 74);
    const off = 28 + measure(this.formNo, ARCH(112.5, 900), 56) + 30;
    label(ctx, String(this.sc.title ?? '').toUpperCase().slice(0, 34), off, 52, { size: 17, col: rgba('bone', 0.95), spacing: 4 });
    label(ctx, String(this.sc.meta?.topic ?? '').toUpperCase().slice(0, 34), off, 84, { size: 13, col: rgba('bone', 0.7), spacing: 4 });
    ctx.fillStyle = rgba('ink', 0.85);
    ctx.fillRect(0, 160, 1000, 1.6 / c.z);
    label(ctx, 'ISSUED BY  THE BOT', 0, 148, { size: 12, col: rgba('ink', 0.65), spacing: 3 });
    label(ctx, 'NO SIGNATURE REQUIRED', 1000, 148, { size: 12, col: rgba('ink', 0.65), spacing: 3, align: 'right' });
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.steps.forEach((s, i) => {
      if (t < s.word.start - 0.25) return;
      const a = prog(t, s.word.start - 0.25, s.word.start - 0.05);
      setWorld(ctx, c, s.x, s.y);
      ctx.strokeStyle = rgba('ink', 0.85 * a);
      ctx.lineWidth = 2.2 / c.z;
      ctx.strokeRect(0, 0, s.w, s.h);
      label(ctx, `${i + 1}.`, 16, -10, { size: 13, col: rgba('blood', 0.8 * a), spacing: 2 });
      typeText(ctx, s.label, 26, 58, t, s.word.start, Math.max(s.word.end, s.word.start + 0.3), F.mono(500), Math.min(40, fitSize(s.label, F.mono(500), s.w - 50, 40)), 'ink', true);
      if (t > s.word.end) {
        ctx.font = font(F.mono(400), 19);
        ctx.fillStyle = rgba('graphite', 0.95 * prog(t, s.word.end, s.word.end + 0.3));
        ctx.fillText(s.sub, 26, 96);
      }
      ctx.setTransform(1, 0, 0, 1, 0, 0);
    });
  }
  override drawOver(ctx: CanvasRenderingContext2D, t: number, c: Cam) {
    if (this.stamp) drawStamp(ctx, c, this.stamp, t, this.tStamp, 80, 380, 0.56, -0.07);
  }
}

// ===================================================================== STATS (cards that slam + count up)
interface Card { y: number; word: Word; value: string; label: string }
export class Stats extends GenPlate {
  cards: Card[] = [];
  total = ''; tTotal = 1e9;
  build() {
    const d = this.data, P = this.plot, its = items(d, 3), n = Math.max(1, its.length);
    its.forEach((it: any, k: number) => {
      const wd = this.cue(it.cue ?? it.value, k, n);
      const y = -580 + k * 300;
      this.cards.push({ y, word: wd, value: String(it.value ?? '').slice(0, 10), label: String(it.label ?? '').slice(0, 34).toUpperCase() });
      P.add(rectPts(-450, y, 900, 250), wd.start - 0.14, wd.start + 0.16, 'plot', { pen: true, ez: ease.inOutQuad, width: 2 });
      this.hits.push(wd.start);
    });
    if (d.total) {
      this.total = String(d.total).slice(0, 34);
      this.tTotal = Math.max(this.cue(d.totalCue, n, n + 1).start, (this.cards[this.cards.length - 1]?.word.end ?? 0) + 0.3);
    }
    const K = this.cam;
    K.key(this.t0, 0, -460, 1.1, -0.006);
    this.cards.forEach((cd) => K.key(cd.word.start, 0, cd.y + 125, 1.06, 0.004, ease.inOutCubic));
    K.key(this.t1, 0, -160, 0.96, 0, ease.inOutCubic);
    this.captionY = 660;
  }
  override drawUI(ctx: CanvasRenderingContext2D, t: number, c: Cam) {
    for (const cd of this.cards) {
      const t0 = cd.word.start;
      if (t < t0) continue;
      const age = t - t0;
      setWorld(ctx, c, -450, cd.y);
      ctx.fillStyle = rgba('ink2', 0.9 * prog(t, t0, t0 + 0.15));
      ctx.fillRect(1, 1, 898, 248);
      const sc = 1 + 0.32 * (1 - ease.outExpo(clamp(age / 0.16)));
      const fam = ARCH(125, 900);
      const txt = counting(cd.value, age / 0.9);
      const s = fitSize(cd.value, fam, 820, 150) * sc;
      ctx.font = font(fam, s);
      ctx.fillStyle = mixColor('signal', 'bone', prog(t, t0 + 0.9, t0 + 1.5));
      ctx.fillText(txt, 40, 40 + s * 0.78);
      label(ctx, cd.label, 42, 222, { size: 19, col: rgba('ash', 0.92), spacing: 4 });
      ctx.setTransform(1, 0, 0, 1, 0, 0);
    }
    if (this.total && t > this.tTotal) {
      setWorld(ctx, c, 0, -580 + this.cards.length * 300 + 40);
      typeText(ctx, this.total, 0, 0, t, this.tTotal, this.tTotal + 0.6, F.mono(500), Math.min(40, fitSize(this.total, F.mono(500), 940, 40)), 'bone', false, 'center');
      ctx.setTransform(1, 0, 0, 1, 0, 0);
    }
  }
}

// ===================================================================== COMPARE (A vs B)
interface Row { y: number; word: Word; label: string; left: string; right: string }
export class Compare extends GenPlate {
  rows: Row[] = [];
  left = ''; right = '';
  build() {
    const d = this.data, P = this.plot, its = (Array.isArray(d.rows) ? d.rows : items(d, 4)).slice(0, 4), n = Math.max(1, its.length);
    this.left = String(d.left ?? 'A').slice(0, 14).toUpperCase();
    this.right = String(d.right ?? 'B').slice(0, 14).toUpperCase();
    const th = this.t0 + 0.15;
    P.add(rectPts(-480, -660, 430, 130), th, th + 0.3, 'plot', { pen: true, ez: ease.inOutQuad, width: 2.2 });
    P.add(rectPts(50, -660, 430, 130), th + 0.3, th + 0.6, 'plot', { pen: true, ez: ease.inOutQuad, width: 2.2 });
    P.add(arc(0, -595, 46, 0, TAU, 48), th + 0.6, th + 0.8, 'signal', { pen: true, width: 3 });
    its.forEach((it: any, k: number) => {
      const wd = this.cue(it.cue ?? it.label, k, n);
      const y = -440 + k * 250;
      this.rows.push({ y, word: wd, label: String(it.label ?? '').slice(0, 26).toUpperCase(), left: String(it.left ?? '').slice(0, 18), right: String(it.right ?? '').slice(0, 18) });
      P.add([pt(0, y + 30), pt(0, y + 170)], wd.start - 0.1, wd.start + 0.1, 'cons', { width: 1.2, alpha: 0.7 });
      P.add([pt(-470, y + 190), pt(470, y + 190)], wd.start + 0.1, wd.start + 0.4, 'cons', { width: 1, alpha: 0.4, dash: 10 });
      this.hits.push(wd.start);
    });
    const K = this.cam;
    K.key(this.t0, 0, -520, 1.08, -0.006);
    this.rows.forEach((r) => K.key(r.word.start, 0, r.y - 60, 1.03, 0.003, ease.inOutCubic));
    K.key(this.t1, 0, -200, 0.97, 0, ease.inOutCubic);
    this.captionY = 680;
  }
  override drawUI(ctx: CanvasRenderingContext2D, t: number, c: Cam) {
    const th = this.t0 + 0.15, fam = ARCH(112.5, 900);
    for (const [txt, x, tt] of [[this.left, -265, th + 0.2], [this.right, 265, th + 0.5]] as const) {
      if (t < tt) continue;
      setWorld(ctx, c, x, -578);
      const s = Math.min(58, fitSize(txt, fam, 380, 58));
      ctx.font = font(fam, s);
      ctx.fillStyle = mixColor('signal', 'bone', prog(t, tt + 0.2, tt + 0.6));
      ctx.fillText(txt, -measure(txt, fam, s) / 2, s * 0.35);
      ctx.setTransform(1, 0, 0, 1, 0, 0);
    }
    if (t > th + 0.7) {
      setWorld(ctx, c, 0, -583);
      label(ctx, 'VS', 0, 0, { size: 24, col: rgba('bone', 0.95), spacing: 2, weight: 600, align: 'center' });
      ctx.setTransform(1, 0, 0, 1, 0, 0);
    }
    for (const r of this.rows) {
      if (t < r.word.start - 0.2) continue;
      setWorld(ctx, c, 0, r.y);
      label(ctx, r.label, 0, 0, { size: 17, col: rgba('ash', 0.9 * prog(t, r.word.start - 0.2, r.word.start)), spacing: 4, align: 'center' });
      const f2 = ARCH(100, 700);
      typeText(ctx, r.left, -250, 120, t, r.word.start, r.word.start + 0.4, f2, Math.min(52, fitSize(r.left, f2, 420, 52)), 'bone', false, 'center');
      typeText(ctx, r.right, 250, 120, t, r.word.start + 0.25, r.word.start + 0.65, f2, Math.min(52, fitSize(r.right, f2, 420, 52)), 'bone', false, 'center');
      ctx.setTransform(1, 0, 0, 1, 0, 0);
    }
  }
}

// ===================================================================== OUTRO
export class Outro extends GenPlate {
  override header = false;
  override captionY: 'none' = 'none';
  tEnd = 0;
  build() {
    const r = wrapKaraoke(this.ws, 0, -420, 960, 120, ARCH(125, 900), 'end', { maxRows: 5, minSize: 60, lh: 1.08 });
    this.kw.push(...r.kws);
    const last = this.ws[this.ws.length - 1];
    this.tEnd = last ? last.end : this.t1 - 1;
    const uy = -420 + r.height - r.size * 0.75;
    const uw = 380;
    this.plot.add(bezier(pt(-uw, uy), pt(-uw * 0.3, uy + 30), pt(uw * 0.4, uy - 22), pt(uw, uy + 2), 48), this.tEnd - 0.3, this.tEnd + 0.1, 'signal', { pen: true, ez: ease.inOutQuad, width: 6 });
    this.plot.wp(pt(uw + 40, uy), this.tEnd + 0.4, 3);
    this.plot.note('FOLLOW  @DATAVELVET', 0, uy + 220, this.tEnd + 0.1, { size: 46, col: 'bone', align: 'center', fam: 'archivo', weight: 900, spacing: 0.04 });
    this.plot.note('SAVE THIS FOR LATER', 0, uy + 280, this.tEnd + 0.4, { size: 20, col: 'ash', align: 'center', spacing: 0.3 });
    this.hits.push(this.tEnd);
    this.cam.key(this.t0, 0, -280, 1.06, -0.006);
    this.cam.key(this.t1, 0, -200, 1.0, 0.004, ease.linear);
  }
  override postFX(t: number) {
    return { fade: prog(t, this.t1 - 0.9, this.t1 - 0.05, ease.inCubic), frame: ease.outCubic(prog(t, this.tEnd, this.tEnd + 0.6)) };
  }
}

export * from './_plates3d';
export * from './_edit';
export * from './_compose';
