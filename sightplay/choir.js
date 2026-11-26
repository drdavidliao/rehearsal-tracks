// The choir sings its printed parts during a run (from level 6, wherever choir staves are printed), with a few
// mistakes; if asked, half of each section following the leaders by ear, late and unevenly; and, if asked, a couple of
// sections rushing in a runaway spiral, vamping to get back.
// choirPlan is pure (tests check it); singPlan turns a plan into Web Audio voices.
import { rng } from './theory.js';

export const LEAD_JITTER = 15; // ms either side of the beat: leaders read and watch
export const DRAG = { mean: 70, sd: 30, min: 20, max: 160 }; // ms late: followers react to what they hear
export const MISTAKE_KINDS = ['wrong', 'hang', 'early', 'flat'];

// The choir's lines from top to bottom, with section names. Empty if nothing on the page is a choir.
export function choirLines(ex) {
  const lines = [];
  if (ex.texture === 'V') ex.staves.filter((st) => st.group === 'choir').forEach((st) => st.voices.forEach((v) => lines.push(v.notes)));
  else if (ex.texture === 'L4') ex.staves.forEach((st) => lines.push(st.voices[0].notes));
  const names = ex.figures && ex.figures.choir === 'TTBB' ? ['T1', 'T2', 'Bar', 'B'] : ['S', 'A', 'T', 'B'];
  return lines.map((notes, i) => ({ section: names[i], notes }));
}

const gauss = (r) => Math.sqrt(-2 * Math.log(1 - r())) * Math.cos(2 * Math.PI * r());

// Rushing (an option): a couple of sections, the busiest, rush. Each beat they get further ahead, and the further ahead
// they are the faster they go (they hear they are off, get anxious, and push harder). When they are about RUSH.vampAt
// of a beat ahead they notice, vamp on their note until the music catches up, come back in on the beat, and start
// rushing again.
export const RUSH = { base: 20, panic: 0.35, vampAt: 0.6 }; // ms ahead added per beat; extra per beat per ms ahead

// Sung times (ms) of one rushing line: [{ k, t, dur, vamp? }], and the beats where they came back in.
export function rushLine(line, beatMs, r) {
  const out = []; const backAt = []; let off = 0;
  line.forEach((n, k) => {
    const w = n.start * beatMs; const wEnd = (n.start + n.dur) * beatMs;
    const s0 = w + off;
    off -= (RUSH.base + RUSH.panic * -off) * n.dur * (0.8 + 0.4 * r());
    out.push({ k, t: s0, dur: wEnd + off - s0 });
    if (-off > RUSH.vampAt * beatMs && k < line.length - 1) {
      // vamp: the same note again, a beat at a time, until the written music reaches them
      for (let t = wEnd + off; t < wEnd - 1; t += beatMs) out.push({ k, t, dur: Math.min(beatMs, wEnd - t), vamp: true });
      backAt.push(n.start + n.dur);
      off = 0;
    }
  });
  return { out, backAt };
}

// The busiest lines (most notes per beat, repeated notes counting extra): the "doo doo" parts that run away.
function busiest(sung, n) {
  const score = sung.map((line, li) => [li, line.length + line.filter((x, k) => k && x.midi === line[k - 1].midi).length]);
  return score.sort((a, b) => b[1] - a[1]).slice(0, n).map(([li]) => li).sort();
}

// Every sung note: { section, group: 'lead' | 'follow', k, midi, t (ms after beat 1 of bar 1), dur (ms), cents, sag (cents
// by the end, negative = flat), mistake?, vamp? }. Plus the mistakes (one section each, never two at once) and the
// rushing sections with where they vamped.
export function choirPlan(ex, beatMs, { drag = false, rush = false, mistakes = true } = {}, seed = ex.seed + 17) {
  const r = rng(seed);
  const lines = choirLines(ex);
  if (!lines.length) return { events: [], mistakes: [], rushing: [] };
  // sung pitches: the choir sings from its own copies, so a misprint in yours is sung correctly
  const sung = lines.map((ln) => ln.notes.map((n) => ({ start: n.start, dur: n.dur, midi: n.misprint && ex.misprint ? ex.misprint.from : n.midis[0], mp: !!n.misprint })));
  const rushers = rush ? busiest(sung, 2) : [];
  // mistakes: about one every three bars, not in the first bar, none overlapping, not in a rushing section
  const plan = [];
  if (mistakes && rushers.length < sung.length) {
    const want = Math.max(1, Math.round(ex.nBars / 3));
    const busy = [];
    for (let tries = 0; plan.length < want && tries < 300; tries++) {
      const li = Math.floor(r() * sung.length); const line = sung[li];
      if (rushers.includes(li) || line.length < 2) continue;
      const k = 1 + Math.floor(r() * (line.length - 1));
      const n = line[k]; const prev = line[k - 1];
      if (n.start < ex.beats || n.mp || (ex.misprint && Math.abs(n.start - ex.misprint.start) < 1)) continue; // one surprise at a time
      const kind = r.pick(MISTAKE_KINDS);
      let m = null;
      if (kind === 'wrong') m = { kind, li, k, from: n.start, to: n.start + n.dur, midi: n.midi + (r() < 0.5 ? 1 : -1) };
      else if (kind === 'hang' && prev.midi !== n.midi && n.dur >= 1) m = { kind, li, k, from: n.start, to: n.start + 0.5, midi: prev.midi };
      else if (kind === 'early' && prev.dur >= 2 && prev.midi !== n.midi) m = { kind, li, k, from: n.start - 1, to: n.start, midi: n.midi };
      else if (kind === 'flat' && n.dur >= 2) m = { kind, li, k, from: n.start, to: n.start + n.dur, sag: -35 };
      if (!m || busy.some(([a, b]) => m.from < b + 1 && m.to > a - 1)) continue;
      busy.push([m.from, m.to]);
      plan.push({ ...m, section: lines[li].section });
    }
  }
  const events = [];
  // one sung piece as each singer group sings it; times in ms
  const emit = (section, k, midi, t, dur, extra = {}) => {
    events.push({ section, group: 'lead', k, midi, t: t + LEAD_JITTER * (2 * r() - 1), dur, cents: 6 * (2 * r() - 1), sag: 0, ...extra });
    if (drag) {
      const late = Math.min(DRAG.max, Math.max(DRAG.min, DRAG.mean + DRAG.sd * gauss(r)));
      events.push({ section, group: 'follow', k, midi, t: t + late, dur, cents: 12 * (2 * r() - 1), sag: 0, ...extra });
    } else {
      // a second, on-time singer, so a section is not a single pure voice
      events.push({ section, group: 'lead', k, midi, t: t + LEAD_JITTER * (2 * r() - 1), dur, cents: 8 * (2 * r() - 1), sag: 0, ...extra });
    }
  };
  const rushing = [];
  sung.forEach((line, li) => {
    const section = lines[li].section;
    if (rushers.includes(li)) {
      const { out, backAt } = rushLine(line, beatMs, r);
      out.forEach((p) => emit(section, p.k, line[p.k].midi, p.t, p.dur, p.vamp ? { vamp: true } : {}));
      rushing.push({ section, backAt });
      return;
    }
    line.forEach((n, k) => {
      const m = plan.find((x) => x.li === li && x.k === k);
      // mistakes are the whole section's (the followers copy the leaders)
      let pieces = [{ start: n.start, dur: n.dur, midi: n.midi }];
      if (m && m.kind === 'wrong') pieces = [{ ...pieces[0], midi: m.midi, mistake: 'wrong' }];
      if (m && m.kind === 'hang') pieces = [{ start: n.start, dur: 0.5, midi: m.midi, mistake: 'hang' }, { start: n.start + 0.5, dur: n.dur - 0.5, midi: n.midi }];
      if (m && m.kind === 'flat') pieces = [{ ...pieces[0], sag: m.sag, mistake: 'flat' }];
      if (m && m.kind === 'early') {
        // they leave the long note a beat before it ends and sing this one a beat early
        events.filter((e) => e.section === section && e.k === k - 1).forEach((e) => { e.dur -= beatMs; });
        pieces = [{ start: n.start - 1, dur: n.dur + 1, midi: n.midi, mistake: 'early' }];
      }
      for (const p of pieces) {
        const extra = {}; if (p.mistake) extra.mistake = p.mistake; if (p.sag) extra.sag = p.sag;
        emit(section, k, p.midi, p.start * beatMs, p.dur * beatMs, extra);
      }
    });
  });
  events.forEach((e) => { if (e.t < 0) { e.dur += e.t; e.t = 0; } }); // nobody sings in the count-in
  return {
    events: events.sort((a, b) => a.t - b.t),
    mistakes: plan.map(({ kind, section, from, to }) => ({ kind, section, from, to })),
    rushing,
  };
}

// ---------- sound ----------
// An "ah" from a sawtooth through three formant filters (female or male formants by section), soft attack, vibrato.
const FORMANTS = { high: [[800, 1], [1150, 0.5], [2900, 0.2]], low: [[650, 1], [1080, 0.45], [2650, 0.15]] };
const HIGH = new Set(['S', 'A']);

// Schedule one sung note. at: AudioContext time. Returns the oscillators (to stop them early).
export function sing(a, dest, e, at, level = 1) {
  const f = 440 * 2 ** ((e.midi - 69) / 12);
  const durS = Math.max(0.08, e.dur / 1000);
  const o = a.createOscillator(); o.type = 'sawtooth'; o.frequency.setValueAtTime(f, at); o.detune.setValueAtTime(e.cents, at);
  if (e.sag) o.detune.linearRampToValueAtTime(e.cents + e.sag, at + durS);
  const lfo = a.createOscillator(); lfo.frequency.value = 5 + Math.random();
  const lg = a.createGain(); lg.gain.setValueAtTime(0, at); lg.gain.linearRampToValueAtTime(f * 0.005, at + Math.min(0.35, durS));
  lfo.connect(lg).connect(o.frequency);
  const env = a.createGain();
  const peak = 0.035 * level;
  env.gain.setValueAtTime(0.0001, at); env.gain.exponentialRampToValueAtTime(peak, at + 0.07);
  env.gain.setValueAtTime(peak, at + Math.max(0.07, durS - 0.06)); env.gain.exponentialRampToValueAtTime(0.0001, at + durS + 0.12);
  for (const [fc, g] of FORMANTS[HIGH.has(e.section) ? 'high' : 'low']) {
    const bp = a.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = fc; bp.Q.value = 6;
    const bg = a.createGain(); bg.gain.value = g * 3;
    o.connect(bp).connect(bg).connect(env);
  }
  env.connect(dest);
  o.start(at); lfo.start(at); o.stop(at + durS + 0.15); lfo.stop(at + durS + 0.15);
  return [o, lfo];
}
