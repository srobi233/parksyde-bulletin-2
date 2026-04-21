#!/usr/bin/env python3
import os, json, datetime, requests, time, re
from pathlib import Path

ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
PARKSYDE_WEBHOOK   = os.environ.get("PARKSYDE_WEBHOOK")
MODEL     = "claude-sonnet-4-20250514"
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
Meteorologist: Sam (charlie voice). Warm dry Autumn weather in SE Queensland.

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

Use today's REAL news. Make each speaker line 2-3 sentences. Warm dry Australian humour, no schlock."""

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
    if system: body["system"] = system
    if use_search: body["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]
    for attempt in range(4):
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=HEADERS, json=body
            )
            if resp.status_code == 429:
                wait = 60 * (attempt + 1)
                print("Rate limited — waiting " + str(wait) + "s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            return "\n".join(
                b["text"] for b in data.get("content", [])
                if b.get("type") == "text"
            )
        except Exception as e:
            print("Attempt " + str(attempt + 1) + " failed: " + str(e))
            time.sleep(30)
    raise Exception("All retries failed")

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

def parse_bulletin(raw):
    candidate = extract_json(raw)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        print("First parse failed: " + str(e) + ". Attempting cleanup...")
        cleaned = re.sub(r'\[([A-Za-z][A-Za-z\s]{1,40})\]', '', candidate)
        return json.loads(cleaned)

def generate_tts(text, speaker, filename):
    if not ELEVENLABS_API_KEY:
        print("  No ElevenLabs key — skipping TTS")
        return False
    voice_id = VOICES.get(speaker, VOICES["charlie"])
    url = "https://api.elevenlabs.io/v1/text-to-speech/" + voice_id
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    clean_text = re.sub(r'\[[^\]]*\]', '', text).strip()
    body = {
        "text": clean_text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
    }
    try:
        resp = requests.post(url, headers=headers, json=body)
        resp.raise_for_status()
        with open(filename, "wb") as f:
            f.write(resp.content)
        print("  TTS OK: " + filename)
        return True
    except Exception as e:
        print("  TTS failed for " + filename + ": " + str(e))
        return False

def generate_segment_audio(seg_id, script):
    audio_dir = OUTPUT_DIR / "audio"
    audio_dir.mkdir(exist_ok=True)
    if isinstance(script, str):
        path = audio_dir / (seg_id + ".mp3")
        generate_tts(script, "charlie", str(path))
    elif isinstance(script, list):
        for i, line in enumerate(script):
            speaker = line.get("speaker", "charlie")
            text = line.get("text", "")
            path = audio_dir / (seg_id + "_line" + str(i) + ".mp3")
            generate_tts(text, speaker, str(path))
            time.sleep(1)

def main():
    print("ParkSyde Bright Side — " + DATE_STR)
    print("[1/3] Fetching news and writing scripts...")

    prompt = PROMPT_TEMPLATE.replace("__DAY__", DAY_NAME)

    data = None
    last_err = None
    for attempt in range(3):
        news_raw = claude(prompt=prompt, system=SYSTEM_PROMPT, max_tokens=4000, use_search=True)
        try:
            data = parse_bulletin(news_raw)
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
    for key in ["seg1_open","seg2_green","seg3_science","seg5_sports","seg6_outro"]:
        val = data.get(key, [])
        (OUTPUT_DIR / (key + ".json")).write_text(json.dumps(val, indent=2))
    seg4 = data.get("seg4_weather", "")
    (OUTPUT_DIR / "seg4_weather.txt").write_text(seg4)

    manifest = {
        "date": DATE_STR, "day": DAY_NAME,
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "stories": stories,
        "has_audio": bool(ELEVENLABS_API_KEY)
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    Path("output/latest.json").write_text(json.dumps(manifest, indent=2))

    print("[3/3] Generating TTS audio...")
    for seg_id in ["seg1_open","seg2_green","seg3_science","seg5_sports","seg6_outro"]:
        script = data.get(seg_id, [])
        generate_segment_audio(seg_id, script)
    generate_segment_audio("seg4_weather", data.get("seg4_weather", ""))

    if PARKSYDE_WEBHOOK:
        try:
            requests.post(PARKSYDE_WEBHOOK, json={
                "date": DATE_STR, "day": DAY_NAME,
                "scripts": {k: data.get(k) for k in ["seg1_open","seg2_green","seg3_science","seg4_weather","seg5_sports","seg6_outro"]},
                "stories": stories,
                "secret": os.environ.get("PARKSYDE_WEBHOOK_SECRET")
            }, timeout=30)
            print("Replit notified")
        except Exception as e:
            print("Replit ping failed: " + str(e))

    print("Done! Output in " + str(OUTPUT_DIR) + "/")

if __name__ == "__main__":
    main()
