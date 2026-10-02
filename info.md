# Intelligent Danger Zone Monitoring System

## 1. Project Overview

The Intelligent Danger Zone Monitoring System is a real-time computer-vision application that detects people in a camera stream and determines whether they are inside user-defined restricted areas. Each zone has its own maximum occupancy limit. When the detected number of people exceeds that limit, the system raises an alarm and records visual evidence for later review.

The project combines an AI detection pipeline, configurable geometric zones, optional child/age filtering, physical alarm hardware, and a local browser dashboard. It is suitable for demonstrations and prototype safety monitoring in homes, schools, workplaces, industrial areas, and other environments where a camera can observe a restricted region.

## 2. Main Objectives

- Detect people from a live webcam feed.
- Monitor several danger zones independently.
- Allow each zone to have a different occupancy limit.
- Generate an immediate visual and audible warning when a limit is exceeded.
- Preserve a snapshot, video clip, CSV record, and daily summary for every violation.
- Allow zones to be created and edited without restarting the detector.
- Provide a simple dashboard for reviewing historical incidents.

## 3. Key Features

### Real-time AI detection

- Uses a custom-trained YOLOv8 model for object detection.
- Counts only detections classified as `person`.
- Applies a configurable confidence threshold; the current detector uses `0.6`.
- Rejects invalid or implausible detections using bounding-box size and aspect-ratio checks.
- Uses the complete person bounding box for zone membership rather than relying on only the person's feet or center point.

### Flexible danger zones

The system supports three zone types:

1. **Rectangle** - useful for rooms, doorways, work areas, and rectangular floor regions.
2. **Circle** - useful for objects, equipment, pools, or radial safety boundaries.
3. **Freehand polygon** - useful when the monitored area has an irregular shape.

Each zone stores an ID, optional name, geometry, and `maximum_people` limit.

### Per-zone occupancy monitoring

- Zones are evaluated independently on every processed frame.
- A zone is safe when `current_people <= maximum_people`.
- A zone is in violation when `current_people > maximum_people`.
- Multiple zones can be in violation at the same time.
- The display changes zone colors and labels to show the current status.

### Audible safety alert

- Supports an Arduino-controlled buzzer through serial communication.
- Sends `1` to turn the Arduino buzzer on and `0` to turn it off.
- Falls back to a Windows system beep if the Arduino is unavailable or disabled.
- The repository includes `alarm.wav` as an optional project asset; the current detector's direct fallback is a Windows system beep.

### Incident evidence and audit trail

For each new violation period, the system:

- Captures a clean camera snapshot without UI annotations.
- Starts an MP4 video recording.
- Tracks the peak number of people in that zone.
- Writes an entry to `evidence/YYYY-MM-DD/incident_log.csv`.
- Updates a daily `summary.txt`.
- Stops and finalizes the video when the zone becomes compliant again.
- Finalizes active recordings on shutdown or before a live zone configuration reload.

Repeated frames from the same continuous violation do not create separate incidents. A new incident is created only after the previous violation has ended.

### Browser dashboard

The local Flask server serves `dashboard.html`, which provides:

- Date selection and quick-pick dates.
- Automatic refresh of current evidence.
- Overall daily status: safe, warning, or danger.
- Total alerts, affected zones, peak people count, first alert, and latest alert.
- Per-zone summaries and severity information.
- Filterable incident cards.
- Photo and video viewing for each alert.
- Download fallback when a browser cannot play the recorded video format.

### Browser-based zone editor

The password-protected editor provides:

- Live camera reference image refreshed approximately once per second.
- Select/move operations for existing zones.
- Creation of rectangle, circle, and freehand zones.
- Editing of maximum occupancy.
- Zone deletion and save-all support.
- Validation before writing `zones.json`.
- Live hot-reload by the running detector approximately every two seconds.

### Optional child-focused monitoring

When enabled, the detector can:

- Use an OpenCV Haar face cascade as a face-presence filter.
- Estimate age using DeepFace.
- Classify detections below `AGE_THRESHOLD` (currently 14) as children.
- Cache age results by a coarse screen grid and analyze periodically instead of every frame to reduce processing cost.

This is an optional aid, not a reliable identity or age-verification system.

## 4. Technical Stack

### Software

| Layer | Technology | Purpose |
|---|---|---|
| Programming language | Python | Detection, recording, persistence, and server logic |
| Object detection | Ultralytics YOLOv8 | Real-time person detection |
| Computer vision | OpenCV | Camera capture, drawing, image processing, geometric tests, and video writing |
| Numerical processing | NumPy | Polygon and coordinate-array operations |
| Optional age analysis | DeepFace and tf-keras | Approximate age estimation |
| Web backend | Flask | Local dashboard/editor server and REST-style endpoints |
| Web frontend | HTML, CSS, JavaScript | Dashboard and interactive zone editor |
| Configuration | JSON, CSV, `.env` | Zones, incident records, and password configuration |
| Hardware communication | PySerial | Communication with Arduino |
| Model training | Ultralytics training API | Fine-tuning the YOLOv8 model |
| Dataset | COCO 2017 | Training data and person class |

### Hardware

- Webcam or USB camera.
- Optional Arduino Nano or compatible board.
- Optional buzzer connected to the configured Arduino output pin.
- Computer capable of running Python, OpenCV, and YOLO inference.
- A CUDA-capable GPU is recommended for training and higher-speed inference, but CPU execution is possible.

## 5. System Architecture

```text
Camera
  |
  v
detect_danger_zone.py
  |-- YOLOv8 person detection
  |-- confidence/aspect/optional face-age filtering
  |-- geometric zone overlap and occupancy counting
  |-- alarm control
  |-- evidence recording and CSV summaries
  |-- zones.json hot-reload
  |-- zone_reference.jpg refresh
  |
  +--> Arduino buzzer or system beep
  +--> evidence/YYYY-MM-DD/
  +--> zone_reference.jpg

zone_server.py
  |-- Flask API
  |-- password authentication
  |-- dashboard.html
  |-- zone_editor.html
  |-- evidence and zone file serving
```

The detector owns the camera. The web server does not open the camera; it uses the reference image written by the detector. This avoids camera-access conflicts and allows the browser editor to work alongside the detection process.

## 6. Advantages

1. **Immediate response** - violations can trigger an alarm while they are happening.
2. **Configurable areas** - users can model simple or irregular restricted regions.
3. **Per-zone limits** - each area can have its own safety capacity.
4. **Reduced duplicate evidence** - continuous violations are grouped into one incident.
5. **Traceability** - incidents include timestamps, counts, images, videos, and summaries.
6. **Near-live configuration** - saved browser changes are detected without restarting the detector.
7. **Offline/local operation** - the main monitoring workflow can run on a local computer without a cloud service.
8. **Hardware flexibility** - it can use an Arduino buzzer or a software alarm fallback.
9. **Review-friendly interface** - the dashboard turns raw logs into daily statistics and media cards.
10. **Extensibility** - the design can be extended to multiple cameras, notifications, cloud storage, tracking, or additional object classes.
11. **Efficient optional age analysis** - cached and throttled age checks avoid invoking the expensive model on every frame.
12. **Safer geometry handling** - full bounding-box overlap reduces missed detections caused by using only a single point.

## 7. Novelty and Contribution

The novelty of this project is the integration of several practical safety-monitoring capabilities into one local, configurable workflow:

- It combines AI person detection with user-drawn geometric safety boundaries instead of using a fixed camera-wide alert.
- It treats each zone as an independent occupancy-control unit with its own limit and incident lifecycle.
- It connects visual detection to a physical response through an Arduino buzzer while retaining a software fallback.
- It creates a complete evidence trail rather than only showing a transient on-screen warning.
- It provides a browser editor that shares the same zone configuration as the OpenCV detector and supports live reload.
- It separates clean evidence frames from annotated display frames, making saved evidence more useful for later inspection.
- It uses geometry-aware rectangle/circle/polygon intersection logic, allowing irregular real-world boundaries to be monitored.

The project is a prototype contribution and should not be treated as a certified life-safety product without additional validation, redundancy, and professional installation.

## 8. Typical Workflow

1. Install the Python dependencies.
2. Obtain or train `danger_zone_model.pt`.
3. Start `detect_danger_zone.py`.
4. Draw zones in the detector or use the authenticated browser editor.
5. Assign a maximum occupancy to each zone.
6. Confirm the configuration and start detection.
7. The detector counts qualifying people in each zone on every frame.
8. When a limit is exceeded, the alarm starts and evidence recording begins.
9. When the zone returns to its limit or below, the incident is finalized.
10. Run `zone_server.py` to browse the dashboard and edit zones in a local browser.

## 9. Important Project Files

| File | Responsibility |
|---|---|
| `detect_danger_zone.py` | Main camera, detection, zone, alarm, and evidence pipeline |
| `zone_server.py` | Flask server, API, authentication, dashboard serving, and evidence serving |
| `dashboard.html` | Incident review dashboard |
| `zone_editor.html` | Interactive browser zone editor |
| `zones.json` | Shared zone geometry and occupancy configuration |
| `train_model.py` | YOLOv8 training workflow |
| `download_dataset.py` | Optional COCO dataset download helper |
| `arduino_buzzer_control.ino` | Arduino serial buzzer firmware |
| `danger_zone_model.pt` | Custom detector checkpoint |
| `yolov8n.pt` | YOLOv8 Nano starting checkpoint |
| `requirements.txt` | Python dependencies |

## 10. Limitations and Future Improvements

### Current limitations

- A single camera is supported by the current detector.
- Occlusion, poor lighting, camera movement, and unusual viewpoints can reduce detection quality.
- Age estimation is approximate and should not be used as a sole child-safety decision.
- The local authentication system is intended for a trusted local network, not Internet exposure.
- A dropped camera or unavailable model stops reliable monitoring.
- The current system does not track a persistent person identity across frames.

### Potential improvements

- Add multi-object tracking to reduce frame-to-frame flicker.
- Add camera health monitoring and watchdog recovery.
- Support multiple cameras and rooms.
- Add email, SMS, mobile, or push notifications.
- Store evidence in a database or encrypted cloud storage.
- Add role-based access and stronger production authentication.
- Add calibration tools for camera perspective and region-of-interest mapping.
- Add automated tests using recorded video fixtures and known zone geometries.

## 11. Safety and Privacy Notes

Use cameras only where appropriate consent and local privacy requirements are satisfied. Protect `.env`, recorded evidence, and access to the local Flask server. Do not expose the development server directly to the public Internet. Validate the system under the actual lighting, camera position, and occupancy conditions before relying on it for safety decisions.
