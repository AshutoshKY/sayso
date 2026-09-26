# Voice-to-open latency: diagnosis, fix, before/after

How “open antigravity app” felt slow, how that was measured, what changed, and how the path works now.

Write-up of the 2026-09-26 investigation. Operational rules for the next change live in the `laya-voice-app-opener` skill.

## The pipeline (unchanged)

```
mic → Apple Speech (notch app)
    → POST 127.0.0.1:8010/decide   (laya-opener container)
        → POST :8001/v1/systemone  (laya-upstream, CPU)
    → NSWorkspace / open -a <catalog app> / native system controls
```

Every utterance still calls Laya. The host never skips the model. Missing or unrecognized still opens nothing.

The user’s target was: by the time they finish saying *“…app”*, Antigravity should already be opening.

## The five stages we timed

| # | Stage | Where |
|---|---|---|
| 1 | Voice identification | Apple `SFSpeechRecognizer` in `SpeechListen.swift` |
| 2 | Python / Docker hop | notch → `:8010/decide` → `questions_for` + `predict` |
| 3 | Laya inference | `:8001/v1/systemone`, English checkpoint, CPU, `OMP_NUM_THREADS=4` |
| 4 | Response processing | `parse_answers` + `decide` + JSON back to Swift |
| 5 | App launch | `NSWorkspace.openApplication` / `open -a` |

No guess from memory. Each stage was measured on the live stack (Apple M4, 10 cores, 24 GB; `laya-upstream` healthy, `laya-opener` healthy).

## How the issue was checked

### 1. Confirm the stack is the real one

```bash
curl -sS -m 3 http://127.0.0.1:8010/health
# {"status": "ok", "laya": true}

pgrep -lf Sayso
docker ps --filter name=laya
```

Both containers were up. The notch app was running from `~/Applications/Sayso.app`.

### 2. Time `/decide` with the same fat catalog the app sends

The Swift app POSTs the full scanned catalog (~112 apps, ~12 KB). Replay that:

```python
# POST http://127.0.0.1:8010/decide
# body = {"text": "open anti gravity", "catalog": <112 scanned apps>}
```

Before the fix, warm repeats:

| Utterance | p50 |
|---|---|
| `open notes` | 365–454 ms |
| `open anti gravity` | 404–465 ms |
| `open antigravity app` | 411–436 ms |
| `open whatsapp` | 389 ms |

So after speech ended, the user still waited ~400 ms before anything launched.

### 3. Split `/decide` from Laya itself

Direct `POST :8001/v1/systemone` with the same choice sets:

| Head | p50 | What it means |
|---|---|---|
| 2-way (`antigravity` + unspecified) | **135 ms** | Laya floor on this CPU box |
| 5-way named + distractors | **236 ms** | what named apps should cost |
| 6-way browsers | 209 ms | existing browser shortcut |
| 15-way daily set | **399 ms** | what *every* named request was paying |
| 16-way daily + antigravity | 406 ms | old `open anti gravity` prompt |
| 82-way dump | 784 ms | sending the whole catalog would be worse |
| intent + app (two heads) | 737 ms | already dropped; do not bring back |

Host → `:8001` and opener-container → `host.docker.internal:8001` were the same (~405 ms). The Docker hop is not the cost. `timing.total_ms ≈ timing.laya_ms` after we added clocks: Python around Laya is **<1 ms**.

### 4. Time the launch itself

```bash
open -a /Applications/Antigravity.app   # 33 ms
open -a /System/Applications/Notes.app  # 52 ms
open -a /Applications/WhatsApp.app      # 39 ms
open -a "/Applications/Brave Browser.app"  # 53 ms
```

Stage 5 is noise. The Mac is not slow to open these apps.

### 5. Read the speech path (no live mic bench needed)

`native/notch/SpeechListen.swift` before the fix:

- `silence = 1.6` — wait 1.6 s after the last recognition callback.
- Every callback, even an unchanged transcript, reset `lastSpeech`.
- After silence, `endAudio()` then **another 0.8 s** before `finish()`.
- Partials only updated the caption. `/decide` ran only after `finish()`.

That is **~2.4 s of dead air after the last word**, before Laya even starts. For a 1.5 s utterance the user felt ~4 s hotkey → app.

### 6. Check what Laya actually received

```text
questions_for("open anti gravity")     n=16 extras=['antigravity']
questions_for("open antigravity app")  n=17 extras=['antigravity', 'apps']
questions_for("open anti gravity app") n=16 extras=['apps']   # antigravity missing
```

Two bugs in one measurement:

1. Named apps still paid the 15-way daily tax.
2. Trailing *app* compacted to `antigravityapp` (not in catalog). Alias `app` then hit a scanned **Apps.app**, so Laya never saw `antigravity`.

## Root causes (ranked)

1. **Speech wait (stage 1) — ~2.4 s.** Serial silence + final-wait. Dominates perceived latency.
2. **Laya choice-set size (stage 3) — ~400 ms named.** Linear in option count on this CPU container. Named “open X” does not need the daily 15.
3. **Trailing “app” stole the match.** Scanned `Apps.app` ate `open anti gravity app`. Felt like both slowness and a miss.
4. **Not stage 2, 4, or 5.** Python, JSON, Docker, and `open -a` are tens of milliseconds at most.

Laya on CPU is the remaining floor (~135 ms even for 2 options). That is the model, not a bug in this repo.

## What we changed

TDD first (`tests/test_alias.py`, `test_client.py`, `test_loop.py`, `test_server.py`), then Docker-only Python, then a Swift rebuild because the listener changed.

### Smaller Laya head for named apps

`questions_for` now:

- If the utterance names an installed app → that app + 3 distractors + `unspecified` (never a lone app + unspecified black hole).
- If it looks like a browser → the existing 6-way browser head.
- Otherwise (paraphrases: *jot something down*) → the daily 15.

`spoken_key()` strips `open|launch|start|run` and trailing `app|application|please` before compacting. `open anti gravity app` → `antigravity`.

### Fire Laya on the first named partial

`NotchApp.considerPartial` calls `/decide` as soon as a *new* installed name appears. Already-opened ids are skipped so a list can keep launching. Mid-list partials keep the long hold. Stop phrases and negations do not speculative-open.

### Cut the silence pad

`MicListener` silence **1.6 s → 0.45 s**. Unchanged transcripts no longer reset the clock. The 0.8 s post-`endAudio` wait is gone; listen ends immediately after silence.

### Clocks on the wire

`/decide` returns `timing: {total_ms, laya_ms}`. The app `NSLog`s `partial-fire`, `heard`, `decide`, `open` with milliseconds from listen start.

## Before / after

Same machine, warm Laya, fat catalog:

| Path | Before | After |
|---|---|---|
| Speech end → `/decide` starts | ~2.4 s after last word | first named partial; listen ends ~0.45 s after last *new* word |
| `/decide` `open anti gravity` | ~400–465 ms | **~250 ms** |
| `/decide` `open antigravity app` | ~411–436 ms, sometimes asked / wrong | **~290 ms**, opens `antigravity` |
| `/decide` `jot something down` | ~440 ms (15-way) | ~440 ms (still 15-way, correct) |
| Python around Laya | unmeasured | **0.2 ms** |
| `open -a Antigravity` | 33 ms | 33 ms |
| Felt hotkey → app for “open antigravity app” | ~4 s | app starts during *“…app”* |

Replayed after the Docker + app rebuild:

```
open notes fat                 p50=260  -> open notes
open anti gravity fat          p50=251  -> open antigravity
open antigravity app fat       p50=348  -> open antigravity
open anti gravity app fat      p50=286  -> open antigravity
jot something down fat         p50=440  -> open notes
```

241 unit tests + live Laya suite green.

## How it works now vs before

**Before.** Click / ⌃⌥Space → listen until 1.6 s of “silence” (often longer, because unchanged partials reset the timer) → wait 0.8 s more → POST a 15–17 option Laya prompt → wait ~400 ms → `open -a`. Trailing *app* could send `apps` instead of `antigravity`.

**Now.** Click / ⌃⌥Space → partials stream. The moment a new installed name lands (`open anti gravity` → `antigravity`), `/decide` fires with a 5-way head (~250 ms) and that app opens. Mid-list (`Calculator` / `open calculator antigravity`) keeps the long 1.6 s hold so later names still land; a closed list (`open A and B`) ends ~0.45 s after the last *changed* word. A real silence after the last name also ends listen. Laya still runs on every utterance. Paraphrases still use the daily set.

```
before:  [==== speaking ====][---- 1.6s silence ----][-- 0.8s --][=== Laya 400ms ===][open]
now:     [==== speaking ====]
                    ^ first named partial → Laya 250ms → open
                         [0.45s after last new word → listen ends]
```

## How to re-measure

```bash
curl -sS -m 3 http://127.0.0.1:8010/health
# POST /decide and read payload["timing"]
# Console.app filter: laya-opener
```

Useful log lines from the notch app:

- `laya-opener partial-fire 'open anti gravity' +820ms`
- `laya-opener http /decide 251ms`
- `laya-opener open antigravity 2ms (+1070ms from listen)`
- `laya-opener heard 'open anti gravity app' +1400ms`

If `+from listen` on `open` is still >2 s, the leftover is either Apple Speech being late with the first named partial, or Laya CPU (~250 ms named / ~440 ms paraphrase). Next levers: GPU Laya, or a second overlapping speculative call. Do not grow the choice set, and do not put the 1.6 s / 0.8 s waits back.
