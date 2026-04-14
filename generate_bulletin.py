#!/usr/bin/env python3
import os, json, datetime, requests, time
from pathlib import Path

ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
PARKSYDE_WEBHOOK   = os.environ.get("PARKSYDE_WEBHOOK")
MODEL     = "claude-sonnet-4-20250514"
TODAY     = datetime.date.today()
DATE_STR  = TODAY.strftime("%Y-%m-%d")
DAY_NAME  = TODAY.strftime("%A, %B %-d")

OUTPUT_DIR = Path(f"output/{DATE_STR}")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "x-api-key": ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
    "Content-Type": "application/json"
}

# ElevenLabs voice IDs
VOICES = {
    "charlie": "IKne3meq5aSn9XLyUdCD",  # Charlie
    "alice":   "Xb7hH8MSUJpSbSDYk0k2",  # Alice
}

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
                print(f"Rate limited — waiting {wait}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            return "\n".join(
                b["text"] for b in data.get("content", [])
                if b.get("type") == "text"
            )
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            time.sleep(30)
    raise Exception("All retries failed")

def clean(raw):
    raw = raw.strip()
    for fence in ["```json", "```"]:
        if raw.startswith(fence): raw = raw[len(fence):]
    if raw.endswith("```"): raw = raw[:-3]
    return raw.strip()

def generate_tts(text, speaker, filename):
    """Generate audio via ElevenLabs and save as MP3."""
    if not ELEVENLABS_API_KEY:
        print(f"  No ElevenLabs key — skipping TTS")
        return False
    voice_id = VOICES.get(speaker, VOICES["charlie"])
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    # Strip the accent tag for TTS
    clean_text = text.replace("[Australian accent]", "").replace("[Australian acce", "")
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
        print(f"  ✓ TTS: {filename}")
        return True
    except Exception as e:
        print(f"  × TTS failed for {filename}: {e}")
        return False

def generate_segment_audio(seg_id, script):
    """Generate audio for each line in a segment."""
    audio_dir = OUTPUT_DIR / "audio"
    audio_dir.mkdir(exist_ok=True)
    if isinstance(script, str):
        # Weather segment — single speaker
        path = audio_dir / f"{seg_id}.mp3"
        generate_tts(script, "charlie", str(path))
    elif isinstance(script, list):
        for i, line in enumerate(script):
            speaker = line.get("speaker", "charlie")
            text = line.get("text", "")
            path = audio_dir / f"{seg_id}_line{i}.mp3"
            generate_tts(text, speaker, str(path))
            time.sleep(1)  # Avoid ElevenLabs rate limits

def main():
    print(f"ParkSyde Bright Side — {DATE_STR}")

    # CALL 1: Fetch news and write all scripts
    print("[1/3] Fetching news and writing scripts...")
    news_raw = claude(
        prompt=f"""Today is {DAY_NAME}. Search for today's real news and write a complete ParkSyde Bright Side bulletin.

ParkSyde is a Queensland lifestyle brand. Pillars: environment, science, sports, weather.
Hosts: Alex Mercer (charlie voice, casual Aussie bloke). Co-host: Jamie (alice voice, upbeat).
Meteorologist: Sam (charlie voice). Warm dry Autumn weather in SE Queensland.

Return ONLY this JSON structure, no other text:
{{
  "stories": {{
    "environment": ["story 1 headline", "story 2 headline"],
    "science": ["story 1 headline"],
    "sports": ["story 1 headline"],
    "overview": "awe-inspiring story headline"
  }},
  "seg1_open": [
    {{"speaker": "charlie", "text": "[Australian accent] ..."}},
    {{"speaker": "alice", "text": "[Australian accent] ..."}},
    {{"speaker": "charlie", "text": "[Australian accent] ..."}}
  ],
  "seg2_green": [
    {{"speaker": "alice", "text": "[Australian accent] ..."}},
    {{"speaker": "charlie", "text": "[Australian accent] ..."}},
    {{"speaker": "alice", "text": "[Australian accent] ..."}}
  ],
  "seg3_science": [
    {{"speaker": "charlie", "text": "[Australian accent] ..."}},
    {{"speaker": "alice", "text": "[Australian accent] ..."}},
    {{"speaker": "charlie", "text": "[Australian accent] ..."}}
  ],
  "seg4_weather": "[Australian accent] Cheers Alex...",
  "seg5_sports": [
    {{"speaker": "charlie", "text": "[Australian accent] ..."}},
    {{"speaker": "alice", "text": "[Australian accent] ..."}},
    {{"speaker": "charlie", "text": "[Australian accent] ..."}}
  ],
  "seg6_outro": [
    {{"speaker": "charlie", "text": "[Australian accent] ..."}},
    {{"speaker": "alice", "text": "[Australian accent] ..."}},
    {{"speaker": "charlie", "text": "[Australian accent] ..."}},
    {{"speaker": "alice", "text": "[Australian accent] ..."}},
    {{"speaker": "charlie", "text": "[Australian accent] ..."}}
  ]
}}

Use today's REAL news. Make each speaker line 2-3 sentences.""",
        system="You are the head writer for ParkSyde Bright Side, a daily good news bulletin.",
        max_tokens=4000,
        use_search=True
    )

    # Parse
    try:
        data = json.loads(clean(news_raw))
    except Exception as e:
        print(f"JSON parse error: {e}\nRaw: {news_raw[:500]}")
        raise

    # Write script files
    print("[2/3] Writing script files...")
    stories = data.get("stories", {})
    for key in ["seg1_open","seg2_green","seg3_science","seg5_sports","seg6_outro"]:
        val = data.get(key, [])
        (OUTPUT_DIR / f"{key}.json").write_text(json.dumps(val, indent=2))
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

    # Generate TTS audio
    print("[3/3] Generating TTS audio...")
    for seg_id in ["seg1_open","seg2_green","seg3_science","seg5_sports","seg6_outro"]:
        script = data.get(seg_id, [])
        generate_segment_audio(seg_id, script)
    generate_segment_audio("seg4_weather", data.get("seg4_weather", ""))

    # Ping Replit
    if PARKSYDE_WEBHOOK:
        try:
            requests.post(PARKSYDE_WEBHOOK, json={
                "date": DATE_STR, "day": DAY_NAME,
                "scripts": {k: data.get(k) for k in ["seg1_open","seg2_green","seg3_science","seg4_weather","seg5_sports","seg6_outro"]},
                "stories": stories,
                "secret": os.environ.get("PARKSYDE_WEBHOOK_SECRET")
            }, timeout=30)
            print("✓ Replit notified")
        except Exception as e:
            print(f"Replit ping failed: {e}")

    print(f"✅ Done! Output in {OUTPUT_DIR}/")

if __name__ == "__main__":
    main()
