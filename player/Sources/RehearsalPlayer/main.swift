// Follow a marked score against separated stems: click a beat to start there, choose a part, choose a tempo.
import AppKit
import CoreImage
import CEngine
import PDFKit
import SwiftUI

// a position within this of a beat counts as on it: the engine works in whole samples
let eps = 0.002

let stretchNames = ["Rubber Band R3, channels together", "Rubber Band R3, channels apart", "Signalsmith Stretch", "Signalsmith Stretch, short blocks", "PSOLA (one voice)"]

final class Player: ObservableObject {
    @Published var voiceMethod: Int32 = Int32(UserDefaults.standard.object(forKey: "voiceMethod") as? Int ?? 1)
    @Published var instMethod: Int32 = Int32(UserDefaults.standard.object(forKey: "instMethod") as? Int ?? 1)
    @Published var waiting = false
    @Published var darkScore = UserDefaults.standard.bool(forKey: "darkScore") {
        didSet { UserDefaults.standard.set(darkScore, forKey: "darkScore"); score?.applyDark() }
    }
    /// the voice files hold one voice each, rather than a part with the others bleeding through. Belongs to the song.
    @Published var isolated = false {
        didSet {
            engine_set_isolated(isolated ? 1 : 0)
            if let f = folder { UserDefaults.standard.set(isolated, forKey: "isolated:" + f.path) }
        }
    }
    @Published var loopOn = false { didSet { applyLoop() } }
    @Published var loopFrom = "" 
    @Published var loopTo = ""
    /// the loop's bars, once both boxes make sense
    var loopBars: (Bar, Bar)? {
        guard let m = map else { return nil }
        func bar(_ s: String, end: Bool) -> Bar? {
            let t = s.trimmingCharacters(in: .whitespaces)
            if let b = typedBar(t) { return b }
            // a letter: from its first bar, or to the last bar before the next letter
            guard let i = m.bars.firstIndex(where: { $0.letter == t.uppercased() }) else { return nil }
            if !end { return m.bars[i] }
            let next = m.bars[(i + 1)...].firstIndex { $0.letter != nil }
            return next.map { m.bars[$0 - 1] } ?? m.bars.last
        }
        guard let a = bar(loopFrom, end: false), let b = bar(loopTo.isEmpty ? loopFrom : loopTo, end: true), a.beat_t[0] < b.end_t else { return nil }
        return (a, b)
    }

    func applyLoop() {
        guard loopOn, let (a, b) = loopBars else { engine_set_loop(-1, 0); score?.refresh(); return }
        engine_set_loop(a.beat_t[0], b.end_t)
        // into the loop if the playhead is elsewhere
        let t = engine_position()
        if t < a.beat_t[0] - eps || t >= b.end_t { seek(a.beat_t[0]) }
        score?.refresh()
    }

    /// from the boxes: on if they make sense, a beep if not
    func commitLoop() {
        if loopBars != nil { loopOn = true; applyLoop() } else { NSSound.beep(); loopOn = false }
    }
    @Published var toast: String?
    var toastWork: DispatchWorkItem?

    func setMethods(voices: Int32? = nil, instruments: Int32? = nil) {
        if let v = voices { voiceMethod = v; UserDefaults.standard.set(Int(v), forKey: "voiceMethod") }
        if let i = instruments { instMethod = i; UserDefaults.standard.set(Int(i), forKey: "instMethod") }
        engine_set_methods(voiceMethod, instMethod)
        let at = abs(bpm - (map?.tempo ?? bpm)) < 0.01 ? " (heard away from the song's own tempo)" : ""
        say((voices != nil ? "Voices: " + stretchNames[Int(voiceMethod)] : "Instruments: " + stretchNames[Int(instMethod)]) + at)
    }

    func say(_ s: String) {
        toast = s
        toastWork?.cancel()
        let w = DispatchWorkItem { [weak self] in self?.toast = nil }
        toastWork = w
        DispatchQueue.main.asyncAfter(deadline: .now() + 3, execute: w)
    }
    @Published var map: SongMap?
    @Published var songName = ""
    @Published var error: String?
    @Published var mode = Hear.balanced {
        didSet {
            applyVoices()
        }
    }
    /// the instrumental stem, or the click in an unaccompanied song: remembered for each song
    @Published var instruments = true {
        didSet {
            engine_set_instruments(instruments ? 1 : 0)
            if let f = folder { UserDefaults.standard.set(instruments, forKey: "instruments:" + f.path) }
        }
    }
    /// the sections to rehearse, tinted on the score: remembered for each song
    @Published var markedSections = Set<String>() {
        didSet {
            if let f = folder { UserDefaults.standard.set(Array(markedSections), forKey: "sections:" + f.path) }
            score?.refresh()
        }
    }
    /// the rehearsal letters in order, with an Intro for any bars before the first; each runs to the next letter
    var sections: [(name: String, bars: ArraySlice<Bar>)] {
        guard let m = map else { return [] }
        let starts = m.bars.indices.filter { m.bars[$0].letter != nil }
        guard let first = starts.first else { return [] }
        var out: [(name: String, bars: ArraySlice<Bar>)] = first > 0 ? [("Intro", m.bars[0..<first])] : []
        for (i, a) in starts.enumerated() {
            out.append((m.bars[a].letter!, m.bars[a..<(i + 1 < starts.count ? starts[i + 1] : m.bars.count)]))
        }
        return out
    }
    /// the song's voice stems in score order, with their pans, trims and keys
    @Published var voices: [Voice] = []
    /// the voices as the Hear list and the Other checkboxes show them: soloists first
    var listed: [Int] { voices.indices.filter { voices[$0].solo } + voices.indices.filter { !voices[$0].solo } }
    var modes: [Hear] { [.balanced] + listed.map { .only($0) } + (voices.count > 1 ? [.other] : []) }
    func label(_ h: Hear) -> String {
        switch h {
        case .balanced: return "Balanced"
        case .other: return "Other"
        case .only(let i): return voices[i].name + " only"
        }
    }
    func hotkey(_ h: Hear) -> String {
        switch h {
        case .balanced: return "m"
        case .other: return "o"
        case .only(let i): return voices[i].hotkey
        }
    }
    func partName(_ key: String) -> String { voices.first { $0.key == key }?.name ?? key }
    var allVoices: Int32 { Int32((1 << voices.count) - 1) }
    /// what "Other" has checked, the voices as bits of a mask; none is the instruments alone
    @Published var otherVoices: Int32 = 0
    @Published var playing = false
    @Published var bpm = 120.0
    @Published var progress = -1.0
    @Published var heardBpm = 120.0
    @Published var where_ = "Bar 1"
    @Published var typed = ""
    @Published var twoPages = false
    @Published var volume = -3.0
    @Published var devices: [(uid: String, name: String)] = []
    @Published var deviceUID = ""
    var deviceCheck = 0
    @Published var fixes: [NoteFix] = []
    @Published var bypass = false
    /// the chyron's card of British and North American note names, for a London chorus with singers across the Atlantic
    @Published var notesCard = false
    var folder: URL?
    let volumeRange = -40.0...6.0
    var pdf: PDFDocument?
    var pdfDark: PDFDocument?
    var lastStart = 0.0
    var tempoWork: DispatchWorkItem?
    var started = false
    weak var score: ScoreCanvas?

    func open(folder: URL) {
        do {
            let data = try Data(contentsOf: folder.appendingPathComponent("player map.json"))
            let m = try JSONDecoder().decode(SongMap.self, from: data)
            let vs = Voice.from(m)
            guard (1...Int(MAX_VOICES)).contains(vs.count), vs.allSatisfy({ m.stems[$0.key] != nil }) else {
                error = "player map.json names \(vs.count) voice stems; the player takes 1 to \(MAX_VOICES)."; return
            }
            let cstrs = vs.map { strdup(folder.appendingPathComponent(m.stems[$0.key]!).path) }
                + [m.stems["I"].map { strdup(folder.appendingPathComponent($0).path) } ?? nil]
            defer { cstrs.forEach { free($0) } }
            var ptrs = cstrs.map { $0.map { UnsafePointer<CChar>($0) } }
            let cache = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("Rehearsal Player").path
            engine_set_playing(0)
            guard engine_load(&ptrs, Int32(vs.count), cache) != 0 else { error = "Couldn't read the stems named in player map.json."; return }
            var pans = vs.map(\.pan), trims = vs.map(\.trim)
            engine_set_voice_mix(&pans, &trims)
            if !started {
                started = engine_start_output() != 0
                if !started { error = "Couldn't open the audio output." }
                listDevices()
                if let u = UserDefaults.standard.string(forKey: "device"), !u.isEmpty, devices.contains(where: { $0.uid == u }) { setDevice(u) }
            }
            pdf = PDFDocument(url: folder.appendingPathComponent(m.score))
            guard pdf != nil else { error = "Couldn't open \(m.score)."; return }
            pdfDark = m.score_dark.flatMap { PDFDocument(url: folder.appendingPathComponent($0)) }
            map = m
            voices = vs
            otherVoices &= allVoices
            if case .only(let i) = mode, i >= vs.count { mode = .balanced }
            if mode == .other && vs.count < 2 { mode = .balanced }
            applyVoices()     // the engine starts each song with all its voices
            songName = folder.lastPathComponent
            self.folder = folder
            isolated = UserDefaults.standard.bool(forKey: "isolated:" + folder.path)
            instruments = UserDefaults.standard.object(forKey: "instruments:" + folder.path) as? Bool ?? true
            markedSections = Set(UserDefaults.standard.stringArray(forKey: "sections:" + folder.path) ?? [])
            bypass = false
            loopOn = false
            fixes = (try? JSONDecoder().decode([NoteFix].self, from: Data(contentsOf: fixesFile))) ?? []
            sendFixes()
            bpm = m.tempo; heardBpm = m.tempo; lastStart = m.bars[0].beat_t[0]
            error = nil
            seek(lastStart)
            UserDefaults.standard.set(folder.path, forKey: "lastFolder")
            let recent = UserDefaults.standard.stringArray(forKey: "recentFolders") ?? []
            UserDefaults.standard.set(Array(([folder.path] + recent.filter { $0 != folder.path }).prefix(12)), forKey: "recentFolders")
            SongLibrary.shared.add(folder.path)
            score?.reload()
        } catch {
            self.error = "\(folder.lastPathComponent) has no usable player map.json. (\(error.localizedDescription))"
        }
    }

    func seek(_ t: Double) { lastStart = t; engine_seek(t); score?.refresh() }
    func toggle() { engine_set_playing(engine_is_playing() != 0 ? 0 : 1) }

    func bar(at t: Double) -> Int? {
        guard let bars = map?.bars else { return nil }
        var lo = 0, hi = bars.count - 1
        while lo < hi { let mid = (lo + hi + 1) / 2; if bars[mid].beat_t[0] <= t + eps { lo = mid } else { hi = mid - 1 } }
        return lo
    }
    func go(bar n: Int) { if let b = map?.bars.first(where: { $0.num == n }) { seek(b.beat_t[0]) } }
    func go(letter: String) { if let b = map?.bars.first(where: { $0.letter == letter }) { seek(b.beat_t[0]) } }
    func typedBar(_ s: String) -> Bar? { map?.bar(typed: s) }
    /// whether any bar is played more than once
    var hasRepeats: Bool { map.map { Set($0.bars.map(\.num)).count < $0.bars.count } ?? false }
    func pass(_ i: Int) -> Int { map?.pass(i) ?? 0 }
    func step(bars d: Int) {
        guard let m = map, let i = bar(at: engine_position()) else { return }
        seek(m.bars[min(max(i + d, 0), m.bars.count - 1)].beat_t[0])
    }
    func step(beats d: Int) {
        guard let m = map else { return }
        let all = m.bars.flatMap { $0.beat_t }
        let t = engine_position() + eps
        let at = all.lastIndex(where: { $0 <= t }) ?? 0
        seek(all[min(max(at + d, 0), all.count - 1)])
    }

    func setTempo(_ v: Double) {
        guard let m = map else { return }
        bpm = min(max(v.rounded(), bpmRange.lowerBound), bpmRange.upperBound)
        tempoWork?.cancel()
        let w = DispatchWorkItem { [weak self] in
            guard let self else { return }
            engine_set_speed(self.bpm / m.tempo)
        }
        tempoWork = w
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3, execute: w)
    }
    var bpmRange: ClosedRange<Double> {
        let t = map?.tempo ?? 120
        return (t * 0.4).rounded()...(t * 1.5).rounded()
    }

    var fixesFile: URL { (folder ?? URL(fileURLWithPath: "/")).appendingPathComponent("player fixes.json") }

    func sendFixes() {
        let on = bypass ? [] : fixes
        // a fix on a part no longer among the stems goes to none of them
        let known = on.filter { f in voices.contains { $0.key == f.part } }
        var st = known.map { f in Int32(voices.firstIndex { $0.key == f.part }!) }, s0 = known.map(\.start), s1 = known.map(\.end)
        var mu = known.map { Int32($0.mute ? 1 : 0) }, se = known.map { Double($0.semitones) }
        engine_set_fixes(Int32(known.count), &st, &s0, &s1, &mu, &se)
    }

    func changeFix(_ n: Note, _ edit: (inout NoteFix) -> Void) {
        var f = fixes.first(where: { $0.id == n.id }) ?? NoteFix(id: n.id, part: n.part, start: n.start, end: n.end, mute: false, semitones: 0)
        edit(&f)
        fixes.removeAll { $0.id == n.id }
        if f.mute || f.semitones != 0 { fixes.append(f) }
        saveFixes()
    }

    func clearFix(_ id: String) { fixes.removeAll { $0.id == id }; saveFixes() }
    func clearFixes() { fixes = []; saveFixes() }

    func saveFixes() {
        let e = JSONEncoder(); e.outputFormatting = [.prettyPrinted, .sortedKeys]
        if fixes.isEmpty { try? FileManager.default.removeItem(at: fixesFile) }
        else if let d = try? e.encode(fixes) { try? d.write(to: fixesFile) }
        bypass = false
        sendFixes()
        score?.refresh()
    }

    func applyVoices() {
        switch mode {
        case .balanced: engine_set_voices(allVoices)
        case .only(let i): engine_set_voices(Int32(1 << i))
        case .other: engine_set_voices(otherVoices)
        }
    }

    func toggleOther(_ bit: Int32) {
        otherVoices ^= bit
        if otherVoices == allVoices {
            // all of them is the balanced mix, and Other starts clear again
            otherVoices = 0
            mode = .balanced
        } else { applyVoices() }
    }

    func listDevices() {
        var list: [(uid: String, name: String)] = []
        for i in 0..<engine_device_count() {
            var u = [CChar](repeating: 0, count: 512), n = [CChar](repeating: 0, count: 512)
            engine_device_info(i, &u, &n, 512)
            list.append((String(cString: u), String(cString: n)))
        }
        if list.map(\.uid) != devices.map(\.uid) { devices = list }
        // a chosen interface that's been unplugged: the Mac's own output until it's chosen again
        if !deviceUID.isEmpty, !list.contains(where: { $0.uid == deviceUID }) { setDevice("", remember: false) }
    }

    func setDevice(_ uid: String, remember: Bool = true) {
        if engine_set_device(uid) != 0 {
            deviceUID = uid
            if remember { UserDefaults.standard.set(uid, forKey: "device") }
        } else { NSSound.beep(); objectWillChange.send() }
    }

    func setVolume(_ v: Double) {
        volume = min(max((v * 2).rounded() / 2, volumeRange.lowerBound), volumeRange.upperBound)
        engine_set_master_db(volume)
        UserDefaults.standard.set(volume, forKey: "volume")
    }

    /// a bar number or a rehearsal letter, as typed in the Bar box; false if there's no such place
    func go(typed s: String) -> Bool {
        let t = s.trimmingCharacters(in: .whitespaces)
        if let b = typedBar(t) { seek(b.beat_t[0]); return true }
        if map?.bars.contains(where: { $0.letter == t.uppercased() }) == true { go(letter: t.uppercased()); return true }
        return false
    }

    func tick() {
        deviceCheck += 1
        if deviceCheck % 60 == 0 { listDevices() }
        let p = engine_is_playing() != 0
        if p != playing { playing = p }
        let wt = engine_waiting() != 0
        // the mixer has got to audio nobody asked to have rendered: a loop's start, most likely
        if wt && !waiting { engine_render_here() }
        if wt != waiting { waiting = wt }
        let pr = engine_render_progress()
        if abs(pr - progress) > 0.005 || (pr < 0) != (progress < 0) { progress = pr }
        let heard = engine_speed() * (map?.tempo ?? 120)
        if abs(heard - heardBpm) > 0.01 { heardBpm = heard }
        guard let m = map, let i = bar(at: engine_position()) else { return }
        let b = m.bars[i]
        let beat = (b.beat_t.lastIndex(where: { $0 <= engine_position() + eps }) ?? 0) + 1
        let lab = m.bars[...i].last(where: { $0.letter != nil })?.letter
        let again = pass(i)
        let s = "Bar \(b.num)" + (again > 0 ? " (\(again == 1 ? "2nd" : again == 2 ? "3rd" : "\(again + 1)th") time)" : "") + ", beat \(beat)" + (lab.map { "  ·  \($0)" } ?? "")
        if s != where_ { where_ = s }
        score?.refresh()
    }

    // true if the key was used
    func key(_ e: NSEvent) -> Bool {
        guard map != nil, e.modifierFlags.intersection([.command, .control, .option]).isEmpty else { return false }
        switch e.keyCode {
        case 49: toggle(); return true
        case 36, 76:
            if typed.isEmpty { seek(lastStart) } else { if let b = typedBar(typed) { seek(b.beat_t[0]) }; typed = "" }
            return true
        case 53: typed = ""; return true
        case 51: if !typed.isEmpty { typed.removeLast() }; return true
        case 123: e.modifierFlags.contains(.shift) ? step(beats: -1) : step(bars: -1); return true
        case 124: e.modifierFlags.contains(.shift) ? step(beats: 1) : step(bars: 1); return true
        case 126: setTempo(bpm + 1); return true
        case 125: setTempo(bpm - 1); return true
        default: break
        }
        guard let c = e.charactersIgnoringModifiers, c.count == 1 else { return false }
        if c.first!.isNumber { typed += c; return true }
        if c == "'", !typed.isEmpty { typed += c; return true }       // 17' then Return: bar 17's second time
        if let md = modes.first(where: { hotkey($0) == c }) { mode = md; return true }
        if c == "c" { instruments.toggle(); return true }
        if c == "l" { if loopBars != nil { loopOn.toggle() } else { NSSound.beep() }; return true }
        if c == "d" { darkScore.toggle(); return true }
        if c == "v" { setMethods(voices: (voiceMethod + 1) % Int32(stretchNames.count)); return true }
        if c == "i" { setMethods(instruments: (instMethod + 1) % 4); return true }
        if c.first!.isUppercase, map!.bars.contains(where: { $0.letter == c }) { go(letter: c); return true }
        return false
    }
}

// The page and, over it, the playhead and the click layer
final class ScoreCanvas: NSView {
    let pdf = PDFView()
    let overlay = Overlay()
    weak var player: Player?
    var lastPage = -1

    init(player: Player) {
        self.player = player
        super.init(frame: .zero)
        pdf.autoScales = true
        pdf.displayMode = .singlePage
        pdf.displaysPageBreaks = false
        pdf.backgroundColor = .underPageBackgroundColor
        for v in [pdf, overlay] as [NSView] { v.autoresizingMask = [.width, .height]; v.frame = bounds; addSubview(v) }
        overlay.canvas = self
        NotificationCenter.default.addObserver(forName: .PDFViewScaleChanged, object: pdf, queue: .main) { [weak self] _ in self?.refresh() }
        player.score = self
        reload()
    }
    required init?(coder: NSCoder) { fatalError() }
    override func layout() {
        super.layout()
        pdf.frame = bounds; overlay.frame = bounds
        useWholeHeight(pdf)
        pdf.autoScales = true
        refresh()
    }
    /// A scroll view keeps its content clear of the window's title bar, even a see-through one. The page may go under it.
    func useWholeHeight(_ v: NSView) {
        for sub in v.subviews {
            if let sv = sub as? NSScrollView { sv.automaticallyAdjustsContentInsets = false; sv.contentInsets = NSEdgeInsets() }
            useWholeHeight(sub)
        }
    }

    /// Dark is the song's dark copy of the score (dark_score.py), in the same pages at the same places. Without one, it's a filter
    /// on the page's view: white goes to a soft dark grey and black to a soft white, with the hue turned back after the inversion.
    func applyDark() {
        let dark = player?.darkScore ?? false
        let wanted = dark ? (player?.pdfDark ?? player?.pdf) : player?.pdf
        if pdf.document !== wanted {
            let at = pdf.currentPage.flatMap { pdf.document?.index(for: $0) } ?? 0
            pdf.document = wanted
            if let page = wanted?.page(at: at) { pdf.go(to: page) }
            pdf.autoScales = true
        }
        pdf.wantsLayer = true
        pdf.layerUsesCoreImageFilters = true
        if dark, player?.pdfDark != nil {
            pdf.contentFilters = []
            pdf.backgroundColor = NSColor(srgbRed: 0.09, green: 0.09, blue: 0.095, alpha: 1)
            return
        }
        guard dark, let invert = CIFilter(name: "CIColorInvert"), let hue = CIFilter(name: "CIHueAdjust"), let soft = CIFilter(name: "CIColorMatrix") else {
            pdf.contentFilters = []
            pdf.backgroundColor = .underPageBackgroundColor
            return
        }
        hue.setValue(Double.pi, forKey: "inputAngle")
        // in linear light, which is how these filters work: about 12% and 90% on screen
        let k: CGFloat = 0.76, b: CGFloat = 0.014
        soft.setValue(CIVector(x: k, y: 0, z: 0, w: 0), forKey: "inputRVector")
        soft.setValue(CIVector(x: 0, y: k, z: 0, w: 0), forKey: "inputGVector")
        soft.setValue(CIVector(x: 0, y: 0, z: k, w: 0), forKey: "inputBVector")
        soft.setValue(CIVector(x: b, y: b, z: b, w: 0), forKey: "inputBiasVector")
        pdf.contentFilters = [invert, hue, soft]
        pdf.backgroundColor = .white       // the surround, filtered along with the page
    }

    func reload() { pdf.document = nil; applyDark(); lastPage = -1; setTwoPages(player?.twoPages ?? false); refresh() }
    func setTwoPages(_ on: Bool) { pdf.displayMode = on ? .twoUp : .singlePage; pdf.autoScales = true }

    func refresh() {
        guard let p = player, let m = p.map, let doc = pdf.document else { return }
        // while playing, turn a moment early so the first bar overleaf can be read
        let t = engine_position()
        let look = t + (engine_is_playing() != 0 ? 0.4 * engine_speed() : 0)
        if let i = p.bar(at: look) {
            let pg = m.bars[i].page
            if pg != lastPage, let page = doc.page(at: pg), !pdf.visiblePages.contains(page) || lastPage < 0 {
                pdf.go(to: page)
            }
            lastPage = pg
        }
        overlay.needsDisplay = true
    }

    /// x and system of time t
    func place(_ t: Double) -> (Bar, Double)? {
        guard let p = player, let m = p.map, let i = p.bar(at: t) else { return nil }
        let b = m.bars[i]
        let k = b.beat_t.lastIndex(where: { $0 <= t + eps }) ?? 0
        let t0 = b.beat_t[k], t1 = k + 1 < b.beat_t.count ? b.beat_t[k + 1] : b.end_t
        let x0 = b.beat_x[k], x1 = k + 1 < b.beat_x.count ? b.beat_x[k + 1] : b.xb
        let f = t < t0 ? 0 : min(1, (t - t0) / max(t1 - t0, 1e-6))
        return (b, x0 + (x1 - x0) * f)
    }

    /// the sung note whose head is at a point in this view
    func note(near pt: NSPoint) -> Note? {
        guard let m = player?.map, let doc = pdf.document, let page = pdf.page(for: pt, nearest: true) else { return nil }
        let idx = doc.index(for: page)
        let q = pdf.convert(pt, to: page)
        let y = m.page_height - q.y
        var best: (Double, Note)?
        for n in m.notes ?? [] {
            for h in n.heads where h.page == idx {
                let d = hypot(h.x - q.x, h.y - y)
                if d < 12, best == nil || d < best!.0 { best = (d, n) }
            }
        }
        return best?.1
    }

    /// the beat nearest a point in this view
    func beat(near pt: NSPoint) -> (x: Double, t: Double, bar: Bar)? {
        guard let m = player?.map, let doc = pdf.document, let page = pdf.page(for: pt, nearest: true) else { return nil }
        let idx = doc.index(for: page)
        let q = pdf.convert(pt, to: page)
        let y = m.page_height - q.y
        let systems = m.systems.filter { $0.page == idx }
        guard let s = systems.min(by: { dist(y, $0) < dist(y, $1) }) else { return nil }
        var best: (Double, Double, Bar)?
        // a bar in a repeat is here once for each time it's played: the time nearest the playhead
        let now = engine_position()
        func better(_ x: Double, _ t: Double) -> Bool {
            guard let (bx, bt, _) = best else { return true }
            let d = abs(x - q.x), bd = abs(bx - q.x)
            return abs(d - bd) < 0.01 ? abs(t - now) < abs(bt - now) : d < bd
        }
        for b in m.bars where b.page == idx && b.sys == s.sys {
            for (x, t) in zip(b.beat_x, b.beat_t) where better(x, t) { best = (x, t, b) }
        }
        return best.map { ($0.0, $0.1, $0.2) }
    }
    func dist(_ y: Double, _ s: Sys) -> Double { y < s.top ? s.top - y : (y > s.bottom ? y - s.bottom : 0) }

    func rect(x: Double, bar: Bar) -> NSRect? {
        guard let m = player?.map, let page = pdf.document?.page(at: bar.page),
              let s = m.systems.first(where: { $0.page == bar.page && $0.sys == bar.sys }) else { return nil }
        let a = pdf.convert(NSPoint(x: x, y: m.page_height - s.top + 10), from: page)
        let b = pdf.convert(NSPoint(x: x, y: m.page_height - s.bottom - 8), from: page)
        return NSRect(x: a.x, y: min(a.y, b.y), width: 0, height: abs(a.y - b.y))
    }
}

final class Overlay: NSView {
    weak var canvas: ScoreCanvas?
    var hover: (x: Double, t: Double, bar: Bar)?
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }     // one click from Zoom both comes forward and moves
    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        trackingAreas.forEach { removeTrackingArea($0) }
        addTrackingArea(NSTrackingArea(rect: bounds, options: [.mouseMoved, .mouseEnteredAndExited, .activeAlways, .inVisibleRect], owner: self))
    }
    override func mouseMoved(with e: NSEvent) { hover = canvas?.beat(near: convert(e.locationInWindow, from: nil)); needsDisplay = true }
    override func mouseExited(with e: NSEvent) { hover = nil; needsDisplay = true }
    override func mouseDown(with e: NSEvent) {
        guard let c = canvas, let b = c.beat(near: convert(e.locationInWindow, from: nil)) else { return }
        c.player?.seek(b.t)
        if e.clickCount == 2, engine_is_playing() == 0 { engine_set_playing(1) }
    }
    override func rightMouseDown(with e: NSEvent) {
        guard let c = canvas, let p = c.player, let n = c.note(near: convert(e.locationInWindow, from: nil)) else { return }
        let fix = p.fixes.first(where: { $0.id == n.id })
        let beat = n.beat == n.beat.rounded() ? String(Int(n.beat)) : String(n.beat)
        let menu = NSMenu()
        menu.autoenablesItems = false
        let head = menu.addItem(withTitle: "\(p.partName(n.part)), bar \(n.bar), beat \(beat)" + (n.word.isEmpty ? "" : " “\(n.word)”"), action: nil, keyEquivalent: "")
        head.isEnabled = false
        func item(_ title: String, _ on: Bool = false, _ act: @escaping () -> Void) {
            let i = ClosureItem(title: title, act: act)
            i.state = on ? .on : .off
            menu.addItem(i)
        }
        item("Mute", fix?.mute == true) { p.changeFix(n) { $0.mute.toggle(); if $0.mute { $0.semitones = 0 } } }
        item("Up a Semitone") { p.changeFix(n) { $0.mute = false; $0.semitones += 1 } }
        item("Down a Semitone") { p.changeFix(n) { $0.mute = false; $0.semitones -= 1 } }
        if let f = fix {
            menu.addItem(.separator())
            item("Start 20 ms Earlier") { p.changeFix(n) { $0.start = f.start - 0.02 } }
            item("Start 20 ms Later") { p.changeFix(n) { $0.start = min(f.start + 0.02, f.end - 0.04) } }
            item("End 20 ms Earlier") { p.changeFix(n) { $0.end = max(f.end - 0.02, f.start + 0.04) } }
            item("End 20 ms Later") { p.changeFix(n) { $0.end = f.end + 0.02 } }
            menu.addItem(.separator())
            item("Remove This Fix") { p.clearFix(n.id) }
        }
        NSMenu.popUpContextMenu(menu, with: e, for: self)
    }
    override func scrollWheel(with e: NSEvent) { canvas?.pdf.scrollWheel(with: e) }
    override func magnify(with e: NSEvent) { canvas?.pdf.magnify(with: e) }
    override func draw(_ dirty: NSRect) {
        guard let c = canvas else { return }
        drawSections(c)
        drawFixes(c)
        drawLoop(c)
        if let h = hover, let r = c.rect(x: h.x, bar: h.bar), c.pdf.visiblePages.contains(where: { c.pdf.document?.index(for: $0) == h.bar.page }) {
            NSColor.systemBlue.withAlphaComponent(0.25).setFill()
            NSRect(x: r.minX - 1, y: r.minY, width: 2, height: r.height).fill()
        }
        if let (b, x) = c.place(engine_position()), let r = c.rect(x: x, bar: b),
           c.pdf.visiblePages.contains(where: { c.pdf.document?.index(for: $0) == b.page }) {
            NSColor.systemRed.withAlphaComponent(0.75).setFill()
            NSRect(x: r.minX - 1, y: r.minY, width: 2, height: r.height).fill()
        }
    }
}

extension Overlay {
    /// a tint over the bars of each section marked to rehearse, words under the staves included, one piece per system
    func drawSections(_ c: ScoreCanvas) {
        guard let p = c.player, let m = p.map, !p.markedSections.isEmpty, let doc = c.pdf.document else { return }
        NSColor.systemBlue.withAlphaComponent(p.darkScore ? 0.11 : 0.065).setFill()
        for sec in p.sections where p.markedSections.contains(sec.name) {
            var at = sec.bars.startIndex
            while at < sec.bars.endIndex {
                let a = sec.bars[at]
                var end = at
                while end + 1 < sec.bars.endIndex, sec.bars[end + 1].page == a.page, sec.bars[end + 1].sys == a.sys { end += 1 }
                let b = sec.bars[end]
                at = end + 1
                guard let page = doc.page(at: a.page), c.pdf.visiblePages.contains(page),
                      let s = m.systems.first(where: { $0.page == a.page && $0.sys == a.sys }) else { continue }
                let p0 = c.pdf.convert(NSPoint(x: a.xa, y: m.page_height - s.top + 14), from: page)
                let p1 = c.pdf.convert(NSPoint(x: b.xb, y: m.page_height - s.bottom - 22), from: page)
                NSRect(x: p0.x, y: min(p0.y, p1.y), width: p1.x - p0.x, height: abs(p0.y - p1.y)).fill()
            }
        }
    }

    /// green lines at the loop's ends
    func drawLoop(_ c: ScoreCanvas) {
        guard let p = c.player, p.loopOn, let (a, b) = p.loopBars else { return }
        NSColor.systemGreen.withAlphaComponent(0.8).setFill()
        for (x, bar) in [(a.xa + 2, a), (b.xb - 2, b)] {
            guard let page = c.pdf.document?.page(at: bar.page), c.pdf.visiblePages.contains(page), let r = c.rect(x: x, bar: bar) else { continue }
            NSRect(x: r.minX - 1.5, y: r.minY, width: 3, height: r.height).fill()
        }
    }

    /// a ring on each corrected note's heads, grey while they're bypassed: ✕ muted, or the semitones
    func drawFixes(_ c: ScoreCanvas) {
        guard let p = c.player, let m = p.map, !p.fixes.isEmpty, let doc = c.pdf.document else { return }
        let notes = m.notes ?? []
        for f in p.fixes {
            guard let n = notes.first(where: { $0.id == f.id }) else { continue }
            let col: NSColor = p.bypass ? .systemGray : (f.mute ? .systemRed : .systemOrange)
            for h in n.heads {
                guard let page = doc.page(at: h.page), c.pdf.visiblePages.contains(page) else { continue }
                let pt = c.pdf.convert(NSPoint(x: h.x, y: m.page_height - h.y), from: page)
                let ring = NSBezierPath(ovalIn: NSRect(x: pt.x - 9, y: pt.y - 9, width: 18, height: 18))
                col.setStroke(); ring.lineWidth = 1.5; ring.stroke()
                let text = f.mute ? "✕" : (f.semitones > 0 ? "+\(f.semitones)" : "\(f.semitones)".replacingOccurrences(of: "-", with: "−"))
                (text as NSString).draw(at: NSPoint(x: pt.x + 9, y: pt.y + 5), withAttributes: [.font: NSFont.boldSystemFont(ofSize: 11), .foregroundColor: col])
            }
        }
    }
}

/// a menu item that runs a closure
final class ClosureItem: NSMenuItem {
    let act: () -> Void
    init(title: String, act: @escaping () -> Void) {
        self.act = act
        super.init(title: title, action: #selector(run), keyEquivalent: "")
        target = self
    }
    required init(coder: NSCoder) { fatalError() }
    @objc func run() { act() }
}

struct ScoreRep: NSViewRepresentable {
    let player: Player
    func makeNSView(context: Context) -> ScoreCanvas { ScoreCanvas(player: player) }
    func updateNSView(_ v: ScoreCanvas, context: Context) {}
}

struct OtherParts: View {
    @ObservedObject var p: Player
    var rows: [(String, Int32)] { p.listed.map { (p.voices[$0].name, Int32(1 << $0)) } }
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Check all parts you want to hear:").font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            ForEach(rows, id: \.0) { name, bit in
                Toggle(name, isOn: Binding(get: { p.otherVoices & bit != 0 }, set: { _ in p.toggleOther(bit) })).toggleStyle(.checkbox)
            }
        }.padding(.leading, 20)
    }
}

private struct Stretches: LayoutValueKey { static let defaultValue = false }
extension View {
    /// a row of FitColumn that takes the column's width instead of setting it: a slider, a menu, a rule, wrapping words
    func stretches() -> some View { layoutValue(key: Stretches.self, value: true) }
}

/// rows top to bottom, the column as wide as its widest row that doesn't stretch, so the sidebar gives the score every point it can
struct FitColumn: Layout {
    var spacing: CGFloat = 10
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let w = subviews.filter { !$0[Stretches.self] }.map { $0.sizeThatFits(.unspecified).width }.max() ?? 0
        let hs = subviews.map { $0.sizeThatFits(ProposedViewSize(width: w, height: nil)).height }
        return CGSize(width: w, height: hs.reduce(0, +) + spacing * CGFloat(max(0, hs.count - 1)))
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        let p = ProposedViewSize(width: bounds.width, height: nil)
        for s in subviews {
            s.place(at: CGPoint(x: bounds.minX, y: y), proposal: p)
            y += s.sizeThatFits(p).height + spacing
        }
    }
}

/// the controls, down the left edge, so the score has the window's whole height
struct Controls: View {
    @ObservedObject var p: Player
    @State var tempoText = ""
    @State var barText = ""
    @State var volText = ""
    @FocusState var editing: Bool
    @FocusState var editingBar: Bool
    @FocusState var editingVol: Bool
    @FocusState var editingBar2: Bool
    // back to the score's keys (space, arrows and so on) once a box has been used
    func leave() { editing = false; editingBar = false; editingVol = false; editingBar2 = false; NSApp.keyWindow?.makeFirstResponder(nil) }
    func volString(_ v: Double) -> String { v == v.rounded() ? String(Int(v)) : String(format: "%.1f", v) }
    func heading(_ t: String) -> some View { Text(t).font(.caption).foregroundStyle(.secondary) }
    func rule() -> some View { Rectangle().fill(Color(nsColor: .separatorColor)).frame(height: 1).stretches() }
    var body: some View {
        ScrollView(.vertical, showsIndicators: false) {
            FitColumn {
                HStack(spacing: 8) {
                    Button(action: p.toggle) { Image(systemName: p.playing ? "pause.fill" : "play.fill").frame(width: 22, height: 18) }
                        .keyboardShortcut(.none)
                    Text(p.typed.isEmpty ? p.where_ : "Go to bar \(p.typed)…")
                        .font(.system(size: 12, weight: .medium).monospacedDigit()).lineLimit(2).fixedSize(horizontal: false, vertical: true)
                }.stretches()
                HStack(spacing: 6) {
                    Text("Go to bar").fixedSize()
                    TextField("", text: $barText).frame(width: 44).focused($editingBar).multilineTextAlignment(.trailing)
                        .onSubmit {
                            if p.go(typed: barText) { barText = ""; leave() } else { NSSound.beep() }
                        }
                        .help("A bar number or a rehearsal letter. In a repeat, ' or b after the number for the 2nd time through: 17' or 17b")
                }
                if p.hasRepeats {
                    Text("' or b for 2nd time in a repeat: 17' or 17b").font(.caption).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true).stretches()
                }
                rule()
                HStack(spacing: 6) {
                    Text("Tempo ♩ =").fixedSize()
                    TextField("", text: $tempoText).frame(width: 44).focused($editing).multilineTextAlignment(.trailing)
                        .onSubmit { if let v = Double(tempoText) { p.setTempo(v) }; tempoText = String(Int(p.bpm)); leave() }
                    Stepper("", value: Binding(get: { p.bpm }, set: { p.setTempo($0) }), in: p.bpmRange, step: 1).labelsHidden()
                }
                HStack(spacing: 6) {
                    Slider(value: Binding(get: { p.bpm }, set: { p.setTempo($0) }), in: p.bpmRange).controlSize(.small)
                    Button("Reset") { if let t = p.map?.tempo { p.setTempo(t) } }.controlSize(.small)
                }.stretches()
                rule()
                heading("Hear")
                Picker("", selection: $p.mode) {
                    ForEach(p.modes, id: \.self) { Text(p.label($0)).tag($0) }
                }.pickerStyle(.radioGroup).labelsHidden()
                if p.mode == .other { OtherParts(p: p).stretches() }
                Toggle("Instruments / click", isOn: $p.instruments).toggleStyle(.checkbox).help("c")
                rule()
                Toggle("Loop", isOn: Binding(get: { p.loopOn }, set: { on in if on { p.commitLoop() } else { p.loopOn = false } })).toggleStyle(.checkbox)
                HStack(spacing: 6) {
                    Text("bar").fixedSize()
                    TextField("", text: $p.loopFrom).frame(width: 44).focused($editingBar2).multilineTextAlignment(.trailing)
                        .onSubmit { p.commitLoop(); leave() }
                    Text("to").fixedSize()
                    TextField("", text: $p.loopTo).frame(width: 44).focused($editingBar2).multilineTextAlignment(.trailing)
                        .onSubmit { p.commitLoop(); leave() }
                        .help("Bar numbers or letters. In a repeat, ' or b after the number for the 2nd time through: 17' or 17b")
                }
                if !p.sections.isEmpty {
                    rule()
                    heading("Sections to rehearse")
                    let names = p.sections.map(\.name)
                    // four to a row, each column as wide as its widest name
                    Grid(alignment: .leading, horizontalSpacing: 6, verticalSpacing: 4) {
                        ForEach(Array(stride(from: 0, to: names.count, by: 4)), id: \.self) { i in
                            GridRow {
                                ForEach(names[i..<min(i + 4, names.count)], id: \.self) { name in
                                    Toggle(name, isOn: Binding(get: { p.markedSections.contains(name) }, set: { on in
                                        if on { p.markedSections.insert(name) } else { p.markedSections.remove(name) }
                                    })).toggleStyle(.checkbox).fixedSize()
                                }
                            }
                        }
                    }
                }
                rule()
                HStack(spacing: 6) {
                    Text("Volume").fixedSize()
                    TextField("", text: $volText).frame(width: 44).focused($editingVol).multilineTextAlignment(.trailing)
                        .onSubmit {
                            let t = volText.replacingOccurrences(of: "−", with: "-").replacingOccurrences(of: "dB", with: "", options: .caseInsensitive)
                                .trimmingCharacters(in: .whitespaces)
                            if let v = Double(t) { p.setVolume(v) } else { NSSound.beep() }
                            volText = volString(p.volume)
                            leave()
                        }
                    Text("dB").fixedSize()
                }
                Slider(value: Binding(get: { p.volume }, set: { p.setVolume($0) }), in: p.volumeRange).controlSize(.small).stretches()
                heading("Output")
                Picker("", selection: Binding(get: { p.deviceUID }, set: { p.setDevice($0) })) {
                    Text("System output").tag("")
                    ForEach(p.devices, id: \.uid) { Text($0.name).tag($0.uid) }
                }.labelsHidden().controlSize(.small).help("Audio output").stretches()
                rule()
                heading("Chyron")
                Toggle("Note names 🇬🇧 🇨🇦", isOn: $p.notesCard).toggleStyle(.checkbox)
                    .help("Shows the British and North American names for whole to 32nd notes on the chyron")
                rule()
                heading("Score")
                Picker("", selection: $p.darkScore) {
                    Text("Light").tag(false)
                    Text("Dark").tag(true)
                }.pickerStyle(.radioGroup).horizontalRadioGroupLayout().labelsHidden()
                rule()
                heading("Source files")
                Picker("", selection: $p.isolated) {
                    Text("1 purely isolated voice\nper audio file").tag(true)
                    Text("part-predominant files").tag(false)
                }.pickerStyle(.radioGroup).labelsHidden()
                if let f = p.folder?.path {
                    rule()
                    heading("Tags")
                    TagEditor(path: f, leaveAfter: true).id(f).stretches()
                }
            }
            .padding(.horizontal, 10).padding(.top, 34).padding(.bottom, 10)     // the top clears the window's buttons
        }
        .fixedSize(horizontal: true, vertical: false)
        .onChange(of: p.bpm) { tempoText = String(Int($0)) }
        .onChange(of: p.volume) { if !editingVol { volText = volString($0) } }
        .onAppear { tempoText = String(Int(p.bpm)); volText = volString(p.volume) }
    }
}

struct RootView: View {
    @ObservedObject var p: Player
    func note<V: View>(_ v: V) -> some View { v.padding(5).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 6)) }
    var body: some View {
        HStack(spacing: 0) {
            Controls(p: p)
            Divider()
            ZStack {
                if let e = p.error {
                    Text(e).padding().frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if p.map == nil {
                    Text("File ▸ Open Song Folder…").foregroundStyle(.secondary).frame(maxWidth: .infinity, maxHeight: .infinity)
                }
                ScoreRep(player: p).opacity(p.map == nil || p.error != nil ? 0 : 1)
                    .overlay(alignment: .topTrailing) {
                        VStack(alignment: .trailing, spacing: 4) {
                            if let t = p.toast { note(Text(t).font(.caption)) }
                            if p.waiting { note(Text("Getting the audio ready…").font(.caption)) }
                            else if p.progress >= 0 {
                                // playback doesn't wait for this: it only matters for jumping around at once
                                note(HStack(spacing: 6) {
                                    ProgressView(value: p.progress).frame(width: 50).controlSize(.mini)
                                    Text("rendering the rest").font(.caption2)
                                }.foregroundStyle(.secondary))
                            }
                        }.padding(6)
                    }
            }
        }
        .ignoresSafeArea()
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    func menuNeedsUpdate(_ menu: NSMenu) {
        if menu.title == "Recent Songs" {
            menu.removeAllItems()
            let map = "player map.json"
            for path in UserDefaults.standard.stringArray(forKey: "recentFolders") ?? [] where
                !SongLibrary.isScratch(path) && FileManager.default.fileExists(atPath: (path as NSString).appendingPathComponent(map)) {
                let it = ClosureItem(title: (path as NSString).lastPathComponent) { [weak self] in self?.player.open(folder: URL(fileURLWithPath: path)) }
                it.state = path == player.folder?.path ? .on : .off
                menu.addItem(it)
            }
            if menu.items.isEmpty { menu.addItem(withTitle: "No Recent Songs", action: nil, keyEquivalent: "").isEnabled = false }
            return
        }
        for it in menu.items where it.tag >= 100 {
            it.state = (it.tag >= 200 ? Int32(it.tag - 200) == player.instMethod : Int32(it.tag - 100) == player.voiceMethod) ? .on : .off
        }
    }
    let player = Player()
    var window: NSWindow!
    var findWindow: NSWindow?
    var timer: Timer?
    var chyron: ChyronServer?

    func applicationDidFinishLaunching(_ n: Notification) {
        NSApp.setActivationPolicy(.regular)
        // the right 60% of the screen: the rest is for the Zoom window
        let vis = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 800, height: 900)
        let right = NSRect(x: vis.minX + vis.width * 0.4, y: vis.minY, width: vis.width * 0.6, height: vis.height)
        window = NSWindow(contentRect: right, styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
        // no title bar taking the score's height: the buttons sit over the controls, and the top of the window still drags it
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.title = "Rehearsal Player"
        window.minSize = NSSize(width: 640, height: 480)
        window.setFrame(right, display: false)
        window.setFrameAutosaveName("sidebar layout")
        window.contentView = NSHostingView(rootView: RootView(p: player))
        window.makeKeyAndOrderFront(nil)
        buildMenu()
        SongLibrary.shared.start()
        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] e in
            guard let self, e.window === self.window else { return e }     // the score's keys are for its own window
            if self.window.firstResponder is NSText { return e }     // typing a tempo
            return self.player.key(e) ? nil : e
        }
        if let v = UserDefaults.standard.object(forKey: "volume") as? Double { player.setVolume(v) }
        engine_set_methods(player.voiceMethod, player.instMethod)
        let args = CommandLine.arguments.dropFirst().filter { !$0.hasPrefix("-") }
        if let a = args.first { player.open(folder: URL(fileURLWithPath: a)) }
        else if let last = UserDefaults.standard.string(forKey: "lastFolder") { player.open(folder: URL(fileURLWithPath: last)) }
        else { openFolder() }
        timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 30, repeats: true) { [weak self] _ in self?.player.tick() }
        RunLoop.main.add(timer!, forMode: .common)
        chyron = ChyronServer(state: { [weak self] in self?.player.chyronState(at: $0, lead: $1) ?? [:] }, failed: { [weak self] in self?.player.say($0) })
        NSApp.activate(ignoringOtherApps: true)
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ n: Notification) { engine_stop_output() }

    @objc func openFolder() {
        let o = NSOpenPanel()
        o.canChooseDirectories = true; o.canChooseFiles = false
        o.message = "Choose a song folder that has a player map.json"
        if o.runModal() == .OK, let u = o.url { player.open(folder: u) }
    }
    @objc func findSongs() {
        SongLibrary.shared.refresh()
        if findWindow == nil {
            let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 560, height: 620), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
            w.title = "Find Songs"
            w.isReleasedWhenClosed = false
            w.contentView = NSHostingView(rootView: FindSongs(p: player) { [weak w] in w?.orderOut(nil) })
            w.center()
            w.setFrameAutosaveName("find songs")
            findWindow = w
        }
        findWindow?.makeKeyAndOrderFront(nil)
    }
    @objc func toggleBypass(_ item: NSMenuItem) {
        player.bypass.toggle()
        item.state = player.bypass ? .on : .off
        player.sendFixes()
        player.score?.refresh()
    }
    @objc func clearAll() {
        guard !player.fixes.isEmpty else { return }
        let a = NSAlert()
        a.messageText = "Remove all \(player.fixes.count) note fixes for this song?"
        a.addButton(withTitle: "Remove All"); a.addButton(withTitle: "Cancel")
        if a.runModal() == .alertFirstButtonReturn { player.clearFixes() }
    }
    @objc func copyChyron() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(ChyronServer.address, forType: .string)
        player.say("Copied \(ChyronServer.address): in OBS, add a Browser Source with this URL")
    }
    @objc func toggleTwo() { player.twoPages.toggle(); player.score?.setTwoPages(player.twoPages) }

    func buildMenu() {
        let main = NSMenu()
        let app = NSMenuItem(); main.addItem(app)
        let am = NSMenu(); am.addItem(withTitle: "Quit Rehearsal Player", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"); app.submenu = am
        let file = NSMenuItem(); main.addItem(file)
        let fm = NSMenu(title: "File"); fm.addItem(withTitle: "Open Song Folder…", action: #selector(openFolder), keyEquivalent: "o")
        let rm = NSMenu(title: "Recent Songs"); rm.delegate = self
        rm.addItem(withTitle: "No Recent Songs", action: nil, keyEquivalent: "").isEnabled = false
        fm.addItem(withTitle: "Recent Songs", action: nil, keyEquivalent: "").submenu = rm
        fm.addItem(withTitle: "Find Songs…", action: #selector(findSongs), keyEquivalent: "O")
        file.submenu = fm
        let view = NSMenuItem(); main.addItem(view)
        let vm = NSMenu(title: "View"); vm.addItem(withTitle: "Two Pages Side by Side", action: #selector(toggleTwo), keyEquivalent: "2")
        vm.addItem(.separator())
        vm.addItem(withTitle: "Copy Chyron Address for OBS", action: #selector(copyChyron), keyEquivalent: "")
        view.submenu = vm
        let st = NSMenuItem(); main.addItem(st)
        let sm = NSMenu(title: "Stretch")
        sm.delegate = self
        let vh = sm.addItem(withTitle: "Voices (v cycles)", action: nil, keyEquivalent: ""); vh.isEnabled = false
        for (i, n) in stretchNames.enumerated() {
            let it = ClosureItem(title: n) { [weak self] in self?.player.setMethods(voices: Int32(i)) }; it.tag = 100 + i; sm.addItem(it)
        }
        sm.addItem(.separator())
        let ih = sm.addItem(withTitle: "Instruments (i cycles)", action: nil, keyEquivalent: ""); ih.isEnabled = false
        for (i, n) in stretchNames.dropLast().enumerated() {
            let it = ClosureItem(title: n) { [weak self] in self?.player.setMethods(instruments: Int32(i)) }; it.tag = 200 + i; sm.addItem(it)
        }
        st.submenu = sm
        let fix = NSMenuItem(); main.addItem(fix)
        let xm = NSMenu(title: "Fixes")
        xm.addItem(withTitle: "Hear Without Fixes", action: #selector(toggleBypass(_:)), keyEquivalent: "f")
        xm.addItem(withTitle: "Remove All Fixes…", action: #selector(clearAll), keyEquivalent: "")
        fix.submenu = xm
        NSApp.mainMenu = main
    }
}

let delegate = AppDelegate()
let app = NSApplication.shared
app.delegate = delegate
app.run()
