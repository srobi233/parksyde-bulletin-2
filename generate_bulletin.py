#!/usr/bin/env python3
import os, json, datetime, requests, time
from pathlib import Path

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
PARKSYDE_WEBHOOK  = os.environ.get("PARKSYDE_WEBHOOK", "")
MODEL    = "claude-sonnet-4-20250514"
TODAY    = datetime.date.today()
DATE_STR = TODAY.strftime("%Y-%m-%d")
DAY_NAME = TODAY.strftime("%A, %B %-d")

OUTPUT_DIR = Path(f"output/{DATE_STR}")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "x-api-key": ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
    "Content-Type": "application/json"
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
            resp = requests.post("https://api.anthropic.com/v1/messages", headers=HEADERS, json=body, timeout=180)
            if resp.status_code == 429:
                wait = 60 * (attempt + 1)
                print(f"Rate limited — waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            return "\n".join(b["text"] for b in data.get("content", []) if b.get("type") == "text").strip()
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

def main():
    print(f"ParkSyde Bright Side — {DATE_STR}")

    # CALL 1: Fetch all news in one shot
    print("[1/2] Fetching news and writing scripts...")
    news_raw = claude(
        prompt=f"""Today is {DAY_NAME}. Search for today's most positive real news.
Then write a complete ParkSyde Bright Side bulletin script.

ParkSyde is a Queensland lifestyle brand. Pillars: environment, community, innovation, sport, QLD life, positivity.
Hosts: Alex Mercer (charlie voice, casual Aussie male) and Jamie Chen (alice voice, confident female).
Meteorologist: Sam (charlie voice). Warm dry Australian humour throughout.

Return ONLY this JSON structure, no other text:
{{
  "stories": {{
    "environment": ["story 1 headline", "story 2 headline"],
    "science": ["story 1 headline"],
    "sports": ["story 1 headline"],
    "overview": "awe-inspiring story headline"
  }},
  "seg1_open": [
    {{"speaker": "charlie", "text": "[Australian accent] G'day and welcome to ParkSyde. I'm Alex Mercer."}},
    {{"speaker": "alice", "text": "[Australian accent] And I'm Jamie Chen..."}},
    {{"speaker": "charlie", "text": "[Australian accent] Today on The Bright Side..."}}
  ],
  "seg2_green": [
    {{"speaker": "alice", "text": "[Australian accent] First up on the Green Desk..."}},
    {{"speaker": "charlie", "text": "[Australian accent] And in the UK..."}},
    {{"speaker": "alice", "text": "[Australian accent] Back to you legends at the desk."}}
  ],
  "seg3_science": [
    {{"speaker": "charlie", "text": "[Australian accent] Science and Tomorrow..."}},
    {{"speaker": "alice", "text": "[Australian accent] Researchers have..."}},
    {{"speaker": "charlie", "text": "[Australian accent] And one for breakfast lovers..."}}
  ],
  "seg4_weather": "[Australian accent] Cheers Alex and Jamie. Sam here at the weather desk... Back to you legends at the desk.",
  "seg5_sports": [
    {{"speaker": "charlie", "text": "[Australian accent] Time for The Scoreboard..."}},
    {{"speaker": "alice", "text": "[Australian accent] In the NBA..."}},
    {{"speaker": "charlie", "text": "[Australian accent] And in the Premier League..."}},
    {{"speaker": "alice", "text": "[Australian accent] That is why we love sport."}}
  ],
  "seg6_outro": [
    {{"speaker": "charlie", "text": "[Australian accent] Before we go..."}},
    {{"speaker": "alice", "text": "[Australian accent] The overview story..."}},
    {{"speaker": "charlie", "text": "[Australian accent] Puts it all in perspective."}},
    {{"speaker": "alice", "text": "[Australian accent] That's The Bright Side. I'm Jamie Chen."}},
    {{"speaker": "charlie", "text": "[Australian accent] And I'm Alex Mercer. ParkSyde rolls on."}}
  ]
}}

Use today's REAL news. Make each speaker line 2-4 natural spoken sentences. Include one dry Aussie quip per segment.""",
        system="You are the head writer for ParkSyde's Bright Side bulletin. Return valid JSON only. No markdown fences.",
        max_tokens=4000,
        use_search=True
    )

    # Parse
    try:
        data = json.loads(clean(news_raw))
    except Exception as e:
        print(f"JSON parse error: {e}\nRaw: {news_raw[:500]}")
        raise

    # Write outputs
    print("[2/2] Writing output files...")
    stories = data.get("stories", {})

    for key in ["seg1_open","seg2_green","seg3_science","seg5_sports","seg6_outro"]:
        val = data.get(key, [])
        (OUTPUT_DIR / f"{key}.json").write_text(json.dumps(val, indent=2))

    seg4 = data.get("seg4_weather", "")
    (OUTPUT_DIR / "seg4_weather.txt").write_text(seg4 if isinstance(seg4, str) else json.dumps(seg4))

    manifest = {
        "date": DATE_STR, "day": DAY_NAME,
        "generated_at": datetime.datetime.utcnow().isoformat()+"Z",
        "stories": stories
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    Path("output/latest.json").write_text(json.dumps({"latest_date": DATE_STR}))

    # Ping Replit
    if PARKSYDE_WEBHOOK:
        try:
            requests.post(PARKSYDE_WEBHOOK, json={
                "date": DATE_STR, "day": DAY_NAME,
                "scripts": {k: data.get(k) for k in ["seg1_open","seg2_green","seg3_science","seg4_weather","seg5_sports","seg6_outro"]},
                "stories": stories,
                "secret": os.environ.get("PARKSYDE_WEBHOOK_SECRET","")
            }, timeout=30)
            print("✓ Replit notified")
        except Exception as e:
            print(f"Replit ping failed: {e}")

    print(f"Done! Output in {OUTPUT_DIR}/")

if __name__ == "__main__":
    main()

