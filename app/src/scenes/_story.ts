// Story plate (pro-bot): one beat of a running-example explainer, built from what top tech Shorts do.
//   top    - the spoken phrase in 2-4 word chunks, the key word in a Figma-style selection box
//   HUD    - stage stepper (the whole journey, current stage lit), a live counter, corner brackets
//   middle - a realistic UI mockup widget (terminal, code, browser, table, chat, metric, compare, flow, checklist, summary)
//   bottom - a 3D hologram hero object for depth; fast cut on every beat
import { W, H } from '../engine/gl';
import { F, font, measure } from '../engine/type';
import { norm } from '../engine/lyrics';
import { clamp, ease, prog, pulse } from '../engine/util';
import { type Cam } from './_vo';
import { GenPlate, ARCH } from './_gen';
import { asObj, drawObj, type Pen3, type V3 } from './_holo3d';
import { plan } from './_plates3d';

const BLUE = '#3B82F6', GREEN = '#22C55E';
const MONO = () => F.mono(500);


const KW = /^(const|let|var|function|return|await|async|if|else|for|while|import|from|export|new|class|def|print|true|false|null|SELECT|FROM|WHERE|INSERT|INTO|VALUES|UPDATE|SET|CREATE|TABLE|POLICY|USING|AND|OR|ORDER|BY|DESC|ASC|LIMIT|GET|POST|select|from|where|insert|into|values|update|set|create|table|policy|using|and|or|order|by|limit|sudo|curl|git|npm|ssh|ping|dig|cd)$/;
/** Syntax colours (GitHub dark): keywords, strings, numbers, calls, comments; terminal: prompt, ok, errors. */
export function tokens(s: string, term: boolean): [string, string][] {
  if (term) {
    if (s.startsWith('$ ')) return [['$ ', '#3FB950'], [s.slice(2), '#E6EDF3']];
    if (s.startsWith('> ')) return [['> ', '#8B949E'], [s.slice(2), '#C9D1D9']];
    return [[s, /error|denied|fail|refused|timeout/i.test(s) ? '#FF7B72' : /\bok\b|done|ready|200|success|connected|✓/i.test(s) ? '#3FB950' : '#8B949E']];
  }
  const out: [string, string][] = [];
  const re = /("[^"]*"?|'[^']*'?|`[^`]*`?|\/\/.*$|--.*$|#.*$|\b\d+(?:\.\d+)?\b|[A-Za-z_]\w*|\s+|.)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s))) {
    if (!m[0]) { re.lastIndex++; continue; }
    const t = m[0], next = s[re.lastIndex] ?? '';
    const col = /^["'`]/.test(t) ? '#A5D6FF' : /^(\/\/|--|#)/.test(t) ? '#8B949E' : /^\d/.test(t) ? '#79C0FF' : KW.test(t) ? '#FF7B72' : /^[A-Za-z_]/.test(t) && next === '(' ? '#D2A8FF' : '#E6EDF3';
    out.push([t, col]);
  }
  return out;
}
const LIGHT_TOK: Record<string, string> = { '#FF7B72': '#CF222E', '#A5D6FF': '#0A3069', '#79C0FF': '#0550AE', '#D2A8FF': '#8250DF', '#8B949E': '#6E7781', '#E6EDF3': '#1F2328' };
/** GitHub-light syntax colours for code drawn on light cards. */
function onLight(col: string, light: boolean) { return light ? LIGHT_TOK[col] ?? col : col; }
function rgbaHex(hex: string, a: number) {
  const h = hex.replace('#', ''), n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

export class Story extends GenPlate {
  override has3D = true;
  d: any = {};
  light = false;
  chunks: { words: any[]; t0: number; t1: number }[] = [];
  CH = 720;
  noCard = false;            // the World plate puts widgets on 3D panels instead of a flat card
  capInk = '#FFFFFF';
  /** Card height fitted to the widget's content (no empty card space); the 3D hero fills what is left below. */
  fitCH(wd: any) {
    const n = (k: string) => (Array.isArray(wd[k]) ? wd[k].length : 0), L = Math.min(8, n('lines') || n('items'));
    const h: Record<string, number> = {
      terminal: 200 + L * 56, code: 200 + L * 56, browser: 240 + Math.min(4, L) * 92, table: 150 + (wd.query ? 78 : 0) + Math.min(6, n('rows')) * 72,
      chat: 130 + Math.min(6, n('messages')) * 100, metric: 640, compare: 150 + Math.min(5, n('items')) * 112,
      flow: 80 + Math.min(5, n('nodes') || L) * 156, shot: 720, phone: 780, stack: 780, request: 360 + Math.min(5, L) * 46, checklist: 150 + L * 84, summary: 150 + L * 84,
    };
    return clamp(h[wd.kind] ?? 720, 330, 780);
  }
  build() {
    this.d = this.data ?? {};
    this.header = false;
    this.captionY = 'none';
    this.light = !!this.d.light;
    this.CH = this.fitCH(this.d.widget ?? {});
    this.viewCY = Math.min(H * 0.84, (470 + this.CH + H - 60) / 2 + 30);   // 3D hero centred in the space under the card
    this.floorAt = [0, 0, 0];
    this.floorR = 3;
    const ctr: V3 = [0, 0.7, 0];
    plan(this, [{ t: this.t0 + 0.3, p: ctr, d: 4.4 }], { tgt: ctr, dist: 6.2 });
    let cur: any[] = [];                                   // spoken words -> 2-4 word caption chunks
    this.ws.forEach((w, i) => {
      cur.push(w);
      if (/[,.;:!?]$/.test(w.w) || cur.length >= 4 || i === this.ws.length - 1) {
        this.chunks.push({ words: cur, t0: cur[0].start, t1: cur[cur.length - 1].end });
        cur = [];
      }
    });
  }
  override draw3D(P: Pen3, t: number) {
    if (!this.d.object) return;
    drawObj(P, asObj(this.d.object), [0, 0, 0], 1.0, t * 0.35, clamp((t - this.t0) / 0.7), t, 'scan', this.style.tint, 3, pulse(t, this.t0 + 0.4, 0.4));
  }
  card(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, a: number) {
    ctx.globalAlpha = a;
    ctx.fillStyle = this.light ? 'rgba(248,248,250,0.97)' : 'rgba(18,20,26,0.94)';
    ctx.strokeStyle = this.light ? 'rgba(0,0,0,0.10)' : 'rgba(255,255,255,0.10)';
    ctx.lineWidth = 2;
    ctx.beginPath(); (ctx as any).roundRect(x, y, w, h, 22); ctx.fill(); ctx.stroke();
  }
  ink(a = 1) { return this.light ? `rgba(20,22,30,${a})` : `rgba(240,242,248,${a})`; }
  text(ctx: CanvasRenderingContext2D, s: string, x: number, y: number, size: number, col: string, fam = F.archivo(100, 500), max = 0) {
    let sz = size;
    if (max) while (sz > 14 && measure(s, fam, sz) > max) sz -= 2;
    ctx.font = font(fam, sz); ctx.fillStyle = col; ctx.fillText(s, x, y);
    return sz;
  }

  override drawUI(ctx: CanvasRenderingContext2D, t: number, _c: Cam) {
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    const d = this.d, age = t - this.t0, dur = Math.max(0.5, this.t1 - this.t0), sig = this.style.tintHex;
    ctx.strokeStyle = sig; ctx.lineWidth = 5; ctx.globalAlpha = 0.85;                 // HUD corner brackets
    for (const [x, y, sx, sy] of [[40, 40, 1, 1], [W - 40, 40, -1, 1], [40, H - 40, 1, -1], [W - 40, H - 40, -1, -1]] as const) {
      ctx.beginPath(); ctx.moveTo(x + sx * 60, y); ctx.lineTo(x, y); ctx.lineTo(x, y + sy * 60); ctx.stroke();
    }
    const stages: string[] = Array.isArray(d.stages) ? d.stages.slice(0, 7) : [];  // pill stepper with glowing dots
    const lightUI = this.capInk !== '#FFFFFF';
    if (stages.length) {
      const cur = clamp(Number(d.stage) || 0, 0, stages.length - 1), fam = F.mono(700), dot = 12, gap = 10, con = 12;
      const labs = stages.map((s) => String(s).toUpperCase().slice(0, 10));
      const width = (f: number) => labs.reduce((w, l) => w + dot + 8 + measure(l, fam, f), 0) + (labs.length - 1) * (gap * 2 + con) + 56;
      let fs = 30;
      while (fs > 16 && width(fs) > W - 70) fs -= 1;
      const pw = width(fs), px = (W - pw) / 2, py = 70, ph = 70;
      ctx.globalAlpha = 1; ctx.lineWidth = 2;
      ctx.fillStyle = lightUI ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.05)'; ctx.strokeStyle = lightUI ? 'rgba(0,0,0,0.12)' : 'rgba(255,255,255,0.10)';
      ctx.beginPath(); (ctx as any).roundRect(px, py, pw, ph, ph / 2); ctx.fill(); ctx.stroke();
      let x = px + 28;
      labs.forEach((lab, i) => {
        const on = i <= cur, now = i === cur;
        ctx.save();
        if (on) { ctx.shadowColor = sig; ctx.shadowBlur = now ? 16 + 10 * pulse(t, this.t0, 0.6) : 10; }
        ctx.fillStyle = on ? sig : (lightUI ? 'rgba(0,0,0,0.2)' : 'rgba(255,255,255,0.2)');
        ctx.beginPath(); ctx.arc(x + dot / 2, py + ph / 2, now ? dot * 0.8 : dot / 2, 0, 6.3); ctx.fill();
        ctx.restore();
        x += dot + 8;
        ctx.font = font(fam, fs); ctx.fillStyle = on ? (lightUI ? '#0B0D12' : '#FFFFFF') : (lightUI ? 'rgba(0,0,0,0.3)' : 'rgba(255,255,255,0.3)');
        ctx.fillText(lab, x, py + ph / 2 + fs * 0.36); x += measure(lab, fam, fs);
        if (i < labs.length - 1) { ctx.fillStyle = lightUI ? 'rgba(0,0,0,0.12)' : 'rgba(255,255,255,0.12)'; ctx.fillRect(x + gap, py + ph / 2 - 1, con, 2); x += gap * 2 + con; }
      });
    }
    if (d.counter && d.counter.value !== undefined) {                                // HUD metric card (bottom-left glass)
      const from = Number(d.counter.from ?? d.counter.value) || 0, to = Number(d.counter.value) || 0;
      const v = from + (to - from) * ease.outCubic(clamp(age / Math.min(1.2, dur)));
      const num = (Number.isInteger(to) ? Math.round(v).toLocaleString('en-US') : v.toFixed(1)) + (d.counter.unit ? ` ${d.counter.unit}` : '');
      const cw = 420, chh = 170, cx = 64, cy = H - 120 - chh;
      ctx.globalAlpha = 1; ctx.fillStyle = 'rgba(15,23,42,0.86)'; ctx.strokeStyle = 'rgba(255,255,255,0.10)'; ctx.lineWidth = 2;
      ctx.beginPath(); (ctx as any).roundRect(cx, cy, cw, chh, 18); ctx.fill(); ctx.stroke();
      this.text(ctx, String(d.counter.label || 'LIVE').toUpperCase(), cx + 28, cy + 40, 18, '#94A3B8', F.mono(700), cw - 56);
      ctx.save(); ctx.shadowColor = sig; ctx.shadowBlur = 24;
      this.text(ctx, num, cx + 28, cy + 112, 62, sig, F.mono(800), cw - 56);
      ctx.restore();
      if (d.example) this.text(ctx, String(d.example).slice(0, 40), cx + 28, cy + 148, 18, '#64748B', F.archivo(100, 500), cw - 56);
    }
    const ch = this.chunks.find((c) => t >= c.t0 - 0.08 && t <= c.t1 + 0.25) ?? (t < (this.chunks[0]?.t0 ?? 0) ? null : this.chunks[this.chunks.length - 1]);
    if (ch) {                                                                       // caption chunk + key word box
      const fam = ARCH(110, 850), keyset = new Set(String(d.key ?? '').split(/\s+/).map(norm).filter(Boolean));
      const line = ch.words.map((w: any) => w.w).join(' ');
      const sz = Math.min(84, (84 * (W - 160)) / Math.max(1, measure(line, fam, 84)));
      let x = (W - measure(line, fam, sz)) / 2;
      const y = 340;
      ctx.font = font(fam, sz);
      for (const w of ch.words) {
        const ww = measure(w.w, fam, sz), said = t >= w.start - 0.05;
        if (keyset.has(norm(w.w)) && said) {
          const kb = clamp((t - w.start) / 0.3), sc = 0.72 + 0.28 * ease.outBack(kb);     // springy inspector box
          const bx = x - 10, by = y - sz * 0.82, bw = ww + 20, bh = sz * 1.05;
          ctx.save(); ctx.translate(bx + bw / 2, by + bh / 2); ctx.scale(sc, sc); ctx.translate(-(bx + bw / 2), -(by + bh / 2));
          ctx.globalAlpha = clamp(kb * 2); ctx.strokeStyle = BLUE; ctx.lineWidth = 3;
          ctx.fillStyle = 'rgba(59,130,246,0.18)';
          ctx.fillRect(bx, by, bw, bh); ctx.strokeRect(bx, by, bw, bh);
          for (const [hx, hy] of [[bx, by], [bx + bw, by], [bx, by + bh], [bx + bw, by + bh]]) {
            ctx.fillStyle = '#fff'; ctx.fillRect(hx - 6, hy - 6, 12, 12); ctx.strokeRect(hx - 6, hy - 6, 12, 12);
          }
          ctx.restore();
        }
        ctx.globalAlpha = 1; ctx.font = font(fam, sz);
        ctx.fillStyle = said ? this.capInk : (this.capInk === '#FFFFFF' ? 'rgba(170,176,190,0.55)' : 'rgba(90,96,110,0.45)');
        ctx.fillText(w.w, x, y);
        x += ww + measure(' ', fam, sz);
      }
    }
    const wd = d.widget ?? {}, a = ease.outCubic(clamp(age / 0.35));                 // the UI mockup widget
    const X = 70, Y = 470 + 50 * (1 - a), CW = W - 140, CH = this.CH;
    if (wd.kind && !this.noCard) { this.card(ctx, X, Y, CW, CH, a); this.widget(ctx, wd, X, Y, CW, CH, age, dur, a); }
    ctx.globalAlpha = 1;
  }

  widget(ctx: CanvasRenderingContext2D, wd: any, X: number, Y: number, CW: number, CH: number, age: number, dur: number, a: number) {
    const ink = this.ink(), soft = this.ink(0.55), sig = this.style.tintHex;
    const rev = (k: number, n: number) => clamp((age - 0.25 - k * Math.min(0.5, (dur * 0.6) / Math.max(1, n))) / 0.3);
    const title = (s: string) => { this.text(ctx, String(s ?? '').slice(0, 40), X + 32, Y + 56, 30, soft, F.mono(500), CW - 64); };
    const lines: string[] = (Array.isArray(wd.lines) ? wd.lines : Array.isArray(wd.items) ? wd.items : []).filter((x: any) => typeof x !== 'object').map(String).slice(0, 8);
    ctx.globalAlpha = a;
    switch (wd.kind) {
      case 'terminal': case 'code': {                                  // live coding: typed char by char, syntax colours, gutter, cursor
        const term = wd.kind === 'terminal', fs = 30, lh = 56;
        ctx.fillStyle = '#0D1117'; ctx.beginPath(); (ctx as any).roundRect(X + 14, Y + 14, CW - 28, CH - 28, 18); ctx.fill();
        ctx.fillStyle = '#161B22'; ctx.beginPath(); (ctx as any).roundRect(X + 14, Y + 14, CW - 28, 66, [18, 18, 0, 0]); ctx.fill();
        ['#FF5F57', '#FEBC2E', '#28C840'].forEach((c, i) => { ctx.fillStyle = c; ctx.beginPath(); ctx.arc(X + 50 + i * 30, Y + 47, 9, 0, 6.3); ctx.fill(); });
        ctx.fillStyle = '#0D1117'; ctx.beginPath(); (ctx as any).roundRect(X + 160, Y + 24, 280, 56, [10, 10, 0, 0]); ctx.fill();
        this.text(ctx, String(wd.title ?? (term ? 'zsh — 80×24' : 'index.js')), X + 182, Y + 60, 22, '#C9D1D9', F.mono(500), 250);
        const total = lines.reduce((n, l) => n + l.length, 0), cps = Math.max(28, total / Math.max(0.8, dur * 0.62));
        let budget = Math.max(0, age - 0.25) * cps;
        let cursorDrawn = false;
        lines.forEach((ln, i) => {
          const n = Math.floor(clamp(budget, 0, ln.length)); budget -= ln.length;
          if (n <= 0 && i > 0) return;
          const y = Y + 140 + i * lh, hl = i === Number(wd.highlight) && n >= ln.length;
          if (hl) { ctx.fillStyle = rgbaHex(sig, 0.16); ctx.fillRect(X + 22, y - 38, CW - 44, lh - 4); ctx.fillStyle = sig; ctx.fillRect(X + 22, y - 38, 4, lh - 4); }
          ctx.font = font(F.mono(500), fs);
          ctx.fillStyle = '#484F58'; ctx.textAlign = 'right'; ctx.fillText(term ? '' : String(i + 1), X + 74, y); ctx.textAlign = 'left';
          let x = X + (term ? 40 : 96);
          for (const [tok, col] of tokens(ln.slice(0, n), term)) { ctx.fillStyle = col; ctx.fillText(tok, x, y); x += ctx.measureText(tok).width; }
          const here = n < ln.length || budget <= 0 || i === lines.length - 1;
          if (here && !cursorDrawn) { cursorDrawn = true; if (Math.floor(age * 2.4) % 2 === 0) { ctx.fillStyle = sig; ctx.fillRect(x + 2, y - 26, 14, 32); } }
        });
        ctx.fillStyle = rgbaHex(sig, 0.9); ctx.fillRect(X + 14, Y + CH - 52, CW - 28, 38);
        this.text(ctx, term ? '● connected' : `Ln ${lines.length}, Col 1   UTF-8   ${String(wd.lang ?? 'JavaScript')}`, X + 34, Y + CH - 25, 19, '#0B0D12', F.mono(600), CW - 80);
        break;
      }
      case 'browser': {
        ctx.fillStyle = this.light ? '#E9EBF0' : '#232631'; ctx.fillRect(X + 20, Y + 20, CW - 40, 70);
        ctx.fillStyle = this.light ? '#fff' : '#14161C'; ctx.beginPath(); (ctx as any).roundRect(X + 150, Y + 34, CW - 200, 42, 21); ctx.fill();
        this.text(ctx, String(wd.url ?? 'example.com'), X + 172, Y + 64, 24, soft, F.mono(500), CW - 260);
        this.text(ctx, String(wd.title ?? ''), X + 50, Y + 170, 52, ink, ARCH(110, 850), CW - 100);
        lines.forEach((ln, i) => {
          const r = rev(i, lines.length); if (r <= 0) return;
          ctx.globalAlpha = a * r; ctx.fillStyle = this.light ? '#F1F3F7' : '#1C1F28';
          ctx.beginPath(); (ctx as any).roundRect(X + 50, Y + 210 + i * 92, CW - 100, 76, 14); ctx.fill();
          this.text(ctx, ln, X + 78, Y + 258 + i * 92, 32, ink, F.archivo(100, 500), CW - 160);
        });
        break;
      }
      case 'table': {                                                   // a real-looking database table: query bar, avatars, row scan, marks
        const cols: string[] = (wd.columns ?? []).map(String).slice(0, 4), rows: any[][] = (wd.rows ?? []).filter(Array.isArray).slice(0, 6);
        const q = String(wd.query ?? ''), qh = q ? 78 : 0;
        if (q) {
          ctx.fillStyle = this.light ? '#F1F3F6' : '#0D1117'; ctx.strokeStyle = rgbaHex(sig, 0.7); ctx.lineWidth = 2;
          ctx.beginPath(); (ctx as any).roundRect(X + 24, Y + 22, CW - 48, 62, 12); ctx.fill(); ctx.stroke();
          const n = Math.floor(clamp((age - 0.15) * 40, 0, q.length)); let x = X + 46;
          ctx.font = font(F.mono(500), 25);
          for (const [tok, col] of tokens(q.slice(0, n), false)) { ctx.fillStyle = onLight(col, this.light); ctx.fillText(tok, x, Y + 62); x += ctx.measureText(tok).width; }
        } else title(wd.title ?? 'table');
        const top = Y + 70 + qh, cw = (CW - 150) / Math.max(1, cols.length), rh = 72;
        ctx.fillStyle = this.ink(0.05); ctx.fillRect(X + 24, top, CW - 48, 50);
        cols.forEach((c, j) => this.text(ctx, c, X + 110 + j * cw, top + 33, 22, rgbaHex(sig, 0.95), F.mono(600), cw - 14));
        const scan = rows.length ? Math.floor(clamp((age - 0.6) / Math.max(0.6, dur * 0.7), 0, 0.999) * rows.length) : -1;
        rows.forEach((row, i) => {
          const r = rev(i, rows.length); if (r <= 0) return;
          const y = top + 58 + i * rh; ctx.globalAlpha = a * r;
          if (i === scan) { ctx.fillStyle = rgbaHex(sig, 0.14); ctx.fillRect(X + 24, y, CW - 48, rh - 6); }
          ctx.fillStyle = this.ink(0.08); ctx.fillRect(X + 24, y + rh - 6, CW - 48, 1);
          const mk = Array.isArray(wd.marks) ? wd.marks[i] : undefined;
          if (mk !== undefined && i <= scan) {
            ctx.fillStyle = mk ? '#22C55E' : '#EF4444'; ctx.beginPath(); ctx.arc(X + 62, y + 33, 17, 0, 6.3); ctx.fill();
            ctx.strokeStyle = '#fff'; ctx.lineWidth = 4; ctx.beginPath();
            if (mk) { ctx.moveTo(X + 54, y + 34); ctx.lineTo(X + 60, y + 40); ctx.lineTo(X + 71, y + 27); } else { ctx.moveTo(X + 55, y + 26); ctx.lineTo(X + 69, y + 40); ctx.moveTo(X + 69, y + 26); ctx.lineTo(X + 55, y + 40); }
            ctx.stroke();
          } else this.text(ctx, String(i + 1).padStart(2, '0'), X + 46, y + 42, 20, this.ink(0.35), F.mono(500));
          row.slice(0, cols.length).forEach((v, j) => {
            const sv = String(v), x0 = X + 110 + j * cw, person = j === 0 && /^[A-Z][a-z]+$/.test(sv);
            if (person) {                                                // avatar for people
              const hue = (sv.charCodeAt(0) * 47) % 360; ctx.fillStyle = `hsl(${hue},55%,55%)`; ctx.beginPath(); ctx.arc(x0 + 20, y + 33, 20, 0, 6.3); ctx.fill();
              this.text(ctx, sv[0]!, x0 + 12, y + 42, 22, '#fff', F.archivo(100, 700));
              this.text(ctx, sv, x0 + 50, y + 42, 26, this.ink(), F.archivo(100, 600), cw - 60);
            } else this.text(ctx, sv, x0, y + 42, 26, this.ink(), F.mono(500), cw - 14);
          });
        });
        break;
      }
      case 'phone': {                                                   // a real phone mockup: app chat, the last message typed live then sent
        const ph = CH - 24, pw = Math.min(CW * 0.62, ph * 0.5), px = X + (CW - pw) / 2, py = Y + 12, dark = !this.light;
        ctx.fillStyle = '#1B1C1F'; ctx.beginPath(); (ctx as any).roundRect(px, py, pw, ph, 54); ctx.fill();
        ctx.strokeStyle = '#3A3C42'; ctx.lineWidth = 3; ctx.stroke();
        const sx = px + 12, sy = py + 12, sw = pw - 24, sh = ph - 24;
        ctx.fillStyle = dark ? '#0B0B0D' : '#FFFFFF'; ctx.beginPath(); (ctx as any).roundRect(sx, sy, sw, sh, 44); ctx.fill();
        ctx.save(); ctx.beginPath(); (ctx as any).roundRect(sx, sy, sw, sh, 44); ctx.clip();
        const ink = dark ? '#F2F3F5' : '#111318', sub = dark ? '#8B8F98' : '#6B7078';
        ctx.fillStyle = '#000'; ctx.beginPath(); (ctx as any).roundRect(px + pw / 2 - 58, sy + 14, 116, 34, 17); ctx.fill();
        this.text(ctx, '9:41', sx + 34, sy + 42, 22, ink, F.archivo(100, 700));
        ctx.fillStyle = dark ? '#16171A' : '#F6F7F9'; ctx.fillRect(sx, sy + 62, sw, 76);
        ctx.fillStyle = sig; ctx.beginPath(); ctx.arc(sx + 50, sy + 100, 22, 0, 6.3); ctx.fill();
        this.text(ctx, String(wd.app ?? 'Chat').slice(0, 18), sx + 84, sy + 96, 24, ink, F.archivo(100, 700), sw - 110);
        this.text(ctx, 'online', sx + 84, sy + 122, 17, sub, F.archivo(100, 500));
        const msgs = (wd.messages ?? []).filter((m: any) => m && typeof m === 'object').slice(-5);
        const last = msgs[msgs.length - 1], live = !!last && last.from === 'me';
        const tType = 0.3 + 0.12 * Math.max(0, msgs.length - 1), typeDur = Math.max(0.6, Math.min(1.6, dur * 0.35));
        const lastTxt = live ? String(last.text ?? '') : '';
        const typed = lastTxt.slice(0, Math.floor(clamp((age - tType) / typeDur) * lastTxt.length));
        const sent = !live || age > tType + typeDur + 0.2;
        let y = sy + 160;
        msgs.forEach((m: any, i: number) => {
          const isLast = i === msgs.length - 1;
          if (isLast && live && !sent) return;
          const appear = isLast && live ? clamp((age - tType - typeDur - 0.2) / 0.2) : clamp((age - 0.15 - i * 0.12) / 0.2);
          if (appear <= 0) return;
          const me = m.from === 'me', txt = String(m.text ?? ''), fam = F.archivo(100, 500), fsz = 22;
          const w = Math.min(sw * 0.74, measure(txt, fam, fsz) + 40), x = me ? sx + sw - 18 - w : sx + 18;
          ctx.globalAlpha = a * appear; ctx.fillStyle = me ? sig : (dark ? '#26282D' : '#ECEEF1');
          ctx.beginPath(); (ctx as any).roundRect(x, y + 8 * (1 - appear), w, 54, 22); ctx.fill();
          this.text(ctx, txt, x + 20, y + 36 + 8 * (1 - appear), fsz, me ? '#0B0D12' : ink, fam, w - 34);
          if (me) this.text(ctx, '✓✓', x + w - 34, y + 74, 15, sig, F.archivo(100, 700));
          y += me ? 86 : 68;
        });
        ctx.globalAlpha = a;
        const by = sy + sh - 92;
        ctx.fillStyle = dark ? '#1C1D21' : '#F0F1F4'; ctx.beginPath(); (ctx as any).roundRect(sx + 16, by, sw - 94, 56, 28); ctx.fill();
        const showTyped = typed && !sent;
        this.text(ctx, showTyped ? typed : 'Message', sx + 38, by + 36, 22, showTyped ? ink : sub, F.archivo(100, 500), sw - 140);
        if (showTyped && Math.floor(age * 3) % 2 === 0) { const tw = Math.min(sw - 140, measure(typed, F.archivo(100, 500), 22)); ctx.fillStyle = sig; ctx.fillRect(sx + 40 + tw, by + 14, 3, 28); }
        ctx.fillStyle = showTyped ? sig : rgbaHex(sig, 0.35); ctx.beginPath(); ctx.arc(sx + sw - 44, by + 28, 26, 0, 6.3); ctx.fill();
        ctx.fillStyle = '#0B0D12'; ctx.beginPath(); ctx.moveTo(sx + sw - 54, by + 18); ctx.lineTo(sx + sw - 32, by + 28); ctx.lineTo(sx + sw - 54, by + 38); ctx.closePath(); ctx.fill();
        ctx.restore();
        break;
      }
      case 'request': {                                                 // an HTTP request card: method, URL typed, status + timing, JSON reply
        const m = String(wd.method ?? 'GET').toUpperCase(), url = String(wd.url ?? '/'), st = Number(wd.status ?? 200), ms = wd.ms !== undefined ? `${wd.ms} ms` : '';
        const mc = m === 'GET' ? '#22C55E' : m === 'POST' ? '#3B82F6' : m === 'DELETE' ? '#EF4444' : '#F59E0B';
        ctx.fillStyle = this.light ? '#F4F5F7' : '#0D1117'; ctx.beginPath(); (ctx as any).roundRect(X + 24, Y + 30, CW - 48, 96, 16); ctx.fill();
        ctx.fillStyle = rgbaHex(mc, 0.18); ctx.beginPath(); (ctx as any).roundRect(X + 44, Y + 52, 120, 52, 10); ctx.fill();
        this.text(ctx, m, X + 62, Y + 89, 28, mc, F.mono(700));
        const n = Math.floor(clamp((age - 0.2) * 45, 0, url.length));
        this.text(ctx, url.slice(0, n), X + 188, Y + 89, 27, this.ink(), F.mono(500), CW - 260);
        const done = age > 0.3 + url.length / 45 + 0.35;
        ctx.strokeStyle = this.ink(0.25); ctx.lineWidth = 3; ctx.setLineDash([8, 8]); ctx.beginPath(); ctx.moveTo(X + CW / 2, Y + 136); ctx.lineTo(X + CW / 2, Y + 196); ctx.stroke(); ctx.setLineDash([]);
        if (!done) { ctx.fillStyle = sig; ctx.beginPath(); ctx.arc(X + CW / 2, Y + 136 + 60 * ((age * 2) % 1), 8, 0, 6.3); ctx.fill(); }
        if (done) {
          const ok = st < 400, sc = ok ? '#22C55E' : '#EF4444';
          ctx.fillStyle = rgbaHex(sc, 0.16); ctx.beginPath(); (ctx as any).roundRect(X + 24, Y + 206, CW - 48, 84, 16); ctx.fill();
          this.text(ctx, `${st} ${ok ? 'OK' : 'Error'}`, X + 50, Y + 260, 34, sc, F.mono(700));
          if (ms) this.text(ctx, ms, X + CW - 200, Y + 260, 30, this.ink(0.7), F.mono(500));
          lines.slice(0, 5).forEach((ln, i) => {
            const k = clamp((age - 0.9 - i * 0.15) / 0.2); if (k <= 0) return;
            ctx.globalAlpha = a * k; ctx.font = font(F.mono(500), 25); let x = X + 50;
            for (const [tok, col] of tokens(ln, false)) { ctx.fillStyle = onLight(col, this.light); ctx.fillText(tok, x, Y + 340 + i * 46); x += ctx.measureText(tok).width; }
          });
          ctx.globalAlpha = a;
        }
        break;
      }
      case 'stack': {                                                   // isometric stacked layers, a glowing packet drops through them
        const layers = (wd.layers ?? []).filter((o: any) => o && typeof o === 'object').slice(0, 3);
        const tones = ['#3B82F6', sig, '#F59E0B'], n = Math.max(1, layers.length);
        const S = Math.min(CW * 0.46, 430), cx = X + CW / 2, baseY = Y + CH - S * 0.62, step = Math.min(165, (CH - S * 1.25) / Math.max(1, n - 1));
        layers.forEach((L: any, i: number) => {
          const k = ease.outBack(clamp((age - 0.15 - i * 0.3) / 0.5)); if (k <= 0) return;
          const cy = baseY - i * step + (1 - k) * 90, tone = tones[i % 3]!;
          const diamond = (oy: number) => { ctx.beginPath(); ctx.moveTo(cx, cy - S / 2 + oy); ctx.lineTo(cx + S, cy + oy); ctx.lineTo(cx, cy + S / 2 + oy); ctx.lineTo(cx - S, cy + oy); ctx.closePath(); };
          ctx.save(); ctx.globalAlpha = a * clamp(k * 1.4);
          ctx.fillStyle = '#04060A'; diamond(26); ctx.fill();
          ctx.fillStyle = this.light ? '#E9EDF3' : '#111625'; diamond(0); ctx.fill();
          ctx.save(); ctx.shadowColor = tone; ctx.shadowBlur = 18; ctx.strokeStyle = tone; ctx.lineWidth = 3; diamond(0); ctx.stroke(); ctx.restore();
          ctx.translate(cx, cy); ctx.transform(1, 0.5, -1, 0.5, 0, 0);    // draw in the layer's own (isometric) plane
          const h = S / 2;
          ctx.font = font(F.mono(800), 22); ctx.fillStyle = tone; ctx.fillText(String(L.title ?? '').toUpperCase().slice(0, 26), -h + 22, -h + 40);
          const items = (Array.isArray(L.items) ? L.items : []).map(String).slice(0, 6), cols = items.length > 3 ? 3 : Math.max(1, items.length);
          const gw = (S - 44 - (cols - 1) * 12) / cols, gh = 50;
          items.forEach((it: string, j: number) => {
            const gx = -h + 22 + (j % cols) * (gw + 12), gy = -h + 66 + Math.floor(j / cols) * (gh + 12);
            ctx.fillStyle = this.light ? '#FFFFFF' : '#1E293B'; ctx.beginPath(); (ctx as any).roundRect(gx, gy, gw, gh, 8); ctx.fill();
            ctx.save(); ctx.shadowColor = '#10B981'; ctx.shadowBlur = 8; ctx.fillStyle = '#10B981'; ctx.beginPath(); ctx.arc(gx + 18, gy + gh / 2, 6, 0, 6.3); ctx.fill(); ctx.restore();
            this.text(ctx, it.slice(0, 18), gx + 32, gy + gh / 2 + 7, 18, this.ink(), F.mono(600), gw - 40);
          });
          ctx.restore();
        });
        const pk = clamp((age - 0.45 - n * 0.3) / 1.1);                  // the packet travels top -> bottom through every layer
        if (pk > 0 && pk < 1) {
          const top = baseY - (n - 1) * step - S * 0.55, py = top + (baseY - top) * ease.inOutQuad(pk);
          ctx.save(); ctx.globalAlpha = a; ctx.shadowColor = sig; ctx.shadowBlur = 40;
          ctx.fillStyle = sig; ctx.beginPath(); ctx.arc(cx, py, 16, 0, 6.3); ctx.fill();
          ctx.shadowBlur = 0; ctx.fillStyle = '#FFFFFF'; ctx.beginPath(); ctx.arc(cx, py, 7, 0, 6.3); ctx.fill();
          ctx.restore();
        }
        break;
      }
      case 'chat': {
        title(wd.app ?? 'Messages');
        (wd.messages ?? []).filter((m: any) => m && typeof m === 'object').slice(0, 6).forEach((m: any, i: number) => {
          const r = rev(i, 6); if (r <= 0) return;
          const me = m.from === 'me', txt = String(m.text ?? ''), fam = F.archivo(100, 500);
          const w = Math.min(CW - 200, measure(txt, fam, 32) + 56), x = me ? X + CW - 40 - w : X + 40, y = Y + 100 + i * 100 + 20 * (1 - r);
          ctx.globalAlpha = a * r; ctx.fillStyle = me ? BLUE : (this.light ? '#E8EAEE' : '#2A2D37');
          ctx.beginPath(); (ctx as any).roundRect(x, y, w, 76, 28); ctx.fill();
          this.text(ctx, txt, x + 28, y + 50, 32, me ? '#fff' : ink, fam, w - 50);
        });
        break;
      }
      case 'metric': {
        const raw = String(wd.value ?? '0'), m = raw.match(/[\d,.]+/), num = m ? parseFloat(m[0].replace(/,/g, '')) : 0;
        const k = ease.outCubic(clamp((age - 0.2) / Math.min(1.4, dur * 0.6)));
        const shown = m && isFinite(num) ? raw.replace(m[0], Number.isInteger(num) ? Math.round(num * k).toLocaleString('en-US') : (num * k).toFixed(1)) : raw;
        this.text(ctx, shown, X + 50, Y + 330, 190, sig, ARCH(120, 900), CW - 100);
        this.text(ctx, String(wd.label ?? ''), X + 54, Y + 420, 44, ink, ARCH(110, 800), CW - 100);
        this.text(ctx, String(wd.sub ?? ''), X + 54, Y + 480, 30, soft, F.archivo(100, 500), CW - 100);
        for (let i = 0; i < 14; i++) {
          const h = 30 + 120 * Math.abs(Math.sin(i * 1.7 + 0.5)) * clamp((age - 0.3 - i * 0.04) / 0.3);
          ctx.fillStyle = i === 13 ? sig : this.ink(0.18); ctx.fillRect(X + 54 + i * 62, Y + CH - 50 - h, 44, h);
        }
        break;
      }
      case 'compare': {
        title(wd.title ?? '');
        const items = (wd.items ?? []).filter((x: any) => x && typeof x === 'object').slice(0, 5);
        const vmax = Math.max(1, ...items.map((x: any) => Number(x.value) || 0));
        items.forEach((x: any, i: number) => {
          const r = rev(i, items.length), y = Y + 130 + i * 112, v = Number(x.value) || 0;
          ctx.globalAlpha = a;
          this.text(ctx, String(x.label ?? ''), X + 40, y + 40, 32, ink, ARCH(110, 750), 260);
          ctx.fillStyle = this.ink(0.1); ctx.beginPath(); (ctx as any).roundRect(X + 320, y + 6, CW - 380, 48, 24); ctx.fill();
          ctx.fillStyle = i % 2 ? BLUE : sig; ctx.beginPath(); (ctx as any).roundRect(X + 320, y + 6, Math.max(48, (CW - 380) * (v / vmax) * ease.outCubic(r)), 48, 24); ctx.fill();
          ctx.globalAlpha = a * r; this.text(ctx, `${x.value}${x.unit ? ' ' + x.unit : ''}`, X + 340, y + 42, 28, '#fff', F.mono(600));
        });
        break;
      }
      case 'flow': {
        const nodes = (Array.isArray(wd.nodes) ? wd.nodes : lines).map(String).slice(0, 5), act = Number(wd.active ?? nodes.length - 1);
        const nh = 96, gap = (CH - 80 - nodes.length * nh) / Math.max(1, nodes.length - 1);
        nodes.forEach((n: string, i: number) => {
          const r = rev(i, nodes.length), y = Y + 40 + i * (nh + gap), on = i === act;
          ctx.globalAlpha = a * r;
          ctx.fillStyle = on ? sig : (this.light ? '#fff' : '#22252F'); ctx.strokeStyle = on ? sig : this.ink(0.2); ctx.lineWidth = 3;
          ctx.beginPath(); (ctx as any).roundRect(X + 120, y, CW - 240, nh, 20); ctx.fill(); ctx.stroke();
          this.text(ctx, n, X + 160, y + 62, 36, on ? '#0B0D12' : ink, ARCH(110, 800), CW - 320);
          if (i < nodes.length - 1) {
            ctx.strokeStyle = this.ink(0.35); ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(X + CW / 2, y + nh + 6); ctx.lineTo(X + CW / 2, y + nh + gap - 6); ctx.stroke();
            const py = y + nh + 6 + (gap - 12) * ((age * 0.9 + i * 0.3) % 1);
            ctx.fillStyle = sig; ctx.beginPath(); ctx.arc(X + CW / 2, py, 9, 0, 6.3); ctx.fill();
          }
        });
        break;
      }
      case 'checklist': case 'summary': {
        title(wd.title ?? (wd.kind === 'summary' ? 'THE WHOLE JOURNEY' : 'CHECKLIST'));
        lines.forEach((ln, i) => {
          const r = rev(i, lines.length); if (r <= 0) return;
          const y = Y + 120 + i * 84;
          ctx.globalAlpha = a * r;
          ctx.fillStyle = wd.kind === 'summary' ? sig : GREEN; ctx.beginPath(); ctx.arc(X + 70, y + 20, 22, 0, 6.3); ctx.fill();
          ctx.strokeStyle = '#0B0D12'; ctx.lineWidth = 5;
          if (wd.kind === 'summary') this.text(ctx, String(i + 1), X + 61, y + 31, 28, '#0B0D12', ARCH(110, 900));
          else { ctx.beginPath(); ctx.moveTo(X + 59, y + 21); ctx.lineTo(X + 67, y + 29); ctx.lineTo(X + 82, y + 11); ctx.stroke(); }
          this.text(ctx, ln, X + 116, y + 32, 34, ink, F.archivo(100, 600), CW - 160);
        });
        break;
      }
      default: {
        title(wd.title ?? '');
        lines.forEach((ln, i) => { const r = rev(i, lines.length); if (r > 0) { ctx.globalAlpha = a * r; this.text(ctx, '- ' + ln, X + 40, Y + 130 + i * 80, 34, ink); } });
      }
    }
    ctx.globalAlpha = 1;
  }
  override postFX(t: number) {
    const k = 1 - prog(t, this.t0, this.t0 + 0.3);
    return { zoom: 1 + 0.05 * k * k };
  }
}
