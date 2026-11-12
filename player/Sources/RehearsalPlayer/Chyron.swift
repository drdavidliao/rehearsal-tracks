// A chyron for a video call: the player serves a page on this Mac that OBS shows as a Browser Source.
//   http://localhost:8766/        the chyron, on a see-through background
//   http://localhost:8766/state   what it shows, as JSON; /state?at=SECONDS as if the playhead were there
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
        let noInst = !instruments && map?.stems["I"] != nil ? " (no accompaniment)" : ""
        switch mode {
        case .balanced: return "Tutti" + noInst
        case .only(let i): return voices[i].name + noInst
        case .other:
            let names = listed.filter { otherVoices & Int32(1 << $0) != 0 }.map { voices[$0].name }
            return names.isEmpty ? (instruments ? "Accompaniment only" : "Silence") : names.joined(separator: " + ") + noInst
        }
    }

    /// what the chyron shows, and the plain facts under it
    func chyronState(at: Double? = nil) -> [String: Any] {
        guard let m = map, error == nil else { return ["song": NSNull()] }
        let t = at ?? engine_position()
        let i = bar(at: t) ?? 0
        let b = m.bars[i]
        let beat = (b.beat_t.lastIndex(where: { $0 <= t + eps }) ?? 0) + 1
        let secs = sections
        let current = secs.last { $0.bars.startIndex <= i }?.name
        var loop: Any = NSNull()
        if loopOn, let (a, z) = loopBars,
           let ai = m.bars.firstIndex(where: { $0.beat_t[0] == a.beat_t[0] }), let zi = m.bars.firstIndex(where: { $0.end_t == z.end_t }) {
            loop = "Loop from \(barLabel(ai)) to \(barLabel(zi))"
        }
        let modeName: String
        switch mode { case .balanced: modeName = "balanced"; case .only: modeName = "only"; case .other: modeName = "other" }
        return [
            "song": songName,
            "playing": engine_is_playing() != 0,
            "location": spoken(i),
            "part": partLabel,
            "loop": loop,
            "sections": secs.filter { markedSections.contains($0.name) }.map { ["name": $0.name, "current": $0.name == current] },
            // the facts, for anything else that reads this
            "bar": b.num, "pass": pass(i), "beat": beat, "section": current ?? NSNull(), "time": t,
            "mode": modeName, "instruments": instruments, "tempo": bpm, "song_tempo": m.tempo,
            "marked": secs.map(\.name).filter { markedSections.contains($0) },
            "folder": folder?.path ?? NSNull(),
        ]
    }
}

/// a little HTTP server on the loopback address, answered on the main thread, where the player's state lives
final class ChyronServer {
    static var port: UInt16 { UInt16(UserDefaults.standard.integer(forKey: "chyronPort")).nonZero ?? 8766 }
    static var address: String { "http://localhost:\(port)/" }
    let listener: NWListener
    let state: (Double?) -> [String: Any]

    init?(state: @escaping (Double?) -> [String: Any], failed: @escaping (String) -> Void) {
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
            let at = URLComponents(string: path)?.queryItems?.first { $0.name == "at" }?.value.flatMap(Double.init)
            let d = (try? JSONSerialization.data(withJSONObject: state(at), options: [.sortedKeys])) ?? Data("{}".utf8)
            (status, type, body) = ("200 OK", "application/json", d)
        case "/", "/index.html":
            (status, type, body) = ("200 OK", "text/html; charset=utf-8", Data(chyronPage.utf8))
        default:
            (status, type, body) = ("404 Not Found", "text/plain", Data("not here".utf8))
        }
        let head = "HTTP/1.1 \(status)\r\nContent-Type: \(type)\r\nContent-Length: \(body.count)\r\n"
            + "Cache-Control: no-store\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n"
        c.send(content: Data(head.utf8) + body, completion: .contentProcessed { _ in c.cancel() })
    }
}

extension UInt16 { var nonZero: UInt16? { self == 0 ? nil : self } }

/// The page. Query options: scale=1.5 (size), corner=bl|br|tl|tr (where it sits), panel=0 (no dark panel behind the text).
let chyronPage = #"""
<!doctype html>
<html><head><meta charset="utf-8"><title>Rehearsal chyron</title>
<style>
  :root { --s: 1; --accent: #f2b544; --loop: #5fd38a; }
  html, body { margin: 0; background: transparent; overflow: hidden; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif; color: #fff; }
  #c { position: fixed; left: calc(32px * var(--s)); bottom: calc(32px * var(--s)); max-width: calc(100vw - 64px * var(--s));
       background: rgba(14, 16, 20, 0.84); border-radius: calc(12px * var(--s));
       padding: calc(14px * var(--s)) calc(20px * var(--s)) calc(16px * var(--s));
       font-size: calc(36px * var(--s)); line-height: 1.15; transition: opacity .25s; }
  #c.hidden { opacity: 0; }
  body.tr #c, body.br #c { left: auto; right: calc(32px * var(--s)); }
  body.tl #c, body.tr #c { bottom: auto; top: calc(32px * var(--s)); }
  body.nopanel #c { background: none; text-shadow: 0 2px 6px rgba(0,0,0,.9), 0 0 2px rgba(0,0,0,.9); }
  #song { font-size: .55em; font-weight: 600; letter-spacing: .02em; opacity: .78; margin-bottom: .2em; white-space: nowrap;
          overflow: hidden; text-overflow: ellipsis; }
  #main { display: flex; align-items: center; flex-wrap: wrap; gap: .35em .6em; }
  #where { display: flex; align-items: center; gap: .35em; font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; }
  #icon { width: .72em; height: .72em; flex: none; }
  #part { font-size: .72em; font-weight: 700; color: #16130b; background: var(--accent); border-radius: .3em; padding: .08em .45em; white-space: nowrap; }
  #loop { font-size: .62em; font-weight: 600; color: var(--loop); border: 2px solid var(--loop); border-radius: .3em; padding: .05em .4em; white-space: nowrap; }
  #loop:empty { display: none; }
  #boxes { display: flex; flex-wrap: wrap; gap: .3em; margin-top: .45em; font-size: .55em; }
  #boxes:empty { display: none; }
  .box { min-width: 1.6em; text-align: center; padding: .12em .45em; border-radius: .25em; font-weight: 700;
         border: 2px solid rgba(255,255,255,.45); color: rgba(255,255,255,.8); }
  .box.on { background: #fff; border-color: #fff; color: #111; }
</style></head>
<body>
<div id="c" class="hidden">
  <div id="song"></div>
  <div id="main">
    <span id="where"><svg id="icon" viewBox="0 0 10 10"></svg><span id="loc"></span></span>
    <span id="part"></span>
    <span id="loop"></span>
  </div>
  <div id="boxes"></div>
</div>
<script>
const q = new URLSearchParams(location.search);
document.documentElement.style.setProperty('--s', parseFloat(q.get('scale')) || 1);
document.body.classList.add(q.get('corner') || 'bl');
if (q.get('panel') === '0') document.body.classList.add('nopanel');
const $ = id => document.getElementById(id);
const PLAY = '<path d="M1.5 0.5 L9.5 5 L1.5 9.5 Z" fill="currentColor"/>';
const PAUSE = '<rect x="1.2" y="0.8" width="2.8" height="8.4" fill="currentColor"/><rect x="6" y="0.8" width="2.8" height="8.4" fill="currentColor"/>';
let last = '';
function render(s) {
  if (!s.song) { $('c').classList.add('hidden'); return; }
  $('song').textContent = s.song;
  $('icon').innerHTML = s.playing ? PLAY : PAUSE;
  $('loc').textContent = s.location;
  $('part').textContent = s.part;
  $('loop').textContent = s.loop || '';
  const boxes = $('boxes'); boxes.textContent = '';
  for (const sec of s.sections) {
    const d = document.createElement('span');
    d.className = 'box' + (sec.current ? ' on' : '');
    d.textContent = sec.name;
    boxes.appendChild(d);
  }
  $('c').classList.remove('hidden');
}
async function poll() {
  try {
    const r = await fetch('/state', { cache: 'no-store' });
    const t = await r.text();
    if (t !== last) { last = t; render(JSON.parse(t)); }
  } catch (e) { last = ''; $('c').classList.add('hidden'); }
  setTimeout(poll, 200);
}
poll();
</script>
</body></html>
"""#
