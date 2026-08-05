"""
zone_server.py

Tiny local server that lets zone_editor.html do CRUD on zones.json.

A browser page can't read/write files on your disk directly, so this
provides three small endpoints:

    GET  /                -> serves zone_editor.html
    GET  /api/zones        -> returns the current contents of zones.json
    POST /api/zones        -> overwrites zones.json with the posted data
    GET  /zone_reference.jpg -> serves the camera snapshot saved by
                                 detect_danger_zone.py, used as the
                                 background image to draw zones on

Run this alongside (before or after) detect_danger_zone.py:

    pip install flask
    python zone_server.py

Then open http://localhost:5000 in a browser.

Both this server and detect_danger_zone.py read/write the SAME zones.json
file in this folder, so:
  - Zones drawn in the OpenCV window and confirmed with ENTER are saved to
    zones.json and will show up here.
  - Zones added/edited/deleted here and saved will be picked up the next
    time detect_danger_zone.py starts (it loads zones.json at launch).
"""

import json
import os
from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ZONES_FILE = os.path.join(BASE_DIR, "zones.json")
SNAPSHOT_FILE = os.path.join(BASE_DIR, "zone_reference.jpg")

app = Flask(__name__)


def read_zones():
    if not os.path.exists(ZONES_FILE):
        return {"next_zone_id": 1, "zones": []}
    try:
        with open(ZONES_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # Corrupt or unreadable file - don't crash the server, just hand
        # back an empty zone set so the editor still loads.
        return {"next_zone_id": 1, "zones": []}


def write_zones(data):
    with open(ZONES_FILE, "w") as f:
        json.dump(data, f, indent=2)


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "zone_editor.html")


@app.route("/zone_reference.jpg")
def snapshot():
    if not os.path.exists(SNAPSHOT_FILE):
        return jsonify({"error": "No snapshot yet - run detect_danger_zone.py once first"}), 404
    return send_from_directory(BASE_DIR, "zone_reference.jpg")


@app.route("/api/zones", methods=["GET"])
def get_zones():
    return jsonify(read_zones())


@app.route("/api/zones", methods=["POST"])
def save_zones():
    payload = request.get_json(force=True, silent=True)

    if payload is None or "zones" not in payload:
        return jsonify({"error": "Expected JSON body with a 'zones' array"}), 400

    # Basic validation so a bad request from the browser can't corrupt
    # zones.json for the detection script.
    valid_types = {"rectangle", "circle", "freehand"}
    for zone in payload["zones"]:
        if zone.get("type") not in valid_types:
            return jsonify({"error": f"Invalid zone type: {zone.get('type')}"}), 400
        if "id" not in zone or "maximum_people" not in zone:
            return jsonify({"error": "Each zone needs an 'id' and 'maximum_people'"}), 400

    if "next_zone_id" not in payload:
        payload["next_zone_id"] = (max((z["id"] for z in payload["zones"]), default=0) + 1)

    write_zones(payload)
    return jsonify({"status": "ok", "saved": len(payload["zones"])})


if __name__ == "__main__":
    print("=" * 60)
    print("Zone editor server")
    print("=" * 60)
    print(f"Zones file:     {ZONES_FILE}")
    print(f"Snapshot file:  {SNAPSHOT_FILE}")
    print("Open this in your browser:  http://localhost:5000")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=False)