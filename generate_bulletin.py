#!/usr/bin/env python3
import os, json, datetime, requests, sys
from pathlib import Path

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
PARKSYDE_WEBHOOK  = os.environ.get("PARKSYDE_WEBHOOK", "")
MODEL             = "claude-opus-4-5"
TODAY             = datetime.date.today()
DATE_STR          = TODAY.strftime("%Y-%m-%d")
DAY_NAME          = TODAY.strftime("%A, %B %-d")

OUTPUT_DIR = Path(f"output/{DATE_STR}")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "x-api-key": ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
    "Content-Type": "application/json"
}

PARKSYDE_CONTEXT = """
ParkSyde is a Queensland-based community lifestyle development brand.
Pillars: environment, community, innovation, sport, QLD life, positivity.
The Bright Side is ParkSyde's daily upbeat news bulletin.
Hosts: Alex Mercer (charlie voice) and Jamie Chen (alice voice).
Meteorologist: Sam (charlie voice). Warm dry Australian humour throughout.
"""

def claude(messages, system="", max_tokens=4096, use_search=False):
    body = {"model": MODEL, "max_tokens": max_tokens, "messages": messages}
    if system: body["system"] = system
    if use_search: body["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]
    resp = requests.post("https://api.anthropic.com/v1/messages", headers=HEADERS, json=body, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return "\n".join(b["text"] for b in data.get("content", []) if b.get("type") == "text").strip()

def clean_json(raw):
    raw = raw.strip()
    if raw.startswith("```"): raw = "\n".join(raw.split("\n")[1:])
    if raw.endswith("```"): raw = "\n".join(raw.split("\n")[:-1])
    return raw.strip()

def fetch_news():
    print("\n[1/4] Fetching today's news...")
    prompt = f"""Today is {DAY_NAME}. Find today's most positive news in these categories.
Return ONLY valid JSON:
{{
  "environment": [{{"title":"...","summary":"2-3 sentences","location":"...","source":"..."}}],
  "science": [{{"title":"...","summary":"2-3 sentences","source":"..."}}],
  "weather": {{
    "europe": {{"summary":"current positive conditions"}},
    "queensland": {{"summary":"SEQ conditions","detail":"temp, humidity, outlook","location":"specific QLD spot"}}
  }},
  "sports": [{{"title":"...","summary":"...","sport":"NBA/AFL/NRL/EPL/etc","source":"..."}}],
  "overview_story": {{"title":"...","summary":"3-4 sentences, awe-inspiring","source":"..."}}
}}
Find 3 stories per category. Prioritise positive outcomes. Real stories only."""
    raw = claude([{"role":"user","content":prompt}], system=f"News researcher for ParkSyde.\n{PARKSYDE_CONTEXT}\nReturn valid JSON only.", max_tokens=3000, use_search=True)
    return json.loads(clean_json(raw))

def score_and_select(news):
    print("[2/4] Filtering stories...")
    bad = ["death","killed","murder","war","disaster","explosion","attack","abuse","scandal","corruption","shooting"]
    def ok(t, s): return not any(w in (t+" "+s).lower() for w in bad)
    return {
        "environment": [s for s in news.get("environment",[]) if ok(s["title"],s["summary"])][:3],
        "science":     [s for s in news.get("science",[])     if ok(s["title"],s["summary"])][:3],
        "sports":      [s for s in news.get("sports",[])      if ok(s["title"],s["summary"])][:2],
        "weather":     news.get("weather",{}),
        "overview":    news.get("overview_story",{})
    }

def generate_scripts(sel):
    print("[3/4] Writing scripts...")
    sys_prompt = f"Head writer for ParkSyde Bright Side.\n{PARKSYDE_CONTEXT}\nToday is {DAY_NAME}.\nReturn valid JSON only. No markdown."

    def seg(prompt, max_tokens=800):
        raw = claude([{"role":"user","content":prompt}], system=sys_prompt, max_tokens=max_tokens)
        try: return json.loads(clean_json(raw))
        except: return [{"speaker":"charlie","text":f"[Australian accent] {raw}"}]

    env = "\n".join(f"- {s['title']}: {s['summary']}" for s in sel["environment"])
    sci = "\n".join(f"- {s['title']}: {s['summary']}" for s in sel["science"])
    spt = "\n".join(f"- {s['title']}: {s['summary']} ({s.get('sport','')})" for s in sel["sports"])
    wx  = sel["weather"]
    ov  = sel["overview"]

    s1 = seg(f'Write The Open (~40s). Tease these stories: env={sel["environment"][0]["title"] if sel["environment"] else ""}, sci={sel["science"][0]["title"] if sel["science"] else ""}, sport={sel["sports"][0]["title"] if sel["sports"] else ""}.\nReturn JSON: [{{"speaker":"charlie","text":"[Australian accent] ..."}},{{"speaker":"alice","text":"..."}},{{"speaker":"charlie","text":"..."}}]')
    s2 = seg(f'Write The Green Desk (~90s) covering:\n{env}\nJamie(alice) leads, alternate with Alex(charlie), Jamie closes.\nReturn JSON array of 3 speaker turns.')
    s3 = seg(f'Write Science & Tomorrow (~90s) covering:\n{sci}\nAlex(charlie) leads, alternate with Jamie(alice).\nReturn JSON array of 3-4 speaker turns.')
    s4_raw = claude([{"role":"user","content":f'Write Global Weather Desk (~60s) for Sam(charlie). Europe: {wx.get("europe",{}).get("summary","")}. QLD: {wx.get("queensland",{}).get("detail","")} near {wx.get("queensland",{}).get("location","Sandstone Point QLD")}. End with "Back to you legends at the desk." Return plain text only starting with [Australian accent]'}], system=sys_prompt, max_tokens=400)
    s5 = seg(f'Write The Scoreboard (~80s) covering:\n{spt}\nAlex(charlie) opens with energy, alternate, Jamie(alice) closes.\nReturn JSON array of 4 speaker turns.')
    s6 = seg(f'Write The Overview & Outro (~60s). Story: {ov.get("title","")}: {ov.get("summary","")}. Alex sets up, Jamie delivers facts, Alex reflects, Jamie signs off as Jamie Chen, Alex closes as Alex Mercer for ParkSyde.\nReturn JSON array of 5 speaker turns.')

    return {"seg1_open":s1,"seg2_green":s2,"seg3_science":s3,"seg4_weather":s4_raw.strip(),"seg5_sports":s5,"seg6_outro":s6}

def write_outputs(scripts, sel):
    print(f"[4/4] Writing to {OUTPUT_DIR}/...")
    for key, data in scripts.items():
        if key == "seg4_weather":
            (OUTPUT_DIR / "seg4_weather.txt").write_text(data)
        else:
            (OUTPUT_DIR / f"{key}.json").write_text(json.dumps(data, indent=2))
    manifest = {
        "date": DATE_STR, "day": DAY_NAME,
        "generated_at": datetime.datetime.utcnow().isoformat()+"Z",
        "stories": {"environment":[s["title"] for s in sel["environment"]],"science":[s["title"] for s in sel["science"]],"sports":[s["title"] for s in sel["sports"]],"overview":sel["overview"].get("title","")}
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    Path("output/latest.json").write_text(json.dumps({"latest_date":DATE_STR}))
    if PARKSYDE_WEBHOOK:
        try:
            requests.post(PARKSYDE_WEBHOOK, json={"date":DATE_STR,"day":DAY_NAME,"scripts":scripts,"stories":sel,"secret":os.environ.get("PARKSYDE_WEBHOOK_SECRET","")}, timeout=30)
            print("  ✓ Replit notified")
        except Exception as e:
            print(f"  ✗ Replit ping failed: {e}")

def main():
    print(f"ParkSyde Bright Side — {DATE_STR}")
    news = fetch_news()
    sel  = score_and_select(news)
    scripts = generate_scripts(sel)
    write_outputs(scripts, sel)
    print("✅ Done!")

if __name__ == "__main__":
    main()
