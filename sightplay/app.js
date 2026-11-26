import { KEYS, mod, LETTERS, makeChord, spellChordTone } from './theory.js';
import { generate, TEXTURES } from './generate.js';
import { gradeSegment, windows, summarize, nextTempo, simulate, MAX } from './grade.js';
import { render, beatX, renderChord } from './render.js';
import { makeConductor } from './conductor.js';
import { choirPlan, sing } from './choir.js';
import { MAJ, LEVELS, aidsFor, advance, newProgress, misprintRun, HAND_TEXT } from './levels.js';

const $ = (s) => document.querySelector(s);
const params = new URLSearchParams(location.search);
const SIM = params.get('sim');
const MUTE = params.has('mute');

// ---------- storage ----------
const STORE = 'sightplay.v2';
const load = () => { try { return JSON.parse(localStorage.getItem(STORE)) || {}; } catch { return {}; } };
const saved = load();
const FREE_DEFAULTS = {
  keys: ['C', 'G', 'F'], textures: ['L1'], meter: '4', density: 'slow', bars: 8, bpm: 50, hide: 'off', names: true,
  highlight: true, hand: 'both',
};
const state = {
  mode: saved.mode || 'ladder',
  prog: { ...newProgress(), ...(saved.prog || {}) },
  free: { ...FREE_DEFAULTS, ...(saved.free || {}) },
  click: saved.click || 'all',
  choir: saved.choir || 'normal', // normal | soft | off
  drag: !!saved.drag,
  rush: !!saved.rush,
  latencyMs: saved.latencyMs ?? null,
  clockMode: saved.clockMode || 'event',
  flash: { stage: 0, ...(saved.flash || {}) },
  history: saved.history || [],
  theme: saved.theme || 'dark',
};
document.documentElement.dataset.theme = state.theme;
const save = () => {
  const { mode, prog, free, click, choir, drag, rush, latencyMs, clockMode, flash, history, theme } = state;
  try { localStorage.setItem(STORE, JSON.stringify({ mode, prog, free, click, choir, drag, rush, latencyMs, clockMode, flash, history, theme })); } catch { /* private window */ }
};

// ---------- audio: click and a plain piano-ish synth ----------
let actx = null;
let nodes = [];
const audio = () => {
  if (!actx) actx = new AudioContext();
  if (actx.state === 'suspended') actx.resume();
  return actx;
};
const audioAt = (tPerf) => actx.currentTime + (tPerf - performance.now()) / 1000;
function click(tPerf, accent) {
  if (MUTE) return;
  const a = audio(); const at = audioAt(tPerf);
  const o = a.createOscillator(); const g = a.createGain();
  o.frequency.value = accent ? 1600 : 1000;
  g.gain.setValueAtTime(0.0001, at); g.gain.exponentialRampToValueAtTime(accent ? 0.5 : 0.3, at + 0.002);
  g.gain.exponentialRampToValueAtTime(0.0001, at + 0.05);
  o.connect(g).connect(a.destination); o.start(at); o.stop(at + 0.06);
  nodes.push(o);
}
function tone(midi, tPerf, dur) {
  if (MUTE) return;
  const a = audio(); const at = Math.max(a.currentTime, audioAt(tPerf));
  const f = 440 * 2 ** ((midi - 69) / 12);
  const g = a.createGain();
  g.gain.setValueAtTime(0.0001, at); g.gain.exponentialRampToValueAtTime(0.12, at + 0.01);
  g.gain.exponentialRampToValueAtTime(0.03, at + 0.4); g.gain.exponentialRampToValueAtTime(0.0001, at + dur / 1000 + 0.3);
  g.connect(a.destination);
  for (const [type, mult, vol] of [['triangle', 1, 1], ['sine', 2, 0.3]]) {
    const o = a.createOscillator(); const og = a.createGain();
    o.type = type; o.frequency.value = f * mult; og.gain.value = vol;
    o.connect(og).connect(g); o.start(at); o.stop(at + dur / 1000 + 0.4);
    nodes.push(o);
  }
}
function silence() { nodes.forEach((o) => { try { o.stop(); } catch { /* done */ } }); nodes = []; }

// ---------- MIDI ----------
let listener = null; // where notes go: the run, the flash drill or calibration
const NOTE = (m) => LETTERS[[0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6][mod(m, 12)]] + (['', '♯', '', '♯', '', '', '♯', '', '♯', '', '♯', ''][mod(m, 12)]) + (Math.floor(m / 12) - 1);
let clockChecks = 0;
function onMidi(midi, on, stamp) {
  const now = performance.now();
  if (state.clockMode === 'event' && clockChecks < 20) {
    clockChecks++;
    if (Math.abs(now - stamp) > 20) { state.clockMode = 'handler'; save(); showTiming(); }
  }
  const t = state.clockMode === 'event' ? stamp : now;
  if (on) $('#lastnote').textContent = NOTE(midi);
  if (listener) listener(midi, on, t);
}
async function initMidi() {
  if (SIM) { setMidi(`simulated player: ${SIM}`, true); return; }
  if (!navigator.requestMIDIAccess) { setMidi('This browser has no MIDI. Use Chrome.', false); return; }
  try {
    const access = await navigator.requestMIDIAccess();
    const attach = () => {
      const names = [];
      access.inputs.forEach((inp) => {
        names.push(inp.name);
        inp.onmidimessage = (e) => {
          const [st, d1, d2] = e.data; const cmd = st & 0xf0;
          if (cmd === 0x90 && d2 > 0) onMidi(d1, true, e.timeStamp);
          else if (cmd === 0x80 || (cmd === 0x90 && d2 === 0)) onMidi(d1, false, e.timeStamp);
        };
      });
      setMidi(names.length ? `Piano connected: ${names.join(', ')}` : 'No piano found: plug in the MIDI cable.', names.length > 0);
    };
    attach();
    access.onstatechange = attach;
  } catch (err) { setMidi('MIDI permission refused: ' + err.message, false); }
}
function setMidi(text, ok) { $('#midi').textContent = text; $('#midi').className = ok ? 'ok' : 'bad'; }

// ---------- keyboard strip (demo) ----------
const KB_LO = 36; const KB_HI = 84;
function buildKeyboard() {
  const kb = $('#kbd');
  const whites = []; for (let m = KB_LO; m <= KB_HI; m++) if (![1, 3, 6, 8, 10].includes(mod(m, 12))) whites.push(m);
  const ww = 100 / whites.length;
  let html = '';
  whites.forEach((m, i) => { html += `<div class="wk" data-m="${m}" style="left:${i * ww}%;width:${ww}%"></div>`; });
  for (let m = KB_LO; m <= KB_HI; m++) {
    if (![1, 3, 6, 8, 10].includes(mod(m, 12))) continue;
    const i = whites.indexOf(m - 1);
    html += `<div class="bk" data-m="${m}" style="left:${(i + 0.68) * ww}%;width:${ww * 0.64}%"></div>`;
  }
  kb.innerHTML = html;
}
const lightKey = (m, on) => { const k = $(`#kbd [data-m="${m}"]`); if (k) k.classList.toggle('lit', on); };

// ---------- run configuration ----------
const pick = (a) => a[Math.floor(Math.random() * a.length)];
function runConfig(demo) {
  if (state.mode === 'free' && !demo) {
    const f = state.free;
    return {
      keys: f.keys, textures: f.textures, chords: null, inversions: true, density: f.density,
      meters: f.meter === 'mix' ? [3, 4] : [+f.meter], hide: f.hide, hand: f.hand, nBars: +f.bars, bpm: f.bpm,
      aids: { outline: 0, grey: null, tint: false }, highlight: f.highlight, misprint: false, names: f.names, ladder: false,
    };
  }
  const lv = LEVELS[state.prog.level - 1];
  return {
    ...lv, meters: lv.meters, nBars: demo ? 4 : 8, bpm: demo ? 60 : state.prog.bpm, aids: aidsFor(lv.n),
    highlight: true, // the conductor conducts every ladder run misprint: demo ? lv.misprint : misprintRun(lv, state.prog),
    names: true, ladder: !demo, demo,
  };
}
function makeExercise(cfg, seed) {
  for (let i = 0; i < 6; i++) {
    try {
      return generate({
        keyName: pick(cfg.keys), beats: pick(cfg.meters), nBars: cfg.nBars, density: cfg.density, texture: pick(cfg.textures),
        chords: cfg.chords, inversions: cfg.inversions, chromatic: cfg.chromatic, misprint: cfg.misprint, piano: cfg.piano ?? 3,
        seed: seed ?? Math.floor(Math.random() * 2 ** 31),
      });
    } catch (e) { console.warn('regenerating:', e.message); seed = undefined; }
  }
  throw new Error('could not generate an exercise');
}

// ---------- the run ----------
let ex = null; let layout = null; let cfg = null; let run = null; let events = [];
const conductor = makeConductor(document.getElementById('stage'));
const ov = (cls, x, y, w, h, text) => {
  const d = document.createElement('div');
  d.className = cls; Object.assign(d.style, { left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px' });
  if (text) d.textContent = text;
  $('#overlay').appendChild(d);
  return d;
};

function draw() {
  layout = render($('#score'), ex, cfg.aids, state.theme);
  conductor.setMeter(ex.beats); conductor.draw(null, true);
  $('#overlay').innerHTML = '';
  Object.assign($('#overlay').style, { width: layout.width + 'px', height: layout.height + 'px' });
  if (cfg.aids.outline > 0) {
    layout.notes.filter((n) => n.shape).forEach((n) => {
      const d = ov('outline', n.x - 7, n.yTop - 8, 27, n.yBottom - n.yTop + 16);
      d.style.opacity = cfg.aids.outline;
      const t = document.createElement('span'); t.textContent = n.shape; d.appendChild(t);
    });
  }
  showRubric();
}

function start({ demo = false, again = false } = {}) {
  if (run) return;
  stopFlash();
  readFree();
  const newCfg = runConfig(demo);
  if (!again || !ex || !cfg || cfg.demo !== demo) ex = makeExercise(newCfg);
  cfg = newCfg;
  draw();
  $('#results').hidden = true;
  $('#kbd').hidden = !demo;
  const beatMs = 60000 / cfg.bpm;
  const tStart = performance.now() + 700;
  const t0 = tStart + ex.beats * beatMs;
  const segs = ex.harmony.map((h) => ({ t: t0 + h.start * beatMs, dur: h.dur * beatMs, pcs: h.chord.pcs, rootPc: h.chord.root.pc, bassPc: mod(h.voicing[0], 12) }));
  audio();
  const latMs = state.latencyMs ?? (((actx.outputLatency || 0) + (actx.baseLatency || 0)) * 1000);
  events = [];
  run = {
    demo, beatMs, tStart, t0, segs, latMs, results: [], marks: [], timers: [], sys: -1,
    mask: ov('mask', 0, 0, 0, 0), now: ov('now', 0, 0, 0, 0),
  };
  // click
  // a conductor makes no sound: the click plays only on runs without the conductor (free play with it unticked)
  const nClicks = cfg.highlight || state.click === 'off' ? 0 : state.click === 'countin' ? ex.beats : ex.beats * (ex.nBars + 1);
  for (let i = 0; i < nClicks; i++) click(tStart + i * beatMs, i % ex.beats === 0);
  // the choir: sung notes, scheduled a little ahead as the run goes (gradeTick)
  run.choir = state.choir === 'off' ? { events: [], mistakes: [] } : choirPlan(ex, beatMs, { drag: state.drag, rush: state.rush });
  run.choirNext = 0;
  // who plays
  if (demo || SIM) {
    const miss = demo ? Math.min(2, segs.length - 2) : -1;
    const kind = demo ? `demo-${cfg.hand}` : SIM;
    const ev = simulate(kind, segs, ex.harmony, beatMs, Math.random, miss);
    ev.forEach((e) => {
      if (demo && e.on) { const off = ev.find((x) => !x.on && x.midi === e.midi && x.t > e.t); tone(e.midi, e.t, (off ? off.t : e.t + 500) - e.t); }
      run.timers.push(setTimeout(() => {
        events.push({ midi: e.midi, on: e.on, t: e.t });
        if (demo) lightKey(e.midi, e.on);
      }, Math.max(0, e.t - performance.now())));
    });
    listener = null;
  } else {
    listener = (midi, on, t) => events.push({ midi, on, t: t - run.latMs });
  }
  document.body.classList.add('running');
  $('#start').textContent = 'Stop (Esc)';
  run.grader = setInterval(gradeTick, 30);
  requestAnimationFrame(tick);
}

function stop(finished) {
  if (!run) return;
  const r = run; run = null; listener = null;
  r.timers.forEach(clearTimeout); clearInterval(r.grader);
  if (!r.demo || !finished) silence();
  [r.mask, r.now].forEach((d) => { d.style.display = 'none'; });
  conductor.draw(null, true);
  document.querySelectorAll('#kbd .lit').forEach((k) => k.classList.remove('lit'));
  document.body.classList.remove('running');
  $('#count').textContent = '';
  $('#start').textContent = 'Start (space)';
  revealMarks(r);
  if (finished) finish(r);
  updateCard();
}

function tick() {
  if (!run) return;
  const r = run;
  const now = performance.now();
  const beat = (now - r.t0) / r.beatMs;
  $('#count').textContent = beat < 0 && now >= r.tStart ? String(Math.floor(beat + ex.beats) + 1) : '';
  const bar = Math.floor(beat / ex.beats);
  const L = layout.bars[bar];
  r.mask.style.display = 'none'; r.now.style.display = 'none';
  conductor.draw(now >= r.tStart ? beat : null, cfg.highlight);
  const unit = Math.ceil(ex.beats / 2);
  let hiddenUntil = -Infinity;
  if (beat >= 0 && L) {
    const inBar = beat - bar * ex.beats;
    if (cfg.hide === 'bar') {
      hiddenUntil = (bar + 1) * ex.beats;
      Object.assign(r.mask.style, { display: 'block', left: L.x0 + 2 + 'px', top: L.yTop + 'px', width: L.x1 - L.x0 - 4 + 'px', height: L.yBottom - L.yTop + 'px' });
    } else if (cfg.hide === 'half') {
      const b0 = inBar < unit ? 0 : unit; const b1 = inBar < unit ? unit : ex.beats;
      hiddenUntil = bar * ex.beats + b1;
      const xa = b0 === 0 ? L.x0 + 2 : beatX(L, b0, ex.beats) - 8;
      const xb = b1 === ex.beats ? L.x1 - 2 : beatX(L, b1, ex.beats) - 8;
      Object.assign(r.mask.style, { display: 'block', left: xa + 'px', top: L.yTop + 'px', width: xb - xa + 'px', height: L.yBottom - L.yTop + 'px' });
    }
    if (L.sys !== r.sys) {
      r.sys = L.sys;
      const top = $('#score').getBoundingClientRect().top + window.scrollY + layout.systems[L.sys].top;
      window.scrollTo({ top: top - 8 - $('#stage').offsetHeight, behavior: 'smooth' }); // just under the conductor
    }
  }
  requestAnimationFrame(tick);
}

function singAhead(r, now) {
  const ch = r.choir; if (!ch || MUTE) return;
  const level = state.choir === 'soft' ? 0.5 : 1;
  while (r.choirNext < ch.events.length && r.t0 + ch.events[r.choirNext].t < now + 400) {
    const e = ch.events[r.choirNext++];
    const at = Math.max(actx.currentTime, audioAt(r.t0 + e.t));
    nodes.push(...sing(actx, actx.destination, e, at, level));
  }
}

function gradeTick() {
  if (!run) return;
  const r = run; const now = performance.now();
  singAhead(r, now);
  while (r.results.length < r.segs.length) {
    const i = r.results.length;
    const w = windows(r.segs[i], r.segs[i + 1], r.beatMs);
    if (now < w.lateEnd + 40) break;
    const res = gradeSegment(r.segs[i], r.segs[i + 1], events, r.beatMs, cfg.hand);
    r.results.push(res);
    r.marks.push(placeMark(i));
  }
  const endT = r.t0 + ex.nBars * ex.beats * r.beatMs;
  if (r.results.length === r.segs.length && now >= endT) stop(true);
}

const MARK = { hit: '✓', late: '⟳', partial: '½', miss: '✗' };
function placeMark(i) {
  const h = ex.harmony[i];
  const bar = Math.floor(h.start / ex.beats); const L = layout.bars[bar];
  return ov('mark pending', beatX(L, h.start - bar * ex.beats, ex.beats) - 3, L.yBottom - 4, 0, 0, '•');
}
function revealMarks(r) {
  r.marks.forEach((d, i) => {
    const res = r.results[i]; const h = ex.harmony[i];
    d.className = 'mark ' + res.result;
    d.textContent = cfg.names ? `${MARK[res.result]} ${h.name}` : MARK[res.result];
    d.title = `${h.roman}: ${res.points} of ${res.max} points (${res.why})${res.offset != null ? `, ${Math.round(res.offset)} ms` : ''}`;
  });
}

const SECTION = { S: 'sopranos', A: 'altos', T: 'tenors', B: 'basses', T1: 'first tenors', T2: 'second tenors', Bar: 'baritones' };
const SLIP = { wrong: 'sang a wrong note', hang: 'held on to the last chord’s note', early: 'came in a beat early', flat: 'sagged flat on a long note' };
function choirNote(r) {
  if (!r.choir) return '';
  const bar = (b) => Math.floor(Math.max(0, b) / ex.beats) + 1;
  const parts = [];
  const m = r.choir.mistakes;
  if (m.length) parts.push(`The choir slipped: ${m.map((x) => `bar ${bar(x.from)}, the ${SECTION[x.section]} ${SLIP[x.kind]}`).join('; ')}.`);
  r.choir.rushing.forEach((x) => parts.push(`The ${SECTION[x.section]} rushed${x.backAt.length ? `, vamping to get back on the beat in bar${x.backAt.length > 1 ? 's' : ''} ${x.backAt.map(bar).join(', ')}` : ''}.`));
  if (state.drag) parts.push('Half of each section was following by ear, late.');
  return parts.length ? `<div class="hint">${parts.join(' ')} The conductor and the page were right.</div>` : '';
}

function finish(r) {
  if (r.demo) {
    state.prog.seenDemo[state.prog.level] = true; save();
    $('#summary').innerHTML = '<div class="msg">That was the demo: one chord was missed on purpose, and the music went on.</div>';
    $('#resultbtns').hidden = true;
    $('#results').hidden = false;
    return;
  }
  const s = summarize(r.results, ex.harmony);
  const pct = Math.round(s.score * 100);
  let msg = '';
  if (cfg.ladder) { const [q, m] = advance(state.prog, s.score); state.prog = q; msg = m; } else {
    const nt = nextTempo(cfg.bpm, s.score); if (nt !== cfg.bpm) { state.free.bpm = nt; $('#bpm').value = nt; msg = `Tempo ${nt > cfg.bpm ? 'up' : 'down'} to ♩ = ${nt}.`; }
  }
  const timing = s.medianOffset === null ? '' : Math.abs(s.medianOffset) < 40 ? 'On-time chords landed right on the beat.' : `On-time chords landed a median ${Math.abs(Math.round(s.medianOffset))} ms ${s.medianOffset > 0 ? 'late' : 'early'}.`;
  let mp = '';
  let mpPlayed = null;
  if (ex.misprint) {
    const i = ex.misprint.change; const w = windows(r.segs[i], r.segs[i + 1], r.beatMs);
    mpPlayed = events.some((e) => e.on && e.t >= w.from && e.t <= w.lateEnd && mod(e.midi, 12) === mod(ex.misprint.to, 12));
    const bar = Math.floor(ex.misprint.start / ex.beats) + 1;
    mp = `<div>This run had a misprint: bar ${bar}, ${ex.misprint.voice}, a wrong note a half step off. ${mpPlayed ? 'You played it.' : 'You played the chord without it: that is the skill.'}</div>`;
  }
  state.history.unshift({
    when: new Date().toISOString(), mode: cfg.ladder ? 'ladder' : 'free', level: cfg.ladder ? cfg.n : null, key: ex.keyName, tex: ex.texture,
    beats: ex.beats, bpm: cfg.bpm, hide: cfg.hide, hand: cfg.hand, highlight: cfg.highlight, aid: 'conductor', score: pct, misprintPlayed: mpPlayed,
    offsets: r.results.map((x) => (x.offset == null ? null : Math.round(x.offset))),
  });
  state.history.length = Math.min(state.history.length, 500);
  save();
  $('#summary').innerHTML = `
    <div class="big">${pct}%</div>
    <div class="msg">${msg}</div>
    <div>${s.points} of ${s.max} points. ${s.hit} changes with every point on time · ${s.late} late · ${s.partial} part · ${s.miss} none, of ${s.n}. ${timing}</div>
    ${s.weak.length ? `<div>Weakest: ${s.weak.join(', ')}</div>` : ''}
    ${mp}
    ${choirNote(r)}
    <div class="hint">Hover a mark under the music for what happened there.</div>`;
  $('#resultbtns').hidden = false;
  $('#results').hidden = false;
  showHistory();
}

// ---------- rubric: what is graded, worked out from grade.js's rules and this exercise's timing ----------
function showRubric() {
  const beatMs = 60000 / cfg.bpm;
  const segs = ex.harmony.map((h) => ({ t: h.start * beatMs, dur: h.dur * beatMs }));
  const ws = segs.map((sg, i) => { const w = windows(sg, segs[i + 1], beatMs); return { early: sg.t - w.from, late: w.to - sg.t, lateEnd: w.lateEnd - sg.t }; });
  const range = (k) => { const v = ws.map((w) => Math.round(w[k])); const lo = Math.min(...v); const hi = Math.max(...v); return lo === hi ? `${lo} ms` : `${lo}–${hi} ms`; };
  const n = ex.harmony.length;
  const max = MAX[cfg.hand];
  const inv = ex.harmony.some((h) => h.bassRole !== 'R');
  const root = inv ? 'the chord’s root or the bass note printed for it (this exercise prints some inverted basses)' : 'the chord’s root';
  const rows = [];
  if (cfg.hand !== 'right') rows.push(['+2', `<b>Left hand:</b> the lowest key you strike in the window is ${root}, in any octave. (A lower key still held down from before also counts, if it is ${inv ? 'one of those' : 'the root'}.)`]);
  if (cfg.hand !== 'left') {
    const where = cfg.hand === 'both' ? 'above the bass key' : '';
    rows.push(['+1', `<b>Right hand:</b> one note of the chord sounds ${where}, in any octave: struck in the window, or still held down from before.${cfg.hand === 'both' ? ' The root again, higher up, counts.' : ''}`]);
    rows.push(['+1', `<b>Right hand:</b> a second note of the chord with a <i>different name</i> from the first sounds ${where} (two Cs count as one).`]);
    rows.push(['−1', 'For <b>each key</b> struck in the window that is not in the chord. A change never goes below 0.']);
  }
  rows.push(['× ½', `<b>Late:</b> if some keys come after the window, the change is also scored from the keys struck from the change itself until one beat after it (or until the next change’s window opens), at half value. You get whichever score is higher.`]);
  const notGraded = [
    'Which octave anything is in, how the chord is spaced, and what is doubled.',
    ...(cfg.hand === 'left' ? [] : ['A third or fourth chord note in the right hand: allowed, but worth nothing extra.']),
    'The printed rhythm inside a chord: repeated notes, moving inner parts, passing notes, every printed note between changes.',
    'How long you hold a chord, when you let go, the pedal, how loud you play.',
    'Keys you strike between windows: not marked wrong.',
  ];
  if (cfg.hand === 'left') notGraded.unshift('<b>Everything above the lowest key.</b> The right hand may play anything or rest; wrong notes up there cost nothing.');
  if (cfg.hand === 'right') notGraded.unshift('<b>The bass.</b> The left hand may play or rest; the lowest key is just another key.');
  if (ex.misprint || cfg.misprint) notGraded.push('Playing a misprint (a wrong note printed in an inner voice) is not required; striking it costs −1 like any key outside the chord.');
  const tempoRule = cfg.ladder
    ? '85% or more: tempo +6 (at ♩ = 72, the next level, back at ♩ = 40). 60–84%: same tempo. Below 60%: tempo −6, not below 40.'
    : 'Free play: 85% or more raises the tempo 8, below 60% lowers it 8. Your level does not change.';
  $('#rubric').innerHTML = `
    <h2>Rubric for this run</h2>
    <p><b>Graded:</b> the ${n} chord changes in this exercise, nothing else. Each change is worth ${max} points; your score is your points ÷ ${n * max}. The music never waits, so every change is graded whether or not you played.</p>
    <p><b>The window</b> around each change at ♩ = ${cfg.bpm}: from ${range('early')} before it to ${range('late')} after it (half a beat each way, at most 350 ms early and 400 ms late, less for short chords).</p>
    <table class="rub">
      ${rows.map(([pt, txt]) => `<tr><th>${pt}</th><td>${txt}</td></tr>`).join('')}
      <tr><th>Marks</th><td>✓ all ${max} points on time · ⟳ all ${max} points but late (so ${max / 2}) · ½ some points · ✗ none.</td></tr>
      <tr><th>Not graded</th><td><ul>${notGraded.map((x) => `<li>${x}</li>`).join('')}</ul></td></tr>
      <tr><th>Your score</th><td>${tempoRule}</td></tr>
    </table>`;
}

function showFlashRubric() {
  const st = FLASH[Math.min(state.flash.stage, FLASH.length - 1)];
  $('#flashrubric').innerHTML = `
    <h2>Rubric for this set</h2>
    <p><b>Graded:</b> 10 chords, one every 3 s. Each shows for ${st.ms} ms; you have until the next one appears. Each chord is worth 3 points.</p>
    <table class="rub">
      <tr><th>+1</th><td>For each <i>different</i> note of the chord you strike in those 3 s, any octave, either hand (up to 3).</td></tr>
      <tr><th>−1</th><td>For each different key you strike that is not in the chord. A chord never goes below 0.</td></tr>
      <tr><th>Marks</th><td>✓ all 3 · ½ 1 or 2 · ✗ 0.</td></tr>
      <tr><th>Not graded</th><td><ul><li>Octave, order, spacing, which hand.</li><li>How fast you answer inside the 3 s, and whether the notes are together or one by one.</li><li>How long you hold them.</li></ul></td></tr>
      <tr><th>Your score</th><td>9 or 10 ✓ moves you to the next stage.</td></tr>
    </table>`;
}

// ---------- page ----------
// What to do, as instructions; the tempo line says where this run's beat comes from.
const RULE = {
  left: 'Play the root of each chord with your left hand, as your lowest note, on the beat where the chord changes. Only your left hand is graded.',
  right: 'Play two or more notes of each chord with your right hand, on the beat where the chord changes. Only your right hand is graded.',
  both: 'Play each chord on the beat where it changes: its root with your left hand, as your lowest note, and two other notes of the chord with your right.',
};
function ruleText(hand, conductor) {
  const tempo = conductor ? 'Take the tempo from the conductor above the music.'
    : state.click === 'off' ? 'Keep your own steady tempo; nothing gives the beat.'
      : state.click === 'countin' ? 'Take the tempo from the count-in clicks and keep it.' : 'Keep time with the click.';
  return `${RULE[hand]} ${tempo} If you miss a chord, skip it and play the next: the music never waits.`;
}
function updateCard() {
  const p = state.prog;
  document.querySelectorAll('#modes button').forEach((b) => b.classList.toggle('on', b.dataset.mode === state.mode));
  $('#ladder').hidden = state.mode === 'flash';
  $('#flash').hidden = state.mode !== 'flash';
  $('#freeset').hidden = state.mode !== 'free';
  if (state.mode === 'flash') { $('#rule').textContent = 'A chord flashes up, then vanishes. Play it before the next one. Nothing waits.'; showFlashCard(); return; }
  if (state.mode === 'free') {
    readFree();
    $('#rule').textContent = ruleText(state.free.hand, state.free.highlight);
    $('#levelline').textContent = `Free play · ♩ = ${state.free.bpm}`;
    $('#levelsub').textContent = 'Choose everything in the settings below. Free play does not move your level.';
    $('#demo').hidden = true; $('#start').className = 'primary'; $('#offer').hidden = true;
    return;
  }
  const lv = LEVELS[p.level - 1];
  const keyNames = lv.keys.length > 3 ? `${lv.keys.length} keys` : lv.keys.map((k) => KEYS[k].name).join(', ');
  $('#rule').textContent = ruleText(lv.hand, true);
  $('#levelline').textContent = `Level ${p.level} of ${LEVELS.length} · ${keyNames} · ♩ = ${p.bpm}`;
  $('#levelsub').textContent = `${TEXTURES[lv.textures[0]]}${lv.textures.length > 1 ? ' and more' : ''}`;
  const seen = !!p.seenDemo[p.level];
  $('#demo').hidden = false;
  $('#demo').className = seen ? '' : 'primary';
  $('#demo').textContent = seen ? '▶ Demo again' : '▶ Watch the demo (20 s)';
  $('#start').className = seen ? 'primary' : '';
  $('#offer').hidden = !p.offerDown;
  $('#offer').innerHTML = p.offerDown ? `<button id="godown">Go to level ${p.level - 1}</button>` : '';
  if (p.offerDown) $('#godown').onclick = () => { state.prog = { ...state.prog, level: p.level - 1, bpm: 40, low: 0, offerDown: false, runsAtLevel: 0 }; save(); updateCard(); preview(); };
}

function preview() {
  if (state.mode === 'flash' || run) return;
  readFree();
  cfg = runConfig(false);
  ex = makeExercise(cfg);
  draw();
}

function showHistory() {
  $('#history').innerHTML = '<tr><th>When</th><th>Level</th><th>Key</th><th>Texture</th><th>♩</th><th>Aid</th><th>Score</th></tr>' + state.history.slice(0, 15).map((h) => `<tr><td>${new Date(h.when).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</td><td>${h.level ?? 'free'}</td><td>${KEYS[h.key].name}</td><td>${h.tex}</td><td>${h.bpm}</td><td>${h.highlight ? (h.aid === 'conductor' ? 'conductor' : 'highlight') : 'none'}</td><td>${h.score}%</td></tr>`).join('');
}

// free-play settings
function buildFree() {
  const f = state.free;
  $('#keys').innerHTML = Object.entries(KEYS).map(([k, v]) => `<label><input type="checkbox" name="key" value="${k}" ${f.keys.includes(k) ? 'checked' : ''}>${v.name}</label>`).join('');
  $('#textures').innerHTML = Object.entries(TEXTURES).map(([k, v]) => `<label><input type="checkbox" name="tex" value="${k}" ${f.textures.includes(k) ? 'checked' : ''}>${v}</label>`).join('');
  for (const id of ['meter', 'density', 'bars', 'bpm', 'hide', 'hand']) $('#' + id).value = f[id];
  $('#names').checked = f.names; $('#hl').checked = f.highlight; $('#click').value = state.click;
  $('#freeset').addEventListener('change', () => { readFree(); save(); updateCard(); preview(); });
  $('#click').addEventListener('change', () => { state.click = $('#click').value; save(); updateCard(); });
  $('#choir').value = state.choir; $('#drag').checked = state.drag; $('#rush').checked = state.rush;
  $('#rush').addEventListener('change', () => { state.rush = $('#rush').checked; save(); });
  $('#choir').addEventListener('change', () => { state.choir = $('#choir').value; save(); });
  $('#drag').addEventListener('change', () => { state.drag = $('#drag').checked; save(); });
}
function readFree() {
  const f = state.free;
  const keys = [...document.querySelectorAll('input[name=key]:checked')].map((x) => x.value);
  const tex = [...document.querySelectorAll('input[name=tex]:checked')].map((x) => x.value);
  if (keys.length) f.keys = keys; if (tex.length) f.textures = tex;
  f.meter = $('#meter').value; f.density = $('#density').value; f.bars = +$('#bars').value;
  f.bpm = Math.max(30, Math.min(200, +$('#bpm').value || 50)); f.hide = $('#hide').value; f.hand = $('#hand').value;
  f.names = $('#names').checked; f.highlight = $('#hl').checked;
}

// ---------- timing calibration ----------
function showTiming() {
  $('#timing').textContent = `Clock: ${state.clockMode === 'event' ? 'MIDI timestamps' : 'arrival time (the MIDI timestamps disagreed with the page clock)'} · latency correction: ${state.latencyMs == null ? 'browser estimate' : Math.round(state.latencyMs) + ' ms, calibrated'}`;
}
function calibrate() {
  if (run) return;
  stopFlash();
  audio();
  const beatMs = 750; const t0 = performance.now() + 1500; const n = 12;
  const clicks = []; for (let i = 0; i < n; i++) { clicks.push(t0 + i * beatMs); click(t0 + i * beatMs, i % 4 === 0); }
  const taps = [];
  $('#calmsg').textContent = 'Tap any key along with the clicks after the first four…';
  listener = (midi, on, t) => { if (on) taps.push(t); };
  setTimeout(() => {
    listener = null;
    const diffs = taps.map((t) => { const c = clicks.reduce((a, b) => (Math.abs(b - t) < Math.abs(a - t) ? b : a)); return t - c; }).filter((d) => Math.abs(d) < beatMs / 2);
    if (diffs.length < 5) { $('#calmsg').textContent = `Only ${diffs.length} taps landed near a click; try again.`; return; }
    diffs.sort((a, b) => a - b);
    state.latencyMs = diffs[Math.floor(diffs.length / 2)];
    save(); showTiming();
    $('#calmsg').textContent = `Your taps land ${Math.round(state.latencyMs)} ms after the clicks are sent; every note is now shifted back by that.`;
  }, t0 - performance.now() + n * beatMs + 400);
}

// ---------- flash drill ----------
const FLASH = [
  { keys: ['C'], inv: false, ms: 1000, text: 'C major, root position, shown 1 s' },
  { keys: ['C'], inv: true, ms: 1000, text: 'C major, any position, shown 1 s' },
  { keys: MAJ, inv: true, ms: 1000, text: 'eight keys, shown 1 s' },
  { keys: MAJ, inv: true, ms: 600, text: 'eight keys, shown 0.6 s' },
  { keys: MAJ, inv: true, ms: 400, text: 'eight keys, shown 0.4 s' },
  { keys: MAJ, inv: true, ms: 250, text: 'eight keys, shown 0.25 s' },
];
const FLASH_CYCLE = 3000; const FLASH_N = 10;
let flash = null;
function flashItem(stage) {
  const key = KEYS[pick(stage.keys)];
  const ch = makeChord(key, pick(['I', 'ii', 'iii', 'IV', 'V', 'vi']));
  const k = stage.inv ? Math.floor(Math.random() * 3) : 0;
  const order = [0, 1, 2].map((i) => ch.tones[(i + k) % 3].pc);
  let m = 60; while (mod(m, 12) !== order[0]) m++;
  const ms = [m];
  for (const pc of order.slice(1)) { let x = ms[ms.length - 1] + 1; while (mod(x, 12) !== pc) x++; ms.push(x); }
  return { key, ch, midis: ms, spells: ms.map((x) => spellChordTone(ch, x)) };
}
function showFlashCard() {
  showFlashRubric();
  const st = FLASH[Math.min(state.flash.stage, FLASH.length - 1)];
  $('#levelline').textContent = `Flash drill · stage ${state.flash.stage + 1} of ${FLASH.length}`;
  $('#levelsub').textContent = `${st.text} · a new chord every 3 s · 9 of 10 moves you on`;
  $('#demo').hidden = true; $('#start').className = 'primary'; $('#offer').hidden = true;
}
function startFlash() {
  if (flash) { stopFlash(); return; }
  const stage = FLASH[Math.min(state.flash.stage, FLASH.length - 1)];
  flash = { stage, items: [], results: [], timers: [], notes: [] };
  $('#flashdots').innerHTML = '';
  $('#flashmsg').textContent = '';
  $('#start').textContent = 'Stop (Esc)';
  document.body.classList.add('running');
  listener = (midi, on, t) => { if (on) flash.notes.push({ midi, t }); };
  const t0 = performance.now() + 1500;
  for (let i = 0; i < FLASH_N; i++) {
    const item = flashItem(stage); flash.items.push(item);
    const at = t0 + i * FLASH_CYCLE;
    flash.timers.push(setTimeout(() => { renderChord($('#flashchord'), item.key.vf, item.spells, state.theme); $('#flashchord').style.visibility = 'visible'; item.t = performance.now(); }, at - performance.now()));
    flash.timers.push(setTimeout(() => { $('#flashchord').style.visibility = 'hidden'; }, at + stage.ms - performance.now()));
    flash.timers.push(setTimeout(() => judgeFlash(i), at + FLASH_CYCLE - 60 - performance.now()));
  }
}
function judgeFlash(i) {
  const item = flash.items[i];
  const struck = flash.notes.filter((n) => n.t >= item.t && n.t < item.t + FLASH_CYCLE - 60).map((n) => mod(n.midi, 12));
  const need = new Set(item.midis.map((m) => mod(m, 12)));
  const got = new Set(struck.filter((pc) => need.has(pc)));
  const wrong = new Set(struck.filter((pc) => !need.has(pc))).size;
  const pts = Math.max(0, got.size - wrong);
  const res = pts === 3 ? 'hit' : pts > 0 ? 'partial' : 'miss';
  flash.results.push(res);
  const d = document.createElement('span'); d.className = 'dot ' + res; d.textContent = MARK[res]; d.title = item.spells.map((s) => LETTERS[s.letter]).join(' ');
  $('#flashdots').appendChild(d);
  if (flash.results.length === FLASH_N) {
    const hits = flash.results.filter((x) => x === 'hit').length;
    let msg = `${hits} of ${FLASH_N}.`;
    if (hits >= 9 && state.flash.stage < FLASH.length - 1) { state.flash.stage++; msg += ` Stage ${state.flash.stage + 1} next.`; }
    save();
    stopFlash();
    $('#flashmsg').textContent = msg;
    showFlashCard();
  }
}
function stopFlash() {
  if (!flash) return;
  flash.timers.forEach(clearTimeout); flash = null; listener = null;
  $('#flashchord').style.visibility = 'hidden';
  document.body.classList.remove('running');
  $('#start').textContent = 'Start (space)';
}

// ---------- wiring ----------
buildKeyboard();
buildFree();
showTiming();
showHistory();
initMidi();
const go = () => (state.mode === 'flash' ? startFlash() : run ? stop(false) : start());
$('#start').onclick = go;
$('#demo').onclick = () => { if (!run) start({ demo: true }); };
$('#again').onclick = () => start({ again: true });
$('#next').onclick = () => start();
$('#calibrate').onclick = calibrate;
const themeLabel = () => { $('#theme').textContent = state.theme === 'dark' ? 'Light page' : 'Dark page'; };
themeLabel();
$('#theme').onclick = () => { if (run) return; state.theme = state.theme === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = state.theme; save(); themeLabel(); if (ex && state.mode !== 'flash') draw(); };
document.querySelectorAll('#modes button').forEach((b) => { b.onclick = () => { if (run) return; stopFlash(); state.mode = b.dataset.mode; save(); updateCard(); $('#results').hidden = true; preview(); }; });
document.addEventListener('keydown', (e) => {
  if (['INPUT', 'SELECT'].includes(e.target.tagName)) return;
  if (e.code === 'Space') { e.preventDefault(); if (!run && !flash) go(); }
  if (e.code === 'Escape') { stop(false); stopFlash(); }
});
window.addEventListener('pagehide', () => { stop(false); stopFlash(); silence(); });
let resizeTimer = null;
window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (!run && ex) draw(); }, 200); });
updateCard();
preview();
window.sightplay = { note: (m, on) => onMidi(m, on, performance.now()), get flash() { return flash; }, get audioNodes() { return nodes.length; }, get ex() { return ex; }, get events() { return events; }, get run() { return run; }, get layout() { return layout; }, get cfg() { return cfg; }, get audioCtx() { return actx; }, state, start, stop, startFlash, stopFlash, save };
