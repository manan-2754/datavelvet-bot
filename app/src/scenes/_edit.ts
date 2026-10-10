// EDIT plate: live photo-editing tutorials (the screen-demo bot's video type) in the kit's hand-plotted style.
// A real photo is edited on screen with real pixel processing (Canvas2D filters + painted, feathered masks):
// adjustment sliders, Ctrl+I mask inversion, a soft brush painting a region back in, a mask preview and a
// before/after wipe. Each scene carries the layer stack at its start (data.edits) and the actions it performs
// (data.acts), each cued to a spoken word.
import { rgba } from '../engine/palette';
import { F, font, measure } from '../engine/type';
import { type Word } from '../engine/lyrics';
import { clamp, ease, prog, TAU } from '../engine/util';
import { pt, rectPts, setWorld, label, type Cam } from './_vo';
import { GenPlate, ARCH, wrapKaraoke, mixColor } from './_gen';

const IMG: Record<string, Promise<HTMLImageElement>> = {};
function loadImg(src: string) {
  return (IMG[src] ??= new Promise((res) => { const im = new Image(); im.onload = () => res(im); im.onerror = () => res(im); im.src = src; }));
}
interface Lyr { kind: string; value: number; region: string; mask: 'full' | 'none' | 'region'; paint: number }
interface Act { do: string; w: Word; t: number; dur: number; [k: string]: any }
const RANGE: Record<string, [number, number]> = { exposure: [-2, 2], contrast: [-1, 1], saturation: [-1, 1], warmth: [-1, 1], bw: [0, 1], highlights: [-1, 1], shadows: [-1, 1] };
function filterOf(k: string, v: number) {
  switch (k) {
    case 'exposure': return `brightness(${Math.pow(2, v).toFixed(3)})`;
    case 'contrast': return `contrast(${(1 + v).toFixed(3)})`;
    case 'saturation': return `saturate(${Math.max(0, 1 + v).toFixed(3)})`;
    case 'warmth': return v >= 0 ? `sepia(${(v * 0.45).toFixed(3)}) saturate(${(1 + v * 0.35).toFixed(3)})` : `hue-rotate(${(v * 14).toFixed(1)}deg) saturate(${(1 + v * 0.2).toFixed(3)})`;
    case 'bw': return `grayscale(${clamp(v).toFixed(3)})`;
    case 'highlights': return `brightness(${(1 + v * 0.28).toFixed(3)}) contrast(${(1 - v * 0.12).toFixed(3)})`;
    case 'shadows': return `brightness(${(1 + v * 0.35).toFixed(3)}) contrast(${(1 - v * 0.25).toFixed(3)})`;
  }
  return 'none';
}
const fmt = (k: string, v: number) => k === 'bw' ? `${Math.round(v * 100)}%` : `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
const canvas = (w: number, h: number) => { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; };

export class Edit extends GenPlate {
  img: HTMLImageElement | null = null;
  CW = 960; CH = 640; cy = -190;
  hookMode = false;
  acts: Act[] = [];
  start: Lyr[] = [];
  sky = 0.3; subj: [number, number, number, number] = [0.5, 0.55, 0.2, 0.25];
  A!: HTMLCanvasElement; B!: HTMLCanvasElement; M!: HTMLCanvasElement; Fm!: HTMLCanvasElement; O!: HTMLCanvasElement;
  maskShown: HTMLCanvasElement | null = null;
  override async init() {
    const sc = this.ctx.lyrics.scenes[this.ctx.params.scene ?? 0] ?? {};
    const base = (import.meta as any).env?.BASE_URL ?? '/';
    if (sc.data?.photo) this.img = await loadImg(`${base}photos/${sc.data.photo}`);
    super.init();
  }
  build() {
    const d = this.data, P = this.plot;
    this.sky = Math.max(0.12, Number(d.sky) || 0.3);
    if (Array.isArray(d.subject) && d.subject.length === 4) this.subj = d.subject.map(Number) as any;
    this.hookMode = !!d.hook;
    if (this.hookMode) {
      this.header = false; this.captionY = 'none';
      const r = wrapKaraoke(this.ws, 0, -650, 960, 100, ARCH(100, 800), 'q', { maxRows: 4, minSize: 56, lh: 1.08 });
      this.kw.push(...r.kws);
      this.cy = Math.max(-650 + r.height + 380, 40);
    } else this.captionY = 660;
    this.start = (Array.isArray(d.edits) ? d.edits : []).map((e: any) => ({ kind: String(e.kind), value: Number(e.value) || 0, region: String(e.region ?? 'all'), mask: e.mask ?? 'full', paint: Number(e.paint ?? 1) }));
    const acts = Array.isArray(d.acts) ? d.acts : [], n = Math.max(1, acts.length);
    acts.forEach((a: any, k: number) => {
      const w = this.cue(a.cue, k, n);
      const dur = Number(a.dur) || ({ slider: 1.4, paint: 2.8, compare: 1.0, circle: 0.6 } as Record<string, number>)[a.do] || 0.3;
      this.acts.push({ ...a, w, t: w.start, dur });
      this.hits.push(w.start);
    });
    const { CW, CH, cy } = this;
    P.add(rectPts(-CW / 2 - 16, cy - CH / 2 - 16, CW + 32, CH + 32), this.t0 + 0.05, this.t0 + 0.5, 'plot', { pen: true, ez: ease.inOutQuad, width: 2 });
    for (const [x, y] of [[-1, -1], [1, -1], [1, 1], [-1, 1]] as const) {
      const X = x * (CW / 2 + 34), Y = cy + y * (CH / 2 + 34);
      P.add([pt(X, Y - y * 30), pt(X, Y), pt(X - x * 30, Y)], this.t0 + 0.4, this.t0 + 0.55, 'signal', { width: 2.4 });
    }
    for (const a of this.acts) {
      if (a.do === 'note') {
        P.note(String(a.text ?? '').slice(0, 40).toUpperCase(), 0, cy + CH / 2 + 110, a.t, { size: 30, col: 'signal', align: 'center', hot: 0.3, spacing: 0.06 });
      }
    }
    const K = this.cam;
    K.key(this.t0, 0, cy + 40, this.hookMode ? 0.96 : 1.0, -0.004);
    for (const a of this.acts) {
      if (a.do === 'paint' || a.do === 'circle') {
        const [rx, ry] = this.regionCentre(a.region ?? (a.do === 'circle' ? 'subject' : 'sky'));
        K.key(a.t + 0.1, rx * 0.35, ry * 0.6 + cy * 0.4, 1.16, 0.004, ease.inOutCubic);
        K.key(a.t + a.dur + 0.2, rx * 0.25, ry * 0.5 + cy * 0.5, 1.12, 0.002, ease.inOutCubic);
      } else if (a.do === 'slider') K.key(a.t + 0.1, 0, cy + 160, 1.06, -0.002, ease.inOutCubic);
      else if (a.do === 'key' || a.do === 'invert') K.key(a.t + 0.05, 0, cy + 20, 1.03, 0.003, ease.outExpo);
      else if (a.do === 'compare') K.key(a.t + 0.1, 0, cy, 1.04, 0, ease.inOutCubic);
    }
    K.key(this.t1, 0, cy + 30, 1.0, 0.004, ease.linear);
    this.A = canvas(CW, CH); this.B = canvas(CW, CH); this.M = canvas(CW, CH); this.Fm = canvas(CW, CH); this.O = canvas(CW, CH);
  }
  regionCentre(region: string): [number, number] {
    const { CW, CH, cy } = this, x0 = -CW / 2, y0 = cy - CH / 2;
    if (region === 'sky') return [0, y0 + this.sky * CH * 0.5];
    if (region === 'foreground') return [0, y0 + CH * (this.sky + 1) / 2];
    if (region === 'subject') return [x0 + this.subj[0] * CW, y0 + this.subj[1] * CH];
    return [0, cy];
  }
  /** Region shape in card pixels. */
  regionPath(c: CanvasRenderingContext2D, region: string) {
    const { CW, CH } = this, s = this.sky * CH, [cx, cy, rx, ry] = this.subj;
    c.beginPath();
    const horizon = () => { for (let i = 24; i >= 0; i--) c.lineTo((i / 24) * CW, s + 10 * Math.sin(i * 1.3) + 6 * Math.sin(i * 0.4)); };
    if (region === 'sky') { c.moveTo(0, 0); c.lineTo(CW, 0); horizon(); c.closePath(); }
    else if (region === 'foreground') { c.moveTo(0, CH); c.lineTo(CW, CH); horizon(); c.closePath(); }
    else if (region === 'subject') c.ellipse(cx * CW, cy * CH, rx * CW, ry * CH, 0, 0, TAU);
    else if (region === 'background') { c.rect(0, 0, CW, CH); c.ellipse(cx * CW, cy * CH, rx * CW, ry * CH, 0, 0, TAU, true); }
    else c.rect(0, 0, CW, CH);
  }
  /** Brush path that covers a region (zig-zag rows / spiral), in card pixels. */
  brushPath(region: string): { pts: [number, number][]; r: number } {
    const { CW, CH } = this, [cx, cy, rx, ry] = this.subj, out: [number, number][] = [];
    if (region === 'subject') {
      [0.85, 0.55, 0.25].forEach((f, k) => { for (let i = 0; i <= 22; i++) { const a = (i / 22) * TAU + k; out.push([CW * (cx + rx * f * Math.cos(a)), CH * (cy + ry * f * Math.sin(a))]); } });
      return { pts: out, r: Math.max(40, Math.min(rx * CW, ry * CH) * 0.55) };
    }
    const [y0, y1] = region === 'sky' ? [0.02, this.sky] : region === 'foreground' ? [this.sky + 0.05, 0.97] : [0.03, 0.97];
    const rows = Math.max(2, Math.round((y1 - y0) * 9));
    for (let k = 0; k < rows; k++) {
      const y = (y0 + ((y1 - y0) * (k + 0.5)) / rows) * CH;
      for (let j = 0; j <= 10; j++) { const u = j / 10, x = (k % 2 ? 1 - u : u) * CW * 0.94 + CW * 0.03; out.push([x, y + 8 * Math.sin(u * 9 + k)]); }
    }
    return { pts: out, r: ((y1 - y0) * CH) / rows * 0.95 + 18 };
  }
  stateAt(t: number): Lyr[] {
    const L = this.start.map((l) => ({ ...l }));
    for (const a of this.acts) {
      if (t < a.t) break;
      const p = ease.inOutCubic(clamp((t - a.t) / a.dur));
      const pick = () => L[Math.min(Math.max(0, a.layer ?? L.length - 1), L.length - 1)]!;
      if (a.do === 'slider') {
        if (a.layer == null ? !L.length : a.layer >= L.length) L.push({ kind: a.kind ?? 'exposure', value: Number(a.from ?? 0), region: a.region ?? 'all', mask: 'full', paint: 1 });
        pick().value = Number(a.from ?? 0) + (Number(a.to ?? 0) - Number(a.from ?? 0)) * p;
      } else if (a.do === 'invert' && L.length) {
        const l = pick();
        if (t > a.t + 0.12) l.mask = l.mask === 'none' ? 'full' : 'none';
      } else if (a.do === 'paint' && L.length) {
        const l = pick();
        l.mask = 'region'; l.region = a.region ?? 'sky'; l.paint = clamp((t - a.t) / a.dur);
      }
    }
    return L;
  }
  /** Real pixel processing: each adjustment layer = filtered copy of what is below, through its feathered mask. */
  composite(L: Lyr[]): HTMLCanvasElement {
    const { CW, CH } = this, a = this.A.getContext('2d')!, b = this.B.getContext('2d')!;
    a.globalCompositeOperation = 'source-over'; a.filter = 'none';
    a.clearRect(0, 0, CW, CH);
    if (this.img && this.img.naturalWidth) {
      const ir = this.img.naturalWidth / this.img.naturalHeight, cr = CW / CH;
      const sw = ir > cr ? this.img.naturalHeight * cr : this.img.naturalWidth, sh = ir > cr ? this.img.naturalHeight : this.img.naturalWidth / cr;
      a.drawImage(this.img, (this.img.naturalWidth - sw) / 2, (this.img.naturalHeight - sh) / 2, sw, sh, 0, 0, CW, CH);
    } else { a.fillStyle = '#333'; a.fillRect(0, 0, CW, CH); }
    this.maskShown = null;
    for (const l of L) {
      if (l.mask === 'none') continue;
      b.globalCompositeOperation = 'source-over'; b.clearRect(0, 0, CW, CH);
      b.filter = filterOf(l.kind, l.value); b.drawImage(this.A, 0, 0); b.filter = 'none';
      if (!(l.mask === 'full' && l.region === 'all')) {
        const m = this.maskOf(l);
        b.globalCompositeOperation = 'destination-in'; b.drawImage(m, 0, 0); b.globalCompositeOperation = 'source-over';
        if (l.mask === 'region') this.maskShown = m;
      }
      a.drawImage(this.B, 0, 0);
    }
    return this.A;
  }
  maskOf(l: Lyr): HTMLCanvasElement {
    const { CW, CH } = this, m = this.M.getContext('2d')!, f = this.Fm.getContext('2d')!;
    m.globalCompositeOperation = 'source-over'; m.clearRect(0, 0, CW, CH);
    m.fillStyle = '#fff'; m.strokeStyle = '#fff';
    if (l.mask === 'full') { this.regionPath(m, l.region); m.fill('evenodd'); }
    else {
      const { pts, r } = this.brushPath(l.region), n = pts.length - 1, upto = l.paint * n;
      m.save(); this.regionPath(m, l.region); m.clip('evenodd');
      m.lineWidth = r * 2; m.lineCap = 'round'; m.lineJoin = 'round';
      m.beginPath(); m.moveTo(pts[0]![0], pts[0]![1]);
      const fi = Math.floor(upto), fr = upto - fi;
      for (let i = 1; i <= fi; i++) m.lineTo(pts[i]![0], pts[i]![1]);
      if (fi < n) m.lineTo(pts[fi]![0] + (pts[fi + 1]![0] - pts[fi]![0]) * fr, pts[fi]![1] + (pts[fi + 1]![1] - pts[fi]![1]) * fr);
      if (l.paint > 0) m.stroke();
      if (l.paint >= 1) { this.regionPath(m, l.region); m.fill('evenodd'); }
      m.restore();
    }
    f.clearRect(0, 0, CW, CH);
    f.filter = 'blur(12px)'; f.drawImage(this.M, 0, 0); f.filter = 'none';
    return this.Fm;
  }
  brushHead(t: number): [number, number, number] | null {
    for (const a of this.acts) {
      if (a.do !== 'paint' || t < a.t || t > a.t + a.dur) continue;
      const { pts, r } = this.brushPath(a.region ?? 'sky'), n = pts.length - 1, u = clamp((t - a.t) / a.dur) * n, i = Math.min(n - 1, Math.floor(u)), fr = u - i;
      return [pts[i]![0] + (pts[i + 1]![0] - pts[i]![0]) * fr, pts[i]![1] + (pts[i + 1]![1] - pts[i]![1]) * fr, r];
    }
    return null;
  }
  override drawUI(ctx: CanvasRenderingContext2D, t: number, c: Cam) {
    const { CW, CH, cy } = this, x0 = -CW / 2, y0 = cy - CH / 2;
    const a = prog(t, this.t0 + 0.1, this.t0 + 0.45);
    const cmp = this.acts.find((q) => q.do === 'compare' && t >= q.t);
    if (cmp) { const o = this.O.getContext('2d')!; o.clearRect(0, 0, CW, CH); o.drawImage(this.composite([]), 0, 0); }
    const L = this.stateAt(t), img = this.composite(L);
    setWorld(ctx, c, x0, y0);
    ctx.globalAlpha = a;
    if (cmp) {
      const k = ease.outCubic(clamp((t - cmp.t) / cmp.dur));
      const wx = CW * (1 - 0.5 * k + 0.08 * Math.sin((t - cmp.t) * 1.4) * k);
      ctx.drawImage(this.O, 0, 0);
      ctx.save(); ctx.beginPath(); ctx.rect(wx, 0, CW - wx, CH); ctx.clip(); ctx.drawImage(img, 0, 0); ctx.restore();
      ctx.fillStyle = rgba('bone', 0.95); ctx.fillRect(wx - 2, 0, 4, CH);
      ctx.fillStyle = rgba('signal', 1); ctx.beginPath(); ctx.arc(wx, CH / 2, 16, 0, TAU); ctx.fill();
      label(ctx, 'BEFORE', 20, 40, { size: 22, col: rgba('bone', 0.95 * k), spacing: 4, weight: 600 });
      label(ctx, 'AFTER', CW - 20, 40, { size: 22, col: rgba('bone', 0.95 * k), spacing: 4, weight: 600, align: 'right' });
    } else ctx.drawImage(img, 0, 0);
    ctx.globalAlpha = 1;
    // hand-drawn circle around the subject (over the photo)
    for (const q of this.acts) {
      if (q.do !== 'circle' || t < q.t) continue;
      const [cx, cyy, rx, ry] = this.subj, k = ease.inOutQuad(clamp((t - q.t) / q.dur));
      ctx.strokeStyle = rgba('signal', 1); ctx.lineWidth = 6; ctx.lineCap = 'round';
      ctx.shadowColor = rgba('signal', 0.8); ctx.shadowBlur = 18;
      ctx.beginPath(); ctx.ellipse(cx * CW, cyy * CH, rx * CW * 1.05, ry * CH * 1.05, -0.08, -Math.PI / 2, -Math.PI / 2 + TAU * 1.06 * k); ctx.stroke();
      ctx.shadowBlur = 0;
    }
    // mask preview (black = hidden, white = shows)
    const lastMaskAct = [...this.acts].reverse().find((q) => (q.do === 'invert' || q.do === 'paint') && t >= q.t);
    if (lastMaskAct && !cmp) {
      const mk = prog(t, lastMaskAct.t + 0.1, lastMaskAct.t + 0.35), tw = 220, th = (tw * CH) / CW, tx = CW - tw - 18, ty = CH - th - 18;
      ctx.fillStyle = rgba('ink', 0.95 * mk); ctx.fillRect(tx - 4, ty - 30, tw + 8, th + 34);
      ctx.fillStyle = '#000'; ctx.globalAlpha = mk; ctx.fillRect(tx, ty, tw, th);
      if (this.maskShown) ctx.drawImage(this.maskShown, tx, ty, tw, th);
      ctx.globalAlpha = 1;
      label(ctx, 'LAYER MASK', tx, ty - 9, { size: 13, col: rgba('signal', mk), spacing: 3, weight: 600 });
    }
    // brush cursor
    const bh = this.brushHead(t);
    if (bh) {
      ctx.strokeStyle = rgba('bone', 0.95); ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(bh[0], bh[1], bh[2], 0, TAU); ctx.stroke();
      ctx.strokeStyle = rgba('ink', 0.6); ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(bh[0], bh[1], bh[2] + 2.5, 0, TAU); ctx.stroke();
      ctx.fillStyle = rgba('signal', 1); ctx.fillRect(bh[0] - 9, bh[1] - 1.5, 18, 3); ctx.fillRect(bh[0] - 1.5, bh[1] - 9, 3, 18);
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    // layer chips under the card
    if (!this.hookMode && L.length) {
      setWorld(ctx, c, x0, y0 + CH + 40);
      let xx = 0;
      L.forEach((l, i) => {
        const txt = `${l.kind.toUpperCase()} ${i + 1}`, w = measure(txt, F.mono(500), 16, 3) + 70;
        ctx.strokeStyle = rgba('ash', 0.6); ctx.lineWidth = 1.5; ctx.strokeRect(xx, 0, w, 36);
        ctx.fillStyle = l.mask === 'none' ? '#000' : l.mask === 'region' ? rgba('bone', 0.5) : '#fff'; ctx.fillRect(xx + 8, 8, 28, 20);
        ctx.strokeStyle = rgba('ash', 0.8); ctx.strokeRect(xx + 8, 8, 28, 20);
        label(ctx, txt, xx + 46, 24, { size: 16, col: rgba('bone', 0.9), spacing: 3 });
        xx += w + 14;
      });
      ctx.setTransform(1, 0, 0, 1, 0, 0);
    }
    // sliders
    for (const s of this.acts.filter((q) => q.do === 'slider')) {
      const nxt = this.acts.find((q) => q.t > s.t && q.do === 'slider');
      const vis = prog(t, s.t - 0.25, s.t) * (1 - prog(t, (nxt?.t ?? 1e9) - 0.3, nxt?.t ?? 1e9));
      if (vis <= 0) continue;
      const kind = s.kind ?? 'exposure', [lo, hi] = RANGE[kind] ?? [-1, 1];
      const p = ease.inOutCubic(clamp((t - s.t) / s.dur)), v = Number(s.from ?? 0) + (Number(s.to ?? 0) - Number(s.from ?? 0)) * p;
      const X0 = -380, X1 = 380, kx = X0 + ((v - lo) / (hi - lo)) * (X1 - X0);
      setWorld(ctx, c, 0, y0 + CH + 150);
      ctx.globalAlpha = vis;
      label(ctx, String(s.label ?? kind).toUpperCase(), X0, -26, { size: 18, col: rgba('ash', 0.95), spacing: 4 });
      const moving = t > s.t && t < s.t + s.dur;
      ctx.font = font(F.mono(500), 30); ctx.textAlign = 'right';
      ctx.fillStyle = moving ? rgba('signal', 1) : rgba('bone', 0.95); ctx.fillText(fmt(kind, v), X1, -20); ctx.textAlign = 'left';
      ctx.fillStyle = rgba('graphite', 1); ctx.fillRect(X0, -2, X1 - X0, 4);
      const zx = X0 + ((0 - lo) / (hi - lo)) * (X1 - X0);
      ctx.fillStyle = rgba('signal', 0.9); ctx.fillRect(Math.min(zx, kx), -2, Math.abs(kx - zx), 4);
      for (let i = 0; i <= 8; i++) ctx.fillRect(X0 + (i / 8) * (X1 - X0) - 1, 10, 2, i % 4 === 0 ? 12 : 6);
      ctx.fillStyle = rgba('bone', 1); ctx.beginPath(); ctx.arc(kx, 0, moving ? 17 : 14, 0, TAU); ctx.fill();
      ctx.strokeStyle = rgba('signal', 1); ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(kx, 0, (moving ? 17 : 14) + 5, 0, TAU); ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
    }
    // keycaps
    for (const k of this.acts.filter((q) => q.do === 'key' || q.do === 'invert')) {
      const keys = String(k.keys ?? (k.do === 'invert' ? 'Ctrl + I' : '')).split('+').map((s) => s.trim()).filter(Boolean);
      if (!keys.length || t < k.t || t > k.t + 1.8) continue;
      const age = t - k.t, al = prog(t, k.t, k.t + 0.08) * (1 - prog(t, k.t + 1.4, k.t + 1.8)), sc = 1 + 0.25 * (1 - ease.outExpo(clamp(age / 0.18)));
      const fam = ARCH(112.5, 900), ws = keys.map((s) => Math.max(120, measure(s, fam, 64) + 64)), tot = ws.reduce((s, w) => s + w, 0) + 50 * (keys.length - 1);
      setWorld(ctx, c, 0, y0 + CH / 2, sc);
      ctx.globalAlpha = al;
      let x = -tot / 2;
      keys.forEach((s, i) => {
        const w = ws[i]!;
        ctx.fillStyle = rgba('ink2', 0.95); ctx.fillRect(x, -60, w, 120);
        ctx.strokeStyle = mixColor('signal', 'bone', clamp(age / 0.5)); ctx.lineWidth = 3; ctx.strokeRect(x, -60, w, 120);
        ctx.fillStyle = rgba('bone', 1); ctx.font = font(fam, 64); ctx.textAlign = 'center'; ctx.fillText(s, x + w / 2, 22); ctx.textAlign = 'left';
        x += w;
        if (i < keys.length - 1) { ctx.fillStyle = rgba('ash', 1); ctx.font = font(fam, 40); ctx.textAlign = 'center'; ctx.fillText('+', x + 25, 14); ctx.textAlign = 'left'; x += 50; }
      });
      ctx.globalAlpha = 1;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
    }
    if (this.hookMode) {
      setWorld(ctx, c, 0, -860);
      label(ctx, 'DATAVELVET', 0, 0, { size: 18, col: rgba('signal', 0.9 * prog(t, 0.2, 0.6)), spacing: 8, align: 'center' });
      ctx.setTransform(1, 0, 0, 1, 0, 0);
    }
  }
  override postFX(t: number) {
    const base = { bloom: 0.35, bloomThreshold: 1.1, vignette: 0.35 };
    return this.hookMode ? { ...base, fade: 1 - prog(t, 0, 0.35) } : base;
  }
}
