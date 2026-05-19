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
from deepface import DeepFace

# -------------------- ARDUINO SETUP --------------------

ENABLE_ARDUINO_BUZZER = True  # Set to False to use system beep instead
ARDUINO_PORT = "COM3"  # Change to your Arduino COM port (COM3, COM4, etc.)
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
    import cv2
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

# -------------------- MOUSE CALLBACK --------------------

def draw_zone(event, x, y, flags, param):
    global ix, iy, drawing, current_zone, ZONES, detection_started

    if detection_started:
        return

    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        ix, iy = x, y

    elif event == cv2.EVENT_MOUSEMOVE:
        if drawing:
            current_zone = (ix, iy, x, y)

    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        current_zone = (ix, iy, x, y)
        ZONES.append(current_zone)
        current_zone = None


cv2.namedWindow("Child Safety Detector", cv2.WINDOW_NORMAL)
cv2.setWindowProperty("Child Safety Detector", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
cv2.setMouseCallback("Child Safety Detector", draw_zone)

print("\n" + "=" * 60)
print("INSTRUCTIONS")
print("=" * 60)
print("1. Draw danger zones using mouse (click and drag)")
print("2. Press ENTER to start detection")
print("3. Press 'R' to reset zones")
print("4. Press ESC to exit")
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


# -------------------- MAIN LOOP --------------------

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # ========= DRAW MODE =========
    if not detection_started:
        cv2.putText(frame, "DRAW DANGER ZONES", (30, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
        cv2.putText(frame, "Press ENTER to CONFIRM", (30, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        for zone in ZONES:
            x1, y1, x2, y2 = zone
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)

        if current_zone:
            x1, y1, x2, y2 = current_zone
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 1)

    # ========= DETECTION MODE =========
    else:
        results = model(frame)
        person_in_zone = False

        # Draw locked zones
        for zone in ZONES:
            x1, y1, x2, y2 = zone
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)

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
                aspect_ratio = h / w
                if aspect_ratio > 4 or aspect_ratio < 1:
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

                cv2.putText(frame, label, (px1, py1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                # ---------- ZONE CHECK ----------
                person_in_danger_zone = False
                
                if child_detected:
                    for zx1, zy1, zx2, zy2 in ZONES:
                        if px1 < zx2 and px2 > zx1 and py1 < zy2 and py2 > zy1:
                            person_in_danger_zone = True
                            person_in_zone = True
                            cv2.putText(frame, "!!! ALERT !!!", (50, 50),
                                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
                            
                            # Draw RED bounding box for danger
                            cv2.rectangle(frame, (px1, py1), (px2, py2), (0, 0, 255), 3)

                            if not alarm_triggered:
                                play_alarm()
                                alarm_triggered = True
                            break
                
                # Draw GREEN bounding box if person NOT in danger zone
                if not person_in_danger_zone:
                    cv2.rectangle(frame, (px1, py1), (px2, py2), (0, 255, 0), 2)

        # Stop alarm if zone empty
        if not person_in_zone and alarm_triggered:
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
            print(f"\n✓ Detection started with {len(ZONES)} danger zone(s)")

    # R → Reset zones
    if key == ord('r'):
        ZONES.clear()
        detection_started = False
        alarm_triggered = False
        stop_alarm()
        print("\n✓ Zones reset - draw new zones")

# -------------------- CLEAN EXIT --------------------

print("\nShutting down...")
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
