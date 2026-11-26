// Set lists: songs in running order, with a button on a song's last page to the next and on its first page back to the one before
import AppKit
import CEngine
import SwiftUI

/// one place in a set list: a song folder, or an intermission (no path). Its own id, so a song can come twice (a reprise)
/// and still be moved on its own.
struct SetEntry: Codable, Identifiable, Hashable {
    var id = UUID(); var path: String; var intermission: Bool? = nil
    var isBreak: Bool { intermission == true }
    var title: String { isBreak ? "Intermission" : folderName(path) }
    static var interval: SetEntry { SetEntry(path: "", intermission: true) }
}
struct SetList: Codable, Identifiable, Hashable { var id = UUID(); var name: String; var entries: [SetEntry] = [] }

final class SetLists: ObservableObject {
    static let shared = SetLists()
    @Published var lists: [SetList] = [] { didSet { save() } }
    /// the set list being run, if any: the one the Next and Previous buttons follow
    @Published var currentID: UUID? {
        didSet { UserDefaults.standard.set(currentID?.uuidString, forKey: "currentSetList"); placeOpenSong() }
    }
    /// where in the current list the open song is: a song listed twice is at the place it was reached from
    @Published var at: Int?
    /// the song open in the player, kept here so a list chosen or changed can find it
    private var openPath: String?

    init() {
        if let d = UserDefaults.standard.data(forKey: "setLists"), let l = try? JSONDecoder().decode([SetList].self, from: d) { lists = l }
        currentID = UserDefaults.standard.string(forKey: "currentSetList").flatMap(UUID.init(uuidString:))
        if let c = currentID, !lists.contains(where: { $0.id == c }) { currentID = nil }
    }
    private func save() {
        if let d = try? JSONEncoder().encode(lists) { UserDefaults.standard.set(d, forKey: "setLists") }
        if let c = currentID, !lists.contains(where: { $0.id == c }) { currentID = nil }
        // a list edited under the open song: keep its place if the song's still there, or find it again
        if let a = at, let e = current?.entries, a < e.count, e[a].path == openPath { return }
        placeOpenSong()
    }

    var current: SetList? { lists.first { $0.id == currentID } }

    static func playable(_ path: String) -> Bool {
        FileManager.default.fileExists(atPath: (path as NSString).appendingPathComponent(mapFile))
    }

    /// the player has opened a song: at `index` if it came from the list, otherwise its first place in the list, if any
    func opened(_ path: String, index: Int? = nil) {
        openPath = path
        if let i = index, let e = current?.entries, i < e.count, e[i].path == path { at = i } else { placeOpenSong() }
    }
    private func placeOpenSong() {
        let i = current?.entries.firstIndex { $0.path == openPath }
        if at != i { at = i }
    }

    /// the next or previous place in the current list with a song that can be opened, from the open song's place, and
    /// whether an intermission comes between
    func neighbour(_ step: Int) -> (index: Int, entry: SetEntry, pastBreak: Bool)? {
        guard let e = current?.entries, var i = at else { return nil }
        var pastBreak = false
        i += step
        while e.indices.contains(i) {
            if e[i].isBreak { pastBreak = true } else if Self.playable(e[i].path) { return (i, e[i], pastBreak) }
            i += step
        }
        return nil
    }
    /// whether an intermission lies between two places in the current list
    func breakBetween(_ a: Int, _ b: Int) -> Bool {
        guard let e = current?.entries, a != b else { return false }
        return e[(min(a, b) + 1)..<max(a, b)].contains { $0.isBreak }
    }

    func add(_ entry: SetEntry, to id: UUID) {
        guard let k = lists.firstIndex(where: { $0.id == id }) else { return }
        lists[k].entries.append(entry)
    }
    func newList(named name: String? = nil) -> UUID {
        var n = 1
        while lists.contains(where: { $0.name == (n == 1 ? "New Set List" : "New Set List \(n)") }) { n += 1 }
        let l = SetList(name: name ?? (n == 1 ? "New Set List" : "New Set List \(n)"))
        lists.append(l)
        return l.id
    }
}

extension Player {
    /// opens the song at a place in the current set list. Playing carries on into it, for an attacca or a run straight
    /// through, but not across an intermission.
    func open(setIndex i: Int) {
        let sets = SetLists.shared
        guard let e = sets.current?.entries, e.indices.contains(i), !e[i].isBreak else { return }
        let wasPlaying = engine_is_playing() != 0 && !(sets.at.map { sets.breakBetween($0, i) } ?? true)
        open(folder: URL(fileURLWithPath: e[i].path), setIndex: i)
        if wasPlaying, error == nil, map != nil { engine_set_playing(1) }
    }
    func nextInSet() { if let n = SetLists.shared.neighbour(1) { open(setIndex: n.index) } else { NSSound.beep() } }
    func previousInSet() { if let n = SetLists.shared.neighbour(-1) { open(setIndex: n.index) } else { NSSound.beep() } }
}

func folderName(_ path: String) -> String { (path as NSString).lastPathComponent }

/// a song's number in its list, counting songs only: an intermission has none
func songNumber(_ entries: [SetEntry], _ i: Int) -> Int { entries[...i].filter { !$0.isBreak }.count }

/// an intermission as a list shows it: a rule with the word in it
struct IntermissionRow: View {
    var body: some View {
        HStack(spacing: 6) {
            Rectangle().fill(Color.secondary.opacity(0.4)).frame(height: 1)
            Text("Intermission").font(.caption.italic()).foregroundStyle(.secondary).fixedSize()
            Rectangle().fill(Color.secondary.opacity(0.4)).frame(height: 1)
        }
    }
}

/// the buttons over the score: the previous song on the first page, the next on the last
struct SetListButtons: View {
    @ObservedObject var p: Player
    @ObservedObject var sets = SetLists.shared
    func button(_ title: String, _ systemImage: String, trailing: Bool, _ act: @escaping () -> Void) -> some View {
        Button(action: act) {
            HStack(spacing: 6) {
                if !trailing { Image(systemName: systemImage) }
                Text(title).lineLimit(1)
                if trailing { Image(systemName: systemImage) }
            }
            .font(.system(size: 13, weight: .semibold))
            .padding(.horizontal, 12).padding(.vertical, 7)
            .background(.regularMaterial, in: Capsule())
            .overlay(Capsule().stroke(Color.accentColor.opacity(0.6), lineWidth: 1))
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
    }
    var body: some View {
        HStack(alignment: .bottom) {
            if p.onFirstPage, let prev = sets.neighbour(-1) {
                button((prev.pastBreak ? "Previous, before intermission: " : "Previous: ") + prev.entry.title, "chevron.left", trailing: false) { p.open(setIndex: prev.index) }
                    .help("Open the song before this one in \(sets.current?.name ?? "the set list") (⌘[)")
            }
            Spacer(minLength: 12)
            if p.onLastPage, let next = sets.neighbour(1) {
                button((next.pastBreak ? "Next, after intermission: " : "Next: ") + next.entry.title, "chevron.right", trailing: true) { p.open(setIndex: next.index) }
                    .help("Open the next song in \(sets.current?.name ?? "the set list") (⌘])")
            }
        }
        .padding(10)
    }
}

/// in the sidebar: which set list to run, and its songs, the open one in bold; click one to open it
struct SetListPanel: View {
    @ObservedObject var p: Player
    @ObservedObject var sets = SetLists.shared
    var edit: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Picker("", selection: $sets.currentID) {
                Text("None").tag(UUID?.none)
                ForEach(sets.lists) { Text($0.name).tag(UUID?.some($0.id)) }
            }.labelsHidden().controlSize(.small)
            if let l = sets.current {
                if l.entries.isEmpty { Text("No songs yet").font(.caption).foregroundStyle(.secondary) }
                ForEach(Array(l.entries.enumerated()), id: \.element.id) { i, e in
                    let ok = SetLists.playable(e.path)
                    if e.isBreak { IntermissionRow().padding(.vertical, 2) } else {
                    Button { p.open(setIndex: i) } label: {
                        HStack(alignment: .firstTextBaseline, spacing: 4) {
                            Text("\(songNumber(l.entries, i)).").monospacedDigit().foregroundStyle(.secondary)
                            Text(e.title).lineLimit(1).truncationMode(.tail)
                        }
                        .font(.caption).fontWeight(sets.at == i ? .bold : .regular)
                        .frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain).disabled(!ok).opacity(ok ? 1 : 0.4)
                    .help(ok ? e.path : "Not found: \(e.path)")
                    }
                }
            }
            Button("Edit Set Lists…", action: edit).controlSize(.small)
        }
    }
}

/// the window for making set lists: the lists, the songs of the one chosen in order, and every song to add from
struct SetListEditor: View {
    @ObservedObject var sets = SetLists.shared
    @ObservedObject var lib = SongLibrary.shared
    @ObservedObject var p: Player
    @State var chosen: UUID?
    @State var entry: SetEntry.ID?
    @State var song: String?
    @State var search = ""
    /// the tags chosen above the songs: a song must have all of them. Kept apart from the Find window's.
    @State var tags = Set(UserDefaults.standard.stringArray(forKey: "setListTags") ?? []) {
        didSet { UserDefaults.standard.set(Array(tags), forKey: "setListTags") }
    }
    @AppStorage("setListTagsOpen") var tagsOpen = true
    var index: Int? { sets.lists.firstIndex { $0.id == chosen } }
    /// the songs the search box lets through, before the tags
    var typed: [Song] {
        let t = search.trimmingCharacters(in: .whitespaces)
        return t.isEmpty ? lib.songs : lib.songs.filter { s in s.name.localizedCaseInsensitiveContains(t) || s.all.contains { $0.localizedCaseInsensitiveContains(t) } }
    }
    var found: [Song] { typed.filter { tags.isSubset(of: $0.all) } }
    func tagCloud(_ title: String, _ list: [String]) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            caption(title)
            Flow {
                ForEach(list, id: \.self) { t in
                    let on = tags.contains(t), n = typed.filter { tags.union([t]).isSubset(of: $0.all) }.count
                    Chip(text: "\(t)  \(n)", on: on) { if on { tags.remove(t) } else { tags.insert(t) } }
                        .disabled(n == 0 && !on).opacity(n == 0 && !on ? 0.35 : 1)
                }
            }
        }
    }
    func add(_ path: String) {
        guard let c = chosen else { return }
        sets.add(SetEntry(path: path), to: c)
    }
    /// after the song chosen in the list, or at the end
    func addIntermission() {
        guard let k = index else { return }
        let at = entry.flatMap { e in sets.lists[k].entries.firstIndex { $0.id == e } }.map { $0 + 1 } ?? sets.lists[k].entries.count
        let b = SetEntry.interval
        sets.lists[k].entries.insert(b, at: at)
        entry = b.id
    }
    func move(_ d: Int) {
        guard let k = index, let e = entry, let i = sets.lists[k].entries.firstIndex(where: { $0.id == e }), sets.lists[k].entries.indices.contains(i + d) else { return }
        sets.lists[k].entries.swapAt(i, i + d)
    }
    func caption(_ t: String) -> some View { Text(t).font(.caption).foregroundStyle(.secondary) }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                caption("Set lists")
                List(selection: $chosen) {
                    ForEach(sets.lists) { l in Text(l.name).tag(l.id) }
                }
                .listStyle(.bordered(alternatesRowBackgrounds: true))
                HStack(spacing: 4) {
                    Button { chosen = sets.newList() } label: { Image(systemName: "plus") }.help("A new set list")
                    Button {
                        guard let k = index else { return }
                        let a = NSAlert()
                        a.messageText = "Delete the set list “\(sets.lists[k].name)”?"
                        a.informativeText = "The songs themselves aren't touched."
                        a.addButton(withTitle: "Delete"); a.addButton(withTitle: "Cancel")
                        if a.runModal() == .alertFirstButtonReturn { sets.lists.remove(at: k); chosen = sets.lists.first?.id }
                    } label: { Image(systemName: "minus") }.disabled(index == nil).help("Delete this set list")
                    Spacer()
                }.controlSize(.small)
            }
            .frame(width: 170)

            VStack(alignment: .leading, spacing: 6) {
                if let k = index {
                    TextField("Name", text: $sets.lists[k].name).textFieldStyle(.roundedBorder)
                    caption("In order: drag to move, or use the arrows")
                    List(selection: $entry) {
                        ForEach(Array(sets.lists[k].entries.enumerated()), id: \.element.id) { i, e in
                            Group {
                                if e.isBreak { IntermissionRow() } else {
                                    HStack(spacing: 6) {
                                        Text("\(songNumber(sets.lists[k].entries, i)).").monospacedDigit().foregroundStyle(.secondary)
                                        Text(e.title).opacity(SetLists.playable(e.path) ? 1 : 0.4)
                                    }
                                    .help(SetLists.playable(e.path) ? e.path : "Not found: \(e.path)")
                                }
                            }
                            .tag(e.id)
                        }
                        .onMove { sets.lists[k].entries.move(fromOffsets: $0, toOffset: $1) }
                        .onDelete { sets.lists[k].entries.remove(atOffsets: $0) }
                    }
                    .listStyle(.bordered(alternatesRowBackgrounds: true))
                    .onDeleteCommand { if let e = entry { sets.lists[k].entries.removeAll { $0.id == e }; entry = nil } }
                    HStack(spacing: 4) {
                        Button { move(-1) } label: { Image(systemName: "arrow.up") }.disabled(entry == nil).help("Earlier")
                        Button { move(1) } label: { Image(systemName: "arrow.down") }.disabled(entry == nil).help("Later")
                        Button { if let e = entry { sets.lists[k].entries.removeAll { $0.id == e }; entry = nil } } label: { Image(systemName: "minus") }
                            .disabled(entry == nil).help("Take this out of the set list")
                        Button("Add Intermission", action: addIntermission)
                            .help("After the song chosen, or at the end. Next and Previous step over it, and playing stops there.")
                        Spacer()
                        Button("Run This List") { sets.currentID = sets.lists[k].id }
                            .disabled(sets.currentID == sets.lists[k].id)
                            .help("Follow this list with the Next and Previous buttons")
                    }.controlSize(.small)
                } else {
                    Spacer()
                    Text(sets.lists.isEmpty ? "Click + to make a set list." : "Choose a set list.").foregroundStyle(.secondary).frame(maxWidth: .infinity)
                    Spacer()
                }
            }
            .frame(minWidth: 300, maxWidth: .infinity, maxHeight: .infinity)

            VStack(alignment: .leading, spacing: 6) {
                TextField("Find a song or tag", text: $search).textFieldStyle(.roundedBorder)
                DisclosureGroup(isExpanded: $tagsOpen) {
                    ScrollView(.vertical) {
                        VStack(alignment: .leading, spacing: 8) {
                            if !lib.folderTagList.isEmpty { tagCloud("Folders", lib.folderTagList) }
                            if !lib.userTagList.isEmpty { tagCloud("Your tags", lib.userTagList) }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 4)
                    }
                    .frame(maxHeight: 150)
                } label: {
                    caption(tags.isEmpty ? "Tags" : "Tags: " + tags.sorted { $0.localizedStandardCompare($1) == .orderedAscending }.joined(separator: ", "))
                        .lineLimit(1)
                }
                HStack {
                    caption("\(found.count) of \(lib.songs.count) songs. Double-click one to add it")
                    Spacer()
                    if !tags.isEmpty { Button("Clear Tags") { tags = [] }.controlSize(.small) }
                }
                List(found, selection: $song) { s in
                    Text(s.name)
                        .frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
                        .tag(s.path)
                        .gesture(TapGesture(count: 2).onEnded { add(s.path) })
                        .simultaneousGesture(TapGesture().onEnded { song = s.path })
                        .help(s.all.joined(separator: " · "))
                }
                .listStyle(.bordered(alternatesRowBackgrounds: true))
                HStack(spacing: 4) {
                    Button("Add") { if let s = song { add(s) } }.disabled(song == nil || index == nil)
                    Button("Add the Open Song") { if let f = p.folder?.path { add(f) } }.disabled(p.folder == nil || index == nil)
                    Spacer()
                }.controlSize(.small)
            }
            .frame(minWidth: 220, maxWidth: .infinity, maxHeight: .infinity)
        }
        .padding(14)
        .frame(minWidth: 760, minHeight: 420)
        .onAppear {
            SongLibrary.shared.refresh()
            if chosen == nil { chosen = sets.currentID ?? sets.lists.first?.id }
            // a tag no song has any more would hide every song with no chip left to unchoose
            let known = Set(lib.songs.flatMap(\.all))
            if !lib.songs.isEmpty && !tags.isSubset(of: known) { tags.formIntersection(known) }
        }
    }
}
