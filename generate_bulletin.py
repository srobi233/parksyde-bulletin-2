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

def extract_json(raw):
    """Pull the first valid JSON object out of a Claude response."""
    raw = raw.strip()
    # Strip code fences
    if "```json" in raw:
        raw = raw.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in raw:
        raw = raw.split("```", 1)[1].split("```", 1)[0]
    # Find the outermost { ... }
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in response")
    return raw[start:end + 1].strip()

def parse_bulletin(raw):
    """Parse JSON with a fallback that strips common bracket glitches."""
    candidate = extract_json(raw)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        print(f"First parse failed: {e}. Attempting cleanup...")
        # Remove stray [something] tags inside strings (stage directions etc)
        cleaned = re.sub(r'\[([A-Za-z][A-Za-z\s]{1,40})\]', '', candidate)
        return json.loads(cleaned)

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
    # Strip any residual stage directions before sending to TTS
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
        path = audio_dir / f"{seg_id}.mp3"
        generate_tts(script, "charlie", str(path))
    elif isinstance(script, list):
        for i, line in enumerate(script):
            speaker = line.get("speaker", "charlie")
            text = line.get("text", "")
            path = audio_dir / f"{seg_id}_line{i}.mp3"
            generate_tts(text, speaker, str(path))
            time.sleep(1)

def main():
    print(f"ParkSyde Bright Side — {DATE_STR}")

    print("[1/3] Fetching news and writing scripts...")

    prompt = f"""Today is {DAY_NAME}. Search for today's real news and write a complete ParkSyde Bright Side bulletin.

ParkSyde is a Queensland lifestyle brand. Pillars: environment, science, sports, weather.
Hosts: Alex Mercer (charlie voice, casual Aussie bloke). Co-host: Jamie (alice voice, upbeat).
Meteorologist: Sam (charlie voice). Warm dry Autumn weather in SE Queensland.

STRICT OUTPUT RULES:
- Return ONLY a single JSON object. No preamble, no markdown, no code fences.
- The "text" field of every line must contain ONLY the spoken words.
- Do NOT include stage directions, accent notes, or bracketed instructions (​​​​​​​​​​​​​​​​
