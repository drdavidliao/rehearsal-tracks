// Keys, spelling and chords. Pitches are MIDI numbers; a spelled note is {letter 0-6 (C..B), acc -2..2, octave}.

export const LETTERS = ['C', 'D', 'E', 'F', 'G', 'A', 'B'];
export const LETTER_PC = [0, 2, 4, 5, 7, 9, 11];
const MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11];
const MINOR_STEPS = [0, 2, 3, 5, 7, 8, 10]; // natural minor; V and vii° raise the 7th

// vf: VexFlow key-signature name.
export const KEYS = {
  C: { tonicLetter: 0, tonicPc: 0, mode: 'major', vf: 'C', name: 'C major' },
  G: { tonicLetter: 4, tonicPc: 7, mode: 'major', vf: 'G', name: 'G major' },
  D: { tonicLetter: 1, tonicPc: 2, mode: 'major', vf: 'D', name: 'D major' },
  A: { tonicLetter: 5, tonicPc: 9, mode: 'major', vf: 'A', name: 'A major' },
  E: { tonicLetter: 2, tonicPc: 4, mode: 'major', vf: 'E', name: 'E major' },
  F: { tonicLetter: 3, tonicPc: 5, mode: 'major', vf: 'F', name: 'F major' },
  Bb: { tonicLetter: 6, tonicPc: 10, mode: 'major', vf: 'Bb', name: 'B♭ major' },
  Eb: { tonicLetter: 2, tonicPc: 3, mode: 'major', vf: 'Eb', name: 'E♭ major' },
  Db: { tonicLetter: 1, tonicPc: 1, mode: 'major', vf: 'Db', name: 'D♭ major' }, // not on the ladder; kept for free play and old history
  Am: { tonicLetter: 5, tonicPc: 9, mode: 'minor', vf: 'Am', name: 'A minor' },
  Em: { tonicLetter: 2, tonicPc: 4, mode: 'minor', vf: 'Em', name: 'E minor' },
  Bm: { tonicLetter: 6, tonicPc: 11, mode: 'minor', vf: 'Bm', name: 'B minor' },
  'F#m': { tonicLetter: 3, tonicPc: 6, mode: 'minor', vf: 'F#m', name: 'F♯ minor' },
  'C#m': { tonicLetter: 0, tonicPc: 1, mode: 'minor', vf: 'C#m', name: 'C♯ minor' },
  Dm: { tonicLetter: 1, tonicPc: 2, mode: 'minor', vf: 'Dm', name: 'D minor' },
  Gm: { tonicLetter: 4, tonicPc: 7, mode: 'minor', vf: 'Gm', name: 'G minor' },
  Cm: { tonicLetter: 0, tonicPc: 0, mode: 'minor', vf: 'Cm', name: 'C minor' },
  Bbm: { tonicLetter: 6, tonicPc: 10, mode: 'minor', vf: 'Bbm', name: 'B♭ minor' }, // not on the ladder
};

export const mod = (a, n) => ((a % n) + n) % n;

// Accidental needed to give `letter` the pitch class `pc` (-2..2 for anything we generate).
export function accFor(pc, letter) {
  return mod(pc - LETTER_PC[letter] + 6, 12) - 6;
}

export function spellMidi(midi, letter) {
  const acc = accFor(mod(midi, 12), letter);
  const octave = (midi - acc - LETTER_PC[letter]) / 12 - 1;
  return { letter, acc, octave };
}

export function spelledToMidi(s) {
  return 12 * (s.octave + 1) + LETTER_PC[s.letter] + s.acc;
}

const ACC_TEXT = { '-2': '𝄫', '-1': '♭', 0: '', 1: '♯', 2: '𝄪' };
const ACC_VF = { '-2': 'bb', '-1': 'b', 0: '', 1: '#', 2: '##' };
export const nameOf = (letter, acc) => LETTERS[letter] + ACC_TEXT[acc];
export const vfKey = (s) => LETTERS[s.letter].toLowerCase() + ACC_VF[s.acc] + '/' + s.octave;

// Scale degree d (0-6, may be outside: wraps) in key -> {letter, pc}
export function degree(key, d) {
  const steps = key.mode === 'major' ? MAJOR_STEPS : MINOR_STEPS;
  const i = mod(d, 7);
  return { letter: mod(key.tonicLetter + i, 7), pc: mod(key.tonicPc + steps[i], 12) };
}

export const leadingTonePc = (key) => mod(key.tonicPc - 1, 12);

const QUALITY = {
  maj: [0, 4, 7], min: [0, 3, 7], dim: [0, 3, 6], dom7: [0, 4, 7, 10],
};
const ROLE = ['R', '3', '5', '7'];

// Chord vocabulary. deg: root scale degree; q: quality; raise: root raised a half step (minor-key vii°);
// inv: allowed bass roles with a cost (root position is free); fn: T / PD / D.
const VOCAB = {
  major: {
    I: { deg: 0, q: 'maj', fn: 'T', inv: { R: 0, 3: 2.5 } },
    ii: { deg: 1, q: 'min', fn: 'PD', inv: { R: 0, 3: 0.3 } },
    iii: { deg: 2, q: 'min', fn: 'T', inv: { R: 0 } },
    IV: { deg: 3, q: 'maj', fn: 'PD', inv: { R: 0, 3: 2.5 } },
    V: { deg: 4, q: 'maj', fn: 'D', inv: { R: 0, 3: 1.5 } },
    V7: { deg: 4, q: 'dom7', fn: 'D', inv: { R: 0, 3: 2 } },
    vi: { deg: 5, q: 'min', fn: 'T', inv: { R: 0 } },
    'vii°': { deg: 6, q: 'dim', fn: 'D', inv: { 3: 0 } },
    'V/V': { deg: 1, q: 'dom7', fn: 'PD', inv: { R: 0, 3: 1.5 }, secondary: true },
    'V/vi': { deg: 2, q: 'dom7', fn: 'PD', inv: { R: 0, 3: 1.5 }, secondary: true },
  },
  minor: {
    i: { deg: 0, q: 'min', fn: 'T', inv: { R: 0, 3: 2.5 } },
    'ii°': { deg: 1, q: 'dim', fn: 'PD', inv: { 3: 0 } },
    III: { deg: 2, q: 'maj', fn: 'T', inv: { R: 0 } },
    iv: { deg: 3, q: 'min', fn: 'PD', inv: { R: 0, 3: 2.5 } },
    V: { deg: 4, q: 'maj', fn: 'D', inv: { R: 0, 3: 1.5 } },
    V7: { deg: 4, q: 'dom7', fn: 'D', inv: { R: 0, 3: 2 } },
    VI: { deg: 5, q: 'maj', fn: 'T', inv: { R: 0 } },
    VII: { deg: 6, q: 'maj', fn: 'PD', inv: { R: 0 } },
    'vii°': { deg: 6, q: 'dim', fn: 'D', inv: { 3: 0 }, raise: true },
    'V/V': { deg: 1, q: 'dom7', fn: 'PD', inv: { R: 0, 3: 1.5 }, secondary: true },
  },
};
export const vocab = (key) => VOCAB[key.mode];

// Build a chord: {roman, root:{letter,pc}, tones:[{letter,pc,role}], pcs:Set, fn, inv, q}
export function makeChord(key, roman) {
  const v = VOCAB[key.mode][roman];
  if (!v) throw new Error(`no chord ${roman} in ${key.mode}`);
  const r = degree(key, v.deg);
  const rootPc = v.raise ? mod(r.pc + 1, 12) : r.pc;
  const tones = QUALITY[v.q].map((iv, i) => ({
    letter: mod(r.letter + 2 * i, 7), pc: mod(rootPc + iv, 12), role: ROLE[i],
  }));
  return {
    roman, fn: v.fn, q: v.q, inv: v.inv, secondary: !!v.secondary,
    root: { letter: r.letter, pc: rootPc }, tones, pcs: new Set(tones.map((t) => t.pc)),
  };
}

export function chordName(chord, bassRole = 'R') {
  const r = chord.tones[0];
  const acc = accFor(r.pc, r.letter);
  const suffix = { maj: '', min: 'm', dim: '°', dom7: '7' }[chord.q];
  let s = nameOf(r.letter, acc) + suffix;
  if (bassRole !== 'R') {
    const b = chord.tones.find((t) => t.role === bassRole);
    s += '/' + nameOf(b.letter, accFor(b.pc, b.letter));
  }
  return s;
}

export function romanLabel(chord, bassRole = 'R') {
  if (bassRole === 'R') return chord.roman;
  // first inversion figures
  if (chord.q === 'dom7') return chord.roman.replace('7', '65');
  return chord.roman.replace(/^([^/]+)/, (m) => m + '6');
}

// Spell a chord tone pitch by its chord letter.
export function spellChordTone(chord, midi) {
  const t = chord.tones.find((x) => x.pc === mod(midi, 12));
  if (!t) throw new Error(`midi ${midi} not in ${chord.roman}`);
  return spellMidi(midi, t.letter);
}

// Seeded RNG (mulberry32)
export function rng(seed) {
  let a = seed >>> 0;
  const f = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  f.pick = (arr) => arr[Math.floor(f() * arr.length)];
  f.weighted = (obj) => {
    const entries = Object.entries(obj).filter(([, w]) => w > 0);
    const total = entries.reduce((s, [, w]) => s + w, 0);
    let x = f() * total;
    for (const [k, w] of entries) { x -= w; if (x <= 0) return k; }
    return entries[entries.length - 1][0];
  };
  return f;
}
