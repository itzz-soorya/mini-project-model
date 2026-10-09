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
import queue
import shutil
import subprocess
import threading
from collections import deque
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

MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "best_final.pt",
)

if not os.path.exists(MODEL_PATH):
    print(f"✗ Model not found: {MODEL_PATH}")
    print("\nPlease place the trained 'best_final.pt' file in the project folder")
    exit(1)

model = YOLO(MODEL_PATH)
print(f"✓ Model loaded successfully: {MODEL_PATH}")
print(f"Model classes: {model.names}")
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

# -------------------- CAMERA (THREADED CAPTURE) --------------------
#
# Why a dedicated capture thread?
#   cap.read() used to run in the SAME loop as YOLO inference, drawing and
#   disk writes. While that loop was busy (YOLO = 50-200 ms/frame on CPU)
#   nobody drained the camera driver's buffer, so frames piled up: the
#   picture lagged behind real life, recordings came out "fast-forwarded",
#   and a single failed read() ended the whole program.
#
#   Now ONE thread does nothing except read the camera at full speed and
#   keep only the NEWEST frame (producer). Everybody else - UI, YOLO worker,
#   incident recorder - just asks for the newest frame (consumers), so a
#   slow consumer can never back up the camera. A Condition variable lets
#   consumers sleep until a new frame really arrives (no busy-waiting).

USE_VIDEO_FILE = True  # True: use VIDEO_FILE; False: use the webcam
CAMERA_INDEX = 0
VIDEO_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "VIRAT_S_000200_00_000100_000171.mp4",
)
INPUT_SOURCE = VIDEO_FILE if USE_VIDEO_FILE else CAMERA_INDEX


class FrameGrabber(threading.Thread):
    def __init__(self, source=INPUT_SOURCE):
        super().__init__(daemon=True, name="FrameGrabber")
        self.source = source
        self._is_file = isinstance(source, (str, bytes, os.PathLike))
        self._cond = threading.Condition()
        self._frame = None
        self._frame_id = 0
        self._quit = threading.Event()
        self._end_of_stream = threading.Event()
        self.cap = self._open()
        file_fps = (self.cap.get(cv2.CAP_PROP_FPS)
                    if self.cap is not None and self._is_file else 0.0)
        self._file_fps = file_fps if file_fps > 0 else 25.0
        self._next_file_frame_time = time.perf_counter()

    def _open(self):
        """Open a video file directly or try the available webcam backends."""
        if self._is_file:
            if not os.path.isfile(self.source):
                print(f"✗ Video file not found: {self.source}")
                return None

            cap = cv2.VideoCapture(self.source)
            if not cap.isOpened():
                cap.release()
                print(f"✗ Could not open video file: {self.source}")
                return None

            print(f"✓ Video file opened: {self.source}")
            return cap

        if os.name == "nt":
            # DirectShow is more reliable for this threaded capture loop.
            # CAP_ANY may select MSMF and stop delivering frames after the
            # buffer-size configuration is applied.
            backends = [("DirectShow", cv2.CAP_DSHOW), ("MSMF", cv2.CAP_MSMF),
                        ("default", cv2.CAP_ANY)]
        else:
            backends = [("default", cv2.CAP_ANY)]

        for name, backend in backends:
            cap = cv2.VideoCapture(self.source, backend)
            if not cap.isOpened():
                cap.release()
                continue

            # Configure the capture before validating it. Some Windows
            # backends return one warm-up frame, then stop after this setting.
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            got_frame = False
            successful_reads = 0
            for _ in range(60):                    # MSMF can need a few secs to warm up
                ok, frame = cap.read()
                if ok and frame is not None:
                    successful_reads += 1
                    if successful_reads >= 5:
                        got_frame = True
                        break
                time.sleep(0.1)
            if got_frame:
                print(f"✓ Camera backend in use: {name}")
                return cap
            print(f"⚠ Camera backend {name} opened but gave no frames - trying next")
            cap.release()
        return None

    def run(self):
        fails = 0
        while not self._quit.is_set():
            if self.cap is None:                       # camera lost -> keep retrying
                time.sleep(1.0)
                self.cap = self._open()
                if self.cap is not None:
                    print("✓ Camera reconnected")
                continue

            ok, frame = self.cap.read()
            if not ok:
                if self._is_file:
                    print(f"✓ Video file playback finished: {self.source}")
                    self.cap.release()
                    self.cap = None
                    self._end_of_stream.set()
                    with self._cond:
                        self._cond.notify_all()
                    break

                fails += 1
                if fails >= 30:                        # ~1s of failures = camera dropped
                    print("⚠ Camera stopped delivering frames - reconnecting...")
                    self.cap.release()
                    self.cap = None
                    fails = 0
                time.sleep(0.03)
                continue

            fails = 0
            with self._cond:
                self._frame = frame
                self._frame_id += 1
                self._cond.notify_all()

            if self._is_file:
                self._next_file_frame_time += 1.0 / self._file_fps
                delay = self._next_file_frame_time - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)

    @property
    def end_of_stream(self):
        return self._end_of_stream.is_set()

    def wait_for_frame(self, last_id, timeout=1.0):
        """Block until a frame NEWER than last_id exists. Returns (id, frame)
        or (last_id, None) on timeout. Frame is shared - copy() before drawing."""
        with self._cond:
            self._cond.wait_for(
                lambda: (self._frame is not None and
                         self._frame_id != last_id) or
                        self._quit.is_set() or self._end_of_stream.is_set(),
                timeout)
            if self._frame is None or self._frame_id == last_id:
                return last_id, None
            return self._frame_id, self._frame

    def latest(self):
        with self._cond:
            return self._frame_id, self._frame

    def stop(self):
        self._quit.set()
        with self._cond:
            self._cond.notify_all()
        self.join(timeout=2)
        if self.cap is not None:
            self.cap.release()


grabber = FrameGrabber(INPUT_SOURCE)

if grabber.cap is None:
    if USE_VIDEO_FILE:
        print(f"✗ Error: Could not open video file: {VIDEO_FILE}")
        print("  - Check that the file exists and is a supported video format")
    else:
        print("✗ Error: Could not open camera")
        print("  - Close any other program using the camera (an old detect_danger_zone.py, Zoom, Teams, Camera app)")
        print("  - Windows Settings > Privacy > Camera > allow desktop apps")
        print("  - Try CAMERA_INDEX = 1")
    exit(1)

grabber.start()
_first_id, _first_frame = grabber.wait_for_frame(-1, timeout=15.0)
if _first_frame is None:
    if USE_VIDEO_FILE and grabber.end_of_stream:
        print(f"✗ Error: Video file contains no readable frames: {VIDEO_FILE}")
    elif USE_VIDEO_FILE:
        print(f"✗ Error: Video file opened but delivered no frames: {VIDEO_FILE}")
    else:
        print("✗ Error: Camera opened but delivered no frames")
    grabber.stop()
    exit(1)

print("✓ Video input initialized (threaded capture)" if USE_VIDEO_FILE
      else "✓ Camera initialized (threaded capture)")

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

# -------------------- BYTETRACK + TEMPORAL VALIDATION SETTINGS --------------------
# ByteTrack (built into Ultralytics) gives every person a persistent track ID,
# so a person is counted once, no matter how many frames they appear in.
TRACKER_CONFIG = "bytetrack.yaml"
TRACK_CONF = 0.25                 # confidence passed to model.track() (low: far-away people score low)
TRACK_IMGSZ = 1280                # inference size; small/distant people need > 640 (use 960 if CPU is slow)
COUNT_UNTRACKED = True            # count a detection even before ByteTrack has given it an ID

# A zone violation must hold for this many CONSECUTIVE PROCESSED frames before
# it is confirmed (alarm + evidence). A shorter blip is ignored (false-alarm
# filter). Note: "processed" frames = frames the detector actually handled,
# so the real time is TEMPORAL_CONFIRM_FRAMES / detector FPS seconds.
TEMPORAL_CONFIRM_FRAMES = 5

print("\n" + "=" * 60)
print("CONFIGURATION")
print("=" * 60)
print(f"Age detection: {'ENABLED' if ENABLE_AGE_DETECTION else 'DISABLED'}")
print(f"Age threshold: {AGE_THRESHOLD} years")
print(f"Face filter: {'ENABLED' if face_cascade is not None else 'DISABLED'}")
print(f"Tracker: {TRACKER_CONFIG} (conf={TRACK_CONF})")
print(f"Temporal confirmation: {TEMPORAL_CONFIRM_FRAMES} consecutive frames")
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
    with processing_lock:      # don't swap zones while the worker is mid-frame
        finalize_all_active_incidents()
        load_zones_from_file()
        reset_zone_streaks()   # zone ids may now mean something else
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

class AlarmController:
    """Alarm runs in its own thread. Before, winsound.Beep(1000, 500) blocked
    the main loop for half a second on every alarm trigger (frozen video).
    Now the processing code just calls alarm.set(True/False) - instant, and
    idempotent, so it can be called every frame."""

    def __init__(self):
        self._on = threading.Event()
        self._quit = threading.Event()
        self._last = False
        self._use_arduino = bool(ENABLE_ARDUINO_BUZZER and arduino)
        self._thread = threading.Thread(target=self._run, daemon=True, name="Alarm")
        self._thread.start()

    def set(self, active):
        if active:
            self._on.set()
        else:
            self._on.clear()

    def _arduino_write(self, byte):
        try:
            arduino.write(byte)
            return True
        except Exception as e:
            print(f"Error sending to Arduino: {e} - falling back to system beep")
            self._use_arduino = False
            return False

    def _run(self):
        while not self._quit.is_set():
            on = self._on.is_set()
            if on != self._last:
                self._last = on
                if self._use_arduino:
                    if self._arduino_write(b"1" if on else b"0"):
                        print("✓ Buzzer triggered (Arduino)" if on else "✓ Buzzer stopped (Arduino)")
                else:
                    print("✓ Alarm beeping (System)" if on else "✓ Alarm stopped (System)")
            if on and not self._use_arduino:
                try:
                    winsound.Beep(1000, 500)
                except Exception:
                    time.sleep(0.5)
            else:
                time.sleep(0.05)

    def shutdown(self):
        self._on.clear()
        self._quit.set()
        self._thread.join(timeout=2)
        if self._use_arduino:
            try:
                arduino.write(b"0")
            except Exception:
                pass


alarm = AlarmController()


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


# ==================== INCIDENT VIDEO RECORDER (OWN THREAD) ====================
#
# Previously frames were written to the VideoWriter from the YOLO loop, so
# the clip got ONE frame per inference (e.g. 5 fps) but was tagged as 20 fps
# -> wrong speed/length. Also 'mp4v' (MPEG-4 Part 2) can't be played by
# browsers, which is why the dashboard said "can't play this video format".
#
# Now ONE thread owns every VideoWriter and writes the newest camera frame
# at a fixed 20 fps clock, so clip duration == real time regardless of YOLO
# speed. Clips are H.264 (browser-playable): written with 'avc1' if OpenCV
# supports it, otherwise written as mp4v and re-encoded to H.264 with ffmpeg
# in a background thread once the incident ends.

RECORD_FPS = 20.0

# PRE-BUFFERED EVIDENCE: the recorder keeps the last PRE_BUFFER_SECONDS of
# video in memory at all times. When a violation is confirmed the saved clip
# starts with that buffer, so the clip shows the moment people ENTERED the
# zone, not just the moment the (delayed) confirmation fired.
# Memory use ~= PRE_BUFFER_SECONDS * RECORD_FPS * one frame (a 640x480 frame
# is ~0.9 MB, so 3 s ~= 55 MB; a 1080p frame is ~6 MB, so 3 s ~= 370 MB).
# Set to 0 to disable pre-buffering.
PRE_BUFFER_SECONDS = 3.0

# One lock protects "evaluate zones + start/stop incidents", so the YOLO
# worker, zone hot-reload and the R-reset can never interleave.
processing_lock = threading.Lock()


def find_ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg                      # pip install imageio-ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


FFMPEG_EXE = find_ffmpeg()
print("✓ ffmpeg found - clips will be browser-playable H.264" if FFMPEG_EXE else
      "⚠ ffmpeg not found - if the dashboard can't play videos run: pip install imageio-ffmpeg")


def open_video_writer(path, fps, size):
    # The hardware/software H.264 encoders OpenCV tries first ("avc1", "H264")
    # need a matching libopenh264 DLL; on many Windows installs the DLL
    # version is wrong, which prints "Incorrect library version loaded" and
    # "Failed to initialize VideoWriter" before falling back. If ffmpeg is
    # available we skip those attempts: record with mp4v and let
    # transcode_to_h264() convert the finished clip to browser-playable H.264.
    codecs = ("mp4v",) if FFMPEG_EXE else ("avc1", "H264", "mp4v")
    for codec in codecs:
        writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*codec), fps, size)
        if writer.isOpened():
            return writer, codec
        writer.release()
    return None, None


def transcode_to_h264(path):
    """Re-encode a finished clip in place to H.264/yuv420p (plays in browsers)."""
    tmp = path[:-4] + "_h264.mp4"
    try:
        subprocess.run(
            [FFMPEG_EXE, "-y", "-loglevel", "error", "-i", path,
             "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", tmp],
            check=True, timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        os.replace(tmp, path)
    except Exception as e:
        print(f"⚠ Could not convert {os.path.basename(path)} to H.264: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


class IncidentRecorder(threading.Thread):
    def __init__(self, grabber, fps=RECORD_FPS):
        super().__init__(daemon=True, name="IncidentRecorder")
        self.grabber = grabber
        self.fps = fps
        self._clips = {}                 # key -> {"writer", "path", "codec", "size", "backlog"}
        # Rolling pre-buffer of the most recent frames, sampled on the same
        # fixed fps clock as the recording, so replaying it is real-time.
        # Frames are stored by reference (the grabber allocates a new array
        # per read and never modifies an old one), so appending is cheap.
        self._prebuffer = deque(maxlen=max(0, int(PRE_BUFFER_SECONDS * fps)))
        self._lock = threading.Lock()
        self._quit = threading.Event()
        self._post = []                  # background transcode threads

    def start_clip(self, key, path):
        _, frame = self.grabber.latest()
        if frame is None:
            return False
        h, w = frame.shape[:2]
        writer, codec = open_video_writer(path, self.fps, (w, h))
        if writer is None:
            print(f"✗ Could not open a video writer for {path}")
            return False
        with self._lock:
            old = self._clips.pop(key, None)
            # Backlog = the pre-buffered frames (oldest first). The recorder
            # thread writes them into the clip BEFORE any live frame, so the
            # video starts PRE_BUFFER_SECONDS before the confirmation. If the
            # buffer is empty (just started / disabled) fall back to the
            # current frame, as before.
            backlog = list(self._prebuffer) or [frame]
            self._clips[key] = {"writer": writer, "path": path, "codec": codec,
                                "size": (w, h), "backlog": backlog}
        if old:
            self._finish(old)
        return True

    @staticmethod
    def _write_frame(clip, frame):
        """Write one frame, skipping any whose size differs from the clip
        (e.g. the camera reconnected at another resolution)."""
        h, w = frame.shape[:2]
        if (w, h) == clip["size"]:
            clip["writer"].write(frame)

    def stop_clip(self, key):
        with self._lock:
            clip = self._clips.pop(key, None)
        if clip:
            self._finish(clip)

    def _finish(self, clip):
        try:
            clip["writer"].release()
        except Exception:
            pass
        if clip["codec"] == "mp4v" and FFMPEG_EXE:
            t = threading.Thread(target=transcode_to_h264, args=(clip["path"],), daemon=True)
            t.start()
            self._post = [p for p in self._post if p.is_alive()] + [t]

    def run(self):
        interval = 1.0 / self.fps
        next_tick = time.perf_counter()
        while not self._quit.is_set():
            next_tick += interval
            _, frame = self.grabber.latest()
            if frame is not None:
                with self._lock:
                    # Write each active clip's pre-buffered backlog first
                    # (older frames), then this tick's live frame.
                    for clip in self._clips.values():
                        if clip["backlog"]:
                            for old_frame in clip["backlog"]:
                                self._write_frame(clip, old_frame)
                            clip["backlog"] = []
                        self._write_frame(clip, frame)    # read-only use of shared frame
                    # Remember this frame for future pre-rolls (after the
                    # clips were written, so it is never written twice).
                    if self._prebuffer.maxlen:
                        self._prebuffer.append(frame)
            delay = next_tick - time.perf_counter()
            if delay > 0:
                self._quit.wait(delay)
            else:
                next_tick = time.perf_counter()           # fell behind -> resync clock

    def shutdown(self):
        self._quit.set()
        self.join(timeout=2)
        with self._lock:
            keys = list(self._clips.keys())
        for k in keys:
            self.stop_clip(k)
        for t in self._post:
            t.join(timeout=60)


recorder = IncidentRecorder(grabber)
recorder.start()


# ==================== SMART INCIDENT EVIDENCE STORAGE ====================
#
# Nothing here ever runs unless a zone actually exceeds its maximum-people
# limit. No folders, files, or logs are created for a clean/compliant frame.

EVIDENCE_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evidence")
CSV_FIELDNAMES = [
    "Date", "Time", "Zone ID", "Zone Name",
    "People Count", "Allowed Count", "Image", "Video", "Status",
]

# Per-zone incident state, keyed by zone id. Only populated once a zone's
# FIRST violation happens.
zone_incident_state = {}

# Temporal validation state, kept SEPARATELY for every zone: zone id -> number
# of consecutive processed frames in which that zone was over its limit.
zone_violation_streak = {}


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

    # Video is recorded by the IncidentRecorder thread on its own 20 fps clock.
    recorder.start_clip(zone_id, video_path)

    zone_incident_state[zone_id] = {
        "active": True,
        "date": date_str,
        "time": log_time_str,
        "zone_name": zone_name,
        "max_allowed": zone.get("maximum_people", 0),
        "peak_count": current_people,
        "image_filename": image_filename,
        "video_filename": video_filename,
    }

    append_incident_log(zone_incident_state[zone_id], zone_id, current_people)


def continue_incident(zone_id, current_people, evidence_frame):
    """Keep recording the ongoing incident and track its peak headcount."""
    state = zone_incident_state.get(zone_id)
    if not state or not state["active"]:
        return

    state["peak_count"] = max(state["peak_count"], current_people)


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

    recorder.stop_clip(zone_id)      # recorder thread closes (and converts) the clip

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

    tmp_csv = csv_path + ".tmp"
    with open(tmp_csv, "w", newline="") as f:
        csv_writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        csv_writer.writeheader()
        csv_writer.writerows(rows)
    try:
        os.replace(tmp_csv, csv_path)
    except PermissionError:          # Windows: file momentarily open elsewhere
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


def reset_zone_streaks():
    """Forget all temporal-validation progress (zones changed / detection restarted)."""
    zone_violation_streak.clear()


def reset_tracker():
    """Forget every ByteTrack track so person IDs start fresh. Called when
    detection (re)starts, so stale tracks from before a pause can't be
    matched to new people."""
    try:
        predictor = getattr(model, "predictor", None)
        for tracker in (getattr(predictor, "trackers", None) or []):
            tracker.reset()
    except Exception as e:
        print(f"⚠ Could not reset tracker: {e}")


def process_detection_frame(raw_frame, zones):
    """Runs in the DetectionWorker thread. raw_frame is shared/read-only;
    returns a NEW annotated frame.

    Pipeline:
      YOLOv8 -> ByteTrack (persistent IDs) -> zone check -> unique-ID
      occupancy -> temporal validation -> confirmed violation
      -> alarm + image + video + CSV (existing incident system)."""
    global frame_counter
    frame = raw_frame.copy()
    frame_counter += 1

    # ---------- YOLOv8 + BYTETRACK ----------
    # model.track() runs detection and then ByteTrack. persist=True keeps the
    # tracker state between calls so IDs survive from frame to frame.
    results = model.track(
        frame,
        persist=True,
        tracker=TRACKER_CONFIG,
        conf=TRACK_CONF,
        imgsz=TRACK_IMGSZ,
        verbose=False,
    )

    # Clean snapshot of the raw camera frame, taken before any overlays
    # are drawn, so incident evidence images/video are not cluttered.
    evidence_frame = raw_frame   # untouched copy for evidence

    # Valid TRACKED persons this frame: (x1, y1, x2, y2, track_id).
    # Detections without a track ID are never counted (see below).
    tracked_persons = []

    for r in results:
        for box in r.boxes:
            cls = int(box.cls[0])
            if str(model.names[cls]).lower() != "person":
                continue

            px1, py1, px2, py2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])

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

            # ---------- BYTETRACK ID ----------
            # box.id is None when the tracker has not (yet) confirmed this
            # detection as a track. Such a box is still drawn, but it is NOT
            # counted, so a brand-new/flickering detection cannot inflate
            # the occupancy.
            track_id = int(box.id[0]) if box.id is not None else None

            # ---------- FACE FILTER (only if age detection is enabled) ----------
            if ENABLE_AGE_DETECTION and face_cascade is not None:
                gray = cv2.cvtColor(person_crop, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.3, 5)
                if len(faces) == 0:
                    continue

            # ---------- AGE ESTIMATION ----------
            child_detected = True  # Default: detect all persons when age detection disabled
            color = (0, 255, 0)
            if track_id is not None:
                label = f"Person ID {track_id} | {conf:.2f}"
            else:
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

                if track_id is not None:
                    label = f"ID {track_id} | {label}"

            cv2.rectangle(frame, (px1, py1), (px2, py2), color, 1)
            cv2.putText(frame, label, (px1, py1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # ---------- COLLECT FOR PER-ZONE COUNTING ----------
            # Only persons that have a valid ByteTrack ID are counted.
            if child_detected:
                if track_id is not None:
                    tracked_persons.append((px1, py1, px2, py2, track_id))
                elif COUNT_UNTRACKED:
                    # No ByteTrack ID yet (first frames / after dropped frames):
                    # use a unique negative id so the person is still counted once.
                    tracked_persons.append((px1, py1, px2, py2, -(len(tracked_persons) + 1)))

    # ---------- PER-ZONE OCCUPANCY + TEMPORAL VALIDATION ----------
    any_zone_confirmed = False

    # Drop streaks of zones that no longer exist (zone deleted / edited).
    live_zone_ids = {z.get("id") for z in zones}
    for stale_id in [k for k in zone_violation_streak if k not in live_zone_ids]:
        del zone_violation_streak[stale_id]

    for zone in zones:
        zone_id = zone.get("id")

        # Unique-ID occupancy: the SET guarantees that one tracked person is
        # counted once, even if several boxes carried the same ID.
        inside_ids = set()
        inside_boxes = []
        for (px1, py1, px2, py2, track_id) in tracked_persons:
            if person_in_zone_check(px1, py1, px2, py2, zone):
                inside_ids.add(track_id)
                inside_boxes.append((px1, py1, px2, py2))

        current_people = len(inside_ids)
        max_people = int(zone.get("maximum_people", 0))
        over_limit_now = current_people > max_people      # single-frame check

        # Temporal validation (per zone): count consecutive over-limit frames.
        # Any frame at/below the limit resets the streak to 0.
        if over_limit_now:
            streak = zone_violation_streak.get(zone_id, 0) + 1
        else:
            streak = 0
        zone_violation_streak[zone_id] = streak

        zone_confirmed = streak >= TEMPORAL_CONFIRM_FRAMES   # CONFIRMED violation
        zone_pending = over_limit_now and not zone_confirmed # over limit, still verifying

        zx1, zy1, zx2, zy2 = zone_bounding_box(zone)

        if zone_confirmed:
            any_zone_confirmed = True

            # Draw zone border RED and show LIMIT EXCEEDED
            draw_shape(frame, zone, (0, 0, 255), 3)
            cv2.putText(frame, "LIMIT EXCEEDED", (zx1, max(zy1 - 30, 15)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            cv2.putText(frame, "!!! ALERT !!!", (50, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
        elif zone_pending:
            # Over the limit but not yet confirmed: yellow, no alarm/evidence.
            draw_shape(frame, zone, (0, 255, 255), 2)
            cv2.putText(frame, f"VERIFYING {streak}/{TEMPORAL_CONFIRM_FRAMES}",
                        (zx1, max(zy1 - 30, 15)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.putText(frame, f"People : {current_people}/{max_people}",
                        (zx1, max(zy1 - 10, 15)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
        else:
            # Keep zone border GREEN and show People : current/max
            draw_shape(frame, zone, (0, 255, 0), 2)
            cv2.putText(frame, f"People : {current_people}/{max_people}",
                        (zx1, max(zy1 - 10, 15)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

        # ---------- INCIDENT EVIDENCE (only on a CONFIRMED violation) ----------
        # The existing start / continue / finalize logic is unchanged; it is
        # just fed the temporally confirmed flag instead of the raw one.
        handle_zone_incident(zone, zone_confirmed, current_people, evidence_frame)

        # Highlight each counted person's box: red = confirmed violation,
        # yellow = verifying, green = OK.
        if zone_confirmed:
            box_color, box_thickness = (0, 0, 255), 3
        elif zone_pending:
            box_color, box_thickness = (0, 255, 255), 2
        else:
            box_color, box_thickness = (0, 255, 0), 2
        for (px1, py1, px2, py2) in inside_boxes:
            cv2.rectangle(frame, (px1, py1), (px2, py2), box_color, box_thickness)

    alarm.set(any_zone_confirmed)     # alarm only on CONFIRMED violations
    return frame


# ==================== DETECTION WORKER (YOLO IN ITS OWN THREAD) ====================
#
# Pipeline:
#   FrameGrabber thread --newest frame--> DetectionWorker thread --annotated frame--> main/UI thread
#                       \--newest frame--> IncidentRecorder thread (fixed 20 fps clock)
#
# The worker always processes the NEWEST frame and skips any it missed
# (drop-stale policy) so latency never builds up. The UI thread keeps
# polling at camera speed, so the window never freezes while YOLO is busy.
# (cv2.imshow/waitKey must stay on the main thread, so it stays there.)

class DetectionWorker(threading.Thread):
    def __init__(self, grabber):
        super().__init__(daemon=True, name="DetectionWorker")
        self.grabber = grabber
        self._lock = threading.Lock()
        self._result = None
        self._quit = threading.Event()

    def run(self):
        last_id = -1
        while not self._quit.is_set():
            frame_id, raw = self.grabber.wait_for_frame(last_id, timeout=0.5)
            if raw is None:
                if self.grabber.end_of_stream:
                    break
                continue
            last_id = frame_id
            if not detection_started:
                continue
            try:
                with processing_lock:
                    if not detection_started:      # re-check: R may have been pressed
                        continue
                    annotated = process_detection_frame(raw, list(ZONES))
            except Exception as e:
                print(f"✗ Detection error: {e}")
                time.sleep(0.2)
                continue
            with self._lock:
                self._result = annotated

    def latest(self):
        with self._lock:
            return self._result

    def clear(self):
        with self._lock:
            self._result = None

    def stop(self):
        self._quit.set()
        self.join(timeout=3)


detector = DetectionWorker(grabber)
detector.start()


# -------------------- MAIN LOOP (UI THREAD ONLY) --------------------
# Grab newest frame -> draw UI -> show -> read keys. No YOLO, no disk I/O
# for videos, no blocking sound here, so the window stays smooth.

last_frame_id = -1

try:
    while True:
        frame_id, raw_frame = grabber.wait_for_frame(last_frame_id, timeout=1.0)

        if raw_frame is None:
            if grabber.end_of_stream:
                print("✓ Video input reached end of file.")
                break

            # Camera stalled / reconnecting - keep the UI alive instead of quitting.
            waiting = np.zeros((480, 640, 3), dtype=np.uint8)
            waiting_message = "Waiting for camera..." if not USE_VIDEO_FILE else "Waiting for video..."
            cv2.putText(waiting, waiting_message, (150, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
            cv2.imshow("Child Safety Detector", waiting)
            if (cv2.waitKey(1) & 0xFF) == 27:
                break
            continue

        last_frame_id = frame_id
        frame = raw_frame.copy()          # shared frame is read-only; draw on a copy

        # Keep the HTML editor's background image close to live.
        refresh_editor_snapshot(raw_frame)

        # Pick up zone edits saved from zone_editor.html while running.
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
            annotated = detector.latest()
            if annotated is not None:
                frame = annotated
            else:
                cv2.putText(frame, "Starting detection...", (150, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        cv2.imshow("Child Safety Detector", frame)

        key = cv2.waitKey(1) & 0xFF

        # ESC → Exit
        if key == 27:
            break

        # ENTER → Confirm zones
        if key == 13 and not detection_started:
            if len(ZONES) > 0:
                with processing_lock:          # fresh IDs + fresh streaks on start
                    reset_tracker()
                    reset_zone_streaks()
                detection_started = True
                save_zones_to_file()
                print(f"\n✓ Detection started with {len(ZONES)} danger zone(s)")

        # R → Reset zones
        if key == ord('r'):
            detection_started = False
            detector.clear()
            with processing_lock:     # wait for any in-flight frame to finish
                finalize_all_active_incidents()
                ZONES.clear()
                reset_zone_streaks()
                reset_tracker()
            _next_zone_id = 1
            alarm.set(False)
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
    detector.stop()
    finalize_all_active_incidents()
    recorder.shutdown()          # closes clips + finishes H.264 conversion
    grabber.stop()
    cv2.destroyAllWindows()
    alarm.shutdown()

    # Close Arduino connection
    if arduino:
        try:
            arduino.close()
            print("✓ Arduino connection closed")
        except:
            pass

    print("✓ Application closed")