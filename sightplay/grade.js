// Grades each chord change from MIDI events. Pure: no clock, no DOM.
//
// Each change earns points (see points() below; the page's rubric states the same rules) from the keys struck in the
// on-time window around it, plus keys still held from before. The bass is the lowest key struck in the window, or a
// lower key still held from before if that one is the root. Notes struck after the window, up to a beat after the
// change, earn half. Nothing waits: every change is graded whether or not the player kept up.

import { mod } from './theory.js';


// segments: [{t (ms), dur (ms), pcs:Set, rootPc, bassPc}]; events: [{t, midi, on:boolean}] sorted by t.
export function windows(seg, next, beatMs) {
  const early = Math.min(0.5 * beatMs, 350, seg.dur / 2);
  const late = Math.min(0.5 * beatMs, 400, seg.dur / 2);
  const nextEarly = next ? Math.min(0.5 * beatMs, 350, next.dur / 2) : 0.5 * beatMs;
  const lateEnd = Math.min(seg.t + beatMs, next ? next.t - nextEarly : seg.t + beatMs);
  return { from: seg.t - early, to: seg.t + late, lateEnd: Math.max(lateEnd, seg.t + late) };
}

function heldAt(events, t) {
  const down = new Map();
  for (const e of events) {
    if (e.t > t) break;
    if (e.on) down.set(e.midi, e.t); else down.delete(e.midi);
  }
  return [...down.keys()];
}

function judge(seg, attacks, held) {
  if (!attacks.length) return null;
  const okBass = (m) => mod(m, 12) === seg.rootPc || mod(m, 12) === seg.bassPc;
  const lowestAttack = Math.min(...attacks);
  let bass = lowestAttack;
  if (!okBass(bass)) {
    const heldBass = held.filter((m) => m < lowestAttack && okBass(m));
    if (heldBass.length) bass = Math.min(...heldBass);
  }
  const bassOk = okBass(bass);
  const chordPcs = (ms) => new Set(ms.filter((m) => seg.pcs.has(mod(m, 12))).map((m) => mod(m, 12)));
  const tones = chordPcs([...attacks, ...held].filter((m) => m > bass)).size; // counted by note name
  const tonesAll = chordPcs([...attacks, ...held]).size;
  const wrong = attacks.filter((m) => !seg.pcs.has(mod(m, 12)));
  return { bassOk, tones, tonesAll, wrong: wrong.length, bass };
}

// Points for one change, by hand mode (the rubric on the page states exactly these):
//   both:  +2 lowest struck key is the root (or printed bass); +1 per different chord note above it, up to 2;
//          -1 per struck key outside the chord; never below 0.               max 4
//   left:  +2 lowest struck key is the root (or printed bass).                max 2
//   right: +1 per different chord note sounding, up to 2; -1 per struck key outside the chord; never below 0.  max 2
export const MAX = { both: 4, left: 2, right: 2 };
export function points(j, hand) {
  if (!j) return 0;
  if (hand === 'left') return j.bassOk ? 2 : 0;
  if (hand === 'right') return Math.max(0, Math.min(2, j.tonesAll) - j.wrong);
  return Math.max(0, (j.bassOk ? 2 : 0) + Math.min(2, j.tones) - j.wrong);
}

function why(j, hand) {
  if (!j) return 'nothing played';
  const parts = [];
  if (hand !== 'right') parts.push(j.bassOk ? 'bass right' : 'bass not the root');
  if (hand !== 'left') parts.push(`${Math.min(2, hand === 'right' ? j.tonesAll : j.tones)} of 2 chord notes`);
  if (hand !== 'left' && j.wrong) parts.push(`${j.wrong} wrong note${j.wrong > 1 ? 's' : ''}`);
  return parts.join(', ');
}

// events: [{t, midi, on}] sorted by t, already corrected for latency.
// Returns { result: hit | late | partial | miss, points, max, why, offset, ... }.
// hit: every point on time. late: every point, but only from notes after the window (they count half).
export function gradeSegment(seg, next, events, beatMs, hand = 'both') {
  const max = MAX[hand];
  const w = windows(seg, next, beatMs);
  const onIn = (a, b) => events.filter((e) => e.on && e.t >= a && e.t <= b);
  const inWin = onIn(w.from, w.to);
  const held = heldAt(events, seg.t).filter((m) => !inWin.some((e) => e.midi === m));
  const j = judge(seg, inWin.map((e) => e.midi), held);
  const offsets = inWin.map((e) => e.t - seg.t).sort((a, b) => a - b);
  const median = offsets.length ? offsets[Math.floor(offsets.length / 2)] : null;
  const pOn = points(j, hand);
  if (pOn === max) return { result: 'hit', points: max, max, why: 'on time', offset: median, ...j };
  // late band: struck from the change itself to a beat after (earlier notes may belong to the last chord)
  const lateEv = onIn(seg.t, w.lateEnd);
  const jl = lateEv.some((e) => e.t > w.to) ? judge(seg, lateEv.map((e) => e.midi), heldAt(events, seg.t)) : null;
  const pLate = points(jl, hand) / 2;
  if (pLate > pOn) {
    const off = Math.min(...lateEv.filter((e) => e.t > w.to).map((e) => e.t - seg.t));
    return { result: pLate * 2 === max ? 'late' : 'partial', points: pLate, max, why: `late: ${why(jl, hand)}`, offset: off, ...jl };
  }
  return { result: pOn > 0 ? 'partial' : 'miss', points: pOn, max, why: why(j, hand), offset: median, ...(j || {}) };
}

export function summarize(results, harmony) {
  const n = results.length;
  const score = results.reduce((s, r) => s + r.points, 0) / results.reduce((s, r) => s + r.max, 0);
  const count = (k) => results.filter((r) => r.result === k).length;
  const offs = results.filter((r) => r.result === 'hit' && r.offset !== null).map((r) => r.offset).sort((a, b) => a - b);
  const byChord = {};
  results.forEach((r, i) => {
    const k = harmony[i].roman;
    byChord[k] = byChord[k] || { n: 0, score: 0 };
    byChord[k].n++; byChord[k].score += r.points / r.max;
  });
  const weak = Object.entries(byChord).filter(([, v]) => v.n >= 2 && v.score / v.n < 0.6).map(([k]) => k);
  return {
    n, score, points: results.reduce((s, r) => s + r.points, 0), max: results.reduce((s, r) => s + r.max, 0),
    hit: count('hit'), late: count('late'), partial: count('partial'), miss: count('miss'),
    medianOffset: offs.length ? offs[Math.floor(offs.length / 2)] : null, weak,
  };
}

// Tempo to try next in free play, from this run's score.
export function nextTempo(bpm, score) {
  if (score >= 0.85) return Math.min(160, bpm + 8);
  if (score < 0.6) return Math.max(30, bpm - 8);
  return bpm;
}

// Synthetic performances for tests, ?sim and the demo. Returns events [{t, midi, on}].
// miss: index of a change to skip on purpose.
export function simulate(kind, segs, harmony, beatMs, r = Math.random, miss = -1) {
  const ev = [];
  segs.forEach((s, i) => {
    const h = harmony[i];
    const v = h.voicing; // [B,T,A,S] or, printed as played, [LH root, RH three]
    const rootBass = v[0] - mod(v[0] - h.chord.root.pc, 12);
    const near = (pc, around) => { let best = null; for (let m = around - 6; m <= around + 6; m++) if (mod(m, 12) === pc && (best === null || Math.abs(m - around) < Math.abs(best - around))) best = m; return best; };
    let notes; let dt = 0;
    switch (kind) {
      case 'perfect': notes = v; break;
      case 'roots': { // root in the bass, two different chord tones above it
        const up = [v[1], v[2], v[3]].filter((m, k, a) => a.findIndex((x) => mod(x - m, 12) === 0) === k);
        notes = [rootBass, ...up.slice(-2)]; dt = 20; break;
      }
      case 'leftonly': notes = [rootBass]; break;
      case 'rightonly': notes = [near(h.chord.tones[1].pc, 66), near(h.chord.tones[2].pc, 70)]; break; // third and fifth: no root
      case 'demo-left': notes = [rootBass]; break;
      case 'demo-right': notes = v.slice(1); break;
      case 'demo-both': notes = v; break;
      case 'late': notes = v; dt = Math.min(0.75 * beatMs, s.dur - 10); break;
      case 'bassonly': notes = [v[0]]; break;
      case 'wrongnote': notes = [...v, v[3] + 1]; break;
      case 'nothing': notes = []; break;
      case 'sloppy': {
        const x = r();
        notes = x < 0.7 ? v : x < 0.85 ? [v[0]] : [];
        dt = (r() - 0.5) * 0.6 * beatMs;
        break;
      }
      default: throw new Error(kind);
    }
    if (i === miss) notes = [];
    const t0 = s.t + dt;
    notes.forEach((m, k) => ev.push({ t: t0 + k * 8, midi: m, on: true }));
    notes.forEach((m) => ev.push({ t: Math.max(t0 + 60, s.t + s.dur - 30), midi: m, on: false }));
  });
  return ev.sort((a, b) => a.t - b.t || (a.on ? 1 : -1));
}
