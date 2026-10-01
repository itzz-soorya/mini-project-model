# Danger Zone Detection System

A real-time person detection system that monitors user-defined danger zones and triggers an alarm when someone enters a restricted area. Built with a custom-trained YOLOv8 model and OpenCV, with an optional browser-based tool for creating and editing zones.

## Overview

The system watches a live camera feed, checks whether detected people fall inside one or more marked "danger zones," and raises an alarm (buzzer or system beep) when a zone's configured person limit is exceeded. Each incident is logged with a timestamp, a snapshot image, and a short video clip for later review.

Zones can be created directly in the application's video window, or edited afterward through a companion web page that reads and writes the same configuration file, so zones do not need to be redrawn from scratch every time they change.

## Features

- Real-time person detection using a custom-trained YOLOv8 model
- Custom danger zones - rectangle, circle, and freehand shapes
- Automatic alarm when a zone's person limit is exceeded, with Arduino buzzer or system beep support
- Optional age detection to filter for children only
- Face validation to reduce false positives
- Fullscreen monitoring interface
- Incident logging - CSV records plus saved photo/video evidence for each violation
- Browser-based zone editor with full create/read/update/delete support, live camera preview, and automatic reload of changes into the running detector

## Requirements

- Python 3.8 or later
- Webcam
- Windows OS (required for the built-in alarm sound; Arduino buzzer support works cross-platform)
- GPU recommended for training
- 100 GB or more of free disk space (for the COCO dataset, only needed if training your own model)
- Flask (only needed if using the browser-based zone editor)

## Setup Instructions

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Download the COCO 2017 dataset

```bash
python download_dataset.py
```

This downloads the COCO 2017 dataset (approximately 25 GB), required only if you intend to train your own model. See the Kaggle API Setup section below for the credentials this step requires.

### 3. Train a custom YOLO model

```bash
python train_model.py
```

This trains a custom YOLOv8 model on the COCO dataset. Training takes 3 to 8 hours depending on hardware.

### 4. Run the detection system

```bash
python detect_danger_zone.py
```

## Basic Usage

1. Launch the application:
   ```bash
   python detect_danger_zone.py
   ```

2. Draw danger zones directly on the video window using the on-screen toolbar (rectangle, circle, or freehand tool). Zones are outlined in red and each one has a configurable maximum person count.

3. Press `ENTER` to confirm the zones and start monitoring. The detector will begin tracking people and comparing zone occupancy against each zone's limit.

4. When a zone's limit is exceeded, the alarm sounds and an "ALERT" message is shown on screen. The alarm stops automatically once the zone is clear.

### Controls

| Key | Action |
|-----|--------|
| `ENTER` | Confirm zones and start detection |
| `R` | Reset all zones and return to drawing mode |
| `ESC` | Exit the application |

## Zone Editor (Browser-Based)

Drawing and adjusting zones by hand in the OpenCV window is fine for a first pass, but tedious for ongoing changes. The project includes a small local web application for managing zones instead.

### How it works

`detect_danger_zone.py` saves its zone configuration to `zones.json` and continuously refreshes a reference image (`zone_reference.jpg`) from the live camera feed while it runs. A separate local server, `zone_server.py`, serves a dashboard (`dashboard.html`) at the root URL and loads the password-protected zone editor (`zone_editor.html`) when you choose Zone Editor. Both pages read and write the same `zones.json` file, using the reference image as a near-live background to draw on.

### Running the editor

```bash
pip install flask
python zone_server.py
```

Then open `http://localhost:5000` in a browser.

The editor password is loaded from the project `.env` file as
`ZONE_EDITOR_PASSWORD`. Keep this file private and do not commit it.

### What you can do in the editor

- View all current zones overlaid on a near-live camera image, refreshed roughly once per second
- Create new rectangle, circle, or freehand zones
- Move and resize existing zones by dragging their body or handles
- Edit each zone's maximum person count
- Delete zones
- Save changes back to `zones.json`

### Live updates

Changes saved in the browser are picked up automatically by `detect_danger_zone.py` while it is running - there is no need to restart it. The detector checks for changes to `zones.json` every few seconds and reloads the zone list when it detects a change, finalizing any in-progress incident recordings first so nothing is left in an inconsistent state.

The reference image requires `detect_danger_zone.py` to be running, since it owns the camera and is the only process writing that file. If `detect_danger_zone.py` has never been run, the editor will show a message indicating that no camera feed is available yet, and will pick it up automatically once the detector starts.

Note that `zone_server.py` and `detect_danger_zone.py` are independent programs. You only need to run `zone_server.py` while actively editing zones in the browser; it can be stopped afterward without affecting the detector.

## Configuration

Key settings can be edited near the top of `detect_danger_zone.py`:

```python
# Enable age detection (requires deepface)
ENABLE_AGE_DETECTION = False  # Set to True for child-only detection

# Age threshold for children
AGE_THRESHOLD = 14  # Years

# Detection confidence
if conf < 0.6:  # Adjust confidence threshold (0.0 to 1.0)
    continue

# Arduino buzzer
ENABLE_ARDUINO_BUZZER = True
ARDUINO_PORT = "COM5"  # Adjust to match your system
```

Use `find_arduino_port.py` to identify which serial port your Arduino is connected to, and `test_arduino_connection.py` to confirm the connection works before running the full detection script. See `ARDUINO_SETUP.md`, `BUZZER_CONNECTION_GUIDE.md`, and `UPLOAD_GUIDE.md` for the full hardware setup.

## Project Structure

```
mini-project-model/
├── coco2017/                       Downloaded COCO dataset (created by download_dataset.py)
├── detect_danger_zone.py           Main detection application
├── zone_server.py                  Local server for the browser-based zone editor
├── dashboard.html                  Incident dashboard (served at the root URL)
├── zone_editor.html                Browser zone editor (served at /zone_editor)
├── zones.json                      Saved zone configuration (created automatically)
├── zone_reference.jpg              Live reference image for the editor (created automatically)
├── train_model.py                  Model training script
├── download_dataset.py             Dataset downloader
├── danger_zone_model.pt            Custom-trained YOLO model (created after training)
├── yolov8n.pt                      Base YOLOv8 nano checkpoint used as the training starting point
├── arduino_buzzer_control.ino      Arduino sketch - listens on serial for buzzer on/off commands
├── find_arduino_port.py            Utility - lists available serial ports to help identify the Arduino
├── test_arduino_connection.py      Utility - verifies the serial connection to the Arduino before running detection
├── alarm.wav                       Custom alarm sound (optional)
├── requirements.txt                Python dependencies
├── .gitignore
├── README.md                       This file
├── ARDUINO_SETUP.md                Arduino IDE and board setup guide
├── BUZZER_CONNECTION_GUIDE.md      Buzzer wiring guide
├── QUICK_BUZZER_CONNECT.md         Condensed quick-reference version of the buzzer wiring guide
└── UPLOAD_GUIDE.md                 Guide for uploading arduino_buzzer_control.ino to the board
```

`runs/` is also created under the project root once `train_model.py` has been run, containing training outputs.

## Additional Documentation

The Arduino-related setup is split across a few focused guides rather than one long document:

- `ARDUINO_SETUP.md` - installing the Arduino IDE, selecting the board and processor, and general first-time setup
- `BUZZER_CONNECTION_GUIDE.md` - wiring the buzzer to the Arduino
- `QUICK_BUZZER_CONNECT.md` - a condensed version of the wiring guide for quick reference
- `UPLOAD_GUIDE.md` - uploading `arduino_buzzer_control.ino` to the board

If any of these have drifted from what's actually in the files, treat this list as a starting point and adjust the descriptions to match.

## Advanced Options

### Custom alarm sound

Place a `.wav` file named `alarm.wav` in the project directory. The system uses it automatically if present, and falls back to a system beep otherwise.

### Age detection setup

To enable age-based filtering:

1. Install DeepFace:
   ```bash
   pip install deepface tf-keras
   ```

2. Enable it in the configuration:
   ```python
   ENABLE_AGE_DETECTION = True
   ```

Age estimation from a video frame has a meaningful margin of error. Treat this feature as a supplementary filter, not a sole safeguard, particularly in child-safety contexts.

### GPU acceleration

For faster processing, install a CUDA-compatible build of PyTorch:

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

## Model Information

| Property | Value |
|---|---|
| Model | YOLOv8n (Nano), custom trained |
| Training dataset | COCO 2017 (80 object classes) |
| Training time | 3 to 8 hours, hardware dependent |
| Primary detection target | Person class (class 0) |
| Default confidence threshold | 0.6 (adjustable) |

## Kaggle API Setup

Required only if you plan to train your own model, since it downloads the COCO dataset:

1. Go to https://www.kaggle.com/settings
2. Scroll to the API section
3. Click "Create New API Token"
4. Place the downloaded `kaggle.json` file in:
   - Windows: `C:\Users\<YourUsername>\.kaggle\kaggle.json`
   - Linux/Mac: `~/.kaggle/kaggle.json`

## Troubleshooting

**Camera not opening**
```python
cap = cv2.VideoCapture(1)  # Try a different camera index
```

**Face cascade not loading**
The system automatically tries OpenCV's built-in cascade. If the face filter fails to load, detection still works without it.

**Alarm not playing**
- Confirm `alarm.wav` exists, or the system will fall back to a beep
- Check system volume
- Confirm the file is a valid WAV file

**Low FPS**
- Use a smaller camera resolution
- Disable age detection
- Confirm the GPU is actually being used for inference
- Use the YOLOv8n (nano) model variant

**Zone editor shows "no camera feed"**
Confirm `detect_danger_zone.py` is currently running - it is the only process that writes the reference image the editor displays.

**Zone editor changes not appearing in the detector**
Confirm the change was actually saved (the Save All button in the editor) and allow a few seconds for the detector's periodic file check to pick it up.

**Import errors**
```bash
pip install --upgrade --force-reinstall -r requirements.txt
```

**Training taking too long**
- Use a GPU if available
- Reduce epochs in `train_model.py`
- Reduce batch size if running out of memory
- Use a smaller model variant

## Use Cases

- Child safety monitoring around swimming pools or construction zones
- Restricted area monitoring for server rooms or hazardous zones
- Unauthorized access detection
- Industrial safety around dangerous machinery
- Home safety around stairs or balconies for young children

## Performance

| Model | FPS (CPU) | FPS (GPU) | Accuracy |
|---|---|---|---|
| YOLOv8n | 15-25 | 60-100 | High |
| YOLOv8s | 10-15 | 45-80 | Higher |
| YOLOv8m | 5-10 | 30-60 | Highest |

## Training Details

The model is trained using:

- Dataset: COCO 2017 (118K training images, 5K validation images)
- Epochs: 50, with early stopping
- Image size: 640x640
- Batch size: 16
- Optimizer: AdamW
- Loss functions: Box loss, class loss, DFL loss

Training outputs are saved in `runs/train/danger_zone_detector/`.

## Contributing

Suggestions and improvements are welcome. Areas of particular interest:

- Multi-camera / multi-room support
- Object tracking to reduce false-positive alarms from single-frame flicker
- Cloud storage for incident evidence
- Mobile or email/SMS notifications
- A dashboard for browsing incident history

## Disclaimer

This is a demonstration project. For production safety systems, consider:

- Redundant sensors
- Professional-grade cameras
- Backup power systems
- Regular maintenance
- Professional installation

## License

MIT License. Free to use and modify for your own projects.

## Credits

- YOLOv8 - Ultralytics
- COCO Dataset - Microsoft COCO
- OpenCV - Open Source Computer Vision Library
- DeepFace - Age detection library

---

For questions or issues, please open an issue in the repository.
