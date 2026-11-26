"""A narrated memorization lesson over a song's lyric sheet: build the timeline from a script, voice it, draw it,
encode it (one MP4 with chapters and a subtitle track, the .srt beside it).

    from memorize import lesson
    L = lesson.Lesson(sheet, lights_json, song_audio, script, cache_dir)
    L.build(); L.render(out_mp4)

The script is a list of segments, each a dict:
    {'say': [phrase, ...], 'chapter': ('Block by block', 'Verse 1'), 'header': str, 'spot': section or None,
     'mode': MODE}
        phrase: str, or dict(text=..., pulse=[(bar, word), ...], shade=section, spot=section, mode=MODE)
    {'sing': section name or None (the whole song), 'chapter': ..., 'header': ..., 'spot': ..., 'mode': MODE}
MODE: ('full',) | ('faded', section) | ('gone', section) | ('key',) | ('emoji',)
    faded/gone: that section's non-key words at FADED / 0; key: every non-key word gone;
    emoji: every word gone, key words' emoji only (enlarged).
A segment's mode, spot and shading come in over TRANS seconds from the segment before.
The page never moves (no camera).
"""
import hashlib, json, math, os, subprocess, sys, tempfile, shutil
from concurrent.futures import ProcessPoolExecutor
import numpy as np

from . import draw as D
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mp4out

# the Kokoro TTS folder (its .venv and kokoro_tts.py): from memorize/local.json {"tts_dir": ...} (git-ignored), else
# the KOKORO_TTS_DIR environment variable
_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local.json')
TTS_DIR = os.path.expanduser(json.load(open(_LOCAL))['tts_dir'] if os.path.exists(_LOCAL) else os.environ.get('KOKORO_TTS_DIR', ''))
VOICE, SPEED = 'af_heart', 1.2
SR = 48000
FPS = 30
TRANS = 0.6          # s: fades between states
FADED = 0.12
LEAD, TAIL = 2.5, 1.0   # s of music before a block's first syllable and after its last
GAP_SAY, GAP_SING_IN, GAP_SING_OUT = 0.45, 0.35, 0.7
EMOJI_GROW = 1.35


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


class Lesson:
    def __init__(self, sh, lights, song_audio, script, cache):
        self.sh, self.script, self.cache = sh, script, cache
        os.makedirs(cache, exist_ok=True)
        L = json.load(open(lights))['frames']
        self.lt = np.array([f['t'] for f in L])
        self.lit = [tuple(f['lit']) for f in L]
        self.song = self.load_song(song_audio)
        # each token's sung span, for block excerpts and for the bar shown
        first, last = {}, {}
        for i, f in enumerate(L):
            end = L[i + 1]['t'] if i + 1 < len(L) else f['t'] + 1
            for tid in f['lit']:
                first.setdefault(tid, f['t'])
                last[tid] = end
        self.first, self.last = first, last

    # ------------------------------------------------------------------ audio
    def load_song(self, path):
        wav = os.path.join(self.cache, 'song.wav')
        if not os.path.exists(wav):
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-vn', '-ac', '2', '-ar', str(SR), wav], check=True)
        import soundfile as sf
        x, sr = sf.read(wav, dtype='float32')
        assert sr == SR
        return x

    def tts(self, phrases):
        """One wav per segment (phrases joined by kokoro_tts.py), cached by text; returns (stereo 48k, marks)."""
        texts = [p if isinstance(p, str) else p['text'] for p in phrases]
        h = hashlib.sha1(json.dumps([texts, VOICE, SPEED]).encode()).hexdigest()[:16]
        base = os.path.join(self.cache, 'tts_' + h)
        if not os.path.exists(base + '.json'):
            js = base + '.in.json'
            json.dump(texts, open(js, 'w'))
            r = subprocess.run([os.path.join(TTS_DIR, '.venv/bin/python'), os.path.join(TTS_DIR, 'kokoro_tts.py'),
                                js, base + '.24k.wav', VOICE, str(SPEED)], capture_output=True, text=True, check=True)
            marks = json.loads(r.stdout.strip().splitlines()[-1])['marks']
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', base + '.24k.wav', '-ac', '2', '-ar', str(SR),
                            base + '.wav'], check=True)
            json.dump(dict(texts=texts, marks=marks), open(base + '.json', 'w'))
        import soundfile as sf
        x, _ = sf.read(base + '.wav', dtype='float32')
        return x, json.load(open(base + '.json'))['marks']

    # ------------------------------------------------------------------ timeline
    def span(self, section):
        if section is None:
            return 0.0, len(self.song) / SR
        ids = self.ids_of(section)
        a = min(self.first[i] for i in ids) - LEAD
        b = max(self.last[i] for i in ids) + TAIL
        return max(0.0, a), min(len(self.song) / SR, b)

    def ids_of(self, sec):
        """The tokens of a section, or of several (a tuple of names: a block such as a verse and its refrain)."""
        names = sec if isinstance(sec, tuple) else (sec,)
        return [i for s in self.sh.sections if s['name'] in names for i in s['ids']]

    def find_word(self, bar, word, which=0):
        """The tokens of a word in a bar. A word sung twice in one bar (two parts in turn): which=1 for the
        second, 'all' for every one."""
        sh = self.sh
        found = []
        for t in sh.S.W.tokens:
            if t['bar'] == str(bar) and t['syl'] in ('single', 'begin'):
                ids = sh.word_ids(t['id'])
                txt = ''.join(sh.tok[i]['text'] for i in ids).strip(',.?!;:').lower()
                if txt == word.lower():
                    found.append(ids)
        # the narration names key words: where the bar holds the word both bold and plain (the baritone's key
        # "still" beside the tenors' plain one), the bold ones
        bold = [ids for ids in found if any(sh.tok[i].get('bold') for i in ids)]
        found = bold or found
        if not found or (which != 'all' and which >= len(found)):
            raise ValueError(f'no word {word!r} (#{which}) in bar {bar}')
        return [i for ids in found for i in ids] if which == 'all' else found[which]

    def build(self):
        """Lay the segments end to end: their times, audio, and per-phrase actions."""
        t, segs, narr = 0.4, [], []
        for seg in self.script:
            s = dict(seg)
            if 'say' in seg:
                x, marks = self.tts(seg['say'])
                s['audio'] = x
                s['t0'], s['t1'] = t, t + len(x) / SR
                ph = []
                for j, p in enumerate(seg['say']):
                    p = {'text': p} if isinstance(p, str) else dict(p)
                    p['t0'] = t + marks[j]
                    p['t1'] = t + (marks[j + 1] if j + 1 < len(marks) else len(x) / SR)
                    p['pulse_ids'] = [i for bw in p.get('pulse', []) for i in self.find_word(*bw)]
                    ph.append(p)
                    narr.append((p['t0'], p['t1'], p['text']))
                s['phrases'] = ph
                t = s['t1'] + GAP_SAY
            else:
                t += GAP_SING_IN - GAP_SAY
                a, b = self.span(seg['sing'])
                s['song0'], s['song1'] = a, b
                s['t0'], s['t1'] = t, t + (b - a)
                t = s['t1'] + GAP_SING_OUT
            segs.append(s)
        self.segs, self.narr, self.total = segs, narr, t + 0.6
        # chapters: (label, t0, t1, subs)
        chs = []
        for s in segs:
            top, sub = s['chapter'] if isinstance(s['chapter'], tuple) else (s['chapter'], None)
            if not chs or chs[-1][0] != top:
                chs.append([top, s['t0'], s['t1'], []])
            chs[-1][2] = s['t1']
            if sub:
                if not chs[-1][3] or chs[-1][3][-1][0] != sub:
                    chs[-1][3].append([sub, s['t0'], s['t1']])
                chs[-1][3][-1][2] = s['t1']
        # chapters meet: each runs to the next one's start
        for i in range(len(chs)):
            chs[i][1] = 0.0 if i == 0 else chs[i][1]
            chs[i][2] = chs[i + 1][1] if i + 1 < len(chs) else self.total
            subs = chs[i][3]
            for j in range(len(subs)):
                subs[j][1] = chs[i][1] if j == 0 else subs[j][1]
                subs[j][2] = subs[j + 1][1] if j + 1 < len(subs) else chs[i][2]
        self.chapters = [(f'{n + 1}  {c[0]}', c[1], c[2], tuple(tuple(x) for x in c[3])) if c[3]
                         else (f'{n + 1}  {c[0]}', c[1], c[2]) for n, c in enumerate(chs)]
        return self

    # ------------------------------------------------------------------ state at a time
    def mode_alpha(self, mode):
        """(word alpha, emoji alpha, emoji scale) dicts for a mode."""
        sh = self.sh
        if mode[0] == 'full':
            return {}, {}, {}
        if mode[0] in ('faded', 'gone'):
            ids = self.ids_of(mode[1])
            a = FADED if mode[0] == 'faded' else 0.0
            return {i: a for i in ids if i not in sh.key}, {}, {}
        if mode[0] == 'key':
            return {i: 0.0 for i in sh.tok if i not in sh.key}, {}, {}
        if mode[0] == 'emoji':
            return ({i: 0.0 for i in sh.tok}, {i: 1.0 for i in sh.key if sh.tok[i].get('emoji')},
                    {i: EMOJI_GROW for i in sh.key if sh.tok[i].get('emoji')})
        raise ValueError(mode)

    def state_at(self, t):
        """(mode, spot, shaded sections) in force at t, and what was in force before the latest change, with the
        change's start time."""
        hist = []          # (time, mode, spot, shaded)
        mode, spot, shaded = ('full',), None, ()
        for s in self.segs:
            if s['t0'] > t:
                break
            m, sp = s.get('mode', ('full',)), s.get('spot')
            sd = s.get('shaded', shaded)
            hist.append((s['t0'], m, sp, sd))
            for p in s.get('phrases', []):
                if p['t0'] > t:
                    break
                if 'mode' in p or 'spot' in p or 'shade' in p:
                    m = p.get('mode', m)
                    sp = p.get('spot', sp)
                    if 'shade' in p:     # one section, or a tuple shaded together (a verse and its refrain)
                        sd = tuple(sd) + (p['shade'] if isinstance(p['shade'], tuple) else (p['shade'],))
                    hist.append((p['t0'], m, sp, sd))
            shaded = sd
        return hist

    def view(self, t):
        sh = self.sh
        hist = self.state_at(t)
        v = D.View(toc=self.chapters, now=t, shade=1.0)
        # words: blend the latest mode in from the one before it
        cur = hist[-1] if hist else (0, ('full',), None, ())
        # time since the current mode began
        m_start = cur[0]
        for h in reversed(hist):
            if h[1] == cur[1]:
                m_start = h[0]
            else:
                break
        m_prev = next((h[1] for h in reversed(hist) if h[0] < m_start), ('full',))
        k = smooth((t - m_start) / TRANS)
        a1, e1, g1 = self.mode_alpha(cur[1])
        a0, e0, g0 = self.mode_alpha(m_prev)
        for i in set(a1) | set(a0):
            v.alpha[i] = a0.get(i, 1.0) + (a1.get(i, 1.0) - a0.get(i, 1.0)) * k
        for i in set(e1) | set(e0):
            v.ealpha[i] = e0.get(i, v.alpha.get(i, 1.0)) + (e1.get(i, v.alpha.get(i, 1.0)) - e0.get(i, v.alpha.get(i, 1.0))) * k
        for i in set(g1) | set(g0):
            v.escale[i] = g0.get(i, 1.0) + (g1.get(i, 1.0) - g0.get(i, 1.0)) * k
        # spotlight: fades out of the old section, into the new
        s_start = cur[0]
        for h in reversed(hist):
            if h[2] == cur[2]:
                s_start = h[0]
            else:
                break
        s_prev = next((h[2] for h in reversed(hist) if h[0] < s_start), None)
        ks = smooth((t - s_start) / TRANS)
        if cur[2] and s_prev and s_prev != cur[2]:
            # straight from one block to another: the light moves (half out, half in)
            if ks < 0.5:
                v.spot, v.spot_k = (s_prev, cur[2]), 1.0
            else:
                v.spot, v.spot_k = (cur[2],), 1.0
        elif cur[2]:
            v.spot, v.spot_k = (cur[2],), ks
        elif s_prev:
            v.spot, v.spot_k = (s_prev,), 1 - ks
        v.spot = tuple(n for x in v.spot for n in (x if isinstance(x, tuple) else (x,)))
        # shading: each section fades in when it is first shaded; none before the first is named
        sd = cur[3]
        v.shade_each = {}
        for name in sd:
            t_on = next(h[0] for h in hist if name in h[3])
            v.shade_each[name] = smooth((t - t_on) / 0.5)
        # the segment we are in (or the gap after it)
        seg = None
        for s in self.segs:
            if s['t0'] <= t:
                seg = s
        if seg is not None:
            v.header = seg.get('header', '')
            if 'sing' in seg and seg['t0'] <= t < seg['t1']:
                st = seg['song0'] + (t - seg['t0'])
                j = int(np.searchsorted(self.lt, st + 5e-4, side='right')) - 1   # sample times are rounded to 0.1 ms
                if j >= 0:
                    v.lit = self.lit[j]
                    if v.lit:
                        v.bar = sh.tok[v.lit[0]]['bar']
                    else:
                        v.bar = self.bar_before(j)
            for p in seg.get('phrases', []):
                if p['pulse_ids'] and p['t0'] - 0.05 <= t < p['t1'] + 0.25:
                    u = t - p['t0']
                    g = smooth(u / 0.25) * (0.78 + 0.22 * math.cos(2 * math.pi * u / 1.1))
                    g *= 1 - smooth((t - p['t1']) / 0.25)
                    for i in p['pulse_ids']:
                        v.pulse[i] = max(v.pulse.get(i, 0), g)
        return v

    def bar_before(self, j):
        while j >= 0 and not self.lit[j]:
            j -= 1
        return self.sh.tok[self.lit[j][0]]['bar'] if j >= 0 else None

    # ------------------------------------------------------------------ audio mix
    def mix(self, path, music_lufs=None):
        n = int(self.total * SR)
        mus = np.zeros((n, 2), np.float32)
        voc = np.zeros((n, 2), np.float32)
        for s in self.segs:
            i0 = int(round(s['t0'] * SR))
            if 'say' in s:
                x = s['audio']
                voc[i0:i0 + len(x)] += x[:n - i0]
            else:
                a, b = int(round(s['song0'] * SR)), int(round(s['song1'] * SR))
                x = self.song[a:b].copy()
                f = int(0.3 * SR)
                if s['song0'] > 0.05:
                    x[:f] *= np.linspace(0, 1, f)[:, None]
                if s['song1'] < len(self.song) / SR - 0.05:
                    x[-f:] *= np.linspace(1, 0, f)[:, None]
                mus[i0:i0 + len(x)] += x[:n - i0]
        import soundfile as sf
        tmp = tempfile.mkdtemp()
        sf.write(os.path.join(tmp, 'v.wav'), voc, SR)
        sf.write(os.path.join(tmp, 'm.wav'), self.song, SR)
        lv, lm = lufs(os.path.join(tmp, 'v.wav')), lufs(os.path.join(tmp, 'm.wav'))
        g = 10 ** ((lm - lv) / 20)
        out = mus + voc * g
        peak = np.abs(out).max()
        if peak > 0.98:
            out *= 0.98 / peak
        sf.write(path, out, SR, subtype='PCM_16')
        shutil.rmtree(tmp, ignore_errors=True)
        return dict(voice_lufs=lv, music_lufs=lm, voice_gain_db=20 * math.log10(g), peak=float(peak))

    # ------------------------------------------------------------------ render
    def frame_times(self):
        ts = set(np.round(np.arange(0, self.total, 1 / FPS), 4))
        for s in self.segs:
            if 'sing' in s:
                for lt in self.lt:
                    if s['song0'] <= lt < s['song1']:
                        ts.add(round(s['t0'] + lt - s['song0'], 4))
            ts.update((round(s['t0'], 4), round(s['t1'], 4)))
        return sorted(t for t in ts if t < self.total)

    def render(self, out, workers=None, srt=True):
        times = self.frame_times()
        keys, runs = [], []
        for t in times:
            v = self.view(t)
            k = vkey(v)
            if runs and runs[-1][1] == k:
                continue
            runs.append((t, k, v))
        tmp = tempfile.mkdtemp(prefix='memlesson_')
        files = {}
        jobs = []
        for t, k, v in runs:
            if k not in files:
                files[k] = os.path.join(tmp, f'{len(files):06d}.png')
                jobs.append((files[k], v))
        print(f'{len(times)} sample times, {len(runs)} frames, {len(files)} distinct, {self.total / 60:.1f} min', flush=True)
        with ProcessPoolExecutor(max_workers=workers or max(1, (os.cpu_count() or 2) - 1),
                                 initializer=_init, initargs=(self.sh.args,)) as pool:
            for n, _ in enumerate(pool.map(_draw, jobs, chunksize=16)):
                if n % 500 == 0:
                    print(f'  drawn {n}/{len(jobs)}', flush=True)
        lines = ['ffconcat version 1.0']
        for j, (t, k, v) in enumerate(runs):
            nxt = runs[j + 1][0] if j + 1 < len(runs) else self.total
            lines += [f"file '{files[k]}'", 'option framerate 1000', f'duration {nxt - t:.4f}']
        lines += [f"file '{files[runs[-1][1]]}'", 'option framerate 1000']
        lst = os.path.join(tmp, 'frames.ffconcat')
        open(lst, 'w').write('\n'.join(lines) + '\n')
        wav = os.path.join(tmp, 'mix.wav')
        self.levels = self.mix(wav)
        body = out + '.body.mp4'
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst, '-i', wav,
                        '-map', '0:v', '-map', '1:a', '-fps_mode', 'vfr', '-video_track_timescale', '1000',
                        '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'stillimage', '-g', '60', '-crf', '18',
                        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-t', f'{self.total:.3f}',
                        *mp4out.FRAG, body], check=True)
        mp4out.finalize(body)
        # chapters and the narration as a subtitle track, by stream copy
        meta = os.path.join(tmp, 'chapters.txt')
        with open(meta, 'w') as f:
            f.write(';FFMETADATA1\n')
            for c in self.chapters:
                for lab, a, b in ([(c[0], c[1], c[2])] if len(c) < 4 else [(f'{c[0]}: {s[0]}', s[1], s[2]) for s in c[3]]):
                    f.write(f'[CHAPTER]\nTIMEBASE=1/1000\nSTART={int(a * 1000)}\nEND={int(b * 1000)}\ntitle={lab.strip()}\n')
        srt_path = os.path.splitext(out)[0] + '.srt'
        with open(srt_path, 'w') as f:
            for n, (a, b, txt) in enumerate(self.narr, 1):
                f.write(f'{n}\n{srtt(a)} --> {srtt(b)}\n{txt}\n\n')
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', body, '-i', srt_path, '-f', 'ffmetadata', '-i', meta,
                        '-map', '0:v', '-map', '0:a', '-map', '1:s', '-map_metadata', '2', '-map_chapters', '2',
                        '-c', 'copy', '-c:s', 'mov_text', '-metadata:s:s:0', 'language=eng',
                        '-movflags', '+faststart', out], check=True)
        os.remove(body)
        shutil.rmtree(tmp, ignore_errors=True)
        return out


def vkey(v):
    r = lambda d: tuple(sorted((k, round(x, 3)) for k, x in d.items()))
    return (tuple(v.lit), r(v.alpha), r(v.ealpha), r(v.escale), r(v.pulse), tuple(v.spot), round(v.spot_k, 3),
            r(getattr(v, 'shade_each', {})), v.header, v.bar,
            next((c[0] for c in v.toc if c[1] <= v.now < c[2]), None), int(v.now * 2))   # playhead moves 0.5 s steps


_SH = None


def _init(args):
    global _SH
    _SH = D.Sheet(*args)


def _draw(job):
    path, v = job
    D.draw(_SH, v, path)


def lufs(path):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', path, '-af', 'ebur128', '-f', 'null', '-'],
                       capture_output=True, text=True)
    lines = [l for l in r.stderr.splitlines() if l.strip().startswith('I:')]
    return float(lines[-1].split()[1])


def srtt(t):
    ms = int(round(t * 1000))
    return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}'
