// Offline checks of the player's engine: writes raw float stereo of the mix so the numbers can be measured.
//   enginetest <S> <A> <T> <B> <I> <cache dir> <out dir> <speed>
import CEngine
import Foundation

let a = CommandLine.arguments
let paths = Array(a[1...5])
let cstrs = paths.map { strdup($0) }
defer { cstrs.forEach { free($0) } }
var ptrs = cstrs.map { UnsafePointer<CChar>($0) as UnsafePointer<CChar>? }
guard engine_load(&ptrs, a[6]) != 0 else { print("load failed"); exit(1) }
let outDir = a[7], speed = Double(a[8])!
print("rate", engine_sample_rate(), "duration", engine_duration())

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

let names = ["balanced", "S", "A", "T", "B"], masks: [Int32] = [15, 1, 2, 4, 8]
for m in [15, 1, 2, 4, 8, 3, 5, 12, 7, 14, 0] {
    var t: (Float, Float, Float, Float, Float, Float, Float, Float, Float, Float) = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    withUnsafeMutablePointer(to: &t) {
        $0.withMemoryRebound(to: (Float, Float).self, capacity: 5) { engine_gains(Int32(m), $0) }
    }
    print("voices", m, "gains L/R S A T B I:", t)
}
engine_set_master_db(-9)
var v: (Float, Float, Float, Float, Float, Float, Float, Float, Float, Float) = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
withUnsafeMutablePointer(to: &v) { $0.withMemoryRebound(to: (Float, Float).self, capacity: 5) { engine_gains(15, $0) } }
print("balanced at -9 dB: instruments", v.8, "soprano left", v.0)
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
// any further arguments are fixes, stem:start:end:semitones, or m for the semitones to mute
let fixes = a.dropFirst(9).map { $0.split(separator: ":").map(String.init) }
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
let env = ProcessInfo.processInfo.environment
if let v = env["VOICE"].flatMap({ Int32($0) }), let i = env["INST"].flatMap({ Int32($0) }) { engine_set_methods(v, i) }
// LIVE=start,seconds: go there at once, as the app would, and play for that long at 4 times real time without waiting for
// the render; the audio goes to live.f32 at the song's original times
if let live = env["LIVE"] {
    let p = live.split(separator: ",").map { Double($0)! }
    let t0 = Date()
    engine_set_voices(15)
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
// LOOP=start,end: plays for a while from just before the end and says where the playhead went
if let lp = env["LOOP"] {
    let p = lp.split(separator: ",").map { Double($0)! }
    engine_set_loop(p[0], p[1])
    engine_set_voices(15)
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
for m in 0..<5 { render("\(names[m])", voices: masks[m], seconds: D, startAt: 0) }
