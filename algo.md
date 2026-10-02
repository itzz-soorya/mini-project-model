# Danger Zone Monitoring Algorithm

## 1. Algorithm Name

**Real-Time Zone Occupancy Violation Detection with YOLOv8 and Geometric Bounding-Box Overlap**

The algorithm combines:

1. YOLOv8 object detection.
2. Detection filtering.
3. Optional face and age filtering.
4. Shape-specific geometry tests.
5. Per-zone occupancy thresholding.
6. Stateful incident recording.
7. Alarm control and evidence persistence.

## 2. Inputs

- Live camera frames.
- A trained YOLOv8 model.
- A list of configured zones from `zones.json`.
- A maximum occupancy for each zone.
- Detection confidence threshold `C = 0.6`.
- Optional age threshold `A = 14`.
- Optional Arduino serial connection.

Each zone has this logical form:

```text
Zone = {
    id,
    name,
    type: rectangle | circle | freehand,
    geometry,
    maximum_people
}
```

## 3. Outputs

For every processed frame:

- Annotated display frame.
- Occupancy count for every zone.
- Safe or exceeded status for every zone.
- Alarm state.

For every continuous violation:

- One JPEG snapshot.
- One MP4 video clip.
- One CSV incident record.
- An updated daily summary.

## 4. High-Level Flow

```text
Start
  |
  v
Load model, camera, zones, face cascade, and alarm connection
  |
  v
Capture frame
  |
  +--> Refresh zone editor snapshot
  +--> Hot-reload zones.json if it changed
  |
  v
Is detection mode active?
  | No
  +--> Draw/edit zones and wait for confirmation
  |
  | Yes
  v
Run YOLOv8 inference
  |
  v
Keep valid person detections
  |
  v
For every zone, count overlapping person boxes
  |
  v
Compare count with zone maximum
  |
  +--> Within limit: safe display and finalize old incident
  |
  +--> Over limit: alert display, alarm, start/continue recording
  |
  v
Render frame and repeat
  |
  v
On exit: stop alarm, release camera, finalize recordings
```

## 5. Detailed Algorithm

### Step 1: Initialization

1. Load the custom YOLOv8 checkpoint.
2. Open the webcam.
3. Load the Haar face cascade when available.
4. Attempt to connect to the Arduino at the configured serial port and baud rate.
5. If the Arduino connection fails, use the system alarm fallback.
6. Load `zones.json`.
7. Initialize an empty incident state map:

```text
incident_state[zone_id] = {
    active,
    start_time,
    peak_count,
    image_filename,
    video_filename,
    video_writer
}
```

### Step 2: Acquire and prepare a frame

1. Read a frame from the camera.
2. If the frame cannot be read, stop or handle the camera error according to the runtime loop.
3. Periodically write a raw frame to `zone_reference.jpg`.
4. Check the modification time of `zones.json`.
5. If the file changed:
   - Finalize active incidents.
   - Reload the zone list.
   - Continue using the new configuration.

The raw frame is copied before display annotations are drawn. This ensures that saved evidence does not contain temporary UI labels.

### Step 3: Run YOLOv8 inference

Run the detector on the current frame:

```text
results = YOLO(frame)
```

For every returned detection:

1. Read the class ID, confidence, and bounding box `(x1, y1, x2, y2)`.
2. Keep the detection only if its class is `person`.
3. Reject it if:

```text
confidence < 0.6
```

4. Reject zero-width or zero-height boxes.
5. For boxes not touching the frame edge, calculate:

```text
aspect_ratio = height / width
```

   Reject boxes outside the current accepted range:

```text
0.5 <= aspect_ratio <= 4
```

Edge-touching boxes are retained because cropping makes their aspect ratio unreliable.

### Step 4: Optional face and age filtering

If age detection is disabled, every valid person detection is eligible for zone counting.

If age detection is enabled:

1. Crop the person bounding box from the frame.
2. Use the Haar cascade to check whether a face is present.
3. Reject the detection when no face is found.
4. Build a cache key from the approximate position:

```text
grid_key = (x1 // 80, y1 // 80)
```

5. Run DeepFace only when the frame interval is reached or the grid key has no cached result.
6. Estimate age:

```text
if estimated_age < 14:
    child_detected = True
else:
    child_detected = False
```

7. Reuse the cached classification on skipped frames.
8. Add only eligible detections to `detected_person_boxes`.

If age analysis fails, the implementation marks the result as unknown/non-child rather than treating an uncertain result as a confirmed child.

### Step 5: Determine whether a person overlaps a zone

The detector evaluates the full person bounding box against each zone. Let the person rectangle be:

```text
P = [px1, py1, px2, py2]
```

#### Rectangle zone

First normalize the zone coordinates:

```text
zx1 = min(x1, x2)
zy1 = min(y1, y2)
zx2 = max(x1, x2)
zy2 = max(y1, y2)
```

The rectangles overlap when:

```text
px1 < zx2 and px2 > zx1 and py1 < zy2 and py2 > zy1
```

#### Circle zone

For a circle with center `(cx, cy)` and radius `r`, find the closest point on the person rectangle:

```text
closest_x = clamp(cx, px1, px2)
closest_y = clamp(cy, py1, py2)
```

The person overlaps the circle when:

```text
(cx - closest_x)^2 + (cy - closest_y)^2 <= r^2
```

This is the rectangle-circle intersection test.

#### Freehand polygon zone

For a polygon with vertices `v1 ... vn`, the algorithm returns true if at least one of these conditions is satisfied:

1. A polygon vertex lies inside the person rectangle.
2. A person-rectangle corner lies inside the polygon using `pointPolygonTest`.
3. Any edge of the person rectangle intersects any polygon edge using an orientation-based line-segment intersection test.

Testing all three conditions handles:

- The person box being inside the polygon.
- The polygon being inside the person box.
- Partial boundary crossings where neither shape fully contains the other.

### Step 6: Count people per zone

For each zone:

```text
current_people = 0

for person_box in detected_person_boxes:
    if person_in_zone_check(person_box, zone):
        current_people += 1
```

The zone is exceeded when:

```text
zone_exceeded = current_people > maximum_people
```

Notice that equality is safe. For example, a zone allowing 2 people is safe at 0, 1, or 2 people and violated at 3 or more.

### Step 7: Update display and alarm

If `zone_exceeded` is false:

- Draw the zone in green.
- Display `People: current/maximum`.
- Finalize an active incident for that zone.

If `zone_exceeded` is true:

- Draw the zone in red.
- Display `LIMIT EXCEEDED` and an alert message.
- Highlight overlapping people in red.
- Start or continue the incident.
- Trigger the Arduino buzzer or system beep.

The implementation keeps alarm state for the overall monitoring loop, so the alarm can be stopped when no zone remains exceeded.

### Step 8: Manage the incident lifecycle

An incident is stateful and is tracked independently for each zone.

#### Start

When a zone changes from compliant to exceeded:

1. Create the date directory and `images`/`videos` subdirectories.
2. Save one raw JPEG snapshot.
3. Open an MP4 `VideoWriter`.
4. Store the start time, zone metadata, initial count, and file names.
5. Write a CSV row with status `RECORDING`.
6. Write the first evidence frame to the video.

#### Continue

While the zone remains exceeded:

1. Update the peak count:

```text
peak_count = max(peak_count, current_people)
```

2. Append the raw evidence frame to the video.
3. Keep the same snapshot, video file, and incident row.

#### Finalize

When the zone returns to its limit or below:

1. Release the video writer.
2. Replace the CSV `People Count` with the peak count.
3. Change status from `RECORDING` to `VIOLATION`.
4. Rebuild the daily summary.
5. Mark the incident inactive.

The same finalization is performed during shutdown and before replacing zones after a live configuration change.

## 6. Pseudocode

```text
load model
open camera
load zones
connect to Arduino or select system alarm

while application is running:
    frame = camera.read()
    if frame is invalid:
        stop loop

    refresh zone_reference.jpg periodically
    if zones.json was modified:
        finalize all active incidents
        load zones

    if detection has not started:
        draw zone editor UI
        if user confirms:
            save zones
            detection_started = true
        continue

    evidence_frame = copy(frame)
    detections = YOLO(frame)
    people = []

    for detection in detections:
        if detection.class != person:
            continue
        if detection.confidence < 0.6:
            continue
        if invalid_size_or_aspect_ratio(detection):
            continue
        if age_filter_enabled and not qualifying_person(detection):
            continue
        people.append(detection.bounding_box)

    any_zone_exceeded = false

    for zone in zones:
        count = number of people whose boxes overlap zone
        exceeded = count > zone.maximum_people

        if exceeded:
            any_zone_exceeded = true
            draw zone as exceeded
            start_or_continue_incident(zone, count, evidence_frame)
        else:
            draw zone as safe
            finalize_incident_if_active(zone)

    if any_zone_exceeded:
        alarm_on()
    else:
        alarm_off()

    show annotated frame

finalize all active incidents
alarm_off()
release camera and serial resources
```

## 7. Complexity

Let:

- `D` = number of YOLO detections in a frame.
- `Z` = number of zones.
- `P` = number of accepted person detections.
- `V` = number of vertices in a freehand polygon.

The detection model dominates the runtime and depends on the YOLOv8 implementation and hardware. The geometric counting stage is approximately:

- Rectangle zone: `O(P)`.
- Circle zone: `O(P)`.
- Freehand zone: `O(P * V)` in the worst case because rectangle edges are checked against polygon edges.
- All zones: `O(Z * P * V)` in the worst freehand case.

The age cache reduces the frequency of the expensive DeepFace operation from every frame to periodic checks per coarse position.

## 8. Correctness and Design Properties

- A person is counted independently for every zone they overlap.
- A single continuous violation creates one incident per zone, not one file per frame.
- The recorded peak count is not merely the count at the first alert frame.
- Zone changes cannot leave old incident recordings open.
- Clean evidence frames are separated from annotated display frames.
- Invalid zone types and missing geometry are rejected by the Flask API before saving.
- Date and evidence path validation limits dashboard access to the expected evidence structure.

## 9. Practical Limitations

- Bounding-box overlap can count a person whose box only partially enters a zone; this is intentionally conservative for safety monitoring.
- YOLO can produce false positives or miss people because of occlusion, lighting, blur, or unusual viewpoints.
- The age classifier is approximate and should not be used as a legal or safety-critical identity decision.
- Without persistent tracking, a person may be counted differently across frames as detections change.
- The algorithm assumes the camera and zone coordinate system remain aligned; moving the camera requires zone recalibration.

