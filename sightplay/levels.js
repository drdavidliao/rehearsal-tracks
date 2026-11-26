// The ladder (DESIGN.md section 4) and how a run's score moves you along it.

// The keys a sample of current choral scores start in (31 songs, 2026-11-18): together 96% of their bars.
export const MAJ = ['C', 'G', 'D', 'A', 'E', 'F', 'Bb', 'Eb'];
const MIN = ['Am', 'Em', 'Bm', 'F#m', 'C#m', 'Dm', 'Gm', 'Cm'];
const IIV = ['I', 'IV', 'V'];
const MAJ_DIA = ['I', 'ii', 'iii', 'IV', 'V', 'V7', 'vi', 'vii°'];
const MIN_DIA = ['i', 'ii°', 'III', 'iv', 'V', 'V7', 'VI', 'VII', 'vii°'];

const base = {
  keys: ['C'], chords: IIV, inversions: false, textures: ['P'], density: 'one', meters: [4], hide: 'off', hand: 'left',
  chromatic: false, misprint: false, piano: 1,
};
const steps = [
  { turns: 'start', hand: 'left' },
  { turns: 'right hand', hand: 'right' },
  { turns: 'both hands', hand: 'both' },
  { turns: 'keys', keys: ['C', 'G', 'D', 'F'] },
  { turns: 'chords', chords: [...IIV, 'vi', 'ii'] },
  { turns: 'texture', textures: ['V'], piano: 1 },
  { turns: 'changes', chords: [...IIV, 'vi', 'ii', 'V7'], density: 'some2' },
  { turns: 'bass, keys, piano', piano: 2, keys: MAJ, chords: [...IIV, 'vi', 'ii', 'V7', 'vii°'], inversions: true },
  { turns: 'keys, meter', keys: [...MAJ, ...MIN], chords: [...MAJ_DIA, ...MIN_DIA], meters: [4, 3] },
  { turns: 'piano, chords', piano: 3, chords: [...MAJ_DIA, ...MIN_DIA, 'V/V', 'V/vi'], textures: ['V', 'V', 'V', 'L4'], density: 'medium', chromatic: true, misprint: true },
  { turns: 'reading ahead', hide: 'half' },
  { turns: 'reading ahead', hide: 'bar' },
];

export const LEVELS = [];
steps.reduce((prev, s, i) => {
  const lv = { ...prev, ...s, n: i + 1 };
  LEVELS.push(lv);
  return lv;
}, base);

// Aids per level (DESIGN.md 4, 6). highlight is decided per run (alternating).
export function aidsFor(n) {
  return {
    outline: n <= 3 ? 1 : n <= 5 ? 0.4 : 0,
    grey: n === 9 ? 1 : n === 10 ? 2 : null, // 1: faint, 2: nearly ink (colours per theme in render.js PALETTE)
    tint: n === 9 || n === 10,
  };
}

export const HAND_TEXT = { left: 'left hand: the root', right: 'right hand: two or more chord tones', both: 'left hand the root, right hand two chord tones' };

export const TEMPO = { min: 40, max: 72, step: 6 };

export const newProgress = () => ({ level: 1, bpm: TEMPO.min, low: 0, runsAtLevel: 0, offerDown: false, seenDemo: {} });

// Pure: the progress after a ladder run with this score (0..1). Returns [progress, message].
export function advance(p, score) {
  const q = { ...p, runsAtLevel: p.runsAtLevel + 1, offerDown: false };
  let msg;
  if (score >= 0.85) {
    q.low = 0;
    if (p.bpm >= TEMPO.max) {
      if (p.level < LEVELS.length) { q.level = p.level + 1; q.bpm = TEMPO.min; q.runsAtLevel = 0; msg = `Level ${q.level} unlocked.`; }
      else msg = 'Top level, top tempo.';
    } else { q.bpm = Math.min(TEMPO.max, p.bpm + TEMPO.step); msg = `Tempo up to ♩ = ${q.bpm}.`; }
  } else if (score < 0.6) {
    if (p.bpm <= TEMPO.min) {
      q.low = p.low + 1;
      q.offerDown = q.low >= 2 && p.level > 1;
      msg = q.offerDown ? `This level is fighting back. Level ${p.level - 1} is there if you want it.` : 'Same tempo again.';
    } else { q.bpm = Math.max(TEMPO.min, p.bpm - TEMPO.step); q.low = 0; msg = `Tempo down to ♩ = ${q.bpm}.`; }
  } else { q.low = 0; msg = `Same tempo again: 85% moves it up.`; }
  return [q, msg];
}

export const misprintRun = (lv, p) => lv.misprint && p.runsAtLevel % 3 === 2;
