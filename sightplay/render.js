// Draws an exercise with VexFlow (global Vex from the CDN) and returns where each bar, beat and note landed.
// aids: { grey: colour for harmless notes or null, tint: bool (landmine chord tones), outline: opacity 0..1 }
import { vfKey } from './theory.js';

const DUR = { 4: 'w', 3: 'hd', 2: 'h', 1.5: 'qd', 1: 'q', 0.5: '8' };
// Ink per page theme. grey[1] is faint (close to the paper), grey[2] nearly ink.
export const PALETTE = {
  light: { ink: '#1d1d1f', grey: { 1: '#a8a8ac', 2: '#5c5c60' }, tint: '#c77700' },
  dark: { ink: '#e4e4e7', grey: { 1: '#68686e', 2: '#a8a8ae' }, tint: '#f2a43a' },
};
export const MARK_ROOM = 26; // px below a bar's yBottom that its marks need

// Name of a three-note close-position shape, from its staff steps.
function shapeName(spells) {
  const st = spells.map((s) => s.letter + 7 * s.octave).sort((a, b) => a - b);
  const d = [st[1] - st[0], st[2] - st[1]];
  if (d[0] === 2 && d[1] === 2) return (st[0] - 30) % 2 === 0 ? 'lines' : 'spaces'; // E4 (step 30) is the treble's bottom line
  if (d[0] === 2 && d[1] === 3) return 'gap on top';
  if (d[0] === 3 && d[1] === 2) return 'gap below';
  return '';
}

export function render(container, ex, aids = {}, theme = 'light') {
  const P = PALETTE[theme];
  const greyCol = aids.grey ? P.grey[aids.grey] : null;
  const VF = window.Vex.Flow;
  container.innerHTML = '';
  const width = Math.max(600, container.clientWidth - 4); // on-screen px
  // Four staves are drawn at 78% with wider gaps, so two lines still fit the screen under the conductor; everything returned is in screen px.
  const sc = ex.staves.length >= 4 ? 0.78 : 1;
  const W = width / sc; // drawing units
  const barsPerSystem = 4;
  const nStaves = ex.staves.length;
  const staffGap = nStaves === 2 ? 95 : 74;
  // staff tops inside a system; a little more room where the piano part starts
  // (choir to piano a little wider than inside each group)
  const staffY = []; ex.staves.forEach((st, k) => {
    const gap = k === 0 ? 0 : !st.group ? staffGap : st.group !== ex.staves[k - 1].group ? 82 : 70;
    staffY.push(k === 0 ? 0 : staffY[k - 1] + gap);
  });
  const sysHeight = staffY[nStaves - 1] + (nStaves === 2 ? 130 : 122);
  const groups = []; // [first, last] staff index of each bracket/brace group
  ex.staves.forEach((st, k) => { if (k && st.group && st.group === ex.staves[k - 1].group) groups[groups.length - 1][1] = k; else groups.push([k, k]); });
  const nSys = Math.ceil(ex.nBars / barsPerSystem);
  const holder = document.createElement('div');
  container.appendChild(holder);
  const renderer = new VF.Renderer(holder, VF.Renderer.Backends.SVG);
  renderer.resize(width, (nSys * sysHeight + 10) * sc);
  const ctx = renderer.getContext();
  ctx.setFillStyle(P.ink); ctx.setStrokeStyle(P.ink);
  if (sc !== 1) ctx.scale(sc, sc);
  const left = ex.staves.some((s) => s.label) ? (ex.staves.some((s) => (s.label || '').length > 2) ? 50 : 28) : 12;
  const bars = [];
  const systems = [];
  const notes = []; // {staff, start (beats), x, yTop, yBottom, nct, landmine, misprint, shape}

  for (let sys = 0; sys < nSys; sys++) {
    const y0 = 34 + sys * sysHeight;
    const first = sys * barsPerSystem;
    const n = Math.min(barsPerSystem, ex.nBars - first);
    const extra = sys === 0 ? 120 : 95;
    const barW = (W - left - 12 - extra) / barsPerSystem;
    let firstStaves = null;
    let lastStaves = null;
    for (let j = 0; j < n; j++) {
      const bar = first + j;
      const x = left + (j === 0 ? 0 : extra + j * barW);
      const w = j === 0 ? extra + barW : barW;
      const staves = ex.staves.map((st, k) => {
        const s = new VF.Stave(x, y0 + staffY[k], w);
        if (j === 0) {
          if (st.clef === 'treble8') s.addClef('treble', 'default', '8vb');
          else s.addClef(st.clef);
          s.addKeySignature(ex.key.vf);
          if (sys === 0) s.addTimeSignature(`${ex.beats}/4`);
        }
        return s;
      });
      const startX = Math.max(...staves.map((s) => s.getNoteStartX()));
      staves.forEach((s) => { s.setNoteStartX(startX); s.setContext(ctx).draw(); });

      const fmt = new VF.Formatter();
      const allVoices = [];
      const drawList = [];
      const beams = [];
      const beatPts = [];
      ex.staves.forEach((st, k) => {
        const vfVoices = st.voices.map((v) => {
          const src = v.notes.filter((nt) => nt.start >= bar * ex.beats && nt.start < (bar + 1) * ex.beats);
          const vfNotes = src.map((nt) => {
            if (nt.rest) {
              const rn = new VF.StaveNote({ keys: [st.clef === 'bass' ? 'd/3' : 'b/4'], duration: DUR[nt.dur] + 'r', clef: st.clef === 'bass' ? 'bass' : 'treble' });
              rn.setStyle({ fillStyle: P.ink, strokeStyle: P.ink });
              rn.__src = nt; rn.__staff = k; rn.__rest = true;
              return rn;
            }
            const keys = nt.spells.map((sp) => vfKey(st.clef === 'treble8' ? { ...sp, octave: sp.octave + 1 } : sp));
            const opts = { keys, duration: DUR[nt.dur], clef: st.clef === 'bass' ? 'bass' : 'treble' };
            if (v.stem) opts.stem_direction = v.stem; else opts.auto_stem = true;
            const sn = new VF.StaveNote(opts);
            if (nt.dur === 3 || nt.dur === 1.5) VF.Dot.buildAndAttach([sn], { all: true });
            if (nt.nct && greyCol) sn.setStyle({ fillStyle: greyCol, strokeStyle: greyCol });
            else sn.setStyle({ fillStyle: P.ink, strokeStyle: P.ink });
            if (aids.tint) nt.landmine.forEach((lm, i) => { if (lm) sn.setKeyStyle(i, { fillStyle: P.tint, strokeStyle: P.tint }); });
            sn.__src = nt; sn.__staff = k; sn.__hand = v.hand;
            return sn;
          });
          const voice = new VF.Voice({ num_beats: ex.beats, beat_value: 4 }).setMode(VF.Voice.Mode.SOFT);
          voice.addTickables(vfNotes);
          beams.push(...VF.Beam.generateBeams(vfNotes, v.stem ? { maintain_stem_directions: true } : {}));
          return { voice, vfNotes };
        });
        VF.Accidental.applyAccidentals(vfVoices.map((x) => x.voice), ex.key.vf);
        fmt.joinVoices(vfVoices.map((x) => x.voice));
        vfVoices.forEach((x) => { allVoices.push(x.voice); drawList.push([x, staves[k]]); });
      });
      fmt.format(allVoices, staves[0].getNoteEndX() - startX - 12);
      drawList.forEach(([x, s]) => {
        x.voice.draw(ctx, s);
        x.vfNotes.forEach((sn) => {
          const nt = sn.__src;
          const ax = sn.getAbsoluteX();
          beatPts.push([nt.start - bar * ex.beats, ax]);
          if (sn.__rest) return;
          const ys = sn.getYs();
          notes.push({
            staff: sn.__staff, start: nt.start, x: ax, yTop: Math.min(...ys), yBottom: Math.max(...ys),
            nct: !!nt.nct, misprint: !!nt.misprint, landmine: nt.landmine, el: sn.getSVGElement && sn.getSVGElement(),
            shape: sn.__hand === 'right' && nt.midis.length === 3 ? shapeName(nt.spells) : '',
          });
        });
      });
      beams.forEach((b) => b.setContext(ctx).draw());

      const conn = (a, b, type) => new VF.StaveConnector(staves[a], staves[b]).setType(VF.StaveConnector.type[type]).setContext(ctx).draw();
      if (ex.staves.some((st) => st.group)) { // choir and piano: barlines per group, a bracket and a brace
        groups.forEach(([a, b]) => { if (b > a) conn(a, b, 'SINGLE_RIGHT'); });
        if (j === 0) {
          conn(0, nStaves - 1, 'SINGLE_LEFT');
          groups.forEach(([a, b]) => { if (b > a) conn(a, b, ex.staves[a].group === 'piano' ? 'BRACE' : 'BRACKET'); });
        }
      } else if (nStaves > 1) {
        conn(0, nStaves - 1, 'SINGLE_RIGHT');
        if (j === 0) {
          conn(0, nStaves - 1, 'SINGLE_LEFT');
          conn(0, nStaves - 1, nStaves === 2 ? 'BRACE' : 'BRACKET');
        }
      }
      if (j === 0 && left > 12) {
        ex.staves.forEach((st, k) => { ctx.save(); ctx.setFont('Arial', 13, 'bold'); ctx.fillText(st.label || '', 2, staves[k].getYForLine(2) + 5); ctx.restore(); });
      }

      const m = new Map();
      beatPts.forEach(([b, xx]) => { if (!m.has(b) || xx < m.get(b)) m.set(b, xx); });
      bars.push({
        bar, sys, x0: x, x1: x + w, noteX0: startX, pts: [...m.entries()].sort((a, b) => a[0] - b[0]),
        yTop: staves[0].getYForLine(0) - 36, yBottom: staves[nStaves - 1].getYForLine(4) + 32,
      });
      if (j === 0) firstStaves = staves;
      lastStaves = staves;
    }
    systems.push({ top: firstStaves[0].getYForLine(0) - 40, bottom: lastStaves[nStaves - 1].getYForLine(4) + 46 });
  }
  // tall enough for the marks under the last system (they sit just below each bar's yBottom)
  if (sc !== 1) {
    const k = (v) => v * sc;
    bars.forEach((b) => { b.x0 = k(b.x0); b.x1 = k(b.x1); b.noteX0 = k(b.noteX0); b.yTop = k(b.yTop); b.yBottom = k(b.yBottom); b.pts = b.pts.map(([bt, xx]) => [bt, k(xx)]); });
    systems.forEach((y) => { y.top = k(y.top); y.bottom = k(y.bottom); });
    notes.forEach((n) => { n.x = k(n.x); n.yTop = k(n.yTop); n.yBottom = k(n.yBottom); });
  }
  const height = Math.ceil(Math.max((nSys * sysHeight + 10) * sc, ...bars.map((b) => b.yBottom + MARK_ROOM)));
  renderer.resize(width, height);
  // VexFlow's resize re-applies the scale to the scaled viewBox; set it directly
  holder.querySelector('svg').setAttribute('viewBox', `0 0 ${width / sc} ${height / sc}`);
  return { bars, systems, notes, width, height };
}

// x of a beat inside a bar (beats from the bar's start), interpolated between notes.
export function beatX(barLayout, beat, beats) {
  const pts = [[0, barLayout.noteX0], ...barLayout.pts.filter(([b]) => b > 0), [beats, barLayout.x1]];
  for (let i = 0; i < pts.length - 1; i++) {
    const [b0, x0] = pts[i]; const [b1, x1] = pts[i + 1];
    if (beat >= b0 && beat <= b1) return x0 + ((beat - b0) / (b1 - b0 || 1)) * (x1 - x0);
  }
  return barLayout.x1;
}

// One chord on one treble staff, for the flash drill.
export function renderChord(container, keyVf, spells, theme = 'light') {
  const VF = window.Vex.Flow;
  container.innerHTML = '';
  const holder = document.createElement('div');
  container.appendChild(holder);
  const renderer = new VF.Renderer(holder, VF.Renderer.Backends.SVG);
  renderer.resize(260, 150);
  const ctx = renderer.getContext();
  ctx.setFillStyle(PALETTE[theme].ink); ctx.setStrokeStyle(PALETTE[theme].ink);
  const s = new VF.Stave(10, 30, 230).addClef('treble').addKeySignature(keyVf);
  s.setContext(ctx).draw();
  const sn = new VF.StaveNote({ keys: spells.map(vfKey), duration: 'w' });
  sn.setStyle({ fillStyle: PALETTE[theme].ink, strokeStyle: PALETTE[theme].ink });
  const voice = new VF.Voice({ num_beats: 4, beat_value: 4 }).setMode(VF.Voice.Mode.SOFT).addTickables([sn]);
  VF.Accidental.applyAccidentals([voice], keyVf);
  new VF.Formatter().joinVoices([voice]).format([voice], 120);
  voice.draw(ctx, s);
}
