# Speech recognition: diagnosis, fix, before/after

How unusual spoken names (`Hermes`, `Cloudflare`) failed, how that was checked, what changed, and how the stack works now.

This is a write-up of the 2026-09-26 investigation. Operational rules for the next change live in the `laya-voice-app-opener` skill (`references/speech-recognition.md`).

## The pipeline (unchanged)

```
mic → Apple Speech (notch app)
    → POST 127.0.0.1:8010/decide   (laya-opener container)
        → POST :8001/v1/systemone  (Laya)
        → host alias recovery if Laya says unspecified/ask
    → open -a <catalog app>
```

Every utterance still calls Laya. The host never skips the model. Missing or unrecognized still opens nothing.

There are two independent failure points:

1. **ASR** — Apple never wrote the brand into the transcript.
2. **NLP / matching** — the transcript is useful, but alias + Laya do not map it to an installed app.

A miss that looks like “it didn’t recognise Hermes” can be either, or both.

## How the issue was checked

No guess from memory. The live stack and the source were split first.

### 1. Confirm the stack is the real one

```bash
curl -sS -m 3 http://127.0.0.1:8010/health
# {"status": "ok", "laya": true}

pgrep -lf Sayso
ls /Applications | rg -i 'warp|cloud|hermes'
```

Both apps were installed (`Hermes.app`, `Cloudflare WARP.app`). Opener and Laya were healthy.

### 2. Split ASR vs decide

Apple Speech is a black box. The island shows the transcript it actually produced. `/decide` only sees that string.

So the check is:

1. Read the island line (`Listening / …` or `Deciding / …`), not the intended words.
2. POST that exact string to `/decide` with the live scanned catalog.

| Result | Layer |
| --- | --- |
| `/decide` already opens the right app | ASR miss — Apple never said the brand |
| `/decide` also fails | alias / Laya miss |

For `open hermes` and `open cloudflare` as **typed** text, live `/decide` already worked once aliases existed. The original live complaint was voice. That pointed at Apple first, then at recovery when Apple returned a nearby phrase (`her mess`, `cloud flare`) instead of the official name.

### 3. Read the speech and matching code

| Layer | File | What it was doing |
| --- | --- | --- |
| Mic / ASR | `native/notch/SpeechListen.swift` | `SFSpeechRecognizer`, `.dictation`, first hypothesis only, 0.45s silence cut |
| Host catalog / aliases | `native/notch/Engine.swift`, `opener/scan.py` | generate spoken forms from app names |
| Decide / Laya | `opener/client.py`, `opener/loop.py`, `opener/alias.py` | Laya choice, then recover only an *exact* compact id |

Apple Speech has no custom language model. The only bias API is `contextualStrings` (≤100 short phrases). It was unused.

### 4. Why these two names specifically

They fail for different mechanical reasons. Both look the same to the user.

**Hermes**

- Unusual proper name. Apple’s LM prefers common English.
- Typical hypotheses: `her mess`, `her mes`, `hermits`, `hurmez`.
- The scanner used to strip a trailing `s` on short names, so `Hermes` could collapse toward `herme`. That is wrong: Hermes is not a plural.

**Cloudflare (WARP)**

- Compound brand. People say `cloud flare`. Apple often emits that spaced form.
- Display name is `Cloudflare WARP`. Without exploding the compound and keeping the long first token (`cloudflare`) when the tail is a product word (`warp`), the spoken form never matches the catalog id `cloudflarewarp`.

### 5. Why Laya did not save it

Even with a usable nearby transcript, recovery after Laya returned `unspecified` / `ask` was:

```text
exact_installed_id(text)   # compact letters only: "open her mess" → "hermess"
```

That only hits if the compact form *is* a catalog id (`hermes`, `antigravity`). ASR errors are not exact ids, so the host opened nothing. Laya’s criteria also did not list the heard forms, so the model had no reason to pick the app.

## Causes (stacked)

1. **No speech bias.** `contextualStrings` empty. The 100-slot budget was never used. Unusual brands never entered Apple’s search.
2. **Wrong task hint.** `.dictation` is for prose. App names are closer to `.search`.
3. **First hypothesis only.** `bestTranscription` was kept. Alternatives on `transcriptions` / `alternativeSubstrings` were discarded.
4. **Silence cut too early.** 0.45s after any unchanged text. Alternatives often arrive after the first guess.
5. **Recovery too strict.** Exact compact id only. `her mess` and `cloud flare` never recovered.
6. **Scanner gaps.** No compound explode (`cloudflare` → `cloud flare`). Short names could lose a trailing `s`.
7. **Laya criteria** did not mention the heard forms, so the model treated them as unspecified.

## What was changed

Python first (TDD + Docker), then Swift (rebuild the `.app`). Laya is still always called.

### Recognition (Swift notch app)

`SpeechListen.swift`

- `taskHint = .search`
- `contextualStrings` = ranked catalog phrases, cap 100
- Collect best + all transcriptions + each segment’s `alternativeSubstrings`
- `preferCatalog`: lock Apple’s *first named app*, prefer that app’s official spelling. Do not swap in a later hypothesis that names a different app (`notes` must not steal `hermits`)
- Hold ~1.6s until the partial names an installed app or closed list; ~0.45s once a closed list lands

`Engine.swift` / `NotchApp.swift`

- `speechPhrases` ranks ASR confusions and compound brands ahead of `Notes` / `Safari` so the 100-slot cap does not crowd them out
- `aliases(forName:)` explodes compounds, keeps a long first token when the tail is `warp` / `desktop` / `pro` / …, and adds `speechForms` for Hermes
- Only singularise names of length ≥7

### Matching and NLP (Python opener, Docker)

- `scan.py`: same compound / speech-form / phrase-ranking rules as Swift
- `catalog.py` + `client.py`: Hermes and Cloudflare WARP aliases + Laya criteria include the heard forms
- `loop.py`: after Laya `unspecified` / `ask`, recover with `resolve_alias`, not only `exact_installed_id`
- `alias.py`: `prefer_catalog_transcript` mirrors Swift `preferCatalog`

### Tests that lock the behavior

- `test_alias`: `her mess` / `hermits` → hermes; `cloud flare` → cloudflarewarp; prefer official spelling of the first named app
- `test_scan`: speech phrases keep unusual brands under the 100 cap
- `test_loop`: Laya returns unspecified, alias still recovers
- `test_live_laya`: live model + real catalog for the same phrases

## How it worked before vs now

| Step | Before | Now |
| --- | --- | --- |
| Apple hint | `.dictation` | `.search` |
| Vocabulary bias | none | ≤100 ranked phrases, unusual brands first |
| Hypothesis used | first string only | alternatives scored; first named app wins |
| End listen | 0.45s after any unchanged text | 0.45s if closed list; ~1.6s if open/unnamed |
| Hermes spoken forms | `hermes` only (and a risky short singular) | `hermes`, `her mes`, `her mess`, `hermits`, `hurmez` |
| Cloudflare spoken forms | display name / compact id | `cloudflare`, `cloud flare`, `cloud flare warp`, `warp` as that app’s tail |
| After Laya says unspecified | exact compact id only | alias hit recovers the catalog app |
| Laya still called | yes | yes |

Typed `/decide` after the ship (live scanned catalog, Laya up):

```text
open hermes           → hermes
open her mess         → hermes
open hermits          → hermes
open cloudflare       → cloudflarewarp
open cloud flare      → cloudflarewarp
open cloud flare warp → cloudflarewarp
open anti gravity     → antigravity
open podcast and notes → [podcasts, notes]
```

241 unit + live tests green. Opener rebuilt and running; `Sayso.app` rebuilt and relaunched so the new recognizer is actually loaded (`ditto` overwrites the bundle but does not replace a live process).

## What this does not do

- No second speech engine (Whisper, etc.). Bias + alternatives + alias recovery first.
- No generic last-token aliases (`video`, `editor`, `player`, …). Those steal unrelated phrases.
- No skip of Laya when an alias hits. Recovery only runs after the model returns unspecified/ask.
- `warp` is allowed only as Cloudflare WARP’s product tail, not as a generic word.

## If another name still fails

1. Note the island transcript, not the intended words.
2. POST that string to `/decide`.
3. ASR miss → add the heard form to `speechForms` / `contextualStrings` (Python `scan.py` and Swift `Engine.swift` in lockstep).
4. Decide miss → add alias + Laya criteria, then `test_alias` / `test_loop` / `test_live_laya`.

Rebuild the `.app` only when Swift changed; ship Python-only changes as Docker only.
