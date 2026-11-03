#include "engine.h"
#include <AudioToolbox/AudioToolbox.h>
#include <CoreAudio/CoreAudio.h>
#include <rubberband/RubberBandStretcher.h>
#define SIGNALSMITH_USE_ACCELERATE
#include "signalsmith-stretch.h"
#include <algorithm>
#include <atomic>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <functional>
#include <map>
#include <random>
#include <memory>
#include <mutex>
#include <string>
#include <sys/stat.h>
#include <thread>
#include <vector>

namespace fs = std::filesystem;
using RubberBand::RubberBandStretcher;

namespace {

// ------------------------------------------------------------------------------------------- the mix, as specified
const float TRIM_DB[STEM_COUNT] = {0, -3, -3, 0, 0};
const float PAN_KNOB[STEM_COUNT] = {-45, -15, 15, 45, 0};    // Logic's pan knob, -64 to +63
// the boost each heard voice gets, by how many are heard
const float FEATURE_DB[5] = {0, 6, 3, 1.5f, 0};
// files with one voice each: what's heard is at 0 dB and the other voices stay faintly there
const float BEHIND_DB = -18;
std::atomic<bool> g_isolated{false};
std::atomic<float> g_master_db{-3};

float db(float d) { return std::pow(10.f, d / 20.f); }

// A stereo stem panned as a balance with a constant-power law, unity at centre
void pan_gains(float knob, float &l, float &r) {
    if (knob == 0) { l = r = 1; return; }
    float pos = std::clamp(knob / 64.f, -1.f, 1.f), th = (pos + 1) * float(M_PI) / 4;
    l = std::cos(th) * float(M_SQRT2);
    r = std::sin(th) * float(M_SQRT2);
}

using Stem = std::shared_ptr<const std::vector<float>>;

// One stem at one tempo, as far as it has been rendered: frames from..to of out, interleaved stereo, indexed by the
// frame's place in the whole take. The renderer writes ahead of `to` and then publishes it, so the mixer never waits on a lock.
struct Track {
    uint64_t key = 0;       // which audio this is: the stem, its corrections, the tempo and the method
    double speed = 1;
    int64_t frames = 0;
    int64_t from = 0;
    std::atomic<int64_t> to{0};
    std::atomic<bool> cancel{false};
    const float *data = nullptr;
    float *owned = nullptr;
    Stem holder;
    ~Track() { free(owned); }
    bool covers(int64_t at, int64_t n = 1) const { return at >= from && std::min(at + n, frames) <= to.load(std::memory_order_acquire); }
};
using TrackP = std::shared_ptr<Track>;

// the stems of one tempo: each has a render of the whole, and while that is still behind, one from where the playhead went
struct Take {
    double speed = 1;
    int64_t frames = 0;
    double swap_at = -1;    // in seconds of the original audio: the mixer moves to this take there, or at once if negative
    TrackP full[STEM_COUNT], ahead[STEM_COUNT];
    bool same_as(const Take &o) const {
        if (speed != o.speed) return false;
        for (int i = 0; i < STEM_COUNT; i++) if (full[i] != o.full[i] || ahead[i] != o.ahead[i]) return false;
        return true;
    }
};

struct Fix { int stem; double start, end; bool mute; double semitones; };

int g_rate = 44100;
int64_t g_frames = 0;
std::atomic<Take *> g_current{nullptr}, g_pending{nullptr};
std::atomic<int64_t> g_seek{-1};      // a seek, in frames of the original audio
std::atomic<int64_t> g_loop_a{-1}, g_loop_b{-1};     // in frames of the original audio
std::atomic<bool> g_waiting{false};    // the playhead has reached audio that is not rendered yet
std::atomic<int64_t> g_pos{0};        // frames into the current take
std::atomic<double> g_cur_speed{1};
std::atomic<bool> g_playing{false};
std::atomic<int> g_voices{VOICES_ALL};
std::atomic<int> g_swapped{0};
float g_env = 0;                       // 0..1, moved by the mixer: a seek or swap happens at 0, so nothing clicks
float g_gain[STEM_COUNT][2];
bool g_gain_set = false;
const float ENV_STEP = 1.f / 256;
const float GAIN_SMOOTH = 0.004f;

AudioUnit g_unit = nullptr;
AudioDeviceID g_device = 0;           // 0: the system default
std::string g_device_uid;
std::atomic<double> g_latency{0};

// past 0.9 a smooth curve to 1, so a boosted part can't hard-clip; below that the samples are untouched
inline float soft(float x) {
    float a = std::fabs(x);
    if (a <= 0.9f) return x;
    float y = 0.9f + 0.1f * std::tanh((a - 0.9f) / 0.1f);
    return x < 0 ? -y : y;
}

// ------------------------------------------------------------------------------------------- files
bool read_file(const char *path, std::vector<float> &out, int &rate, int64_t &frames) {
    CFURLRef url = CFURLCreateFromFileSystemRepresentation(nullptr, (const UInt8 *)path, strlen(path), false);
    ExtAudioFileRef f = nullptr;
    OSStatus st = ExtAudioFileOpenURL(url, &f);
    CFRelease(url);
    if (st) { fprintf(stderr, "can't open %s\n", path); return false; }
    AudioStreamBasicDescription in{}, fmt{};
    UInt32 sz = sizeof(in);
    ExtAudioFileGetProperty(f, kExtAudioFileProperty_FileDataFormat, &sz, &in);
    SInt64 n = 0; sz = sizeof(n);
    ExtAudioFileGetProperty(f, kExtAudioFileProperty_FileLengthFrames, &sz, &n);
    fmt.mSampleRate = in.mSampleRate; fmt.mFormatID = kAudioFormatLinearPCM;
    fmt.mFormatFlags = kAudioFormatFlagIsFloat | kAudioFormatFlagIsPacked;
    fmt.mBitsPerChannel = 32; fmt.mChannelsPerFrame = 2; fmt.mFramesPerPacket = 1; fmt.mBytesPerFrame = fmt.mBytesPerPacket = 8;
    ExtAudioFileSetProperty(f, kExtAudioFileProperty_ClientDataFormat, sizeof(fmt), &fmt);
    out.assign(size_t(n) * 2, 0.f);
    int64_t done = 0;
    while (done < n) {
        AudioBufferList bl; bl.mNumberBuffers = 1; bl.mBuffers[0].mNumberChannels = 2;
        UInt32 want = UInt32(std::min<int64_t>(n - done, 1 << 16));
        bl.mBuffers[0].mDataByteSize = want * 8; bl.mBuffers[0].mData = out.data() + done * 2;
        if (ExtAudioFileRead(f, &want, &bl) || !want) break;
        done += want;
    }
    ExtAudioFileDispose(f);
    rate = int(in.mSampleRate); frames = done;
    return done == n;
}

// ------------------------------------------------------------------------------------------- corrections and tempos
std::string g_cache_root, g_paths[STEM_COUNT];
std::mutex g_req_mutex;
std::atomic<double> g_want{1};
std::atomic<uint64_t> g_gen{0};
std::atomic<int> g_busy{0};
std::thread &g_worker = *new std::thread;     // never destroyed: a render may be running when the app quits
std::atomic<int> g_method_voices{METHOD_R3_APART}, g_method_inst{METHOD_R3_APART};
std::atomic<int64_t> g_full_total{0}, g_full_done{0};
std::atomic<int> g_full_active{0};
std::mutex g_fix_mutex;
std::vector<Fix> g_fixes;
// the worker's: each stem as loaded, and with its corrections
Stem g_base[STEM_COUNT], g_source[STEM_COUNT];
uint64_t g_source_key[STEM_COUNT];

uint64_t stem_key(int i, const std::vector<Fix> &fixes) {
    uint64_t h = 1469598103934665603ULL;
    auto mix = [&](const void *p, size_t n) { auto c = (const unsigned char *)p; while (n--) { h ^= *c++; h *= 1099511628211ULL; } };
    const std::string &p = g_paths[i];
    mix(p.data(), p.size());
    struct stat s{};
    if (!stat(p.c_str(), &s)) { mix(&s.st_size, sizeof s.st_size); mix(&s.st_mtimespec.tv_sec, sizeof s.st_mtimespec.tv_sec); }
    for (const Fix &f : fixes) {
        if (f.stem != i) continue;
        mix(&f.start, sizeof f.start); mix(&f.end, sizeof f.end); mix(&f.semitones, sizeof f.semitones);
        char m = f.mute; mix(&m, 1);
    }
    return h;
}

fs::path take_path(uint64_t key) {
    char d[32];
    snprintf(d, sizeof d, "%016llx.f32", (unsigned long long)key);
    return fs::path(g_cache_root) / "takes" / d;
}

bool load_cached(Track &t) {
    fs::path p = take_path(t.key);
    std::error_code ec; auto bytes = fs::file_size(p, ec);
    if (ec || bytes < size_t(t.frames) * 8) return false;
    t.owned = (float *)malloc(bytes);
    FILE *f = fopen(p.c_str(), "rb");
    size_t got = f ? fread(t.owned, 1, bytes, f) : 0;
    if (f) fclose(f);
    if (got != bytes) return false;
    t.data = t.owned;
    t.to = t.frames;
    fs::last_write_time(p, fs::file_time_type::clock::now(), ec);
    return true;
}

void save_cached(const Track &t) {
    fs::path p = take_path(t.key), tmp = p;
    tmp += ".tmp";
    std::error_code ec; fs::create_directories(p.parent_path(), ec);
    FILE *f = fopen(tmp.c_str(), "wb");
    if (!f) return;
    fwrite(t.data, 8, size_t(t.frames), f);
    fclose(f);
    fs::rename(tmp, p, ec);
    // the cache keeps the takes used last, up to 4 GB. Stems finish together, so one at a time, and a file may be mid-rename
    static std::mutex tidying;
    std::lock_guard<std::mutex> lk(tidying);
    struct Entry { fs::file_time_type when; uintmax_t size; fs::path path; };
    std::vector<Entry> all;
    for (fs::recursive_directory_iterator it(fs::path(g_cache_root), ec), end; !ec && it != end; it.increment(ec)) {
        std::error_code e1, e2;
        auto when = it->last_write_time(e1);
        auto size = it->file_size(e2);
        if (!e1 && !e2 && it->path().extension() == ".f32") all.push_back({when, size, it->path()});
    }
    std::sort(all.begin(), all.end(), [](const Entry &a, const Entry &b) { return a.when > b.when; });
    uintmax_t total = 0;
    for (const Entry &e : all) {
        total += e.size;
        if (total > 4ull << 30) fs::remove(e.path, ec);
    }
}

// ----------------------------------------------- the methods. Each renders src, from source frame `start` to its end, into a track

// writes out frames as they come, at their place in the take, and says how far it has got
struct Writer {
    Track &t;
    float *buf;
    std::atomic<int64_t> *progress;
    int64_t reported = 0;
    void put(int64_t at, const float *l, const float *r, int64_t n) {
        for (int64_t i = 0; i < n; i++) {
            int64_t j = at + i;
            if (j < t.from || j >= t.frames) continue;
            buf[size_t(j) * 2] = l[i]; buf[size_t(j) * 2 + 1] = r[i];
        }
    }
    void publish(int64_t upto) {
        upto = std::min(upto, t.frames);
        if (upto > t.to.load(std::memory_order_relaxed)) t.to.store(upto, std::memory_order_release);
        if (progress && upto > t.from + reported) { *progress += upto - t.from - reported; reported = upto - t.from; }
    }
};

// One whole pass of Rubber Band R3 in offline mode. A pitch scale other than 1 is for one note's span.
RubberBandStretcher::Options r3_options(bool together, bool pitched) {
    RubberBandStretcher::Options o = RubberBandStretcher::OptionProcessOffline | RubberBandStretcher::OptionEngineFiner;
    if (together) o |= RubberBandStretcher::OptionChannelsTogether;
    if (pitched) o |= RubberBandStretcher::OptionFormantPreserved;
    return o;
}

template <class Out, class Stop>
void r3_pass(const float *in, int64_t n, double speed, double pitch, bool together, Out out, Stop stop) {
    const int BLOCK = 4096;
    RubberBandStretcher s(size_t(g_rate), 2, r3_options(together, pitch != 1), 1.0 / speed, pitch);
    s.setExpectedInputDuration(size_t(n));
    s.setMaxProcessSize(BLOCK);
    std::vector<float> a(BLOCK), b(BLOCK), l(BLOCK * 2), r(BLOCK * 2);
    float *ptr[2] = {a.data(), b.data()};
    float *rp[2] = {l.data(), r.data()};
    auto fill = [&](int64_t at, int m) {
        for (int i = 0; i < m; i++) { a[i] = in[size_t(at + i) * 2]; b[i] = in[size_t(at + i) * 2 + 1]; }
    };
    for (int64_t at = 0; at < n; at += BLOCK) {
        int m = int(std::min<int64_t>(BLOCK, n - at));
        fill(at, m);
        s.study(ptr, size_t(m), at + m >= n);
        if (stop()) return;
    }
    int64_t written = 0;
    auto drain = [&] {
        int av;
        while ((av = s.available()) > 0) {
            size_t got = s.retrieve(rp, size_t(std::min(av, BLOCK * 2)));
            out(written, l.data(), r.data(), int64_t(got));
            written += int64_t(got);
        }
    };
    int64_t at = 0;
    while (at < n) {
        int m = int(std::min<int64_t>({int64_t(BLOCK), n - at, int64_t(std::max<size_t>(s.getSamplesRequired(), 1))}));
        fill(at, m);
        s.process(ptr, size_t(m), at + m >= n);
        at += m;
        drain();
        if (stop()) return;
    }
    while (s.available() >= 0) {
        drain();
        if (s.available() == 0) std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
}

void render_r3(const float *in, int64_t n, Writer &w, double speed, int64_t start, bool together) {
    // a second of sound before the start, for the stretcher to settle into
    const int64_t a = std::max<int64_t>(0, start - g_rate);
    const int64_t base = int64_t(double(a) / speed);
    r3_pass(in + a * 2, n - a, speed, 1.0, together,
            [&](int64_t at, const float *l, const float *r, int64_t m) { w.put(base + at, l, r, m); w.publish(base + at + m); },
            [&] { return w.t.cancel.load(); });
}

void render_signalsmith(const float *in, int64_t n, Writer &w, double speed, int64_t start, int block_ms, int interval_ms) {
    signalsmith::stretch::SignalsmithStretch<float> s;
    if (block_ms) s.configure(2, g_rate * block_ms / 1000, g_rate * interval_ms / 1000);
    else s.presetDefault(2, float(g_rate));
    const int inLat = s.inputLatency(), outLat = s.outputLatency();
    const int64_t a = std::max<int64_t>(0, start - g_rate);
    const int STEP = 1024;
    const int inMax = int(STEP * speed) + 4;
    const size_t cap = size_t(std::max(inMax, inLat)) + 4;
    std::vector<float> il(cap), ir(cap), ol(STEP), or_(STEP);
    float *ip[2] = {il.data(), ir.data()}, *op[2] = {ol.data(), or_.data()};
    int64_t cursor = a;
    auto fill = [&](int m) {
        for (int i = 0; i < m; i++, cursor++) {
            il[size_t(i)] = cursor < n ? in[size_t(cursor) * 2] : 0;
            ir[size_t(i)] = cursor < n ? in[size_t(cursor) * 2 + 1] : 0;
        }
    };
    fill(inLat);
    s.seek(ip, inLat, speed);
    // the output's first frame is outLat frames behind the time the stretcher is at, which is a
    const int64_t base = int64_t(double(a) / speed) - outLat;
    double wanted = 0;
    int64_t written = 0;
    while (base + written < w.t.frames && !w.t.cancel.load()) {
        wanted += STEP * speed;
        int m = std::min(int(wanted), inMax);
        wanted -= m;
        fill(m);
        s.process(ip, m, op, STEP);
        w.put(base + written, ol.data(), or_.data(), STEP);
        written += STEP;
        w.publish(base + written);
    }
}

// Pitch-synchronous overlap-add for a stem with one voice. Where it finds a steady pitch it cuts the sound into two-period
// grains around marks a period apart and lays them out at the new spacing, repeating or dropping whole periods, so each
// period stays as it was sung. Elsewhere (consonants, breaths) it does the same with short grains at a fixed spacing.
struct Marks {
    std::vector<int64_t> at;
    std::vector<int> half;     // half a grain: a period, or the fixed spacing
};

Marks find_marks(const float *in, int64_t n) {
    // a mono copy at an eighth of the rate is plenty to find a pitch: the marks then find their own places at the full rate
    const int D = 8, W = g_rate / D / 25, HOP = g_rate / D / 100;
    const int tmin = g_rate / D / 1200, tmax = g_rate / D / 65;
    const int64_t nd = n / D;
    std::vector<float> x((size_t)nd);
    for (int64_t i = 0; i < nd; i++) {
        float v = 0;
        for (int k = 0; k < D; k++) v += in[size_t(i * D + k) * 2] + in[size_t(i * D + k) * 2 + 1];
        x[size_t(i)] = v / float(2 * D);
    }
    // YIN at each hop: the period, or 0 where there isn't a steady one
    const int64_t frames = std::max<int64_t>(0, (nd - W - tmax) / HOP);
    std::vector<int> period(size_t(frames) + 1, 0);
    std::vector<float> d(size_t(tmax) + 2);
    for (int64_t f = 0; f < frames; f++) {
        const float *p = x.data() + f * HOP;
        float e = 0;
        for (int j = 0; j < W; j++) e += p[j] * p[j];
        if (e / float(W) < 1e-6f) continue;
        float sum = 0;
        int best = 0;
        d[0] = 1;
        for (int t = 1; t <= tmax; t++) {
            float v = 0;
            for (int j = 0; j < W; j++) { float u = p[j] - p[j + t]; v += u * u; }
            sum += v;
            d[size_t(t)] = sum > 0 ? v * float(t) / sum : 1;
        }
        for (int t = tmin; t < tmax; t++) {
            if (d[size_t(t)] < 0.15f) {
                while (t + 1 < tmax && d[size_t(t) + 1] < d[size_t(t)]) t++;
                best = t;
                break;
            }
        }
        period[size_t(f)] = best;
    }
    // a run of hops agreeing with its neighbours is a voiced stretch
    std::vector<int> smooth(period);
    for (size_t f = 2; f + 2 < period.size(); f++) {
        int v[5] = {period[f - 2], period[f - 1], period[f], period[f + 1], period[f + 2]};
        std::sort(v, v + 5);
        smooth[f] = v[2];
    }
    Marks m;
    const int FIXED = g_rate / 200;
    auto mono = [&](int64_t i) { return in[size_t(i) * 2] + in[size_t(i) * 2 + 1]; };
    int64_t t = 0;
    int64_t last_voiced = -1;
    while (t < n) {
        int64_t f = t / (D * HOP);
        int p = f < int64_t(smooth.size()) ? smooth[size_t(f)] * D : 0;
        if (p == 0) {
            m.at.push_back(t); m.half.push_back(FIXED);
            t += FIXED;
            last_voiced = -1;
            continue;
        }
        // the highest peak near where the next period should fall, so the marks keep to the same place in each period
        int64_t lo = last_voiced >= 0 ? t - p / 4 : t, hi = last_voiced >= 0 ? t + p / 4 : t + p;
        int64_t best = std::clamp(t, int64_t(0), n - 1);
        float top = -1e9f;
        for (int64_t i = std::max<int64_t>(lo, 0); i < std::min(hi, n); i++) { float v = mono(i); if (v > top) { top = v; best = i; } }
        m.at.push_back(best); m.half.push_back(p);
        last_voiced = best;
        t = best + p;
    }
    return m;
}

void render_psola(const float *in, int64_t n, Writer &w, double speed, int64_t start, const Marks &m) {
    const int64_t maxg = g_rate / 30;
    const int64_t out0 = int64_t(double(start) / speed);
    std::vector<float> wsum(size_t(w.t.frames - out0) + size_t(maxg) * 2 + 8);     // the windows laid over each output frame
    float *buf = w.buf;
    size_t k = 0;
    while (k + 1 < m.at.size() && m.at[k + 1] < start) k++;
    double ts = double(out0);
    int64_t done = out0;     // frames before this have had every grain that touches them, and are normalised
    std::vector<float> win;
    int chunk = 0;
    auto finish = [&](int64_t upto) {
        upto = std::min(upto, w.t.frames);
        for (int64_t i = done; i < upto; i++) {
            float g = wsum[size_t(i - out0)];
            if (g > 1e-4f) { buf[size_t(i) * 2] /= g; buf[size_t(i) * 2 + 1] /= g; }
        }
        done = std::max(done, upto);
        w.publish(done);
    };
    while (ts < double(w.t.frames) && !w.t.cancel.load()) {
        const double ta = ts * speed;
        while (k + 1 < m.at.size() && std::fabs(double(m.at[k + 1]) - ta) <= std::fabs(double(m.at[k]) - ta)) k++;
        const int64_t c = m.at[k];
        const int half = m.half[k];
        const int64_t os = int64_t(ts);
        for (int j = -half; j < half; j++) {
            const int64_t si = c + j, oi = os + j;
            if (si < 0 || si >= n || oi < out0 || oi >= w.t.frames) continue;
            const float g = 0.5f + 0.5f * std::cos(float(M_PI) * float(j) / float(half));
            buf[size_t(oi) * 2] += in[size_t(si) * 2] * g;
            buf[size_t(oi) * 2 + 1] += in[size_t(si) * 2 + 1] * g;
            wsum[size_t(oi - out0)] += g;
        }
        ts += half;
        if (++chunk % 16 == 0) finish(int64_t(ts) - maxg);
    }
    if (!w.t.cancel.load()) finish(w.t.frames);
}

// each stem's marks, found once
std::mutex g_marks_mutex;
std::map<const void *, std::shared_ptr<Marks>> g_marks;
std::shared_ptr<Marks> marks_for(const Stem &src) {
    std::lock_guard<std::mutex> lk(g_marks_mutex);
    auto &m = g_marks[src.get()];
    if (!m) m = std::make_shared<Marks>(find_marks(src->data(), int64_t(src->size() / 2)));
    return m;
}

TrackP new_track(uint64_t key, double speed, int64_t from_source) {
    auto t = std::make_shared<Track>();
    t->key = key; t->speed = speed;
    t->frames = std::llround(double(g_frames) / speed);
    t->from = int64_t(double(from_source) / speed);
    t->to = t->from;
    return t;
}

void render_track(TrackP t, Stem src, int method, int64_t start, bool full) {
    g_busy++;
    if (full) g_full_active++;
    std::thread([t, src, method, start, full] {
        const size_t alloc = (size_t(t->frames) + 16384) * 8;
        t->owned = (float *)calloc(alloc, 1);
        Writer w{*t, t->owned, full ? &g_full_done : nullptr};
        t->data = t->owned;
        const float *in = src->data();
        const int64_t n = std::min(g_frames, int64_t(src->size() / 2));
        switch (method) {
            case METHOD_R3_TOGETHER: render_r3(in, n, w, t->speed, start, true); break;
            case METHOD_R3_APART: render_r3(in, n, w, t->speed, start, false); break;
            case METHOD_SIGNALSMITH: render_signalsmith(in, n, w, t->speed, start, 0, 0); break;
            case METHOD_SIGNALSMITH_SHORT: render_signalsmith(in, n, w, t->speed, start, 50, 15); break;
            case METHOD_PSOLA: { auto m = marks_for(src); render_psola(in, n, w, t->speed, start, *m); break; }
        }
        if (!t->cancel.load()) {
            w.publish(t->frames);
            // whatever a method left short at the very end is silence
            t->to.store(t->frames, std::memory_order_release);
            if (full && start == 0) save_cached(*t);
        }
        if (full) { g_full_done += t->frames - w.reported; g_full_active--; }
        g_busy--;
    }).detach();
}

// ----------------------------------------------- corrections

// one note's correction in a stem. The new sound is blended in and out inside the note's span, so the audio either side is untouched.
void apply_fix(std::vector<float> &v, const Fix &f) {
    const int64_t n = int64_t(v.size() / 2);
    const int64_t i0 = std::clamp(int64_t(f.start * g_rate), int64_t(0), n), i1 = std::clamp(int64_t(f.end * g_rate), int64_t(0), n);
    if (i1 <= i0) return;
    const int64_t xf = std::max<int64_t>(1, std::min<int64_t>(g_rate * 12 / 1000, (i1 - i0) / 4));
    auto weight = [&](int64_t i) { return std::min({1.f, float(i - i0) / float(xf), float(i1 - i) / float(xf)}); };
    if (f.mute) {
        for (int64_t i = i0; i < i1; i++) { float g = 1 - weight(i); v[size_t(i) * 2] *= g; v[size_t(i) * 2 + 1] *= g; }
        return;
    }
    if (f.semitones == 0) return;
    // with the sound either side, so the shifter sees the note in context
    const int64_t pad = g_rate * 3 / 10, a = std::max<int64_t>(0, i0 - pad), b = std::min(n, i1 + pad);
    std::vector<float> shifted(size_t(b - a) * 2, 0.f);
    r3_pass(v.data() + a * 2, b - a, 1.0, std::pow(2.0, f.semitones / 12), true,
            [&](int64_t at, const float *l, const float *r, int64_t m) {
                for (int64_t q = 0; q < m && at + q < b - a; q++) { shifted[size_t(at + q) * 2] = l[q]; shifted[size_t(at + q) * 2 + 1] = r[q]; }
            }, [] { return false; });
    for (int64_t i = i0; i < i1; i++) {
        float g = weight(i);
        for (int c = 0; c < 2; c++) {
            float &o = v[size_t(i) * 2 + c];
            o = o * (1 - g) + shifted[size_t(i - a) * 2 + c] * g;
        }
    }
}

// brings each stem's corrected audio up to date with the list; the worker thread's alone
void prepare_sources(const std::vector<Fix> &fixes) {
    std::vector<std::thread> th;
    for (int i = 0; i < STEM_COUNT; i++) {
        uint64_t key = stem_key(i, fixes);
        if (key == g_source_key[i]) continue;
        th.emplace_back([i, key, &fixes] {
            std::vector<Fix> mine;
            for (const Fix &f : fixes) if (f.stem == i) mine.push_back(f);
            if (mine.empty()) { g_source[i] = g_base[i]; }
            else {
                auto v = std::make_shared<std::vector<float>>(*g_base[i]);
                for (const Fix &f : mine) apply_fix(*v, f);
                g_source[i] = v;
            }
            g_source_key[i] = key;
        });
    }
    for (auto &x : th) x.join();
}

// ----------------------------------------------- planning: what the mixer should be given, for what's been asked

std::atomic<Take *> g_retired[32];
std::atomic<int> g_retired_n{0};
std::vector<Take *> g_all_takes;   // the worker's: every take the mixer may hold

void cancel_unused(Take *dead, const Take *keep) {
    auto used = [&](const TrackP &t) {
        if (!keep) return false;
        for (int i = 0; i < STEM_COUNT; i++) if (keep->full[i] == t || keep->ahead[i] == t) return true;
        return false;
    };
    for (int i = 0; i < STEM_COUNT; i++) {
        if (dead->full[i] && !used(dead->full[i])) dead->full[i]->cancel = true;
        if (dead->ahead[i] && !used(dead->ahead[i])) dead->ahead[i]->cancel = true;
    }
}

void retire_old() {
    Take *cur = g_current.load();
    for (int i = 0, n = g_retired_n.load(); i < n; i++) {
        Take *t = g_retired[i].exchange(nullptr);
        if (t && t != cur) { cancel_unused(t, cur); delete t; }
    }
    g_retired_n = 0;
}

void hand_over(Take *t) {
    Take *old = g_pending.exchange(t);
    if (old) { cancel_unused(old, t); delete old; }
}

double source_now() {
    int64_t sk = g_seek.load();
    if (sk >= 0) return double(sk) / g_rate;
    return double(g_pos.load()) / g_rate * g_cur_speed.load();
}

// how far past the playhead a render must be for it to be worth waiting on rather than starting another, in seconds of the original
const double WAIT_FOR_RENDER = 3;

void plan_job(double speed, uint64_t gen) {
    if (!g_current.load()) return;     // no song yet: the choice stands for when there is one
    retire_old();
    std::vector<Fix> fixes;
    { std::lock_guard<std::mutex> lk(g_fix_mutex); fixes = g_fixes; }
    prepare_sources(fixes);
    if (g_gen.load() != gen) return;
    Take *cur = g_pending.load();
    if (!cur) cur = g_current.load();
    const bool playing = g_playing.load() && g_seek.load() < 0;

    auto t = std::make_unique<Take>();
    t->speed = speed;
    t->frames = std::llround(double(g_frames) / speed);
    bool changed = false;
    uint64_t keys[STEM_COUNT];
    int methods[STEM_COUNT];
    for (int i = 0; i < STEM_COUNT; i++) {
        methods[i] = (i == STEM_I ? g_method_inst : g_method_voices).load();
        keys[i] = g_source_key[i];
        if (speed != 1.0) {
            uint64_t sp = uint64_t(std::llround(speed * 100000)) * 1099511628211ULL + uint64_t(methods[i]) * 16777619ULL + 3;
            keys[i] = (keys[i] ^ sp) * 1099511628211ULL;
        }
        if (!cur->full[i] || cur->full[i]->key != keys[i]) changed = true;
    }
    // the new version starts a moment ahead of the playhead, so it's ready when the playhead gets there and nothing stops
    double target = source_now();
    if (changed && playing) target += 1.0 * g_cur_speed.load();
    const int64_t tgt = int64_t(target * g_rate);
    const int64_t tgt_out = int64_t(target * g_rate / speed);
    const bool first_fulls = g_full_active.load() == 0;
    if (first_fulls) { g_full_total = 0; g_full_done = 0; }
    for (int i = 0; i < STEM_COUNT; i++) {
        if (cur->full[i] && cur->full[i]->key == keys[i]) {
            t->full[i] = cur->full[i];
            t->ahead[i] = cur->ahead[i];
        } else {
            TrackP f = new_track(keys[i], speed, 0);
            if (speed == 1.0) {
                f->holder = g_source[i];
                f->data = g_source[i]->data();
                f->frames = std::min(g_frames, int64_t(g_source[i]->size() / 2));
                f->to = f->frames;
            } else if (!load_cached(*f)) {
                g_full_total += f->frames;
                render_track(f, g_source[i], methods[i], 0, true);
            }
            t->full[i] = f;
        }
        const TrackP &f = t->full[i];
        const bool soon = f->to.load() + int64_t(WAIT_FOR_RENDER * g_rate / speed) > tgt_out;
        if (soon) { if (!(t->ahead[i] && t->ahead[i]->covers(tgt_out))) t->ahead[i] = nullptr; continue; }
        const TrackP &a = t->ahead[i];
        const bool held = a && a->from <= tgt_out && a->to.load() + int64_t(WAIT_FOR_RENDER * g_rate / speed) > tgt_out;
        if (!held) {
            TrackP na = new_track(keys[i], speed, tgt);
            render_track(na, g_source[i], methods[i], tgt, false);
            t->ahead[i] = na;
        }
    }
    if (t->same_as(*cur)) return;
    for (int i = 0; i < STEM_COUNT; i++) t->frames = std::min(t->frames, t->full[i]->frames);
    t->swap_at = changed && playing ? target : -1;
    if (changed && playing) {
        // give the new version its head start, unless asked for something else first
        const int64_t need = std::min(t->frames, tgt_out + int64_t(0.3 * g_rate));
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(4);
        while (g_gen.load() == gen && std::chrono::steady_clock::now() < deadline) {
            bool ok = true;
            for (int i = 0; i < STEM_COUNT; i++)
                ok = ok && ((t->full[i]->data && t->full[i]->covers(need)) || (t->ahead[i] && t->ahead[i]->data && t->ahead[i]->covers(need)));
            if (ok) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
    }
    if (g_gen.load() != gen) { cancel_unused(t.get(), cur); return; }
    hand_over(t.release());
}

void request_job(double speed) {
    uint64_t gen = ++g_gen;
    g_want = speed;
    g_busy++;
    std::thread prev = std::move(g_worker);
    g_worker = std::thread([speed, gen, p = std::move(prev)]() mutable {
        if (p.joinable()) p.join();     // the job before sees the new generation and stops
        if (g_gen.load() == gen) plan_job(speed, gen);
        g_busy--;
    });
}

// ------------------------------------------------------------------------------------------- output
// the mixer's: what each stem is being played from
const Track *g_sel[STEM_COUNT];
Take *g_sel_take = nullptr;

void choose_tracks(Take *t, int64_t pos) {
    g_sel_take = t;
    for (int s = 0; s < STEM_COUNT; s++) {
        const Track *f = t->full[s].get(), *a = t->ahead[s].get();
        g_sel[s] = (f->data && f->covers(pos)) || !a ? f : a;
    }
}

void mix_block(float *out, int frames) {
    Take *t = g_current.load(std::memory_order_acquire);
    if (!t) { std::fill(out, out + frames * 2, 0.f); return; }
    float target[STEM_COUNT][2];
    engine_gains(g_voices.load(std::memory_order_relaxed), target);
    if (!g_gain_set) { memcpy(g_gain, target, sizeof g_gain); g_gain_set = true; }
    int64_t pos = g_pos.load(std::memory_order_relaxed);
    const bool play = g_playing.load(std::memory_order_relaxed);
    if (g_sel_take != t) choose_tracks(t, pos);
    // a track that has run out, or a render that's since caught up: only moved between where the sound is stopped anyway
    bool covered = true;
    auto check = [&] {
        covered = true;
        for (int s = 0; s < STEM_COUNT; s++) if (!g_sel[s]->data || !g_sel[s]->covers(pos, frames)) covered = false;
    };
    check();
    const int64_t loop_a = g_loop_a.load(std::memory_order_relaxed);
    int64_t loop_out = loop_a >= 0 ? int64_t(double(g_loop_b.load(std::memory_order_relaxed)) / t->speed) : -1;
    for (int i = 0; i < frames; i++) {
        // reaching the loop's end by playing there; a click past it plays on
        if (pos == loop_out && play && g_seek.load(std::memory_order_relaxed) < 0) g_seek.store(loop_a, std::memory_order_relaxed);
        const bool seeking = g_seek.load(std::memory_order_relaxed) >= 0;
        Take *pn = g_pending.load(std::memory_order_acquire);
        const bool swapping = pn && (!play || pn->swap_at < 0 || double(pos) * t->speed / g_rate >= pn->swap_at);
        if (g_env <= 0 && (seeking || swapping || !covered)) {
            // at silence: position in the original audio is the common coin between takes
            double source = double(pos) * t->speed;
            int64_t sk = g_seek.exchange(-1);
            if (sk >= 0) source = double(sk);
            if (swapping && (pn = g_pending.exchange(nullptr))) {
                int n = g_retired_n.load();
                if (n < 32) { g_retired[n].store(t); g_retired_n.store(n + 1); }
                t = pn;
                g_current.store(pn, std::memory_order_release);
                g_cur_speed.store(pn->speed);
                g_swapped.fetch_add(1);
            }
            pos = std::min(t->frames, int64_t(source / t->speed));
            if (loop_a >= 0) loop_out = int64_t(double(g_loop_b.load(std::memory_order_relaxed)) / t->speed);
            choose_tracks(t, pos);
            check();
        }
        const bool ready = covered && pos < t->frames;
        const bool sound = play && !seeking && !swapping && ready;
        g_env = std::clamp(g_env + (sound ? ENV_STEP : -ENV_STEP), 0.f, 1.f);
        float l = 0, r = 0;
        if (g_env > 0 && ready) {
            for (int s = 0; s < STEM_COUNT; s++) {
                g_gain[s][0] += (target[s][0] - g_gain[s][0]) * GAIN_SMOOTH;
                g_gain[s][1] += (target[s][1] - g_gain[s][1]) * GAIN_SMOOTH;
                const float *d = g_sel[s]->data;
                l += d[size_t(pos) * 2] * g_gain[s][0];
                r += d[size_t(pos) * 2 + 1] * g_gain[s][1];
            }
            pos++;      // through a fade-out too, so a stop doesn't hold one sample
        } else {
            g_env = g_env > 0 && !ready ? 0 : g_env;
            memcpy(g_gain, target, sizeof g_gain);
        }
        out[i * 2] = soft(l * g_env);
        out[i * 2 + 1] = soft(r * g_env);
    }
    g_pos.store(pos, std::memory_order_relaxed);
    g_waiting.store(play && !covered && pos < t->frames, std::memory_order_relaxed);
    if (pos >= t->frames && play) g_playing.store(false);
}

OSStatus callback(void *, AudioUnitRenderActionFlags *, const AudioTimeStamp *, UInt32, UInt32 frames, AudioBufferList *io) {
    mix_block((float *)io->mBuffers[0].mData, int(frames));
    return noErr;
}

double device_latency() {
    AudioDeviceID dev = g_device; UInt32 sz = sizeof dev;
    AudioObjectPropertyAddress a{kAudioHardwarePropertyDefaultOutputDevice, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    if (!dev && AudioObjectGetPropertyData(kAudioObjectSystemObject, &a, 0, nullptr, &sz, &dev)) return 0;
    auto get = [&](AudioObjectPropertySelector sel, AudioObjectPropertyScope sc) {
        UInt32 v = 0, s = sizeof v;
        AudioObjectPropertyAddress p{sel, sc, kAudioObjectPropertyElementMain};
        return AudioObjectGetPropertyData(dev, &p, 0, nullptr, &s, &v) ? 0u : v;
    };
    UInt32 frames = get(kAudioDevicePropertyLatency, kAudioDevicePropertyScopeOutput) + get(kAudioDevicePropertySafetyOffset, kAudioDevicePropertyScopeOutput) +
                    get(kAudioDevicePropertyBufferFrameSize, kAudioObjectPropertyScopeGlobal);
    AudioStreamID streams[8]; UInt32 ss = sizeof streams;
    AudioObjectPropertyAddress ps{kAudioDevicePropertyStreams, kAudioDevicePropertyScopeOutput, kAudioObjectPropertyElementMain};
    if (!AudioObjectGetPropertyData(dev, &ps, 0, nullptr, &ss, streams) && ss >= sizeof(AudioStreamID)) {
        UInt32 v = 0, s = sizeof v;
        AudioObjectPropertyAddress pl{kAudioStreamPropertyLatency, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
        if (!AudioObjectGetPropertyData(streams[0], &pl, 0, nullptr, &s, &v)) frames += v;
    }
    Float64 sr = 44100; UInt32 s2 = sizeof sr;
    AudioObjectPropertyAddress pr{kAudioDevicePropertyNominalSampleRate, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    AudioObjectGetPropertyData(dev, &pr, 0, nullptr, &s2, &sr);
    return double(frames) / sr;
}

std::string cf_string(AudioDeviceID dev, AudioObjectPropertySelector sel) {
    CFStringRef s = nullptr; UInt32 sz = sizeof s;
    AudioObjectPropertyAddress p{sel, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    if (AudioObjectGetPropertyData(dev, &p, 0, nullptr, &sz, &s) || !s) return "";
    char b[512] = "";
    CFStringGetCString(s, b, sizeof b, kCFStringEncodingUTF8);
    CFRelease(s);
    return b;
}

std::vector<AudioDeviceID> output_devices() {
    AudioObjectPropertyAddress p{kAudioHardwarePropertyDevices, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    UInt32 sz = 0;
    std::vector<AudioDeviceID> out;
    if (AudioObjectGetPropertyDataSize(kAudioObjectSystemObject, &p, 0, nullptr, &sz)) return out;
    std::vector<AudioDeviceID> all(sz / sizeof(AudioDeviceID));
    if (AudioObjectGetPropertyData(kAudioObjectSystemObject, &p, 0, nullptr, &sz, all.data())) return out;
    for (auto d : all) {
        AudioObjectPropertyAddress c{kAudioDevicePropertyStreamConfiguration, kAudioDevicePropertyScopeOutput, kAudioObjectPropertyElementMain};
        UInt32 n = 0;
        if (AudioObjectGetPropertyDataSize(d, &c, 0, nullptr, &n) || !n) continue;
        std::vector<char> buf(n);
        if (AudioObjectGetPropertyData(d, &c, 0, nullptr, &n, buf.data())) continue;
        auto list = (AudioBufferList *)buf.data();
        UInt32 ch = 0;
        for (UInt32 i = 0; i < list->mNumberBuffers; i++) ch += list->mBuffers[i].mNumberChannels;
        if (ch) out.push_back(d);
    }
    return out;
}

} // namespace

// ------------------------------------------------------------------------------------------- API
extern "C" {

void engine_gains(int voices, float gains[STEM_COUNT][2]) {
    const float master = db(g_master_db.load(std::memory_order_relaxed));
    for (int s = 0; s < STEM_COUNT; s++) {
        float g = db(TRIM_DB[s]);
        const int heard = (voices & VOICES_ALL);
        if (s != STEM_I && heard != VOICES_ALL) {
            const bool on = voices >> s & 1;
            if (g_isolated.load(std::memory_order_relaxed)) g = !heard ? 0 : on ? 1 : db(BEHIND_DB);
            else g = on ? g * db(FEATURE_DB[std::popcount(unsigned(heard))]) : 0;
        }
        float l, r;
        pan_gains(PAN_KNOB[s], l, r);
        gains[s][0] = g * l * master;
        gains[s][1] = g * r * master;
    }
}

int engine_load(const char *const *paths, const char *cache_dir) {
    engine_wait_render();
    std::vector<float> loaded[STEM_COUNT];
    std::atomic<int> ok{1};
    std::vector<std::thread> th;
    int rates[STEM_COUNT]; int64_t lens[STEM_COUNT];
    for (int i = 0; i < STEM_COUNT; i++)
        th.emplace_back([&, i] { if (!read_file(paths[i], loaded[i], rates[i], lens[i])) ok = 0; });
    for (auto &x : th) x.join();
    if (!ok.load()) return 0;
    int64_t len0 = lens[0];
    for (int i = 0; i < STEM_COUNT; i++) {
        if (rates[i] != rates[0]) { fprintf(stderr, "stem %d is at another sample rate\n", i); return 0; }
        len0 = std::min(len0, lens[i]);
    }
    auto t = new Take;                 // the take of a song loaded before is left: the mixer may be in it
    g_rate = rates[0];
    g_frames = len0;
    t->frames = len0;
    g_cache_root = cache_dir;
    { std::lock_guard<std::mutex> lk(g_fix_mutex); g_fixes.clear(); }
    { std::lock_guard<std::mutex> lk(g_marks_mutex); g_marks.clear(); }
    for (int i = 0; i < STEM_COUNT; i++) {
        g_paths[i] = paths[i];
        g_base[i] = std::make_shared<std::vector<float>>(std::move(loaded[i]));
        g_source[i] = g_base[i];
        g_source_key[i] = stem_key(i, {});
        auto f = std::make_shared<Track>();
        f->key = g_source_key[i]; f->frames = len0; f->to = len0;
        f->holder = g_base[i]; f->data = g_base[i]->data();
        t->full[i] = f;
    }
    g_gen++;
    delete g_pending.exchange(nullptr);
    g_current.store(t);
    g_cur_speed = 1;
    g_want = 1;
    g_pos = 0;
    return 1;
}

int engine_start_output(void) {
    AudioComponentDescription d{kAudioUnitType_Output, OSType(g_device ? kAudioUnitSubType_HALOutput : kAudioUnitSubType_DefaultOutput),
                                kAudioUnitManufacturer_Apple, 0, 0};
    AudioComponent c = AudioComponentFindNext(nullptr, &d);
    if (!c || AudioComponentInstanceNew(c, &g_unit)) return 0;
    if (g_device && AudioUnitSetProperty(g_unit, kAudioOutputUnitProperty_CurrentDevice, kAudioUnitScope_Global, 0, &g_device, sizeof g_device)) return 0;
    AudioStreamBasicDescription fmt{};
    fmt.mSampleRate = g_rate; fmt.mFormatID = kAudioFormatLinearPCM;
    fmt.mFormatFlags = kAudioFormatFlagIsFloat | kAudioFormatFlagIsPacked;
    fmt.mBitsPerChannel = 32; fmt.mChannelsPerFrame = 2; fmt.mFramesPerPacket = 1; fmt.mBytesPerFrame = fmt.mBytesPerPacket = 8;
    AudioUnitSetProperty(g_unit, kAudioUnitProperty_StreamFormat, kAudioUnitScope_Input, 0, &fmt, sizeof fmt);
    AURenderCallbackStruct cb{callback, nullptr};
    AudioUnitSetProperty(g_unit, kAudioUnitProperty_SetRenderCallback, kAudioUnitScope_Input, 0, &cb, sizeof cb);
    UInt32 q = kRenderQuality_Max;
    AudioUnitSetProperty(g_unit, kAudioUnitProperty_RenderQuality, kAudioUnitScope_Global, 0, &q, sizeof q);
    if (AudioUnitInitialize(g_unit) || AudioOutputUnitStart(g_unit)) return 0;
    g_latency = device_latency();
    return 1;
}

void engine_stop_output(void) {
    if (g_unit) { AudioOutputUnitStop(g_unit); AudioUnitUninitialize(g_unit); AudioComponentInstanceDispose(g_unit); g_unit = nullptr; }
}

int engine_device_count(void) { return int(output_devices().size()); }

void engine_device_info(int index, char *uid, char *name, int capacity) {
    auto all = output_devices();
    uid[0] = name[0] = 0;
    if (index < 0 || index >= int(all.size())) return;
    snprintf(uid, size_t(capacity), "%s", cf_string(all[size_t(index)], kAudioDevicePropertyDeviceUID).c_str());
    snprintf(name, size_t(capacity), "%s", cf_string(all[size_t(index)], kAudioObjectPropertyName).c_str());
}

int engine_set_device(const char *uid) {
    AudioDeviceID found = 0;
    if (uid[0]) {
        for (auto d : output_devices()) if (cf_string(d, kAudioDevicePropertyDeviceUID) == uid) found = d;
        if (!found) return 0;
    }
    const AudioDeviceID before = g_device;
    engine_stop_output();
    g_device = found;
    if (engine_start_output()) { g_device_uid = uid; return 1; }
    // that device wouldn't open: back to the one before
    engine_stop_output();
    g_device = before;
    engine_start_output();
    return 0;
}

void engine_set_playing(int p) {
    if (p) g_latency = device_latency();
    g_playing.store(p != 0);
}
int engine_is_playing(void) { return g_playing.load(); }
void engine_set_voices(int v) { g_voices.store(v & VOICES_ALL); }
void engine_set_isolated(int isolated) { g_isolated.store(isolated != 0); }
void engine_set_master_db(double d) { g_master_db.store(float(d)); }
void engine_seek(double source_seconds) {
    g_seek.store(int64_t(std::max(0.0, source_seconds) * g_rate));
    std::lock_guard<std::mutex> lk(g_req_mutex);
    request_job(g_want.load());     // starts a render here if none is near
}

double engine_position(void) {
    int64_t sk = g_seek.load();
    if (sk >= 0) return double(sk) / g_rate;
    double s = double(g_pos.load()) / g_rate;
    if (g_playing.load()) s = std::max(0.0, s - g_latency.load());
    return s * g_cur_speed.load();
}
double engine_duration(void) { return double(g_frames) / g_rate; }
double engine_speed(void) { return g_cur_speed.load(); }
double engine_render_progress(void) {
    if (g_full_active.load() == 0 || g_full_total.load() == 0) return -1;
    return std::min(0.99, double(g_full_done.load()) / double(g_full_total.load()));
}
int engine_waiting(void) { return g_waiting.load() ? 1 : 0; }
void engine_set_loop(double start, double end) {
    g_loop_b.store(int64_t(end * g_rate));
    g_loop_a.store(start < 0 ? -1 : int64_t(start * g_rate));
}
void engine_render_here(void) {
    std::lock_guard<std::mutex> lk(g_req_mutex);
    request_job(g_want.load());
}
void engine_set_methods(int voices, int instruments) {
    std::lock_guard<std::mutex> lk(g_req_mutex);
    g_method_voices = voices;
    g_method_inst = instruments;
    request_job(g_want.load());
}
int engine_sample_rate(void) { return g_rate; }

void engine_set_speed(double speed) {
    std::lock_guard<std::mutex> lk(g_req_mutex);
    request_job(std::round(speed * 100000) / 100000);
}

void engine_set_fixes(int count, const int *stems, const double *starts, const double *ends, const int *mutes, const double *semitones) {
    std::lock_guard<std::mutex> lk(g_req_mutex);
    {
        std::lock_guard<std::mutex> f(g_fix_mutex);
        g_fixes.clear();
        for (int i = 0; i < count; i++) g_fixes.push_back({stems[i], starts[i], ends[i], mutes[i] != 0, semitones[i]});
    }
    request_job(g_want.load());
}

void engine_wait_render(void) {
    while (g_busy.load() > 0) std::this_thread::sleep_for(std::chrono::milliseconds(10));
}

void engine_mix(float *out, int frames) { mix_block(out, frames); }

}
