"""
parksyde_filter.py
ParkSyde brand alignment scorer.
"""

PILLARS = {
    "community":   {"weight":1.2,"keywords":["community","volunteer","local","together","fundraise","charity","family","celebration","unity","support"]},
    "environment": {"weight":1.4,"keywords":["conservation","wildlife","nature","environment","renewable","solar","reef","forest","ocean","species","rewild","restore","mangrove","sustainable","ecosystem"]},
    "innovation":  {"weight":1.3,"keywords":["breakthrough","discovery","research","science","technology","innovation","medical","trial","engineers","researchers","scientists","first ever"]},
    "sport":       {"weight":1.2,"keywords":["sport","athlete","game","match","record","championship","olympic","cricket","football","rugby","basketball","tennis","swimming","marathon","nba","afl","nrl"]},
    "queensland":  {"weight":1.5,"keywords":["queensland","brisbane","gold coast","sunshine coast","cairns","moreton","sandstone point","qld","australia","australian","aussie","great barrier reef"]},
    "positivity":  {"weight":1.3,"keywords":["hope","triumph","overcome","recovery","saved","returned","comeback","milestone","achievement","success","inspiring","resilience","survived","thriving","restored","celebrated","historic"]}
}

EXCLUSIONS = ["death","killed","murder","war","conflict","disaster","crash","explosion","attack","terrorism","abuse","scandal","corruption","bankrupt","collapse","shooting","stabbing"]

def score_story(title, body="", segment=None):
    text = (title+" "+body).lower()
    for kw in EXCLUSIONS:
        if kw in text:
            return {"total_score":0,"passes":False,"exclusion_hit":kw}
    scores = {}
    for pillar, config in PILLARS.items():
        hits = sum(1 for kw in config["keywords"] if kw in text)
        scores[pillar] = round(hits * config["weight"], 2)
    total = round(sum(scores.values()), 2)
    return {"total_score":total,"pillar_scores":scores,"passes":total>=2.0,"exclusion_hit":None}

def rank_stories(stories, segment=None, top_n=3):
    scored = []
    for s in stories:
        r = score_story(s.get("title",""), s.get("body",""), segment)
        if r["passes"]:
            scored.append({**s,**r})
    return sorted(scored, key=lambda x: x["total_score"], reverse=True)[:top_n]

if __name__ == "__main__":
    tests = [
        {"title":"White rhinos return to Uganda after 50 years","body":"Conservation groups reintroduced southern white rhinos."},
        {"title":"Brisbane startup wins global clean energy award","body":"Queensland solar company named world leader."},
        {"title":"Man charged over property fraud","body":"Police arrested developer."},
    ]
    for t in tests:
        r = score_story(t["title"], t["body"])
        print(f"{'✓' if r['passes'] else '✗'} {t['title'][:50]} — score: {r['total_score']}")
