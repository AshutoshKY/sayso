<p align="center">
  <img src="docs/images/icon.png" alt="Sayso App Icon" width="120" height="120">
</p>

# Sayso

Speak at the Mac notch. The named app opens — and the Mac itself obeys: volume, brightness, dark mode, lock, battery, AirDrop.

<p align="center">
  <img src="https://github.com/user-attachments/assets/dbc060cc-c95d-4a75-a530-bd5b26a18cd3"
 alt="Sayso — the real notch island after saying 'open notes': Notes app icon, OPENED, Notes" width="840">
</p>

Hover the purple dot, press **⌃⌥Space**, or say **Hey Mac**. A black island drops. You talk. Laya — running **on this Mac, in Docker, no internet** — picks the installed app. Sayso opens it, closes its windows, or quits it.

<p align="center">
  <img src="docs/images/states.png" alt="The three real states — Idle: purple dot by the notch. Listening: live EQ and transcript with Cancel. Opened: the app launches in about 1.4 s." width="840">
</p>

*Both images show real captures of the live island — no mockups.*

> **No cloud LLM.** Not ChatGPT. Not Claude. Not Gemini. Speech is Apple Speech. The decision is Laya System-1 on CPU. Once the image is loaded, the stack is offline.

```
You  →  notch island  →  POST :8010/decide     (laya-opener, this repo)
                              │
               ┌──────────────┴──────────────┐
               ▼                             ▼
       [host-parsed system]        POST :8001/v1/systemone (laya-upstream)
         (~3 ms, skips Laya)                 │
               │                             ▼
               │                    installed app prediction /
               │                    system-control paraphrase
               └──────────────┬──────────────┘
                              ▼
            open / close / quit / kill / volume / brightness /
            dark mode / lock / battery / wifi / bluetooth / airdrop
```

| | |
|---|---|
| **~250 ms** | named-app decide (p50, 5-way head) |
| **~400 ms** | paraphrase decide (daily 15-way set) |
| **33–53 ms** | app launch (`NSWorkspace`) |
| **~3 ms** | system-command decide (host parse, no Laya call) |
| **241** | unit tests |
| **0** | cloud LLM calls |
| **macOS 14+** | Apple Silicon |
| **Python + Swift** | decide API in Docker · island on the host |

| You say | What happens |
|---|---|
| *open notes* | Opens Notes |
| *jot something down* | Opens Notes (paraphrase) |
| *open anti gravity* | Opens Antigravity |
| *open her mess* / *open hermits* | Opens Hermes (Apple misheard; we still got it) |
| *open podcast and notes* | Opens both, as each name lands |
| *hey mac open notes and safari* | Same — wake word + a list in one breath |
| *open youtube in brave* | YouTube in Brave — not “some browser” |
| *open clipboard* | Opens whatever you just copied |
| *close brave* | Closes the windows; Brave stays running |
| *close notes* (not running) | “Notes isn't open. Open it?” — *yes* opens it |
| *quit brave* / *kill brave* | Quits or force-quits |
| *hello* / unknown name | Opens **nothing** |
| *goodbye* | Island says goodbye and Sayso quits |
| *increase volume by 2* | Volume up 20% (steps are 10%; *by 2 percent* = 2%) |
| *volume up* / *mute* / *set volume to 50* | Does what it says — CoreAudio, works on HDMI outputs |
| *make the screen brighter* / *dim the screen* | Brightness ∓10%; *increase brightness by 3* = +30% |
| *turn on dark mode* / *light mode* | System appearance flips (one-time Automation consent) |
| *night mode on* | Night Shift on |
| *lock screen* | Locks the Mac (synthetic ⌃⌘Q) |
| *battery percentage* | Island says e.g. “Battery 100%, plugged in.” |
| *open wifi settings* / *open bluetooth settings* | That System Settings pane opens |
| *turn off airdrop* | AirDrop off (*airdrop everyone* turns it back on) |
| *open notes and increase volume by 2* | Both — mixed app + system commands compose |
| *hey mac increase volume by 2* | Wake + system — volume up 20% |
| *hey mac mute* / *hey mac lock screen* / *hey mac turn on dark mode* | Wake + that system command |
| *hey mac open notes and increase volume by 2* | Wake + mixed — Notes opens and volume goes up 20% |

Unknown name → nothing. No silent fallthrough to Chrome or Calendar. System captions report the real outcome — *“Volume 70%”*, *“Battery 100%, plugged in”* — never just your words echoed back.

## Architecture

```mermaid
flowchart LR
  subgraph macHost["Mac host"]
    User["You"]
    Mic["Mic"]
    Notch["Sayso.app<br/>notch island + menu bar"]
    Speech["Apple Speech"]
    Scan["Catalog scan"]
    Executors["Executors<br/>NSWorkspace · AX · CoreAudio<br/>DisplayServices · HID · AppleScript"]
  end

  subgraph docker["Docker"]
    Opener["laya-opener :8010<br/>Python decide API<br/>host system parser + policy"]
    Laya["laya-upstream :8001<br/>Laya english, CPU"]
  end

  User -->|click / hover / ⌃⌥Space / Hey Mac| Notch
  User --> Mic
  Mic --> Speech
  Speech -->|partial + final transcript| Notch
  Scan --> Notch
  Notch -->|POST /decide + catalog + running| Opener
  Opener -.->|app prediction or paraphrase| Laya
  Laya -.->|choice + probabilities| Opener
  Opener -->|action + apps + system + timing| Notch
  Notch --> Executors
```

| Process | Where | Port | Job |
|---|---|---|---|
| `Sayso.app` | `~/Applications/Sayso.app` | — | Notch UI, mic, Apple Speech, catalog scan, app execution & native system controls |
| `laya-opener` | Docker, **this repo** | `127.0.0.1:8010` | Decide API. System command parsing (~3 ms), Laya prompt builder, policy, alias recovery |
| `laya-upstream` | Docker, **separate image** | `127.0.0.1:8001` | Laya System-1 English checkpoint on CPU |

```mermaid
sequenceDiagram
  actor You
  participant Island as Notch island
  participant Speech as Apple Speech
  participant Opener as laya-opener :8010
  participant Laya as laya-upstream :8001
  participant Mac as macOS Executors

  You->>Island: hover / click / shortcut / Hey Mac
  Island->>Speech: start MicListener
  Speech-->>Island: partials (prefer catalog spelling)
  Island->>Opener: POST /decide (fires as each new name lands)
  alt App prediction or system paraphrase
    Opener->>Laya: POST /v1/systemone
    Laya-->>Opener: probabilities
  else Fully-parsed system command (~3 ms)
    Note over Opener: Parse volume, brightness, lock, dark mode, etc.
  end
  Opener-->>Island: action, apps, system, timing
  Island->>Mac: open / close / quit / system controls
  Speech-->>Island: silence → finish
```

How the pieces fit:

1. The island listens with the Mac’s own speech recognizer.
2. It asks the decide service on `localhost:8010` — “what did they mean?”
3. Fully-parsed system commands (volume, brightness, lock, dark mode, battery, etc.) resolve on the host in ~3 ms without calling Laya.
4. For app requests and paraphrases, that service asks Laya on `localhost:8001` — still this machine, still Docker.
5. Laya returns scores. Policy + spoken-name aliases pick the app.
6. The island opens, closes, or quits apps, or directly adjusts macOS settings (CoreAudio, DisplayServices, HID, AppleScript).

Full internals: [docs/how-it-works.md](docs/how-it-works.md). Speech notes: [docs/speech-recognition.md](docs/speech-recognition.md). Latency notes: [docs/voice-to-open-latency.md](docs/voice-to-open-latency.md).

## Requirements

- **macOS 14+** on Apple Silicon (the notch app is `arm64-apple-macos14.0`)
- **Xcode Command Line Tools** (`xcode-select --install`) — Swift, clang, codesign
- **Docker Desktop** or OrbStack, with the Docker CLI on `PATH`
- **`laya-upstream:latest`** already on the machine. This repo does **not** ship the model image. The opener container talks to it at `http://host.docker.internal:8001`.
- First run: grant **Microphone** and **Speech Recognition**. First *close*: grant **Accessibility** once.

If you do not have `laya-upstream:latest`, `docker compose up` will fail on the `laya` service. Build or load that image from the Laya project first, then come back here.

## Run locally

```bash
git clone https://github.com/AshutoshKY/sayso.git
cd sayso
./launch
```

`./launch` will:

1. Refuse if Docker is not running (and try to open Docker Desktop).
2. `docker compose up -d --build` (or rebuild only `opener` if `laya-upstream` is already a container).
3. Poll `http://127.0.0.1:8010/health` for up to 60 s.
4. Build `Sayso.app` if it is missing, then `open` it.

Check the pods:

```bash
docker compose ps
curl -sS -m 3 http://127.0.0.1:8010/health
# expect: {"status": "ok", "laya": true}
```

Then:

- Click the purple notch dot, press **⌃⌥Space**, hover the notch (~500 ms), or say **Hey Mac** / **Bhai Mac**.
- Say *open notes*, *jot something down*, *remind me later*.
- One breath after the wake works the same as after the hotkey: *hey mac open notes and safari*, *hey mac increase volume by 2*. The mic stays open through the rest of the sentence — it does not cut after the first name or after *increase volume*.
- Right-click the menu-bar waveform for **Settings** (per-trigger on/off, wake phrases, hover wait, shortcut, listening master, Quit).
- Say *goodbye* to dismiss.

Do **not** run `python -m opener` or any Laya process on the Mac. Inference and decide both stay in Docker.

### First-time app build only

```bash
./scripts/build_app.sh
open "$HOME/Applications/Sayso.app"
```

That compiles the Swift accessory, signs it with a stable “Laya Opener” identity (so TCC grants survive rebuilds), and copies it to `~/Applications/Sayso.app`.

### Optional: start at login

```bash
./scripts/install_launch_agent.sh
```

Restarts on crash; stays dead after Quit from the menu.

### Python-only changes (no .app rebuild)

```bash
docker build -t laya-app-opener:latest .
docker rm -f laya-opener
docker compose up -d --no-deps opener
curl -sS -m 3 http://127.0.0.1:8010/health
```

### Swift / Info.plist / signing changes

```bash
./scripts/build_app.sh
kill $(pgrep -n Sayso); sleep 1
open "$HOME/Applications/Sayso.app"
```

`ditto` overwrites the bundle but does not replace a live process. Confirm a new pid with `pgrep -lf Sayso`.

## Tests

Unit suite (no Docker, no mic):

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -q
```

Live Laya checks (`tests/test_live_laya.py`) skip unless `:8001` is healthy. With the stack up they lock:

- `open anti gravity` → `antigravity`
- `open podcast and notes` → `apps: [podcasts, notes]`
- `hey mac open notes and safari` → `apps: [notes, safari]`
- `hey mac increase volume by 2` → `volume_up 0.2`
- `open her mess` → `hermes`
- `open cloud flare` → `cloudflarewarp`
- `open youtube in brave` → `open_url` + `https://www.youtube.com` + `brave`

Probe decide yourself:

```bash
curl -sS http://127.0.0.1:8010/decide \
  -H 'Content-Type: application/json' \
  -d '{"text":"open notes","catalog":{"notes":{"say":"Notes","aliases":["notes"],"criteria":"Notes.app"}},"running":[],"pending":[]}'
```

## Repo layout

```
sayso/
├── launch                         # compose up + open the notch app
├── docker-compose.yml             # laya-upstream :8001, laya-opener :8010
├── Dockerfile                     # python:3.12-slim → opener.server
├── catalog.json                   # curated daily catalog (copied into the .app)
├── opener/                        # runs ONLY in Docker
│   ├── server.py                  # GET /health, POST /decide
│   ├── loop.py                    # split / Laya / alias recover
│   ├── client.py                  # questions_for + POST Laya
│   ├── policy.py                  # Decision from probabilities
│   ├── system_cmd.py              # system controls: host parse + Laya fallback + labels
│   ├── alias.py                   # spoken_key, resolve_alias, prefer_catalog
│   └── …
├── native/notch/                  # Swift accessory (Sayso.app)
├── scripts/
│   ├── build_app.sh
│   ├── ensure_codesign.sh
│   ├── install_launch_agent.sh
│   └── com.laya.opener.plist      # template; __HOME__ substituted on install
├── docs/                          # internals, speech, latency
└── tests/
```

Python and Swift keep alias / speech-form / `preferCatalog` rules in lockstep.

## Product rules

- Voice-first, **English only**.
- **Every utterance calls Laya.** Host matching may add extras or recover an exact installed name after Laya asks. It must not skip the call.
- Missing or unrecognized → open nothing. No Calendar / Chrome / default-browser fallthrough.
- Several names in one phrase (`and` / `,` / `then`) → act on every hit. Same after a wake word (*hey mac open notes and safari*).
- Wake + command stays on one speech session. The first name or a system fragment (*increase volume*) must not cut the mic, or *and safari* / *by 2* never arrive.
- Close = windows only (one Accessibility grant). Quit / kill = `terminate` / `forceTerminate`. Finder and Sayso are protected.
- `open <site> in <app>` and `open clipboard` are parsed on the host; Laya still names the app. Unknown site with no app → ask, no default-browser guess.
- System controls (volume, brightness, appearance, Night Shift, lock, battery, settings panes, AirDrop) are parsed on the host and **skip Laya** when the phrasing fully parses (`open clipboard` precedent). Paraphrases without gate words still go through Laya's `system` head. Execution happens on the Mac in Swift; the caption reports the real result (true level, battery, failure), never a canned line.

## What this is not

- Not a general Siri / Spotlight replacement.
- Not a Laya playground (that is the Laya repo).
- Not an on-host model runner.
- Not a second speech engine.
- Not a fallback-to-Chrome product.
- Not a ChatGPT / Claude / Gemini wrapper. There is no cloud LLM in this stack.

## License

MIT. See [LICENSE](LICENSE).
