// Offline checks of the player's engine: writes raw float stereo of the mix so the numbers can be measured.
//   enginetest <cache dir> <out dir> <speed> <instrumental stem, or - for none> <voice stem>...
// PANS and TRIMS in the environment, comma-separated, one per voice: the app's pans and trims for the song. Without them four
// voices take SATB's (-45 -15 15 45; 0 -3 -3 0), and any other number is centred at 0 dB.
// FIXES in the environment, space-separated: stem:start:end:semitones, or m for the semitones to mute.
import CEngine
import Foundation

let a = CommandLine.arguments
let outDir = a[2], speed = Double(a[3])!
let voicePaths = Array(a[5...])
let nv = voicePaths.count
let cstrs = voicePaths.map { strdup($0) } + [a[4] == "-" ? nil : strdup(a[4])]
defer { cstrs.forEach { free($0) } }
var ptrs = cstrs.map { $0.map { UnsafePointer<CChar>($0) } }
guard engine_load(&ptrs, Int32(nv), a[1]) != 0 else { print("load failed"); exit(1) }
let env = ProcessInfo.processInfo.environment
func list(_ k: String) -> [Float]? { env[k].map { $0.split(separator: ",").map { Float($0)! } } }
var pans = list("PANS") ?? (nv == 4 ? [-45, -15, 15, 45] : Array(repeating: 0, count: nv))
var trims = list("TRIMS") ?? (nv == 4 ? [0, -3, -3, 0] : Array(repeating: 0, count: nv))
engine_set_voice_mix(&pans, &trims)
let all = Int32((1 << nv) - 1)
print("rate", engine_sample_rate(), "duration", engine_duration(), "voices", engine_voice_count())

func gains(_ m: Int32) -> [Float] {
    var g = [Float](repeating: 0, count: Int(STEM_MAX) * 2)
    g.withUnsafeMutableBufferPointer { b in b.baseAddress!.withMemoryRebound(to: (Float, Float).self, capacity: Int(STEM_MAX)) { engine_gains(m, $0) } }
    return Array(g.prefix((nv + 1) * 2))
}

func render(_ name: String, voices: Int32, seconds: Double, startAt: Double) {
    engine_set_voices(voices)
    engine_seek(startAt)
    engine_set_playing(1)
    let n = Int(seconds * Double(engine_sample_rate()) / engine_speed())
    var buf = [Float](repeating: 0, count: n * 2)
    buf.withUnsafeMutableBufferPointer { engine_mix($0.baseAddress, Int32(n)) }
    engine_set_playing(0)
    var flush = [Float](repeating: 0, count: 1024)
    flush.withUnsafeMutableBufferPointer { engine_mix($0.baseAddress, 512) }
    let pk = buf.map { abs($0) }.max() ?? 0
    let over = buf.filter { abs($0) > 0.9 }.count
    print(name, "peak", pk, "samples past 0.9:", over, "position after", engine_position())
    FileManager.default.createFile(atPath: "\(outDir)/\(name).f32", contents: buf.withUnsafeBufferPointer { Data(buffer: $0) })
}

if env["ISOLATED"] != nil { engine_set_isolated(1) }
// every combination of voices for up to five, else all, none and each alone
let masks: [Int32] = nv <= 5 ? Array(0...all).reversed() : [all, 0] + (0..<nv).map { Int32(1 << $0) }
for m in masks {
    print("voices", String(m, radix: 2), "gains L/R, voices then instruments:", gains(m).map { String(format: "%.4f", $0) }.joined(separator: " "))
}
engine_set_master_db(-9)
print("balanced at -9 dB: instruments", gains(all)[nv * 2], "first voice left", gains(all)[0])
engine_set_instruments(0)
print("instruments off: instruments", gains(all)[nv * 2], gains(all)[nv * 2 + 1], "first voice left", gains(all)[0])
engine_set_instruments(1)
engine_set_master_db(-3)
if speed != 1 {
    let t0 = Date()
    engine_set_speed(speed)
    engine_wait_render()
    // the mixer takes the new take on its next block
    var f = [Float](repeating: 0, count: 2048)
    f.withUnsafeMutableBufferPointer { engine_mix($0.baseAddress, 1024) }
    print("render or load took", Date().timeIntervalSince(t0), "s; speed now", engine_speed())
}
let fixes = (env["FIXES"] ?? "").split(separator: " ").map { $0.split(separator: ":").map(String.init) }
if !fixes.isEmpty {
    var st = fixes.map { Int32($0[0])! }, s0 = fixes.map { Double($0[1])! }, s1 = fixes.map { Double($0[2])! }
    var mu = fixes.map { Int32($0[3] == "m" ? 1 : 0) }, se = fixes.map { Double($0[3]) ?? 0 }
    let t0 = Date()
    engine_set_fixes(Int32(fixes.count), &st, &s0, &s1, &mu, &se)
    engine_wait_render()
    var f = [Float](repeating: 0, count: 2048)
    f.withUnsafeMutableBufferPointer { engine_mix($0.baseAddress, 1024) }
    print("fixes took", Date().timeIntervalSince(t0), "s")
}
if let v = env["VOICE"].flatMap({ Int32($0) }), let i = env["INST"].flatMap({ Int32($0) }) { engine_set_methods(v, i) }
// LIVE=start,seconds: go there at once, as the app would, and play for that long at 4 times real time without waiting for
// the render; the audio goes to live.f32 at the song's original times
if let live = env["LIVE"] {
    let p = live.split(separator: ",").map { Double($0)! }
    let t0 = Date()
    engine_set_voices(all)
    engine_seek(p[0])
    engine_set_playing(1)
    let block = 512, rate = Double(engine_sample_rate())
    var buf = [Float](repeating: 0, count: block * 2), out = [Float](), firstSound: Double?, waits = 0, total = 0
    let want = Int(p[1] * rate / engine_speed())
    while total < want {
        buf.withUnsafeMutableBufferPointer { engine_mix($0.baseAddress, Int32(block)) }
        if engine_waiting() != 0 {
            if firstSound != nil { waits += 1 }
            Thread.sleep(forTimeInterval: 0.002)
            continue
        }
        if firstSound == nil && buf.contains(where: { $0 != 0 }) { firstSound = Date().timeIntervalSince(t0) }
        if firstSound != nil { out += buf; total += block; Thread.sleep(forTimeInterval: Double(block) / rate / 4) }
    }
    print("live: first sound after", firstSound ?? -1, "s; blocks that had to wait after that:", waits, "; position", engine_position())
    FileManager.default.createFile(atPath: "\(outDir)/live.f32", contents: out.withUnsafeBufferPointer { Data(buffer: $0) })
    exit(0)
}
// STRESS=cycles: changes tempo, method and place over and over while playing, and says how much memory the process holds
if let st = env["STRESS"], let cycles = Int(st) {
    func footprint() -> Double {
        var info = rusage_info_v4()
        let r = withUnsafeMutablePointer(to: &info) { $0.withMemoryRebound(to: rusage_info_t?.self, capacity: 1) { proc_pid_rusage(getpid(), RUSAGE_INFO_V4, $0) } }
        return r == 0 ? Double(info.ri_phys_footprint) / 1e9 : -1
    }
    func play(_ secs: Double) {
        var buf = [Float](repeating: 0, count: 1024)
        let end = Date().addingTimeInterval(secs)
        while Date() < end {
            buf.withUnsafeMutableBufferPointer { engine_mix($0.baseAddress, 512) }
            Thread.sleep(forTimeInterval: 0.0116)
        }
    }
    engine_set_playing(1)
    let speeds = [1.0, 0.8, 0.83333, 0.9, 1.1, 0.75, 1.25]
    print("start", footprint())
    for c in 1...cycles {
        engine_set_speed(speeds[c % speeds.count])
        play(0.4)
        engine_set_methods(Int32(c % 5), Int32(c % 4))
        play(0.4)
        engine_seek(Double((c * 37) % 200))
        play(0.4)
        if c % 10 == 0 { print("cycle", c, "footprint GB", footprint()) }
    }
    engine_set_speed(1)
    play(0.5)
    engine_render_here()
    engine_wait_render()
    play(0.5)
    engine_render_here()
    engine_wait_render()
    play(0.5)
    print("settled at the song's own tempo, footprint GB", footprint(), "speed now", engine_speed())
    play(14)
    engine_set_speed(0.8)
    play(1)
    engine_wait_render()
    engine_render_here()
    engine_wait_render()
    play(1)
    engine_render_here()
    engine_wait_render()
    play(0.5)
    print("settled at 0.8 with its whole render done, footprint GB", footprint(), "speed now", engine_speed(), "position", engine_position(), "playing", engine_is_playing())
    play(14)     // time for vmmap to look from outside
    exit(0)
}
// LOOPTEMPO=start,end,at,speed: loops, changes tempo with the playhead at `at`, then plays in real time and says what's heard
if let lt = env["LOOPTEMPO"] {
    let p = lt.split(separator: ",").map { Double($0)! }
    engine_set_loop(p[0], p[1])
    engine_set_voices(all)
    engine_seek(p[2])
    engine_set_playing(1)
    var buf = [Float](repeating: 0, count: 1024)
    func play(_ secs: Double, _ note: ((Double) -> Void)? = nil) -> Int {
        let t0 = Date()
        var waits = 0, next = 1.0
        while Date().timeIntervalSince(t0) < secs {
            buf.withUnsafeMutableBufferPointer { engine_mix($0.baseAddress, 512) }
            if engine_waiting() != 0 { waits += 1; engine_render_here() }
            let e = Date().timeIntervalSince(t0)
            if e >= next { note?(e); next += 1 }
            Thread.sleep(forTimeInterval: 0.0116)
        }
        return waits
    }
    _ = play(0.05)
    engine_set_speed(p[3])
    let t0 = Date()
    var movedAt: Double?
    var trace = [String]()
    var waits = 0
    do {
        // not through the helper's closure: a top-level closure capturing these has crashed this program
        var next = 1.0
        while Date().timeIntervalSince(t0) < 12 {
            buf.withUnsafeMutableBufferPointer { engine_mix($0.baseAddress, 512) }
            if engine_waiting() != 0 { waits += 1; engine_render_here() }
            let e = Date().timeIntervalSince(t0)
            if e >= next {
                if movedAt == nil && engine_speed() == p[3] { movedAt = e }
                trace.append(String(format: "%.2f@%.1f", engine_speed(), engine_position()))
                next += 1
            }
            Thread.sleep(forTimeInterval: 0.0116)
        }
    }
    print("loop", p[0], "-", p[1], "change at", p[2], ": moved to the new tempo by", movedAt.map { String(format: "%.0f s", $0) } ?? "NEVER", "; blocks waiting", waits)
    for line in trace { print(" ", line, terminator: "") }
    print("")
    exit(0)
}
// LOOP=start,end: plays for a while from just before the end and says where the playhead went
if let lp = env["LOOP"] {
    let p = lp.split(separator: ",").map { Double($0)! }
    engine_set_loop(p[0], p[1])
    engine_set_voices(all)
    engine_seek(p[1] - 0.5)
    engine_set_playing(1)
    var buf = [Float](repeating: 0, count: 1024), last = 0.0, wraps = [Double]()
    let blocks = Int(4 * Double(engine_sample_rate()) / engine_speed() / 512)
    var done = 0
    while done < blocks {
        buf.withUnsafeMutableBufferPointer { engine_mix($0.baseAddress, 512) }
        if engine_waiting() != 0 { engine_render_here(); Thread.sleep(forTimeInterval: 0.01); continue }
        let q = engine_position()
        if q < last - 0.1 { wraps.append(last); wraps.append(q) }
        last = q; done += 1
    }
    print("loop: playhead went back (from, to, ...):", wraps)
    exit(0)
}
engine_wait_render()
var flushed = [Float](repeating: 0, count: 2048)
flushed.withUnsafeMutableBufferPointer { engine_mix($0.baseAddress, 1024) }
let D = engine_duration()
render("balanced", voices: all, seconds: D, startAt: 0)
for i in 0..<nv { render("voice\(i)", voices: Int32(1 << i), seconds: D, startAt: 0) }
