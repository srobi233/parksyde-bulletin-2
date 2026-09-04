#!/usr/bin/env python3
"""
ParkSyde Bright Side — daily good-news bulletin generator.

Runs once a day from .github/workflows/daily_bulletin.yml. Asks Claude to
search today's real news, write a six-segment script, then (optionally) turns
each spoken line into audio with ElevenLabs and writes everything under
output/<date>/.

Two things broke this pipeline between June and September 2026, and both are
guarded against here because neither announced itself:

  1. The model id was pinned to a dated snapshot ("claude-sonnet-4-20250514")
     that was later retired. The API answered 404. The retry loop caught the
     exception, printed "Attempt N failed", slept, and retried three more
     times — so the log said "All retries failed" and never once printed the
     word "model". Four identical retries of a request that can never succeed
     is not resilience, it is a blindfold. Client errors now stop immediately
     and print the API's own response body.

  2. A corrected copy of this file was pasted into the workflow YAML by
     mistake, which made the workflow un-parseable. GitHub silently stopped
     scheduling it — no red X, no email, just nothing. See the README.
"""

import os, sys, json, datetime, time, re
from pathlib import Path

try:
    import requests
except ModuleNotFoundError:
    sys.exit("FATAL: the 'requests' package is not installed. The workflow "
             "installs it in the 'Install dependencies' step — check that "
             "step still exists in .github/workflows/daily_bulletin.yml.")

# --- required secret: fail loudly and clearly rather than with a raw KeyError
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    sys.exit("FATAL: ANTHROPIC_API_KEY is not set. Add it under Settings -> "
             "Secrets and variables -> Actions, and make sure it is passed "
             "through the workflow's env: block.")

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")   # optional — audio
PARKSYDE_WEBHOOK   = os.environ.get("PARKSYDE_WEBHOOK")     # optional — ping

# Model. Sonnet is the deliberate choice for a daily unattended run: this
# bulletin writes 20-odd short spoken lines from search results, which Sonnet
# does well, and the pipeline has to survive on a budget nobody is watching.
# For a noticeably richer script, swap this one line to "claude-opus-5".
# Do NOT append a date to these ids — a dated snapshot is what died in June.
MODEL = "claude-sonnet-5"

# Server-side web search tool version. Current on Sonnet 5 and Opus 5. If you
# ever pin MODEL to an older model, this must go back to "web_search_20250305"
# — the tool type and the model version have to agree or the API returns 400.
WEB_SEARCH_TOOL = "web_search_20260209"

TODAY     = datetime.date.today()
DATE_STR  = TODAY.strftime("%Y-%m-%d")
DAY_NAME  = TODAY.strftime("%A, %B %-d")

OUTPUT_DIR = Path("output/" + DATE_STR)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "x-api-key": ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
    "Content-Type": "application/json"
}

VOICES = {
    "charlie": "IKne3meq5aSn9XLyUdCD",
    "alice":   "Xb7hH8MSUJpSbSDYk0k2",
}

PROMPT_TEMPLATE = """Today is __DAY__. Search for today's real news and write a complete ParkSyde Bright Side bulletin.

ParkSyde is a Queensland lifestyle brand. Pillars: environment, science, sports, weather.
Hosts: Alex Mercer (charlie voice, casual Aussie bloke). Co-host: Jamie (alice voice, upbeat).
Meteorologist: Sam (charlie voice). South-east Queensland weather.

STRICT OUTPUT RULES:
- Return ONLY a single JSON object. No preamble, no markdown, no code fences.
- The text field of every line must contain ONLY the spoken words.
- Do NOT include stage directions, accent notes, or bracketed instructions. No [Australian accent], no [laughs], no [pause]. The voices are already Australian.
- Do NOT use double quotes inside any text value. If you need to quote something, use single quotes.
- Do NOT use unescaped newlines inside any string.

Return this exact structure:
{
  "stories": {
    "environment": ["story 1 headline", "story 2 headline"],
    "science": ["story 1 headline"],
    "sports": ["story 1 headline"],
    "overview": "awe-inspiring story headline"
  },
  "seg1_open": [
    {"speaker": "charlie", "text": "..."},
    {"speaker": "alice", "text": "..."},
    {"speaker": "charlie", "text": "..."}
  ],
  "seg2_green": [
    {"speaker": "alice", "text": "..."},
    {"speaker": "charlie", "text": "..."},
    {"speaker": "alice", "text": "..."}
  ],
  "seg3_science": [
    {"speaker": "charlie", "text": "..."},
    {"speaker": "alice", "text": "..."},
    {"speaker": "charlie", "text": "..."}
  ],
  "seg4_weather": "Cheers Alex...",
  "seg5_sports": [
    {"speaker": "charlie", "text": "..."},
    {"speaker": "alice", "text": "..."},
    {"speaker": "charlie", "text": "..."}
  ],
  "seg6_outro": [
    {"speaker": "charlie", "text": "..."},
    {"speaker": "alice", "text": "..."},
    {"speaker": "charlie", "text": "..."},
    {"speaker": "alice", "text": "..."},
    {"speaker": "charlie", "text": "..."}
  ]
}

Use today's REAL news. Make each speaker line 2-3 sentences. Warm, dry Australian humour, no schlock."""

SYSTEM_PROMPT = (
    "You are the head writer for ParkSyde Bright Side, a daily good news bulletin. "
    "You always return a single valid JSON object and nothing else. "
    "You never include stage directions, brackets, or unescaped quotes inside string values."
)


def claude(prompt, system="", max_tokens=4000, use_search=False):
    body = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}]
    }
    if system:
        body["system"] = system
    if use_search:
        # Server-side search: Anthropic runs the searches and returns final text.
        body["tools"] = [{
            "type": WEB_SEARCH_TOOL,
            "name": "web_search",
            "max_uses": 5
        }]

    for attempt in range(4):
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=HEADERS, json=body, timeout=180
            )

            if resp.status_code == 429:
                wait = 60 * (attempt + 1)
                print("Rate limited - waiting " + str(wait) + "s")
                time.sleep(wait)
                continue

            # Any other 4xx is a request problem — a retired model id, a tool
            # type the model does not accept, a revoked key, no credit. Retrying
            # cannot fix it and, worse, buries the reason. Stop and show the
            # API's own words. This is the guard that would have named the
            # June failure in the first line of the log.
            if 400 <= resp.status_code < 500:
                sys.exit(
                    "FATAL: Anthropic API returned " + str(resp.status_code) +
                    " for model '" + MODEL + "'.\n"
                    "This is a request problem (model id, web-search tool "
                    "version, API key, or billing), not a transient one, so "
                    "retrying is pointless.\nResponse body:\n" + resp.text
                )

            resp.raise_for_status()          # 5xx and network errors -> retry
            data = resp.json()
            return "\n".join(
                b["text"] for b in data.get("content", [])
                if b.get("type") == "text"
            )
        except SystemExit:
            raise
        except Exception as e:
            print("Attempt " + str(attempt + 1) + " failed: " + str(e))
            time.sleep(30)

    raise Exception("All retries failed (server kept returning 5xx or the "
                    "network kept dropping)")


def extract_json(raw):
    raw = raw.strip()
    if "```json" in raw:
        raw = raw.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in raw:
        raw = raw.split("```", 1)[1].split("```", 1)[0]
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in response")
    return raw[start:end + 1].strip()


def clean_spoken(text):
    """Strip anything that is markup rather than words.

    The web-search tool returns citations as <cite index='28-2,28-3'>…</cite>
    and the model writes them straight into the spoken lines. 185 of them
    survive in 20 of the 45 bulletins already published. Nothing removed them:
    the TTS cleaner strips [stage directions] in square brackets and nothing
    else, so ElevenLabs was handed the literal string "<cite index='28-2,28-3'>
    Extended highlights are up from the Eagles and Bombers clash" and read the
    markup out along with the sentence. On the page it showed as raw tags.

    A listener would have heard it every second morning. Nobody was listening,
    which is the only reason it lasted."""
    if not text:
        return ""
    text = re.sub(r'<[^>]*>', '', text)          # cite tags and any other markup
    text = re.sub(r'\[[^\]]*\]', '', text)       # [Australian accent], [pause]
    text = re.sub(r'\s+', ' ', text)             # the gaps those left behind
    return text.strip()


def clean_bulletin(data):
    """Run every spoken line through clean_spoken, in place."""
    for key in list(data.keys()):
        val = data[key]
        if isinstance(val, str) and key.startswith("seg"):
            data[key] = clean_spoken(val)
        elif isinstance(val, list):
            for line in val:
                if isinstance(line, dict) and "text" in line:
                    line["text"] = clean_spoken(line["text"])
    return data


def parse_bulletin(raw):
    candidate = extract_json(raw)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        # Occasionally a stage direction survives the prompt rules. Strip
        # short bracketed asides and try once more before giving up.
        print("First parse failed: " + str(e) + ". Attempting cleanup...")
        cleaned = re.sub(r'\[([A-Za-z][A-Za-z\s]{1,40})\]', '', candidate)
        return json.loads(cleaned)


def generate_tts(text, speaker, filename):
    if not ELEVENLABS_API_KEY:
        print("  No ElevenLabs key - skipping TTS")
        return False
    voice_id = VOICES.get(speaker, VOICES["charlie"])
    url = "https://api.elevenlabs.io/v1/text-to-speech/" + voice_id
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    # Belt and braces. clean_bulletin() has already been over every line, but
    # this is the last point before words become a voice, and a stray tag here
    # is not a rendering blemish — it is something a person hears.
    clean_text = clean_spoken(text)
    if not clean_text:
        print("  Nothing to say for " + filename + " — skipping")
        return False
    body = {
        "text": clean_text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
    }
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        with open(filename, "wb") as f:
            f.write(resp.content)
        print("  TTS OK: " + filename)
        return True
    except Exception as e:
        # Audio is a bonus, not the bulletin. A failed voice line must not
        # cost the day's scripts, so this reports and carries on.
        print("  TTS failed for " + filename + ": " + str(e))
        return False


def generate_segment_audio(seg_id, script):
    """Voice one segment. Returns its lines, each carrying the audio path that
    was ACTUALLY written — or None where the voice failed.

    Reporting what happened rather than nothing is the whole point. The
    manifest used to record `has_audio: bool(ELEVENLABS_API_KEY)`, which is a
    statement about a key, not about a file, and it was written before a single
    voice had been attempted. On 1 June 2026 the key was set, every TTS call
    failed, and that day's manifest still reads `has_audio: true` beside an
    output folder with no audio directory in it at all. The player believed it
    and offered a play button for a bulletin that had no voice."""
    audio_dir = OUTPUT_DIR / "audio"
    audio_dir.mkdir(exist_ok=True)
    lines = []

    if isinstance(script, str):
        if not script.strip():
            return lines
        name = seg_id + ".mp3"
        ok = generate_tts(script, "charlie", str(audio_dir / name))
        lines.append({"speaker": "charlie", "text": script,
                      "audio": (DATE_STR + "/audio/" + name) if ok else None})
    elif isinstance(script, list):
        for i, line in enumerate(script):
            speaker = line.get("speaker", "charlie")
            text = line.get("text", "")
            name = seg_id + "_line" + str(i) + ".mp3"
            ok = generate_tts(text, speaker, str(audio_dir / name))
            lines.append({"speaker": speaker, "text": text,
                          "audio": (DATE_STR + "/audio/" + name) if ok else None})
            time.sleep(1)

    return lines


SEGMENTS = ["seg1_open", "seg2_green", "seg3_science", "seg5_sports", "seg6_outro"]

# Segment ids are filenames; these are what a listener sees. Order is broadcast
# order, which is NOT the order of SEGMENTS — the weather sits fourth, between
# science and sport, exactly as the hosts read it.
RUNNING_ORDER = [
    ("seg1_open",    "The Open"),
    ("seg2_green",   "Green Desk"),
    ("seg3_science", "Science & Tomorrow"),
    ("seg4_weather", "Weather"),
    ("seg5_sports",  "The Scoreboard"),
    ("seg6_outro",   "Overview & Outro"),
]


def main():
    print("ParkSyde Bright Side - " + DATE_STR + " (model: " + MODEL + ")")
    print("[1/3] Fetching news and writing scripts...")

    prompt = PROMPT_TEMPLATE.replace("__DAY__", DAY_NAME)

    data = None
    last_err = None
    for attempt in range(3):
        news_raw = claude(prompt=prompt, system=SYSTEM_PROMPT,
                          max_tokens=4000, use_search=True)
        try:
            data = clean_bulletin(parse_bulletin(news_raw))
            break
        except Exception as e:
            last_err = e
            print("Bulletin parse attempt " + str(attempt + 1) + " failed: " + str(e))
            print("Raw head: " + news_raw[:400])
            time.sleep(10)
    if data is None:
        raise Exception("Could not parse bulletin after 3 attempts: " + str(last_err))

    print("[2/3] Writing script files...")
    stories = data.get("stories", {})
    for key in SEGMENTS:
        (OUTPUT_DIR / (key + ".json")).write_text(
            json.dumps(data.get(key, []), indent=2))
    (OUTPUT_DIR / "seg4_weather.txt").write_text(data.get("seg4_weather", ""))

    print("[3/3] Generating TTS audio...")
    # The manifest is written AFTER this, not before, so it can describe what
    # exists rather than what was hoped for.
    segments = []
    for seg_id, title in RUNNING_ORDER:
        script = data.get(seg_id, "" if seg_id == "seg4_weather" else [])
        lines = generate_segment_audio(seg_id, script)
        if not lines:
            continue
        segments.append({
            "id": seg_id,
            "title": title,
            # One readable paragraph for anyone who cannot or does not want to
            # listen — the page has to be worth opening with the sound off.
            "script": " ".join(l["text"] for l in lines if l.get("text")).strip(),
            "lines": lines,
        })

    voiced = sum(1 for s in segments for l in s["lines"] if l.get("audio"))
    spoken = sum(len(s["lines"]) for s in segments)

    manifest = {
        "date": DATE_STR,
        "day": DAY_NAME,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model": MODEL,
        "stories": stories,
        "segments": segments,
        # Counts, not intentions. `has_audio` is now true only when a file was
        # written and the write was confirmed.
        "lines": spoken,
        "audio_files": voiced,
        "has_audio": voiced > 0,
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    Path("output/latest.json").write_text(json.dumps(manifest, indent=2))

    if spoken and voiced < spoken:
        # Loud, because a half-voiced bulletin is the failure that hid behind
        # `has_audio: true` for the last three weeks it ran.
        print("WARNING: " + str(spoken - voiced) + " of " + str(spoken) +
              " lines have no audio. Check the ElevenLabs key and quota.")

    if PARKSYDE_WEBHOOK:
        try:
            requests.post(PARKSYDE_WEBHOOK, json={
                "date": DATE_STR,
                "day": DAY_NAME,
                "scripts": {k: data.get(k) for k in
                            SEGMENTS + ["seg4_weather"]},
                "stories": stories,
                "secret": os.environ.get("PARKSYDE_WEBHOOK_SECRET")
            }, timeout=30)
            print("Webhook notified")
        except Exception as e:
            print("Webhook ping failed: " + str(e))

    print("Done. Output in " + str(OUTPUT_DIR) + "/")


if __name__ == "__main__":
    main()
