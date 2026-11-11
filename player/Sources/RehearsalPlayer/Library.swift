// Every song on this Mac, its tags, and the window for finding one by them
import AppKit
import SwiftUI

let mapFile = "player map.json", tagsFile = "player tags.json"

struct Song: Identifiable, Hashable {
    let path: String
    var id: String { path }
    var name: String { (path as NSString).lastPathComponent }
    /// from the folders it's in: can't be removed, and follow the song if it moves
    let folderTags: [String]
    /// the user's, kept in the song folder
    var tags: [String]
    var all: [String] { folderTags + tags.filter { !folderTags.contains($0) } }
}

final class SongLibrary: ObservableObject {
    static let shared = SongLibrary()
    @Published private(set) var songs: [Song] = []
    /// the tags chosen in the cloud: a song must have all of them
    @Published var chosen = Set(UserDefaults.standard.stringArray(forKey: "findTags") ?? []) {
        didSet { UserDefaults.standard.set(Array(chosen), forKey: "findTags") }
    }
    private let query = NSMetadataQuery()
    private var found: [String] = []
    private var extra: [String] = []

    /// a test's copy, a build's, or one in the Trash: not a song to offer
    static func isScratch(_ path: String) -> Bool {
        let home = NSHomeDirectory()
        if ["/private/", "/tmp/", "/var/"].contains(where: path.hasPrefix) { return true }
        if path.contains("/.Trash/") || path.contains("/.build/") { return true }
        return path.hasPrefix(home + "/Library/") && !path.hasPrefix(home + "/Library/CloudStorage/")
    }

    /// The folders a song is in, from the top: Choir/2026 Fall/Song gives Choir and 2026 Fall. A folder that repeats the one
    /// above it loses that (Band/Band 2026 Fall gives Band and 2026 Fall), so the same season is one tag across groups.
    static func folderTags(_ path: String) -> [String] {
        let home = NSHomeDirectory() + "/"
        guard path.hasPrefix(home) else { return [] }
        var parts = Array(path.dropFirst(home.count).split(separator: "/").map(String.init).dropLast())
        if parts.starts(with: ["Library", "CloudStorage"]) { parts.removeFirst(2) }
        if let top = parts.first, ["Dropbox", "Documents", "Desktop", "Downloads", "Music", "Cowork"].contains(where: top.hasPrefix) { parts.removeFirst() }
        var out: [String] = []
        for p in parts {
            var t = p
            for above in out where t.hasPrefix(above + " ") { t = String(t.dropFirst(above.count + 1)) }
            if !out.contains(t) { out.append(t) }
        }
        return out
    }

    static func readTags(_ path: String) -> [String] {
        let url = URL(fileURLWithPath: path).appendingPathComponent(tagsFile)
        return (try? JSONDecoder().decode([String].self, from: Data(contentsOf: url))) ?? []
    }

    func start() {
        query.predicate = NSPredicate(format: "%K == %@", NSMetadataItemFSNameKey, mapFile)
        query.searchScopes = [NSMetadataQueryLocalComputerScope]
        for n in [Notification.Name.NSMetadataQueryDidFinishGathering, .NSMetadataQueryDidUpdate] {
            NotificationCenter.default.addObserver(forName: n, object: query, queue: .main) { [weak self] _ in self?.gather() }
        }
        query.start()
        refresh()
    }

    private func gather() {
        query.disableUpdates()
        found = (query.results as? [NSMetadataItem] ?? []).compactMap { $0.value(forAttribute: NSMetadataItemPathKey) as? String }
            .map { ($0 as NSString).deletingLastPathComponent }
        query.enableUpdates()
        refresh()
    }

    /// a song opened by hand counts, even where Spotlight doesn't look
    func add(_ path: String) { if !extra.contains(path) { extra.append(path); refresh() } }

    /// reads every song's tags again: another computer may have changed them
    func refresh() {
        let recent = UserDefaults.standard.stringArray(forKey: "recentFolders") ?? []
        let paths = Set(found + recent + extra).filter {
            !Self.isScratch($0) && FileManager.default.fileExists(atPath: ($0 as NSString).appendingPathComponent(mapFile))
        }
        songs = paths.map { Song(path: $0, folderTags: Self.folderTags($0), tags: Self.readTags($0)) }
            .sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
        let known = Set(songs.flatMap(\.all))
        if !songs.isEmpty && !chosen.isSubset(of: known) { chosen.formIntersection(known) }
    }

    func song(_ path: String?) -> Song? { songs.first { $0.path == path } }
    var folderTagList: [String] { Array(Set(songs.flatMap(\.folderTags))).sorted { $0.localizedStandardCompare($1) == .orderedAscending } }
    var userTagList: [String] {
        let folders = Set(songs.flatMap(\.folderTags))
        return Array(Set(songs.flatMap(\.tags))).filter { !folders.contains($0) }.sorted { $0.localizedStandardCompare($1) == .orderedAscending }
    }
    var matches: [Song] { songs.filter { chosen.isSubset(of: $0.all) } }
    /// how many songs would be listed with this tag chosen as well
    func count(with tag: String) -> Int { songs.filter { chosen.union([tag]).isSubset(of: $0.all) }.count }

    private func write(_ tags: [String], _ path: String) {
        let url = URL(fileURLWithPath: path).appendingPathComponent(tagsFile)
        if tags.isEmpty { try? FileManager.default.removeItem(at: url) }
        else if let d = try? JSONEncoder().encode(tags) { try? d.write(to: url, options: .atomic) }
        refresh()
    }

    func addTag(_ raw: String, to path: String) {
        let text = raw.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty, let s = song(path) else { return }
        // the spelling already in use, so "christmas" and "Christmas" are one tag
        let tag = (folderTagList + userTagList).first { $0.caseInsensitiveCompare(text) == .orderedSame } ?? text
        if !s.all.contains(tag) { write(s.tags + [tag], path) }
    }
    func removeTag(_ tag: String, from path: String) {
        if let s = song(path) { write(s.tags.filter { $0 != tag }, path) }
    }
}

/// lays its views out in rows, wrapping at the width it's given
struct Flow: Layout {
    var spacing: CGFloat = 4
    private func place(_ views: Subviews, _ width: CGFloat) -> (points: [CGPoint], size: CGSize) {
        var points: [CGPoint] = [], x: CGFloat = 0, y: CGFloat = 0, row: CGFloat = 0, widest: CGFloat = 0
        for v in views {
            let s = v.sizeThatFits(.unspecified)
            if x > 0 && x + s.width > width { x = 0; y += row + spacing; row = 0 }
            points.append(CGPoint(x: x, y: y))
            x += s.width + spacing; row = max(row, s.height); widest = max(widest, x - spacing)
        }
        return (points, CGSize(width: widest, height: y + row))
    }
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        place(subviews, proposal.width ?? .infinity).size
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let p = place(subviews, bounds.width).points
        for (v, at) in zip(subviews, p) { v.place(at: CGPoint(x: bounds.minX + at.x, y: bounds.minY + at.y), proposal: .unspecified) }
    }
}

struct Chip: View {
    let text: String
    var on = false
    var action: (() -> Void)? = nil
    var body: some View {
        let label = Text(text).font(.caption).lineLimit(1).padding(.horizontal, 7).padding(.vertical, 2)
            .foregroundStyle(on ? Color.white : Color.primary)
            .background(on ? Color.accentColor : Color.secondary.opacity(0.18), in: Capsule())
        if let action { Button(action: action) { label }.buttonStyle(.plain) } else { label }
    }
}

/// one song's tags: its folders', fixed, and the user's, with a box to add more
struct TagEditor: View {
    @ObservedObject var lib = SongLibrary.shared
    let path: String
    /// give the keyboard back to the score after adding one
    var leaveAfter = false
    @State var text = ""
    @FocusState var typing: Bool
    func add(_ t: String) {
        lib.addTag(t, to: path); text = ""
        if leaveAfter { typing = false; NSApp.keyWindow?.makeFirstResponder(nil) }
    }
    var suggestions: [String] {
        let have = Set(lib.song(path)?.all ?? [])
        return text.isEmpty ? [] : (lib.userTagList + lib.folderTagList).filter { !have.contains($0) && $0.localizedCaseInsensitiveContains(text) }.prefix(8).map { $0 }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            if let s = lib.song(path), !s.all.isEmpty {
                Flow {
                    ForEach(s.folderTags, id: \.self) { Chip(text: $0).opacity(0.7).help("From the song's folders") }
                    ForEach(s.tags.filter { !s.folderTags.contains($0) }, id: \.self) { t in
                        Chip(text: t + " ×") { lib.removeTag(t, from: path) }.help("Remove this tag")
                    }
                }
            }
            TextField("Add a tag", text: $text).focused($typing).controlSize(.small).onSubmit { add(text) }
            if !suggestions.isEmpty { Flow { ForEach(suggestions, id: \.self) { t in Chip(text: t) { add(t) } } } }
        }
    }
}

struct FindSongs: View {
    @ObservedObject var lib = SongLibrary.shared
    @ObservedObject var p: Player
    var opened: () -> Void
    @State var selected: String?
    func open(_ s: Song) { p.open(folder: URL(fileURLWithPath: s.path)); opened() }
    func cloud(_ title: String, _ tags: [String]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Flow {
                ForEach(tags, id: \.self) { t in
                    let on = lib.chosen.contains(t), n = lib.count(with: t)
                    Chip(text: "\(t)  \(n)", on: on) { if on { lib.chosen.remove(t) } else { lib.chosen.insert(t) } }
                        .disabled(n == 0).opacity(n == 0 ? 0.35 : 1)
                }
            }
        }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if !lib.folderTagList.isEmpty { cloud("Folders", lib.folderTagList) }
            if !lib.userTagList.isEmpty { cloud("Your tags", lib.userTagList) }
            HStack {
                Text("\(lib.matches.count) of \(lib.songs.count) songs").font(.caption).foregroundStyle(.secondary)
                Spacer()
                if !lib.chosen.isEmpty { Button("Clear") { lib.chosen = [] }.controlSize(.small) }
            }
            List(lib.matches, selection: $selected) { s in
                HStack {
                    Text(s.name).fontWeight(s.path == p.folder?.path ? .semibold : .regular)
                    Spacer()
                    Text(s.all.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
                .contentShape(Rectangle())
                .tag(s.path)
                .gesture(TapGesture(count: 2).onEnded { open(s) })
                .simultaneousGesture(TapGesture().onEnded { selected = s.path })
            }
            .listStyle(.bordered(alternatesRowBackgrounds: true))
            .frame(minHeight: 160)
            if let path = selected, let s = lib.song(path) {
                VStack(alignment: .leading, spacing: 5) {
                    HStack {
                        Text("Tags for \(s.name)").font(.caption).foregroundStyle(.secondary)
                        Spacer()
                        Button("Open") { open(s) }.controlSize(.small).keyboardShortcut(.defaultAction)
                    }
                    TagEditor(path: path).id(path)
                }
            } else {
                Text("Double-click a song to open it, or click one to tag it.").font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .frame(minWidth: 460, minHeight: 420)
    }
}
