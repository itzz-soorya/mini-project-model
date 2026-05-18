# 🚨 Danger Zone Detection System

An intelligent real-time person detection system that monitors danger zones and triggers alarms when someone enters restricted areas. Built with custom-trained YOLOv8 and OpenCV.

## 🎯 Features

- **Real-time Person Detection** using custom-trained YOLOv8
- **Custom Danger Zones** - Draw zones with mouse
- **Automatic Alarm** - Triggers when person enters danger zone
- **Age Detection** (Optional) - Filter for children only
- **Face Validation** - Reduces false positives
- **Fullscreen Monitoring** - Professional surveillance interface

## 📋 Requirements

- Python 3.8+
- Webcam
- Windows OS (for alarm sounds)
- GPU recommended (for training)
- 100GB+ disk space (for COCO dataset)

## 🚀 Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Download COCO 2017 Dataset

```bash
python download_dataset.py
```

This will download the COCO 2017 dataset (~25GB) required for training.

**Note:** You'll need to set up Kaggle API credentials first (see Kaggle API Setup section below).

### 3. Train Custom YOLO Model

```bash
python train_model.py
```

This trains a custom YOLOv8 model on the COCO dataset. Training takes 3-8 hours depending on hardware.

### 4. Run Detection System

```bash
python detect_danger_zone.py
```

## 🎮 How to Use

1. **Launch the application**
   ```bash
   python detect_danger_zone.py
   ```

2. **Draw Danger Zones**
   - Click and drag on the video to draw rectangular zones
   - Draw as many zones as needed
   - Zones appear in red

3. **Start Detection**
   - Press `ENTER` to confirm zones and start monitoring
   - System will detect persons entering danger zones

4. **Alarm System**
   - Alarm sounds when person enters danger zone
   - Alarm stops when zone is clear
   - "ALERT!" message displays on screen

5. **Controls**
   - `ENTER` - Start detection
   - `R` - Reset zones (draw new ones)
   - `ESC` - Exit application

## ⚙️ Configuration

Edit settings in `detect_danger_zone.py`:

```python
# Enable age detection (requires deepface)
ENABLE_AGE_DETECTION = False  # Set to True for child-only detection

# Age threshold for children
AGE_THRESHOLD = 14  # Years

# Detection confidence
if conf < 0.6:  # Adjust confidence threshold (0.0 - 1.0)
    continue
```

## 📁 Project Structure

```
mini-project-model/
├── detect_danger_zone.py      # Main application
├── train_model.py             # Model training script
├── download_dataset.py        # Dataset downloader
├── setup.py                   # Automated setup
├── requirements.txt           # Dependencies
├── README.md                  # This file
├── danger_zone_model.pt       # Trained YOLO model (created after setup)
├── alarm.wav                  # Alarm sound (optional)
└── runs/                      # Training outputs (if custom training)
```

## 🔧 Advanced Options

### Custom Alarm Sound

Place a `.wav` file named `alarm.wav` in the project directory. The system will use it automatically.

### Age Detection Setup

To enable age-based filtering:

1. Install DeepFace:
   ```bash
   pip install deepface tf-keras
   ```

2. Enable in code:
   ```python
   ENABLE_AGE_DETECTION = True
   ```

### GPU Acceleration

For faster processing, ensure you have CUDA-compatible GPU and install:

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

## 📊 Model Information

- **Model**: YOLOv8n (Nano) - Custom trained
- **Training Dataset**: COCO 2017 (80 object classes)
- **Training Time**: 3-8 hours (hardware dependent)
- **Primary Detection**: Person class (class 0)
- **Confidence Threshold**: 0.6 (adjustable)

## 🔐 Kaggle API Setup

Required for downloading the COCO dataset:

1. Go to https://www.kaggle.com/settings
2. Scroll to API section
3. Click "Create New API Token"
4. Place `kaggle.json` in:
   - Windows: `C:\Users\<YourUsername>\.kaggle\kaggle.json`
   - Linux/Mac: `~/.kaggle/kaggle.json`

## 🎛️ Troubleshooting

### Camera not opening
```bash
# Try different camera index
cap = cv2.VideoCapture(1)  # Change from 0 to 1
```

### Face cascade not loading
The system automatically tries OpenCV's built-in cascade. If face filter is disabled, detection still works.

### Alarm not playing
- Ensure `alarm.wav` exists, or system will use beep sound
- Check volume settings
- Verify file format is WAV

### Low FPS
- Use smaller camera resolution
- Disable age detection
- Ensure GPU is being used
- Use YOLOv8n (nano) model

### Import errors
```bash
# Reinstall dependencies
pip install --upgrade --force-reinstall -r requirements.txt
```

### Training taking too long
- Use GPU if available
- Reduce epochs in train_model.py (line 116)
- Reduce batch size if out of memory
- Use smaller model variant

## 🎯 Use Cases

- **Child Safety**: Monitor swimming pools, construction zones
- **Restricted Areas**: Server rooms, hazardous zones
- **Security**: Unauthorized access detection
- **Industrial Safety**: Dangerous machinery areas
- **Home Safety**: Stairs, balconies for toddlers

## 📝 Performance

| Model | FPS (CPU) | FPS (GPU) | Accuracy |
|-------|-----------|-----------|----------|
| YOLOv8n | 15-25 | 60-100 | High |
| YOLOv8s | 10-15 | 45-80 | Higher |
| YOLOv8m | 5-10 | 30-60 | Highest |

## 📈 Training Details

The model is trained using:
- **Dataset**: COCO 2017 (118K training images, 5K validation)
- **Epochs**: 50 (with early stopping)
- **Image Size**: 640x640
- **Batch Size**: 16
- **Optimizer**: AdamW
- **Loss Functions**: Box loss, Class loss, DFL loss

Training outputs are saved in `runs/train/danger_zone_detector/`

## 🤝 Contributing

Suggestions and improvements welcome! Areas for enhancement:
- Multi-camera support
- Cloud storage for alerts
- Mobile app notifications
- Sound level detection
- Motion tracking

## ⚠️ Disclaimer

This is a demonstration project. For production safety systems, consider:
- Redundant sensors
- Professional-grade cameras
- Backup power systems
- Regular maintenance
- Professional installation

## 📜 License

MIT License - Feel free to use and modify for your projects.

## 🙏 Credits

- **YOLOv8**: Ultralytics
- **COCO Dataset**: Microsoft COCO
- **OpenCV**: Open Source Computer Vision Library
- **DeepFace**: Age detection library

---

**Made with ❤️ for Safety and Security**

For questions or issues, please create an issue in the repository.
