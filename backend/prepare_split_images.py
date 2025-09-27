import json
import shutil
from pathlib import Path

# Paths
base_dir = Path("semantic_dataset")
ann_dir =  Path("data") / "processed" / "annotations"
raw_dir = base_dir / "raw_data" / "train2017"   # change if needed
out_base = base_dir / "data" / "images"

# Make sure output folders exist
(out_base / "train").mkdir(parents=True, exist_ok=True)
(out_base / "val").mkdir(parents=True, exist_ok=True)
(out_base / "test").mkdir(parents=True, exist_ok=True)

def copy_split(split):
    ann_file = ann_dir / f"{split}.json"
    with open(ann_file) as f:
        data = json.load(f)

    print(f"Copying {split}: {len(data['images'])} images")
    for img in data["images"]:
        src = raw_dir / img["file_name"]
        dst = out_base / split / img["file_name"]
        if not dst.exists():
            if src.exists():
                shutil.copy2(src, dst)  # or use os.symlink for faster setup
            else:
                print(f"⚠ Missing file: {src}")

for split in ["train", "val", "test"]:
    copy_split(split)

print("✅ Done! Images are now in semantic_dataset/data/images/{train,val,test}")