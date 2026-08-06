"""
zone_server.py

Tiny local server that lets zone_editor.html do CRUD on zones.json.

A browser page can't read/write files on your disk directly, so this
provides three small endpoints:

    GET  /                -> serves zone_editor.html
    GET  /api/zones        -> returns the current contents of zones.json
    POST /api/zones        -> overwrites zones.json with the posted data
    GET  /zone_reference.jpg -> serves the camera frame that
                                 detect_danger_zone.py refreshes about once
                                 a second, used as a near-live background
                                 image to draw zones on

Run this alongside (before or after) detect_danger_zone.py:

    pip install flask
    python zone_server.py

Then open http://localhost:5000 in a browser.

Both this server and detect_danger_zone.py read/write the SAME zones.json
file in this folder, so:
  - Zones drawn in the OpenCV window and confirmed with ENTER are saved to
    zones.json and will show up here.
  - Zones added/edited/deleted here and saved will be picked up automatically
    by detect_danger_zone.py while it's running (checked every couple of
    seconds), no restart needed.

Note: the live background image only updates while detect_danger_zone.py is
actually running - it owns the camera and writes zone_reference.jpg itself,
since most webcams only allow one program to access them at a time.
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
    resp = send_from_directory(BASE_DIR, "zone_reference.jpg")
    # This file is overwritten roughly once a second by detect_danger_zone.py
    # for the near-live editor view - make sure the browser doesn't cache it.
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/api/zones", methods=["GET"])
def get_zones():
    return jsonify(read_zones())


@app.route("/api/zones", methods=["POST"])
def save_zones():
    payload = request.get_json(force=True, silent=True)

    if payload is None or "zones" not in payload:
        return jsonify({"error": "Expected JSON body with a 'zones' array"}), 400

    # Basic validation so a bad request from the browser can't corrupt
    # zones.json for the detection script - a missing shape field here
    # would otherwise surface as a KeyError deep inside
    # detect_danger_zone.py's drawing/detection loop instead of a clean
    # error at save time.
    required_fields = {
        "rectangle": ("x1", "y1", "x2", "y2"),
        "circle": ("cx", "cy", "radius"),
        "freehand": ("points",),
    }

    for zone in payload["zones"]:
        zone_type = zone.get("type")
        if zone_type not in required_fields:
            return jsonify({"error": f"Invalid zone type: {zone_type}"}), 400
        if "id" not in zone or "maximum_people" not in zone:
            return jsonify({"error": "Each zone needs an 'id' and 'maximum_people'"}), 400

        missing = [f for f in required_fields[zone_type] if f not in zone]
        if missing:
            return jsonify({"error": f"Zone {zone.get('id')} ({zone_type}) is missing: {missing}"}), 400

        if zone_type == "freehand" and len(zone["points"]) < 3:
            return jsonify({"error": f"Zone {zone.get('id')} (freehand) needs at least 3 points"}), 400

    # Always clamp next_zone_id to be at least one past the highest id
    # actually present, instead of only filling it in when the field is
    # missing entirely - a stale/too-small value here (e.g. after zones
    # were deleted then new ones added client-side) could otherwise hand
    # out a duplicate id later.
    max_existing_id = max((z["id"] for z in payload["zones"]), default=0)
    payload["next_zone_id"] = max(payload.get("next_zone_id", 1), max_existing_id + 1)

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