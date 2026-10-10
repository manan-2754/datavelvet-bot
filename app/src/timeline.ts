// The edit, built from the generated script: one plate per scene, each cut in the pause before the scene's
// first line (never after it). data/lyrics.json carries the lines (each tagged with its scene) and the
// scenes themselves ({ plate, title, data, meta }), written by the bot (bot/make_vo.py).
import type { TimelineEntry } from './engine/engine';
import type { SceneClass } from './engine/scene';
import type { Lyrics } from './engine/lyrics';
import type { AudioData } from './engine/audio';

// All plates live in scenes/_plates.ts; a scene's `plate` picks the class.
const CLASSES: Record<string, string> = {
  hook: 'Hook', title: 'Title', specimen: 'Specimen', holo: 'Holo', flows: 'Flows', form: 'Form', stats: 'Stats', compare: 'Compare', outro: 'Outro',
  scene3d: 'Scene3D', layers: 'Layers', orbit: 'Orbit', tunnel: 'Tunnel', bars3d: 'Bars3D', edit: 'Edit', compose: 'Compose',
};
const plates = import.meta.glob<Record<string, SceneClass>>('./scenes/_plates.ts');
const scene = (name: string) => () =>
  plates['./scenes/_plates.ts']!().then((m) => ({ default: m[CLASSES[name.replace(/^g_/, '')] ?? 'Title']! }));

export function makeTimeline(ly: Lyrics, au: AudioData): TimelineEntry[] {
  const scenes = ly.scenes ?? [];
  const starts = scenes.map((_: any, i: number) => {
    if (i === 0) return 0;
    const first = ly.lines.find((l: any) => l.scene === i);
    if (!first) return null;
    const prev = ly.lines[first.i - 1];
    const gap = prev ? first.start - prev.end : 1;
    return first.start - Math.min(0.2, Math.max(0.04, gap * 0.45));
  });
  const out: TimelineEntry[] = [];
  scenes.forEach((s: any, i: number) => {
    const t0 = starts[i];
    if (t0 == null) return;
    let t1 = au.duration;
    for (let j = i + 1; j < scenes.length; j++) if (starts[j] != null) { t1 = starts[j]!; break; }
    out.push({ id: `${String(i).padStart(2, '0')}_${s.plate}`, load: scene(`g_${s.plate}`), start: t0, end: t1, params: { scene: i } });
  });
  return out;
}
