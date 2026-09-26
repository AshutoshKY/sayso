import AppKit
import Carbon
import Combine
import SwiftUI

/// Host preferences. Keep wake forms / key codes in lockstep with opener/settings.py.
enum PrefKey {
    static let suite = "com.laya.opener"
    static let listening = "listening_enabled"
    static let wake = "wake_enabled"
    static let hotkeyOn = "hotkey_enabled"
    static let hoverOn = "hover_enabled"
    static let clickOn = "click_enabled"
    static let phrases = "wake_phrases"
    static let hover = "hover_dwell_ms"
    static let hotkey = "hotkey"
    static let backend = "decision_backend"
}

enum SettingsLogic {
    static let defaultPhrases = ["hey mac", "bhai mac"]
    static let backends = ["laya", "jev"]
    static let hoverMin = 100
    static let hoverMax = 2000
    static let wakeForms: [String: [String]] = [
        "hey mac": ["hey mac", "hay mac", "hey mack", "hay mack"],
        "bhai mac": ["bhai mac", "bye mac", "by mac", "buy mac", "bai mac", "by mack", "bye mack"],
    ]
    static let keyCodes: [String: UInt32] = [
        "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
        "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17,
        "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26, "8": 28, "0": 29,
        "o": 31, "u": 32, "i": 34, "p": 35, "return": 36, "l": 37, "j": 38, "k": 40,
        "n": 45, "m": 46, "tab": 48, "space": 49, "delete": 51, "escape": 53,
        "left": 123, "right": 124, "down": 125, "up": 126,
    ]

    static func cleanText(_ text: String) -> String {
        var lowered = text.trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
        let filler = try? NSRegularExpression(pattern: "^(?:um+|uh+|er+|ah+|hmm+)\\s+", options: .caseInsensitive)
        while true {
            let ns = lowered as NSString
            guard let filler,
                  let match = filler.firstMatch(in: lowered, range: NSRange(location: 0, length: ns.length)),
                  match.range.length > 0
            else { break }
            lowered = ns.replacingCharacters(in: match.range, with: "").trimmingCharacters(in: .whitespaces)
        }
        return lowered
    }

    static func forms(for phrase: String) -> [String] {
        let key = phrase.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
        guard !key.isEmpty else { return [] }
        var out = [key]
        for item in wakeForms[key] ?? [] where !out.contains(item) {
            out.append(item)
        }
        return out
    }

    /// Prefix-only. Returns (hit, remainder after the wake phrase).
    static func matchWake(_ text: String, phrases: [String]) -> (Bool, String) {
        let cleaned = cleanText(text)
        if cleaned.isEmpty { return (false, "") }
        var candidates: [String] = []
        for phrase in phrases {
            candidates.append(contentsOf: forms(for: phrase))
        }
        candidates.sort { lhs, rhs in
            if lhs.count != rhs.count { return lhs.count > rhs.count }
            return lhs < rhs
        }
        for phrase in candidates {
            if cleaned == phrase { return (true, "") }
            let prefix = phrase + " "
            if cleaned.hasPrefix(prefix) {
                return (true, String(cleaned.dropFirst(prefix.count)).trimmingCharacters(in: .whitespaces))
            }
        }
        return (false, cleaned)
    }

    static func stripWake(_ text: String, phrases: [String]) -> String {
        let (hit, rest) = matchWake(text, phrases: phrases)
        return hit ? rest : text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// How long a bare wake waits for a following command. Apple's first
    /// partial is almost always just the wake word; committing then drops
    /// "open safari". Keep in lockstep with opener/settings.py WAKE_BARE_HOLD.
    static let wakeBareHold: TimeInterval = 0.45

    enum WakeCommit {
        case ignore
        case hold
        case go(String)
        case listen
    }

    static let incompleteCommand: [String] = [
        "open", "launch", "start", "run",
        "close", "quit", "kill", "force quit",
        "open the", "open a", "open an", "open my", "open please",
        "launch the", "launch a", "launch an", "launch my",
        "start the", "start a", "start an", "close the", "quit the",
    ]

    static func listStillOpen(_ text: String) -> Bool {
        // Apple often emits just "Calculator" mid-utterance. Keep the
        // long hold until and/then or a real silence after the last name.
        let cleaned = cleanText(text)
        if cleaned.isEmpty { return false }
        if cleaned.hasSuffix(",") || cleaned.hasSuffix(" and") || cleaned.hasSuffix(" then") {
            return true
        }
        if cleaned.range(of: "\\b(?:and|then)\\b", options: .regularExpression) != nil {
            return false
        }
        return true
    }

    static func commandReady(_ text: String) -> Bool {
        let cleaned = cleanText(text)
        if cleaned.isEmpty { return false }
        if incompleteCommand.contains(cleaned) { return false }
        if cleaned.hasSuffix(",") || cleaned.hasSuffix(" and") || cleaned.hasSuffix(" then") {
            return false
        }
        return true
    }

    static func listenHoldNamed(_ text: String) -> Bool {
        let cleaned = cleanText(text)
        if cleaned.isEmpty { return false }
        if incompleteCommand.contains(cleaned) { return false }
        if listStillOpen(cleaned) { return false }
        return true
    }

    /// Advance hover arming. Returns (armed, shouldSchedule).
    /// A listen consumes the current hover. Collapse and island-cover
    /// tracking events (fake exit/enter) must stay disarmed. Re-arm
    /// only on a later genuine mouse-exit after the island has collapsed.
    static func hoverApply(
        event: String,
        armed: Bool,
        expanded: Bool = false,
        busy: Bool = false,
        listeningEnabled: Bool = true,
        hoverEnabled: Bool = true
    ) -> (Bool, Bool) {
        if event == "start" || event == "collapse" { return (false, false) }
        if event == "exit" {
            if expanded || busy { return (false, false) }
            return (true, false)
        }
        guard event == "enter" else { return (armed, false) }
        let schedule = listeningEnabled && hoverEnabled && armed && !expanded && !busy
        return (armed, schedule)
    }

    static func wakeCommit(_ text: String, phrases: [String], elapsed: TimeInterval, hold: TimeInterval = wakeBareHold, final: Bool = false) -> WakeCommit {
        let (hit, rest) = matchWake(text, phrases: phrases)
        if !hit { return .ignore }
        // beginSeeded aborts the mic. A partial first name or a system-ish
        // fragment must not commit or later words are lost.
        if !rest.isEmpty, final { return .go(rest) }
        if elapsed >= hold, rest.isEmpty { return .listen }
        return .hold
    }

    static func name(forKeyCode code: UInt32) -> String? {
        keyCodes.first(where: { $0.value == code })?.key
    }

    static func normalizeHotkey(key: String, modifiers: [String]) -> (key: String, code: UInt32, modifiers: [String]) {
        var mapped = key.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if keyCodes[mapped] == nil { mapped = "space" }
        let aliases = [
            "ctrl": "control", "control": "control",
            "alt": "option", "opt": "option", "option": "option",
            "cmd": "command", "command": "command",
            "shift": "shift",
        ]
        var mods: [String] = []
        for item in modifiers {
            if let name = aliases[item.lowercased()], !mods.contains(name) {
                mods.append(name)
            }
        }
        if mods.isEmpty { mods = ["control", "option"] }
        let order = ["control", "option", "command", "shift"]
        mods = order.filter { mods.contains($0) }
        return (mapped, keyCodes[mapped] ?? 49, mods)
    }

    static func carbonModifiers(_ mods: [String]) -> UInt32 {
        var flags: UInt32 = 0
        if mods.contains("control") { flags |= UInt32(controlKey) }
        if mods.contains("option") { flags |= UInt32(optionKey) }
        if mods.contains("command") { flags |= UInt32(cmdKey) }
        if mods.contains("shift") { flags |= UInt32(shiftKey) }
        return flags
    }

    static func label(key: String, modifiers: [String]) -> String {
        var parts: [String] = []
        if modifiers.contains("control") { parts.append("⌃") }
        if modifiers.contains("option") { parts.append("⌥") }
        if modifiers.contains("shift") { parts.append("⇧") }
        if modifiers.contains("command") { parts.append("⌘") }
        if key == "space" {
            parts.append("Space")
        } else if key.count == 1 {
            parts.append(key.uppercased())
        } else {
            parts.append(key.capitalized)
        }
        return parts.joined()
    }
}

final class Preferences: ObservableObject {
    static let shared = Preferences()

    @Published var listeningEnabled: Bool { didSet { persist() } }
    @Published var wakeEnabled: Bool { didSet { persist() } }
    @Published var hotkeyEnabled: Bool { didSet { persist() } }
    @Published var hoverEnabled: Bool { didSet { persist() } }
    @Published var clickEnabled: Bool { didSet { persist() } }
    @Published var wakePhraseText: String { didSet { persist() } }
    @Published var hoverDwellMs: Int { didSet { persist() } }
    @Published var hotkeyKey: String { didSet { persist() } }
    @Published var hotkeyModifiers: [String] { didSet { persist() } }
    @Published var decisionBackend: String { didSet { persist() } }

    var micNeeded: Bool { listeningEnabled && wakeEnabled }

    var onChange: (() -> Void)?
    private var writing = false
    private var ready = false
    private let defaults = UserDefaults.standard

    var wakePhrases: [String] {
        let parts = wakePhraseText
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
            .filter { !$0.isEmpty }
        return parts.isEmpty ? SettingsLogic.defaultPhrases : parts
    }

    var wakeContextual: [String] {
        var seen = Set<String>()
        var out: [String] = []
        for phrase in wakePhrases {
            for form in SettingsLogic.forms(for: phrase) where !seen.contains(form) {
                seen.insert(form)
                out.append(form)
            }
        }
        return out
    }

    var hoverDwell: TimeInterval { Double(hoverDwellMs) / 1000.0 }

    var hotkeyCode: UInt32 {
        SettingsLogic.keyCodes[hotkeyKey] ?? 49
    }

    var hotkeyLabel: String {
        SettingsLogic.label(key: hotkeyKey, modifiers: hotkeyModifiers)
    }

    var payload: [String: Any] {
        [
            "listening_enabled": listeningEnabled,
            "wake_enabled": wakeEnabled,
            "hotkey_enabled": hotkeyEnabled,
            "hover_enabled": hoverEnabled,
            "click_enabled": clickEnabled,
            "wake_phrases": wakePhrases,
            "hover_dwell_ms": hoverDwellMs,
            "hotkey": [
                "key": hotkeyKey,
                "key_code": Int(hotkeyCode),
                "modifiers": hotkeyModifiers,
            ],
            "decision_backend": decisionBackend,
        ]
    }

    private init() {
        listeningEnabled = defaults.object(forKey: PrefKey.listening) as? Bool ?? true
        wakeEnabled = defaults.object(forKey: PrefKey.wake) as? Bool ?? true
        hotkeyEnabled = defaults.object(forKey: PrefKey.hotkeyOn) as? Bool ?? true
        hoverEnabled = defaults.object(forKey: PrefKey.hoverOn) as? Bool ?? true
        clickEnabled = defaults.object(forKey: PrefKey.clickOn) as? Bool ?? true
        let storedPhrases = defaults.stringArray(forKey: PrefKey.phrases) ?? SettingsLogic.defaultPhrases
        wakePhraseText = storedPhrases.joined(separator: ", ")
        let hover = defaults.object(forKey: PrefKey.hover) as? Int ?? 500
        hoverDwellMs = min(SettingsLogic.hoverMax, max(SettingsLogic.hoverMin, hover))
        if let raw = defaults.dictionary(forKey: PrefKey.hotkey) {
            let key = raw["key"] as? String ?? "space"
            let mods = raw["modifiers"] as? [String] ?? ["control", "option"]
            let norm = SettingsLogic.normalizeHotkey(key: key, modifiers: mods)
            hotkeyKey = norm.key
            hotkeyModifiers = norm.modifiers
        } else {
            hotkeyKey = "space"
            hotkeyModifiers = ["control", "option"]
        }
        let backend = (defaults.string(forKey: PrefKey.backend) ?? "laya").lowercased()
        decisionBackend = SettingsLogic.backends.contains(backend) ? backend : "laya"
        ready = true
    }

    func setHotkey(key: String, modifiers: [String]) {
        let norm = SettingsLogic.normalizeHotkey(key: key, modifiers: modifiers)
        hotkeyKey = norm.key
        hotkeyModifiers = norm.modifiers
    }

    private func persist() {
        guard ready, !writing else { return }
        writing = true
        defaults.set(listeningEnabled, forKey: PrefKey.listening)
        defaults.set(wakeEnabled, forKey: PrefKey.wake)
        defaults.set(hotkeyEnabled, forKey: PrefKey.hotkeyOn)
        defaults.set(hoverEnabled, forKey: PrefKey.hoverOn)
        defaults.set(clickEnabled, forKey: PrefKey.clickOn)
        defaults.set(wakePhrases, forKey: PrefKey.phrases)
        defaults.set(hoverDwellMs, forKey: PrefKey.hover)
        defaults.set(
            ["key": hotkeyKey, "key_code": Int(hotkeyCode), "modifiers": hotkeyModifiers],
            forKey: PrefKey.hotkey
        )
        defaults.set(decisionBackend, forKey: PrefKey.backend)
        writing = false
        onChange?()
    }
}

struct SettingsRoot: View {
    @ObservedObject var prefs: Preferences
    var onQuit: () -> Void
    @State private var recording = false

    var body: some View {
        Form {
            Section("Listening") {
                Toggle("Listening", isOn: $prefs.listeningEnabled)
                Text("Master switch. Off = no listen from any trigger.")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            Section("Triggers") {
                Toggle("Shortcut", isOn: $prefs.hotkeyEnabled)
                    .disabled(!prefs.listeningEnabled)
                Toggle("Hover notch", isOn: $prefs.hoverEnabled)
                    .disabled(!prefs.listeningEnabled)
                Toggle("Click notch / menu bar", isOn: $prefs.clickEnabled)
                    .disabled(!prefs.listeningEnabled)
                Toggle("Wake word", isOn: $prefs.wakeEnabled)
                    .disabled(!prefs.listeningEnabled)
                Text(prefs.micNeeded
                     ? "Wake word keeps the microphone on. Turn it off to clear the orange mic indicator."
                     : "Microphone is idle until you trigger a listen.")
                    .font(.caption)
                    .foregroundColor(.secondary)
                TextField("Wake phrases", text: $prefs.wakePhraseText)
                    .disabled(!prefs.listeningEnabled || !prefs.wakeEnabled)
                Text("Comma-separated. Default: hey mac, bhai mac")
                    .font(.caption)
                    .foregroundColor(.secondary)
                HStack {
                    Text("Hover wait")
                    Spacer()
                    Text("\(prefs.hoverDwellMs) ms")
                        .foregroundColor(.secondary)
                        .monospacedDigit()
                }
                .disabled(!prefs.listeningEnabled || !prefs.hoverEnabled)
                Slider(
                    value: Binding(
                        get: { Double(prefs.hoverDwellMs) },
                        set: { prefs.hoverDwellMs = Int($0.rounded()) }
                    ),
                    in: Double(SettingsLogic.hoverMin) ... Double(SettingsLogic.hoverMax),
                    step: 50
                )
                .disabled(!prefs.listeningEnabled || !prefs.hoverEnabled)
                HStack {
                    Text("Shortcut")
                    Spacer()
                    Button(recording ? "Press keys…" : prefs.hotkeyLabel) {
                        recording.toggle()
                    }
                    .keyboardShortcut(.defaultAction)
                    .disabled(!prefs.listeningEnabled || !prefs.hotkeyEnabled)
                }
                if recording {
                    HotkeyCatcher(active: $recording) { key, mods in
                        prefs.setHotkey(key: key, modifiers: mods)
                        recording = false
                    }
                    .frame(height: 1)
                    Text("Press the new shortcut. Esc cancels.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            Section("Decision") {
                Picker("Engine", selection: $prefs.decisionBackend) {
                    Text("Laya").tag("laya")
                    Text("Jev (soon)").tag("jev")
                }
                if prefs.decisionBackend != "laya" {
                    Text("\(prefs.decisionBackend.capitalized) is not wired yet. Requests will not open apps until it is.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            Section {
                Button("Quit Sayso", role: .destructive, action: onQuit)
            }
        }
        .formStyle(.grouped)
        .frame(minWidth: 420, minHeight: 520)
        .padding(.bottom, 8)
    }
}

struct HotkeyCatcher: NSViewRepresentable {
    @Binding var active: Bool
    var onCapture: (String, [String]) -> Void

    func makeNSView(context: Context) -> KeyCatcherView {
        let view = KeyCatcherView()
        view.onCapture = onCapture
        view.onCancel = { active = false }
        return view
    }

    func updateNSView(_ view: KeyCatcherView, context: Context) {
        view.onCapture = onCapture
        view.onCancel = { active = false }
        if active {
            DispatchQueue.main.async { view.window?.makeFirstResponder(view) }
        }
    }
}

final class KeyCatcherView: NSView {
    var onCapture: ((String, [String]) -> Void)?
    var onCancel: (() -> Void)?

    override var acceptsFirstResponder: Bool { true }

    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 {
            onCancel?()
            return
        }
        guard let name = SettingsLogic.name(forKeyCode: UInt32(event.keyCode)) else { return }
        var mods: [String] = []
        if event.modifierFlags.contains(.control) { mods.append("control") }
        if event.modifierFlags.contains(.option) { mods.append("option") }
        if event.modifierFlags.contains(.command) { mods.append("command") }
        if event.modifierFlags.contains(.shift) { mods.append("shift") }
        if mods.isEmpty { return }
        onCapture?(name, mods)
    }
}
