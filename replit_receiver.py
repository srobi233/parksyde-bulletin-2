"""
replit_receiver.py
ParkSyde Bright Side - Replit Live Endpoint
"""
import os, json, datetime
from pathlib import Path
from flask import Flask, request, jsonify

app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get("PARKSYDE_WEBHOOK_SECRET", "")
STORAGE_DIR = Path("bulletins")
STORAGE_DIR.mkdir(exist_ok=True)
LATEST_FILE = STORAGE_DIR / "latest.json"

def verify(secret):
    if not WEBHOOK_SECRET: return True
    return secret == WEBHOOK_SECRET

def save(date_str, data):
    (STORAGE_DIR / f"{date_str}.json").write_text(json.dumps(data, indent=2))
    LATEST_FILE.write_text(json.dumps({"latest_date":date_str,"updated_at":datetime.datetime.utcnow().isoformat()+"Z"}))

def load(date_str):
    p = STORAGE_DIR / f"{date_str}.json"
    return json.loads(p.read_text()) if p.exists() else None

@app.route("/health")
def health():
    latest = json.loads(LATEST_FILE.read_text()) if LATEST_FILE.exists() else {}
    return jsonify({"status":"ok","latest_bulletin":latest.get("latest_date")})

@app.route("/bulletin/push", methods=["POST"])
def receive():
    data = request.get_json(force=True, silent=True)
    if not data: return jsonify({"error":"Invalid JSON"}), 400
    if not verify(data.get("secret","")): return jsonify({"error":"Unauthorized"}), 401
    date_str = data.get("date")
    if not date_str: return jsonify({"error":"Missing date"}), 400
    save(date_str, {"date":date_str,"day":data.get("day",""),"received_at":datetime.datetime.utcnow().isoformat()+"Z","stories":data.get("stories",{}),"scripts":data.get("scripts",{})})
    return jsonify({"status":"accepted","date":date_str}), 201

@app.route("/bulletin/latest")
def latest():
    if not LATEST_FILE.exists(): return jsonify({"error":"No bulletin yet"}), 404
    date_str = json.loads(LATEST_FILE.read_text()).get("latest_date")
    bulletin = load(date_str)
    return jsonify(bulletin) if bulletin else (jsonify({"error":"Not found"}), 404)

@app.route("/bulletin/<date_str>")
def by_date(date_str):
    bulletin = load(date_str)
    return jsonify(bulletin) if bulletin else (jsonify({"error":"Not found"}), 404)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
