"""
Danger Zone Detection System
Detects when a person enters a marked danger zone and triggers an alarm
"""

from ultralytics import YOLO
import cv2
import winsound
import os
import serial
import time
import math
import csv
import datetime
import json
import numpy as np
from deepface import DeepFace

# -------------------- ARDUINO SETUP --------------------

ENABLE_ARDUINO_BUZZER = True  # Set to False to use system beep instead
ARDUINO_PORT = "COM5"  # ✓ Detected Arduino Nano on COM5
ARDUINO_BAUD = 9600

arduino = None

if ENABLE_ARDUINO_BUZZER:
    try:
        arduino = serial.Serial(ARDUINO_PORT, ARDUINO_BAUD, timeout=1)
        time.sleep(2)  # Wait for Arduino to initialize
        print(f"✓ Arduino connected on {ARDUINO_PORT}")
    except Exception as e:
        print(f"⚠ Arduino connection failed: {e}")
        print("  Falling back to system beep")
        ENABLE_ARDUINO_BUZZER = False
        arduino = None

# -------------------- BUILD/LOAD MODEL --------------------

print("=" * 60)
print("LOADING YOLO MODEL")
print("=" * 60)

MODEL_PATH = "danger_zone_model.pt"

if not os.path.exists(MODEL_PATH):
    print(f"✗ Model not found: {MODEL_PATH}")
    print("\nPlease run 'python train_model.py' first to create the model")
    print("(Choose option 1 for quick setup with pre-trained model)")
    exit(1)

model = YOLO(MODEL_PATH)
print(f"✓ Model loaded successfully: {MODEL_PATH}")
print("=" * 60)

# -------------------- LOAD FACE CASCADE SAFELY --------------------

CASCADE_PATH = "haarcascade_frontalface_default.xml"
face_cascade = cv2.CascadeClassifier(CASCADE_PATH)

if face_cascade.empty():
    # Try to load from OpenCV data directory
    cascade_file = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_cascade = cv2.CascadeClassifier(cascade_file)

    if face_cascade.empty():
        print("WARNING: Haarcascade not loaded. Face filter disabled.")
        face_cascade = None
    else:
        print(f"✓ Face cascade loaded from OpenCV data")
else:
    print(f"✓ Face cascade loaded: {CASCADE_PATH}")

# -------------------- CAMERA --------------------

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("✗ Error: Could not open camera")
    exit(1)

print("✓ Camera initialized")

# The HTML zone editor displays this file as its background so you can draw
# zones on top of it. It's refreshed periodically from inside the main loop
# below (see refresh_editor_snapshot()) rather than captured once here, so
# the editor shows a near-live view instead of a one-time-only photo.
SNAPSHOT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zone_reference.jpg")

# -------------------- ALARM --------------------

alarm_path = os.path.join(os.path.dirname(__file__), "alarm.wav")

# Check if alarm file exists, if not create a simple beep alternative
if not os.path.exists(alarm_path):
    print(f"⚠ Alarm file not found: {alarm_path}")
    print("  Using system beep instead")
    alarm_path = None  # Will use winsound.Beep() instead

# -------------------- SETTINGS --------------------

ENABLE_AGE_DETECTION = False     # True → child-only mode
AGE_THRESHOLD = 14

# DeepFace age analysis is expensive (often 100-300ms per call). Running it
# on every detected person on every single frame tanks real FPS. Instead,
# only run it once every AGE_CHECK_INTERVAL frames; on the frames in
# between, fall back to the last known age/child classification for that
# detection area (or a safe "treat as person" default if none exists yet).
AGE_CHECK_INTERVAL = 5
frame_counter = 0

# Cache of the last age-analysis result per rough screen position (grid
# cell), so frames that skip the DeepFace call can still show a sensible
# label/color instead of re-running the expensive analysis every frame.
AGE_CACHE_GRID = 80  # pixels per grid cell
age_result_cache = {}

print("\n" + "=" * 60)
print("CONFIGURATION")
print("=" * 60)
print(f"Age detection: {'ENABLED' if ENABLE_AGE_DETECTION else 'DISABLED'}")
print(f"Age threshold: {AGE_THRESHOLD} years")
print(f"Face filter: {'ENABLED' if face_cascade is not None else 'DISABLED'}")
print("=" * 60)

# -------------------- ZONE DRAWING --------------------

drawing = False
ix, iy = -1, -1
ZONES = []
current_zone = None

alarm_triggered = False
detection_started = False

# zones.json lives next to this script. The HTML editor (zone_editor.html +
# zone_server.py) reads and writes the same file, so zones created here in
# OpenCV can be edited there, and edits made there are picked up here.
ZONES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zones.json")


def save_zones_to_file():
    """Persist current ZONES + next id to zones.json."""
    global _next_zone_id, _zones_mtime
    try:
        with open(ZONES_FILE, "w") as f:
            json.dump({"next_zone_id": _next_zone_id, "zones": ZONES}, f, indent=2)
        _zones_mtime = os.path.getmtime(ZONES_FILE)
        print(f"✓ Zones saved to {ZONES_FILE}")
    except Exception as e:
        print(f"✗ Could not save zones.json: {e}")


def load_zones_from_file():
    """Load zones previously saved by this script, or edited via the HTML CRUD editor."""
    global ZONES, _next_zone_id
    if not os.path.exists(ZONES_FILE):
        return
    try:
        with open(ZONES_FILE, "r") as f:
            data = json.load(f)
        ZONES = data.get("zones", [])
        _next_zone_id = data.get("next_zone_id", len(ZONES) + 1)
        print(f"✓ Loaded {len(ZONES)} zone(s) from {ZONES_FILE}")
    except Exception as e:
        print(f"✗ Could not load zones.json: {e}")


# -------------------- LIVE ZONE HOT-RELOAD --------------------
# Lets zones.json be edited via zone_editor.html while detect_danger_zone.py
# is already running, without needing to restart the script. We only stat()
# the file (cheap) every ZONE_RELOAD_CHECK_SECONDS, and only actually
# re-parse/reload it if its modification time changed since the last check.

ZONE_RELOAD_CHECK_SECONDS = 2.0
_zones_mtime = os.path.getmtime(ZONES_FILE) if os.path.exists(ZONES_FILE) else 0
_last_zone_check_time = 0.0


def check_for_live_zone_updates():
    """Call once per main-loop iteration. Reloads ZONES from disk if the
    HTML editor (or another process) has saved a newer zones.json since we
    last checked."""
    global _zones_mtime, _last_zone_check_time

    now = time.time()
    if now - _last_zone_check_time < ZONE_RELOAD_CHECK_SECONDS:
        return
    _last_zone_check_time = now

    if not os.path.exists(ZONES_FILE):
        return

    mtime = os.path.getmtime(ZONES_FILE)
    if mtime == _zones_mtime:
        return  # unchanged since last check

    _zones_mtime = mtime

    # Close out any in-progress incident recordings before swapping the
    # zone list out from under them - old zone ids may no longer exist
    # (or may now mean something different) after the reload.
    finalize_all_active_incidents()
    load_zones_from_file()
    print("↻ zones.json changed on disk - live-reloaded zones")


# -------------------- LIVE EDITOR SNAPSHOT --------------------
# Overwrites zone_reference.jpg with the current frame on a throttled
# interval, so the HTML editor can poll it and show a near-live view
# instead of a one-time-only photo. Written to a temp file first and then
# swapped into place (os.replace is atomic on both Windows and Linux), so
# zone_server.py never serves a half-written/corrupt JPEG mid-write.

SNAPSHOT_REFRESH_SECONDS = 1.0
_last_snapshot_time = 0.0
_snapshot_warned = False


def refresh_editor_snapshot(raw_frame):
    """Call once per main-loop iteration with the raw (un-annotated) frame."""
    global _last_snapshot_time, _snapshot_warned

    now = time.time()
    if now - _last_snapshot_time < SNAPSHOT_REFRESH_SECONDS:
        return
    _last_snapshot_time = now

    try:
        # Keep the .jpg extension on the temp file - cv2.imwrite picks its
        # encoder from the filename's extension, so something like
        # "zone_reference.jpg.tmp" (ending in .tmp) fails silently with no
        # encoder found. "zone_reference_tmp.jpg" still ends in .jpg.
        base, ext = os.path.splitext(SNAPSHOT_FILE)
        tmp_path = f"{base}_tmp{ext}"

        ok = cv2.imwrite(tmp_path, raw_frame)
        if not ok:
            raise RuntimeError("cv2.imwrite returned False")
        os.replace(tmp_path, SNAPSHOT_FILE)
        _snapshot_warned = False

    except Exception as e:
        # Non-critical - the editor just won't have an up-to-the-second
        # frame this cycle. Don't let a snapshot hiccup crash detection,
        # but do warn once so a persistent failure isn't silently invisible.
        if not _snapshot_warned:
            print(f"⚠ Could not update {SNAPSHOT_FILE} for the HTML editor: {e}")
            _snapshot_warned = True

# -------------------- DRAWING TOOL SELECTOR --------------------

# Currently selected drawing tool: "rectangle", "circle", or "freehand"
CURRENT_TOOL = "rectangle"

# Freehand path being drawn right now (list of (x, y) points)
freehand_points = []

# Toolbar button definitions: (label, tool_id, x1, y1, x2, y2)
TOOLBAR_BUTTONS = [
    ("Rectangle", "rectangle", 10, 10, 130, 45),
    ("Circle", "circle", 10, 55, 130, 90),
    ("Freehand", "freehand", 10, 100, 130, 135),
]


def point_in_button(x, y, bx1, by1, bx2, by2):
    return bx1 <= x <= bx2 and by1 <= y <= by2


def draw_toolbar(frame):
    """Draw the floating tool-selector toolbar in the top-left corner."""
    for label, tool_id, bx1, by1, bx2, by2 in TOOLBAR_BUTTONS:
        is_selected = (tool_id == CURRENT_TOOL)

        # Highlight the currently selected tool
        bg_color = (0, 200, 0) if is_selected else (60, 60, 60)
        text_color = (255, 255, 255)
        border_color = (0, 255, 255) if is_selected else (200, 200, 200)

        cv2.rectangle(frame, (bx1, by1), (bx2, by2), bg_color, -1)
        cv2.rectangle(frame, (bx1, by1), (bx2, by2), border_color, 2)

        text_x = bx1 + 8
        text_y = by1 + 23
        cv2.putText(frame, label, (text_x, text_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, text_color, 1, cv2.LINE_AA)


# -------------------- MAX PEOPLE PER ZONE --------------------

DEFAULT_MAX_PEOPLE = 0
_next_zone_id = 1  # Simple incrementing id for each new zone


def ask_max_people():
    """
    Small OpenCV popup dialog asking the user for the maximum number of
    people allowed inside the zone that was just drawn.

    - Digit keys build up the number.
    - BACKSPACE removes the last digit.
    - ENTER confirms the typed value.
    - ESC, closing the window, or an empty/invalid entry falls back to
      DEFAULT_MAX_PEOPLE (0).
    """
    win_name = "Max People Input"
    input_str = ""

    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)

    result = DEFAULT_MAX_PEOPLE

    while True:
        popup = np.zeros((150, 420, 3), dtype=np.uint8)
        cv2.putText(popup, "Maximum people allowed?", (15, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        cv2.putText(popup, input_str if input_str else "_", (15, 95),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        cv2.putText(popup, "ENTER = confirm   ESC = default (0)", (15, 135),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

        cv2.imshow(win_name, popup)

        # If the user closed the popup window directly, fall back to default
        try:
            if cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) < 1:
                result = DEFAULT_MAX_PEOPLE
                break
        except cv2.error:
            result = DEFAULT_MAX_PEOPLE
            break

        key = cv2.waitKey(0) & 0xFF

        if key == 27:  # ESC -> default
            result = DEFAULT_MAX_PEOPLE
            break

        elif key == 13 or key == 10:  # ENTER -> confirm
            if input_str == "":
                result = DEFAULT_MAX_PEOPLE
            else:
                try:
                    value = int(input_str)
                    result = value if value >= 0 else DEFAULT_MAX_PEOPLE
                except ValueError:
                    result = DEFAULT_MAX_PEOPLE
            break

        elif key in (8, 127):  # BACKSPACE -> remove last digit
            input_str = input_str[:-1]

        elif 48 <= key <= 57:  # digits 0-9
            if len(input_str) < 5:
                input_str += chr(key)

        # any other key is ignored

    try:
        cv2.destroyWindow(win_name)
    except cv2.error:
        pass

    return result


def finish_zone_with_limit(zone_data):
    """
    Called right after a shape (rectangle/circle/freehand) is finished.
    Prompts for the maximum-people limit, tags the zone with an id,
    and appends it to the global ZONES list.
    """
    global ZONES, _next_zone_id

    max_people = ask_max_people()

    zone_data["id"] = _next_zone_id
    zone_data["maximum_people"] = max_people
    _next_zone_id += 1

    ZONES.append(zone_data)


# -------------------- MOUSE CALLBACK --------------------

def draw_zone(event, x, y, flags, param):
    global ix, iy, drawing, current_zone, ZONES, detection_started
    global CURRENT_TOOL, freehand_points

    if detection_started:
        return

    # ---------- TOOLBAR CLICK HANDLING ----------
    if event == cv2.EVENT_LBUTTONDOWN:
        for label, tool_id, bx1, by1, bx2, by2 in TOOLBAR_BUTTONS:
            if point_in_button(x, y, bx1, by1, bx2, by2):
                CURRENT_TOOL = tool_id
                return  # Toolbar click consumed, don't start drawing a shape

    # ---------- RECTANGLE ----------
    if CURRENT_TOOL == "rectangle":
        if event == cv2.EVENT_LBUTTONDOWN:
            drawing = True
            ix, iy = x, y

        elif event == cv2.EVENT_MOUSEMOVE:
            if drawing:
                current_zone = {"type": "rectangle", "x1": ix, "y1": iy, "x2": x, "y2": y}

        elif event == cv2.EVENT_LBUTTONUP:
            if drawing:
                drawing = False
                current_zone = None
                finish_zone_with_limit({"type": "rectangle", "x1": ix, "y1": iy, "x2": x, "y2": y})

    # ---------- CIRCLE ----------
    elif CURRENT_TOOL == "circle":
        if event == cv2.EVENT_LBUTTONDOWN:
            drawing = True
            ix, iy = x, y

        elif event == cv2.EVENT_MOUSEMOVE:
            if drawing:
                radius = int(math.hypot(x - ix, y - iy))
                current_zone = {"type": "circle", "cx": ix, "cy": iy, "radius": radius}

        elif event == cv2.EVENT_LBUTTONUP:
            if drawing:
                drawing = False
                radius = int(math.hypot(x - ix, y - iy))
                current_zone = None
                finish_zone_with_limit({"type": "circle", "cx": ix, "cy": iy, "radius": radius})

    # ---------- FREEHAND ----------
    elif CURRENT_TOOL == "freehand":
        if event == cv2.EVENT_LBUTTONDOWN:
            drawing = True
            freehand_points = [(x, y)]
            current_zone = {"type": "freehand", "points": freehand_points}

        elif event == cv2.EVENT_MOUSEMOVE:
            if drawing:
                freehand_points.append((x, y))
                current_zone = {"type": "freehand", "points": freehand_points}

        elif event == cv2.EVENT_LBUTTONUP:
            if drawing:
                drawing = False
                if len(freehand_points) >= 3:
                    finish_zone_with_limit({"type": "freehand", "points": list(freehand_points)})
                freehand_points = []
                current_zone = None


cv2.namedWindow("Child Safety Detector", cv2.WINDOW_NORMAL)
cv2.setWindowProperty("Child Safety Detector", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
cv2.setMouseCallback("Child Safety Detector", draw_zone)

# Pick up zones saved from a previous run, or edited via the HTML CRUD
# editor (zone_editor.html + zone_server.py), so you don't have to redraw
# them by hand in OpenCV every time.
load_zones_from_file()
if ZONES:
    print(f"\n✓ {len(ZONES)} zone(s) loaded from zones.json - press ENTER to use them as-is,")
    print("  or draw more / edit further before confirming.")

print("\n" + "=" * 60)
print("INSTRUCTIONS")
print("=" * 60)
print("1. Choose a drawing tool from the toolbar (Rectangle / Circle / Freehand)")
print("2. Draw danger zones using mouse (click and drag)")
print("3. Press ENTER to start detection")
print("4. Press 'R' to reset zones")
print("5. Press ESC to exit")
print("=" * 60)
print("\nSTARTING APPLICATION...\n")

# -------------------- HELPER FUNCTIONS --------------------

def play_alarm():
    """Trigger 15V buzzer via Arduino"""
    global arduino

    # IF-ELSE condition to check if Arduino is available
    if ENABLE_ARDUINO_BUZZER and arduino:
        try:
            arduino.write(b'1')  # Send '1' to Arduino to turn ON buzzer
            print("✓ Buzzer triggered (Arduino)")
        except Exception as e:
            print(f"Error sending to Arduino: {e}")
            # Fallback to system beep
            winsound.Beep(1000, 500)
    else:
        # Fallback to system beep if Arduino not available
        try:
            winsound.Beep(1000, 500)  # 1000 Hz for 500ms
            print("✓ Alarm beep triggered (System)")
        except Exception as e:
            print(f"Warning: Could not play alarm - {e}")


def stop_alarm():
    """Stop 15V buzzer via Arduino"""
    global arduino

    # IF-ELSE condition to check if Arduino is available
    if ENABLE_ARDUINO_BUZZER and arduino:
        try:
            arduino.write(b'0')  # Send '0' to Arduino to turn OFF buzzer
            print("✓ Buzzer stopped (Arduino)")
        except Exception as e:
            print(f"Error sending to Arduino: {e}")
    else:
        # Stop system beep
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
            print("✓ Alarm stopped (System)")
        except:
            pass


def draw_shape(frame, zone, color, thickness):
    """Draw a single zone (rectangle / circle / freehand) on the frame."""
    shape_type = zone.get("type")

    if shape_type == "rectangle":
        cv2.rectangle(frame, (zone["x1"], zone["y1"]), (zone["x2"], zone["y2"]), color, thickness)

    elif shape_type == "circle":
        cv2.circle(frame, (zone["cx"], zone["cy"]), zone["radius"], color, thickness)

    elif shape_type == "freehand":
        points = zone.get("points", [])
        if len(points) > 1:
            pts_array = np.array(points, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(frame, [pts_array], isClosed=True, color=color, thickness=thickness)


def zone_bounding_box(zone):
    """Return (zx1, zy1, zx2, zy2) bounding box for any zone shape."""
    shape_type = zone.get("type")

    if shape_type == "rectangle":
        # Normalize so zx1<zx2, zy1<zy2 regardless of which corner the zone
        # was dragged from - person_in_zone_check's overlap test assumes
        # this ordering, otherwise a bottom-right -> top-left drag silently
        # breaks detection for that zone.
        x1, x2 = sorted((zone["x1"], zone["x2"]))
        y1, y2 = sorted((zone["y1"], zone["y2"]))
        return x1, y1, x2, y2

    elif shape_type == "circle":
        cx, cy, r = zone["cx"], zone["cy"], zone["radius"]
        return cx - r, cy - r, cx + r, cy + r

    elif shape_type == "freehand":
        points = zone.get("points", [])
        if not points:
            return 0, 0, 0, 0
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return min(xs), min(ys), max(xs), max(ys)

    return 0, 0, 0, 0


def zone_contains_point(x, y, zone):
    """
    Precise point-in-shape test for circle and freehand zones.
    Circle: standard distance-from-center <= radius check.
    Freehand: cv2.pointPolygonTest against the drawn outline (treated as a
    closed polygon), so points outside the actual traced shape but inside
    its bounding box are correctly excluded.
    """
    shape_type = zone.get("type")

    if shape_type == "circle":
        cx, cy, r = zone["cx"], zone["cy"], zone["radius"]
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r

    elif shape_type == "freehand":
        points = zone.get("points", [])
        if len(points) < 3:
            return False
        pts_array = np.array(points, dtype=np.int32).reshape((-1, 1, 2))
        return cv2.pointPolygonTest(pts_array, (float(x), float(y)), False) >= 0

    return False


def _rect_circle_overlap(px1, py1, px2, py2, cx, cy, r):
    """True rectangle-vs-circle intersection: find the point on the box
    closest to the circle's center, then check if that point is within
    the radius."""
    closest_x = max(px1, min(cx, px2))
    closest_y = max(py1, min(cy, py2))
    dx, dy = cx - closest_x, cy - closest_y
    return (dx * dx + dy * dy) <= r * r


def _segments_intersect(a1, a2, b1, b2):
    """Standard orientation-based line-segment intersection test."""
    def orientation(p, q, r):
        val = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
        if val == 0:
            return 0
        return 1 if val > 0 else 2

    def on_segment(p, q, r):
        return (min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and
                min(p[1], r[1]) <= q[1] <= max(p[1], r[1]))

    o1, o2 = orientation(a1, a2, b1), orientation(a1, a2, b2)
    o3, o4 = orientation(b1, b2, a1), orientation(b1, b2, a2)

    if o1 != o2 and o3 != o4:
        return True
    if o1 == 0 and on_segment(a1, b1, a2):
        return True
    if o2 == 0 and on_segment(a1, b2, a2):
        return True
    if o3 == 0 and on_segment(b1, a1, b2):
        return True
    if o4 == 0 and on_segment(b1, a2, b2):
        return True
    return False


def _rect_polygon_overlap(px1, py1, px2, py2, points):
    """True rectangle-vs-polygon intersection: covers full containment
    either way, plus partial edge-crossing overlap (e.g. the zone outline
    cuts across a corner of the person's box without either shape being
    fully inside the other)."""
    if len(points) < 3:
        return False

    box_corners = [(px1, py1), (px2, py1), (px2, py2), (px1, py2)]
    freehand_zone = {"type": "freehand", "points": points}

    # Any polygon vertex inside the box.
    for (x, y) in points:
        if px1 <= x <= px2 and py1 <= y <= py2:
            return True

    # Any box corner inside the polygon (covers the box being fully
    # inside the polygon, or the polygon fully inside the box).
    for corner in box_corners:
        if zone_contains_point(corner[0], corner[1], freehand_zone):
            return True

    # Any box edge crossing any polygon edge (covers partial overlap
    # where neither shape contains a vertex of the other).
    n = len(points)
    for i in range(n):
        p3, p4 = points[i], points[(i + 1) % n]
        for j in range(4):
            b1, b2 = box_corners[j], box_corners[(j + 1) % 4]
            if _segments_intersect(b1, b2, p3, p4):
                return True

    return False


def person_in_zone_check(px1, py1, px2, py2, zone):
    """
    Check whether a detected person's bounding box overlaps the given zone.
    All three shapes now use true geometric overlap against the person's
    full box (not a single reference point), so a zone drawn over any part
    of a person - not just their feet - correctly counts them as inside.
    This matters for close-range/webcam framing where a person's box can
    extend well beyond the visible frame in either direction, not just
    top-down/floor-level camera setups.
    """
    shape_type = zone.get("type")

    if shape_type == "rectangle":
        zx1, zy1, zx2, zy2 = zone_bounding_box(zone)
        return px1 < zx2 and px2 > zx1 and py1 < zy2 and py2 > zy1

    elif shape_type == "circle":
        cx, cy, r = zone["cx"], zone["cy"], zone["radius"]
        return _rect_circle_overlap(px1, py1, px2, py2, cx, cy, r)

    elif shape_type == "freehand":
        return _rect_polygon_overlap(px1, py1, px2, py2, zone.get("points", []))


# ==================== SMART INCIDENT EVIDENCE STORAGE ====================
#
# Nothing here ever runs unless a zone actually exceeds its maximum-people
# limit. No folders, files, or logs are created for a clean/compliant frame.

EVIDENCE_ROOT = "evidence"
CSV_FIELDNAMES = [
    "Date", "Time", "Zone ID", "Zone Name",
    "People Count", "Allowed Count", "Image", "Video", "Status",
]

# Per-zone incident state, keyed by zone id. Only populated once a zone's
# FIRST violation happens.
zone_incident_state = {}


def get_zone_display_name(zone):
    """Human-readable zone name; falls back to Zone<id> if none was set."""
    name = zone.get("name")
    return name if name else f"Zone{zone.get('id', '?')}"


def sanitize_for_filename(name):
    """Strip spaces/punctuation so the name is safe to use in a filename."""
    cleaned = "".join(ch for ch in name if ch.isalnum())
    return cleaned if cleaned else "Zone"


def ensure_day_folders(date_str):
    """
    Create evidence/<date>/images and evidence/<date>/videos.
    Only ever called at the moment a new incident actually starts.
    """
    day_dir = os.path.join(EVIDENCE_ROOT, date_str)
    images_dir = os.path.join(day_dir, "images")
    videos_dir = os.path.join(day_dir, "videos")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(videos_dir, exist_ok=True)
    return day_dir, images_dir, videos_dir


def start_incident(zone, current_people, evidence_frame):
    """Begin a brand-new incident for this zone: snapshot + video start."""
    zone_id = zone.get("id")
    zone_name = get_zone_display_name(zone)
    safe_name = sanitize_for_filename(zone_name)

    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    file_time_str = now.strftime("%H-%M-%S")
    log_time_str = now.strftime("%H:%M:%S")

    _, images_dir, videos_dir = ensure_day_folders(date_str)

    image_filename = f"{safe_name}_{file_time_str}.jpg"
    video_filename = f"{safe_name}_{file_time_str}.mp4"
    image_path = os.path.join(images_dir, image_filename)
    video_path = os.path.join(videos_dir, video_filename)

    cv2.imwrite(image_path, evidence_frame)

    h, w = evidence_frame.shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    video_writer = cv2.VideoWriter(video_path, fourcc, 20.0, (w, h))

    zone_incident_state[zone_id] = {
        "active": True,
        "date": date_str,
        "time": log_time_str,
        "zone_name": zone_name,
        "max_allowed": zone.get("maximum_people", 0),
        "peak_count": current_people,
        "image_filename": image_filename,
        "video_filename": video_filename,
        "video_writer": video_writer,
    }

    append_incident_log(zone_incident_state[zone_id], zone_id, current_people)

    if video_writer.isOpened():
        video_writer.write(evidence_frame)


def continue_incident(zone_id, current_people, evidence_frame):
    """Keep recording the ongoing incident and track its peak headcount."""
    state = zone_incident_state.get(zone_id)
    if not state or not state["active"]:
        return

    state["peak_count"] = max(state["peak_count"], current_people)

    writer = state.get("video_writer")
    if writer is not None and writer.isOpened():
        writer.write(evidence_frame)


def update_summary(date_str):
    """Rebuild summary.txt for a day from that day's incident_log.csv."""
    day_dir = os.path.join(EVIDENCE_ROOT, date_str)
    csv_path = os.path.join(day_dir, "incident_log.csv")
    summary_path = os.path.join(day_dir, "summary.txt")

    if not os.path.exists(csv_path):
        return

    with open(csv_path, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return

    zones_summary = {}
    all_times = []

    for row in rows:
        zid = row["Zone ID"]
        people = int(row["People Count"])
        allowed = int(row["Allowed Count"])
        all_times.append(row["Time"])

        if zid not in zones_summary:
            zones_summary[zid] = {
                "name": row["Zone Name"],
                "violations": 0,
                "max_allowed": allowed,
                "highest_count": people,
            }

        info = zones_summary[zid]
        info["violations"] += 1
        info["max_allowed"] = allowed
        info["highest_count"] = max(info["highest_count"], people)

    lines = [f"Date : {date_str}", f"Total Incidents : {len(rows)}", "-" * 50]

    for zid in sorted(zones_summary.keys(), key=lambda v: int(v) if v.isdigit() else v):
        info = zones_summary[zid]
        lines.append(f"Zone {zid} ({info['name']})")
        lines.append(f"Violations : {info['violations']}")
        lines.append(f"Maximum People Allowed : {info['max_allowed']}")
        lines.append(f"Highest People Count : {info['highest_count']}")
        lines.append("-" * 50)

    lines.append(f"First Incident : {min(all_times)}")
    lines.append(f"Last Incident : {max(all_times)}")

    with open(summary_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def append_incident_log(state, zone_id, people_count):
    """Publish a new incident as soon as its evidence image is captured."""
    day_dir = os.path.join(EVIDENCE_ROOT, state["date"])
    csv_path = os.path.join(day_dir, "incident_log.csv")
    row = {
        "Date": state["date"],
        "Time": state["time"],
        "Zone ID": zone_id,
        "Zone Name": state["zone_name"],
        "People Count": people_count,
        "Allowed Count": state["max_allowed"],
        "Image": state["image_filename"],
        "Video": state["video_filename"],
        "Status": "RECORDING",
    }

    write_header = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="") as f:
        csv_writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        if write_header:
            csv_writer.writeheader()
        csv_writer.writerow(row)
        f.flush()
    update_summary(state["date"])


def finalize_incident(zone_id):
    """Close the video, update the published row, and refresh summary.txt."""
    state = zone_incident_state.get(zone_id)
    if not state or not state["active"]:
        return

    writer = state.get("video_writer")
    if writer is not None:
        try:
            writer.release()
        except Exception:
            pass

    date_str = state["date"]
    day_dir = os.path.join(EVIDENCE_ROOT, date_str)
    csv_path = os.path.join(day_dir, "incident_log.csv")

    with open(csv_path, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        if (row.get("Zone ID") == str(zone_id)
                and row.get("Time") == state["time"]
                and row.get("Image") == state["image_filename"]):
            row["People Count"] = state["peak_count"]
            row["Status"] = "VIOLATION"
            break

    with open(csv_path, "w", newline="") as f:
        csv_writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        csv_writer.writeheader()
        csv_writer.writerows(rows)

    update_summary(date_str)

    state["active"] = False


def handle_zone_incident(zone, zone_exceeded, current_people, evidence_frame):
    """
    Called once per zone per frame. Starts / continues / finalizes an
    incident purely based on whether the zone is currently over its limit.
    A brand-new image + video are only created once the PREVIOUS incident
    for that zone has ended and a new violation begins.
    """
    zone_id = zone.get("id")
    state = zone_incident_state.get(zone_id)

    if zone_exceeded:
        if state is None or not state["active"]:
            start_incident(zone, current_people, evidence_frame)
        else:
            continue_incident(zone_id, current_people, evidence_frame)
    else:
        if state is not None and state["active"]:
            finalize_incident(zone_id)


def finalize_all_active_incidents():
    """Called on shutdown so no in-progress incident is left un-logged."""
    for zone_id, state in list(zone_incident_state.items()):
        if state.get("active"):
            finalize_incident(zone_id)


# -------------------- MAIN LOOP --------------------

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Keep the HTML editor's background image close to live.
        refresh_editor_snapshot(frame)

        # Pick up zone edits saved from zone_editor.html while this script
        # is already running (throttled internally - see
        # ZONE_RELOAD_CHECK_SECONDS - so this is cheap to call every frame).
        check_for_live_zone_updates()

        # ========= DRAW MODE =========
        if not detection_started:
            cv2.putText(frame, "DRAW DANGER ZONES", (150, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
            cv2.putText(frame, "Press ENTER to CONFIRM", (150, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            for zone in ZONES:
                draw_shape(frame, zone, (0, 0, 255), 2)
                zx1, zy1, zx2, zy2 = zone_bounding_box(zone)
                zone_label = f"Zone {zone.get('id', '?')} (Max:{zone.get('maximum_people', 0)})"
                cv2.putText(frame, zone_label, (zx1, max(zy1 - 10, 15)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)

            if current_zone:
                draw_shape(frame, current_zone, (255, 0, 0), 1)

            # Toolbar drawn last so it stays on top
            draw_toolbar(frame)

        # ========= DETECTION MODE =========
        else:
            frame_counter += 1
            results = model(frame)

            # Clean snapshot of the raw camera frame, taken before any overlays
            # are drawn, so incident evidence images/video are not cluttered.
            evidence_frame = frame.copy()

            # Boxes of every valid detected person this frame (for per-zone counting)
            detected_person_boxes = []

            for r in results:
                for box in r.boxes:
                    cls = int(box.cls[0])
                    if model.names[cls] != "person":
                        continue

                    px1, py1, px2, py2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])

                    # ---------- BASIC CONFIDENCE FILTER ----------
                    if conf < 0.6:
                        continue

                    w = px2 - px1
                    h = py2 - py1
                    if w == 0 or h == 0:
                        continue

                    # ---------- ASPECT RATIO FILTER ----------
                    # Skip the filter for boxes touching the frame edge - they're
                    # partially cropped, so their aspect ratio is unreliable and
                    # shouldn't be used to reject a real detection.
                    frame_h, frame_w = frame.shape[:2]
                    touches_edge = (px1 <= 1 or py1 <= 1 or
                                     px2 >= frame_w - 1 or py2 >= frame_h - 1)

                    if not touches_edge:
                        aspect_ratio = h / w
                        # Widened lower bound (was 1) so crouching/bending/seated
                        # people aren't discarded just for being wider than tall.
                        if aspect_ratio > 4 or aspect_ratio < 0.5:
                            continue

                    person_crop = frame[py1:py2, px1:px2]
                    if person_crop.size == 0:
                        continue

                    # ---------- FACE FILTER (only if age detection is enabled) ----------
                    if ENABLE_AGE_DETECTION and face_cascade is not None:
                        gray = cv2.cvtColor(person_crop, cv2.COLOR_BGR2GRAY)
                        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
                        if len(faces) == 0:
                            continue

                    # ---------- AGE ESTIMATION ----------
                    child_detected = True  # Default: detect all persons when age detection disabled
                    color = (0, 255, 0)
                    label = f"PERSON {conf:.2f}"

                    if ENABLE_AGE_DETECTION:
                        # Grid cell key for this person's rough position, used to
                        # cache their last age result between throttled checks.
                        grid_key = (px1 // AGE_CACHE_GRID, py1 // AGE_CACHE_GRID)
                        run_deepface = (frame_counter % AGE_CHECK_INTERVAL == 0) or (grid_key not in age_result_cache)

                        if run_deepface:
                            try:
                                result = DeepFace.analyze(
                                    person_crop,
                                    actions=['age'],
                                    enforce_detection=False,
                                    silent=True
                                )
                                age = result[0]['age']

                                if age < AGE_THRESHOLD:
                                    child_detected = True
                                    label = f"CHILD ({int(age)})"
                                    color = (0, 0, 255)
                                else:
                                    child_detected = False
                                    label = f"ADULT ({int(age)})"
                                    color = (0, 255, 0)

                            except:
                                child_detected = False
                                label = f"UNKNOWN {conf:.2f}"

                            age_result_cache[grid_key] = (child_detected, label, color)

                        else:
                            # Reuse the last known result for this position
                            # instead of re-running DeepFace every frame.
                            child_detected, label, color = age_result_cache[grid_key]

                    cv2.putText(frame, label, (px1, py1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                    # ---------- COLLECT FOR PER-ZONE COUNTING ----------
                    if child_detected:
                        detected_person_boxes.append((px1, py1, px2, py2))

            # ---------- PER-ZONE PEOPLE-LIMIT CHECK ----------
            any_zone_exceeded = False

            for zone in ZONES:
                current_people = 0
                for (px1, py1, px2, py2) in detected_person_boxes:
                    if person_in_zone_check(px1, py1, px2, py2, zone):
                        current_people += 1

                max_people = zone.get("maximum_people", 0)
                zone_exceeded = current_people > max_people

                zx1, zy1, zx2, zy2 = zone_bounding_box(zone)

                if zone_exceeded:
                    any_zone_exceeded = True

                    # Draw zone border RED and show LIMIT EXCEEDED
                    draw_shape(frame, zone, (0, 0, 255), 3)
                    cv2.putText(frame, "LIMIT EXCEEDED", (zx1, max(zy1 - 30, 15)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                    cv2.putText(frame, "!!! ALERT !!!", (50, 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
                else:
                    # Keep zone border GREEN and show People : current/max
                    draw_shape(frame, zone, (0, 255, 0), 2)
                    cv2.putText(frame, f"People : {current_people}/{max_people}",
                                (zx1, max(zy1 - 10, 15)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

                # ---------- INCIDENT EVIDENCE (only on actual violation) ----------
                handle_zone_incident(zone, zone_exceeded, current_people, evidence_frame)

                # Highlight each person's box red/green based on whether their
                # zone(s) are currently over the limit
                for (px1, py1, px2, py2) in detected_person_boxes:
                    if person_in_zone_check(px1, py1, px2, py2, zone):
                        box_color = (0, 0, 255) if zone_exceeded else (0, 255, 0)
                        box_thickness = 3 if zone_exceeded else 2
                        cv2.rectangle(frame, (px1, py1), (px2, py2), box_color, box_thickness)

            if any_zone_exceeded:
                if not alarm_triggered:
                    play_alarm()
                    alarm_triggered = True
            else:
                if alarm_triggered:
                    stop_alarm()
                    alarm_triggered = False

        cv2.imshow("Child Safety Detector", frame)

        key = cv2.waitKey(1) & 0xFF

        # ESC → Exit
        if key == 27:
            break

        # ENTER → Confirm zones
        if key == 13 and not detection_started:
            if len(ZONES) > 0:
                detection_started = True
                save_zones_to_file()
                print(f"\n✓ Detection started with {len(ZONES)} danger zone(s)")

        # R → Reset zones
        if key == ord('r'):
            finalize_all_active_incidents()
            ZONES.clear()
            _next_zone_id = 1
            detection_started = False
            alarm_triggered = False
            stop_alarm()
            save_zones_to_file()
            print("\n✓ Zones reset - draw new zones")

except Exception as e:
    print(f"\n✗ Unexpected error: {e}")

finally:
    # -------------------- CLEAN EXIT --------------------
    # This block always runs - even if the loop above crashed - so the
    # camera, Arduino connection, and any in-progress incident recording
    # are never left open/corrupted.
    print("\nShutting down...")

    # Close out any incident that was still active when the app was closed
    finalize_all_active_incidents()

    cap.release()
    cv2.destroyAllWindows()
    stop_alarm()

    # Close Arduino connection
    if arduino:
        try:
            arduino.close()
            print("✓ Arduino connection closed")
        except:
            pass

    print("✓ Application closed")