"""
YOLO Model Training Script
Trains YOLOv8 model on COCO 2017 dataset for person detection
"""

from ultralytics import YOLO
import os
import yaml

def create_coco_yaml(dataset_path):
    """Create COCO dataset configuration for YOLO"""
    
    # COCO dataset structure
    coco_yaml = {
        'path': dataset_path,
        'train': 'train2017',
        'val': 'val2017',
        'test': 'test2017',
        
        # Class names (we're focusing on person detection)
        'names': {
            0: 'person',
            1: 'bicycle',
            2: 'car',
            3: 'motorcycle',
            4: 'airplane',
            5: 'bus',
            6: 'train',
            7: 'truck',
            8: 'boat',
            9: 'traffic light',
            10: 'fire hydrant',
            11: 'stop sign',
            12: 'parking meter',
            13: 'bench',
            14: 'bird',
            15: 'cat',
            16: 'dog',
            17: 'horse',
            18: 'sheep',
            19: 'cow',
            20: 'elephant',
            21: 'bear',
            22: 'zebra',
            23: 'giraffe',
            24: 'backpack',
            25: 'umbrella',
            26: 'handbag',
            27: 'tie',
            28: 'suitcase',
            29: 'frisbee',
            30: 'skis',
            31: 'snowboard',
            32: 'sports ball',
            33: 'kite',
            34: 'baseball bat',
            35: 'baseball glove',
            36: 'skateboard',
            37: 'surfboard',
            38: 'tennis racket',
            39: 'bottle',
            40: 'wine glass',
            41: 'cup',
            42: 'fork',
            43: 'knife',
            44: 'spoon',
            45: 'bowl',
            46: 'banana',
            47: 'apple',
            48: 'sandwich',
            49: 'orange',
            50: 'broccoli',
            51: 'carrot',
            52: 'hot dog',
            53: 'pizza',
            54: 'donut',
            55: 'cake',
            56: 'chair',
            57: 'couch',
            58: 'potted plant',
            59: 'bed',
            60: 'dining table',
            61: 'toilet',
            62: 'tv',
            63: 'laptop',
            64: 'mouse',
            65: 'remote',
            66: 'keyboard',
            67: 'cell phone',
            68: 'microwave',
            69: 'oven',
            70: 'toaster',
            71: 'sink',
            72: 'refrigerator',
            73: 'book',
            74: 'clock',
            75: 'vase',
            76: 'scissors',
            77: 'teddy bear',
            78: 'hair drier',
            79: 'toothbrush'
        }
    }
    
    yaml_path = 'coco_config.yaml'
    with open(yaml_path, 'w') as f:
        yaml.dump(coco_yaml, f, default_flow_style=False)
    
    print(f"✓ Created COCO config: {yaml_path}")
    return yaml_path


def train_yolo_model(epochs=50, imgsz=640, batch=16):
    """
    Train YOLOv8 model on COCO dataset
    
    Args:
        epochs: Number of training epochs
        imgsz: Image size for training
        batch: Batch size
    """
    
    print("=" * 60)
    print("YOLO MODEL TRAINING")
    print("=" * 60)
    
    # Check if dataset path exists
    if os.path.exists("dataset_path.txt"):
        with open("dataset_path.txt", "r") as f:
            dataset_path = f.read().strip()
        print(f"✓ Found dataset path: {dataset_path}")
    else:
        print("✗ Dataset path not found!")
        print("Please run 'python download_dataset.py' first")
        return None
    
    # Create COCO configuration
    coco_yaml = create_coco_yaml(dataset_path)
    
    # Initialize YOLOv8 model
    # You can use: yolov8n.pt (nano), yolov8s.pt (small), yolov8m.pt (medium), yolov8l.pt (large)
    print("\n" + "=" * 60)
    print("INITIALIZING YOLO MODEL")
    print("=" * 60)
    
    model = YOLO('yolov8n.pt')  # Using nano version for faster training
    print("✓ Loaded YOLOv8n (Nano) base model")
    
    # Train the model
    print("\n" + "=" * 60)
    print("STARTING TRAINING")
    print("=" * 60)
    print(f"Epochs: {epochs}")
    print(f"Image size: {imgsz}")
    print(f"Batch size: {batch}")
    print("=" * 60)
    
    try:
        results = model.train(
            data=coco_yaml,
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            name='danger_zone_detector',
            patience=10,  # Early stopping patience
            save=True,
            device=0,  # Use GPU if available, else CPU
            workers=4,
            project='runs/train'
        )
        
        print("\n" + "=" * 60)
        print("TRAINING COMPLETE!")
        print("=" * 60)
        
        # Save the best model
        best_model_path = 'runs/train/danger_zone_detector/weights/best.pt'
        if os.path.exists(best_model_path):
            # Copy to root directory for easy access
            import shutil
            shutil.copy(best_model_path, 'best_final.pt')
            print(f"✓ Best model saved to: best_final.pt")
        
        print("\nNext step:")
        print("Run 'python detect_danger_zone.py' to start detection")
        
        return model
        
    except Exception as e:
        print(f"\n✗ Training error: {e}")
        return None


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("CUSTOM YOLO MODEL TRAINING")
    print("=" * 60)
    print("\nThis will train a YOLO model from scratch on COCO dataset.")
    print("\nRequirements:")
    print("✓ Downloaded COCO dataset (run download_dataset.py first)")
    print("✓ Sufficient disk space (>100GB)")
    print("✓ GPU recommended for faster training")
    print("✓ Training time: 3-8 hours depending on hardware")
    print("=" * 60)
    
    proceed = input("\nReady to start training? (yes/no): ").strip().lower()
    
    if proceed in ['yes', 'y']:
        print("\n" + "=" * 60)
        print("STARTING TRAINING PROCESS")
        print("=" * 60)
        
        # Train the model
        train_yolo_model(epochs=50, imgsz=640, batch=16)
    else:
        print("\nTraining cancelled.")
        print("To start later, run: python train_model.py")
