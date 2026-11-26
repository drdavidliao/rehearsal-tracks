// Pitch trainer: walks one singer through a few notes, out of time and then in time, with the phone's speaker and mic
// taking turns (the mic is not scored while the phone makes a sound, nor while that sound dies away).
// URL flags for testing: ?sim (a simulated singer instead of the mic, no sound), &rate=8 (run the clock 8x).
(function () {
  'use strict';
  const P = window.Pitch;
  const Q = new URLSearchParams(location.search);
  const SIM = Q.has('sim');
  const RATE = SIM ? +(Q.get('rate') || 1) : 1;
  const $ = s => document.querySelector(s);

  // ------------------------------------------------------------------ clock and cancelling
  const T0 = performance.now();
  const now = () => (performance.now() - T0) * RATE / 1000; // seconds, sped up in sim
  class Stopped extends Error {}
  let runId = 0;
  const alive = id => { if (id !== runId) throw new Stopped(); };
  const sleep = (s, id) => new Promise(r => setTimeout(r, Math.max(0, s) * 1000 / RATE)).then(() => alive(id));

  // ------------------------------------------------------------------ exercise and progress
  let EX = null;
  const STORE = () => 'pitch-trainer:' + EX.title;
  const PASSES = ['learn', 'review', 'pairs', 'time', 'done'];
  let ST = null;
  function freshState() {
    return { pass: 'learn', idx: 0, speedIdx: 0, mode: 'sing',
             notes: EX.notes.map(() => ({ solid: false, rung: 0, pulse: 1, level: 0, streak: 0 })), sessions: 0 };
  }
  function load() {
    try { const s = JSON.parse(localStorage.getItem(STORE())); if (s && s.notes && s.notes.length === EX.notes.length) return s; } catch (e) {}
    return freshState();
  }
  function save() { try { localStorage.setItem(STORE(), JSON.stringify(ST)); } catch (e) {} }

  // ------------------------------------------------------------------ audio engine
  const E = {
    ac: null, an: null, buf: null, sr: 48000, noise: 0.0005, tail: 0.25, rtt: 0.15, heard: true,
    frames: [], gates: [], clips: {}, guide: null,
  };
  const FR = 4096;
  function gate(a, b) { E.gates.push([a, b]); if (E.gates.length > 50) E.gates.shift(); }
  const gated = t => E.gates.some(([a, b]) => t >= a && t <= b);

  async function startAudio() {
    if (SIM) { E.sr = 48000; return; }
    try { if (navigator.audioSession) navigator.audioSession.type = 'play-and-record'; } catch (e) {} // iPhone: not muted by the silent switch
    E.ac = new (window.AudioContext || window.webkitAudioContext)();
    await E.ac.resume();
    let src;
    if (Q.has('nomic')) { // testing the sound without a mic: a silent input
      src = E.ac.createConstantSource ? E.ac.createConstantSource() : E.ac.createOscillator();
      if (src.offset) src.offset.value = 0; src.start();
    } else {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: {
        echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 } });
      src = E.ac.createMediaStreamSource(stream);
    }
    E.an = E.ac.createAnalyser();
    E.an.fftSize = FR;
    src.connect(E.an);
    E.buf = new Float32Array(FR);
    E.sr = E.ac.sampleRate;
    E.out = E.ac.createGain();
    E.out.connect(E.ac.destination);
  }

  // one analysis frame every 40 ms
  function tick() {
    let f;
    const t = now();
    if (SIM) f = Sim.frame(t);
    else {
      E.an.getFloatTimeDomainData(E.buf);
      f = P.detect(E.buf, E.sr, { highpass: 100, noiseRms: E.noise });
    }
    const tc = SIM ? t : t - FR / 2 / E.sr; // a frame's time is its middle
    E.frames.push({ t: tc, midi: f.midi, voiced: f.voiced, rms: f.rms, gated: gated(tc) });
    while (E.frames.length && E.frames[0].t < t - 20) E.frames.shift();
  }

  const recent = (dur, from) => { const t = from == null ? now() : from; return E.frames.filter(f => f.t > t - dur && f.t <= t && !f.gated); };
  const median = a => { if (!a.length) return null; const s = a.slice().sort((x, y) => x - y); return s[s.length >> 1]; };

  // on the note: over the last half second, his median within ±40 cents and most of it within ±75 (room for a scoop,
  // vibrato and wobble, as people sing; a semitone off still fails). Gated frames don't count against him.
  function heldAt(m, dur = 0.5) {
    const fs = recent(dur);
    if (fs.length < dur / 0.04 * 0.8) return false; // at least 0.4 s of him, not counting the phone's turn
    const v = fs.filter(f => f.voiced);
    if (v.length < fs.length * 0.7) return false;
    const c = v.map(f => (f.midi - m) * 100);
    return Math.abs(median(c)) < 40 && c.filter(x => Math.abs(x) < 75).length >= v.length * 0.7;
  }
  // his steady pitch over the last second, or null
  function steady(dur = 1.0) {
    const fs = recent(dur);
    if (fs.length < dur / 0.04 * 0.5) return null;
    const v = fs.filter(f => f.voiced).map(f => f.midi);
    if (v.length < fs.length * 0.6) return null;
    const s = v.slice().sort((a, b) => a - b);
    const iqr = s[Math.floor(s.length * 0.75)] - s[Math.floor(s.length * 0.25)];
    return iqr < 1.0 ? median(v) : null;
  }
  const silent = (dur = 0.2) => { const fs = recent(dur); return fs.length >= 2 && fs.every(f => !f.voiced); };
  function shown() { // what the staff draws for him: median of the last 3 voiced frames
    const fs = E.frames.slice(-4).filter(f => f.voiced && !f.gated);
    return fs.length ? median(fs.map(f => f.midi)) : null;
  }

  // ---- sounds
  function envelope(x, sr, att = 0.03, rel = 0.08) {
    const a = Math.round(att * sr), r = Math.round(rel * sr);
    for (let i = 0; i < a && i < x.length; i++) x[i] *= i / a;
    for (let i = 0; i < r && i < x.length; i++) x[x.length - 1 - i] *= i / r;
    return x;
  }
  function playBuffer(x, gain, at) {
    const b = E.ac.createBuffer(1, x.length, E.sr);
    b.copyToChannel ? b.copyToChannel(x, 0) : b.getChannelData(0).set(x);
    const s = E.ac.createBufferSource(); s.buffer = b;
    const g = E.ac.createGain(); g.gain.value = gain;
    s.connect(g); g.connect(E.out);
    s.start(at);
  }
  // a guide note: the sung "ah" (optionally gliding in from another pitch) with the piano's chord under it, quietly.
  // Resolves when the sound and its echo in the room are over, so he can be heard again.
  async function pulse(midi, o, id) {
    o = o || {};
    const dur = o.dur || 0.8, gain = o.gain == null ? 0.6 : o.gain;
    UI.guide(midi, o.from);
    Sim.heard(midi, o);
    const t = now();
    if (!SIM) {
      const from = o.from, f0 = from == null ? P.midiToHz(midi) : (tt => {
        const k = Math.min(1, Math.max(0, (tt - dur * 0.3) / (dur * 0.35)));
        return P.midiToHz(from + (midi - from) * (k * k * (3 - 2 * k)));
      });
      const at = E.ac.currentTime + 0.03;
      playBuffer(envelope(P.synthVoice(E.sr, dur, f0, { vowel: 'ah', amp: 0.5, vibrato: 12 }), E.sr), gain, at);
      if (o.chord && o.chord.length) {
        const c = new Float32Array(Math.round(E.sr * dur));
        for (const m of o.chord) {
          const hz = P.midiToHz(m), w = 2 * Math.PI * hz / E.sr;
          for (let i = 0; i < c.length; i++) c[i] += (Math.sin(w * i) + 0.3 * Math.sin(2 * w * i)) * 0.05;
        }
        playBuffer(envelope(c, E.sr, 0.05, 0.15), gain * 0.7, at);
      }
    }
    gate(t, t + 0.03 + dur + E.rtt + E.tail);
    await sleep(0.03 + dur + E.rtt + E.tail, id);
    UI.guide(null);
  }

  async function loadClips(pct) {
    if (SIM || E.clips[pct]) return;
    const get = async n => E.ac.decodeAudioData(await (await fetch(`${n}-${pct}.mp3`)).arrayBuffer());
    E.clips[pct] = { voice: await get('voice'), accomp: await get('accomp') };
  }
  // the track from clip time a to b (in the stretched clip's own seconds), the part's stem with gains per note.
  // Returns the clock time that clip time 0 falls at.
  function playClip(pct, a, b, voiceGain, fadeOut) {
    const k = 100 / pct, t = now(), lead = 0.08;
    const c0 = t + lead - a * k;
    if (!SIM) {
      const at = E.ac.currentTime + lead, c = E.clips[pct];
      const ga = E.ac.createGain(), gv = E.ac.createGain();
      ga.connect(E.out); gv.connect(E.out);
      const sa = E.ac.createBufferSource(); sa.buffer = c.accomp; sa.connect(ga);
      const sv = E.ac.createBufferSource(); sv.buffer = c.voice; sv.connect(gv);
      ga.gain.setValueAtTime(0.9, at);
      if (fadeOut) { ga.gain.setValueAtTime(0.9, at + (b - a) * k - 0.08); ga.gain.linearRampToValueAtTime(0, at + (b - a) * k); }
      // voice gain automation, piecewise, in clip time
      const segs = voiceGain(); // [[t0, t1, gain]] in unstretched clip seconds, plus a default
      gv.gain.setValueAtTime(segs.base, at);
      const list = segs.list.slice().sort((p, q) => p[0] - q[0]);
      for (let j = 0; j < list.length; j++) {
        const [s0, s1raw, g, onset] = list[j];
        const s1 = j + 1 < list.length ? Math.min(s1raw, list[j + 1][0] - 0.012) : s1raw; // never into the next note
        const x0 = at + (s0 - a) * k - 0.01, x1 = at + (s1 - a) * k;
        if (x1 < at) continue;
        gv.gain.setValueAtTime(g, Math.max(at, x0));
        if (onset) { const o = Math.max(at, x0); gv.gain.setValueAtTime(1, o); gv.gain.setValueAtTime(1, o + 0.15 * k - 0.03); gv.gain.linearRampToValueAtTime(0, o + 0.15 * k); }
        gv.gain.setValueAtTime(segs.base, Math.max(at, x1));
      }
      sa.start(at, a * k, (b - a) * k); sv.start(at, a * k, (b - a) * k);
    }
    gate(t, t + lead + (b - a) * k + E.rtt + E.tail);
    return c0;
  }

  // ---- start-up checks: the room's noise, then whether (and how late, how long) the mic hears the speaker
  async function measureRoom(id) {
    UI.cue('Quiet', 'Measuring the room for 2 seconds…');
    await sleep(2.0, id);
    const fs = E.frames.slice(-40);
    E.noise = median(fs.map(f => f.rms)) || 0.0005;
    const busy = fs.filter(f => f.voiced).length / Math.max(1, fs.length);
    if (SIM) return 'ok';
    if (E.noise > 0.03) return 'loud';
    if (busy > 0.3) return 'busy';
    // the speaker test: one short tone
    const t = now();
    const at = E.ac.currentTime + 0.05;
    playBuffer(envelope(P.synthVoice(E.sr, 0.4, P.midiToHz(52), { amp: 0.5 }), E.sr), 0.6, at);
    gate(t, t + 1.5);
    await sleep(1.5, id);
    const lvl = E.frames.filter(f => f.t > t - 0.1 && f.t < t + 1.5);
    const loud = lvl.filter(f => f.rms > Math.max(E.noise * 4, 0.002));
    if (loud.length) {
      E.heard = true;
      E.rtt = Math.min(0.5, Math.max(0.03, loud[0].t - (t + 0.05)));
      E.tail = Math.min(0.6, Math.max(0.12, loud[loud.length - 1].t - (t + 0.05 + 0.4) - E.rtt + 0.05));
    } else {
      E.heard = false; // earbuds, or a very quiet speaker
      E.rtt = (E.ac.outputLatency || 0) + (E.ac.baseLatency || 0) + 0.05;
      E.tail = 0.08;
    }
    return 'ok';
  }

  // ------------------------------------------------------------------ waiting on the singer
  const SING = () => (ST.mode === 'hum' ? 'Hum' : 'Sing');
  async function waitFor(pred, timeout, id) {
    const t = now();
    while (now() - t < timeout) { if (pred()) return true; await sleep(0.08, id); }
    return false;
  }
  const waitHeld = (m, timeout, id) => waitFor(() => heldAt(m), timeout, id);
  async function waitSteady(timeout, id) {
    let p = null;
    await waitFor(() => (p = steady()) != null, timeout, id);
    return p;
  }
  // after "Sing": wait for him to come in, then judge the first 0.3 s of his note
  async function reentry(m, timeout, id) {
    const t = now();
    let onset = null;
    while (now() - t < timeout) {
      const v = recent(0.1).filter(f => f.voiced);
      if (v.length) { onset = v[0].t; break; }
      await sleep(0.04, id);
    }
    if (onset == null) return null;
    await sleep(0.42, id);
    // skip his first 0.1 s (the scoop into the note), judge the next 0.3 s
    const v = E.frames.filter(f => f.t >= onset + 0.1 && f.t <= onset + 0.4 && f.voiced && !f.gated);
    const md = median(v.map(f => f.midi));
    return md == null ? null : md;
  }

  // ------------------------------------------------------------------ one note: offer, find him, walk, re-voice
  const pulseOpts = i => ({ dur: 0.15 + 0.65 * ST.notes[i].pulse, gain: 0.3 + 0.3 * ST.notes[i].pulse, chord: EX.notes[i].chord });
  const easeOff = i => { ST.notes[i].pulse = Math.max(0, ST.notes[i].pulse * 0.85 - 0.02); };

  async function walk(i, id) {
    const T = EX.notes[i].midi;
    for (;;) {
      UI.cue(SING(), 'Any note. Hold it.');
      const p = await waitSteady(6, id);
      if (p == null) {
        UI.cue(SING(), ST.mode === 'hum' ? 'Louder, or closer to the phone.' : 'Louder, or hum close to the phone.');
        await waitSteady(6, id);
        continue;
      }
      if (heldAt(T)) return;
      let G = Math.round(p);
      UI.cue('Match me', 'I’ll sing your note.');
      await pulse(G, { dur: 0.8 }, id);
      UI.cue(SING(), 'Same note. Hold it.');
      if (!(await waitHeld(G, 3, id))) continue;
      UI.good();
      let lost = false;
      while (G !== T) {
        const next = G + Math.sign(T - G);
        UI.cue('Move with me', next > G ? 'A little higher.' : 'A little lower.');
        await pulse(next, { dur: 1.1, from: G, chord: next === T ? EX.notes[i].chord : null }, id);
        UI.cue(SING(), 'Hold it.');
        if (await waitHeld(next, 3, id)) { G = next; UI.good(); }
        else { lost = true; break; }
      }
      if (!lost) return;
    }
  }

  async function ladder(i, gaps, id) {
    const T = EX.notes[i].midi, n = ST.notes[i];
    let r = Math.min(n.rung, gaps.length - 1), fails = 0;
    while (r < gaps.length) {
      UI.cue('Stop', '');
      await waitFor(() => silent(0.2), 2, id);
      UI.wait(gaps[r]);
      await sleep(gaps[r], id);
      UI.cue(SING(), 'Same note.');
      const m = await reentry(T, 4, id);
      if (m != null && Math.abs(m - T) * 100 < 50) {
        UI.good(); r++; fails = 0; n.rung = r; easeOff(i); save();
        await waitFor(() => false, 0.8, id); // let him hear himself land
        continue;
      }
      fails++;
      UI.miss(m, T);
      if (fails >= 2) { await walk(i, id); fails = 0; continue; }
      save(); // the same gap again, after a cue
      UI.cue('Listen', '');
      await pulse(T, pulseOpts(i), id);
      UI.cue(SING(), 'Hold it.');
      if (!(await waitHeld(T, 4, id))) await walk(i, id);
    }
  }

  async function learnNote(i, id) {
    const T = EX.notes[i].midi;
    UI.focus(i);
    const known = EX.notes.some((o, j) => j < i && o.midi === T && ST.notes[j].solid);
    UI.cue('Listen', known ? 'You know this one.' : '');
    await pulse(T, pulseOpts(i), id);
    UI.cue(SING(), 'Hold it.');
    if (!(await waitHeld(T, 4, id))) await walk(i, id);
    UI.good();
    await ladder(i, known ? [1.5] : [0.5, 1.5, 4], id);
    ST.notes[i].solid = true;
    save();
  }

  // ------------------------------------------------------------------ the passes
  async function learnPass(id) {
    while (ST.idx < EX.notes.length) {
      await learnNote(ST.idx, id);
      ST.idx++; save();
      if (ST.idx < EX.notes.length && (await timeUp(id))) return false;
    }
    return true;
  }
  async function reviewPass(id) {
    while (ST.idx < EX.notes.length) {
      const i = ST.idx, T = EX.notes[i].midi;
      UI.focus(i);
      UI.cue('Listen', '');
      await pulse(T, pulseOpts(i), id);
      UI.cue(SING(), '');
      if (await waitHeld(T, 4, id)) { UI.good(); easeOff(i); await sleep(0.4, id); }
      else { UI.miss(shown(), T); await walk(i, id); ST.notes[i].rung = 0; await ladder(i, [0.5, 1.5], id); }
      ST.idx++; save();
      if (ST.idx < EX.notes.length && (await timeUp(id))) return false;
    }
    return true;
  }
  async function pairsPass(id) {
    while (ST.idx < EX.notes.length - 1) {
      const i = ST.idx, a = EX.notes[i], b = EX.notes[i + 1];
      UI.focus(i, i + 1);
      UI.cue('Listen', '');
      await pulse(a.midi, pulseOpts(i), id);
      UI.cue(SING(), `“${a.word}”, hold it.`);
      if (!(await waitHeld(a.midi, 4, id))) await walk(i, id);
      UI.good();
      UI.focus(i + 1, null, i);
      UI.cue('Now the next', `Move to “${b.word}” on your own.`);
      if (await waitHeld(b.midi, 3.5, id)) { UI.good(); easeOff(i + 1); ST.idx++; ST.retry = false; await sleep(0.4, id); }
      else { // the pulse only on a miss, then the same pair once more, then on

        UI.miss(shown(), b.midi);
        UI.cue('Listen', '');
        await pulse(b.midi, pulseOpts(i + 1), id);
        UI.cue(SING(), 'Hold it.');
        if (!(await waitHeld(b.midi, 4, id))) await walk(i + 1, id);
        UI.good();
        if (ST.retry) { ST.idx++; ST.retry = false; } else ST.retry = true;
        await sleep(0.4, id);
      }
      save();
      if (ST.idx < EX.notes.length - 1 && (await timeUp(id))) return false;
    }
    return true;
  }

  // in time: listen to the track (the part fading note by note as he earns it), then sing it back alone
  const LEVEL_GAIN = [1, 0.25, -1, 0, 0]; // -1: only the note's first 150 ms
  function voiceGains() {
    const lv = ST.notes.map(n => n.level);
    const base = Math.min(...lv.map(l => (LEVEL_GAIN[l] < 0 ? 0 : LEVEL_GAIN[l])));
    return { base, list: EX.notes.map((n, i) => [n.t0, n.t1, LEVEL_GAIN[lv[i]] < 0 ? 0 : LEVEL_GAIN[lv[i]], LEVEL_GAIN[lv[i]] < 0]) };
  }
  function beatsOf(k) { // clip-time beats, each {t, bar, n}
    const out = [];
    for (const m of EX.meters) for (let j = 0; j < m.num; j++) out.push({ t: m.t0 + (m.t1 - m.t0) * j / m.num, bar: m.bar, n: j + 1 });
    return out;
  }
  async function timePass(id) {
    for (;;) {
      const pct = [60, 80, 100][ST.speedIdx];
      const k = 100 / pct;
      await loadClips(pct);
      const cold = ST.notes.every(n => n.level >= 4);
      UI.focus(null);
      UI.round(pct, ST.notes.map(n => n.level));
      const lastBar = EX.meters[EX.meters.length - 2]; // the exercise's last bar (the clip runs one bar on)
      if (!cold) {
        UI.cue('Listen', `The track, ${pct}% speed.`);
        const c0 = playClip(pct, 0, lastBar.t1 + 0.3, voiceGains, true);
        Sim.listen();
        await UI.beats(beatsOf(), c0, k, lastBar.t1, id);
        await sleep(E.rtt + E.tail, id);
      }
      // his turn: the bar before as a lead-in, all but its last beat, then the beat keeps flashing
      const lead = EX.meters[0], beat = (lead.t1 - lead.t0) / lead.num;
      UI.cue('Your turn', 'After the lead-in, sing it on your own.');
      await sleep(0.6, id);
      const c0 = playClip(pct, lead.t0, lead.t1 - beat, () => ({ base: 0, list: [] }), true);
      Sim.echo(c0, k, ST.notes);
      UI.cue('', '');
      await UI.beats(beatsOf(), c0, k, lastBar.t1, id);
      await sleep(0.4, id);
      // score each note in its window, shifted by the mic's lag
      const shift = E.rtt / 2;
      const res = EX.notes.map(n => {
        const a = c0 + n.t0 * k + shift - 0.06, b = c0 + n.t1 * k + shift + 0.12;
        const v = E.frames.filter(f => f.t >= a && f.t <= b && f.voiced && !f.gated);
        if (v.length < 2) return { heard: false };
        const md = median(v.map(f => f.midi));
        return { heard: true, midi: md, ok: Math.abs(md - n.midi) * 100 < 50 };
      });
      UI.results(res);
      let missed = 0, unheard = 0;
      res.forEach((r, i) => {
        const n = ST.notes[i];
        if (!r.heard) { unheard++; return; }
        if (r.ok) { if (n.level < 4) n.level++; }
        else { missed++; n.level = Math.max(0, n.level - 1); }
      });
      const all = missed <= 1 && unheard <= 1;
      save();
      await sleep(1.6, id);
      // a missed note gets its pulse, now, and one hold
      for (let i = 0; i < res.length; i++) if (res[i].heard && !res[i].ok) {
        UI.focus(i);
        UI.cue('Listen', `“${EX.notes[i].word}”`);
        await pulse(EX.notes[i].midi, pulseOpts(i), id);
        UI.cue(SING(), 'Hold it.');
        if (await waitHeld(EX.notes[i].midi, 4, id)) UI.good(); else await walk(i, id);
        UI.focus(null);
      }
      if (all) {
        if (ST.speedIdx < 2) { ST.speedIdx++; save(); }
        else if (ST.notes.every(n => n.level >= 4)) { ST.pass = 'done'; save(); return true; }
      }
      if (await timeUp(id)) return false;
    }
  }

  // ------------------------------------------------------------------ the jump drill (?jump): one note after a lead-in
  // The track plays the bars before the note as recorded, to get into the key; nothing there is judged. Then the note:
  //   level 0  the track goes on through the note (his part sings it): sing with it, then hold it alone
  //   level 1  a hint: the note's first 150 ms and the chord under it, then hold it alone
  //   level 2  the track stops before the note: sing it from nothing, the trace is the only help
  // Two holds in a row move up a level, a miss moves down one.
  const JUMP_LEVELS = ['Note played', 'Just a hint', 'On your own'];
  async function jumpDrill(id) {
    const ti = EX.jump != null ? EX.jump : EX.notes.length - 1;
    const n = EX.notes[ti], T = n.midi;
    const pct = 100, k = 1;
    await loadClips(pct);
    ST.jump = ST.jump || { level: 0, streak: 0, tries: 0, holds: 0 };
    const J = ST.jump;
    const first = EX.meters.find(m => m.bar === EX.bars[0]);
    UI.focus(ti);
    for (;;) {
      UI.jumpInfo(J, JUMP_LEVELS);
      UI.cue('Get in the key', `Listen to bars ${EX.bars[0]}–${n.bar - 1}.`);
      const end = J.level === 0 ? n.t1 + 0.05 : J.level === 1 ? n.t0 + 0.35 : n.t0 - 0.02;
      const gains = () => ({ base: 1, list: [[n.t0, n.t1, J.level === 0 ? 1 : 0, J.level === 1]] });
      const c0 = playClip(pct, first.t0, end, gains, true);
      if (J.level < 2) Sim.heard(T, {});
      const beats = beatsOf().filter(b => b.t >= first.t0 - 1e-6 && b.t < n.t0 - 1e-6);
      await UI.beats(beats, c0, k, n.t0, id);
      UI.cue(SING(), J.level === 0 ? `“${n.word}”, with the track, then hold it.` : J.level === 1 ? `“${n.word}”, from the hint. Hold it.` : `“${n.word}”. Hold it.`);
      // judged once the phone is quiet again
      await sleep(Math.max(0, c0 + end * k - now()) + E.rtt + E.tail, id);
      UI.cue(SING(), 'Hold it.');
      const ok = await waitHeld(T, 3, id);
      J.tries++;
      if (ok) {
        UI.good(); J.holds++; J.streak++;
        if (J.streak >= 2 && J.level < 2) { J.level++; J.streak = 0; }
        UI.cue('Yes', J.level === 2 && J.streak ? 'On your own. Again.' : '');
      } else {
        const m = shown();
        UI.miss(m, T); J.streak = 0;
        if (J.level > 0) J.level--;
        UI.cue('Again', m == null ? 'I couldn’t hear you.' : UI.say(m, T));
      }
      save();
      Sim.cue('Stop');
      await sleep(1.6, id);
    }
  }

  // sessions are short: about three minutes, stopping only between notes or rounds
  let sessionStart = 0;
  async function timeUp(id) { alive(id); return now() - sessionStart > (SIM ? 180 * (+(Q.get('session') || 1)) : 180); }

  async function session(id) {
    sessionStart = now();
    ST.sessions++; save();
    UI.screen('run');
    const r = await measureRoom(id);
    if (r !== 'ok') {
      const go = await UI.ask(r === 'loud' ? 'Too noisy here' : 'Lots of other sound here',
        'Hum close to the phone, or try somewhere quieter.', 'Try anyway', 'Later');
      if (!go) { UI.screen('start'); return; }
    }
    if (E.heard === false) UI.note('Earbuds detected. Good.');
    if (Q.has('jump')) return jumpDrill(id);
    for (;;) {
      let finished = true;
      if (ST.pass === 'learn') finished = await learnPass(id);
      else if (ST.pass === 'review') finished = await reviewPass(id);
      else if (ST.pass === 'pairs') finished = await pairsPass(id);
      else if (ST.pass === 'time') finished = await timePass(id);
      else break;
      if (finished) { ST.pass = PASSES[PASSES.indexOf(ST.pass) + 1]; ST.idx = 0; save(); }
      if (!finished || (await timeUp(id))) break;
    }
    UI.done(ST);
  }

  // ------------------------------------------------------------------ simulated singer (?sim)
  const Sim = (() => {
    let pitch = null, goal = null, singing = true, wob = 0, learned = {}, plan = null, ready = 0, misses = 0;
    const rnd = (sd) => { let s = 0; for (let i = 0; i < 6; i++) s += Math.random(); return (s - 3) * sd / 0.7; };
    function start() { pitch = EX.notes[0].midi - 12 + rnd(0.3); goal = pitch; }
    function frame(t) {
      if (pitch == null) start();
      if (plan) { // singing back in time
        const seg = plan.find(s => t >= s[0] && t <= s[1]);
        return seg ? { midi: seg[2] + 0.15 * Math.sin(t * 6), voiced: true, rms: 0.05 } : { midi: 0, voiced: false, rms: 0.0002 };
      }
      if (!singing || t < ready) return { midi: 0, voiced: false, rms: 0.0002 };
      pitch += (goal - pitch) * 0.25;
      wob = 0.25 * Math.sin(t * 2 * Math.PI * 0.9) + rnd(0.08);
      return { midi: pitch + wob, voiced: true, rms: 0.05 };
    }
    return {
      frame,
      heard(m, o) { // a guide note: he follows if it's close, or if he has learned it
        if (!SIM) return;
        if (pitch == null) start();
        singing = true;
        const d = Math.abs(m - goal);
        if (d <= 1.5 && Math.random() < 0.85) goal = m;
        else if (learned[m] && Math.random() < 0.7) goal = m;
        else if (d > 1.5 && Math.random() < 0.15) goal = m;
      },
      cue(word) {
        if (!SIM) return;
        if (word === 'Stop' || word === 'Get in the key') singing = false;
        if (word === 'Sing' || word === 'Hum') {
          if (!singing) { singing = true; ready = now() + 0.3; const err = rnd(0.25) + (Math.random() < 0.12 ? -12 : 0); pitch = goal + err; goal = goal + (Math.abs(err) < 0.5 ? 0 : err * 0.5); }
        }
        if (word === 'Now the next') { const i = UI.cur(); if (i != null) { const m = EX.notes[i].midi; if (learned[m] && Math.random() < 0.6) goal = m; else if (Math.random() < 0.3) goal = m; } }
      },
      learnedAt(m) { learned[m] = true; },
      listen() {},
      echo(c0, k, ns) {
        if (!SIM) return;
        plan = EX.notes.map((n, i) => {
          const p = Math.min(0.95, 0.55 + 0.1 * ns[i].level + (learned[n.midi] ? 0.1 : 0));
          const m = Math.random() < p ? n.midi + rnd(0.15) : n.midi + (Math.random() < 0.5 ? -12 : -2);
          return [c0 + n.t0 * k, c0 + n.t1 * k, m];
        });
        const end = c0 + EX.meters[EX.meters.length - 2].t1 * k + 0.5;
        setTimeout(() => { plan = null; singing = false; }, (end - now()) * 1000 / RATE);
      },
    };
  })();

  // ------------------------------------------------------------------ UI
  const UI = (() => {
    let focusI = null, nextI = null, prevI = null, guideM = null, guideFrom = null, flashUntil = 0, flashKind = '', beat = null;
    const el = {};
    const LOG = [];
    function log(s) { LOG.push(`${now().toFixed(1)} ${s}`); if (LOG.length > 400) LOG.shift(); }
    window.TRAINER_LOG = LOG;
    function cue(word, hint) {
      el.cue.textContent = word; el.hint.textContent = hint || '';
      el.cue.dataset.kind = word === 'Stop' ? 'stop' : (word === 'Sing' || word === 'Hum') ? 'go' : word ? 'listen' : '';
      Sim.cue(word);
      log(`cue ${word} | ${hint || ''}`);
    }
    function dots() {
      el.dots.innerHTML = EX.notes.map((n, i) => {
        const s = ST.notes[i];
        const cls = [i === focusI ? 'cur' : '', i === nextI ? 'next' : '', s.solid ? 'solid' : ''].join(' ');
        return `<li class="${cls}"><span class="dot"></span><span class="w">${n.word}</span></li>`;
      }).join('');
      const names = { learn: 'Learn the notes', review: 'Check each note', pairs: 'Note to note', time: 'In time', done: 'Done' };
      el.pass.textContent = names[ST.pass] || '';
    }
    function focus(i, next, prev) {
      focusI = i; nextI = next == null ? null : next; prevI = prev == null ? null : prev;
      log(`focus ${i}${next != null ? ' next ' + next : ''}`);
      dots();
    }
    function guide(m, from) { guideM = m; guideFrom = from == null ? null : from; if (m != null) log(`pulse ${m}${from != null ? ' from ' + from : ''}`); }
    function good() { flashUntil = now() + 0.7; flashKind = 'good'; if (focusI != null) Sim.learnedAt(EX.notes[focusI].midi); log('good'); }
    function miss(m, T) { flashUntil = now() + 0.9; flashKind = 'miss'; log(`miss ${m == null ? '-' : m.toFixed(2)} vs ${T}`); }
    function wait(s) {
      el.cue.textContent = 'Wait'; el.cue.dataset.kind = 'stop'; el.hint.textContent = '';
      el.bar.hidden = false; el.bar.firstElementChild.style.transition = 'none'; el.bar.firstElementChild.style.width = '100%';
      requestAnimationFrame(() => { el.bar.firstElementChild.style.transition = `width ${s / RATE}s linear`; el.bar.firstElementChild.style.width = '0%'; });
      setTimeout(() => { el.bar.hidden = true; }, s * 1000 / RATE);
      log(`wait ${s}`);
    }
    function describe(m, T) {
      const e = (m - T) * 100;
      if (Math.abs(e) < 40) return ['On it', 'good'];
      if (Math.abs(e + 1200) < 60) return ['Right note, an octave down', 'oct'];
      if (Math.abs(e - 1200) < 60) return ['Right note, an octave up', 'oct'];
      if (Math.abs(e) < 100) return [`${Math.round(Math.abs(e))}¢ ${e < 0 ? 'low' : 'high'}`, 'near'];
      const st = Math.round(Math.abs(e) / 100);
      return [`${st} half step${st > 1 ? 's' : ''} ${e < 0 ? 'low' : 'high'}`, 'far'];
    }

    // ---- the live staff
    const STEPS = 'CDEFGAB';
    const diat = n => n.octave * 7 + STEPS.indexOf(n.step);
    function draw() {
      const svg = el.staff, W = svg.clientWidth || 360, H = 190, h = 6.5; // h: one staff position
      const T = focusI != null ? EX.notes[focusI] : null;
      const yOf = d => H / 2 - (d - 23) * h + 10; // E3 (23) near the middle of the view
      const lines = [18, 20, 22, 24, 26].map(d => `<line x1="12" x2="${W - 12}" y1="${yOf(d)}" y2="${yOf(d)}" class="ln"/>`).join('');
      let s = lines;
      const xNow = W * 0.7;
      const headAt = (n, x, cls, label) => {
        const d = diat(n), y = yOf(d);
        let led = '';
        for (let k = 16; k >= d; k -= 2) led += `<line x1="${x - 13}" x2="${x + 13}" y1="${yOf(k)}" y2="${yOf(k)}" class="ln"/>`;
        for (let k = 28; k <= d; k += 2) led += `<line x1="${x - 13}" x2="${x + 13}" y1="${yOf(k)}" y2="${yOf(k)}" class="ln"/>`;
        const acc = n.alter === -1 ? '♭' : n.alter === 1 ? '♯' : (EX.notes.some(o => o.step === n.step && o.alter) ? '♮' : '');
        return led + `<ellipse cx="${x}" cy="${y}" rx="8" ry="5.6" transform="rotate(-20 ${x} ${y})" class="${cls}"/>` +
          (acc ? `<text x="${x - 22}" y="${y + 6}" class="acc ${cls}">${acc}</text>` : '') +
          (label ? `<text x="${x}" y="${Math.max(yOf(d) + 26, yOf(16) + 24)}" class="lab" text-anchor="middle">${label}</text>` : '');
      };
      if (T) {
        const yT = yOf(diat(T));
        const yM = m => yT - (m - T.midi) * (7 / 12) * h;
        // his trace, last 3.5 s
        const t = now(), span = 3.5;
        const pts = E.frames.filter(f => f.t > t - span);
        let path = '', last = null, col = '';
        for (const f of pts) {
          if (!f.voiced || f.gated) { last = null; continue; }
          const x = 12 + (xNow - 12) * (1 - (t - f.t) / span), y = Math.max(4, Math.min(H - 4, yM(f.midi)));
          const k = describe(f.midi, T.midi)[1];
          path += last && last.k === k ? ` L${x.toFixed(1)},${y.toFixed(1)}` : `${path ? '"/>' : ''}<path class="tr ${k}" d="M${x.toFixed(1)},${y.toFixed(1)}`;
          last = { k };
        }
        if (path) s += path + '"/>';
        s += headAt(T, xNow, 'tgt', T.word);
        if (nextI != null) s += headAt(EX.notes[nextI], xNow + 46, 'nxt', '');
        // the guide's note, while it is sounding
        if (guideM != null) {
          const y = yM(guideM);
          s += `<rect x="${xNow + 24}" y="${y - 6}" width="12" height="12" transform="rotate(45 ${xNow + 30} ${y})" class="gd"/><text x="${xNow + 42}" y="${y + 4}" class="lab">me</text>`;
        }
        const m = shown();
        if (m != null) {
          const [txt, k] = describe(m, T.midi);
          const y = Math.max(8, Math.min(H - 8, yM(m)));
          s += `<circle cx="${xNow - 18}" cy="${y}" r="5" class="you ${k}"/>`;
          el.read.textContent = txt; el.read.dataset.kind = k;
          if (k === 'oct' && m < T.midi) s += `<line x1="${xNow - 18}" x2="${xNow - 18}" y1="${y - 8}" y2="${yT + 8}" class="up"/>`;
        } else { el.read.textContent = ' '; el.read.dataset.kind = ''; }
      } else {
        el.read.textContent = ' ';
      }
      if (beat) s += `<circle cx="${W - 24}" cy="22" r="${beat.down ? 12 : 8}" class="beat"/>`;
      svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
      svg.innerHTML = s;
      document.body.dataset.flash = now() < flashUntil ? flashKind : '';
      requestAnimationFrame(draw);
    }

    function screen(n) { for (const x of document.querySelectorAll('[data-screen]')) x.hidden = x.dataset.screen !== n; }
    function ask(title, text, yes, no) {
      return new Promise(r => {
        el.askT.textContent = title; el.askP.textContent = text; el.askY.textContent = yes; el.askN.textContent = no;
        el.ask.hidden = false;
        el.askY.onclick = () => { el.ask.hidden = true; r(true); };
        el.askN.onclick = () => { el.ask.hidden = true; r(false); };
        if (SIM) setTimeout(() => el.askY.click(), 50);
      });
    }
    function done(st) {
      if (Q.has('jump') && st.jump) {
        el.doneT.textContent = 'Done for now.';
        el.doneP.textContent = `${st.jump.holds} of ${st.jump.tries} held. Next time starts at: ${JUMP_LEVELS[st.jump.level].toLowerCase()}.`;
        screen('done'); log('session end jump'); return;
      }
      const solid = EX.notes.filter((n, i) => st.notes[i].solid).map(n => n.name);
      el.doneT.textContent = st.pass === 'done' ? 'All five, in time, on your own.' : 'Done for now.';
      const names = { learn: 'learning the notes', review: 'checking each note', pairs: 'note to note', time: 'in time' };
      el.doneP.textContent = st.pass === 'done' ? 'Come back any time to keep it fresh.' :
        `Next time: ${names[st.pass]}${st.pass === 'time' ? `, ${[60, 80, 100][st.speedIdx]}% speed` : ''}.` +
        (solid.length ? ` Solid so far: ${[...new Set(solid)].join(', ')}.` : '');
      screen('done');
      log('session end ' + JSON.stringify({ pass: st.pass, idx: st.idx }));
    }
    function round(pct, levels) { log(`round ${pct}% levels ${levels.join(',')}`); dots(); }
    async function beats(list, c0, k, end, id) {
      for (const b of list) {
        const at = c0 + b.t * k;
        if (b.t > end + 1e-6) break;
        await sleep(at - now(), id);
        beat = { down: b.n === 1 };
        el.cue.textContent = String(b.n); el.cue.dataset.kind = 'beat';
        setTimeout(() => { beat = null; }, 120 / RATE);
      }
      await sleep(c0 + end * k - now(), id);
      el.cue.textContent = '';
    }
    function results(res) {
      el.dots.querySelectorAll('li').forEach((li, i) => { li.dataset.res = !res[i].heard ? 'unheard' : res[i].ok ? 'ok' : 'miss'; });
      const bad = res.map((r, i) => r.heard && !r.ok ? `“${EX.notes[i].word}” ${describe(r.midi, EX.notes[i].midi)[0]}` : null).filter(Boolean);
      cue(bad.length ? 'Close' : res.every(r => r.heard) ? 'All of them' : 'Again', bad.join(' · ') || (res.every(r => r.heard) ? '' : 'Some notes were too quiet to hear.'));
      log('results ' + res.map(r => !r.heard ? '?' : r.ok ? 'ok' : r.midi.toFixed(1)).join(' '));
      setTimeout(() => el.dots.querySelectorAll('li').forEach(li => delete li.dataset.res), 2500 / RATE);
    }
    function note(t) { el.hint.textContent = t; }
    function jumpInfo(J, names) {
      el.pass.textContent = `${names[J.level]} · ${J.holds} of ${J.tries} held`;
      el.dots.hidden = true;
      log(`jump level ${J.level} streak ${J.streak} ${J.holds}/${J.tries}`);
    }
    const say = (m, T) => describe(m, T)[0];
    function init() {
      for (const k of ['cue', 'hint', 'staff', 'dots', 'pass', 'read', 'bar', 'ask', 'askT', 'askP', 'askY', 'askN', 'doneT', 'doneP']) el[k] = document.getElementById(k);
      dots();
      requestAnimationFrame(draw);
    }
    return { cue, focus, guide, good, miss, wait, screen, ask, done, round, beats, results, note, init, cur: () => focusI, log, jumpInfo, say };
  })();

  // ------------------------------------------------------------------ boot
  async function boot() {
    const r = await fetch('exercise.json');
    if (!r.ok) throw new Error(`exercise.json: ${r.status}`);
    EX = await r.json();
    ST = load();
    $('#title').textContent = EX.title.replace(/, m(\d+)-(\d+)$/, ', bars $1–$2');
    $('#text').textContent = EX.text || '';
    if (EX.score_png) $('#score').src = 'score.png'; else $('#score').hidden = true;
    UI.init();
    UI.screen('start');
    $('#resume').textContent = ST.sessions ? 'Picking up where you left off.' : '';
    if (Q.has('jump')) {
      const n = EX.notes[EX.jump != null ? EX.jump : EX.notes.length - 1];
      document.querySelector('[data-screen=start] .lead').textContent =
        `Bars ${EX.bars[0]}–${n.bar - 1} play to get you into the key. Then you sing “${n.word}” in bar ${n.bar}. The phone plays the note at first, then less, then not at all.`;
    }
    const go = async mode => {
      ST.mode = mode; save();
      const id = ++runId;
      try {
        if (!E.ac && !SIM && !window.__audioStarted) {
          window.__audioStarted = true;
          await startAudio();
          setInterval(tick, 40);
        } else if (SIM && !window.__audioStarted) { window.__audioStarted = true; setInterval(tick, 40 / RATE); }
        if (E.ac) await E.ac.resume();
        try { if (navigator.wakeLock) await navigator.wakeLock.request('screen'); } catch (e) {}
        await session(id);
      } catch (e) {
        if (e instanceof Stopped) return;
        console.error(e);
        UI.screen('start');
        $('#resume').textContent = e && e.name === 'NotAllowedError' ? 'The microphone is blocked. Allow it for this page in the browser’s site settings, then try again.' : 'Something went wrong: ' + (e && e.message);
      }
    };
    $('#go-sing').onclick = () => go('sing');
    $('#go-hum').onclick = () => go('hum');
    $('#again').onclick = () => go(ST.mode);
    $('#stop').onclick = () => { runId++; UI.done(ST); };
    $('#reset').onclick = () => { if ($('#reset').dataset.armed) { ST = freshState(); save(); location.reload(); } else { $('#reset').dataset.armed = '1'; $('#reset').textContent = 'Tap again to start over'; } };
    if (Q.has('auto')) go(Q.get('auto') || 'sing');
  }
  window.TRAINER = { get state() { return ST; }, E, now, playClip, voiceGains, loadClips, get EX() { return EX; } };
  boot().catch(e => { // a page that can't start says why, instead of staying blank
    console.error(e);
    const m = document.querySelector('main');
    const p = document.createElement('p');
    p.className = 'lead';
    p.textContent = location.protocol === 'file:' ?
      'This page has to be opened from a website (https://…), not as a file.' :
      'This page couldn’t load its exercise (exercise.json, the score and the tracks belong in the same folder as this page). ' + (e && e.message || '');
    m.appendChild(p);
  });
})();
