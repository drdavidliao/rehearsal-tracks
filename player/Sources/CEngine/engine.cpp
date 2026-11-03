#include "engine.h"
#include <AudioToolbox/AudioToolbox.h>
#include <CoreAudio/CoreAudio.h>
#include <rubberband/RubberBandStretcher.h>
#include <algorithm>
#include <atomic>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <functional>
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

// the stems of one tempo, interleaved stereo: takes share the stems they have in common. key says which corrections a stem has
struct Take {
    double speed = 1;
    int64_t frames = 0;
    Stem stem[STEM_COUNT];
    uint64_t key[STEM_COUNT] = {};
};

struct Fix { int stem; double start, end; bool mute; double semitones; };

int g_rate = 44100;
int64_t g_frames = 0;
std::atomic<Take *> g_current{nullptr}, g_pending{nullptr};
std::atomic<int64_t> g_seek{-1};      // a seek, in frames of the original audio
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
std::atomic<double> g_progress{-1};
std::atomic<int> g_busy{0};
std::thread &g_worker = *new std::thread;     // never destroyed: a render may be running when the app quits
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

fs::path take_path(uint64_t key, double speed) {
    char d[32], b[32];
    snprintf(d, sizeof d, "%016llx", (unsigned long long)key);
    snprintf(b, sizeof b, "%06d.f32", int(std::lround(speed * 100000)));
    return fs::path(g_cache_root) / "stems" / d / b;
}

Stem load_cached(uint64_t key, double speed) {
    fs::path p = take_path(key, speed);
    std::error_code ec; auto bytes = fs::file_size(p, ec);
    if (ec) return nullptr;
    auto v = std::make_shared<std::vector<float>>(bytes / sizeof(float));
    FILE *f = fopen(p.c_str(), "rb");
    size_t got = f ? fread(v->data(), 1, bytes, f) : 0;
    if (f) fclose(f);
    if (got != bytes) return nullptr;
    fs::last_write_time(p, fs::file_time_type::clock::now(), ec);
    return v;
}

void save_cached(uint64_t key, double speed, const std::vector<float> &v) {
    fs::path p = take_path(key, speed), tmp = p;
    tmp += ".tmp";
    std::error_code ec; fs::create_directories(p.parent_path(), ec);
    FILE *f = fopen(tmp.c_str(), "wb");
    if (!f) return;
    fwrite(v.data(), sizeof(float), v.size(), f);
    fclose(f);
    fs::rename(tmp, p, ec);
    // the cache keeps the stems used last, up to 4 GB
    std::vector<fs::directory_entry> all;
    for (auto &e : fs::recursive_directory_iterator(fs::path(g_cache_root), ec)) if (e.is_regular_file()) all.push_back(e);
    std::sort(all.begin(), all.end(), [](auto &a, auto &b) { return a.last_write_time() > b.last_write_time(); });
    uintmax_t total = 0;
    for (auto &e : all) {
        total += e.file_size(ec);
        if (total > 4ull << 30) fs::remove(e.path(), ec);
    }
}

// R3 offline: studies the whole stem first, the engine's best quality. Returns false if overtaken by a newer request.
// A pitch scale other than 1 is for one note's span, where no tempo changes and the formants stay.
bool stretch(const float *in, int64_t n, std::vector<float> &out, double speed, double pitch, uint64_t gen, std::atomic<int64_t> *done) {
    const int BLOCK = 4096;
    RubberBandStretcher::Options opts = RubberBandStretcher::OptionProcessOffline | RubberBandStretcher::OptionEngineFiner |
                                        RubberBandStretcher::OptionChannelsTogether;
    if (pitch != 1) opts |= RubberBandStretcher::OptionFormantPreserved;
    RubberBandStretcher s(size_t(g_rate), 2, opts, 1.0 / speed, pitch);
    s.setExpectedInputDuration(size_t(n));
    s.setMaxProcessSize(BLOCK);
    std::vector<float> a(BLOCK), b(BLOCK);
    float *ptr[2] = {a.data(), b.data()};
    auto fill = [&](int64_t at, int m) {
        for (int i = 0; i < m; i++) { a[i] = in[size_t(at + i) * 2]; b[i] = in[size_t(at + i) * 2 + 1]; }
    };
    for (int64_t at = 0; at < n; at += BLOCK) {
        int m = int(std::min<int64_t>(BLOCK, n - at));
        fill(at, m);
        s.study(ptr, size_t(m), at + m >= n);
        if (gen && g_gen.load() != gen) return false;
        if (done) *done += m / 4;
    }
    out.clear();
    out.reserve(size_t(n / speed + BLOCK) * 2);
    std::vector<float> l(BLOCK * 2), r(BLOCK * 2);
    float *rp[2] = {l.data(), r.data()};
    auto drain = [&] {
        int av;
        while ((av = s.available()) > 0) {
            int m = std::min(av, BLOCK * 2);
            size_t got = s.retrieve(rp, size_t(m));
            for (size_t i = 0; i < got; i++) { out.push_back(l[i]); out.push_back(r[i]); }
        }
    };
    int64_t at = 0;
    while (at < n) {
        int m = int(std::min<int64_t>({int64_t(BLOCK), n - at, int64_t(std::max<size_t>(s.getSamplesRequired(), 1))}));
        fill(at, m);
        s.process(ptr, size_t(m), at + m >= n);
        at += m;
        drain();
        if (gen && g_gen.load() != gen) return false;
        if (done) *done += (m * 3) / 4;
    }
    while (s.available() >= 0) {
        drain();
        if (s.available() == 0) std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    return true;
}

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
    std::vector<float> shifted;
    stretch(v.data() + a * 2, b - a, shifted, 1.0, std::pow(2.0, f.semitones / 12), 0, nullptr);
    if (int64_t(shifted.size() / 2) < b - a) shifted.resize(size_t(b - a) * 2, 0.f);
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

void hand_over(Take *t) {
    Take *old = g_pending.exchange(t);
    delete old;
}

Take *g_retired = nullptr;
void retire_last() {
    // called from the worker before starting anything new: whatever the mixer has swapped out is safe by then
    if (g_retired && g_retired != g_current.load()) { delete g_retired; g_retired = nullptr; }
}

void render_job(double speed, uint64_t gen) {
    std::vector<Fix> fixes;
    { std::lock_guard<std::mutex> lk(g_fix_mutex); fixes = g_fixes; }
    prepare_sources(fixes);
    Take *cur = g_current.load();
    auto t = std::make_unique<Take>();
    t->speed = speed;
    std::vector<int> todo;
    for (int i = 0; i < STEM_COUNT; i++) {
        t->key[i] = g_source_key[i];
        if (speed == 1.0) t->stem[i] = g_source[i];
        else if (cur->speed == speed && cur->key[i] == t->key[i]) t->stem[i] = cur->stem[i];
        else if (!(t->stem[i] = load_cached(t->key[i], speed))) todo.push_back(i);
    }
    if (!todo.empty()) {
        std::atomic<int64_t> done{0};
        const int64_t total = g_frames * int64_t(todo.size());
        g_progress = 0;
        std::atomic<int> ok{1}, finished{0};
        std::vector<std::thread> th;
        for (int i : todo)
            th.emplace_back([&, i] {
                auto v = std::make_shared<std::vector<float>>();
                if (stretch(g_source[i]->data(), int64_t(g_source[i]->size() / 2), *v, speed, 1.0, gen, &done)) {
                    save_cached(t->key[i], speed, *v);
                    t->stem[i] = v;
                } else ok = 0;
                finished++;
            });
        while (finished.load() < int(todo.size())) {
            g_progress = std::min(0.99, double(done.load()) / double(total));
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }
        for (auto &x : th) x.join();
        if (!ok.load()) return;
    }
    if (g_gen.load() != gen) return;
    t->frames = int64_t(t->stem[0]->size() / 2);
    for (int i = 0; i < STEM_COUNT; i++) t->frames = std::min(t->frames, int64_t(t->stem[i]->size() / 2));
    // already playing just this: nothing to move to
    bool same = !g_pending.load() && cur->speed == speed;
    for (int i = 0; i < STEM_COUNT; i++) same = same && cur->key[i] == t->key[i];
    if (!same) hand_over(t.release());
}

void request_job(double speed) {
    uint64_t gen = ++g_gen;
    g_want = speed;
    g_busy++;
    std::thread prev = std::move(g_worker);
    g_worker = std::thread([speed, gen, p = std::move(prev)]() mutable {
        if (p.joinable()) p.join();     // the job before sees the new generation and stops
        retire_last();
        if (g_gen.load() == gen) render_job(speed, gen);
        if (g_gen.load() == gen) g_progress = -1;
        g_busy--;
    });
}

// ------------------------------------------------------------------------------------------- output
void mix_block(float *out, int frames) {
    Take *t = g_current.load(std::memory_order_acquire);
    if (!t) { std::fill(out, out + frames * 2, 0.f); return; }
    float target[STEM_COUNT][2];
    engine_gains(g_voices.load(std::memory_order_relaxed), target);
    if (!g_gain_set) { memcpy(g_gain, target, sizeof g_gain); g_gain_set = true; }
    const float *data[STEM_COUNT];
    for (int s = 0; s < STEM_COUNT; s++) data[s] = t->stem[s]->data();
    int64_t pos = g_pos.load(std::memory_order_relaxed);
    const bool play = g_playing.load(std::memory_order_relaxed);
    for (int i = 0; i < frames; i++) {
        const bool seeking = g_seek.load(std::memory_order_relaxed) >= 0;
        const bool swapping = g_pending.load(std::memory_order_relaxed) != nullptr;
        if (g_env <= 0 && (seeking || swapping)) {
            // at silence: position in the original audio is the common coin between takes
            double source = double(pos) * t->speed;
            int64_t sk = g_seek.exchange(-1);
            if (sk >= 0) source = double(sk);
            if (Take *np = g_pending.exchange(nullptr)) {
                g_retired = t;
                t = np;
                g_current.store(np, std::memory_order_release);
                g_cur_speed.store(np->speed);
                g_swapped.fetch_add(1);
                for (int s = 0; s < STEM_COUNT; s++) data[s] = t->stem[s]->data();
            }
            pos = std::min(t->frames, int64_t(source / t->speed));
        }
        const bool sound = play && !seeking && !swapping && pos < t->frames;
        g_env = std::clamp(g_env + (sound ? ENV_STEP : -ENV_STEP), 0.f, 1.f);
        float l = 0, r = 0;
        if (g_env > 0 && pos < t->frames) {
            for (int s = 0; s < STEM_COUNT; s++) {
                g_gain[s][0] += (target[s][0] - g_gain[s][0]) * GAIN_SMOOTH;
                g_gain[s][1] += (target[s][1] - g_gain[s][1]) * GAIN_SMOOTH;
                l += data[s][size_t(pos) * 2] * g_gain[s][0];
                r += data[s][size_t(pos) * 2 + 1] * g_gain[s][1];
            }
            pos++;      // through a fade-out too, so a stop doesn't hold one sample
        } else {
            memcpy(g_gain, target, sizeof g_gain);
        }
        out[i * 2] = soft(l * g_env);
        out[i * 2 + 1] = soft(r * g_env);
    }
    g_pos.store(pos, std::memory_order_relaxed);
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
        if (s != STEM_I) g = (voices >> s & 1) ? g * db(FEATURE_DB[std::popcount(unsigned(voices & VOICES_ALL))]) : 0;
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
    t->frames = len0;
    g_rate = rates[0];
    g_frames = len0;
    g_cache_root = cache_dir;
    { std::lock_guard<std::mutex> lk(g_fix_mutex); g_fixes.clear(); }
    for (int i = 0; i < STEM_COUNT; i++) {
        g_paths[i] = paths[i];
        g_base[i] = std::make_shared<std::vector<float>>(std::move(loaded[i]));
        g_source[i] = t->stem[i] = g_base[i];
        g_source_key[i] = t->key[i] = stem_key(i, {});
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
void engine_set_master_db(double d) { g_master_db.store(float(d)); }
void engine_seek(double source_seconds) { g_seek.store(int64_t(std::max(0.0, source_seconds) * g_rate)); }

double engine_position(void) {
    int64_t sk = g_seek.load();
    if (sk >= 0) return double(sk) / g_rate;
    double s = double(g_pos.load()) / g_rate;
    if (g_playing.load()) s = std::max(0.0, s - g_latency.load());
    return s * g_cur_speed.load();
}
double engine_duration(void) { return double(g_frames) / g_rate; }
double engine_speed(void) { return g_cur_speed.load(); }
double engine_render_progress(void) { return g_progress.load(); }
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
