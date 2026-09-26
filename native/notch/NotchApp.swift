import AppKit
import Carbon
import SwiftUI

enum Mode {
    case idle, waking, listening, thinking, ok, fail
}

final class AppState: ObservableObject {
    @Published var mode: Mode = .idle
    @Published var caption: String = ""
    @Published var expanded: Bool = false
    @Published var busy: Bool = false
    @Published var openedIds: [String] = []
    @Published var resultVerb: String = "Opened"
}

private var retainedDelegate: AppDelegate?

@main
enum LayaOpener {
    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        retainedDelegate = delegate
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        app.run()
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    let state = AppState()
    var catalog: CatalogFile!
    var browser: String?
    let listener = MicListener()
    let wakeListener = MicListener(timeout: 20, silence: 0.35)
    let prefs = Preferences.shared
    var panel: NotchPanel!
    var islandPanel: NotchPanel!
    var status: NSStatusItem?
    var settingsWindow: NSWindow?
    var hotKeyRef: EventHotKeyRef?
    var eventHandler: EventHandlerRef?
    var wakeRestart: DispatchWorkItem?
    var wakeFirstHeard: Date?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        catalog = Engine.installed(Engine.loadCatalog())
        browser = Engine.defaultBrowser(in: catalog)
        configureSpeech()
        prefs.onChange = { [weak self] in self?.prefsChanged() }
        MicListener.prewarmPermissions()

        panel = NotchPanel()
        let root = IslandView(
            state: state,
            catalog: catalog,
            onTap: { [weak self] in self?.dotTapped() },
            onListen: { },
            onQuit: { NSApp.terminate(nil) }
        )
        let host = HoverHostView(rootView: root)
        host.onHover = { [weak self] inside in self?.hoverChanged(inside) }
        host.onClick = { [weak self] in self?.dotTapped() }
        host.autoresizingMask = [.width, .height]
        panel.contentView = host
        panel.setFrame(idleRect(), display: true)
        panel.orderFrontRegardless()

        islandPanel = NotchPanel()
        let chrome = NSHostingView(
            rootView: IslandChrome(
                state: state,
                catalog: catalog,
                onCancel: { [weak self] in self?.cancelListen() }
            )
        )
        chrome.autoresizingMask = [.width, .height]
        islandPanel.contentView = chrome
        // Stay ordered-front at alpha 0 so the window is already on every
        // space (including a later fullscreen Space). orderOut parks it on
        // the Space where it was created, so the island is missing until
        // you leave the fullscreen app.
        islandPanel.alphaValue = 0
        islandPanel.ignoresMouseEvents = true
        islandPanel.setFrame(islandRect(), display: true)
        islandPanel.orderFrontRegardless()

        installStatusItem()
        installHotKeyHandler()
        registerHotKey()
        startWakeWatch()
        NSWorkspace.shared.notificationCenter.addObserver(
            self,
            selector: #selector(spaceOrScreenChanged),
            name: NSWorkspace.activeSpaceDidChangeNotification,
            object: nil
        )
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(spaceOrScreenChanged),
            name: NSApplication.didChangeScreenParametersNotification,
            object: nil
        )

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            DispatchQueue.main.async {
                self.state.mode = .waking
                self.state.caption = "Waking Laya…"
                self.resize(expand: true, animate: true)
            }
            let ready = Engine.ensureLaya(
                container: self.catalog.container,
                layaContainer: self.catalog.laya_container ?? "laya-upstream"
            )
            if ready {
                _ = Engine.remoteDecide(text: "open notes", catalog: self.catalog)
            }
            DispatchQueue.main.async {
                if ready {
                    self.state.mode = .ok
                    self.state.caption = self.listenHint()
                    self.collapseSoon(after: 2.4)
                } else {
                    self.state.mode = .fail
                    self.state.caption = "Start Docker Desktop"
                }
            }
        }
    }

    func listenHint() -> String {
        var parts: [String] = []
        if prefs.clickEnabled { parts.append("Click") }
        if prefs.hotkeyEnabled { parts.append(prefs.hotkeyLabel) }
        if prefs.wakeEnabled { parts.append(prefs.wakePhrases.first ?? "Hey Mac") }
        if prefs.hoverEnabled { parts.append("hover") }
        return parts.isEmpty ? "Listening off" : parts.joined(separator: ", ")
    }

    func speechBias() -> [String] {
        var seen = Set<String>()
        var out: [String] = []
        if prefs.wakeEnabled {
            for form in prefs.wakeContextual {
                let phrase = form.trimmingCharacters(in: .whitespacesAndNewlines)
                guard phrase.count >= 3, phrase.count <= 32 else { continue }
                let key = phrase.lowercased()
                guard !seen.contains(key) else { continue }
                seen.insert(key)
                out.append(phrase)
            }
        }
        for phrase in Engine.speechPhrases(from: catalog) {
            let key = phrase.lowercased()
            guard !seen.contains(key) else { continue }
            seen.insert(key)
            out.append(phrase)
        }
        return Array(out.prefix(100))
    }

    func configureSpeech() {
        let phrases = speechBias()
        let prefer: ([String]) -> String = { [weak self] texts in
            guard let self else { return texts.first ?? "" }
            return Engine.preferCatalog(texts, catalog: self.catalog)
        }
        let named: (String) -> Bool = { [weak self] text in
            guard let self else { return false }
            let command = self.commandText(text)
            if command.isEmpty { return false }
            // Short hold only after a closed list ("open A and B").
            // Bare names ("Calculator") and mid-list stay on the long hold.
            guard SettingsLogic.listenHoldNamed(command) else { return false }
            return !Engine.namedApps(
                in: command,
                catalog: self.catalog,
                browser: self.browser
            ).isEmpty
        }
        listener.configure(phrases: phrases, prefer: prefer, named: named)
        wakeListener.configure(
            phrases: phrases,
            prefer: prefer,
            named: { [weak self] text in
                guard let self else { return false }
                let (hit, rest) = SettingsLogic.matchWake(text, phrases: self.prefs.wakePhrases)
                // Short silence only after a *closed* list that is not
                // still growing a system command. A first name, mid-list,
                // or "increase volume" must keep the 1.6s hold.
                return hit
                    && SettingsLogic.listenHoldNamed(rest)
                    && !Engine.looksSystemish(rest)
            }
        )
    }

    func prefsChanged() {
        configureSpeech()
        registerHotKey()
        hoverWork?.cancel()
        hoverWork = nil
        if !prefs.micNeeded {
            wakeRestart?.cancel()
            wakeRestart = nil
            wakeListener.abort()
        }
        if !prefs.listeningEnabled, state.busy || state.mode == .listening {
            cancelListen()
        } else if prefs.micNeeded {
            scheduleWakeWatch()
        }
    }

    func startWakeWatch() {
        guard prefs.micNeeded else { return }
        guard !state.busy else { return }
        guard !wakeListener.isActive else { return }
        wakeFirstHeard = nil
        wakeListener.listen(
            timeout: 20,
            partial: { [weak self] text in self?.considerWake(text) },
            completion: { [weak self] text in
                self?.considerWake(text, final: true)
                self?.scheduleWakeWatch()
            }
        )
    }

    func scheduleWakeWatch() {
        wakeRestart?.cancel()
        let work = DispatchWorkItem { [weak self] in
            self?.wakeRestart = nil
            self?.startWakeWatch()
        }
        wakeRestart = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25, execute: work)
    }

    func considerWake(_ text: String, final: Bool = false) {
        guard prefs.micNeeded else { return }
        guard !state.busy else { return }
        let (hit, rest) = SettingsLogic.matchWake(text, phrases: prefs.wakePhrases)
        if hit, wakeFirstHeard == nil {
            wakeFirstHeard = Date()
            // Island up immediately so "Hey Mac" feels instant, but keep
            // this same recognition session open for the command.
            previewWake(rest)
        }
        let elapsed = wakeFirstHeard.map { Date().timeIntervalSince($0) } ?? 0
        let commit = SettingsLogic.wakeCommit(text, phrases: prefs.wakePhrases, elapsed: elapsed, final: final)
        switch commit {
        case .ignore:
            return
        case .hold:
            previewWake(rest)
            if final, rest.isEmpty {
                wakeListener.abort()
                startListen()
            }
        case .go(let remainder):
            wakeListener.abort()
            beginSeeded(remainder)
        case .listen:
            wakeListener.abort()
            startListen()
        }
    }

    func previewWake(_ remainder: String) {
        state.mode = .listening
        state.caption = remainder
        resize(expand: true, animate: false)
    }

    func beginSeeded(_ text: String) {
        guard prefs.listeningEnabled, !state.busy else { return }
        listenGeneration += 1
        openedThisListen.removeAll()
        actedThisListen.removeAll()
        pendingConfirm = []
        speculativeText = ""
        speculativeBusy = false
        listenStarted = Date()
        state.openedIds = []
        state.resultVerb = "Opened"
        hoverArmed = SettingsLogic.hoverApply(event: "start", armed: hoverArmed).0
        state.busy = true
        state.mode = .listening
        state.caption = text
        resize(expand: true, animate: false)
        considerPartial(text)
        heard(text)
    }

    func toggleListen() {
        guard prefs.listeningEnabled, prefs.hotkeyEnabled else { return }
        if state.busy || state.mode == .listening {
            cancelListen()
            return
        }
        startListen()
    }

    func cancelListen() {
        listenGeneration += 1
        hoverWork?.cancel()
        hoverWork = nil
        listener.abort()
        speculativeBusy = false
        speculativeText = ""
        openedThisListen.removeAll()
        actedThisListen.removeAll()
        pendingConfirm = []
        state.busy = false
        state.mode = .idle
        state.caption = ""
        state.openedIds = []
        state.resultVerb = "Opened"
        resize(expand: false, animate: false)
        syncHoverArmFromMouse()
        scheduleWakeWatch()
    }

    func startListen() {
        guard prefs.listeningEnabled else { return }
        guard !state.busy else { return }
        beginMic()
    }

    func startListenFromClick() {
        guard prefs.clickEnabled else { return }
        startListen()
    }

    // Tap on the collapsed purple dot. Taps inside the hover panel are handled
    // by its buttons, so ignore the background gesture there.
    func dotTapped() {
        guard prefs.clickEnabled else { return }
        if state.busy || state.mode == .listening {
            cancelListen()
            return
        }
        startListen()
    }

    // Hover must dwell 500ms on the notch before listen starts.
    // Leaving early cancels. After a listen, the cursor must leave the
    // notch before hover can start another — a parked mouse must not loop.
    // Click and ⌃⌥Space stay immediate.
    func hoverChanged(_ inside: Bool) {
        hoverWork?.cancel()
        hoverWork = nil
        // Collapse and the expanded island covering the idle strip both
        // fire a fake exit. Ignore it — only a later real leave re-arms.
        if !inside, state.expanded || state.busy { return }
        let event = inside ? "enter" : "exit"
        let (nextArmed, schedule) = SettingsLogic.hoverApply(
            event: event,
            armed: hoverArmed,
            expanded: state.expanded,
            busy: state.busy,
            listeningEnabled: prefs.listeningEnabled,
            hoverEnabled: prefs.hoverEnabled
        )
        hoverArmed = nextArmed
        guard schedule else { return }
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            self.hoverWork = nil
            let (_, still) = SettingsLogic.hoverApply(
                event: "enter",
                armed: self.hoverArmed,
                expanded: self.state.expanded,
                busy: self.state.busy,
                listeningEnabled: self.prefs.listeningEnabled,
                hoverEnabled: self.prefs.hoverEnabled
            )
            guard still else { return }
            self.startListen()
        }
        hoverWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + prefs.hoverDwell, execute: work)
    }

    var openedThisListen: Set<String> = []
    var actedThisListen: Set<String> = []
    var pendingConfirm: [String] = []
    var speculativeText = ""
    var speculativeBusy = false
    var listenStarted = Date()
    var hoverWork: DispatchWorkItem?
    var listenGeneration = 0
    var hoverArmed = true

    func beginMic() {
        wakeRestart?.cancel()
        wakeRestart = nil
        wakeListener.abort()
        listenGeneration += 1
        let generation = listenGeneration
        openedThisListen.removeAll()
        actedThisListen.removeAll()
        pendingConfirm = []
        speculativeText = ""
        speculativeBusy = false
        listenStarted = Date()
        state.openedIds = []
        state.resultVerb = "Opened"
        hoverArmed = SettingsLogic.hoverApply(event: "start", armed: hoverArmed).0
        state.busy = true
        state.mode = .listening
        state.caption = ""
        resize(expand: true, animate: false)
        listener.listen(partial: { [weak self] text in
            guard let self, self.listenGeneration == generation else { return }
            let uttered = text.trimmingCharacters(in: .whitespacesAndNewlines)
            self.state.caption = uttered
            self.considerPartial(text)
        }, completion: { [weak self] text in
            guard let self, self.listenGeneration == generation else { return }
            self.heard(text)
        })
    }

    func commandText(_ text: String) -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard prefs.wakeEnabled else { return trimmed }
        return SettingsLogic.stripWake(trimmed, phrases: prefs.wakePhrases)
    }

    func considerPartial(_ text: String) {
        let uttered = commandText(text)
        guard !uttered.isEmpty, uttered != speculativeText else { return }
        speculativeText = uttered
        if Engine.isStop(uttered) { return }
        if Engine.negation.contains(where: { Engine.wordMatch($0, in: uttered) }) { return }
        if Engine.lifecycleVerbs.contains(where: { uttered.lowercased().hasPrefix($0) }) { return }
        if Engine.looksLikeURLOpen(uttered) { return }
        // System controls (volume, brightness, lock, ...) wait for the final
        // transcript — never speculative-fire a partial that names one.
        if Engine.looksSystemish(uttered) { return }
        if !pendingConfirm.isEmpty { return }
        let fresh = Engine.newlyNamedApps(
            uttered,
            catalog: catalog,
            browser: browser,
            already: openedThisListen
        )
        guard !fresh.isEmpty, !speculativeBusy else { return }
        speculativeBusy = true
        NSLog("laya-opener partial-fire '%@' +%.0fms", uttered, Date().timeIntervalSince(listenStarted) * 1000)
        decide(uttered, collapse: false) { [weak self] in
            self?.speculativeBusy = false
        }
    }

    func heard(_ text: String) {
        let uttered = commandText(text)
        let heardAt = Date().timeIntervalSince(listenStarted) * 1000
        NSLog("laya-opener heard '%@' +%.0fms", uttered, heardAt)
        guard !uttered.isEmpty else {
            if !openedThisListen.isEmpty || !actedThisListen.isEmpty {
                finishListen(action: "open", line: state.caption)
                return
            }
            state.mode = .fail
            state.caption = "Didn't catch that"
            state.busy = false
            collapseSoon()
            return
        }
        state.mode = .thinking
        state.caption = uttered
        decide(uttered, collapse: true)
    }

    func decide(_ uttered: String, collapse: Bool, done: (() -> Void)? = nil) {
        let generation = listenGeneration
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            let t0 = Date()
            let decision = Engine.handle(
                text: uttered,
                catalog: self.catalog,
                browser: self.browser,
                settings: self.prefs.payload,
                running: Engine.runningIds(in: self.catalog),
                pending: self.pendingConfirm
            )
            let layaMs = Date().timeIntervalSince(t0) * 1000
            let line = Engine.spoken(decision, catalog: self.catalog)
            NSLog("laya-opener decide '%@' %.0fms -> %@ %@", uttered, layaMs, decision.action, decision.app ?? "-")
            DispatchQueue.main.async {
                guard self.listenGeneration == generation else {
                    done?()
                    return
                }
                self.apply(decision, line: line, collapse: collapse)
                done?()
            }
        }
    }

    func apply(_ decision: Decision, line: String, collapse: Bool) {
        let ids = decision.apps.isEmpty ? [decision.app].compactMap { $0 } : decision.apps
        switch decision.action {
        case "open_url":
            pendingConfirm = []
            if let raw = decision.url, !raw.isEmpty {
                Engine.openURL(raw, inApp: decision.app, catalog: catalog)
                if let app = decision.app, catalog.apps[app] != nil {
                    openedThisListen.insert(app)
                    if !state.openedIds.contains(app) {
                        state.openedIds.append(app)
                    }
                }
                NSLog("laya-opener open_url %@ in %@", raw, decision.app ?? "-")
            }
        case "open":
            pendingConfirm = []
            for app in ids where catalog.apps[app] != nil && !openedThisListen.contains(app) {
                let t0 = Date()
                Engine.openApp(app, catalog: catalog)
                openedThisListen.insert(app)
                if !state.openedIds.contains(app) {
                    state.openedIds.append(app)
                }
                NSLog(
                    "laya-opener open %@ %.0fms (+%.0fms from listen)",
                    app,
                    Date().timeIntervalSince(t0) * 1000,
                    Date().timeIntervalSince(listenStarted) * 1000
                )
            }
        case "close":
            for app in ids where catalog.apps[app] != nil && !actedThisListen.contains(app) {
                Engine.closeWindows(app, catalog: catalog)
                actedThisListen.insert(app)
                if !state.openedIds.contains(app) {
                    state.openedIds.append(app)
                }
                NSLog("laya-opener close %@", app)
            }
            pendingConfirm = decision.pending
        case "quit":
            for app in ids where catalog.apps[app] != nil && !actedThisListen.contains(app) {
                Engine.quitApp(app, catalog: catalog, force: false)
                actedThisListen.insert(app)
                if !state.openedIds.contains(app) {
                    state.openedIds.append(app)
                }
                NSLog("laya-opener quit %@", app)
            }
            pendingConfirm = decision.pending
        case "kill":
            for app in ids where catalog.apps[app] != nil && !actedThisListen.contains(app) {
                Engine.quitApp(app, catalog: catalog, force: true)
                actedThisListen.insert(app)
                if !state.openedIds.contains(app) {
                    state.openedIds.append(app)
                }
                NSLog("laya-opener kill %@", app)
            }
            pendingConfirm = decision.pending
        case "confirm":
            pendingConfirm = decision.pending.isEmpty ? ids : decision.pending
        case "refuse":
            pendingConfirm = []
        case "system":
            pendingConfirm = []
        default:
            break
        }
        // System commands execute for real on this Mac; the caption reports
        // what actually happened (true levels, battery, failures) rather than
        // the Python-side label line.
        var line = line
        if !decision.system.isEmpty {
            let results = decision.system.map { Engine.runSystem($0) }.filter { !$0.isEmpty }
            if !results.isEmpty {
                let sysLine = results.joined(separator: " ")
                line = (decision.action == "system" || line.isEmpty) ? sysLine : line + " " + sysLine
            }
        }
        if decision.action == "confirm" || (!decision.pending.isEmpty && ["close", "quit", "kill"].contains(decision.action)) {
            state.caption = line
            state.mode = .listening
            state.busy = true
            if !listener.isActive {
                continueForConfirm()
            }
            return
        }
        guard collapse else {
            if ["open", "open_url", "close", "quit", "kill", "system"].contains(decision.action) {
                state.caption = line
            }
            return
        }
        finishListen(action: decision.action, line: line)
    }

    func continueForConfirm() {
        // Keep listenGeneration so a still-in-flight heard() is not discarded.
        let generation = listenGeneration
        speculativeText = ""
        speculativeBusy = false
        listenStarted = Date()
        state.busy = true
        state.mode = .listening
        resize(expand: true, animate: false)
        listener.listen(partial: { [weak self] text in
            guard let self, self.listenGeneration == generation else { return }
            self.state.caption = text.trimmingCharacters(in: .whitespacesAndNewlines)
        }, completion: { [weak self] text in
            guard let self, self.listenGeneration == generation else { return }
            self.heard(text)
        })
    }

    static func verbLabel(_ action: String) -> String {
        switch action {
        case "close": return "Closed"
        case "quit": return "Quit"
        case "kill": return "Force quit"
        case "stop": return "Bye"
        case "system": return "Done"
        default: return "Opened"
        }
    }

    func finishListen(action: String, line: String) {
        let succeeded = ["open", "close", "quit", "kill", "stop", "system"].contains(action)
            || !openedThisListen.isEmpty
            || !actedThisListen.isEmpty
        state.busy = false
        state.caption = line
        state.resultVerb = Self.verbLabel(action)
        state.mode = succeeded ? .ok : .fail
        if action == "chat", openedThisListen.isEmpty, actedThisListen.isEmpty {
            state.mode = .idle
        }
        if action == "stop" {
            collapseSoon(after: 0.8, thenQuit: true)
        } else {
            let quick = succeeded && action != "refuse"
            collapseSoon(after: quick ? 0.9 : 1.4)
        }
    }

    func collapseSoon(after: TimeInterval = 1.6, thenQuit: Bool = false) {
        let generation = listenGeneration
        DispatchQueue.main.asyncAfter(deadline: .now() + after) { [weak self] in
            guard let self, self.listenGeneration == generation else { return }
            self.state.mode = .idle
            self.state.caption = ""
            self.state.openedIds = []
            self.state.resultVerb = "Opened"
            self.pendingConfirm = []
            self.resize(expand: false, animate: false)
            self.syncHoverArmFromMouse()
            if thenQuit {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                    NSApp.terminate(nil)
                }
            } else {
                self.scheduleWakeWatch()
            }
        }
    }

    func syncHoverArmFromMouse() {
        hoverArmed = SettingsLogic.hoverApply(event: "collapse", armed: hoverArmed).0
    }

    struct NotchGeom {
        var frame: CGRect
        var height: CGFloat
        var notchMinX: CGFloat
        var notchMaxX: CGFloat
    }

    func menuBarHeight(on screen: NSScreen) -> CGFloat {
        var height = screen.safeAreaInsets.top
        if height < 1 {
            height = screen.frame.maxY - screen.visibleFrame.maxY
        }
        return max(height, 24)
    }

    func notchGeom() -> NotchGeom {
        let screen = NSScreen.main ?? NSScreen.screens[0]
        let frame = screen.frame
        let height = menuBarHeight(on: screen)
        var notchMinX = frame.midX - 96
        var notchMaxX = frame.midX + 96
        if let left = screen.auxiliaryTopLeftArea, let right = screen.auxiliaryTopRightArea {
            notchMinX = left.maxX
            notchMaxX = right.minX
        }
        return NotchGeom(frame: frame, height: height, notchMinX: notchMinX, notchMaxX: notchMaxX)
    }

    // Collapsed hit window: full notch strip plus a sliver left of the housing so
    // the 8px indicator is visible and hover/click anywhere on the notch works.
    // The window itself is transparent; only the purple circle draws.
    func idleRect() -> CGRect {
        let g = notchGeom()
        let leftPad: CGFloat = 16
        let x = g.notchMinX - leftPad
        let width = max(g.notchMaxX - x, 40)
        return CGRect(x: x, y: g.frame.maxY - g.height, width: width, height: g.height)
    }



    // Black island hanging from the camera housing. The top `g.height` sits
    // under the bezel (hidden); all content lives in the visible drop below.
    func islandRect() -> CGRect {
        let g = notchGeom()
        let notchW = g.notchMaxX - g.notchMinX
        let width = max(notchW + 168, 372)
        let drop: CGFloat = 56
        let height = g.height + drop
        return CGRect(
            x: g.frame.midX - width / 2,
            y: g.frame.maxY - height,
            width: width,
            height: height
        )
    }

    func relayout(animate: Bool) {
        // Idle window never moves — purple-dot + hover target.
        // Island stays ordered-front at all times so it already lives on
        // every Space (including a later fullscreen Space). Hide with
        // alpha, not orderOut — orderOut parks the window on the Space
        // where it was last shown.
        let overlay = NSWindow.Level(rawValue: NSWindow.Level.screenSaver.rawValue + 1)
        panel.level = overlay
        panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary, .ignoresCycle]
        panel.setFrame(idleRect(), display: true)
        panel.orderFrontRegardless()
        islandPanel.level = overlay
        islandPanel.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary, .ignoresCycle]
        islandPanel.setFrame(islandRect(), display: true)
        islandPanel.alphaValue = state.expanded ? 1 : 0
        islandPanel.ignoresMouseEvents = !state.expanded
        islandPanel.orderFrontRegardless()
    }

    func resize(expand: Bool, animate: Bool) {
        state.expanded = expand
        relayout(animate: animate)
    }

    func installStatusItem() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = item.button {
            button.image = NSImage(
                systemSymbolName: "waveform",
                accessibilityDescription: "Sayso"
            )
            button.action = #selector(statusClicked)
            button.target = self
        }
        item.menu = nil
        status = item
        item.button?.sendAction(on: [.leftMouseUp, .rightMouseUp])
    }

    func statusMenu() -> NSMenu {
        let menu = NSMenu()
        let listen = NSMenuItem(
            title: "Listen  \(prefs.hotkeyLabel)",
            action: #selector(forceListen),
            keyEquivalent: ""
        )
        listen.isEnabled = prefs.listeningEnabled
        menu.addItem(listen)
        menu.addItem(NSMenuItem(title: "Settings…", action: #selector(openSettings), keyEquivalent: ","))
        let listening = NSMenuItem(
            title: prefs.listeningEnabled ? "Turn Listening Off" : "Turn Listening On",
            action: #selector(toggleListeningPref),
            keyEquivalent: ""
        )
        menu.addItem(listening)
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "Quit", action: #selector(quit), keyEquivalent: "q"))
        return menu
    }

    @objc func statusClicked() {
        let event = NSApp.currentEvent
        if event?.type == .rightMouseUp {
            status?.menu = statusMenu()
            status?.button?.performClick(nil)
            status?.menu = nil
            return
        }
        startListenFromClick()
    }

    @objc func forceListen() { startListen() }
    @objc func quit() { NSApp.terminate(nil) }

    @objc func toggleListeningPref() {
        prefs.listeningEnabled.toggle()
    }

    @objc func openSettings() {
        if let window = settingsWindow {
            presentSettings(window)
            return
        }
        let root = SettingsRoot(prefs: prefs, onQuit: { [weak self] in self?.quit() })
        let host = NSHostingController(rootView: root)
        let window = NSWindow(contentViewController: host)
        window.title = "Sayso"
        window.styleMask = [.titled, .closable, .miniaturizable]
        window.setContentSize(NSSize(width: 440, height: 680))
        window.center()
        window.isReleasedWhenClosed = false
        window.delegate = self
        settingsWindow = window
        presentSettings(window)
    }

    func presentSettings(_ window: NSWindow) {
        NSApp.setActivationPolicy(.regular)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func spaceOrScreenChanged() {
        relayout(animate: false)
    }

    func installHotKeyHandler() {
        guard eventHandler == nil else { return }
        var eventType = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        let userData = Unmanaged.passUnretained(self).toOpaque()
        InstallEventHandler(
            GetEventDispatcherTarget(),
            { _, _, userData -> OSStatus in
                guard let userData else { return noErr }
                let app = Unmanaged<AppDelegate>.fromOpaque(userData).takeUnretainedValue()
                DispatchQueue.main.async { app.toggleListen() }
                return noErr
            },
            1,
            &eventType,
            userData,
            &eventHandler
        )
    }

    func unregisterHotKey() {
        if let hotKeyRef {
            UnregisterEventHotKey(hotKeyRef)
            self.hotKeyRef = nil
        }
    }

    func registerHotKey() {
        unregisterHotKey()
        guard prefs.listeningEnabled, prefs.hotkeyEnabled else { return }
        let hotKeyID = EventHotKeyID(signature: OSType(0x4C59414F), id: 1)
        let status = RegisterEventHotKey(
            prefs.hotkeyCode,
            SettingsLogic.carbonModifiers(prefs.hotkeyModifiers),
            hotKeyID,
            GetEventDispatcherTarget(),
            0,
            &hotKeyRef
        )
        if status != noErr {
            state.caption = "Hotkey busy — use menu bar"
        }
    }
}

extension AppDelegate: NSWindowDelegate {
    func windowWillClose(_ notification: Notification) {
        if notification.object as? NSWindow === settingsWindow {
            NSApp.setActivationPolicy(.accessory)
        }
    }
}

final class NotchPanel: NSPanel {
    init() {
        super.init(
            contentRect: .zero,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        isOpaque = false
        backgroundColor = .clear
        hasShadow = false
        // High enough to sit over a fullscreen Space; fullScreenAuxiliary
        // is what actually lets an accessory panel join that Space.
        level = NSWindow.Level(rawValue: NSWindow.Level.screenSaver.rawValue + 1)
        collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary, .ignoresCycle]
        isMovable = false
        titleVisibility = .hidden
        titlebarAppearsTransparent = true
        hidesOnDeactivate = false
        becomesKeyOnlyIfNeeded = true
        isFloatingPanel = true
        animationBehavior = .none
        acceptsMouseMovedEvents = true
        ignoresMouseEvents = false
    }

    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
}

final class HoverHostView<Content: View>: NSHostingView<Content> {
    var onHover: ((Bool) -> Void)?
    var onClick: (() -> Void)?
    private var tracking: NSTrackingArea?

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let tracking {
            removeTrackingArea(tracking)
        }
        let area = NSTrackingArea(
            rect: bounds,
            options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
            owner: self,
            userInfo: nil
        )
        addTrackingArea(area)
        tracking = area
    }

    override func mouseEntered(with event: NSEvent) {
        onHover?(true)
    }

    override func mouseExited(with event: NSEvent) {
        onHover?(false)
    }

    override func mouseDown(with event: NSEvent) {
        onClick?()
    }

    override func hitTest(_ point: NSPoint) -> NSView? {
        bounds.contains(point) ? self : nil
    }
}

struct IslandView: View {
    @ObservedObject var state: AppState
    var catalog: CatalogFile
    var onTap: () -> Void
    var onListen: () -> Void
    var onQuit: () -> Void

    var body: some View {
        GeometryReader { geo in
            Circle()
                .fill(Color(red: 0.42, green: 0.16, blue: 0.78))
                .frame(width: 8, height: 8)
                .shadow(color: Color(red: 0.42, green: 0.16, blue: 0.78).opacity(0.9), radius: 3, x: 0, y: 0)
                .frame(width: geo.size.width, height: geo.size.height, alignment: .leading)
                .padding(.leading, 4)
                .contentShape(Rectangle())
                .onTapGesture { onTap() }
        }
    }
}

struct IslandChrome: View {
    @ObservedObject var state: AppState
    var catalog: CatalogFile
    var onCancel: () -> Void

    let purple = Color(red: 0.66, green: 0.36, blue: 0.98)

    var body: some View {
        GeometryReader { geo in
            let bezel = max(safeTop(geo), 24)
            ZStack(alignment: .top) {
                IslandShape()
                    .fill(Color.black)
                HStack(spacing: 10) {
                    glyph
                        .frame(width: 28, height: 28)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(eyebrow)
                            .font(.system(size: 10, weight: .semibold, design: .rounded))
                            .foregroundColor(eyebrowColor)
                            .textCase(.uppercase)
                            .tracking(0.7)
                        Text(headline)
                            .font(.system(size: 13, weight: .semibold, design: .rounded))
                            .foregroundColor(Color(white: 0.96))
                            .lineLimit(1)
                    }
                    Spacer(minLength: 8)
                    if showsCancel {
                        Button(action: onCancel) {
                            Text("Cancel")
                                .font(.system(size: 11, weight: .semibold, design: .rounded))
                                .foregroundColor(Color(white: 0.88))
                                .padding(.horizontal, 10)
                                .padding(.vertical, 5)
                                .background(Color.white.opacity(0.12))
                                .clipShape(Capsule())
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 18)
                .padding(.top, bezel + 8)
                .padding(.bottom, 12)
            }
        }
    }

    var showsCancel: Bool {
        state.mode == .listening || state.mode == .thinking
    }

    func safeTop(_ geo: GeometryProxy) -> CGFloat {
        if let screen = NSScreen.main {
            var height = screen.safeAreaInsets.top
            if height < 1 {
                height = screen.frame.maxY - screen.visibleFrame.maxY
            }
            return max(height, 24)
        }
        return 24
    }

    @ViewBuilder
    var glyph: some View {
        switch state.mode {
        case .listening:
            Waveform(active: true, tint: purple)
                .frame(width: 26, height: 20)
        case .ok:
            if let id = state.openedIds.first, let icon = AppGlyph.image(id: id, catalog: catalog) {
                Image(nsImage: icon)
                    .resizable()
                    .interpolation(.high)
                    .frame(width: 24, height: 24)
                    .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
            } else {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundColor(Color(red: 0.49, green: 0.85, blue: 0.54))
            }
        case .fail:
            Image(systemName: "xmark.circle.fill")
                .font(.system(size: 20, weight: .semibold))
                .foregroundColor(Color(red: 0.91, green: 0.42, blue: 0.35))
        case .thinking, .waking:
            ProgressView()
                .controlSize(.small)
                .colorScheme(.dark)
        default:
            Image(systemName: "circle.dotted")
                .font(.system(size: 16, weight: .medium))
                .foregroundColor(Color(white: 0.55))
        }
    }

    var eyebrow: String {
        switch state.mode {
        case .idle: return "Laya"
        case .waking: return "Waking"
        case .listening: return "Listening"
        case .thinking: return "Deciding"
        case .ok: return state.resultVerb
        case .fail: return "Hmm"
        }
    }

    var eyebrowColor: Color {
        switch state.mode {
        case .listening: return purple
        case .ok: return Color(red: 0.49, green: 0.85, blue: 0.54)
        case .fail: return Color(red: 0.91, green: 0.42, blue: 0.35)
        default: return Color(white: 0.55)
        }
    }

    var headline: String {
        if state.mode == .ok, !state.openedIds.isEmpty {
            let names = state.openedIds.map { catalog.apps[$0]?.say ?? $0 }
            if names.count >= 2 {
                return "\(names.dropLast().joined(separator: ", ")) and \(names.last!)"
            }
            return names[0]
        }
        if state.caption.isEmpty {
            switch state.mode {
            case .listening: return "Speak an app name"
            case .waking: return "Waking Laya…"
            default: return "Laya"
            }
        }
        return state.caption
    }
}

struct IslandShape: Shape {
    func path(in rect: CGRect) -> Path {
        let top: CGFloat = 0
        let bottom: CGFloat = 22
        var path = Path()
        path.move(to: CGPoint(x: rect.minX, y: rect.minY + top))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY + top))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY - bottom))
        path.addQuadCurve(
            to: CGPoint(x: rect.maxX - bottom, y: rect.maxY),
            control: CGPoint(x: rect.maxX, y: rect.maxY)
        )
        path.addLine(to: CGPoint(x: rect.minX + bottom, y: rect.maxY))
        path.addQuadCurve(
            to: CGPoint(x: rect.minX, y: rect.maxY - bottom),
            control: CGPoint(x: rect.minX, y: rect.maxY)
        )
        path.closeSubpath()
        return path
    }
}

enum AppGlyph {
    static func image(id: String, catalog: CatalogFile) -> NSImage? {
        guard let spec = catalog.apps[id] else { return nil }
        if let path = spec.paths?.first, FileManager.default.fileExists(atPath: path) {
            return NSWorkspace.shared.icon(forFile: path)
        }
        if let bid = spec.bundle, let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bid) {
            return NSWorkspace.shared.icon(forFile: url.path)
        }
        return nil
    }
}

struct Waveform: View {
    var active: Bool
    var tint: Color

    var body: some View {
        TimelineView(.animation(minimumInterval: 0.08, paused: !active)) { timeline in
            let t = timeline.date.timeIntervalSinceReferenceDate
            HStack(alignment: .center, spacing: 3) {
                ForEach(0 ..< 7, id: \.self) { i in
                    Capsule()
                        .fill(tint)
                        .frame(width: 4, height: bar(i, t))
                }
            }
        }
    }

    func bar(_ i: Int, _ t: TimeInterval) -> CGFloat {
        if !active { return 4 }
        let phase = t * 7 + Double(i) * 0.7
        return 5 + CGFloat((sin(phase) + 1) / 2) * 14
    }
}
