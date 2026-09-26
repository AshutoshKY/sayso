import AppKit
import ApplicationServices
import Foundation

struct Thresholds: Codable {
    var intent: Double
    var app: Double
}

struct AppSpec: Codable {
    var open: String
    var say: String
    var bundle: String?
    var aliases: [String]
    var criteria: String
    var paths: [String]?
}

struct CatalogFile: Codable {
    var laya_url: String
    var opener_url: String?
    var opener_health: String?
    var container: String
    var laya_container: String?
    var thresholds: Thresholds
    var intent: [String: String]
    var unspecified: String
    var apps: [String: AppSpec]
}

struct LayaHead {
    var choice: String?
    var confidence: Double
}

struct Decision {
    var action: String
    var app: String?
    var reason: String
    var apps: [String] = []
    var pending: [String] = []
    var url: String?
}

enum Engine {
    static let stopPhrases = [
        "goodbye", "good bye", "bye", "stop listening", "that's all",
        "thats all", "quit listening", "go to sleep", "we're done", "we are done",
    ]
    static let chatPhrases: Set<String> = [
        "hello", "hi", "hey", "hello there", "hi there", "hey there",
        "good morning", "good afternoon", "good evening",
        "thanks", "thank you", "how are you", "what's up", "whats up", "yo",
    ]
    static let genericBrowser = [
        "the browser", "a browser", "web browser", "my browser", "default browser",
    ]
    static let genericMusic = [
        "play some music", "play music", "some music", "play a song", "play a track",
    ]
    static let layaCriteria: [String: String] = [
        "notes": "jot something down, write a note, apple notes",
        "reminders": "remind me later, a to-do, reminders",
        "mail": "send an email, inbox, mail",
        "messages": "send a text, imessage, messages",
        "finder": "where is that file, browse folders, finder",
        "facetime": "take a video call, facetime",
        "calendar": "show my calendar, schedule, agenda",
        "photos": "show my photos, photo library",
        "maps": "get directions, apple maps",
        "spotify": "play music on spotify",
        "music": "apple music specifically",
        "unspecified": "weather, small talk, or none of the apps above",
    ]
    static let negation = [
        "don't", "dont", "do not", "never", "hate",
        "not open", "no need to open",
    ]
    static let lifecycleVerbs = [
        "force quit", "close", "quit", "kill",
    ]
    static let protectedApps: Set<String> = ["finder", "layaopener"]
    static let siteWords: [String] = [
        "youtube", "you tube", "youtu.be", "github", "gmail", "chatgpt",
        "clipboard", "reddit", "twitter", "google.com", "youtube.com", "github.com",
    ]

    static func looksLikeURLOpen(_ text: String) -> Bool {
        let lowered = text.lowercased()
        if lowered.range(of: #"\bin\b"#, options: .regularExpression) != nil { return true }
        if siteWords.contains(where: { wordMatch($0, in: lowered) }) { return true }
        if lowered.range(of: #"\b[a-z0-9-]+\.(com|org|net|io|dev|app|ai)\b"#, options: .regularExpression) != nil {
            return true
        }
        return false
    }

    static func loadCatalog() -> CatalogFile {
        let urls = [
            Bundle.main.url(forResource: "catalog", withExtension: "json"),
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
                .appendingPathComponent("catalog.json"),
        ]
        for url in urls.compactMap({ $0 }) {
            if let data = try? Data(contentsOf: url),
               let file = try? JSONDecoder().decode(CatalogFile.self, from: data)
            {
                return file
            }
        }
        fatalError("catalog.json missing from app bundle")
    }

    static let scanRoots: [String] = [
        "/Applications",
        "/System/Applications",
        "/System/Applications/Utilities",
        "/System/Cryptexes/App/System/Applications",
        NSHomeDirectory() + "/Applications",
    ]

    static func slug(_ name: String) -> String {
        name.lowercased().unicodeScalars
            .filter { CharacterSet.alphanumerics.contains($0) }
            .map(String.init)
            .joined()
    }

    static let productTails: Set<String> = ["warp", "desktop", "helper", "pro", "lite", "ide"]
    static let compounds: [(String, String)] = [
        ("cloudflare", "cloud flare"),
        ("whatsapp", "whats app"),
        ("facetime", "face time"),
        ("antigravity", "anti gravity"),
        ("textedit", "text edit"),
    ]
    static let speechForms: [String: [String]] = [
        "hermes": ["her mes", "her mess", "hermits", "hurmez"],
    ]

    static func aliases(forName name: String) -> [String] {
        let lower = name.lowercased()
        let spacedCamel = name.replacingOccurrences(
            of: "([a-z])([A-Z])",
            with: "$1 $2",
            options: .regularExpression
        ).lowercased()
        let tokens = spacedCamel.split { ch in
            !ch.isLetter && !ch.isNumber
        }.map(String.init).filter { !$0.isEmpty }
        let spaced = tokens.joined(separator: " ")
        let compact = tokens.joined()
        var out: [String] = []
        for item in [lower, spacedCamel, spaced, compact] where !item.isEmpty && !out.contains(item) {
            out.append(item)
        }
        if spaced.hasSuffix(" edit") {
            let editor = spaced + "or"
            if !out.contains(editor) { out.append(editor) }
        }
        if spaced.hasSuffix("s") && spaced.count >= 7 && !spaced.hasSuffix("ss") && !spaced.hasSuffix("us")
            && !spaced.hasSuffix("is") && !spaced.hasSuffix("os")
        {
            let singular = String(spaced.dropLast())
            if !singular.isEmpty && !out.contains(singular) { out.append(singular) }
        }
        let appleShort: Set<String> = ["tv", "mail", "notes", "music", "maps", "photos", "calendar", "podcasts"]
        if appleShort.contains(compact) {
            let apple = "apple " + (spaced.isEmpty ? compact : spaced)
            if !out.contains(apple) { out.append(apple) }
        }
        let blocked: Set<String> = ["video", "editor", "player", "manager", "helper", "studio", "browser", "launcher"]
        if tokens.count >= 2 {
            let head = tokens.prefix(2).joined(separator: " ")
            if !out.contains(head) { out.append(head) }
            if let tail = tokens.last, tail.count >= 8, !blocked.contains(tail), !out.contains(tail) {
                out.append(tail)
            }
            if let first = tokens.first, let tail = tokens.last,
               !out.contains(first), !blocked.contains(first),
               first.count >= 10 || (first.count >= 8 && productTails.contains(tail))
            {
                out.append(first)
            }
        }
        for (token, exploded) in compounds where compact.contains(token) {
            let rest = compact.replacingOccurrences(of: token, with: "", options: [], range: compact.range(of: token))
            for form in [exploded, token, rest.isEmpty ? exploded : (exploded + " " + rest)]
            where !form.isEmpty && !out.contains(form) {
                out.append(form)
            }
        }
        for form in speechForms[compact] ?? [] where !out.contains(form) {
            out.append(form)
        }
        return out
    }

    static func shouldSkip(_ stem: String) -> Bool {
        let lowered = stem.lowercased()
        if lowered.hasPrefix(".") { return true }
        if ["utilities", "relocated items"].contains(lowered) { return true }
        for suffix in [" helper", " uninstaller", " installer", " updater", " crash reporter"] {
            if lowered.hasSuffix(suffix) { return true }
        }
        return false
    }

    static func installed(_ file: CatalogFile) -> CatalogFile {
        var copy = file
        var kept: [String: AppSpec] = [:]
        for (id, spec) in file.apps {
            if let paths = spec.paths {
                if let hit = paths.first(where: { FileManager.default.fileExists(atPath: $0) }) {
                    var next = spec
                    next.paths = [hit]
                    kept[id] = next
                }
            } else {
                kept[id] = spec
            }
        }
        var knownPaths = Set(kept.values.compactMap(\.paths).flatMap { $0 })
        var knownBundles = Set(kept.values.compactMap(\.bundle))
        for root in scanRoots {
            guard let items = try? FileManager.default.contentsOfDirectory(atPath: root) else { continue }
            for item in items where item.hasSuffix(".app") {
                let path = (root as NSString).appendingPathComponent(item)
                var isDir: ObjCBool = false
                guard FileManager.default.fileExists(atPath: path, isDirectory: &isDir), isDir.boolValue else { continue }
                let stem = String(item.dropLast(4))
                if shouldSkip(stem) { continue }
                if knownPaths.contains(path) { continue }
                let bundle = Bundle(path: path)?.bundleIdentifier
                if let bundle, knownBundles.contains(bundle) { continue }
                var key = slug(stem)
                if key.isEmpty { continue }
                var n = 2
                while kept[key] != nil {
                    key = slug(stem) + String(n)
                    n += 1
                }
                let aliases = aliases(forName: stem)
                let sample = aliases.prefix(4).joined(separator: ", ")
                kept[key] = AppSpec(
                    open: stem,
                    say: stem,
                    bundle: bundle,
                    aliases: aliases,
                    criteria: "the app \(stem). \(sample)",
                    paths: [path]
                )
                knownPaths.insert(path)
                if let bundle { knownBundles.insert(bundle) }
            }
        }
        copy.apps = kept
        return copy
    }

    static func defaultBrowser(in file: CatalogFile) -> String? {
        guard let url = URL(string: "https://example.com"),
              let appURL = NSWorkspace.shared.urlForApplication(toOpen: url),
              let bid = Bundle(url: appURL)?.bundleIdentifier
        else {
            return file.apps["safari"] != nil ? "safari" : file.apps.keys.sorted().first
        }
        if let match = file.apps.first(where: { $0.value.bundle == bid }) {
            return match.key
        }
        return file.apps["safari"] != nil ? "safari" : nil
    }

    static func wordMatch(_ phrase: String, in text: String) -> Bool {
        let escaped = NSRegularExpression.escapedPattern(for: phrase)
        let pattern = "(?<!\\w)" + escaped + "(?!\\w)"
        return text.range(of: pattern, options: [.regularExpression, .caseInsensitive]) != nil
    }

    static func isStop(_ text: String) -> Bool {
        stopPhrases.contains { wordMatch($0, in: text) }
    }

    static func spokenKey(_ text: String) -> String {
        var lowered = text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let prefix = ["force quit ", "open ", "launch ", "start ", "run ", "close ", "quit ", "kill "]
        for item in prefix where lowered.hasPrefix(item) {
            lowered = String(lowered.dropFirst(item.count))
            break
        }
        while true {
            var trimmed = lowered
            for suffix in [" app", " application", " please"] {
                if trimmed.hasSuffix(suffix) {
                    trimmed = String(trimmed.dropLast(suffix.count))
                }
            }
            if trimmed == lowered { break }
            lowered = trimmed
        }
        return slug(lowered)
    }

    static func exactInstalledId(_ text: String, catalog: CatalogFile) -> String? {
        let key = spokenKey(text)
        if !key.isEmpty, catalog.apps[key] != nil { return key }
        return nil
    }

    static func splitRequests(_ text: String) -> [String] {
        let raw = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if raw.isEmpty { return [] }
        let splitter = try? NSRegularExpression(pattern: "\\s*(?:,|\\band\\b|\\bthen\\b)\\s*", options: .caseInsensitive)
        let ns = raw as NSString
        var parts: [String] = []
        var cursor = 0
        if let splitter {
            for match in splitter.matches(in: raw, range: NSRange(location: 0, length: ns.length)) {
                let piece = ns.substring(with: NSRange(location: cursor, length: match.range.location - cursor))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if !piece.isEmpty { parts.append(piece) }
                cursor = match.range.location + match.range.length
            }
        }
        let tail = ns.substring(from: cursor).trimmingCharacters(in: .whitespacesAndNewlines)
        if !tail.isEmpty { parts.append(tail) }
        if parts.count <= 1 { return [raw] }
        let verbs = ["force quit ", "close ", "quit ", "kill ", "open ", "launch ", "start ", "run "]
        var prefix = ""
        let firstLower = parts[0].lowercased()
        for verb in verbs where firstLower.hasPrefix(verb) {
            prefix = String(parts[0].prefix(verb.count))
            break
        }
        return parts.enumerated().map { index, part in
            if index == 0 || prefix.isEmpty { return part }
            let lowered = part.lowercased()
            if verbs.contains(where: { lowered.hasPrefix($0) }) { return part }
            return prefix + part
        }
    }

    static func namedApps(in text: String, catalog: CatalogFile, browser: String?) -> [String] {
        var out: [String] = []
        for part in splitRequests(text) {
            for recovered in namedInPart(part, catalog: catalog, browser: browser) where !out.contains(recovered) {
                out.append(recovered)
            }
        }
        return out
    }

    static func namedInPart(_ part: String, catalog: CatalogFile, browser: String?) -> [String] {
        // Walk tokens left-to-right. Do not compact the whole chunk —
        // "calculator antigravity" is two ids, not one fake spoken_key.
        let tokens = part.lowercased().split { !$0.isLetter && !$0.isNumber }.map(String.init)
        guard !tokens.isEmpty else { return [] }
        var aliases: [(Int, [String], String)] = []
        for (id, spec) in catalog.apps {
            var names = [id, spec.say, spec.open]
            names.append(contentsOf: spec.aliases)
            for name in names {
                let words = name.lowercased().split { !$0.isLetter && !$0.isNumber }.map(String.init)
                if !words.isEmpty {
                    aliases.append((words.count, words, id))
                }
            }
        }
        aliases.sort { lhs, rhs in
            if lhs.0 != rhs.0 { return lhs.0 > rhs.0 }
            return lhs.2 < rhs.2
        }
        var out: [String] = []
        var i = 0
        while i < tokens.count {
            var hit: String?
            var width = 0
            for item in aliases {
                let length = item.0
                guard i + length <= tokens.count else { continue }
                if Array(tokens[i..<(i + length)]) == item.1 {
                    hit = item.2
                    width = length
                    break
                }
            }
            if let hit {
                if !out.contains(hit) { out.append(hit) }
                i += max(width, 1)
            } else {
                i += 1
            }
        }
        return out
    }

    static func newlyNamedApps(
        _ text: String,
        catalog: CatalogFile,
        browser: String?,
        already: Set<String>
    ) -> [String] {
        namedApps(in: text, catalog: catalog, browser: browser).filter { !already.contains($0) }
    }

    static let commonSpeech: Set<String> = [
        "notes", "mail", "safari", "chrome", "calendar", "photos", "maps",
        "messages", "finder", "music", "settings", "terminal", "preview",
    ]

    static func isUnusual(_ id: String, spec: AppSpec) -> Bool {
        let compact = slug(id)
        if speechForms[compact] != nil { return true }
        if compounds.contains(where: { compact.contains($0.0) }) { return true }
        let official: Set<String> = [compact, slug(spec.say), slug(spec.open)]
        return spec.aliases.contains { !official.contains(slug($0)) }
    }

    static func phrasePriority(_ phrase: String, id: String, spec: AppSpec) -> Int {
        let lowered = phrase.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let compact = slug(lowered)
        if speechForms[compact] != nil || (speechForms[slug(id)] ?? []).contains(lowered) {
            return 0
        }
        if compounds.contains(where: { slug(id).contains($0.0) || compact.contains($0.0) }) {
            return 1
        }
        if isUnusual(id, spec: spec) && !commonSpeech.contains(compact) {
            return 2
        }
        return 3
    }

    static func speechPhrases(from file: CatalogFile, limit: Int = 100) -> [String] {
        var seen = Set<String>()
        var scored: [(Int, String, String)] = []
        for (id, spec) in file.apps {
            var candidates = [spec.say.isEmpty ? (spec.open.isEmpty ? id : spec.open) : spec.say]
            candidates.append(contentsOf: spec.aliases)
            for raw in candidates {
                let phrase = raw.trimmingCharacters(in: .whitespacesAndNewlines)
                guard phrase.count >= 3, phrase.count <= 32 else { continue }
                let key = phrase.lowercased()
                guard !seen.contains(key) else { continue }
                seen.insert(key)
                scored.append((phrasePriority(phrase, id: id, spec: spec), key, phrase))
            }
        }
        scored.sort { lhs, rhs in
            if lhs.0 != rhs.0 { return lhs.0 < rhs.0 }
            return lhs.1 < rhs.1
        }
        let extras = [
            "youtube", "you tube", "youtube.com",
            "github", "github.com",
            "gmail", "chatgpt", "clipboard",
            "reddit", "twitter",
        ]
        var out = scored.prefix(max(0, limit - extras.count)).map(\.2)
        var used = Set(out.map { $0.lowercased() })
        for extra in extras where extra.count >= 3 && extra.count <= 32 {
            let key = extra.lowercased()
            guard !used.contains(key) else { continue }
            used.insert(key)
            out.append(extra)
        }
        return Array(out.prefix(limit))
    }

    static func preferCatalog(_ texts: [String], catalog: CatalogFile) -> String {
        let cleaned = texts
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        guard let first = cleaned.first else { return "" }
        var firstNamed: String?
        var best: String?
        var bestScore: (Int, Int)?
        for (index, text) in cleaned.enumerated() {
            guard let named = resolveAlias(text, catalog: catalog, browser: nil) else { continue }
            if firstNamed == nil { firstNamed = named }
            if named != firstNamed { continue }
            let spec = catalog.apps[named]
            var official = [named]
            if let say = spec?.say, !say.isEmpty { official.append(say) }
            if let open = spec?.open, !open.isEmpty { official.append(open) }
            let canon = official.contains { wordMatch($0, in: text) }
            let score = (canon ? 0 : 1, index)
            if bestScore == nil || score.0 < bestScore!.0 || (score.0 == bestScore!.0 && score.1 < bestScore!.1) {
                bestScore = score
                best = text
            }
        }
        return best ?? first
    }

    static func resolveAlias(_ text: String, catalog: CatalogFile, browser: String?) -> String? {
        if let exact = exactInstalledId(text, catalog: catalog) {
            return exact
        }
        var hits: [(Int, String)] = []
        for (id, spec) in catalog.apps {
            for alias in spec.aliases where !alias.isEmpty && wordMatch(alias, in: text) {
                hits.append((alias.count, id))
            }
        }
        if !hits.isEmpty {
            hits.sort { lhs, rhs in
                if lhs.0 != rhs.0 { return lhs.0 > rhs.0 }
                return lhs.1 < rhs.1
            }
            return hits[0].1
        }
        if let browser, genericBrowser.contains(where: { wordMatch($0, in: text) }) {
            return browser
        }
        if let music = defaultMusic(in: catalog),
           genericMusic.contains(where: { wordMatch($0, in: text) })
        {
            return music
        }
        return nil
    }

    static func defaultMusic(in file: CatalogFile) -> String? {
        if file.apps["spotify"] != nil { return "spotify" }
        if file.apps["music"] != nil { return "music" }
        return nil
    }

    static func decide(
        text: String,
        alias: String?,
        intent: LayaHead,
        app: LayaHead,
        thresholds: Thresholds
    ) -> Decision {
        if isStop(text) { return Decision(action: "stop", app: nil, reason: "stop") }
        if intent.choice == "refuse" {
            return Decision(action: "refuse", app: nil, reason: "laya")
        }
        if intent.choice == nil {
            if app.choice == nil || app.choice == "unspecified" || app.confidence < thresholds.app {
                return Decision(action: "ask", app: nil, reason: "unspecified")
            }
            return Decision(action: "open", app: app.choice, reason: "laya")
        }
        if intent.choice != "launch" || intent.confidence < thresholds.intent {
            return Decision(action: "chat", app: nil, reason: "not-launch")
        }
        if app.choice == nil || app.choice == "unspecified" || app.confidence < thresholds.app {
            return Decision(action: "ask", app: nil, reason: "unspecified")
        }
        return Decision(action: "open", app: app.choice, reason: "laya")
    }

    static func spokenNames(_ ids: [String], catalog: CatalogFile, fallback: String = "it") -> String {
        let names = ids.map { catalog.apps[$0]?.say ?? $0 }
        if names.isEmpty { return fallback }
        if names.count == 1 { return names[0] }
        return "\(names.dropLast().joined(separator: ", ")) and \(names.last!)"
    }

    static func spoken(_ decision: Decision, catalog: CatalogFile) -> String {
        let ids = decision.apps.isEmpty ? [decision.app].compactMap { $0 } : decision.apps
        switch decision.action {
        case "open_url":
            if decision.url == "clipboard" {
                if let app = decision.app, !app.isEmpty {
                    return "Opening the clipboard in \(spokenNames([app], catalog: catalog))."
                }
                return "Opening the clipboard."
            }
            let site = siteLabel(decision.url)
            if let app = decision.app, !app.isEmpty {
                return "Opening \(site) in \(spokenNames([app], catalog: catalog))."
            }
            return "Opening \(site)."
        case "open":
            return "Opening \(spokenNames(ids, catalog: catalog))."
        case "close", "quit", "kill":
            let verb = decision.action == "close" ? "Closed"
                : decision.action == "quit" ? "Quit" : "Force quit"
            var line = "\(verb) \(spokenNames(ids, catalog: catalog))."
            if !decision.pending.isEmpty {
                line += " \(spokenNames(decision.pending, catalog: catalog, fallback: "that app")) isn't open. Open it?"
            }
            return line
        case "confirm":
            let pending = decision.pending.isEmpty ? ids : decision.pending
            return "\(spokenNames(pending, catalog: catalog, fallback: "That app")) isn't open. Open it?"
        case "refuse":
            return "Okay, I won't."
        case "ask":
            if decision.reason == "which-app" { return "Which app should I close?" }
            if decision.reason == "protected" { return "I won't quit that." }
            return "Which app should I open?"
        case "stop":
            return "Goodbye."
        default:
            return "I open apps. Try saying open notes, or open the browser."
        }
    }

    static func siteLabel(_ raw: String?) -> String {
        guard let raw, !raw.isEmpty, raw != "clipboard" else { return "the clipboard" }
        let host = raw.replacingOccurrences(of: "https://", with: "")
            .replacingOccurrences(of: "http://", with: "")
            .split(separator: "/").first.map(String.init)?.lowercased() ?? raw
        let labels: [String: String] = [
            "youtube.com": "YouTube", "www.youtube.com": "YouTube", "youtu.be": "YouTube",
            "github.com": "GitHub", "www.github.com": "GitHub",
            "mail.google.com": "Gmail", "gmail.com": "Gmail",
            "google.com": "Google", "www.google.com": "Google",
            "x.com": "X", "twitter.com": "X",
            "reddit.com": "Reddit", "www.reddit.com": "Reddit",
            "chatgpt.com": "ChatGPT", "chat.openai.com": "ChatGPT",
        ]
        if let named = labels[host] { return named }
        if host.hasPrefix("www."), let named = labels[String(host.dropFirst(4))] { return named }
        return host
    }

    static func applicationURL(for id: String, catalog: CatalogFile) -> URL? {
        guard let spec = catalog.apps[id] else { return nil }
        if let path = spec.paths?.first, FileManager.default.fileExists(atPath: path) {
            return URL(fileURLWithPath: path)
        }
        if let bid = spec.bundle,
           let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bid)
        {
            return url
        }
        return nil
    }

    static func openURL(_ raw: String, inApp id: String?, catalog: CatalogFile) {
        if raw == "clipboard" {
            openClipboard(inApp: id, catalog: catalog)
            return
        }
        guard let page = URL(string: raw) else { return }
        let config = NSWorkspace.OpenConfiguration()
        if let id, let appURL = applicationURL(for: id, catalog: catalog) {
            NSWorkspace.shared.open([page], withApplicationAt: appURL, configuration: config)
            return
        }
        NSWorkspace.shared.open(page)
    }

    static func openClipboard(inApp id: String?, catalog: CatalogFile) {
        let board = NSPasteboard.general
        if let urls = board.readObjects(forClasses: [NSURL.self], options: nil) as? [URL],
           let first = urls.first
        {
            let config = NSWorkspace.OpenConfiguration()
            if let id, let appURL = applicationURL(for: id, catalog: catalog) {
                NSWorkspace.shared.open([first], withApplicationAt: appURL, configuration: config)
            } else {
                NSWorkspace.shared.open(first)
            }
            return
        }
        let text = (board.string(forType: .string) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        if let page = URL(string: text), let scheme = page.scheme,
           ["http", "https", "file"].contains(scheme.lowercased())
        {
            openURL(page.absoluteString, inApp: id, catalog: catalog)
            return
        }
        if text.hasPrefix("/"), FileManager.default.fileExists(atPath: text) {
            NSWorkspace.shared.open(URL(fileURLWithPath: text))
            return
        }
        if let id {
            openApp(id, catalog: catalog)
        }
    }

    static func openApp(_ id: String, catalog: CatalogFile) {
        guard let spec = catalog.apps[id] else { return }
        let config = NSWorkspace.OpenConfiguration()
        if let path = spec.paths?.first, FileManager.default.fileExists(atPath: path) {
            NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: path), configuration: config)
            return
        }
        if let bid = spec.bundle,
           let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bid)
        {
            NSWorkspace.shared.openApplication(at: url, configuration: config)
        }
    }

    static func runningIds(in catalog: CatalogFile) -> [String] {
        catalog.apps.compactMap { id, _ in
            isRunning(id, catalog: catalog) ? id : nil
        }.sorted()
    }

    static func runningApps(for id: String, catalog: CatalogFile) -> [NSRunningApplication] {
        guard let spec = catalog.apps[id] else { return [] }
        if let bid = spec.bundle, !bid.isEmpty {
            return NSRunningApplication.runningApplications(withBundleIdentifier: bid)
        }
        let wanted = slug(spec.open.isEmpty ? id : spec.open)
        return NSWorkspace.shared.runningApplications.filter { app in
            guard let name = app.localizedName else { return false }
            return slug(name) == wanted
        }
    }

    static func isRunning(_ id: String, catalog: CatalogFile) -> Bool {
        runningApps(for: id, catalog: catalog).contains { !$0.isTerminated }
    }

    static func closeWindows(_ id: String, catalog: CatalogFile) {
        // Accessibility, not Apple Events: one TCC grant instead of a
        // per-app Automation prompt every first close.
        ensureAccessibility()
        let apps = runningApps(for: id, catalog: catalog)
        for app in apps where !app.isTerminated {
            closeWindows(of: app)
        }
    }

    static func ensureAccessibility() {
        let prompt = kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String
        let opts = [prompt: true] as CFDictionary
        _ = AXIsProcessTrustedWithOptions(opts)
    }

    static func closeWindows(of app: NSRunningApplication) {
        let pid = app.processIdentifier
        guard pid > 0 else { return }
        let element = AXUIElementCreateApplication(pid)
        var value: AnyObject?
        let err = AXUIElementCopyAttributeValue(element, kAXWindowsAttribute as CFString, &value)
        guard err == .success, let windows = value as? [AXUIElement] else { return }
        for window in windows {
            var buttonRef: AnyObject?
            let got = AXUIElementCopyAttributeValue(window, kAXCloseButtonAttribute as CFString, &buttonRef)
            if got == .success, let button = buttonRef {
                AXUIElementPerformAction(button as! AXUIElement, kAXPressAction as CFString)
                continue
            }
            AXUIElementPerformAction(window, kAXCancelAction as CFString)
        }
    }

    static func quitApp(_ id: String, catalog: CatalogFile, force: Bool) {
        let apps = runningApps(for: id, catalog: catalog)
        for app in apps where !app.isTerminated {
            if force {
                _ = app.forceTerminate()
            } else {
                _ = app.terminate()
            }
        }
    }

    static func speak(_ text: String) {
        guard !text.isEmpty else { return }
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/say")
        task.arguments = ["-v", "Samantha", text]
        task.standardOutput = FileHandle.nullDevice
        task.standardError = FileHandle.nullDevice
        try? task.run()
    }

    static func dockerBin() -> String {
        for path in ["/opt/homebrew/bin/docker", "/usr/local/bin/docker"] {
            if FileManager.default.isExecutableFile(atPath: path) { return path }
        }
        return "/usr/local/bin/docker"
    }

    static func run(_ args: [String]) {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: args[0])
        task.arguments = Array(args.dropFirst())
        task.standardOutput = FileHandle.nullDevice
        task.standardError = FileHandle.nullDevice
        try? task.run()
        task.waitUntilExit()
    }

    static func healthOK(_ raw: String = "http://127.0.0.1:8010/health") -> Bool {
        guard let url = URL(string: raw) else { return false }
        var request = URLRequest(url: url)
        request.timeoutInterval = 2
        let sem = DispatchSemaphore(value: 0)
        var ok = false
        URLSession.shared.dataTask(with: request) { data, _, _ in
            if let data, let body = String(data: data, encoding: .utf8), body.contains("ok") {
                ok = true
            }
            sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + 2.5)
        return ok
    }

    static func ensureLaya(container: String, layaContainer: String = "laya-upstream") -> Bool {
        if healthOK() { return true }
        run([dockerBin(), "start", layaContainer])
        run([dockerBin(), "start", container])
        for _ in 0 ..< 30 {
            if healthOK() { return true }
            Thread.sleep(forTimeInterval: 0.4)
        }
        return healthOK()
    }

    static func predict(text: String, catalog: CatalogFile) -> (LayaHead, LayaHead) {
        let empty = (LayaHead(choice: nil, confidence: 0), LayaHead(choice: nil, confidence: 0))
        guard let url = URL(string: catalog.laya_url) else { return empty }

        let body: [String: Any] = [
            "state": text,
            "model": "english",
            "questions": [
                "app": [
                    "type": "choice",
                    "instructions": "Which app is the user talking about?",
                    "criteria": layaCriteria,
                ],
            ],
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: body) else { return empty }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "content-type")
        request.httpBody = data
        request.timeoutInterval = 30

        let sem = DispatchSemaphore(value: 0)
        var payload: [String: Any] = [:]
        URLSession.shared.dataTask(with: request) { data, _, _ in
            if let data,
               let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            {
                payload = obj
            }
            sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + 31)
        let answers = payload["answers"] as? [String: Any] ?? [:]
        return (head(answers["intent"]), head(answers["app"]))
    }

    static func head(_ raw: Any?) -> LayaHead {
        guard let block = raw as? [String: Any] else {
            return LayaHead(choice: nil, confidence: 0)
        }
        let choice = block["choice"] as? String
        let conf = (block["answer_confidence"] as? Double)
            ?? (block["confidence"] as? Double)
            ?? 0
        return LayaHead(choice: choice, confidence: conf)
    }

    static func handle(
        text: String,
        catalog: CatalogFile,
        browser: String?,
        settings: [String: Any] = [:],
        running: [String] = [],
        pending: [String] = []
    ) -> Decision {
        _ = browser
        let phrases = (settings["wake_phrases"] as? [String]) ?? SettingsLogic.defaultPhrases
        let wakeOn = (settings["wake_enabled"] as? Bool) ?? true
        var uttered = text
        if wakeOn {
            let (hit, rest) = SettingsLogic.matchWake(text, phrases: phrases)
            if hit {
                if rest.isEmpty {
                    return Decision(action: "chat", app: nil, reason: "wake")
                }
                uttered = rest
            }
        }
        if isStop(uttered) {
            return Decision(action: "stop", app: nil, reason: "stop")
        }
        return remoteDecide(
            text: uttered,
            catalog: catalog,
            settings: settings,
            running: running,
            pending: pending
        )
    }

    static func remoteDecide(
        text: String,
        catalog: CatalogFile,
        settings: [String: Any] = [:],
        running: [String] = [],
        pending: [String] = []
    ) -> Decision {
        let endpoint = catalog.opener_url ?? "http://127.0.0.1:8010/decide"
        guard let url = URL(string: endpoint) else {
            return Decision(action: "ask", app: nil, reason: "bad-url")
        }
        var apps: [String: [String: Any]] = [:]
        for (id, spec) in catalog.apps {
            apps[id] = [
                "say": spec.say,
                "criteria": spec.criteria,
                "aliases": spec.aliases,
            ]
        }
        var body: [String: Any] = [
            "text": text,
            "catalog": apps,
            "running": running,
            "pending": pending,
        ]
        if !settings.isEmpty {
            body["settings"] = settings
            if let backend = settings["decision_backend"] {
                body["backend"] = backend
            }
        }
        guard let data = try? JSONSerialization.data(withJSONObject: body) else {
            return Decision(action: "ask", app: nil, reason: "encode")
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "content-type")
        request.httpBody = data
        request.timeoutInterval = 30
        let sem = DispatchSemaphore(value: 0)
        var payload: [String: Any] = [:]
        let t0 = Date()
        URLSession.shared.dataTask(with: request) { data, _, _ in
            if let data,
               let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            {
                payload = obj
            }
            sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + 31)
        NSLog("laya-opener http /decide %.0fms", Date().timeIntervalSince(t0) * 1000)
        let action = payload["action"] as? String ?? "ask"
        let app = payload["app"] as? String
        let opened = payload["apps"] as? [String] ?? []
        let waiting = payload["pending"] as? [String] ?? []
        let page = payload["url"] as? String
        return Decision(
            action: action,
            app: app,
            reason: payload["reason"] as? String ?? "laya",
            apps: opened.isEmpty ? (app.map { [$0] } ?? []) : opened,
            pending: waiting,
            url: page
        )
    }
}
