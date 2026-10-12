// World plate (pro-bot v2): ONE persistent, lit 3D world for the whole video, like the best tech explainers.
//   - every stage of the journey is a hub in the world with a real shaded 3D hero object (soft shadows, studio light)
//   - every beat's UI mockup (terminal, browser, table, real web-page screenshot...) is a panel standing in the world;
//     panels stay where they are, so the camera keeps passing what was already explained
//   - one continuous camera: slow push-in during a beat, a fast orbit/fly to the next panel on every cut, a lifted
//     fly-over between stages (render motion blur makes the whips feel real)
//   - the running example is a physical token that travels hub to hub along a cable with live data flowing in it
//   - background swaps light/dark by stage; captions + HUD (stepper, counter) are drawn on top by the Story plate
import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import { W } from '../engine/gl';
import { F, font } from '../engine/type';
import { clamp, ease } from '../engine/util';
import type { Frame, PostOverrides } from '../engine/scene';
import type * as T from 'three';
import { Story } from './_story';
import { Presenter, type Gesture } from './_presenter';

const IMG: Record<string, Promise<HTMLImageElement>> = {};
function loadImg(src: string) {
  return (IMG[src] ??= new Promise((res) => { const im = new Image(); im.onload = () => res(im); im.onerror = () => res(im); im.src = src; }));
}
const v3 = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const PW = 4.4;                    // panel width (world units)
const RP = 4.6, RC = 9.6;          // panel ring radius (behind the hero), camera ring radius
const STEP = 0.9;                  // angle between neighbouring panels of one stage
const LIGHT_BG = new THREE.Color('#ECEEF2'), DARK_BG = new THREE.Color('#090A0F');

interface Panel { mesh: THREE.Mesh; slab: THREE.Mesh; g: THREE.Group; canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D; tex: THREE.CanvasTexture; ph: number; drawnFinal: boolean }

function phys(color: string | THREE.Color, o: Partial<THREE.MeshPhysicalMaterialParameters> = {}) {
  return new THREE.MeshPhysicalMaterial({ color, roughness: 0.35, metalness: 0.05, clearcoat: 0.6, clearcoatRoughness: 0.2, ...o });
}
function glow(color: THREE.Color, k = 2.2) { return new THREE.MeshBasicMaterial({ color: color.clone().multiplyScalar(k), toneMapped: false }); }
function rbox(w: number, h: number, d: number, r: number, m: THREE.Material) {
  const mesh = new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 4, Math.min(r, w / 2, h / 2, d / 2)), m);
  mesh.castShadow = true; mesh.receiveShadow = true; return mesh;
}
function textCanvas(w: number, h: number, draw: (c: CanvasRenderingContext2D) => void) {
  const cv = document.createElement('canvas'); cv.width = w; cv.height = h;
  draw(cv.getContext('2d')!);
  const tx = new THREE.CanvasTexture(cv); tx.colorSpace = THREE.SRGBColorSpace; tx.anisotropy = 8;
  return tx;
}

/** Real shaded 3D hero objects (primitives + extrusions), about 2.2 units tall, standing on y = 0. */
function hero(kind: string, tint: THREE.Color, example: string): THREE.Group {
  const g = new THREE.Group(), body = phys('#E9EBEF'), dark = phys('#1B1E25', { roughness: 0.45, metalness: 0.3 }),
    metal = new THREE.MeshStandardMaterial({ color: '#C3C7D0', metalness: 0.9, roughness: 0.25 }), acc = phys(tint, { clearcoat: 1, roughness: 0.25 }), lit = glow(tint);
  const add = (m: THREE.Object3D, x = 0, y = 0, z = 0) => { m.position.set(x, y, z); m.traverse((o: any) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } }); g.add(m); return m; };
  const screen = (w: number, h: number, kindS: 'chat' | 'code') => new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({
    map: textCanvas(512, Math.round((512 * h) / w), (c) => {
      const cw = 512, ch = Math.round((512 * h) / w);
      c.fillStyle = kindS === 'chat' ? '#ECE5DD' : '#0E1117'; c.fillRect(0, 0, cw, ch);
      if (kindS === 'chat') {
        c.fillStyle = '#075E54'; c.fillRect(0, 0, cw, 90); c.fillStyle = '#fff'; c.font = '600 34px sans-serif'; c.fillText('Chat', 40, 60);
        const msg = (example.match(/'([^']+)'|"([^"]+)"/)?.slice(1).find(Boolean) ?? example).slice(0, 22);
        c.font = '500 36px sans-serif'; const tw = c.measureText(msg).width + 50;
        c.fillStyle = '#DCF8C6'; c.beginPath(); (c as any).roundRect(cw - tw - 30, ch * 0.62, tw, 70, 18); c.fill();
        c.fillStyle = '#111'; c.fillText(msg, cw - tw - 5, ch * 0.62 + 47);
        c.fillStyle = '#34B7F1'; c.font = '600 26px sans-serif'; c.fillText('✓✓', cw - 80, ch * 0.62 + 100);
      } else {
        const cols = ['#C792EA', '#82AAFF', '#C3E88D', '#FFCB6B', '#F07178'];
        for (let i = 0; i < 14; i++) { c.fillStyle = cols[i % 5]!; c.fillRect(30 + (i % 3) * 20, 30 + i * 30, 120 + ((i * 97) % 260), 14); }
      }
    }), toneMapped: false,
  }));
  switch (kind) {
    case 'phone': {
      const p = new THREE.Group(); p.add(rbox(1.2, 2.4, 0.14, 0.16, dark));
      const s = screen(1.08, 2.24, 'chat'); s.position.z = 0.072; p.add(s);
      p.rotation.x = -0.12; add(p, 0, 1.3, 0); break;
    }
    case 'laptop': {
      add(rbox(2.6, 0.1, 1.7, 0.05, metal), 0, 0.05, 0);
      const lid = new THREE.Group(); const l = rbox(2.6, 1.7, 0.07, 0.05, metal); l.position.y = 0.85; lid.add(l);
      const s = screen(2.4, 1.5, 'code'); s.position.set(0, 0.85, 0.04); lid.add(s);
      lid.rotation.x = -0.22; add(lid, 0, 0.1, -0.82); break;
    }
    case 'server': case 'stack': {
      for (let i = 0; i < 4; i++) {
        add(rbox(1.9, 0.44, 1.4, 0.05, i % 2 ? dark : phys('#2A2E37', { metalness: 0.4 })), 0, 0.25 + i * 0.5, 0);
        for (let k = 0; k < 3; k++) { const led = add(new THREE.Mesh(new THREE.SphereGeometry(0.035, 12, 8), lit), -0.75 + k * 0.12, 0.25 + i * 0.5, 0.71); led.userData.blink = i * 3 + k; }
        add(new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.04, 0.01), metal), 0.35, 0.25 + i * 0.5, 0.705);
      }
      break;
    }
    case 'db': {
      for (let i = 0; i < 3; i++) {
        add(new THREE.Mesh(new THREE.CylinderGeometry(0.9, 0.9, 0.52, 64), i === 2 ? acc : body), 0, 0.3 + i * 0.62, 0);
        add(new THREE.Mesh(new THREE.TorusGeometry(0.9, 0.025, 8, 64).rotateX(Math.PI / 2), lit), 0, 0.58 + i * 0.62, 0);
      }
      break;
    }
    case 'globe': {
      const gl = new THREE.Group();
      gl.add(new THREE.Mesh(new THREE.SphereGeometry(1.05, 64, 48), phys('#DDE4EE', { roughness: 0.5 })));
      const dots = new THREE.InstancedMesh(new THREE.SphereGeometry(0.022, 6, 4), acc, 900), m = new THREE.Matrix4();
      let n = 0;
      for (let i = 0; i < 2600 && n < 900; i++) {
        const y = 1 - (2 * (i + 0.5)) / 2600, r = Math.sqrt(1 - y * y), a = i * 2.39996, x = Math.cos(a) * r, z = Math.sin(a) * r;
        const land = Math.sin(x * 3.1 + 1) * Math.cos(z * 2.7) + Math.sin(y * 4.2 + x * 1.3) * 0.8;   // continent-ish blobs
        if (land > 0.35) { m.setPosition(x * 1.06, y * 1.06, z * 1.06); dots.setMatrixAt(n++, m); }
      }
      dots.count = n; gl.add(dots);
      const ring = new THREE.Mesh(new THREE.TorusGeometry(1.45, 0.018, 8, 128), lit); ring.rotation.x = 1.2; gl.add(ring);
      add(gl, 0, 1.3, 0); g.userData.spin = gl; break;
    }
    case 'chip': {
      const c = new THREE.Group();
      c.add(rbox(1.9, 0.16, 1.9, 0.06, dark));
      const die = rbox(1.0, 0.12, 1.0, 0.04, metal); die.position.y = 0.13; c.add(die);
      const core = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.02, 0.6), lit); core.position.y = 0.2; c.add(core);
      for (let s = 0; s < 4; s++) for (let k = 0; k < 9; k++) {
        const pin = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.05, 0.22), metal), o = -0.8 + k * 0.2;
        if (s < 2) pin.position.set(o, 0, s ? 1.05 : -1.05); else { pin.rotation.y = Math.PI / 2; pin.position.set(s === 2 ? 1.05 : -1.05, 0, o); }
        c.add(pin);
      }
      c.rotation.x = 0.55; add(c, 0, 1.1, 0); break;
    }
    case 'router': {
      add(rbox(2.0, 0.36, 1.2, 0.12, body), 0, 0.2, 0);
      for (let k = 0; k < 3; k++) {
        const a = add(new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, 1.3, 16), dark), -0.7 + k * 0.7, 1.0, -0.4); a.rotation.z = (k - 1) * 0.25;
        const led = add(new THREE.Mesh(new THREE.SphereGeometry(0.04, 12, 8), lit), -0.5 + k * 0.25, 0.25, 0.61); led.userData.blink = k;
      }
      for (let k = 0; k < 3; k++) { const arc = add(new THREE.Mesh(new THREE.TorusGeometry(0.35 + k * 0.3, 0.035, 8, 48, Math.PI * 0.6), lit), 0, 1.75, 0); arc.rotation.z = Math.PI * 0.2; arc.userData.wave = k; }
      break;
    }
    case 'cloud': {
      for (const [x, y, r] of [[0, 1.4, 0.75], [-0.75, 1.15, 0.55], [0.75, 1.15, 0.55], [-0.35, 1.0, 0.5], [0.4, 0.98, 0.5]] as const) add(new THREE.Mesh(new THREE.SphereGeometry(r, 48, 32), phys('#F4F6FA', { roughness: 0.6 })), x, y, 0);
      break;
    }
    case 'lock': {
      add(rbox(1.4, 1.2, 0.5, 0.14, acc), 0, 0.75, 0);
      g.userData.shackle = add(new THREE.Mesh(new THREE.TorusGeometry(0.45, 0.1, 16, 48, Math.PI), metal), 0, 1.35, 0);
      add(new THREE.Mesh(new THREE.CylinderGeometry(0.11, 0.11, 0.1, 24).rotateX(Math.PI / 2), dark), 0, 0.82, 0.26);
      break;
    }
    case 'shield': {
      const s = new THREE.Shape(); s.moveTo(0, 1.1); s.quadraticCurveTo(0.6, 1.0, 0.95, 0.85); s.quadraticCurveTo(0.95, -0.4, 0, -1.05); s.quadraticCurveTo(-0.95, -0.4, -0.95, 0.85); s.quadraticCurveTo(-0.6, 1.0, 0, 1.1);
      add(new THREE.Mesh(new THREE.ExtrudeGeometry(s, { depth: 0.3, bevelEnabled: true, bevelSize: 0.06, bevelThickness: 0.06, bevelSegments: 4 }), acc), 0, 1.2, -0.15);
      const ck = new THREE.Shape(); ck.moveTo(-0.45, 0.05); ck.lineTo(-0.12, -0.3); ck.lineTo(0.48, 0.38); ck.lineTo(0.36, 0.5); ck.lineTo(-0.12, -0.05); ck.lineTo(-0.33, 0.17);
      add(new THREE.Mesh(new THREE.ExtrudeGeometry(ck, { depth: 0.1, bevelEnabled: false }), body), 0, 1.2, 0.2);
      break;
    }
    case 'gear': {
      const s = new THREE.Shape(), n = 12;
      for (let i = 0; i <= n * 4; i++) { const a = (i / (n * 4)) * Math.PI * 2, r = i % 4 < 2 ? 1.0 : 0.8; if (i) s.lineTo(Math.cos(a) * r, Math.sin(a) * r); else s.moveTo(r, 0); }
      const hole = new THREE.Path(); hole.absarc(0, 0, 0.3, 0, Math.PI * 2, true); s.holes.push(hole);
      g.userData.gear = add(new THREE.Mesh(new THREE.ExtrudeGeometry(s, { depth: 0.3, bevelEnabled: true, bevelSize: 0.03, bevelThickness: 0.03 }), metal), 0, 1.25, -0.15);
      break;
    }
    case 'user': {
      add(new THREE.Mesh(new THREE.CapsuleGeometry(0.55, 0.6, 8, 32), acc), 0, 0.85, 0); add(new THREE.Mesh(new THREE.SphereGeometry(0.42, 48, 32), body), 0, 1.95, 0);
      break;
    }
    case 'bot': {
      add(rbox(1.3, 1.0, 1.0, 0.25, body), 0, 1.5, 0); add(rbox(1.0, 0.8, 0.8, 0.2, dark), 0, 0.5, 0);
      for (const x of [-0.28, 0.28]) add(new THREE.Mesh(new THREE.SphereGeometry(0.12, 24, 16), lit), x, 1.55, 0.5);
      add(new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.4), metal), 0, 2.15, 0); add(new THREE.Mesh(new THREE.SphereGeometry(0.08, 16, 12), lit), 0, 2.38, 0);
      break;
    }
    case 'pyramid': {
      for (let i = 0; i < 4; i++) {
        const r0 = 1.3 - i * 0.3, m = add(new THREE.Mesh(new THREE.CylinderGeometry(r0 - 0.27, r0, 0.42, 4, 1), i % 2 ? acc : body), 0, 0.23 + i * 0.5, 0);
        m.rotation.y = Math.PI / 4;
      }
      break;
    }
    case 'helix': {
      for (let i = 0; i < 22; i++) {
        const a = i * 0.55, y = 0.2 + i * 0.09;
        add(new THREE.Mesh(new THREE.SphereGeometry(0.1, 16, 12), acc), Math.cos(a) * 0.6, y, Math.sin(a) * 0.6);
        add(new THREE.Mesh(new THREE.SphereGeometry(0.1, 16, 12), body), -Math.cos(a) * 0.6, y, -Math.sin(a) * 0.6);
      }
      break;
    }
    default: {   // cube
      add(rbox(1.5, 1.5, 1.5, 0.18, phys(tint, { transmission: 0.6, thickness: 1.2, roughness: 0.15, clearcoat: 1 })), 0, 1.0, 0);
      add(rbox(0.7, 0.7, 0.7, 0.1, lit), 0, 1.0, 0);
    }
  }
  return g;
}

class World {
  scene = new THREE.Scene();
  cam = new THREE.PerspectiveCamera(36, 1080 / 1920, 0.1, 400);
  sun = new THREE.DirectionalLight(0xffffff, 2.4);
  ground: THREE.Mesh;
  hubs: THREE.Vector3[] = [];
  heroes: THREE.Group[] = [];
  stageT0: number[] = [];
  beatT0: number[] = [];
  beatStage: number[] = [];
  beatAng: number[] = [];
  beatLight: boolean[] = [];
  panels: (Panel | null)[] = [];
  curve: THREE.CatmullRomCurve3;
  token: THREE.Group;
  flow: THREE.InstancedMesh;
  tint: THREE.Color;
  scenes: any[] = [];
  imgs = new Map<string, HTMLImageElement>();
  painter: any;
  swarm: THREE.InstancedMesh;
  swarmT: { p: THREE.Vector3; r: THREE.Euler; ph: number }[] = [];
  presenter: Presenter;
  packet!: THREE.Group;
  constructor(renderer: THREE.WebGLRenderer, ly: any, tintHex: string, imgs: Map<string, HTMLImageElement>) {
    this.imgs = imgs;
    this.painter = Object.create(Story.prototype);
    this.painter.style = { tintHex };
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    const pm = new THREE.PMREMGenerator(renderer);
    this.scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
    this.scene.environmentIntensity = 0.85;
    this.tint = new THREE.Color(tintHex);
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x8890a0, 0.6), this.sun, this.sun.target);
    this.sun.castShadow = true; this.sun.shadow.mapSize.set(2048, 2048); this.sun.shadow.radius = 6; this.sun.shadow.bias = -0.0004;
    Object.assign(this.sun.shadow.camera, { left: -10, right: 10, top: 10, bottom: -10, near: 1, far: 60 });
    this.ground = new THREE.Mesh(new THREE.PlaneGeometry(600, 600), new THREE.MeshStandardMaterial({ color: LIGHT_BG, roughness: 1 }));
    const dots = textCanvas(64, 64, (c) => { c.fillStyle = '#000'; c.fillRect(0, 0, 64, 64); c.fillStyle = '#2A3140'; c.beginPath(); c.arc(32, 32, 3.2, 0, 6.3); c.fill(); });
    dots.wrapS = dots.wrapT = THREE.RepeatWrapping; dots.repeat.set(500, 500);
    Object.assign(this.ground.material as THREE.MeshStandardMaterial, { emissive: new THREE.Color('#ffffff'), emissiveMap: dots, emissiveIntensity: 1 });
    this.ground.rotation.x = -Math.PI / 2; this.ground.receiveShadow = true; this.scene.add(this.ground);
    this.scene.fog = new THREE.Fog(LIGHT_BG, 20, 70);

    const scenes: any[] = (this.scenes = ly.scenes ?? []);
    scenes.forEach((s: any, i: number) => {
      const first = ly.lines.find((l: any) => l.scene === i);
      this.beatT0[i] = i === 0 ? 0 : first ? first.start - 0.12 : (this.beatT0[i - 1] ?? 0) + 2;
      this.beatStage[i] = Number(s.data?.stage) || 0;
      this.beatLight[i] = !!s.data?.light;
    });
    const nStage = Math.max(1, ...this.beatStage.map((x) => x + 1));
    for (let st = 0; st < nStage; st++) {
      this.hubs.push(v3(st * 17, 0, Math.sin(st * 1.7) * 5));
      const bi = this.beatStage.indexOf(st);
      this.stageT0[st] = bi >= 0 ? this.beatT0[bi]! : 1e9;
      const h = hero(String(scenes[bi]?.data?.object ?? 'cube'), this.tint, String(scenes[0]?.data?.example ?? ''));
      h.position.copy(this.hubs[st]!); h.scale.setScalar(0.001); h.userData.base = 0.82;
      const pool = new THREE.Mesh(new THREE.PlaneGeometry(9, 9), new THREE.MeshBasicMaterial({ map: textCanvas(256, 256, (c) => {   // radial glow under the hero
        const g = c.createRadialGradient(128, 128, 0, 128, 128, 128); g.addColorStop(0, 'rgba(255,255,255,0.32)'); g.addColorStop(0.45, 'rgba(255,255,255,0.07)'); g.addColorStop(1, 'rgba(255,255,255,0)');
        c.fillStyle = g; c.fillRect(0, 0, 256, 256);
      }), color: this.tint, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }));
      pool.rotation.x = -Math.PI / 2; pool.position.set(this.hubs[st]!.x, 0.03, this.hubs[st]!.z); this.scene.add(pool);
      this.scene.add(h); this.heroes.push(h);
    }
    const count: number[] = Array(nStage).fill(0);                    // panel angle: fan the stage's beats around its hub
    const per = this.beatStage.reduce((m, s) => ((m[s] = (m[s] ?? 0) + 1), m), [] as number[]);
    this.beatStage.forEach((st, i) => {
      const j = count[st]!++, n = per[st] ?? 1;
      this.beatAng[i] = (j - (n - 1) / 2) * Math.min(STEP, 2.4 / Math.max(1, n - 1)) * (st % 2 ? -1 : 1);
    });
    const pts = this.hubs.map((h) => v3(h.x, 0.04, h.z));
    if (pts.length < 2) pts.push(v3(17, 0.04, 0));
    this.curve = new THREE.CatmullRomCurve3(pts, false, 'catmullrom', 0.3);
    const cable = new THREE.Mesh(new THREE.TubeGeometry(this.curve, 400, 0.05, 8, false), phys('#9AA3B2', { roughness: 0.5 }));
    cable.receiveShadow = true; this.scene.add(cable);
    this.flow = new THREE.InstancedMesh(new THREE.SphereGeometry(0.07, 12, 8), glow(this.tint, 3), 160);
    this.scene.add(this.flow);
    this.token = new THREE.Group();
    const ex = String(scenes[0]?.data?.example ?? 'your data');
    const tt = textCanvas(1024, 200, (c) => {
      c.fillStyle = '#ffffff'; c.beginPath(); (c as any).roundRect(4, 4, 1016, 192, 96); c.fill();
      c.fillStyle = tintHex; c.beginPath(); c.arc(100, 100, 52, 0, 6.3); c.fill();
      c.fillStyle = '#12151C'; let sz = 70; c.font = `700 ${sz}px sans-serif`;
      while (sz > 30 && c.measureText(ex).width > 800) { sz -= 4; c.font = `700 ${sz}px sans-serif`; }
      c.fillText(ex, 180, 100 + sz * 0.36);
    });
    this.token.add(new THREE.Mesh(new THREE.PlaneGeometry(2.6, 0.51), new THREE.MeshBasicMaterial({ map: tt, transparent: true, toneMapped: false })));
    this.scene.add(this.token);
    this.token.visible = false;                                         // the metric card carries the running example now
    this.packet = new THREE.Group();                                    // glowing packet: hero -> screen on every beat
    this.packet.add(new THREE.Mesh(new THREE.SphereGeometry(0.11, 20, 14), glow(this.tint, 4)));
    this.packet.add(new THREE.Sprite(new THREE.SpriteMaterial({ map: textCanvas(128, 128, (c) => {
      const g = c.createRadialGradient(64, 64, 0, 64, 64, 64); g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(0.25, 'rgba(255,255,255,0.5)'); g.addColorStop(1, 'rgba(255,255,255,0)');
      c.fillStyle = g; c.fillRect(0, 0, 128, 128);
    }), color: this.tint, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false })));
    (this.packet.children[1] as THREE.Sprite).scale.setScalar(0.9);
    this.packet.visible = false; this.scene.add(this.packet);
    const N = 1100, sw = new THREE.InstancedMesh(new RoundedBoxGeometry(0.3, 0.1, 0.03, 2, 0.02), new THREE.MeshStandardMaterial({ roughness: 0.35, metalness: 0.1 }), N);
    const col = new THREE.Color();
    for (let k = 0; k < N; k++) {                                     // the swarm: thousands of "data chips" for big numbers
      const y = 1 - (2 * (k + 0.5)) / N, r = Math.sqrt(1 - y * y), a = k * 2.39996, R = 1.1 + (((k * 7919) % 100) / 100) * 1.2;
      this.swarmT.push({ p: v3(Math.cos(a) * r * R, 1.9 + y * R * 0.55, Math.sin(a) * r * R - 1.0), r: new THREE.Euler(0, -a + Math.PI / 2, (((k * 31) % 20) - 10) * 0.03), ph: (k % 97) / 97 });
      sw.setColorAt(k, col.set(k % 5 === 0 ? tintHex : k % 7 === 0 ? '#9AA3B2' : '#F5F7FA'));
    }
    sw.castShadow = true; sw.visible = false;
    this.swarm = sw; this.scene.add(sw);
    this.presenter = new Presenter(this.scene.environment!, new THREE.Color(String(scenes[0]?.data?.outfit ?? '#5B3FD6')));
  }

  /** Paint beat i's widget into its panel (any beat at any time, so split renders can start anywhere). */
  paint(i: number, t: number) {
    const sd = this.scenes[i]?.data ?? {}, wd = sd.widget ?? {}, img = wd.img ? this.imgs.get(wd.img) : undefined;
    if (!wd.kind && !img) return;
    let p = this.panels[i];
    if (!p) p = this.makePanel(i, clamp((Story.prototype.fitCH(img ? { kind: 'shot' } : wd) / 940) * PW, 1.8, 3.0));
    if (p.drawnFinal) return;
    const t0 = this.beatT0[i]!, dur = Math.max(0.5, (this.beatT0[i + 1] ?? t0 + 4) - t0), age = t - t0, P = this.painter;
    P.light = !!sd.light; P.d = sd;
    const c = p.ctx, cw = p.canvas.width, chh = p.canvas.height, CW = W - 140, k = cw / CW, CH = chh / k;
    c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, cw, chh);
    c.save(); c.scale(k, k);
    P.card(c, 0, 0, CW, CH, 1);
    if (img && img.naturalWidth && wd.kind === 'photo') {             // real photo: Ken Burns drift + licence credit
      const iw = img.naturalWidth, ih = img.naturalHeight, z = 1.04 + 0.08 * clamp(age / dur), s = Math.max(CW / iw, CH / ih) * z;
      c.save(); c.beginPath(); (c as any).roundRect(0, 0, CW, CH, 22); c.clip();
      c.drawImage(img, (CW - iw * s) / 2 - 20 * clamp(age / dur), (CH - ih * s) / 2, iw * s, ih * s);
      const gr = c.createLinearGradient(0, CH - 90, 0, CH); gr.addColorStop(0, 'rgba(0,0,0,0)'); gr.addColorStop(1, 'rgba(0,0,0,0.7)');
      c.fillStyle = gr; c.fillRect(0, CH - 90, CW, 90);
      c.font = font(F.mono(500), 20); c.fillStyle = 'rgba(255,255,255,0.85)'; c.fillText(String(wd.credit ?? '').slice(0, 70), 24, CH - 22);
      c.restore();
    } else if (img && img.naturalWidth) {                             // real web page, live-scrolling
      const bar = 70;
      c.fillStyle = P.light ? '#E9EBF0' : '#232631'; c.fillRect(0, 0, CW, bar);
      ['#FF5F57', '#FEBC2E', '#28C840'].forEach((col, q) => { c.fillStyle = col; c.beginPath(); c.arc(34 + q * 28, 35, 9, 0, 6.3); c.fill(); });
      c.fillStyle = P.light ? '#fff' : '#14161C'; c.beginPath(); (c as any).roundRect(130, 15, CW - 160, 40, 20); c.fill();
      c.font = font(F.mono(500), 22); c.fillStyle = P.ink(0.6); c.fillText(String(wd.url ?? '').replace(/^https?:[/][/]/, '').slice(0, 52), 152, 43);
      const iw = img.naturalWidth, ih = img.naturalHeight, scl = CW / iw, vis = (CH - bar) / scl;
      const scroll = Math.max(0, (ih - vis) * Math.min(0.35, 0.35 * ease.inOutQuad(clamp((age - 0.6) / Math.max(1, dur - 0.6)))));
      c.save(); c.beginPath(); c.rect(0, bar, CW, CH - bar); c.clip();
      c.drawImage(img, 0, scroll, iw, Math.min(vis, ih), 0, bar, CW, Math.min(vis, ih) * scl);
      c.restore();
    } else {
      P.widget(c, wd, 0, 0, CW, CH, Math.min(age, dur + 2), dur, 1);
    }
    c.restore();
    p.tex.needsUpdate = true;
    if (age > dur) p.drawnFinal = true;
  }

  updateSwarm(t: number) {
    const i = this.scenes.findIndex((s: any, k: number) => s?.data?.swarm && t >= this.beatT0[k]! && t < (this.beatT0[k + 1] ?? 1e9) + 0.9);
    if (i < 0) { this.swarm.visible = false; return; }
    const hub = this.hubs[this.beatStage[i]!]!, age = t - this.beatT0[i]!, dur = (this.beatT0[i + 1] ?? this.beatT0[i]! + 4) - this.beatT0[i]!;
    const out = ease.inCubic(clamp((age - dur) / 0.8)), m = new THREE.Matrix4(), q = new THREE.Quaternion(), sc = v3(), pos = v3(), rot = new THREE.Euler();
    const src = v3(hub.x, 1.2, hub.z), spin = t * 0.18;
    this.swarm.visible = true;
    this.swarmT.forEach((d, k) => {
      const e = ease.outCubic(clamp((age - 0.15 - d.ph * 0.7) / 0.9));
      const x = d.p.x * Math.cos(spin) - d.p.z * Math.sin(spin), z = d.p.x * Math.sin(spin) + d.p.z * Math.cos(spin);
      pos.set(hub.x + x, d.p.y + 0.15 * Math.sin(t * 1.3 + d.ph * 6), hub.z + z).lerp(src, 1 - e).lerp(src, out);
      rot.set(d.r.x, d.r.y - spin, d.r.z + (1 - e) * 4); q.setFromEuler(rot);
      const s = Math.max(0.001, e * (1 - out)); sc.set(s, s, s);
      this.swarm.setMatrixAt(k, m.compose(pos, q, sc));
    });
    this.swarm.instanceMatrix.needsUpdate = true;
  }

  stageAt(t: number) { let s = 0; this.stageT0.forEach((t0, i) => { if (t >= t0) s = i; }); return s; }
  beatAt(t: number) { let b = 0; this.beatT0.forEach((t0, i) => { if (t >= t0) b = i; }); return b; }

  /** Camera pose for beat i at time t (no transition): ring around the stage hub, slow push-in + drift. */
  pose(i: number, t: number) {
    const hub = this.hubs[this.beatStage[i]!]!, a = this.beatAng[i]!, age = Math.max(0, t - this.beatT0[i]!);
    const dur = Math.max(1, (this.beatT0[i + 1] ?? this.beatT0[i]! + 4) - this.beatT0[i]!), k = clamp(age / dur);
    return { hub, ang: a + 0.015 * k * (i % 2 ? 1 : -1), r: RC - 1.1 * ease.inOutQuad(k), lift: 0 };
  }

  camAt(t: number) {
    const i = this.beatAt(t), cur = this.pose(i, t);
    if (i > 0) {
      const prev = this.pose(i - 1, this.beatT0[i]!), stageJump = this.beatStage[i] !== this.beatStage[i - 1];
      const dur = stageJump ? 1.15 : 0.6, k = clamp((t - this.beatT0[i]!) / dur);
      if (k < 1) {
        const e = ease.inOutCubic(k);
        let da = cur.ang - prev.ang; da = Math.atan2(Math.sin(da), Math.cos(da));
        return { hub: prev.hub.clone().lerp(cur.hub, e), ang: prev.ang + da * e, r: prev.r + (cur.r - prev.r) * e + (stageJump ? 5 * Math.sin(Math.PI * e) : 0.6 * Math.sin(Math.PI * e)), lift: stageJump ? 3.2 * Math.sin(Math.PI * e) : 0 };
      }
    }
    return cur;
  }

  bg(t: number) {
    const i = this.beatAt(t), k = i > 0 && this.beatLight[i] !== this.beatLight[i - 1] ? ease.inOutCubic(clamp((t - this.beatT0[i]!) / 0.7)) : 1;
    const to = this.beatLight[i] ? LIGHT_BG : DARK_BG, from = i > 0 ? (this.beatLight[i - 1] ? LIGHT_BG : DARK_BG) : to;
    return from.clone().lerp(to, k);
  }

  panelPos(i: number) {
    const hub = this.hubs[this.beatStage[i]!]!, a = this.beatAng[i]!;
    return { pos: v3(hub.x - Math.sin(a) * RP, 3.45, hub.z - Math.cos(a) * RP), yaw: a };
  }

  makePanel(i: number, ph: number) {
    const cw = 1080, chpx = Math.round((1080 * ph) / PW);
    const canvas = document.createElement('canvas'); canvas.width = cw; canvas.height = chpx;
    const tex = new THREE.CanvasTexture(canvas); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 8;
    const g = new THREE.Group();
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(PW, ph), new THREE.MeshBasicMaterial({ map: tex, transparent: true, toneMapped: false }));
    mesh.position.z = 0.051;
    const slab = rbox(PW + 0.06, ph + 0.06, 0.1, 0.08, phys(this.beatLight[i] ? '#FFFFFF' : '#15181F'));
    g.add(slab, mesh);
    const { pos, yaw } = this.panelPos(i);
    g.position.copy(pos); g.rotation.y = yaw; g.scale.setScalar(0.001);
    this.scene.add(g);
    return (this.panels[i] = { mesh, slab, g, canvas, ctx: canvas.getContext('2d')!, tex, ph, drawnFinal: false });
  }

  update(t: number) {
    const bg = this.bg(t);
    for (let i = 0; i <= this.beatAt(t); i++) this.paint(i, t);
    this.updateSwarm(t);
    (this.ground.material as THREE.MeshStandardMaterial).color.copy(bg).multiplyScalar(0.96);
    (this.scene.fog as THREE.Fog).color.copy(bg);
    const st = this.stageAt(t);
    this.heroes.forEach((h, s) => {
      const age = t - this.stageT0[s]!;
      h.scale.setScalar(Math.max(0.001, age < 0 ? 0.001 : 0.82 * ease.outBack(clamp(age / 0.6))));
      const spin = age > 0 ? Math.PI * 2 * ease.outCubic(clamp(age / 1.4)) : 0;
      h.rotation.y = spin + 0.35 * Math.sin(t * 0.45 + s);
      h.position.y = 0.05 * Math.sin(t * 1.4 + s);
      if (h.userData.spin) h.userData.spin.rotation.y = t * 0.5;
      if (h.userData.gear) h.userData.gear.rotation.z = t * 0.8;
      if (h.userData.shackle) h.userData.shackle.position.y = 1.35 + (s === st ? 0.18 * Math.max(0, Math.sin(t * 1.2)) : 0);
      h.traverse((o: any) => {
        if (o.userData.wave !== undefined) o.scale.setScalar(1 + 0.12 * Math.sin(t * 4 - o.userData.wave));
        if (o.userData.blink !== undefined) o.visible = Math.sin(t * 7 + o.userData.blink * 2.1) > -0.4;
      });
    });
    const sl = this.curve.getLength(), stageU = (s: number) => (this.hubs.length > 1 ? s / (this.hubs.length - 1) : 0);
    const bi = this.beatAt(t), jumpK = bi > 0 && this.beatStage[bi] !== this.beatStage[bi - 1] ? ease.inOutCubic(clamp((t - this.beatT0[bi]!) / 1.15)) : 1;
    const u = stageU(Math.max(0, st - 1)) + (stageU(st) - stageU(Math.max(0, st - 1))) * (st > 0 ? jumpK : 1);
    const m = new THREE.Matrix4();
    for (let k = 0; k < 160; k++) {                                   // live data flowing along the cable, up to the token
      const f = (k / 160 + (t * 4.0) / sl) % 1, uu = f * clamp(u + 0.02, 0.02, 1);
      const p = this.curve.getPointAt(uu); m.makeTranslation(p.x, 0.12, p.z); this.flow.setMatrixAt(k, m);
    }
    this.flow.instanceMatrix.needsUpdate = true;
    const c = this.camAt(t), hub = c.hub;
    this.cam.position.set(hub.x + Math.sin(c.ang) * c.r, 3.6 + c.lift, hub.z + Math.cos(c.ang) * c.r);
    this.cam.position.x += Math.sin(t * 0.7) * 0.06; this.cam.position.y += Math.sin(t * 0.9 + 1) * 0.05;   // handheld breath
    this.cam.lookAt(hub.x, 2.6 + c.lift * 0.3, hub.z);
    this.cam.updateMatrixWorld();
    const tp = this.curve.getPointAt(clamp(u, 0, 1));                 // the running example floats over the current hub
    this.token.position.set(tp.x + Math.sin(c.ang) * 2.4, 0.3 + 0.05 * Math.sin(t * 2), tp.z + Math.cos(c.ang) * 2.4);
    this.token.scale.setScalar(0.62);
    this.token.quaternion.copy(this.cam.quaternion);
    this.sun.position.set(hub.x + 6, 14, hub.z + 8); this.sun.target.position.copy(hub);
    {
      const b = this.beatAt(t), k = clamp((t - this.beatT0[b]! - 0.1) / 0.75), from = this.hubs[this.beatStage[b]!]!.clone().setY(2.1), to = this.panelPos(b).pos;
      this.packet.visible = k > 0 && k < 1 && !!this.panels[b];
      if (this.packet.visible) { this.packet.position.copy(from).lerp(to, ease.inOutQuad(k)); this.packet.position.y += Math.sin(Math.PI * k) * 1.1; }
    }
    this.panels.forEach((p, i) => {
      if (!p) return;
      const age = t - this.beatT0[i]!, end = (this.beatT0[i + 1] ?? 1e9) - this.beatT0[i]!, gone = ease.inOutCubic(clamp((age - end) / 0.8));
      const { pos, yaw } = this.panelPos(i), back = v3(-Math.sin(yaw), 0, -Math.cos(yaw)).multiplyScalar(4.5 * gone);
      p.g.position.copy(pos).add(back); p.g.position.y += 1.4 * gone;
      const near = p.g.position.distanceTo(this.cam.position) < hub.distanceTo(this.cam.position) - 1 ? 0 : 1;
      p.g.userData.vis = (p.g.userData.vis ?? near) + (near - (p.g.userData.vis ?? near)) * 0.25;
      const sc = age < 0 ? 0 : ease.outBack(clamp((age - 0.15) / 0.45)) * (1 - 0.3 * gone) * p.g.userData.vis;
      p.g.scale.setScalar(Math.max(0.001, sc));
    });
    return bg;
  }
}

let WORLD: World | null = null, WORLD_KEY: any = null;
const IMGS = new Map<string, HTMLImageElement>();

export class WorldPlate extends Story {
  override async init() {
    const base = (import.meta as any).env?.BASE_URL ?? '/';
    const want = (this.ctx.lyrics.scenes ?? []).map((s: any) => s?.data?.widget?.img).filter((x: any) => x && !IMGS.has(x));
    await Promise.all(want.map(async (src: string) => IMGS.set(src, await loadImg(`${base}${src}`))));   // every beat's real page/photo, up front
    super.init();
  }
  override build() {
    super.build();
    const tint = this.ctx.lyrics.scenes?.[0]?.data?.tint;
    if (tint) this.style.tintHex = tint;
    this.has3D = false;
    this.noCard = true;
    if (WORLD_KEY !== this.ctx.lyrics) { WORLD = new World(this.ctx.renderer, this.ctx.lyrics, this.style.tintHex, IMGS); WORLD_KEY = this.ctx.lyrics; }
  }

  override drawUI(ctx: CanvasRenderingContext2D, t: number, c: any) {
    const lightBg = !!WORLD && WORLD.bg(t).getHSL({ h: 0, s: 0, l: 0 }).l > 0.5;
    this.capInk = lightBg ? '#12151C' : '#FFFFFF';
    const gr = ctx.createLinearGradient(0, 0, 0, 470);                      // soft top fade so captions read over the world
    gr.addColorStop(0, lightBg ? 'rgba(236,238,242,0.92)' : 'rgba(11,13,18,0.9)'); gr.addColorStop(1, lightBg ? 'rgba(236,238,242,0)' : 'rgba(11,13,18,0)');
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = gr; ctx.fillRect(0, 0, W, 470);
    super.drawUI(ctx, t, c);
  }

  override render(f: Frame, out: T.WebGLRenderTarget): PostOverrides {
    const { renderer, comp } = this.ctx, t = f.t, Wd = WORLD!;
    const bg = Wd.update(t);
    renderer.setRenderTarget(out);
    renderer.setClearColor(bg, 1);
    renderer.clear(true, true, true);
    renderer.render(Wd.scene, Wd.cam);
    const i = this.idx, g = (Wd.scenes[i]?.data?.gesture ?? 'idle') as Gesture, pg = (Wd.scenes[i - 1]?.data?.gesture ?? 'idle') as Gesture;
    void g; void pg;                                                         // no presenter: the objects carry the story
    const U = this.ui; U.clear();
    this.drawUI(U.ctx, t, { cx: 0, cy: 0, z: 1, roll: 0 });
    comp.draw(renderer, U.upload(), out);
    const age = t - this.t0;
    return { bloom: 0.12, bloomThreshold: 1.5, vignette: 0.22, grain: 0.03, zoom: 1 + 0.012 * Math.exp(-age * 9) };
  }
}
