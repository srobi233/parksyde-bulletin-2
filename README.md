# ParkSyde Bright Side

A daily good-news bulletin. Every morning at 6am AEST a GitHub Action asks
Claude to search the day's real news, write a six-segment script for two
Australian hosts, turn each spoken line into audio with ElevenLabs, and commit
the result to `output/<date>/`.

There is no server, no subscription and no third-party build service. It is a
Python script and a scheduled workflow. That is the whole system, deliberately
— it went quiet once already because it depended on something that lapsed.

## What runs, and when

| Piece | What it does |
|---|---|
| `.github/workflows/daily_bulletin.yml` | 20:00 UTC daily (6am AEST), and on demand from the Actions tab. Runs the generator, commits the output. |
| `.github/workflows/workflows-valid.yml` | On every push. Checks that every workflow file still parses and every Python file still compiles. See "Why silence is the danger". |
| `generate_bulletin.py` | The generator. Writes scripts, then audio, then an optional webhook ping. |
| `widget.html` | Standalone player for a bulletin. Opens from a file, no server. |
| `replit_receiver.py` | Flask endpoint that receives the webhook and serves the latest bulletin. Runs on Replit, not here. |
| `parksyde_filter.py` | Brand-alignment scorer for story selection. **Not currently wired into the generator** — it exists but nothing calls it. |
| `docs/jules.yml.disabled` | A Google Jules workflow that was sitting in a folder called `github/` (no dot), which GitHub ignores, so it never ran. Parked here rather than deleted. To use it, move it to `.github/workflows/` and add a `JULES_API_KEY` secret. |
| `docs/platform-brief.md` | A build brief for a larger ParkSyde platform, pasted into this repo as a file with no extension. Kept for reference; nothing reads it. |

## Secrets it needs

Set under **Settings → Secrets and variables → Actions**:

| Secret | Required? | Without it |
|---|---|---|
| `ANTHROPIC_API_KEY` | **Yes** | The run stops immediately with a clear message. |
| `ELEVENLABS_API_KEY` | No | Scripts are written, audio is skipped. |
| `PARKSYDE_WEBHOOK` | No | Output is committed, the Replit endpoint is not pinged. |
| `PARKSYDE_WEBHOOK_SECRET` | No | The webhook is sent unauthenticated. |

## Why silence is the danger

The bulletin ran daily until **1 June 2026**, then failed every day until
**21 July**, then stopped running at all. Two separate faults, neither of which
announced itself:

1. **A retired model id.** `MODEL` was pinned to `claude-sonnet-4-20250514`, a
   dated snapshot that was later withdrawn. The API answered `404`. The retry
   loop caught the exception, printed `Attempt 1 failed`, slept thirty seconds
   and tried the identical request three more times. The log's last line was
   `All retries failed` — it never printed the word *model*. Forty-five days of
   red ticks that said nothing about the cause.

2. **A corrected script pasted into the workflow file.** On 22 July a fixed
   copy of `generate_bulletin.py` was pasted into
   `.github/workflows/daily_bulletin.yml` instead of into the script. That made
   the YAML un-parseable. GitHub does not *fail* an invalid workflow — it stops
   scheduling it. No run, no red X, no email. From that day the Bright Side
   simply did not exist, and the repository looked no different.

Both are fixed, and both now have a guard rather than a promise:

- Any 4xx from the API stops the run on the first attempt and prints the API's
  own response body, naming the model it tried. Only 5xx and network errors
  retry, because only those can succeed on a second go.
- `workflows-valid.yml` lives in a *separate file* and fails visibly if any
  workflow will not parse. A paste that breaks one file is caught by the other.
- The daily workflow compiles the generator before it spends a token.

This was blamed at the time on a lapsed Emergent subscription. It was not:
there is no Emergent dependency anywhere in this repository. The pipeline was
already dead from its own two faults.

## Changing the model

One line, near the top of `generate_bulletin.py`:

```python
MODEL = "claude-sonnet-5"
```

Sonnet is the deliberate choice for an unattended daily run — the job is
twenty-odd short spoken lines from search results, and the whole point of this
setup is that it survives on a budget nobody is watching. Swap to
`claude-opus-5` for a richer script.

**Never append a date to a model id.** A dated snapshot is exactly what died in
June. If you ever pin an older model, `WEB_SEARCH_TOOL` must change with it —
the web-search tool version and the model version have to agree, or the API
returns 400.

## Running it by hand

Actions → Daily Bulletin → Run workflow. Or locally:

```sh
pip install requests
ANTHROPIC_API_KEY=sk-... python generate_bulletin.py
```

Output lands in `output/<today>/`: five `seg*.json` script files, one
`seg4_weather.txt`, a `manifest.json`, and `audio/` if an ElevenLabs key was
set. `output/latest.json` always points at the most recent day.
