// The song map and the voices the player makes of it
import Foundation

struct Bar: Codable { let num, page, sys: Int; let xa, xb: Double; let letter: String?; let beat_x, beat_t: [Double]; let end_t: Double }
struct Sys: Codable { let page, sys: Int; let top, bottom: Double }
struct NoteHead: Codable { let page: Int; let x, y: Double }
struct Note: Codable { let id, part: String; let bar: Int; let beat: Double; let midi: Int; let word: String; let start, end: Double; let heads: [NoteHead] }
/// a correction, kept in the song folder. Its times start as the note's and can be nudged.
struct NoteFix: Codable { let id, part: String; var start, end: Double; var mute: Bool; var semitones: Int }
/// a voice stem as the map names it, top to bottom as in the score. `stems[key]` is its file and notes' `part` is its key.
/// Parts of one section split in two (Tenor 2a and 2b) share a `section`; without one, the name decides (see Voice.section(of:)).
/// `trim` (dB) is added to the voice's own, for a stem louder or softer than the others were made.
struct VoiceSpec: Codable { let key: String; let name: String?; let section: String?; let solo: Bool?; let trim: Float? }
struct SongMap: Codable {
    let notes: [Note]?
    let score_dark: String?
    let score: String; let stems: [String: String]; let offset: Double; let page_height: Double; let pages: Int
    let tempo: Double; let music_end: Double; let systems: [Sys]; let bars: [Bar]
    /// the voice stems in score order. A map without this has stems S, A, T, B and an optional A2 (a second alto, or a soloist).
    let voices: [VoiceSpec]?
    /// for a map without `voices`: what to call S, A, T, B and A2. "A2": "Solo" makes A2 a soloist.
    let part_names: [String: String]?
}

extension SongMap {
    /// a bar as typed: its number, and for a bar in a repeat, b or ' for its second time through (c or '' for a third).
    /// A repeated bar is in the map once for each time it's played, in order.
    func bar(typed s: String) -> Bar? {
        var t = s.trimmingCharacters(in: .whitespaces).lowercased(), pass = 0
        while let c = t.last, c == "'" || c == "\u{2019}" { pass += 1; t.removeLast() }
        if pass == 0, t.count > 1, let c = t.last, let v = c.asciiValue, (97...101).contains(v) { pass = Int(v) - 97; t.removeLast() }
        guard let n = Int(t) else { return nil }
        let times = bars.filter { $0.num == n }
        return pass < times.count ? times[pass] : nil
    }
    /// which time through a repeat bar i is: 0 the first
    func pass(_ i: Int) -> Int { bars[..<i].filter { $0.num == bars[i].num }.count }
}

/// a voice as the player mixes it: its place in the engine is its place in Player.voices
struct Voice {
    let key, name, section: String
    let solo: Bool
    var pan: Float = 0, trim: Float = 0
    var hotkey = ""
    /// the map's correction for this stem, added to the trim the mix gives it
    var stemTrim: Float = 0

    /// Tenor 2a and Tenor 2b are halves of Tenor 2, Bass a and Bass b of Bass, Alto 1 and Alto 2 of Alto, Soprano 1 and 2 of
    /// Soprano. Tenor 1 and Tenor 2, or Baritone and Bass, are sections of their own.
    static func section(of name: String) -> String {
        let n = name.trimmingCharacters(in: .whitespaces)
        if let last = n.last, "abcd".contains(last), n.count > 2 {
            let before = n[n.index(n.endIndex, offsetBy: -2)]
            if before == " " || before.isNumber { return String(n.dropLast()).trimmingCharacters(in: .whitespaces) }
        }
        for s in ["Soprano", "Alto"] where n.hasPrefix(s + " ") && ["1", "2", "3"].contains(n.dropFirst(s.count + 1)) { return s }
        return n
    }

    /// The pans and trims. Sections other than soloists spread evenly from -45 (the highest) to +45, the outer two at 0 dB and
    /// any between at -3 dB, except that four sections are at -0.5, -2.5, -2.5, -0.5; a section's halves sit 5 either side of
    /// its place. Soloists are centred at 0 dB.
    static func mix(_ vs: inout [Voice]) {
        var sections: [String] = []
        for v in vs where !v.solo && !sections.contains(v.section) { sections.append(v.section) }
        let n = sections.count
        for (k, sec) in sections.enumerated() {
            let pan: Float = n == 1 ? 0 : -45 + 90 * Float(k) / Float(n - 1)
            let outer = k == 0 || k == n - 1
            let trim: Float = n == 4 ? (outer ? -0.5 : -2.5) : (outer ? 0 : -3)
            let members = vs.indices.filter { !vs[$0].solo && vs[$0].section == sec }
            for (j, i) in members.enumerated() {
                vs[i].pan = pan + (members.count == 1 ? 0 : -5 + 10 * Float(j) / Float(members.count - 1))
                vs[i].trim = trim + vs[i].stemTrim
            }
        }
        // keys: s a t b for each section's first part, the lowest always b (more than four: s a t b e f g h), and z x y w for
        // soloists and then the other halves
        let named = n <= 1 ? ["s"] : n <= 4 ? Array(["s", "a", "t"].prefix(n - 1)) + ["b"] : ["s", "a", "t", "b", "e", "f", "g", "h"]
        var sectionKeys = named[...], extra = ["z", "x", "y", "w", "j", "k"][...]
        for i in vs.indices where vs[i].solo { vs[i].hotkey = extra.popFirst() ?? ""; vs[i].trim = vs[i].stemTrim }
        var seen = Set<String>()
        for i in vs.indices where !vs[i].solo {
            vs[i].hotkey = (seen.insert(vs[i].section).inserted ? sectionKeys.popFirst() : extra.popFirst()) ?? ""
        }
    }

    /// the voices a map names, in score order
    static func from(_ m: SongMap) -> [Voice] {
        var vs: [Voice]
        if let list = m.voices {
            vs = list.map { s in
                let name = s.name ?? s.key
                return Voice(key: s.key, name: name, section: s.section ?? section(of: name), solo: s.solo ?? name.lowercased().hasPrefix("solo"), stemTrim: s.trim ?? 0)
            }
        } else {
            // the older kind: S, A, T, B, with A2 a second alto part or a soloist
            let names = m.part_names ?? [:]
            let solo = names["A2"] == "Solo"
            let twoAltos = m.stems["A2"] != nil && !solo
            let order = (solo ? ["A2"] : []) + ["S", "A"] + (twoAltos ? ["A2"] : []) + ["T", "B"]
            let plain = ["S": "Soprano", "A": twoAltos ? "Alto 1" : "Alto", "A2": solo ? "Solo" : "Alto 2", "T": "Tenor", "B": "Bass"]
            vs = order.filter { m.stems[$0] != nil }.map { k in
                let name = names[k] ?? plain[k]!
                // the stem letter, not the name, says which parts are halves of one: a TTBB song's Tenor 1 and Tenor 2 are not
                let sec = k == "A2" && twoAltos ? "A" : k
                return Voice(key: k, name: name, section: sec, solo: k == "A2" && solo)
            }
        }
        mix(&vs)
        return vs
    }
}

/// what the Hear list plays: all the voices, one of them (by its place in Player.voices), or the ones checked under Other
enum Hear: Hashable { case balanced, only(Int), other }
