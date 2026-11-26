// Generates an exercise: a phrase-structured progression, a four-part voicing with real voice-leading, then a texture.
import {
  KEYS, makeChord, vocab, mod, spellMidi, spellChordTone, degree, chordName, romanLabel, rng,
} from './theory.js';

// ---------- progression ----------

const TRANS = {
  major: {
    I: { IV: 3, ii: 2, V: 2.5, V7: 1, vi: 3, iii: 0.4, 'V/V': 0.6, 'V/vi': 0.4 },
    ii: { V: 3, V7: 3, 'vii°': 0.7, 'V/V': 0.4 },
    iii: { vi: 2, IV: 2 },
    IV: { V: 3, V7: 2, ii: 1.5, I: 1.5, 'vii°': 0.5, 'V/V': 0.6 },
    V: { I: 4, vi: 1.5 },
    V7: { I: 4, vi: 1.2 },
    vi: { ii: 2.5, IV: 2.5, V: 0.8, iii: 0.4, 'V/V': 0.5 },
    'vii°': { I: 3 },
    'V/V': { V: 4, V7: 3 },
    'V/vi': { vi: 4 },
  },
  minor: {
    i: { iv: 3, 'ii°': 1.5, V: 2.5, V7: 1, VI: 2.5, III: 0.6, VII: 0.8, 'V/V': 0.4 },
    'ii°': { V: 3, V7: 3 },
    III: { VI: 2, iv: 2 },
    iv: { V: 3, V7: 2, 'ii°': 1, i: 1.2, 'vii°': 0.5 },
    V: { i: 4, VI: 1.5 },
    V7: { i: 4, VI: 1.2 },
    VI: { 'ii°': 2, iv: 2.5, V: 1, III: 0.3 },
    VII: { III: 4 },
    'vii°': { i: 3 },
    'V/V': { V: 4, V7: 3 },
  },
};
const CHROMATIC = new Set(['V/V', 'V/vi']);

// Harmonic-rhythm patterns per bar (beats), by density.
const PATTERNS = {
  4: {
    slow: [[[4], 4], [[2, 2], 1]],
    medium: [[[4], 2], [[2, 2], 3], [[2, 1, 1], 0.6], [[1, 1, 2], 0.6]],
    fast: [[[2, 2], 3], [[2, 1, 1], 1.5], [[1, 1, 2], 1.5], [[1, 1, 1, 1], 1]],
    one: [[[4], 1]],
    some2: [[[4], 3], [[2, 2], 1]],
  },
  3: {
    slow: [[[3], 4], [[2, 1], 1]],
    medium: [[[3], 2], [[2, 1], 2], [[1, 2], 0.6]],
    fast: [[[2, 1], 2], [[1, 2], 1], [[1, 1, 1], 1.5]],
    one: [[[3], 1]],
    some2: [[[3], 3], [[2, 1], 1]],
  },
};

function pickPattern(r, beats, density) {
  const list = PATTERNS[beats][density];
  const idx = r.weighted(Object.fromEntries(list.map(([, w], i) => [i, w])));
  return list[+idx][0];
}

function makeSlots(r, nBars, beats, density) {
  const slots = [];
  const phrases = [];
  for (let bar = 0; bar < nBars; bar++) {
    const endOfPhrase = bar % 4 === 3;
    const pat = endOfPhrase ? [beats] : pickPattern(r, beats, density);
    let b = 0;
    for (const d of pat) { slots.push({ start: bar * beats + b, dur: d, bar }); b += d; }
    if (endOfPhrase) phrases.push(slots.length);
  }
  return { slots, phrases };
}

function progression(r, key, slots, phrases, chromatic, only) {
  const tonic = key.mode === 'major' ? 'I' : 'i';
  const allowed = (c) => (chromatic || !CHROMATIC.has(c)) && (!only || only.has(c));
  // the transition table restricted to allowed chords
  const trans = Object.fromEntries(Object.entries(TRANS[key.mode]).map(([k, row]) => [k, Object.fromEntries(Object.entries(row).filter(([c]) => allowed(c)))]));
  // two back: discourage A-B-A-B ping-pong between the same two chords
  const step = (prev, before) => {
    const opts = Object.fromEntries(Object.entries(trans[prev]).map(([c, w]) => [c, c === before ? w * 0.25 : w]));
    return r.weighted(opts);
  };
  const romans = [];
  let from = 0;
  phrases.forEach((end, pi) => {
    const authentic = pi % 2 === 1 || pi === phrases.length - 1;
    for (let tries = 0; ; tries++) {
      if (tries > 2000) throw new Error('progression: no cadence found');
      const seq = [];
      let prev = romans.length ? romans[romans.length - 1] : null;
      let before = romans.length > 1 ? romans[romans.length - 2] : null;
      const nFree = end - from - (authentic ? 2 : 1);
      if (nFree < 0) continue;
      let ok = true;
      for (let i = 0; i < nFree; i++) {
        const c = prev === null ? tonic : step(prev, before);
        seq.push(c); before = prev; prev = c;
      }
      if (authentic) {
        const d = r() < 0.5 ? 'V' : 'V7';
        if (prev !== null && !(trans[prev][d] > 0)) {
          const alt = d === 'V' ? 'V7' : 'V';
          if (!(trans[prev][alt] > 0)) ok = false; else seq.push(alt);
        } else seq.push(d);
        seq.push(tonic);
      } else {
        if (prev !== null && !(trans[prev].V > 0)) ok = false;
        seq.push('V');
      }
      if (ok) { romans.push(...seq); break; }
    }
    from = end;
  });
  return romans;
}

// ---------- voicing ----------

const RANGE = { S: [60, 79], A: [55, 74], T: [48, 67], B: [40, 60] };
// Men's chorus: tenor 1, tenor 2, baritone, bass in the S A T B slots (sounding pitch).
const RANGE_TTBB = { S: [55, 69], A: [50, 66], T: [45, 62], B: [38, 55] };
// Comfortable limits inside each range: [top voice high, top voice low, third voice high, bass low]
const RANGES = { SATB: RANGE, TTBB: RANGE_TTBB };
const SOFT = { SATB: [76, 63, 65, 43], TTBB: [67, 57, 60, 41] };
const pitchesOf = (pc, [lo, hi]) => {
  const out = [];
  for (let m = lo; m <= hi; m++) if (mod(m, 12) === pc) out.push(m);
  return out;
};

// Pitch class a dominant-type chord's leading tone resolves from (null if not dominant-type)
function leadingTone(chord) {
  if (chord.roman.startsWith('vii')) return chord.root.pc;
  if (chord.fn === 'D' || chord.secondary) return chord.tones[1].pc; // third of V / V7 / V/x
  return null;
}
const seventhPc = (chord) => (chord.q === 'dom7' ? chord.tones[3].pc : null);

function candidates(chord, key, r, inversions = true, RANGE = RANGES.SATB, soft = SOFT.SATB) {
  const out = [];
  const lt = leadingTone(chord);
  const roleOf = (pc) => chord.tones.find((t) => t.pc === pc).role;
  const pcs = [...chord.pcs];
  for (const [role, invCost] of inversions ? Object.entries(chord.inv) : [['R', 0]]) {
    const bassPc = chord.tones.find((t) => t.role === role).pc;
    for (const b of pitchesOf(bassPc, RANGE.B)) {
      for (const tp of pcs) for (const t of pitchesOf(tp, RANGE.T)) {
        if (t <= b || t - b > 24) continue;
        for (const ap of pcs) for (const a of pitchesOf(ap, RANGE.A)) {
          if (a <= t || a - t > 12) continue;
          for (const sp of pcs) for (const s of pitchesOf(sp, RANGE.S)) {
            if (s <= a || s - a > 12) continue;
            const v = [b, t, a, s];
            const count = {};
            v.forEach((m) => { const pc = mod(m, 12); count[pc] = (count[pc] || 0) + 1; });
            const roles = {};
            Object.entries(count).forEach(([pc, n]) => { roles[roleOf(+pc)] = n; });
            let cost = invCost;
            if (chord.q === 'dom7') {
              if (!roles.R || !roles['3'] || !roles['7']) continue;
              if (roles['7'] > 1 || roles['3'] > 1) continue;
              if (!roles['5']) cost += 0.6;
            } else {
              if (!roles.R || !roles['3'] || !roles['5']) continue;
              if (roles['3'] > 1) cost += chord.q === 'maj' ? 3 : chord.q === 'dim' ? -0.5 : 0.6;
              if (roles['5'] > 1) cost += chord.q === 'dim' ? 4 : 1;
              if (roles.R > 1 && chord.q === 'dim') cost += 2;
            }
            if (lt !== null && count[lt] > 1) continue;
            if (s > soft[0]) cost += s - soft[0];
            if (s < soft[1]) cost += (soft[1] - s) * 0.5;
            if (t > soft[2]) cost += t - soft[2];
            if (b < soft[3]) cost += (soft[3] - b) * 0.5;
            cost += r() * 2;
            out.push({ v, role, cost });
          }
        }
      }
    }
  }
  return out;
}

function transCost(p, c, pc, cc) {
  const [pb, pt, pa, ps] = p.v;
  const [cb, ct, ca, cs] = c.v;
  let cost = 0;
  const d = [cb - pb, ct - pt, ca - pa, cs - ps];
  cost += Math.abs(d[1]) + Math.abs(d[2]) + Math.abs(d[3]) + 0.5 * Math.abs(d[0]);
  if (Math.abs(d[3]) > 4) cost += (Math.abs(d[3]) - 4) * 1.5;
  for (const i of [1, 2]) if (Math.abs(d[i]) > 5) cost += Math.abs(d[i]) - 5;
  if (Math.abs(d[0]) > 9) cost += (Math.abs(d[0]) - 9) * 0.5;
  // parallel perfect intervals
  for (let i = 0; i < 4; i++) for (let j = i + 1; j < 4; j++) {
    const ip = mod(p.v[j] - p.v[i], 12);
    const ic = mod(c.v[j] - c.v[i], 12);
    if (ip === ic && (ip === 0 || ip === 7) && d[i] !== 0 && d[j] !== 0) {
      if (Math.sign(d[i]) === Math.sign(d[j])) return Infinity;
      if (i === 0 && j === 3) cost += 10;
    }
  }
  // hidden octaves / fifths in outer voices with a soprano leap
  const outer = mod(cs - cb, 12);
  if ((outer === 0 || outer === 7) && Math.sign(d[0]) === Math.sign(d[3]) && d[0] !== 0 && Math.abs(d[3]) > 2) cost += 4;
  // overlap
  if (ct > pa || ca < pt) cost += 3;
  if (ca > ps || cs < pa) cost += 3;
  if (ct < pb) cost += 3;
  // leading tone and seventh resolution
  const lt = leadingTone(pc);
  if (lt !== null && cc.pcs.has(mod(lt + 1, 12))) {
    for (const i of [1, 2, 3]) {
      if (mod(p.v[i], 12) === lt && d[i] !== 1) cost += i === 3 ? 4 : 1.5;
    }
  }
  const sev = seventhPc(pc);
  if (sev !== null) {
    for (const i of [1, 2, 3]) {
      if (mod(p.v[i], 12) === sev && !(d[i] === -1 || d[i] === -2)) cost += cc.pcs.has(sev) && d[i] === 0 ? 1 : 5;
    }
  }
  return cost;
}

function voice(chords, key, r, inversions = true, choir = 'SATB') {
  const cand = (ch) => candidates(ch, key, r, inversions, RANGES[choir], SOFT[choir]);
  const BEAM = 150;
  let layer = cand(chords[0]).map((c) => ({ ...c, total: c.cost, back: null }));
  layer.sort((a, b) => a.total - b.total);
  layer = layer.slice(0, BEAM);
  const layers = [layer];
  for (let i = 1; i < chords.length; i++) {
    const cands = cand(chords[i]);
    const next = [];
    for (const c of cands) {
      let best = Infinity; let back = null;
      for (const p of layer) {
        const t = p.total + transCost(p, c, chords[i - 1], chords[i]);
        if (t < best) { best = t; back = p; }
      }
      if (best < Infinity) next.push({ ...c, total: best + c.cost, back });
    }
    if (!next.length) throw new Error(`voicing: dead end at chord ${i} ${chords[i].roman}`);
    next.sort((a, b) => a.total - b.total);
    layer = next.slice(0, BEAM);
    layers.push(layer);
  }
  const out = [];
  for (let n = layer[0]; n; n = n.back) out.unshift(n);
  return out;
}

// ---------- textures ----------

const SPLIT = { 4: [[3, 1]], 3: [[2, 1]], 2: [[1, 1], [1.5, 0.5]], 1: [[0.5, 0.5]] };

const chordNote = (chord, start, dur, midis) => ({
  start, dur, midis, spells: midis.map((m) => spellChordTone(chord, m)),
});

// Diatonic pitch for a letter between/next to chord tones; returns {midi, spell} or null.
function stepNote(key, fromMidi, fromLetter, dir, toMidi) {
  const letter = mod(fromLetter + dir, 7);
  let pc = null;
  for (let d = 0; d < 7; d++) { const x = degree(key, d); if (x.letter === letter) pc = x.pc; }
  const tryPc = (cand) => {
    const st = mod(dir * (cand - mod(fromMidi, 12)), 12);
    if (st !== 1 && st !== 2) return null;
    const m = fromMidi + dir * st;
    if (toMidi !== undefined) {
      const st2 = (toMidi - m) * (toMidi === fromMidi ? -dir : dir);
      if (toMidi !== fromMidi && st2 !== 1 && st2 !== 2) return null;
      if (toMidi === fromMidi && st2 !== 1 && st2 !== 2) return null;
    }
    const sp = spellMidi(m, letter);
    if (Math.abs(sp.acc) > 1) return null;
    return { midi: m, spell: sp };
  };
  return tryPc(pc) || tryPc(mod(pc + 1, 12)) || tryPc(mod(pc - 1, 12));
}

function blockVoices(slots, chords, voicing) {
  return [0, 1, 2, 3].map((vi) => slots.map((s, i) => chordNote(chords[i], s.start, s.dur, [voicing[i].v[vi]])));
}

// Restrike some slots homorhythmically, then add passing and neighbour tones.
function addMotion(key, voices, slots, r, opts = {}) {
  const { pNct = 0.35, pRestrike = 0.25, maxPerSlot = 2, ranges = RANGE } = opts;
  // restrike: same pitches, split rhythm, all voices together
  const restrike = slots.map((s, i) => i < slots.length - 1 && s.dur >= 2 && r() < pRestrike);
  voices = voices.map((v) => v.flatMap((n, i) => {
    if (!restrike[i]) return [n];
    const parts = n.dur === 4 ? [2, 2] : n.dur === 3 ? [2, 1] : [1, 1];
    let t = n.start;
    return parts.map((d) => { const x = { ...n, start: t, dur: d }; t += d; return x; });
  }));
  // NCTs: on the last note before a chord change in each voice
  const slotEnds = new Set(slots.map((s) => s.start + s.dur));
  const nctAt = {}; // time -> [{voice, midi}]
  const order = [3, 0, 1, 2]; // soprano and bass first
  const out = voices.map((v) => v.slice());
  for (const vi of order) {
    const v = out[vi];
    const res = [];
    for (let i = 0; i < v.length; i++) {
      const n = v[i]; const nx = v[i + 1];
      if (!nx || !slotEnds.has(n.start + n.dur) || r() > pNct) { res.push(n); continue; }
      const a = n.midis[0]; const b = nx.midis[0];
      const gap = b - a;
      const choices = SPLIT[n.dur];
      if (!choices) { res.push(n); continue; }
      const [d1, d2] = r.pick(choices);
      const t2 = n.start + d1;
      let nct = null;
      if (Math.abs(gap) === 3 || Math.abs(gap) === 4) {
        const dir = Math.sign(gap);
        if (mod(n.spells[0].letter + 2 * dir, 7) === nx.spells[0].letter) nct = stepNote(key, a, n.spells[0].letter, dir, b);
      } else if (gap === 0 && vi !== 0 && r() < 0.5) {
        nct = stepNote(key, a, n.spells[0].letter, r() < 0.6 ? 1 : -1, b);
      }
      const others = nctAt[t2] || [];
      if (nct && others.length < maxPerSlot && others.every((o) => ![0, 7].includes(mod(Math.abs(o.midi - nct.midi), 12)))) {
        const [lo, hi] = ranges['BTAS'[vi]];
        if (nct.midi >= lo && nct.midi <= hi) {
          (nctAt[t2] = nctAt[t2] || []).push({ voice: vi, midi: nct.midi });
          res.push({ ...n, dur: d1 });
          res.push({ start: t2, dur: d2, midis: [nct.midi], spells: [nct.spell], nct: true });
          continue;
        }
      }
      res.push(n);
    }
    out[vi] = res;
  }
  return out;
}

// LH accompaniment figures from the bass and the chord.
function lhFigure(kind, slots, chords, voicing, beats) {
  const notes = [];
  slots.forEach((s, i) => {
    const ch = chords[i];
    const b = voicing[i].v[0] >= 50 ? voicing[i].v[0] - 12 : voicing[i].v[0]; // keep figures low
    const above = (m, min) => { for (let x = m + min; x < m + min + 12; x++) if (ch.pcs.has(mod(x, 12))) return x; return null; };
    const x = above(b, 5);
    let y = above(x, 3); // no seconds in the chord
    if (y > 64) y = x;
    if (kind === 'arp') {
      const pat = [b, x, y, x];
      for (let k = 0; k < s.dur * 2; k++) notes.push(chordNote(ch, s.start + k * 0.5, 0.5, [pat[k % 4]]));
    } else { // oompah
      notes.push(chordNote(ch, s.start, 1, [b]));
      for (let k = 1; k < s.dur; k++) notes.push(chordNote(ch, s.start + k, 1, x === y ? [x] : [x, y]));
    }
  });
  return notes;
}

// Printed as played: left hand the root alone, right hand the triad in close position, moving as little as possible.
function printedAsPlayed(slots, chords, r) {
  const lh = []; const rh = []; let prevR = null; let prevL = 48;
  slots.forEach((s, i) => {
    const ch = chords[i];
    const pcs = ch.tones.slice(0, 3).map((t) => t.pc);
    let best = null;
    for (let bottom = 57; bottom <= 67; bottom++) {
      if (!pcs.includes(mod(bottom, 12))) continue;
      const notes = [bottom];
      for (let m = bottom + 1; notes.length < 3 && m < bottom + 12; m++) {
        if (pcs.includes(mod(m, 12)) && !notes.some((x) => mod(x, 12) === mod(m, 12))) notes.push(m);
      }
      if (notes.length < 3) continue;
      const cost = (prevR ? notes.reduce((a, m, k) => a + Math.abs(m - prevR[k]), 0) : Math.abs(notes[1] - 66)) + r() * 0.5;
      if (!best || cost < best.cost) best = { notes, cost };
    }
    prevR = best.notes;
    const roots = []; for (let m = 41; m <= 55; m++) if (mod(m, 12) === ch.root.pc) roots.push(m);
    const root = roots.reduce((a, b) => (Math.abs(b - prevL) < Math.abs(a - prevL) ? b : a));
    prevL = root;
    lh.push(chordNote(ch, s.start, s.dur, [root]));
    rh.push(chordNote(ch, s.start, s.dur, best.notes));
  });
  return { lh, rh };
}

// ---------- voices over piano (DESIGN.md 3a) ----------

const rest = (start, dur) => ({ start, dur, midis: [], spells: [], rest: true });
const cloneNote = (n, shift = 0) => ({
  ...n, midis: n.midis.map((m) => m + shift), spells: n.spells.map((sp) => ({ ...sp, octave: sp.octave + shift / 12 })),
});

// Right-hand chord per slot: three chord notes in close position (the 7th for the 5th on a dominant 7th), bottom note
// in lo..hi, moving as little as possible.
function rhChords(slots, chords, r, lo = 60, hi = 68) {
  let prev = null;
  return slots.map((s, i) => {
    const ch = chords[i];
    const roles = ch.q === 'dom7' ? ['R', '3', '7'] : ['R', '3', '5'];
    const pcs = roles.map((ro) => ch.tones.find((t) => t.role === ro).pc);
    let best = null;
    for (let bottom = lo; bottom <= hi; bottom++) {
      if (!pcs.includes(mod(bottom, 12))) continue;
      const notes = [bottom];
      for (let m = bottom + 1; notes.length < 3 && m < bottom + 12; m++) {
        if (pcs.includes(mod(m, 12)) && !notes.some((x) => mod(x, 12) === mod(m, 12))) notes.push(m);
      }
      if (notes.length < 3) continue;
      const cost = (prev ? notes.reduce((a, m, k) => a + Math.abs(m - prev[k]), 0) : Math.abs(notes[1] - 67)) + r() * 0.5;
      if (!best || cost < best.cost) best = { notes, cost };
    }
    prev = best.notes;
    return best.notes;
  });
}

// Split a slot into notes of these lengths (beats), cycling through `pick(k)` for the pitches; null pitches are rests.
function figure(ch, s, lens, pickAt) {
  const out = []; let t = s.start; let k = 0;
  while (t < s.start + s.dur - 1e-9) {
    const d = Math.min(lens[k % lens.length], s.start + s.dur - t);
    const ms = pickAt(k, t - s.start);
    out.push(ms ? chordNote(ch, t, d, ms) : rest(t, d));
    t += d; k++;
  }
  return out;
}

const RH_FIGURES = { 1: ['pulse', 'broken'], 2: ['arp', 'afterbeat', 'melody'], 3: ['pop'] };
const LH_FIGURES = { 1: ['held', 'octaves'], 2: ['oompah', 'arp'], 3: ['reduction', 'line'] };
const upTo = (table, lvl) => Object.entries(table).filter(([k]) => +k <= lvl).flatMap(([, v]) => v);

// Returns { rh: [voices], lh: [voices], rhKind, lhKind }. m: the choir's lines with motion; block: without.
function pianoPart(level, slots, chords, voicing, m, block, choir, r) {
  const rhKind = r.pick(upTo(RH_FIGURES, level));
  const lhKind = r.pick(upTo(LH_FIGURES, level));
  const tri = rhChords(slots, chords, r);
  let rh;
  if (rhKind === 'melody') {
    const up = choir === 'TTBB' ? 12 : 0; // a tenor tune doubled an octave up
    rh = [
      { stem: 1, notes: m[3].map((n) => cloneNote(n, up)) },
      { stem: -1, notes: block[2].map((n) => cloneNote(n, up)) },
    ];
  } else {
    const notes = slots.flatMap((s, i) => {
      const ch = chords[i]; const [a, b, c] = tri[i];
      switch (rhKind) {
        case 'pulse': return figure(ch, s, [1], () => [a, b, c]);
        case 'broken': return figure(ch, s, [0.5], (k) => [[a], [c], [b], [c]][k % 4]);
        case 'arp': return figure(ch, s, [0.5], (k) => [[a], [b], [c], [a + 12], [c], [b]][k % 6]);
        case 'afterbeat': return figure(ch, s, [0.5], (k) => (k % 2 ? [a, b, c] : null));
        case 'pop': return figure(ch, s, s.dur >= 3 ? [1.5, 1.5, 1] : s.dur === 2 ? [1.5, 0.5] : [1], () => [a, b, c]);
        default: throw new Error(rhKind);
      }
    });
    rh = [{ stem: 0, notes }];
  }
  // left hand: its bass is the choir's bass note, in octave 40..55
  const lowBass = (i) => { let b = voicing[i].v[0]; while (b > 55) b -= 12; while (b < 40) b += 12; return b; };
  let lh;
  if (lhKind === 'line') lh = m[0].map((n) => cloneNote(n));
  else if (lhKind === 'oompah' || lhKind === 'arp') lh = lhFigure(lhKind, slots, chords, voicing);
  else {
    lh = slots.flatMap((s, i) => {
      const ch = chords[i]; const b = lowBass(i);
      if (lhKind === 'held') return [chordNote(ch, s.start, s.dur, [b])];
      if (lhKind === 'octaves') {
        let lo = b; while (lo > 47) lo -= 12; while (lo < 36) lo += 12; const hi = lo + 12;
        return figure(ch, s, s.dur === 4 ? [2] : [s.dur], () => [lo, hi]);
      }
      // reduction: bass octave and two chord notes above (three above if no octave below fits), held
      const lo = b - 12 >= 36 ? b - 12 : null;
      // open spacing, as an orchestral reduction prints it: at least a third between notes, the first a fourth up
      const above = []; let last = b;
      for (let x = b + 5; x <= 64 && above.length < (lo ? 2 : 3); x++) if (ch.pcs.has(mod(x, 12)) && !above.some((y) => mod(y - x, 12) === 0) && x - last >= 3) { above.push(x); last = x; }
      return [chordNote(ch, s.start, s.dur, [...(lo ? [lo] : []), b, ...above])];
    });
  }
  return { rh, lh: [{ stem: 0, notes: lh }], rhKind, lhKind };
}

// One inner-voice chord tone at one change becomes a note a half step away, outside the chord.
function applyMisprint(m, slots, chords, r) {
  for (let tries = 0; tries < 50; tries++) {
    const i = 1 + Math.floor(r() * (slots.length - 2));
    const vi = r() < 0.5 ? 1 : 2; // tenor or alto
    const k = m[vi].findIndex((n) => n.start === slots[i].start);
    if (k < 0) continue;
    const n = m[vi][k];
    const from = n.midis[0];
    for (const d of r() < 0.5 ? [1, -1] : [-1, 1]) {
      const to = from + d;
      if (chords[i].pcs.has(mod(to, 12))) continue;
      const same = spellMidi(to, n.spells[0].letter);
      const spell = Math.abs(same.acc) <= 1 ? same : spellMidi(to, mod(n.spells[0].letter + d, 7));
      if (Math.abs(spell.acc) > 1) continue;
      m[vi][k] = { ...n, midis: [to], spells: [spell], misprint: true };
      return { change: i, start: slots[i].start, voice: vi === 1 ? 'tenor' : 'alto', from, to, spell, printedAs: n.spells[0] };
    }
  }
  return null;
}

export const TEXTURES = {
  P: 'Printed as you play',
  L1: 'Block chords (2 + 2)',
  L2: 'Chorale with moving parts',
  L3: 'Piano accompaniment figures',
  L4: 'SATB open score (4 staves)',
  V: 'Voices over piano',
};

export function generate(opts) {
  const {
    keyName = 'C', beats = 4, nBars = 8, density = 'medium', texture = 'L2', seed = Date.now() & 0x7fffffff,
    chords: only = null, inversions = true, chromatic = texture !== 'L1' && texture !== 'P', misprint = false,
    piano = 3, choir: choirOpt = null,
  } = opts;
  const key = KEYS[keyName];
  const r = rng(seed);
  const { slots, phrases } = makeSlots(r, nBars, beats, density);
  const romans = progression(r, key, slots, phrases, chromatic, only ? new Set(only) : null);
  const chords = romans.map((x) => makeChord(key, x));
  const choir = texture === 'V' ? (choirOpt || (r() < 0.5 ? 'SATB' : 'TTBB')) : 'SATB';
  const voicing = voice(chords, key, r, inversions, choir);
  const harmony = slots.map((s, i) => ({
    start: s.start, dur: s.dur, bar: s.bar, chord: chords[i], bassRole: voicing[i].role,
    name: chordName(chords[i], voicing[i].role), roman: romanLabel(chords[i], voicing[i].role),
    voicing: voicing[i].v,
  }));
  const block = blockVoices(slots, chords, voicing);
  let staves;
  let mp = null;
  let figures = null;
  if (texture === 'P') {
    const { lh, rh } = printedAsPlayed(slots, chords, r);
    harmony.forEach((h, i) => { h.voicing = [lh[i].midis[0], ...rh[i].midis]; h.bassRole = 'R'; h.name = chordName(h.chord, 'R'); h.roman = romanLabel(h.chord, 'R'); });
    staves = [
      { clef: 'treble', voices: [{ stem: 0, notes: rh, hand: 'right' }] },
      { clef: 'bass', voices: [{ stem: 0, notes: lh, hand: 'left' }] },
    ];
  } else if (texture === 'L1' || texture === 'L2' || texture === 'L4') {
    const m = texture === 'L1' ? block.map((v) => v.slice()) : addMotion(key, block, slots, r);
    if (misprint) mp = applyMisprint(m, slots, chords, r);
    staves = texture === 'L4'
      ? [
        { clef: 'treble', label: 'S', voices: [{ stem: 0, notes: m[3] }] },
        { clef: 'treble', label: 'A', voices: [{ stem: 0, notes: m[2] }] },
        { clef: 'treble8', label: 'T', voices: [{ stem: 0, notes: m[1] }] },
        { clef: 'bass', label: 'B', voices: [{ stem: 0, notes: m[0] }] },
      ]
      : [
        { clef: 'treble', voices: [{ stem: 1, notes: m[3] }, { stem: -1, notes: m[2] }] },
        { clef: 'bass', voices: [{ stem: 1, notes: m[1] }, { stem: -1, notes: m[0] }] },
      ];
  } else if (texture === 'V') {
    const m = addMotion(key, block, slots, r, { ranges: RANGES[choir] });
    const p = pianoPart(piano, slots, chords, voicing, m, block, choir, r);
    const satb = choir === 'SATB';
    staves = [
      { clef: satb ? 'treble' : 'treble8', label: satb ? 'S A' : 'T', group: 'choir', voices: [{ stem: 1, notes: m[3] }, { stem: -1, notes: m[2] }] },
      { clef: 'bass', label: satb ? 'T B' : 'B', group: 'choir', voices: [{ stem: 1, notes: m[1] }, { stem: -1, notes: m[0] }] },
      { clef: 'treble', label: 'Pno', group: 'piano', voices: p.rh },
      { clef: 'bass', label: '', group: 'piano', voices: p.lh },
    ];
    figures = { choir, rh: p.rhKind, lh: p.lhKind, piano };
  } else { // L3
    const m = addMotion(key, block, slots, r, { pRestrike: 0, maxPerSlot: 1 });
    const kind = r() < 0.5 ? 'arp' : 'oompah';
    staves = [
      { clef: 'treble', voices: [{ stem: 1, notes: m[3] }, { stem: -1, notes: block[2] }] },
      { clef: 'bass', voices: [{ stem: 0, notes: lhFigure(kind, slots, chords, voicing, beats) }] },
    ];
  }
  // landmines: chord tones outside the key signature (natural minor in minor keys)
  const scale = new Set([0, 1, 2, 3, 4, 5, 6].map((d) => degree(key, d).pc));
  staves.forEach((st) => st.voices.forEach((v) => v.notes.forEach((n) => {
    n.landmine = n.midis.map((x) => !n.nct && !n.misprint && !scale.has(mod(x, 12)));
  })));
  return { keyName, key, beats, nBars, texture, seed, harmony, staves, misprint: mp, figures };
}
