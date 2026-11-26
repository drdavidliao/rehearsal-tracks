// Pitch of one sung frame, for low male voices on a phone mic.
//
// 1. Period by McLeod's normalised square difference (NSDF), computed with an FFT. A period is found from the
//    waveform's repetition, so it is there even when the fundamental itself is weak or filtered out (phone mics roll
//    off below ~100-150 Hz), as long as the harmonics are.
// 2. Octave check on the spectrum, both ways:
//    - is the true pitch half of it? energy at f/2, 3f/2, 5f/2 ... (the odd multiples of f/2) besides f's own harmonics
//    - is the true pitch double it? f's odd harmonics (f, 3f, 5f ...) nearly absent while its even ones are strong
// 3. Voicing: clarity (the NSDF peak) and level over the measured noise floor.
//
// detect(frame, sr, opts) -> {hz, midi, clarity, rms, voiced, why}
(function (root) {
  'use strict';

  // ---- radix-2 FFT, in place, on Float64Arrays ----
  const fftCache = {};
  function fftTables(n) {
    if (fftCache[n]) return fftCache[n];
    const rev = new Uint32Array(n), bits = Math.log2(n);
    for (let i = 0; i < n; i++) {
      let r = 0;
      for (let b = 0; b < bits; b++) r |= ((i >> b) & 1) << (bits - 1 - b);
      rev[i] = r;
    }
    const cos = new Float64Array(n / 2), sin = new Float64Array(n / 2);
    for (let i = 0; i < n / 2; i++) { cos[i] = Math.cos(-2 * Math.PI * i / n); sin[i] = Math.sin(-2 * Math.PI * i / n); }
    return (fftCache[n] = { rev, cos, sin });
  }
  function fft(re, im) {
    const n = re.length, { rev, cos, sin } = fftTables(n);
    for (let i = 0; i < n; i++) {
      const j = rev[i];
      if (j > i) { let t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
    }
    for (let size = 2; size <= n; size <<= 1) {
      const half = size >> 1, step = n / size;
      for (let i = 0; i < n; i += size) {
        for (let j = 0, k = 0; j < half; j++, k += step) {
          const a = i + j, b = a + half;
          const tr = re[b] * cos[k] - im[b] * sin[k], ti = re[b] * sin[k] + im[b] * cos[k];
          re[b] = re[a] - tr; im[b] = im[a] - ti; re[a] += tr; im[a] += ti;
        }
      }
    }
  }

  const hzToMidi = hz => 69 + 12 * Math.log2(hz / 440);
  const midiToHz = m => 440 * Math.pow(2, (m - 69) / 12);

  // ---- NSDF via autocorrelation ----
  function nsdf(x, maxLag) {
    const n = x.length, N = 1 << Math.ceil(Math.log2(2 * n));
    const re = new Float64Array(N), im = new Float64Array(N);
    for (let i = 0; i < n; i++) re[i] = x[i];
    fft(re, im);
    for (let i = 0; i < N; i++) { re[i] = re[i] * re[i] + im[i] * im[i]; im[i] = 0; }
    fft(re, im); // real input, symmetric: forward FFT of the power spectrum gives N * autocorrelation
    const out = new Float64Array(maxLag + 1);
    let m = 0;
    for (let i = 0; i < n; i++) m += 2 * x[i] * x[i];
    for (let t = 0; t <= maxLag; t++) {
      if (t > 0) m -= x[t - 1] * x[t - 1] + x[n - t] * x[n - t];
      const r = re[t] / N;
      out[t] = m > 0 ? 2 * r / m : 0;
    }
    return out;
  }

  // ---- magnitude spectrum (Hann) for the octave check ----
  function spectrum(x) {
    const n = x.length, N = 1 << Math.ceil(Math.log2(n)) + 1; // zero-pad x2 for finer bins
    const re = new Float64Array(N), im = new Float64Array(N);
    for (let i = 0; i < n; i++) re[i] = x[i] * (0.5 - 0.5 * Math.cos(2 * Math.PI * i / (n - 1)));
    fft(re, im);
    const mag = new Float64Array(N / 2);
    for (let i = 0; i < N / 2; i++) mag[i] = Math.hypot(re[i], im[i]);
    return { mag, binHz: null, N };
  }
  // strongest magnitude within +-tol (fraction) of hz
  function peakNear(spec, sr, hz, tol) {
    const bin = hz * spec.N / sr, w = Math.max(1, Math.round(bin * tol));
    let best = 0;
    for (let b = Math.max(1, Math.round(bin) - w); b <= Math.round(bin) + w && b < spec.mag.length; b++)
      if (spec.mag[b] > best) best = spec.mag[b];
    return best;
  }
  // energy in a harmonic series k*f for k in ks, below fmax
  function seriesEnergy(spec, sr, f, ks, fmax) {
    let e = 0;
    for (const k of ks) { const h = k * f; if (h > fmax) break; const p = peakNear(spec, sr, h, 0.025); e += p * p; }
    return e;
  }
  const ODD = [1, 3, 5, 7, 9, 11, 13, 15], EVEN = [2, 4, 6, 8, 10, 12, 14, 16], ALL = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];

  function detect(x, sr, opts) {
    opts = opts || {};
    const fmin = opts.fmin || 45, fmax = opts.fmax || 500;
    const noise = opts.noiseRms || 0;
    let s = 0, mean = 0;
    for (let i = 0; i < x.length; i++) mean += x[i];
    mean /= x.length;
    let y = new Float64Array(x.length);
    for (let i = 0; i < x.length; i++) y[i] = x[i] - mean;
    // optional low cut (2 poles) against rumble: the period survives in the harmonics
    if (opts.highpass) {
      const al = 1 / (1 + 2 * Math.PI * opts.highpass / sr);
      for (let p = 0; p < 2; p++) {
        let px = 0, py = 0;
        for (let i = 0; i < y.length; i++) { py = al * (py + y[i] - px); px = y[i]; y[i] = py; }
      }
      y = y.subarray(256); // drop the filter's settling
    }
    for (let i = 0; i < y.length; i++) s += y[i] * y[i];
    const rms = Math.sqrt(s / y.length);
    const res = { hz: 0, midi: 0, clarity: 0, rms, voiced: false, why: '' };
    if (rms < Math.max(1e-4, noise * (opts.noiseFactor || 2.5))) { res.why = 'quiet'; return res; }

    const minLag = Math.floor(sr / fmax), maxLag = Math.min(Math.ceil(sr / fmin), (y.length >> 1));
    const d = nsdf(y, maxLag);
    // key maxima: highest point between each positive-going and the next negative-going zero crossing
    const peaks = [];
    let t = 1;
    while (t < maxLag && d[t] > 0) t++; // skip the lag-0 lobe
    while (t < maxLag) {
      while (t < maxLag && d[t] <= 0) t++;
      let bestT = -1, bestV = -Infinity;
      while (t < maxLag && d[t] > 0) { if (d[t] > bestV && t >= minLag) { bestV = d[t]; bestT = t; } t++; }
      if (bestT > 0 && bestT < maxLag) peaks.push([bestT, bestV]);
    }
    if (!peaks.length) { res.why = 'no period'; return res; }
    const top = Math.max(...peaks.map(p => p[1]));
    const k = opts.k || 0.88;
    const [pt, pv] = peaks.find(p => p[1] >= k * top);
    // parabolic interpolation
    const a = d[pt - 1], b = d[pt], c = d[pt + 1];
    const den = a - 2 * b + c;
    const shift = den !== 0 ? 0.5 * (a - c) / den : 0;
    let hz = sr / (pt + shift);
    res.clarity = pv;

    // octave check
    const spec = spectrum(y);
    const fTop = Math.min(sr / 2 - 100, 4000);
    const own = seriesEnergy(spec, sr, hz, ALL, fTop);
    // (a) true pitch an octave lower? odd multiples of hz/2 carry energy
    if (hz / 2 >= fmin) {
      const sub = seriesEnergy(spec, sr, hz / 2, ODD, fTop);
      const lagOk = 2 * (pt + shift) <= maxLag ? d[Math.round(2 * (pt + shift))] > 0.5 * pv : true;
      if (sub > (opts.subRatio || 0.18) * own && lagOk) { hz /= 2; res.why = 'octave down by spectrum'; }
    }
    // (b) true pitch an octave higher? hz's odd harmonics nearly gone, even ones strong
    if (!res.why && hz * 2 <= fmax) {
      const odd = seriesEnergy(spec, sr, hz, ODD, fTop), even = seriesEnergy(spec, sr, hz, EVEN, fTop);
      if (odd < (opts.oddRatio || 0.06) * even) { hz *= 2; res.why = 'octave up by spectrum'; }
    }
    res.hz = hz;
    res.midi = hzToMidi(hz);
    res.voiced = pv >= (opts.minClarity || 0.75);
    if (!res.voiced) res.why = 'unclear';
    return res;
  }

  // ---- a sung-vowel synth (glottal pulses through vowel formants); the app's guide voice and the tests' singer ----
  // Renders into a Float32Array. f0 may be a number or a function of time (s).
  const VOWELS = { ah: [[700, 80, 1], [1220, 90, 0.5], [2600, 120, 0.25]],
                   oo: [[320, 60, 1], [800, 80, 0.3], [2240, 120, 0.1]],
                   ee: [[300, 60, 1], [2300, 100, 0.45], [3000, 120, 0.3]] };
  function synthVoice(sr, dur, f0, o) {
    o = o || {};
    const n = Math.round(sr * dur), out = new Float32Array(n);
    const forms = VOWELS[o.vowel || 'ah'];
    const keepFund = o.fundamental !== false;
    const nh = o.harmonics || 40;
    const tilt = o.tilt || 1.6; // spectral rolloff of the source, 1/k^tilt
    const even = o.evenGain == null ? 1 : o.evenGain;
    let ph = 0;
    const vib = o.vibrato || 0, vibHz = o.vibratoHz || 5.5, jitter = o.jitter || 0;
    let jit = 0;
    for (let i = 0; i < n; i++) {
      const tt = i / sr;
      let f = typeof f0 === 'function' ? f0(tt) : f0;
      if (jitter) { jit += (Math.random() - 0.5) * jitter * 0.02; jit *= 0.995; }
      f *= Math.pow(2, (vib * Math.sin(2 * Math.PI * vibHz * tt) + jit) / 1200);
      ph += 2 * Math.PI * f / sr;
      let v = 0;
      for (let k = keepFund ? 1 : 2; k <= nh; k++) {
        const hk = k * f;
        if (hk > sr / 2 - 200) break;
        let g = 1 / Math.pow(k, tilt);
        let fg = 0.04;
        for (const [fc, bw, amp] of forms) fg += amp / (1 + Math.pow((hk - fc) / bw, 2));
        g *= fg;
        if (k % 2 === 0) g *= even;
        v += g * Math.sin(k * ph);
      }
      out[i] = v;
    }
    let peak = 0;
    for (let i = 0; i < n; i++) peak = Math.max(peak, Math.abs(out[i]));
    const amp = o.amp || 0.3;
    for (let i = 0; i < n; i++) out[i] *= amp / (peak || 1);
    return out;
  }

  root.Pitch = { detect, hzToMidi, midiToHz, synthVoice, nsdf, fft };
})(typeof window !== 'undefined' ? window : globalThis);
