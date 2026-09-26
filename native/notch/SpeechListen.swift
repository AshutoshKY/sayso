import AVFoundation
import Foundation
import Speech

final class MicListener: NSObject {
    private var timeout: TimeInterval
    private let silence: TimeInterval
    private var engine: AVAudioEngine?
    private var recognizer: SFSpeechRecognizer?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var best = ""
    private var lastSpeech = Date()
    private var heard = false
    private var finished = false
    private var ending = false
    private var watchdog: Timer?
    private var onDone: ((String) -> Void)?
    private var onPartial: ((String) -> Void)?
    private var authorized = false
    private var tapped = false
    private var contextual: [String] = []
    private var prefer: (([String]) -> String)?
    private var named: ((String) -> Bool)?
    private let unknownHold: TimeInterval
    private var session = 0

    init(timeout: TimeInterval = 12, silence: TimeInterval = 0.45) {
        self.timeout = timeout
        self.silence = silence
        // Mid-list / unnamed hold. 0.75s was still cutting mid-sentence
        // when Apple emitted a lone name ("Calculator") and the speaker
        // paused a beat before the next one.
        self.unknownHold = max(silence, 1.6)
    }

    func configure(
        phrases: [String] = [],
        prefer: (([String]) -> String)? = nil,
        named: ((String) -> Bool)? = nil
    ) {
        contextual = phrases
        self.prefer = prefer
        self.named = named
    }

    static func prewarmPermissions() {
        switch SFSpeechRecognizer.authorizationStatus() {
        case .notDetermined:
            SFSpeechRecognizer.requestAuthorization { _ in
                DispatchQueue.main.async { prewarmMic() }
            }
        default:
            prewarmMic()
        }
    }

    private static func prewarmMic() {
        if AVCaptureDevice.authorizationStatus(for: .audio) == .notDetermined {
            AVCaptureDevice.requestAccess(for: .audio) { _ in }
        }
    }

    var isActive: Bool { !finished && onDone != nil }

    func listen(
        timeout: TimeInterval? = nil,
        partial: ((String) -> Void)? = nil,
        completion: @escaping (String) -> Void
    ) {
        if let timeout { self.timeout = timeout }
        session += 1
        onPartial = partial
        onDone = completion
        best = ""
        heard = false
        finished = false
        ending = false
        lastSpeech = Date()
        let current = session
        switch SFSpeechRecognizer.authorizationStatus() {
        case .authorized:
            askMic()
        case .notDetermined:
            SFSpeechRecognizer.requestAuthorization { [weak self] status in
                DispatchQueue.main.async {
                    guard let self, self.session == current else { return }
                    guard status == .authorized else {
                        self.finish("")
                        return
                    }
                    self.askMic()
                }
            }
        default:
            finish("")
        }
    }

    func cancel() {
        finish(best)
    }

    /// Stop the mic and drop callbacks. Does not deliver a transcript.
    func abort() {
        session += 1
        onDone = nil
        onPartial = nil
        finished = true
        ending = true
        teardownEngine()
    }

    private func askMic() {
        let current = session
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            authorized = true
            begin()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .audio) { [weak self] ok in
                DispatchQueue.main.async {
                    guard let self, self.session == current else { return }
                    guard ok else {
                        self.finish("")
                        return
                    }
                    self.authorized = true
                    self.begin()
                }
            }
        default:
            finish("")
        }
    }

    private func teardownEngine() {
        watchdog?.invalidate()
        watchdog = nil
        task?.cancel()
        task = nil
        if let engine {
            if engine.isRunning {
                engine.stop()
            }
            if tapped {
                _ = LayaTry({ engine.inputNode.removeTap(onBus: 0) }, nil)
                tapped = false
            }
        }
        engine = nil
        request = nil
    }

    private func begin() {
        let current = session
        teardownEngine()
        guard session == current else { return }
        finished = false
        ending = false
        let locale = Locale(identifier: "en-US")
        guard let recognizer = SFSpeechRecognizer(locale: locale), recognizer.isAvailable else {
            finish("")
            return
        }
        recognizer.defaultTaskHint = .search
        self.recognizer = recognizer
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        request.addsPunctuation = false
        request.requiresOnDeviceRecognition = false
        request.taskHint = .search
        if !contextual.isEmpty {
            request.contextualStrings = Array(contextual.prefix(100))
        }
        self.request = request

        let engine = AVAudioEngine()
        self.engine = engine
        let input = engine.inputNode
        var tapError: NSError?
        let tappedOk = LayaTry({
            input.installTap(onBus: 0, bufferSize: 2048, format: nil) { buffer, _ in
                request.append(buffer)
            }
        }, &tapError)
        guard tappedOk else {
            finish("")
            return
        }
        tapped = true

        lastSpeech = Date()
        task = recognizer.recognitionTask(with: request) { [weak self] result, error in
            guard let self, !self.finished, self.session == current else { return }
            if let result {
                let text = self.pick(from: result)
                if !text.isEmpty {
                    let changed = text != self.best
                    self.best = text
                    self.heard = true
                    if changed {
                        self.lastSpeech = Date()
                    }
                    let partial = self.onPartial
                    DispatchQueue.main.async { partial?(text) }
                }
                if result.isFinal {
                    self.finish(self.best)
                    return
                }
            }
            if error != nil {
                self.finish(self.best)
            }
        }

        do {
            try engine.start()
        } catch {
            finish("")
            return
        }

        watchdog = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            guard let self, self.session == current else { return }
            self.tick()
        }
    }

    private func hold() -> TimeInterval {
        if named?(best) == true { return silence }
        return unknownHold
    }

    private func pick(from result: SFSpeechRecognitionResult) -> String {
        var texts: [String] = []
        var seen = Set<String>()
        func add(_ raw: String) {
            let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else { return }
            let key = text.lowercased()
            guard !seen.contains(key) else { return }
            seen.insert(key)
            texts.append(text)
        }
        add(result.bestTranscription.formattedString)
        for transcription in result.transcriptions {
            add(transcription.formattedString)
            let ns = transcription.formattedString as NSString
            for segment in transcription.segments {
                for alt in segment.alternativeSubstrings {
                    add(ns.replacingCharacters(in: segment.substringRange, with: alt))
                }
            }
        }
        if let prefer {
            return prefer(texts)
        }
        return texts.first ?? ""
    }

    private func tick() {
        guard !finished, !ending else { return }
        let now = Date()
        if heard && now.timeIntervalSince(lastSpeech) >= hold() {
            endAudioAndWait()
            return
        }
        if now.timeIntervalSince(lastSpeech) >= timeout {
            if heard {
                endAudioAndWait()
            } else {
                finish("")
            }
        }
    }

    private func endAudioAndWait() {
        guard !ending, !finished else { return }
        ending = true
        request?.endAudio()
        if let engine, engine.isRunning {
            engine.stop()
        }
        finish(best)
    }

    private func finish(_ text: String) {
        guard !finished else { return }
        finished = true
        teardownEngine()
        let callback = onDone
        onDone = nil
        onPartial = nil
        DispatchQueue.main.async {
            callback?(text)
        }
    }
}
