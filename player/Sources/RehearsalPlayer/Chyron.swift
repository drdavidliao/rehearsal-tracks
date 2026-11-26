// A chyron for a video call: the player serves a page on this Mac that OBS shows as a Browser Source.
//   http://localhost:8766/        the chyron (player/chyron.html, in the app's Resources), on a see-through background
//   http://localhost:8766/state   what it shows, as JSON; /state?at=SECONDS as if the playhead were there;
//                                  &lead=MS for where it will be that many milliseconds from now
// The port is the "chyronPort" default. Only this Mac can reach it.
import AppKit
import CEngine
import Network

extension Player {
    /// a bar in play order, with the time through a repeat: "17", "17 (2nd time)"
    func barLabel(_ i: Int) -> String {
        guard let m = map else { return "" }
        let again = pass(i)
        return "\(m.bars[i].num)" + (again > 0 ? " (\(ordinal(again + 1)) time)" : "")
    }
    func ordinal(_ n: Int) -> String {
        let suffix = (11...13).contains(n % 100) ? "th" : n % 10 == 1 ? "st" : n % 10 == 2 ? "nd" : n % 10 == 3 ? "rd" : "th"
        return "\(n)\(suffix)"
    }

    /// Where bar i is, as a conductor says it: "B", "1 after B", "2 before C", or else "B: 34".
    /// With numbered marks, or before the first mark, it is "Bar 34". Counted in play order, so a repeat's second time counts again.
    func spoken(_ i: Int) -> String {
        guard let m = map else { return "" }
        let starts = m.bars.indices.filter { m.bars[$0].letter != nil }
        let prev = starts.last { $0 <= i }, next = starts.first { $0 > i }
        let again = pass(i) > 0 ? " (\(ordinal(pass(i) + 1)) time)" : ""
        if let p = prev, p == i { return m.bars[p].letter! + again }
        let after = prev.map { i - $0 }, before = next.map { $0 - i }
        // the nearer letter; a bar as near to both is after the one it's in
        if let a = after, a <= 2, before == nil || a <= before! { return "\(a) after \(m.bars[prev!].letter!)" + again }
        if let b = before, b <= 2 { return "\(b) before \(m.bars[next!].letter!)" + again }
        // a mark that's a bar number already says where it is: "Bar 15", not "12: 15"
        guard let p = prev, let mark = m.bars[p].letter, Int(mark) == nil else { return "Bar \(barLabel(i))" }
        return "\(mark): \(barLabel(i))"
    }

    /// who's heard, for the chyron
    var partLabel: String {
        let noInst = !instruments && map?.stems["I"] != nil ? " (a cappella)" : ""
        switch mode {
        case .balanced: return "Tutti" + noInst
        case .only(let i): return voices[i].name + noInst
        case .other:
            let names = listed.filter { otherVoices & Int32(1 << $0) != 0 }.map { voices[$0].name }
            return names.isEmpty ? (instruments ? "Accompaniment only" : "Silence") : names.joined(separator: " + ") + noInst
        }
    }

    /// what the chyron shows, and the plain facts under it
    /// The playhead `lead` seconds from now, so a chyron that reaches the viewer late (OBS adds its own delay) shows where
    /// the music is when they see it: ahead by the lead times the speed while playing, and round to the loop's start when
    /// that passes the loop's end. A moment given by `at` moves ahead as if playing, so the lead can be tried while stopped.
    func ahead(_ t: Double, lead: Double, at given: Bool) -> Double {
        guard lead > 0, given || engine_is_playing() != 0 else { return t }
        var u = t + lead * engine_speed()
        if loopOn, let (a, b) = loopBars, t < b.end_t, u >= b.end_t { u = a.beat_t[0] + (u - b.end_t) }
        return u
    }

    func chyronState(at: Double? = nil, lead: Double = 0) -> [String: Any] {
        guard let m = map, error == nil else { return ["song": NSNull(), "started": playerStarted, "notes_card": notesCard, "announcement": announced] }
        let t = ahead(at ?? engine_position(), lead: lead, at: at != nil)
        let i = bar(at: t) ?? 0
        let b = m.bars[i]
        let beat = (b.beat_t.lastIndex(where: { $0 <= t + eps }) ?? 0) + 1
        let secs = sections
        let current = secs.last { $0.bars.startIndex <= i }?.name
        var loop: Any = NSNull(), loopEnds: Any = NSNull()
        if loopOn, let (a, z) = loopBars,
           let ai = m.bars.firstIndex(where: { $0.beat_t[0] == a.beat_t[0] }), let zi = m.bars.firstIndex(where: { $0.end_t == z.end_t }) {
            loop = "Loop from \(barLabel(ai)) to \(barLabel(zi))"
            loopEnds = [barLabel(ai), barLabel(zi)]
        }
        let modeName: String
        switch mode { case .balanced: modeName = "balanced"; case .only: modeName = "only"; case .other: modeName = "other" }
        return [
            "song": songName, "started": playerStarted, "notes_card": notesCard, "announcement": announced,
            "playing": engine_is_playing() != 0,
            "location": spoken(i),
            "part": partLabel,
            "loop": loop, "loop_bars": loopEnds,
            "sections": secs.filter { markedSections.contains($0.name) }.map { ["name": $0.name, "current": $0.name == current] },
            // the facts, for anything else that reads this
            "bar": b.num, "pass": pass(i), "beat": beat, "section": current ?? NSNull(), "time": t,
            "mode": modeName, "instruments": instruments, "tempo": bpm, "song_tempo": m.tempo,
            "marked": secs.map(\.name).filter { markedSections.contains($0) },
            "folder": folder?.path ?? NSNull(),
        ]
    }
}

/// a stamp for this run of the player (set at the first request): a page that sees it change knows the player restarted
let playerStarted = Date().timeIntervalSince1970

/// a little HTTP server on the loopback address, answered on the main thread, where the player's state lives
final class ChyronServer {
    static var port: UInt16 { UInt16(UserDefaults.standard.integer(forKey: "chyronPort")).nonZero ?? 8766 }
    static var address: String { "http://localhost:\(port)/" }
    let listener: NWListener
    let state: (Double?, Double) -> [String: Any]

    init?(state: @escaping (Double?, Double) -> [String: Any], failed: @escaping (String) -> Void) {
        self.state = state
        let params = NWParameters.tcp
        params.allowLocalEndpointReuse = true
        params.requiredLocalEndpoint = .hostPort(host: .ipv4(.loopback), port: NWEndpoint.Port(rawValue: Self.port)!)
        guard let l = try? NWListener(using: params) else { return nil }
        listener = l
        l.newConnectionHandler = { [weak self] c in
            c.start(queue: .main)
            self?.read(c, Data())
        }
        l.stateUpdateHandler = { s in
            if case .failed(let e) = s { failed("The chyron couldn't use port \(Self.port): \(e.localizedDescription)") }
        }
        l.start(queue: .main)
    }

    private func read(_ c: NWConnection, _ got: Data) {
        c.receive(minimumIncompleteLength: 1, maximumLength: 16384) { [weak self] data, _, done, err in
            guard let self else { c.cancel(); return }
            let all = got + (data ?? Data())
            if let head = String(data: all, encoding: .utf8), head.contains("\r\n\r\n") {
                let path = head.split(separator: " ").dropFirst().first.map(String.init) ?? "/"
                self.answer(c, path)
            } else if done || err != nil || all.count > 65536 {
                c.cancel()
            } else {
                self.read(c, all)
            }
        }
    }

    private func answer(_ c: NWConnection, _ path: String) {
        let route = path.split(separator: "?").first.map(String.init) ?? "/"
        let (status, type, body): (String, String, Data)
        switch route {
        case "/state":
            let items = URLComponents(string: path)?.queryItems ?? []
            let at = items.first { $0.name == "at" }?.value.flatMap(Double.init)
            // lead: milliseconds ahead of the playhead, for OBS's delay
            let lead = (items.first { $0.name == "lead" }?.value.flatMap(Double.init) ?? 0) / 1000
            let d = (try? JSONSerialization.data(withJSONObject: state(at, min(max(lead, 0), 2)), options: [.sortedKeys])) ?? Data("{}".utf8)
            (status, type, body) = ("200 OK", "application/json", d)
        case "/", "/index.html":
            // read on every request, so a changed chyron.html in the app shows at the next reload
            if let u = Bundle.main.url(forResource: "chyron", withExtension: "html"), let d = try? Data(contentsOf: u) {
                (status, type, body) = ("200 OK", "text/html; charset=utf-8", d)
            } else {
                (status, type, body) = ("404 Not Found", "text/plain", Data("chyron.html isn't in the app: build it with build.sh".utf8))
            }
        default:
            (status, type, body) = ("404 Not Found", "text/plain", Data("not here".utf8))
        }
        let head = "HTTP/1.1 \(status)\r\nContent-Type: \(type)\r\nContent-Length: \(body.count)\r\n"
            + "Cache-Control: no-store\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n"
        c.send(content: Data(head.utf8) + body, completion: .contentProcessed { _ in c.cancel() })
    }
}

extension UInt16 { var nonZero: UInt16? { self == 0 ? nil : self } }
