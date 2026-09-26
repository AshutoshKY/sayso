import AVFoundation
import Foundation
import Speech

/// One-shot mic listener. Prints the transcript to stdout and exits.
/// Prefers on-device recognition; falls back to Apple dictation if needed.
@main
enum ListenOnce {
    static func main() {
        let timeout = TimeInterval(ProcessInfo.processInfo.environment["LISTEN_TIMEOUT"] ?? "8") ?? 8
        let silence = TimeInterval(ProcessInfo.processInfo.environment["LISTEN_SILENCE"] ?? "1.2") ?? 1.2
        let runner = Runner(timeout: timeout, silence: silence)
        runner.start()
        RunLoop.main.run()
    }
}

final class Runner: NSObject {
    let timeout: TimeInterval
    let silence: TimeInterval
    let engine = AVAudioEngine()
    var recognizer: SFSpeechRecognizer?
    var request: SFSpeechAudioBufferRecognitionRequest?
    var task: SFSpeechRecognitionTask?
    var best = ""
    var lastSpeech = Date()
    var heard = false
    var finished = false
    var watchdog: Timer?

    init(timeout: TimeInterval, silence: TimeInterval) {
        self.timeout = timeout
        self.silence = silence
    }

    func start() {
        SFSpeechRecognizer.requestAuthorization { status in
            DispatchQueue.main.async {
                guard status == .authorized else {
                    self.fail("speech authorization: \(status.rawValue)")
                    return
                }
                self.askMic()
            }
        }
    }

    func askMic() {
        AVCaptureDevice.requestAccess(for: .audio) { ok in
            DispatchQueue.main.async {
                guard ok else {
                    self.fail("microphone denied")
                    return
                }
                self.begin()
            }
        }
    }

    func begin() {
        let locale = Locale(identifier: "en-US")
        guard let recognizer = SFSpeechRecognizer(locale: locale), recognizer.isAvailable else {
            fail("speech recognizer unavailable")
            return
        }
        self.recognizer = recognizer
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        if recognizer.supportsOnDeviceRecognition {
            request.requiresOnDeviceRecognition = true
        }
        self.request = request

        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else {
            fail("no input format")
            return
        }
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            request.append(buffer)
        }

        lastSpeech = Date()
        task = recognizer.recognitionTask(with: request) { [weak self] result, error in
            guard let self, !self.finished else { return }
            if let result {
                let text = result.bestTranscription.formattedString.trimmingCharacters(in: .whitespacesAndNewlines)
                if !text.isEmpty {
                    self.best = text
                    self.heard = true
                    self.lastSpeech = Date()
                }
                if result.isFinal {
                    self.finish()
                    return
                }
            }
            if error != nil {
                self.finish()
            }
        }

        do {
            try engine.start()
        } catch {
            fail("engine: \(error.localizedDescription)")
            return
        }

        watchdog = Timer.scheduledTimer(withTimeInterval: 0.15, repeats: true) { [weak self] _ in
            self?.tick()
        }
    }

    func tick() {
        let now = Date()
        if heard && now.timeIntervalSince(lastSpeech) >= silence {
            finish()
            return
        }
        if now.timeIntervalSince(lastSpeech) >= timeout {
            finish()
        }
    }

    func finish() {
        guard !finished else { return }
        finished = true
        watchdog?.invalidate()
        request?.endAudio()
        task?.cancel()
        engine.stop()
        engine.inputNode.removeTap(onBus: 0)
        FileHandle.standardOutput.write((best + "\n").data(using: .utf8)!)
        exit(best.isEmpty ? 2 : 0)
    }

    func fail(_ message: String) {
        FileHandle.standardError.write(("listen: \(message)\n").data(using: .utf8)!)
        exit(1)
    }
}
