// The conductor, seen over the top of the music: a figure 20 feet away, out of focus because the eye is focused on the
// page 18 inches away, in a dim evening hall. The baton follows the common 2/4, 3/4 and 4/4 patterns, falling into each
// beat point (the ictus) fastest and floating at the top of each rebound.
//
// Blur, worked out (the pupil size is an assumption, not measured):
//   defocus = 1/0.457 m − 1/6.10 m = 2.02 dioptres
//   blur disc ≈ pupil × defocus = 5.5 mm × 2.02 = 11 mrad (0.64°); a dim hall dilates the pupil (4.5–6.5 mm gives 9–13 mrad)
//   one drawing unit is 4.3 mm on the conductor (the 4/4 pattern is about 100 units, 43 cm, wide) = 0.71 mrad at 20 ft
//   so the disc is about 16 units across; a Gaussian with the same spread as a uniform disc has σ = diameter / 4 ≈ 4 units.
export const BLUR_UNITS = 4;

// Patterns as conductors draw them, from the conductor's own side (box 140 × 160, y down; larger x is outward, away
// from the body, for the right hand). ictus[k] is beat k+1; seg[k] holds the two Bézier control points from beat k+1 to
// the next beat. The last beat's segment is the upbeat and the downbeat: { up: [c1, c2], top: y, at } rises from the
// last beat to the top, directly over beat 1, by beat fraction `at`, floats there, and falls straight down into beat 1.
//
// Forearm rule: the hand barely travels outward past the downbeat (swinging the forearm far out is not healthy), so
// nothing goes beyond OUTWARD_MAX, about 22 units (9 cm) out from the 4/4 downbeat. Most of the sideways travel is
// between the downbeat and the end of the next stroke. The outward beat lands at the edge, the hand holds still there
// for a beat (the dwell), and the next beat leaves from the same spot (4/4: 3 and 4; 3/4: 2 and 3). The two ends of a
// dwell are half ictuses: the first only arrives (the hand stops dead on it, no rebound), the second only leaves.
//
// Beat points: 4/4: 1 at the bottom of the downbeat, 2 at the inner end of a horizontal stroke, 3 at
// the outer end of a horizontal stroke, a dwell, 4 at the start of the upbeat. 3/4: 1 at the bottom of the downbeat, 2
// at the outer end of a horizontal stroke, a dwell, 3 at the start of a diagonal upstroke. The downbeat is vertical in
// every pattern.
export const OUTWARD_MAX = 94;
const PATTERNS = {
  2: { ictus: [[66, 128], [84, 112]], seg: [[[68, 100], [80, 96]], { up: [[88, 40], [72, 8]], top: 8, at: 0.5 }] },
  3: {
    ictus: [[58, 128], [92, 126], [92, 126]],
    seg: [[[60, 114], [68, 112]], [[92, 126], [92, 126]], { up: [[83, 94], [60, 15]], top: 8, at: 0.5 }],
  },
  4: {
    ictus: [[72, 128], [26, 124], [92, 126], [92, 126]],
    seg: [[[70, 112], [60, 110]], [[30, 110], [46, 112]], [[92, 126], [92, 126]], { up: [[88, 40], [78, 8]], top: 8, at: 0.5 }],
  },
};
export const patternFor = (beats) => PATTERNS[beats] || PATTERNS[4];

const bez = (p0, p1, p2, p3, u) => {
  const v = 1 - u;
  return [0, 1].map((i) => v * v * v * p0[i] + 3 * v * v * u * p1[i] + 3 * v * u * u * p2[i] + u * u * u * p3[i]);
};

// Baton tip in the pattern box at a time in beats from the first downbeat (negative in the count-in). On the ictus at
// whole beats.
export function batonAt(beats, beat) {
  const P = patternFor(beats); const n = P.ictus.length;
  const k = ((Math.floor(beat) % n) + n) % n;
  const u = beat - Math.floor(beat);
  const S = P.seg[k]; const p0 = P.ictus[k]; const p3 = P.ictus[(k + 1) % n];
  if (Array.isArray(S)) return bez(p0, S[0], S[1], p3, u);
  const top = [p3[0], S.top];
  if (u < S.at) return bez(p0, S.up[0], S.up[1], top, u / S.at);
  return bez(top, top, top, p3, (u - S.at) / (1 - S.at)); // straight down, from rest at the top to fastest at the beat
}

// The same point as you see it, facing the conductor: mirrored (their right hand is on your left; their beat 2 of 4
// goes to your right), placed in front of the body. Figure units: 0,0 mid-chest, y down; shoulders at y −30.
export function seenAt(beats, beat) {
  const [x, y] = batonAt(beats, beat);
  return [-(x - 72) - 22, y - 128 + 40]; // beat points at mid-chest, so the hand stays above the music
}

const NS = 'http://www.w3.org/2000/svg';
const el = (name, attrs, parent) => {
  const e = document.createElementNS(NS, name);
  Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
  if (parent) parent.appendChild(e);
  return e;
};

const C = { wall: '#0b0b0d', glow: '#2b261f', suit: '#141418', shirt: '#7c776e', skin: '#7a6656', cuff: '#a39d92', baton: '#d6d0c4' };
const R_SHOULDER = [-46, -26]; const L_SHOULDER = [46, -26];
const BATON = [24, -40]; // from hand to tip, as seen (points up and across the body)

export function makeConductor(host) {
  let beats = 4;
  host.innerHTML = '';
  const svg = el('svg', { viewBox: '-260 -96 520 186', preserveAspectRatio: 'xMidYMid meet', width: '100%', height: '100%' }, host);
  const defs = el('defs', {}, svg);
  const f = el('filter', { id: 'cond-eye', filterUnits: 'userSpaceOnUse', x: -600, y: -300, width: 1200, height: 600 }, defs);
  el('feGaussianBlur', { stdDeviation: BLUR_UNITS }, f);
  const grad = el('radialGradient', { id: 'cond-glow', gradientUnits: 'userSpaceOnUse', cx: 0, cy: -20, r: 230 }, defs);
  el('stop', { offset: 0, 'stop-color': C.glow }, grad); el('stop', { offset: 1, 'stop-color': C.wall }, grad);
  el('rect', { x: -2000, y: -300, width: 4000, height: 600, fill: C.wall }, svg);
  el('rect', { x: -2000, y: -300, width: 4000, height: 600, fill: 'url(#cond-glow)' }, svg); // a pool of stage light behind the podium
  const g = el('g', { filter: 'url(#cond-eye)' }, svg);
  // body: suit, shirt and collar, neck, head with darker hair
  el('path', { d: 'M-52,-30 Q0,-40 52,-30 L60,40 L50,140 L-50,140 L-60,40 Z', fill: C.suit }, g);
  el('path', { d: 'M-11,-33 L11,-33 L4,10 L-4,10 Z', fill: C.shirt }, g);
  el('rect', { x: -9, y: -46, width: 18, height: 16, fill: C.skin }, g);
  el('ellipse', { cx: 0, cy: -64, rx: 19, ry: 24, fill: C.skin }, g);
  el('path', { d: 'M-20,-66 Q-20,-92 0,-91 Q20,-92 20,-66 Q14,-80 0,-80 Q-14,-80 -20,-66 Z', fill: '#2a2420' }, g);
  // left arm (on your right): resting near the chest
  el('path', { d: `M${L_SHOULDER} Q66,20 30,34`, stroke: C.suit, 'stroke-width': 15, fill: 'none', 'stroke-linecap': 'round' }, g);
  el('ellipse', { cx: 26, cy: 34, rx: 6, ry: 5, fill: C.skin }, g);
  // right arm, hand and baton: moved every frame
  const arm = el('path', { stroke: C.suit, 'stroke-width': 15, fill: 'none', 'stroke-linecap': 'round' }, g);
  const cuff = el('circle', { r: 5, fill: C.cuff }, g);
  const hand = el('ellipse', { rx: 6, ry: 5, fill: C.skin }, g);
  const baton = el('line', { stroke: C.baton, 'stroke-width': 1.6, 'stroke-linecap': 'round' }, g);

  function place([tx, ty]) {
    const hx = tx - BATON[0]; const hy = ty - BATON[1];
    const ex = (R_SHOULDER[0] + hx) / 2 - 18; const ey = (R_SHOULDER[1] + hy) / 2 + 22; // elbow out and down
    arm.setAttribute('d', `M${R_SHOULDER} Q${ex},${ey} ${hx + 3},${hy + 4}`);
    cuff.setAttribute('cx', hx + 4); cuff.setAttribute('cy', hy + 5);
    hand.setAttribute('cx', hx); hand.setAttribute('cy', hy);
    baton.setAttribute('x1', hx); baton.setAttribute('y1', hy); baton.setAttribute('x2', tx); baton.setAttribute('y2', ty);
  }
  // beat: time in beats, or null before the run (baton raised, ready). on: false, the conductor stands with the
  // baton lowered for the whole run (runs without the conductor, for the on/off comparison).
  function draw(beat, on = true) {
    if (!on) place([-30, 70]); // arm lowered, baton resting
    else place(seenAt(beats, beat === null ? -0.5 : beat));
  }
  function setMeter(b) { beats = b; }
  draw(null);
  return { setMeter, draw };
}
