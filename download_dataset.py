"""
COCO 2017 Dataset Downloader
Downloads the COCO 2017 dataset for YOLO training
"""

import kagglehub
import os
import shutil

def download_coco_dataset():
    """Download COCO 2017 dataset from Kaggle"""
    
    print("=" * 60)
    print("DOWNLOADING COCO 2017 DATASET")
    print("=" * 60)
    print("\n📥 Download Info:")
    print("  - Size: ~25GB")
    print("  - Resumable: YES (Ctrl+C safe)")
    print("  - If interrupted, restart this script to resume")
    print("=" * 60)
    
    try:
        # Download latest version
        # kagglehub automatically resumes interrupted downloads
        # It uses a cache directory and checks existing files
        print("\nDownloading... (This may take 30-60 minutes)")
        print("Press Ctrl+C to pause - you can resume later\n")
        
        path = kagglehub.dataset_download("awsaf49/coco-2017-dataset")
        print(f"\n✓ Dataset downloaded successfully!")
        print(f"Path to dataset files: {path}")
        
        # Create a symbolic link or copy to a local directory
        dataset_dir = os.path.join(os.path.dirname(__file__), "coco_dataset")
        
        if not os.path.exists(dataset_dir):
            print(f"\nCreating dataset directory: {dataset_dir}")
            os.makedirs(dataset_dir, exist_ok=True)
        
        print(f"\nDataset location: {path}")
        print(f"Local directory: {dataset_dir}")
        
        # Save the path for future reference
        with open("dataset_path.txt", "w") as f:
            f.write(path)
        
        print("\n" + "=" * 60)
        print("DOWNLOAD COMPLETE!")
        print("=" * 60)
        print(f"\nNext steps:")
        print(f"1. Run 'python train_model.py' to train the YOLO model")
        print(f"2. The dataset path has been saved to 'dataset_path.txt'")
        
        return path
        
    except KeyboardInterrupt:
        print("\n\n⏸ Download paused by user (Ctrl+C)")
        print("=" * 60)
        print("DOWNLOAD INTERRUPTED")
        print("=" * 60)
        print("\n✓ Progress has been saved!")
        print("✓ Run this script again to resume from where you stopped")
        print("\nKagglehub cache location (partial files saved here):")
        cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "kagglehub")
        print(f"  {cache_dir}")
        print("\nTo resume: python download_dataset.py")
        return None
        
    except Exception as e:
        print(f"\n✗ Error downloading dataset: {e}")
        print("\nMake sure you have:")
        print("1. Installed kagglehub: pip install kagglehub")
        print("2. Set up Kaggle API credentials")
        print("\n💡 Tip: If download was interrupted, you can resume by")
        print("   running this script again. Progress is automatically saved.")
        return None

if __name__ == "__main__":
    download_coco_dataset()
