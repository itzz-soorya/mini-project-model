from ultralytics import YOLO

model = YOLO("best_final.pt")

frames = 0
frames_with_boxes = 0
total_boxes = 0

for result in model.predict(
    "VIRAT_S_000200_00_000100_000171.mp4",
    imgsz=1280,
    conf=0.1,
    stream=True,
    save=False,
    verbose=False,
):
    frames += 1
    count = len(result.boxes)
    total_boxes += count

    if count:
        frames_with_boxes += 1
        print(f"Frame {frames}: {count} detection(s)")

print(f"Total frames: {frames}")
print(f"Frames with detections: {frames_with_boxes}")
print(f"Total boxes: {total_boxes}")